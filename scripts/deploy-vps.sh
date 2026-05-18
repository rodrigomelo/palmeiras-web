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
find "${REMOTE_DIR}" -path "${REMOTE_DIR}/.venv" -prune -o -type d -exec chmod 755 {} +
find "${REMOTE_DIR}" -path "${REMOTE_DIR}/.venv" -prune -o -type f -exec chmod 644 {} +
chmod +x "${REMOTE_DIR}/scripts/deploy-vps.sh"

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}" >/dev/null
systemctl restart "${SERVICE_NAME}"
systemctl is-active --quiet "${SERVICE_NAME}"

for attempt in {1..20}; do
  if curl --fail --silent --show-error "http://127.0.0.1:${APP_PORT}/api/health" >/tmp/palmeiras-web-health.json; then
    cat /tmp/palmeiras-web-health.json
    exit 0
  fi
  sleep 1
done

systemctl status "${SERVICE_NAME}" --no-pager -l >&2 || true
journalctl -u "${SERVICE_NAME}" -n 80 --no-pager >&2 || true
exit 1
REMOTE
