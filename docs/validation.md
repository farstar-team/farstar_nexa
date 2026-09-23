# Validation and release acceptance

This document separates checks that can run from the source tree from checks that require a real Docker host, a fresh Ubuntu 24.04 server or external provider credentials. A passing unit test suite is not a production acceptance record.

## Local source checks

Run these commands from the repository root:

```bash
python -m pytest tests -q
ruff check backend cli scripts tests
cd frontend && npm ci && npm run lint && npm run typecheck && npm run build
docker compose config --quiet
```

The backend suite uses disposable SQLite by default. PostgreSQL coverage uses an empty dedicated database through `TEST_DATABASE_URL`. Never point tests at production data.

## Fresh-server acceptance

On a disposable Ubuntu Server 24.04 x86-64 or ARM64 host, record the result of:

1. Running `installer.sh` from the published `main` branch with no pre-existing Nexa directories.
2. First owner creation and login through the loopback SSH tunnel.
3. `farstarnexa status`, `doctor`, `config`, service restart and host reboot recovery.
4. Mock account, keyword rule, simulated inbound message, inbox and execution history.
5. Docker Compose down/up persistence, backup creation, checksum validation and restore on disposable data.
6. Domain activation, HTTPS issuance/renewal diagnostics and return to loopback mode.
7. Telegram webhook/linking and Instagram OAuth/webhook/send acceptance with real test accounts.
8. A published release update and the documented recovery procedure.

No result should be recorded as passed without its date, host, version and evidence. This workstation cannot replace a clean-server acceptance run when Docker or external provider access is unavailable.
