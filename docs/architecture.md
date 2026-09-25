# Architecture and V2 decisions

## Scope and milestones

V1 established deployment, authentication, provider-independent messaging and operational tooling. V2 adds commerce data and a versioned multi-action engine while preserving the original message rules. Application workflows are tested on SQLite and PostgreSQL; external Meta behavior and release changes remain separate acceptance gates.

## Service boundaries

The monorepo deploys seven Compose services: PostgreSQL, Redis, one-shot migration, API, worker, static frontend, and Caddy. The Python API and worker run as UID 10001 with a read-only filesystem, dropped capabilities and no Docker socket. Database/Redis ports are private to the Compose network. Only Caddy publishes host ports. Bind-mounted persistence is independent of image/release directories, so `docker compose down` does not remove it.

Python 3.13 is the container runtime. SQLAlchemy 2 and Alembic provide explicit queries and versioned forward migrations. PostgreSQL 17 is a supported mature major; infrastructure images resolve to checked multi-architecture digests. Runtime Python dependencies and frontend dependencies are locked. Caddy manages ACME HTTPS; this keeps certificate lifecycle separate from application code. Vite provides a static frontend without an unnecessary server rendering process. These decisions follow the [FastAPI container guidance](https://fastapi.tiangolo.com/deployment/docker/), [PostgreSQL support policy](https://www.postgresql.org/support/versioning/) and [Caddy HTTPS documentation](https://caddyserver.com/docs/automatic-https).

## Workspace and authorization model

Every user owns one workspace. Accounts, products, rates, media, leads, automations, conversations, messages and execution records carry a workspace foreign key. Public API reads/updates derive the workspace from the authenticated user; submitted workspace IDs never establish ownership. Related IDs are checked at each object boundary. Administrative user listing is available to ADMIN/SUPER_ADMIN. Server operations and integration credentials require SUPER_ADMIN. Normal admin privileges do not grant access to other users' content or tokens.

Roles are deliberately centralized in `security.PERMISSIONS`. Browser navigation is a convenience; backend checks enforce access. The schema can later introduce membership records without changing the provider contracts or messages' workspace ownership.

## Durable ingestion, execution and delivery

Incoming webhook acknowledgement follows the durable insertion of a PostgreSQL job. A unique provider event key rejects duplicates. Redis is not the source of truth for work: losing cache data cannot erase pending incoming messages. Redis supplies rate limiting and worker heartbeat only.

Workers claim jobs with `FOR UPDATE SKIP LOCKED`. Ingestion locks the connected account to serialize conversation creation, priority selection and customer/product cooldown checks. The first matching rule wins; a cooldown never falls through to a lower-priority rule. Text matching performs deterministic NFKC normalization, Arabic/Persian kaf and yeh conversion, diacritic removal and whitespace normalization.

V2 stores a validated `version: 2` flow plus action rows. Completed actions commit individually and are not replayed after a worker restart. `DELAY` changes the durable job's availability time instead of sleeping a worker. Sending first commits a `sending` marker; rate-limit responses can return to `pending` with bounded exponential backoff, but timeouts and crashes become `unknown` and are never automatically resent. Every real send rechecks account, owner, automation and product state immediately before the external call.

Comment webhook IDs provide event deduplication. Before a real private reply, the worker reads the original comment timestamp, media and sender from Meta, enforces the seven-day window and accepts only feed/reel surfaces. A follow-up DM requires a verified inbound message within the preceding 24 hours. Dry runs execute matching, pricing, templates and all actions but use separate simulated messages, create no leads and make no provider call.

`Provider.send` returns an actual provider receipt or raises a rejected/uncertain delivery result. Mock receipts are deterministic and explicitly prefixed `mock:`. Real sends use Instagram's official Graph endpoint. Before a send, the worker commits a `sending` marker. If a remote timeout or process crash leaves delivery uncertain, the record becomes `unknown` and is not automatically resent. This sacrifices automatic recovery of some unsent messages to avoid duplicated customer replies when the provider offers no idempotent-send guarantee. Failed incoming processing retries with bounded backoff. Successful Telegram job payloads are cleared; pending payloads are encrypted because they can contain linking tokens.

No application transaction can guarantee exactly-once effects at an external API. Operators must reconcile `unknown` delivery with the provider before taking further action. There is deliberately no automatic resend for uncertain delivery.

## Database and migrations

Migration `0001` creates the foundation. Additive migration `0002` creates products, manual rates, Instagram media, leads and action execution rows, then extends existing automations and executions. Existing rules and messages are retained; disabled legacy rules become `PAUSED`. Foreign keys, event uniqueness, tenant relationships and indexes enforce the core relationships. Alembic records the schema version. Application startup never calls `create_all` or recreates tables. Migrations run in a separate service before API/worker startup. Automatic downgrade is disabled; recovery uses a validated backup and its compatible code.

Legacy timestamps remain UTC without a database timezone for compatibility. New commerce and flow timestamps are timezone-aware UTC; API serialization normalizes both generations to an explicit UTC offset. The frontend uses `Intl.DateTimeFormat` with the user's timezone and Persian calendar. Chart daily buckets remain UTC.

## Host operations boundary

The browser reauthenticates the owner before requesting backup, restore, deletion, release update or domain actions. API requests contain a bounded action and validated argument, then receive an HMAC signature. The host agent verifies signature, age, UUID and confirmation, and records a root-owned replay receipt outside the writable spool. The agent dispatches fixed Python functions using argument arrays, never browser-provided shell strings. It uses atomic writes with random temporary names and does not follow submitted symlinks.

The agent is still a privileged component. An API compromise can invoke the fixed operations using the application's signing key, including installing trusted repository releases. Maintain the upstream repository and owner accounts as privileged infrastructure. The agent can be disabled entirely while retaining CLI operations.

## Extension points

Add a provider adapter to the registry and normalize its webhooks into incoming jobs. New trigger/action types require a versioned schema, explicit dispatch and a recorded action result. The product JSON fields permit future variants/packages without storing prices as floating point. Teams, billing, AI services and full variant pricing are outside V2. One external message per trigger remains a deliberate Meta/private-reply safety boundary; non-message actions can be composed around it.
