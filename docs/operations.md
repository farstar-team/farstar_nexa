# Server operations and recovery

## CLI and owner panel

`sudo farstarnexa` opens the management menu. Noninteractive commands are `status`, `start`, `stop`, `restart`, `logs`, `doctor`, `repair`, `config`, `apply-config`, `admin create-admin`, `admin reset-password`, `telegram-webhook`, `backup`, `restore NAME`, `delete-backup NAME`, `domain DOMAIN`, `domain remove`, `ssl`, `check-update`, `update vX.Y.Z` and `uninstall`. Disruptive CLI operations prompt for an exact confirmation word; `--yes` is an explicit automation confirmation.

The SUPER_ADMIN panel queues backup/restore/deletion, domain, SSL, release and diagnostic operations. It requires the current password and an explicit confirmation for destructive/disruptive actions. An offline agent returns an honest unavailable error. Progress is visible while the API is online; stopping/recreating the API temporarily interrupts polling. The agent keeps operation results outside application containers. `journalctl -u farstarnexa-agent` shows agent service lifecycle; `farstarnexa logs` shows application/container logs locally. Raw shell output is never sent to normal browser users.

## Back up

Run `sudo farstarnexa backup`. Backups are stored under `/var/lib/farstarnexa/backups`. Each is a gzip tar archive containing exactly `database.dump`, `nexa.env`, `Caddyfile` and `metadata.json`. Metadata includes product, format 1, semantic version, Alembic schema, creation time, hostname and SHA-256 checksums. Archives are checked after creation. `pg_dump` streams directly to disk. API/worker writers pause for a consistent snapshot; PostgreSQL remains running.

The database contains integration configuration, encrypted provider credentials, Telegram links, messages and jobs. The environment includes the key ring needed to decrypt those credentials. Caddy certificates are deliberately excluded: they can be reissued for the restored domain. Redis limits/heartbeat and reproducible images are excluded. V1 has no uploaded media storage; a future storage feature must extend the backup format first.

Archives are not encrypted as a whole. They contain secrets, including encryption keys. Access is restricted to root and authenticated SUPER_ADMIN downloads; normal users cannot list or download them. Keep an encrypted off-server copy and periodically test its restore. A checksum detects corruption, not malicious archive authorship. Import only trusted backups; V1 offers no browser archive upload. A root operator may copy a trusted backup into the backup directory with correct permissions.

## Restore

`sudo farstarnexa restore NAME` validates the archive before pausing writers, checks exact application version and schema compatibility, creates a safety backup, validates the PostgreSQL dump catalog, and restores in a single transaction. Only regular files with the exact expected names are accepted; traversal, links and extra members are rejected. Database restoration deliberately overwrites current data and requires confirmation.

This server's database credentials and filesystem paths remain unchanged. Application encryption keys, provider settings and domain configuration come from the backup. A successful restore runs migrations, restarts services, and checks readiness. A failure after the safety backup leaves writers stopped for investigation. Do not repeatedly click restore. Review diagnostics and retain both the original and safety archives.

Restoring to another host needs the same Nexa version and a working PostgreSQL installation. DNS must be updated separately. Old browser sessions in the restored database can become valid with restored secrets; immediately invalidate sessions or rotate the session signing environment and revoke database sessions when recovering from a security incident.

## Domain and HTTPS

Set correct A/AAAA DNS records, verify reachability, and run `sudo farstarnexa domain panel.example.com`. Nexa checks resolution, persists `BASE_URL` and proxy host, switches to secure-cookie production mode, disables mock mode, recreates API/worker/proxy, and checks internal readiness. Internal readiness does not prove public DNS points to this host: inspect the diagnostic DNS/server addresses and test the public HTTPS URL yourself. Incorrect IPv6 records can prevent ACME issuance even when IPv4 works.

Caddy performs certificate issuance and renewal automatically. `farstarnexa ssl` reloads its current configuration and reports certificate/DNS information. It does not revoke certificates or force a premature ACME renewal. The owner panel shows certificate status, issuer and expiry once available. `domain remove` disables public bindings and returns to an SSH-tunnel-only panel while retaining certificates. If Telegram was configured, reconcile its webhook after every domain change; environment-configured bots are reconfigured automatically by the CLI. Panel-configured bots can be reconfigured with `farstarnexa telegram-webhook` or the owner panel. Update Meta's OAuth redirect and webhook URL in the Meta dashboard.

## Updates

`check-update` reads the official GitHub latest release and reports when none exists. `update vX.Y.Z` accepts only a newer semantic release tag from the fixed official repository. It checks disk space, clones to a new release directory, verifies VERSION, builds images before downtime, creates a pre-update backup, stops writers, migrates forward, starts new containers, and tests readiness before switching the current-release symlink. Configuration and bind-mounted data remain outside source directories. Never run `git reset --hard` over a production installation or replace a database with repository content.

Update failure retains the old `current` symlink and pre-update backup but may leave the database migrated. Writers are stopped. Old code must not be started against an incompatible schema. For recovery:

1. Record the failed target tag, old version and backup filename from CLI output or backup history.
2. Keep API/worker stopped; stop the agent to prevent conflicting operations.
3. Inspect the current Alembic revision and migration/release notes. If the schema is still the old compatible revision, start the old release and check readiness.
4. If migration changed the schema, use a compatible release and an explicitly confirmed backup restore. V1's normal restore command refuses version/schema mismatches. Cross-version disaster recovery needs an operator to restore the old dump into a separate PostgreSQL database, verify it with the old code, and switch only after validation. Do not bypass that guard on a live database.
5. Restart the agent and verify integrations after recovery.

Automated cross-version database rollback is intentionally not offered. Release signing, cross-version recovery tooling, real update fault-injection drills and scheduled off-server backups are next hardening work. No release update has been exercised against a published Nexa release yet.

## Repair and removal

`repair` validates Compose, rebuilds application images and applies forward migrations; it does not reset data or invent missing secrets. `uninstall` stops services and disables the agent, retaining configuration, source, certificates, database and backups. Any later physical deletion is an explicit operator decision outside this command.
