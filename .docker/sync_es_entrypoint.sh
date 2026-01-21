#!/bin/bash
set -e

echo "Starting NyaaV3 sync_es service..."

APP_USER="${APP_USER:-appuser}"
STATE_DIR="${STATE_DIR:-/app/state}"

fix_volume_permissions() {
  if [ "$(id -u)" = "0" ]; then
    mkdir -p "${STATE_DIR}" /app/logs /app/torrents || true
    chown -R "${APP_USER}:${APP_USER}" "${STATE_DIR}" /app/logs /app/torrents || true
    chmod -R u+rwX "${STATE_DIR}" /app/logs /app/torrents || true
  fi
}

fix_volume_permissions

if [ "$(id -u)" = "0" ]; then
  exec gosu "${APP_USER}" "$0" "$@"
fi

# Ensure app config exists (sync_es imports nyaa.create_app('config'))
python /usr/local/bin/nyaav3-generate-config.py

# Ensure dependencies are reachable (mysql + redis + elasticsearch)
/usr/local/bin/nyaav3-wait-for-services.sh

SYNC_CFG="${SYNC_ES_CONFIG:-${STATE_DIR}/es_sync_config.json}"
SYNC_SAVE="${SYNC_ES_SAVE_LOC:-${STATE_DIR}/es_sync_position.json}"

if [ ! -f "${SYNC_CFG}" ]; then
  cat > "${SYNC_CFG}" << EOF
{
  "save_loc": "${SYNC_SAVE}",
  "mysql_host": "${DB_HOST:-mariadb}",
  "mysql_port": ${DB_PORT:-3306},
  "mysql_user": "${DB_USER:-nyaauser}",
  "mysql_password": "${DB_PASSWORD:-nyaapass}",
  "database": "${DB_NAME:-nyaav3}",
  "internal_queue_depth": ${SYNC_ES_INTERNAL_QUEUE_DEPTH:-10000},
  "es_chunk_size": ${SYNC_ES_CHUNK_SIZE:-10000},
  "flush_interval": ${SYNC_ES_FLUSH_INTERVAL:-5}
}
EOF
fi

if [ ! -f "${SYNC_SAVE}" ]; then
  echo "Initializing sync_es position file..."
  MASTER_STATUS=$(mysql -h "${DB_HOST:-mariadb}" -P "${DB_PORT:-3306}" -u "${DB_USER:-nyaauser}" -p"${DB_PASSWORD:-nyaapass}" -e "SHOW MASTER STATUS" 2>/dev/null | tail -n 1 || true)
  LOG_FILE=$(echo "${MASTER_STATUS}" | awk '{print $1}')
  LOG_POS=$(echo "${MASTER_STATUS}" | awk '{print $2}')
  if [ -n "${LOG_FILE}" ] && [ -n "${LOG_POS}" ]; then
    echo "{\"log_file\": \"${LOG_FILE}\", \"log_pos\": ${LOG_POS}}" > "${SYNC_SAVE}"
  else
    echo "{\"log_file\": \"\", \"log_pos\": 4}" > "${SYNC_SAVE}"
  fi
fi

exec python sync_es.py "${SYNC_CFG}"
