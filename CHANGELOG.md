# Changelog

## [0.5.5] - 2026-09-26

- Preserved the configured `www` host when changing the public domain and kept diagnostics compatible with multiple Caddy hosts.

## [0.5.4] - 2026-09-26

- Simplified product pricing into mutually exclusive converted-price and direct-price modes.
- Replaced the product SKU field with one required internal product identifier and clearer required markers.
- Added a scrollable Instagram-style media picker with thumbnail cards and explicit confirmation.

## [0.5.3] - 2026-09-26

- Replaced the remaining user-facing Flow wording with clear Persian automation wording.

## [0.5.2] - 2026-09-26

- Redirected the removed `/guide` URL to the root page at the Caddy layer.

## [0.5.1] - 2026-09-26

- Switched TGJU pricing from the official Sana feed to the free-market currency profiles, preserving rial values and converting to toman explicitly.
- Added a versioned rate cache namespace so previously cached Sana values cannot be reused.
- Moved the public guide to the root page and redirect `/guide` to `/`.
- Renamed Flow creation to Automation creation and added Persian help tips for automation fields and actions.
- Restyled select menus and all checkbox controls as accessible on/off switches.

## [0.5.0] - 2026-09-26

- Redesigned the public guide hero with a new Farstar Nexa logo and clearer Persian copy.
- Added page-specific animated usage guides to every authenticated panel page.
- Added quick automation presets for price replies and direct messages.
- Added post and Reel selection while creating or editing a product.
- Switched the active currency feed to TGJU Sana sell rates and removed alternate providers from the UI.
- Added a separate admin email settings page with generated sender addresses and test delivery.
- Added broadcast notifications for active users across panel, email and Telegram channels.
- Added optional Telegram channel membership locking for bot access.
- Improved all collapsible sections with consistent visual controls.

## [0.4.5] - 2026-09-26

- Removed the temporary test domain from the illustrated guide and render the current host dynamically.

## [0.4.4] - 2026-09-26

- Added a public illustrated usage guide at `/guide` with an animated desktop walkthrough.
- Added Persian FAQ content covering Inbox, Automations, pricing, support and Telegram Mini App usage.
- Added guide access from the landing page and authenticated panel navigation.
- Added clear explanations of Inbox and Automation behavior for new users.

## [0.4.3] - 2026-09-26

- Mark queued email and Telegram notifications as failed when worker delivery errors occur.

## [0.4.2] - 2026-09-26

- Updated the release safety-backup schema guard for the support and notification migration.

## [0.4.1] - 2026-09-26

- Enabled Telegram Mini App SDK loading under the production Content Security Policy.

## [0.4.0] - 2026-09-26

- Added support tickets and live-chat threads with admin replies and status management.
- Added panel notifications with queued email and Telegram delivery channels.
- Added encrypted SMTP settings, test-email delivery and password-reset email flow.
- Added an admin content editor for public landing and support copy.
- Added Telegram Mini App authentication and menu entry using the central public URL.
- Simplified activity text for users and restored a compact mobile-visible logout icon.
- Added polished collapsible sections and responsive support/notification layouts.

## [0.3.3] - 2026-09-26

- Implemented the optional Bonbast POST API provider using its documented sell-price fields and Toman-to-Rial normalization.

## [0.3.2] - 2026-09-26

- Display the active exchange-rate provider clearly in Workspace rate settings.

## [0.3.1] - 2026-09-26

- Show the configured Iranian rate-source attribution in the Workspace rate panel.

## [0.3.0] - 2026-09-26

- Added Iranian Sana exchange-rate support with cached, fail-closed provider handling and optional Bonbast configuration.
- Added direct seller pricing, independent online-rate and profit/fee toggles, and expanded safe message variables.
- Added cursor-aware variable insertion and drag-and-drop tokens in the flow editor.
- Added the public Persian product landing page and restored a visible mobile logout action.

## [0.2.1] - 2026-09-25

- Completed the product catalogue list with linked-media and automation counts, last-update timestamps, explicit activation controls and referentially safe deletion.

## [0.2.0] - 2026-09-25

- Added workspace-scoped products with Decimal pricing, explicit IRR/TOMAN conversion, manual and cached live exchange rates, adjustments, rounding, bounds and scheduled discounts.
- Added Instagram post/reel synchronization, pagination cursors and multi-select product links using the official Meta API boundary.
- Added versioned comment and message flows with safe templates, product/price sends, tags, leads, internal notes and durable delays.
- Added event deduplication, customer/product cooldowns, delivery-window checks, bounded rate-limit retries and action-level execution records.
- Added Persian RTL product, media, lead, flow-builder, dry-run, price-preview and execution-detail interfaces.
- Added an additive Alembic migration that preserves legacy users, sessions, accounts, messages and automations; disabled legacy rules migrate to `PAUSED`.
- Added backend and frontend coverage for tenant isolation, Decimal pricing, Persian matching, webhook formats, dry-run safety, retry/timeout behavior and core user workflows.

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
