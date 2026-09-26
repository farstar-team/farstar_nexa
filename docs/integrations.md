# Provider integrations

Nexa keeps provider adapters behind a common account, webhook and send boundary. The mock adapter is intended for local development only and is rejected when `ENVIRONMENT=production`.

## Instagram

Real mode requires a Meta app configured for Instagram Login, a supported professional account, the permissions approved for the intended operations and public HTTPS callback URLs. Configure the application ID, app secret, redirect URI, webhook verification value and API version through the root-only environment file or the SUPER_ADMIN integration panel. Values saved by the panel are encrypted in PostgreSQL and are never returned to the browser.

Before production traffic, validate the complete OAuth callback, webhook verification/subscription, inbound event deduplication, keyword reply and provider send receipt with a dedicated test account. A missing credential must fail clearly; it must never silently enable the mock adapter.

## Google login

Google sign-in is disabled until both `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set in the root-only environment file. In Google Cloud Console, create a Web application OAuth client, add the current public origin as an authorized JavaScript origin, and add this exact authorized redirect URI:

`https://YOUR_DOMAIN/api/auth/google/callback`

The callback is derived from `BASE_URL`, so changing the domain and applying the configuration updates it without changing database records. The server stores only Google's stable subject identifier; the Google access token is never stored.

Nexa 0.2 uses only documented Instagram Login operations: `GET /<IG_USER_ID>/media` for owned professional media, comment webhook fields, `GET /<IG_COMMENT_ID>?fields=id,timestamp,media,from` to verify the original comment, and `POST /<IG_USER_ID>/messages` with `recipient.comment_id` for a private reply. It requests `instagram_business_basic`, `instagram_business_manage_comments` and `instagram_business_manage_messages`. The Meta app must subscribe the connected account to `comments,messages` and obtain the required access level through App Review for accounts outside app roles.

Meta allows one private reply within seven days of a post/reel comment. The webhook notification time is not treated as comment creation time; Nexa reads the comment timestamp immediately before delivery. Follow-up messages are not sent until the recipient replies, and then only within the documented 24-hour window. Live-video comments and unsupported surfaces are rejected. Provider `unknown` results are quarantined for manual review rather than retried, avoiding duplicate customer messages.

Official references used for this release:

- [Private replies](https://developers.facebook.com/documentation/instagram-platform/private-replies)
- [Comment moderation and webhook payloads](https://developers.facebook.com/documentation/instagram-platform/comment-moderation)
- [IG Comment fields](https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-comment)
- [IG User media](https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/media)
- [App Review](https://developers.facebook.com/documentation/instagram-platform/app-review)

Exchange-rate live mode uses the fixed-host, no-key ExchangeRate-API open endpoint through a provider interface. Redis stores provider timestamps and an expiry; stale rates fail closed unless the seller explicitly selected a manual fallback. The source is a daily indicative reference and is not presented as Iran's free-market rate. Product or workspace manual rates are recommended when the seller needs a commercial market rate. Attribution: [Rates By Exchange Rate API](https://www.exchangerate-api.com).

## Telegram

Create a bot with BotFather. Set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME` without the `@` prefix and a random URL-safe `TELEGRAM_WEBHOOK_SECRET` containing 32–256 characters. Register the webhook with `sudo farstarnexa telegram-webhook` or the SUPER_ADMIN panel after HTTPS is available.

A signed-in user creates a one-time ten-minute link in the panel and opens it in a private chat with the bot. Group `/start` attempts are rejected, tokens are stored hashed/encrypted as appropriate, and successful Telegram jobs clear their raw payload. Reconcile the webhook after every domain change.

Never commit provider tokens, app secrets, webhook secrets or encryption keys. Use `.env.example` only as a placeholder reference.
