FROM mariadb:12.2.1-ubi10-rc

# Copy config + init scripts into the image to avoid Windows bind-mount permission issues.
# The official entrypoint will execute /docker-entrypoint-initdb.d/* on first init.

COPY --chmod=0644 .docker/configs/mariadb.cnf /etc/mysql/conf.d/custom.cnf
COPY --chmod=0755 .docker/configs/mariadb-init/01-binlog-permissions.sh /docker-entrypoint-initdb.d/01-binlog-permissions.sh

