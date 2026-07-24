#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-root@177.7.35.32}"
REMOTE_DIR="${REMOTE_DIR:-/var/www/palmeiras-web}"
REMOTE_STAGE="${REMOTE_DIR}.incoming"
SERVICE_NAME="${SERVICE_NAME:-palmeiras-web}"
APP_PORT="${APP_PORT:-5001}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

if [[ ! -f requirements.lock ]]; then
  echo "requirements.lock not found; run this script from the Palmeiras Web project." >&2
  exit 1
fi

if [[ "${REMOTE_DIR}" != /var/www/* || "${REMOTE_STAGE}" != "${REMOTE_DIR}.incoming" ]]; then
  echo "Refusing to deploy outside the expected /var/www release path." >&2
  exit 1
fi

ssh "${REMOTE_HOST}" "install -d -m 0755 '${REMOTE_STAGE}'"

rsync -az --delete \
  --exclude='/.git/' \
  --exclude='/.env' \
  --exclude='/.env.*' \
  --exclude='/.venv/' \
  --exclude='/venv/' \
  --exclude='/.pytest_cache/' \
  --exclude='/.ruff_cache/' \
  --exclude='/screenshots/' \
  --exclude='/apps/android/' \
  --exclude='/apps/ios/' \
  --exclude='**/build/' \
  --exclude='**/xcuserdata/' \
  --exclude='**/__pycache__/' \
  --exclude='*.py[cod]' \
  --exclude='*.log' \
  --exclude='*.err' \
  "${PROJECT_ROOT}/" "${REMOTE_HOST}:${REMOTE_STAGE}/"

ssh "${REMOTE_HOST}" \
  "REMOTE_DIR='${REMOTE_DIR}' REMOTE_STAGE='${REMOTE_STAGE}' SERVICE_NAME='${SERVICE_NAME}' APP_PORT='${APP_PORT}' bash -s" <<'REMOTE'
set -euo pipefail

if [[ ! -f /etc/palmeiras-web.env ]]; then
  echo "Missing /etc/palmeiras-web.env on the server." >&2
  exit 1
fi

set -a
. /etc/palmeiras-web.env
set +a

missing_env=()
for required_var in SUPABASE_URL SUPABASE_ANON_KEY; do
  if [[ -z "${!required_var:-}" ]]; then
    missing_env+=("${required_var}")
  fi
done
if (( ${#missing_env[@]} )); then
  echo "Missing required Palmeiras environment variable(s): ${missing_env[*]}" >&2
  exit 1
fi

missing_collector_env=()
for collector_var in SUPABASE_KEY FOOTBALL_API_KEY; do
  if [[ -z "${!collector_var:-}" ]]; then
    missing_collector_env+=("${collector_var}")
  fi
done
if (( ${#missing_collector_env[@]} )); then
  echo "Warning: collector will fail until these variable(s) are added to /etc/palmeiras-web.env: ${missing_collector_env[*]}" >&2
fi

cd "${REMOTE_STAGE}"
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.lock

chown -R root:root "${REMOTE_STAGE}"
find "${REMOTE_STAGE}" -path "${REMOTE_STAGE}/.venv" -prune -o -type d -exec chmod 755 {} +
find "${REMOTE_STAGE}" -path "${REMOTE_STAGE}/.venv" -prune -o -type f -exec chmod 644 {} +
chmod +x "${REMOTE_STAGE}/scripts/deploy-vps.sh"
install -d -o www-data -g www-data -m 775 "${REMOTE_STAGE}/apps/web/static/crests"
chown -R www-data:www-data "${REMOTE_STAGE}/apps/web/static/crests"
backup_suffix="backup-$(date +%Y%m%d%H%M%S)"
web_unit="/etc/systemd/system/${SERVICE_NAME}.service"
collector_unit="/etc/systemd/system/palmeiras-collector.service"
collector_timer="/etc/systemd/system/palmeiras-collector.timer"
for unit_file in "${web_unit}" "${collector_unit}" "${collector_timer}"; do
  if [[ -f "${unit_file}" ]]; then
    cp -a "${unit_file}" "${unit_file}.${backup_suffix}"
  fi
done

nginx_site="/etc/nginx/sites-available/palmeiras-web"
nginx_backup="${nginx_site}.${backup_suffix}"
if [[ -f "${nginx_site}" ]]; then
  cp -a "${nginx_site}" "${nginx_backup}"
fi
install -m 0644 "${REMOTE_STAGE}/deploy/nginx-palmeiras.conf" "${nginx_site}"
if ! nginx -t; then
  if [[ -f "${nginx_backup}" ]]; then
    cp -a "${nginx_backup}" "${nginx_site}"
    nginx -t
  fi
  echo "Nginx validation failed; the previous site configuration was restored." >&2
  exit 1
fi

install -m 0644 "${REMOTE_STAGE}/deploy/palmeiras-web.service" "${web_unit}"
install -m 0644 "${REMOTE_STAGE}/deploy/palmeiras-collector.service" "${collector_unit}"
install -m 0644 "${REMOTE_STAGE}/deploy/palmeiras-collector.timer" "${collector_timer}"

previous_release="${REMOTE_DIR}.previous"
failed_release="${REMOTE_DIR}.failed-$(date +%Y%m%d%H%M%S)"
rollback_needed=0

rollback() {
  exit_code=$?
  if (( rollback_needed )); then
    rollback_needed=0
    echo "Deployment failed; restoring the previous release." >&2
    if [[ -d "${REMOTE_DIR}" ]]; then
      mv "${REMOTE_DIR}" "${failed_release}" || true
    fi
    if [[ -d "${previous_release}" ]]; then
      mv "${previous_release}" "${REMOTE_DIR}" || true
    fi
    if [[ -f "${nginx_backup}" ]]; then
      cp -a "${nginx_backup}" "${nginx_site}" || true
    fi
    for unit_file in "${web_unit}" "${collector_unit}" "${collector_timer}"; do
      if [[ -f "${unit_file}.${backup_suffix}" ]]; then
        cp -a "${unit_file}.${backup_suffix}" "${unit_file}" || true
      fi
    done
    systemctl daemon-reload || true
    systemctl restart "${SERVICE_NAME}" || true
    systemctl reload nginx || true
  fi
  exit "${exit_code}"
}
trap rollback EXIT

if [[ -d "${previous_release}" ]]; then
  rm -rf -- "${previous_release}"
fi
mv "${REMOTE_DIR}" "${previous_release}"
rollback_needed=1
mv "${REMOTE_STAGE}" "${REMOTE_DIR}"

systemctl daemon-reload
systemctl reload nginx
systemctl enable "${SERVICE_NAME}" >/dev/null
systemctl restart "${SERVICE_NAME}"
systemctl is-active --quiet "${SERVICE_NAME}"
systemctl enable palmeiras-collector.timer >/dev/null
systemctl restart palmeiras-collector.timer
systemctl is-active --quiet palmeiras-collector.timer
systemctl start --no-block palmeiras-collector.service || true

for attempt in {1..20}; do
  if curl --fail --silent --show-error --max-time 5 "http://127.0.0.1:${APP_PORT}/api/v1/health" >/tmp/palmeiras-web-health.json; then
    cat /tmp/palmeiras-web-health.json
    break
  fi
  if [[ "${attempt}" == "20" ]]; then
    systemctl status "${SERVICE_NAME}" --no-pager -l >&2 || true
    journalctl -u "${SERVICE_NAME}" -n 80 --no-pager >&2 || true
    exit 1
  fi
  sleep 1
done

curl --fail --silent --show-error --max-time 10 "https://palmeiras.rodrigolanna.com.br/" >/dev/null
curl --fail --silent --show-error --max-time 10 "https://palmeiras.rodrigolanna.com.br/api/v1/health" >/dev/null

rollback_needed=0
trap - EXIT
REMOTE
