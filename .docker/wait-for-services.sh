#!/bin/bash
# Wait for services to be ready

set -e

echo "Waiting for services to be ready..."

# Wait for MariaDB
echo "Waiting for MariaDB..."
until mysqladmin ping -h "${DB_HOST:-mariadb}" -u "${DB_USER:-nyaauser}" -p"${DB_PASSWORD:-nyaapass}" --silent; do
    echo "MariaDB is unavailable - sleeping"
    sleep 2
done
echo "MariaDB is ready!"

# Wait for Redis
echo "Waiting for Redis..."
until redis-cli -h "${REDIS_HOST:-redis}" -p "${REDIS_PORT:-6379}" -a "${REDIS_PASSWORD:-redispass}" ping 2>/dev/null | grep -q "PONG"; do
    echo "Redis is unavailable - sleeping"
    sleep 2
done
echo "Redis is ready!"

# Wait for Elasticsearch (if enabled)
if [ "${USE_ELASTIC_SEARCH:-true}" = "true" ]; then
    echo "Waiting for Elasticsearch..."
    ES_URL="${ES_URL:-${ES_HOSTS:-http://elasticsearch:9200}}"
    ES_URL="${ES_URL%%,*}"
    until curl -s "${ES_URL}" > /dev/null; do
        echo "Elasticsearch is unavailable - sleeping"
        sleep 5
    done
    echo "Elasticsearch is ready!"
fi

echo "All services are ready!"
