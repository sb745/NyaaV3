#!/usr/bin/env python3
"""Generate /app/config.py from environment variables.

Why this exists:
- The legacy entrypoint used Bash heredoc interpolation, which breaks easily for
  booleans (e.g. DEBUG=false becomes invalid Python), strings with quotes, etc.
- This generator normalizes types and safely quotes strings.

The goal is not to replicate every setting in config.example.py, but to provide
reasonable Docker defaults and keep env->config mapping explicit.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy.engine import URL


def env(name: str, default: Any | None = None) -> str | None:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    return v


def env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    v = v.strip().lower()
    if v in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "f", "no", "n", "off"}:
        return False
    # Fall back to default if value is unexpected
    return default


def env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    try:
        return int(v)
    except ValueError:
        return default


def py_repr(value: Any) -> str:
    """Return a deterministic, safe Python representation."""
    if isinstance(value, (dict, list, tuple, int, float, bool)) or value is None:
        return repr(value)
    # Strings: use json to ensure correct escaping then convert to python repr
    if isinstance(value, str):
        return json.dumps(value)
    return repr(value)


def main() -> None:
    site_flavor = env("SITE_FLAVOR", "nyaa")
    use_mysql = env_bool("USE_MYSQL", True)
    base_dir = "/app"

    def _strip(v: Any | None) -> Any | None:
        if isinstance(v, str):
            return v.strip()
        return v

    db_user = _strip(env("DB_USER", "nyaauser"))
    db_password = _strip(env("DB_PASSWORD", "nyaapass"))
    db_host = _strip(env("DB_HOST", "mariadb"))
    db_port = env_int("DB_PORT", 3306)
    db_name = env("DB_NAME", "nyaav3")

    if use_mysql:
        if not db_host:
            db_host = "mariadb"
        if str(db_host).lower() in {"localhost", "127.0.0.1"}:
            # Inside docker, localhost points to the *app* container.
            # We don't raise, but this is almost always a misconfiguration.
            # (kept silent by default to avoid noisy logs)
            pass
        # Build a safe URI; handles special characters in username/password.
        sqlalchemy_database_uri = URL.create(
            drivername="mysql+mysqldb",
            username=db_user,
            password=db_password,
            host=db_host,
            port=db_port,
            database=db_name,
            query={"charset": "utf8mb4"},
        ).render_as_string(hide_password=False)
    else:
        sqlalchemy_database_uri = f"sqlite:///{base_dir}/test.db?check_same_thread=False"

    es_hosts = env("ES_HOSTS", "http://elasticsearch:9200")
    # app expects a list in config
    es_hosts_list = [es_hosts]

    cfg: dict[str, Any] = {
        "DEBUG": env_bool("DEBUG", False),

        # Maintenance / raid mode
        "MAINTENANCE_MODE": env_bool("MAINTENANCE_MODE", False),
        "MAINTENANCE_MODE_MESSAGE": env(
            "MAINTENANCE_MODE_MESSAGE",
            "Site is currently in read-only maintenance mode.",
        ),
        "MAINTENANCE_MODE_LOGINS": env_bool("MAINTENANCE_MODE_LOGINS", True),
        "RAID_MODE_LIMIT_UPLOADS": env_bool("RAID_MODE_LIMIT_UPLOADS", False),
        "RAID_MODE_UPLOADS_MESSAGE": env(
            "RAID_MODE_UPLOADS_MESSAGE",
            "Anonymous uploads are currently disabled.",
        ),
        "RAID_MODE_LIMIT_REGISTER": env_bool("RAID_MODE_LIMIT_REGISTER", False),
        "RAID_MODE_REGISTER_MESSAGE": env(
            "RAID_MODE_REGISTER_MESSAGE",
            "Registration is currently being limited.",
        ),
        "SITE_NAME": env("SITE_NAME", "Nyaa"),
        "GLOBAL_SITE_NAME": env("GLOBAL_SITE_NAME", "Nyaa.si"),
        "SITE_FLAVOR": site_flavor,
        "EXTERNAL_URLS": {"fap": "***", "main": "***"},
        "CSRF_SESSION_KEY": env("CSRF_SESSION_KEY", "changeme_in_production"),
        "SECRET_KEY": env("SECRET_KEY", "changeme_in_production"),

        # Features (used at import-time in some modules)
        "USE_RECAPTCHA": env_bool("USE_RECAPTCHA", False),
        "USE_EMAIL_VERIFICATION": env_bool("USE_EMAIL_VERIFICATION", False),
        "ENABLE_GRAVATAR": env_bool("ENABLE_GRAVATAR", True),
        "ALLOW_PASSWORD_RESET": env_bool("ALLOW_PASSWORD_RESET", True),
        "ACCOUNT_RECAPTCHA_AGE": env_int("ACCOUNT_RECAPTCHA_AGE", 604800),

        # Upload limits / account limits
        "RATELIMIT_ACCOUNT_AGE": env_int("RATELIMIT_ACCOUNT_AGE", 604800),
        "MAX_UPLOAD_BURST": env_int("MAX_UPLOAD_BURST", 5),
        "UPLOAD_BURST_DURATION": env_int("UPLOAD_BURST_DURATION", 2700),
        "UPLOAD_TIMEOUT": env_int("UPLOAD_TIMEOUT", 900),
        "MINIMUM_ANONYMOUS_TORRENT_SIZE": env_int("MINIMUM_ANONYMOUS_TORRENT_SIZE", 1048576),
        "PER_IP_ACCOUNT_COOLDOWN": env_int("PER_IP_ACCOUNT_COOLDOWN", 86400),
        # Cookies
        "SESSION_COOKIE_SECURE": env_bool("SESSION_COOKIE_SECURE", True),
        "SESSION_COOKIE_HTTPONLY": env_bool("SESSION_COOKIE_HTTPONLY", True),
        "SESSION_COOKIE_SAMESITE": env("SESSION_COOKIE_SAMESITE", "Lax"),
        # DB
        "USE_MYSQL": use_mysql,
        "SQLALCHEMY_DATABASE_URI": sqlalchemy_database_uri,
        # Email
        "MAIL_BACKEND": env("MAIL_BACKEND", "smtp"),
        "MAIL_FROM_ADDRESS": env("MAIL_FROM_ADDRESS", "Sender Name <sender@domain.com>"),
        "SMTP_SERVER": env("SMTP_SERVER", ""),
        "SMTP_PORT": env_int("SMTP_PORT", 587),
        "SMTP_USERNAME": env("SMTP_USERNAME", ""),
        "SMTP_PASSWORD": env("SMTP_PASSWORD", ""),
        # Search
        "RESULTS_PER_PAGE": env_int("RESULTS_PER_PAGE", 75),
        "MAX_PAGES": env_int("MAX_PAGES", 100),
        "COUNT_CACHE_SIZE": env_int("COUNT_CACHE_SIZE", 256),
        "COUNT_CACHE_DURATION": env_int("COUNT_CACHE_DURATION", 30),
        "USE_BAKED_SEARCH": env_bool("USE_BAKED_SEARCH", False),
        "USE_ELASTIC_SEARCH": env_bool("USE_ELASTIC_SEARCH", True),
        "ENABLE_ELASTIC_SEARCH_HIGHLIGHT": env_bool("ENABLE_ELASTIC_SEARCH_HIGHLIGHT", False),
        "ES_MAX_SEARCH_RESULT": env_int("ES_MAX_SEARCH_RESULT", 1000),
        "ES_INDEX_NAME": env("ES_INDEX_NAME", site_flavor),
        "ES_HOSTS": es_hosts_list,

        # Tracker integration defaults
        "ENFORCE_MAIN_ANNOUNCE_URL": env_bool("ENFORCE_MAIN_ANNOUNCE_URL", False),
        "MAIN_ANNOUNCE_URL": env(
            "MAIN_ANNOUNCE_URL",
            "http://127.0.0.1:6881/announce",
        ),
        "TRACKER_API_URL": env("TRACKER_API_URL", "http://127.0.0.1:6881/api"),
        "TRACKER_API_AUTH": env("TRACKER_API_AUTH", "topsecret"),
        # Cache / redis
        "CACHE_TYPE": env("CACHE_TYPE", "redis"),
        "CACHE_THRESHOLD": env_int("CACHE_THRESHOLD", 8192),
        "CACHE_REDIS_HOST": env("REDIS_HOST", "redis"),
        "CACHE_REDIS_PORT": env_int("REDIS_PORT", 6379),
        "CACHE_REDIS_PASSWORD": env("REDIS_PASSWORD", "redispass"),
        "CACHE_KEY_PREFIX": env("CACHE_KEY_PREFIX", "catcache_"),
        # Rate limiting
        "RATELIMIT_UPLOADS": env_bool("RATELIMIT_UPLOADS", True),
        # Flask-Limiter expects RATELIMIT_STORAGE_URI
        "RATELIMIT_STORAGE_URI": env(
            "RATELIMIT_STORAGE_URI",
            f"redis://:{env('REDIS_PASSWORD','redispass')}@{env('REDIS_HOST','redis')}:{env_int('REDIS_PORT',6379)}/0",
        ),
        "RATELIMIT_STORAGE_URL": env(
            "RATELIMIT_STORAGE_URL",
            f"redis://:{env('REDIS_PASSWORD','redispass')}@{env('REDIS_HOST','redis')}:{env_int('REDIS_PORT',6379)}/0",
        ),
        "RATELIMIT_KEY_PREFIX": env("RATELIMIT_KEY_PREFIX", "nyaaratelimit_"),

        # Torrent storage
        "BACKUP_TORRENT_FOLDER": env("BACKUP_TORRENT_FOLDER", "torrents"),

        # Trusted requirements
        "TRUSTED_MIN_UPLOADS": env_int("TRUSTED_MIN_UPLOADS", 10),
        "TRUSTED_MIN_DOWNLOADS": env_int("TRUSTED_MIN_DOWNLOADS", 10000),
        "TRUSTED_REAPPLY_COOLDOWN": env_int("TRUSTED_REAPPLY_COOLDOWN", 90),

        # Commenting
        "EDITING_TIME_LIMIT": env_int("EDITING_TIME_LIMIT", 0),

        # Misc
        "MAX_FILES_VIEW": env_int("MAX_FILES_VIEW", 1000),

        # Unified writable dirs (avoid writing into bind-mounted /app)
        "DATA_DIR": env("DATA_DIR", os.getenv("STATE_DIR", "/app/state")),
        "INFO_DICTS_DIR": env(
            "INFO_DICTS_DIR",
            f"{os.getenv('STATE_DIR', '/app/state')}/info_dicts",
        ),
        # Keep torrents/logs defaults aligned with docker-compose volume mounts
        "TORRENTS_DIR": env("TORRENTS_DIR", "/app/torrents"),
        "LOG_DIR": env("LOG_DIR", "/app/logs"),

        # Flask-Assets / webassets
        # Keep build/cache artifacts out of the bind-mounted repo.
        "ASSETS_CACHE": env("ASSETS_CACHE", f"{os.getenv('STATE_DIR', '/app/state')}/webassets-cache"),
        "ASSETS_DEBUG": env_bool("ASSETS_DEBUG", False),
        "ASSETS_AUTO_BUILD": env_bool("ASSETS_AUTO_BUILD", True),
    }

    content = """# Auto-generated by .docker/generate_config.py
# Do not edit manually; change environment variables instead.

"""

    # Keep BASE_DIR for code that references it
    content += "import os\n\n"
    content += f"BASE_DIR = {py_repr(base_dir)}\n\n"

    for k in sorted(cfg.keys()):
        content += f"{k} = {py_repr(cfg[k])}\n"

    # Prefer writing to /app/state so this works even when /app is a read-only
    # bind-mount (common on Windows/macOS in dev).
    state_dir = Path(os.getenv("STATE_DIR", "/app/state"))
    state_dir.mkdir(parents=True, exist_ok=True)

    out_path = state_dir / "config.py"
    out_path.write_text(content, encoding="utf-8")

    # Best-effort compatibility: also write /app/config.py when possible
    # (some tooling may expect it), but don't fail if /app is not writable.
    legacy_path = Path("/app/config.py")
    try:
        legacy_path.write_text(content, encoding="utf-8")
    except PermissionError:
        pass


if __name__ == "__main__":
    main()
