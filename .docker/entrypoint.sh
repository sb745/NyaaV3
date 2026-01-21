#!/bin/bash
set -e

echo "Starting NyaaV3 application..."

STATE_DIR="${STATE_DIR:-/app/state}"
INIT_MARKER="${STATE_DIR}/.docker_initialized"

APP_USER="${APP_USER:-appuser}"

fix_volume_permissions() {
    # Ensure mounted volumes are writable by the non-root runtime user.
    # On Docker Desktop / Windows this commonly comes in as root-owned.
    if [ "$(id -u)" = "0" ]; then
        mkdir -p "${STATE_DIR}" /app/logs /app/torrents || true
        mkdir -p "${STATE_DIR}/info_dicts" || true
        mkdir -p "${STATE_DIR}/static" "${STATE_DIR}/webassets-cache" || true
        chown -R "${APP_USER}:${APP_USER}" "${STATE_DIR}" /app/logs /app/torrents || true
        chmod -R u+rwX "${STATE_DIR}" /app/logs /app/torrents || true

        # Copy packaged static assets into writable static dir (first boot or if missing default avatar)
        if [ -d "/app/nyaa/static" ] && ( [ -z "$(ls -A "${STATE_DIR}/static" 2>/dev/null || true)" ] || [ ! -f "${STATE_DIR}/static/img/avatar/default.png" ] ); then
            # -n = don't overwrite existing, keep idempotent
            cp -rn /app/nyaa/static/. "${STATE_DIR}/static/" || true
            chown -R "${APP_USER}:${APP_USER}" "${STATE_DIR}/static" || true
        fi
    fi
}

# Function to generate config.py from environment variables
generate_config() {
    echo "Generating config.py from environment variables (python generator)..."
    python /usr/local/bin/nyaav3-generate-config.py
    echo "config.py generated successfully"
}

# Function to setup database
setup_database() {
    echo "Setting up database..."

    # Wait for MariaDB to be ready
    /usr/local/bin/nyaav3-wait-for-services.sh

    # Run database creation script (idempotent-ish)
    echo "Running db_create.py..."
    python db_create.py

    echo "Database setup completed"
}

# Function to setup Elasticsearch
setup_elasticsearch() {
    echo "Setting up Elasticsearch..."

    ES_URL="${ES_URL:-${ES_HOSTS:-http://elasticsearch:9200}}"
    ES_URL="${ES_URL%%,*}"

    # Wait for Elasticsearch to be ready, with timeout
    ATTEMPTS=0
    MAX_ATTEMPTS=12  # ~60 seconds with 5 second intervals
    until curl -s "${ES_URL}" > /dev/null; do
        ATTEMPTS=$((ATTEMPTS + 1))
        if [ $ATTEMPTS -gt $MAX_ATTEMPTS ]; then
            echo "WARNING: Elasticsearch did not become available within timeout"
            echo "Elasticsearch may be disabled (profile not enabled) or experiencing issues"
            return 1
        fi
        echo "Waiting for Elasticsearch... (attempt $ATTEMPTS/$MAX_ATTEMPTS)"
        sleep 5
    done

    # Create ES indices
    echo "Creating Elasticsearch indices..."
    ES_URL="${ES_URL}" /usr/local/bin/nyaav3-create-es.sh

    # Import data to ES (optional)
    if [ "${ES_RUN_IMPORT:-false}" = "true" ]; then
        echo "Importing data to Elasticsearch (ES_RUN_IMPORT=true)..."
        python import_to_es.py
    else
        echo "Skipping ES import (set ES_RUN_IMPORT=true to enable)"
    fi

    echo "Elasticsearch setup completed"
}

# Function to start binlog sync in background
start_binlog_sync() {
    echo "Starting binlog sync in background..."
    # Check if Elasticsearch is available before attempting to sync
    ES_URL="${ES_URL:-${ES_HOSTS:-http://elasticsearch:9200}}"
    ES_URL="${ES_URL%%,*}"

    if ! curl -s "${ES_URL}" > /dev/null 2>&1; then
        echo "WARNING: Elasticsearch is not available (profile may be disabled)"
        echo "Skipping binlog sync - it requires Elasticsearch"
        return 0
    fi

    SYNC_CFG="${SYNC_ES_CONFIG:-${STATE_DIR}/es_sync_config.json}"

    # Generate es_sync_config.json compatible with sync_es.py if not exists
    if [ ! -f "${SYNC_CFG}" ]; then
        cat > "${SYNC_CFG}" << EOF
{
  "save_loc": "${SYNC_ES_SAVE_LOC:-${STATE_DIR}/es_sync_position.json}",
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

    # Ensure save loc exists so sync_es can resume; initialize with SHOW MASTER STATUS if missing
    if [ ! -f "${SYNC_ES_SAVE_LOC:-${STATE_DIR}/es_sync_position.json}" ]; then
        echo "Initializing sync_es position file..."
        # best-effort; if it fails, sync_es will crash and restart
        MASTER_STATUS=$(mysql -h "${DB_HOST:-mariadb}" -P "${DB_PORT:-3306}" -u "${DB_USER:-nyaauser}" -p"${DB_PASSWORD:-nyaapass}" -e "SHOW MASTER STATUS" 2>/dev/null | tail -n 1 || true)
        LOG_FILE=$(echo "${MASTER_STATUS}" | awk '{print $1}')
        LOG_POS=$(echo "${MASTER_STATUS}" | awk '{print $2}')
        if [ -n "${LOG_FILE}" ] && [ -n "${LOG_POS}" ]; then
            echo "{\"log_file\": \"${LOG_FILE}\", \"log_pos\": ${LOG_POS}}" > "${SYNC_ES_SAVE_LOC:-${STATE_DIR}/es_sync_position.json}"
        else
            echo "{\"log_file\": \"\", \"log_pos\": 4}" > "${SYNC_ES_SAVE_LOC:-${STATE_DIR}/es_sync_position.json}"
        fi
    fi

    # Start sync_es.py in background
    python sync_es.py "${SYNC_CFG}" &

    echo "Binlog sync started"
}

# Main execution
main() {
    fix_volume_permissions

    # Drop privileges for the app runtime
    if [ "$(id -u)" = "0" ]; then
        exec gosu "${APP_USER}" "$0" "$@"
    fi

    mkdir -p "${STATE_DIR}" || true
    # Generate configuration
    generate_config

    # Setup database / ES only on first start (or when explicitly forced)
    if [ ! -f "${INIT_MARKER}" ] || [ "${FORCE_INIT:-false}" = "true" ]; then
        echo "First-time initialization (or FORCE_INIT=true)..."

        # Setup database
        setup_database

        # Setup Elasticsearch if enabled
        if [ "${USE_ELASTIC_SEARCH:-true}" = "true" ]; then
            setup_elasticsearch
        fi

        # Start binlog sync if enabled
        if [ "${ENABLE_BINLOG_SYNC:-true}" = "true" ]; then
            start_binlog_sync
        fi

        touch "${INIT_MARKER}"
    else
        echo "Initialization already done (marker: ${INIT_MARKER})."
        # Still wait for dependencies to avoid immediate crash loops
        /usr/local/bin/nyaav3-wait-for-services.sh

        if [ "${ENABLE_BINLOG_SYNC:-true}" = "true" ]; then
            start_binlog_sync
        fi
    fi
    
    # Execute the command (default is uWSGI)
    exec "$@"
}

# Run main function
main "$@"
