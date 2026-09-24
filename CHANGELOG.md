# Changelog

## [0.1.1] - 2026-09-24

- Centralized public integration URLs under the existing `BASE_URL` configuration and validated its origin format.
- Added current OAuth and webhook URLs to the owner integration settings panel without exposing credentials.
- Clarified the Persian message shown when Instagram integration is not configured.
- Added coverage for domain replacement, secure session cookies and logout revocation.
- Includes installer migration retries and image permissions fixes for restrictive host umasks.

## [0.1.0] - 2026-09-23

Initial Farstar Nexa foundation release.

- Added the FastAPI backend, PostgreSQL/Alembic schema, Redis worker and provider-independent automation pipeline.
- Added Persian RTL React/TypeScript panel with responsive light and dark themes.
- Added mock Instagram workflow, Instagram and Telegram integration boundaries, inbox and execution history.
- Added Docker Compose deployment, Ubuntu 24.04 installer, `farstarnexa` CLI, host agent and backup/restore/update operations.
- Added CI, unit tests, documentation and third-party license notices.

Production acceptance for a fresh Ubuntu 24.04 host, external Meta/Telegram credentials, live backup/restore and release updates remains an operational gate described in `docs/validation.md`.
