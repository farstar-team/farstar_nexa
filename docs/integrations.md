# Provider integrations

Nexa keeps provider adapters behind a common account, webhook and send boundary. The mock adapter is intended for local development only and is rejected when `ENVIRONMENT=production`.

## Instagram

Real mode requires a Meta app configured for Instagram Login, a supported professional account, the permissions approved for the intended operations and public HTTPS callback URLs. Configure the application ID, app secret, redirect URI, webhook verification value and API version through the root-only environment file or the SUPER_ADMIN integration panel. Values saved by the panel are encrypted in PostgreSQL and are never returned to the browser.

Before production traffic, validate the complete OAuth callback, webhook verification/subscription, inbound event deduplication, keyword reply and provider send receipt with a dedicated test account. A missing credential must fail clearly; it must never silently enable the mock adapter.

## Telegram

Create a bot with BotFather. Set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME` without the `@` prefix and a random URL-safe `TELEGRAM_WEBHOOK_SECRET` containing 32–256 characters. Register the webhook with `sudo farstarnexa telegram-webhook` or the SUPER_ADMIN panel after HTTPS is available.

A signed-in user creates a one-time ten-minute link in the panel and opens it in a private chat with the bot. Group `/start` attempts are rejected, tokens are stored hashed/encrypted as appropriate, and successful Telegram jobs clear their raw payload. Reconcile the webhook after every domain change.

Never commit provider tokens, app secrets, webhook secrets or encryption keys. Use `.env.example` only as a placeholder reference.
