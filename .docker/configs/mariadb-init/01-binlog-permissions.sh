#!/bin/bash
set -euo pipefail

# This script runs on FIRST initialization of MariaDB (empty /var/lib/mysql).
# It grants binlog/replication permissions required by sync_es.py.
#
# Uses the same user created by MYSQL_USER (wired from DB_USER in compose).

echo "Granting binlog/replication permissions to ${MYSQL_USER}@% ..."

mysql -u root -p"${MYSQL_ROOT_PASSWORD}" <<SQL
GRANT REPLICATION SLAVE, BINLOG MONITOR ON *.* TO '${MYSQL_USER}'@'%';
GRANT REPLICATION CLIENT ON *.* TO '${MYSQL_USER}'@'%';
FLUSH PRIVILEGES;
SQL

echo "Binlog/replication permissions granted."

