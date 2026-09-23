# Farstar Nexa

**فاراستار نکسا** — a Persian-first messaging and automation platform. **A Farstar Product.**

[Official repository](https://github.com/farstar-team/farstar_nexa) · [Instagram @farstar_nexa](https://www.instagram.com/farstar_nexa/)

Nexa gives each user a personal workspace for connected accounts, conversations and keyword replies. Instagram is the first messaging adapter; the automation engine is independent of any one provider.

## V1 status

Version **0.1.0** is a working foundation, pending production acceptance on a fresh Ubuntu 24.04 server. Do not equate a green application test suite with a verified production installer or disaster recovery procedure. See [validation](docs/validation.md).

| Status | Features |
| --- | --- |
| Implemented and locally verified | Registration/login/logout, Argon2id passwords, session revocation, RBAC, workspace isolation, Persian RTL interface, mobile layout, light/dark mode, mock Instagram accounts, keyword rules, asynchronous test messages, inbox, execution history, user controls, encrypted integration settings |
| Implemented; external validation required | Official Instagram OAuth and webhook adapter, Telegram webhook/linking/inline controls, Docker deployment, Ubuntu installer, host CLI/agent, backup/restore, domain/automatic TLS, release updates |
| Planned | Email delivery for password recovery, token refresh scheduling, outbound delivery reconciliation, retention policies, proactive Telegram notifications, full English translation, teams, quotas/billing, more messaging providers, visual flows |

The mock provider is explicitly labelled **حالت آزمایشی** and cannot start under `ENVIRONMENT=production`. A missing external credential never causes a fake connection or an automatic switch to mock mode.

## Architecture

FastAPI, SQLAlchemy and Alembic serve the application API. PostgreSQL 17 holds durable state and transactional jobs; Redis handles atomic rate limits and worker heartbeats. React, TypeScript and Vite build the frontend. Caddy terminates HTTPS and routes API/webhook traffic; unprivileged Nginx serves frontend assets. The host operations agent has a small, validated command set; the web container has no Docker socket or host shell.

```text
backend/       API, service logic, providers, migrations, operations protocol
frontend/      React panels, translations, brand assets
cli/           Ubuntu server manager, backups, release/domain operations
docker/        Reproducible application images
deploy/        Caddy and static asset server configuration
scripts/       Development setup and deployment smoke checks
tests/         Auth, tenant isolation, jobs, webhooks, tokens and archive tests
docs/          Architecture, installation, operations, integrations and validation
```

See [architecture and decisions](docs/architecture.md) for transaction boundaries, message delivery tradeoffs and milestones.

## Install and first login

Target: a fresh **Ubuntu Server 24.04 LTS**, x86-64 or ARM64, with at least 2 CPU cores, 4 GiB RAM and enough disk space for images plus two copies of the database. These are starting recommendations, not measured capacity limits.

Once this source is published to the official repository's `main` branch:

```bash
curl -fsSL https://raw.githubusercontent.com/farstar-team/farstar_nexa/main/installer.sh | sudo bash
```

For an already-cloned checkout, run `sudo bash installer.sh`. The installer obtains the official repository; local uncommitted code is not installed by that command. The remote command is not usable while the official repository is empty.

The installer installs Docker/Compose, generates unique secrets, starts the services, runs migrations and prompts on your terminal for the first **SUPER_ADMIN** username, email and password. There is no default owner password. A rerun preserves configuration and data and does not recreate an existing owner.

Without a domain, the panel listens only on the server's loopback interface. From your computer:

```bash
ssh -L 8080:127.0.0.1:8080 root@SERVER_IP
```

Open `http://localhost:8080`, then sign in with the credentials you chose. For public access, add a domain and HTTPS. See [installation](docs/installation.md).

## Server management

Run `sudo farstarnexa` for the English menu. Common commands:

```bash
sudo farstarnexa status
sudo farstarnexa start
sudo farstarnexa restart
sudo farstarnexa logs
sudo farstarnexa doctor
sudo farstarnexa config
sudo farstarnexa admin reset-password
```

`stop`, `repair`, `apply-config`, `admin create-admin`, `telegram-webhook`, `uninstall`, and the operational commands below are also available. Uninstall stops services and retains all persistent files. See [operations](docs/operations.md).

## Domains and SSL

Point your domain's A/AAAA records to the VPS, allow inbound TCP 80/443, then:

```bash
sudo farstarnexa domain panel.example.com
sudo farstarnexa ssl
```

Caddy obtains and renews certificates automatically. Domain changes update `BASE_URL` and recreate only the relevant application/proxy services. Configure the new Meta redirect and webhook URLs in the Meta app dashboard. `farstarnexa domain remove` returns to loopback-only access; it retains certificate files for recovery. Domain and SSL operations are also queued from the SUPER_ADMIN panel.

## Backups, restore and updates

```bash
sudo farstarnexa backup
sudo farstarnexa restore nexa-YYYYMMDDTHHMMSS-xxxxxxxx.tar.gz
sudo farstarnexa check-update
sudo farstarnexa update v0.1.1
```

The example release must actually exist before it can be installed. Backups contain a PostgreSQL custom-format dump, application/environment secrets, domain configuration and a checked manifest. Writers pause during backup. Restore validates archive entries, checksums, version and schema, makes a safety backup, and uses a single database transaction. It requires explicit confirmation. Backups contain sensitive material and are **not encrypted archives**; protect downloaded copies and use encrypted off-server storage.

Updates stage an official version tag, build images before downtime, back up, migrate forward and health-check the new services. A failed update stops writers and retains old code plus the safety backup. It does not blindly roll back a changed database. Read the [recovery procedure](docs/operations.md) before production use. SUPER_ADMIN can request these operations from the panel with password reauthentication.

## Instagram and Telegram

The integration settings form in **مدیریت سیستم → وضعیت سیستم** stores Meta and Telegram credentials encrypted in PostgreSQL; saved values are never returned to the browser. Environment configuration remains supported, with saved panel values taking precedence.

Instagram real mode requires an official Meta app, Instagram Login, a supported professional account, appropriate permissions and public HTTPS callbacks. OAuth, subscription and message sends must all succeed before Nexa records a live connection. The adapter needs a real credentialed acceptance test and scheduled token refresh before sustained production use.

Create a bot with Telegram's BotFather. Configure its token, username without `@`, and a random webhook secret of 32–256 URL-safe characters, then choose **ثبت وب‌هوک تلگرام** in the owner panel or run `sudo farstarnexa telegram-webhook`. A signed-in user generates a one-time ten-minute link in **تلگرام** and opens it in a private bot chat. The bot supports account lists, automation controls with confirmation, execution totals and a panel link. See [integrations](docs/integrations.md).

## Development and testing

```bash
python scripts/dev-env.py
docker compose up --build -d
docker compose exec api python -m nexa.manage create-admin
```

Open `http://localhost:8080`. Development configuration explicitly enables the mock provider. Create a mock account, add a keyword rule, then use **آزمایش پیام ورودی**. Both the test tool and real webhooks enter the same job pipeline.

```bash
python -m venv .venv
# Activate .venv for your shell first.
pip install -r backend/requirements.lock -e './backend[dev]'
pytest tests -q
ruff check backend cli scripts tests
cd frontend
npm ci
npm run lint
npm run typecheck
npm run build
```

Tests use a disposable SQLite database by default. Set `TEST_DATABASE_URL` to an **empty dedicated test PostgreSQL database** for PostgreSQL tests. The suite clears all application tables in that database. CI includes PostgreSQL tests and a container persistence/backup/restore smoke workflow, with no production deployment. See [development and troubleshooting](docs/development.md).

## Security and license

Read [security](docs/security.md) before deploying. Keep `.env`, database dumps, backup archives, provider credentials and encryption keys out of Git. Losing the encryption keys makes stored provider credentials unrecoverable.

MIT license; third-party notices and the bundled font license are retained under [licenses](licenses/THIRD_PARTY.md).
