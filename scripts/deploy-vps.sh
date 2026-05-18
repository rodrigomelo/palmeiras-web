#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-root@177.7.35.32}"
REMOTE_DIR="${REMOTE_DIR:-/var/www/palmeiras-web}"
SERVICE_NAME="${SERVICE_NAME:-palmeiras-web}"
APP_PORT="${APP_PORT:-5001}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

if [[ ! -f requirements.txt ]]; then
  echo "requirements.txt not found; run this script from the Palmeiras Web project." >&2
  exit 1
fi

rsync -az --delete \
  --exclude='/.git/' \
  --exclude='/.env' \
  --exclude='/.env.*' \
  --exclude='/.venv/' \
  --exclude='/venv/' \
  --exclude='/.vercel/' \
  --exclude='/.pytest_cache/' \
  --exclude='/.ruff_cache/' \
  --exclude='**/__pycache__/' \
  --exclude='*.py[cod]' \
  --exclude='*.log' \
  --exclude='*.err' \
  "${PROJECT_ROOT}/" "${REMOTE_HOST}:${REMOTE_DIR}/"

ssh "${REMOTE_HOST}" \
  "REMOTE_DIR='${REMOTE_DIR}' SERVICE_NAME='${SERVICE_NAME}' APP_PORT='${APP_PORT}' bash -s" <<'REMOTE'
set -euo pipefail

if [[ ! -f /etc/palmeiras-web.env ]]; then
  echo "Missing /etc/palmeiras-web.env on the server." >&2
  exit 1
fi

cd "${REMOTE_DIR}"
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

chown -R root:root "${REMOTE_DIR}"

systemctl daemon-reload
systemctl restart "${SERVICE_NAME}"
systemctl is-active --quiet "${SERVICE_NAME}"

curl --fail --silent --show-error "http://127.0.0.1:${APP_PORT}/api/health" >/tmp/palmeiras-web-health.json
cat /tmp/palmeiras-web-health.json
REMOTE
