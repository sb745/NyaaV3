# NyaaV3 Docker Setup

Production-ready Docker configuration, updated for NyaaV3.
> [!WARNING]
> This Docker deployment has only been tested on Linux (so far). You may encounter permission issues or other unknown problems in a Windows/macOS environment.

## Quick Start

1. **Copy environment file:**
   ```bash
   cp .env.example .env
   ```

2. **Edit .env file:**
   Update at minimum the security keys:
   ```bash
   SECRET_KEY=your_secure_random_secret_key
   CSRF_SESSION_KEY=another_secure_random_key
   ```

3. **Build and start:**
   ```bash
   docker compose up -d --build
   ```

> [!TIP]
> If you are on Windows/macOS and use the dev override (which bind-mounts the repo into `/app`), you can run into `permission denied` for the entrypoint if the entrypoint lives under `/app`. This deployment avoids that by copying entrypoints into `/usr/local/bin` in the image. If you still hit permissions issues on Linux/WSL, run `./scripts/fix-docker-permissions.sh`.

> [!TIP]
> If MariaDB init scripts show `Permission denied`, this deployment also bakes MariaDB init scripts into a custom MariaDB image (see `.docker/mariadb/Dockerfile`) to avoid bind-mount permission problems.

4. **Access the application:**
   - Web interface: http://localhost:5500

## Architecture

The setup includes 4 core services (plus 2 optional Elasticsearch-related services):

1. **app** - Flask application with uWSGI (Python 3.14.2)
2. **mariadb** - MariaDB with binlog enabled
3. **redis** - Caching and rate limiting
4. **elasticsearch** - Search engine (*optional*)
5. **sync_es** - Binlog sync service for Elasticsearch (*optional*)

## Production vs Development

### Development Mode
By default, with `docker-compose.override.yml` present:
- Source code mounted for live reload
- Flask development server (not uWSGI)
- Debug mode enabled
- Health checks disabled

### Production Mode
Run with `-f docker-compose.yml` explicitly:
```bash
docker compose -f docker-compose.yml up -d
```
- Uses uWSGI with gevent workers
- Optimized for performance
- Health checks enabled
- Non-root user for security

## Elasticsearch

Elasticsearch is optional and disabled by default. The application uses MariaDB full-text search for all search functionality.

### Enabling
To start with Elasticsearch enabled, use Docker Compose profiles:
```bash
COMPOSE_PROFILES=es docker compose up -d
```

This will start both `elasticsearch` and `sync_es` services. **Remember to set `USE_ELASTIC_SEARCH=true` in your `.env` file.**

## Configuration

### Environment Variables
All configuration is done via environment variables in the `.env` file. Variables in `.env.example` are the most common/critical settings.

> [!IMPORTANT]
> Many additional configuration variables are **not listed** in `.env.example` but are automatically loaded with sensible defaults by the `.docker/generate_config.py` script. If you want to override any of these defaults, you can add them to your `.env` file and they will be picked up automatically.

### Customizing MariaDB Configuration
Edit `.docker/configs/mariadb.cnf` for MariaDB-specific settings.

### Customizing uWSGI Configuration
Edit `.docker/configs/uwsgi.ini` for production uWSGI settings.

## Initialization Process

On first start (or when `FORCE_INIT=true`), the container runs:
1. Waits for all services to be ready
2. Generates `config.py` from environment variables
3. Creates database with `db_create.py` (no migrations)
4. Sets up Elasticsearch indices with `create_es.sh`
5. Optionally imports data to Elasticsearch with `import_to_es.py` (`ES_RUN_IMPORT=true`)
6. Starts binlog sync in background (if enabled)
7. Starts uWSGI/Flask application

On subsequent starts, the app container skips the initialization steps using a marker file stored in the `app_state` volume.

> [!NOTE]
> When the repo is bind-mounted into `/app`, the container may not be able to write `/app/config.py` as a non-root user. The Docker setup therefore writes the generated config to `/app/state/config.py` and sets `PYTHONPATH=/app/state:/app`.

> [!NOTE]
> Webassets/Flask-Assets needs to write cache/build artifacts. When the repo is bind-mounted into `/app`, it cannot write under `/app/nyaa/static`. To avoid this, the Docker setup:
> - sets `NYAA_STATIC_FOLDER=/app/state/static`
> - sets `ASSETS_CACHE=/app/state/webassets-cache`
> - copies packaged static files from `/app/nyaa/static` into `/app/state/static` on first boot.

> [!NOTE]
> Torrent uploads write bencoded info dicts. The Docker setup routes these into `/app/state/info_dicts` via `INFO_DICTS_DIR` so uploads never try to write into the bind-mounted repo (`/app/info_dicts`).

> [!NOTE]
> Docker named volumes are often created as `root:root`.
> The app image starts as root, fixes ownership/permissions on `/app/state`, `/app/logs`, `/app/torrents`, then drops to the non-root user.

### Binlog permissions for `sync_es`
`sync_es.py` reads the MariaDB binlog, so the DB user must have replication-related privileges.

This repo includes an init script at:
- `.docker/configs/mariadb-init/01-binlog-permissions.sh`

It is mounted into the MariaDB container at `/docker-entrypoint-initdb.d/` and runs **only when the MariaDB data directory is first initialized** (fresh `mariadb_data` volume).

If you already have an existing `mariadb_data` volume, you must either run the GRANTs manually once, or recreate the `mariadb_data` volume.

## Data Persistence

All data is stored in Docker volumes:

| Volume | Purpose | Location in container |
|--------|---------|----------------------|
| `nyaav3_mariadb_data` | MariaDB database files | `/var/lib/mysql` |
| `nyaav3_elasticsearch_data` | Elasticsearch indices | `/usr/share/elasticsearch/data` |
| `nyaav3_redis_data` | Redis AOF files | `/data` |
| `nyaav3_app_torrents` | Uploaded torrent files | `/app/torrents` |
| `nyaav3_app_logs` | Application logs | `/app/logs` |
| `nyaav3_app_state` | Init marker + sync_es position/config | `/app/state` |

## Management Commands

### Rebuild application
```bash
docker compose build app
```

### Database backup
```bash
docker compose exec mariadb mysqldump -unyaauser -pnyaapass nyaav3 > backup.sql
```

### Database restore
```bash
docker compose exec -T mariadb mysql -unyaauser -pnyaapass nyaav3 < backup.sql
```
