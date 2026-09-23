#!/usr/bin/env bash
set -Eeuo pipefail
if [[ ${CI:-} != true ]]; then echo 'Run this script only in a disposable CI environment.'; exit 1; fi
python3 scripts/dev-env.py
sudo chown -R 10001:10001 runtime/operations runtime/backups
docker compose config --quiet
docker compose up --build -d
python3 scripts/smoke.py
docker compose down
docker compose up -d
python3 scripts/smoke.py

mkdir -p runtime/server-root
ln -s "$PWD" runtime/server-root/current
export NEXA_ROOT="$PWD/runtime/server-root"
export NEXA_DATA="$PWD/runtime"
export NEXA_CONFIG="$PWD/.env"
sudo -E python3 cli/main.py backup
archive=$(find runtime/backups -maxdepth 1 -name 'nexa-*.tar.gz' -printf '%f\n' | sort | tail -1)
sudo -E python3 cli/main.py restore "$archive" --yes
python3 scripts/smoke.py
