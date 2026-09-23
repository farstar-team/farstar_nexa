# Security notes

Nexa treats the environment file, encryption key ring, provider credentials, database dumps, backup archives, session material and runtime logs as sensitive operational data. They belong on the host's protected filesystem and must never be committed to Git. `.env.example` contains placeholders only.

Passwords use Argon2id. Browser sessions are revocable and protected by CSRF checks and secure-cookie production settings. Integration values saved through the panel are encrypted at rest; their presence is reported as a boolean rather than returning plaintext. Workspace ownership and role permissions are enforced in the API.

The API and worker run without the Docker socket, as an unprivileged user and with a read-only image filesystem. The host agent is still privileged: protect its signing key, service account and repository access. It accepts a fixed operation set and records replay markers outside the application containers.

Backups contain the database and the key material needed to decrypt provider settings. They are not encrypted archives in V1. Restrict them to root/SUPER_ADMIN access, use encrypted off-server storage and test restores on disposable data. Rotate keys and revoke sessions after a suspected compromise.

Public production mode requires HTTPS and refuses mock mode or insecure cookies. Domain, firewall, DNS, OAuth permissions and Telegram/Meta credentials remain deployment responsibilities; review `docs/installation.md` and `docs/operations.md` before exposing the service.
