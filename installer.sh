#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

if [[ ${EUID} -ne 0 ]]; then echo 'Run this installer as root or with sudo.' >&2; exit 1; fi
source /etc/os-release
if [[ ${ID} != ubuntu || ${VERSION_ID} != 24.04 ]]; then echo 'Ubuntu Server 24.04 LTS is required.' >&2; exit 1; fi
case "$(uname -m)" in x86_64|aarch64) ;; *) echo 'Unsupported architecture.' >&2; exit 1;; esac
exec 9>/var/lock/farstarnexa-install.lock
flock -n 9 || { echo 'Another installation is running.' >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl git python3 openssl
if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable" >/etc/apt/sources.list.d/docker.list
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker
install -d -m 0755 /opt/farstarnexa /opt/farstarnexa/releases
install -d -m 0700 /etc/farstarnexa
install -d -m 0755 /var/lib/farstarnexa /var/lib/farstarnexa/proxy
install -d -m 0700 -o 10001 -g 10001 /var/lib/farstarnexa/operations
install -d -m 0750 -o root -g 10001 /var/lib/farstarnexa/backups

if [[ ! -e /opt/farstarnexa/current ]]; then
    target="/opt/farstarnexa/releases/initial-$(date -u +%Y%m%dT%H%M%S)"
    git clone --depth 1 https://github.com/farstar-team/farstar_nexa.git "$target"
    ln -s "$target" /opt/farstarnexa/current
fi
if [[ ! -f /etc/farstarnexa/nexa.env ]]; then
    python3 - <<'PY'
import base64, os, secrets
from pathlib import Path
password = secrets.token_hex(32)
values = {
    'ENVIRONMENT': 'development', 'BASE_URL': 'http://localhost:8080', 'COOKIE_SECURE': 'false',
    'MOCK_MODE': 'false', 'REGISTRATION_ENABLED': 'true', 'SECRET_KEY': secrets.token_hex(32),
    'ENCRYPTION_KEYS': base64.urlsafe_b64encode(os.urandom(32)).decode(), 'POSTGRES_PASSWORD': password,
    'DATABASE_URL': f'postgresql+psycopg://nexa:{password}@postgres:5432/nexa',
    'REDIS_URL': 'redis://redis:6379/0', 'DATA_DIR': '/var/lib/farstarnexa', 'CADDY_SITE': ':80',
    'HTTP_BIND': '127.0.0.1:8080', 'HTTPS_BIND': '127.0.0.1:8443',
    'META_APP_ID': '', 'META_APP_SECRET': '', 'META_VERIFY_TOKEN': secrets.token_urlsafe(32),
    'META_API_VERSION': 'v23.0', 'TELEGRAM_BOT_TOKEN': '', 'TELEGRAM_BOT_USERNAME': '',
    'TELEGRAM_WEBHOOK_SECRET': secrets.token_urlsafe(32),
}
path = Path('/etc/farstarnexa/nexa.env')
path.write_text('\n'.join(f'{k}={v}' for k,v in values.items())+'\n')
path.chmod(0o600)
PY
fi
if [[ ! -f /var/lib/farstarnexa/proxy/Caddyfile ]]; then
    install -m 0644 /opt/farstarnexa/current/deploy/Caddyfile /var/lib/farstarnexa/proxy/Caddyfile
fi
cat >/usr/local/bin/farstarnexa <<'SH'
#!/bin/sh
exec python3 /opt/farstarnexa/current/cli/main.py "$@"
SH
chmod 0755 /usr/local/bin/farstarnexa
cat >/etc/systemd/system/farstarnexa-agent.service <<'UNIT'
[Unit]
Description=Farstar Nexa operations agent
After=docker.service network-online.target
Requires=docker.service
[Service]
Type=simple
ExecStart=/usr/local/bin/farstarnexa agent
Restart=on-failure
RestartSec=5
UMask=0077
PrivateTmp=true
NoNewPrivileges=true
[Install]
WantedBy=multi-user.target
UNIT
export NEXA_ENV_FILE=/etc/farstarnexa/nexa.env
export NEXA_RELEASE
NEXA_RELEASE=$(cat /opt/farstarnexa/current/VERSION)
cd /opt/farstarnexa/current
docker compose --env-file "$NEXA_ENV_FILE" build
if ! docker compose --env-file "$NEXA_ENV_FILE" up -d; then
    echo 'Farstar Nexa services failed to start. Migration and database logs follow:' >&2
    docker compose --env-file "$NEXA_ENV_FILE" logs --no-color --tail 100 migrate postgres >&2 || true
    exit 1
fi
farstarnexa start
farstarnexa doctor
echo 'Create the first owner account. Existing installations keep their owner account.'
docker compose --env-file "$NEXA_ENV_FILE" exec api python -m nexa.manage create-admin </dev/tty
systemctl daemon-reload
systemctl enable --now farstarnexa-agent.service
farstarnexa start
echo 'Farstar Nexa installed. No public HTTP login is enabled.'
echo 'From your computer: ssh -L 8080:127.0.0.1:8080 root@SERVER_IP'
echo 'Then open http://localhost:8080 and sign in with your chosen credentials.'
echo 'Add HTTPS later: sudo farstarnexa domain panel.example.com'
