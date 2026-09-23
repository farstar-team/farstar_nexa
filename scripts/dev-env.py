import base64
import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / ".env"
if path.exists():
    raise SystemExit(".env already exists; nothing changed.")
password = secrets.token_hex(32)
content = (root / ".env.example").read_text()
content = content.replace("SECRET_KEY=GENERATE_WITH_DEV_ENV_SCRIPT", "SECRET_KEY=" + secrets.token_hex(32))
content = content.replace(
    "ENCRYPTION_KEYS=GENERATE_WITH_DEV_ENV_SCRIPT",
    "ENCRYPTION_KEYS=" + base64.urlsafe_b64encode(os.urandom(32)).decode(),
)
content = content.replace("GENERATE_WITH_DEV_ENV_SCRIPT", password)
content = content.replace("TELEGRAM_WEBHOOK_SECRET=", "TELEGRAM_WEBHOOK_SECRET=" + secrets.token_urlsafe(32))
content = content.replace("META_VERIFY_TOKEN=", "META_VERIFY_TOKEN=" + secrets.token_urlsafe(32))
path.write_text(content)
path.chmod(0o600)
for folder in ("operations", "backups", "proxy"):
    (root / "runtime" / folder).mkdir(parents=True, exist_ok=True)
(root / "runtime/proxy/Caddyfile").write_text((root / "deploy/Caddyfile").read_text())
print("Development configuration generated. Run docker compose up --build -d.")
