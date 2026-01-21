# Multi-stage Dockerfile for NyaaV3 production
# Builder stage
FROM python:3.14.2-slim-trixie AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    default-libmysqlclient-dev \
    pkg-config \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create and activate virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Runtime stage
FROM python:3.14.2-slim-trixie

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    mariadb-client \
    redis-tools \
    curl \
    gosu \
    libmariadb3 \
    libmariadb-dev \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /bin/bash appuser

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create application directory
WORKDIR /app

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/torrents /app/logs && \
    chown -R appuser:appuser /app

# Copy Docker configuration files
COPY .docker/configs/uwsgi.ini /app/.docker/configs/uwsgi.ini
COPY .docker/entrypoint.sh /usr/local/bin/nyaav3-entrypoint.sh
COPY .docker/sync_es_entrypoint.sh /usr/local/bin/nyaav3-sync-es-entrypoint.sh
COPY .docker/wait-for-services.sh /usr/local/bin/nyaav3-wait-for-services.sh
COPY .docker/generate_config.py /usr/local/bin/nyaav3-generate-config.py
COPY create_es.sh /usr/local/bin/nyaav3-create-es.sh
COPY .docker/sitecustomize.py /usr/local/lib/python3.14/site-packages/sitecustomize.py

# Make scripts executable
RUN chmod 0755 \
    /usr/local/bin/nyaav3-entrypoint.sh \
    /usr/local/bin/nyaav3-sync-es-entrypoint.sh \
    /usr/local/bin/nyaav3-wait-for-services.sh \
    /usr/local/bin/nyaav3-generate-config.py \
    /usr/local/bin/nyaav3-create-es.sh

# Run as root so entrypoint can fix volume permissions then drop to appuser
USER root

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_APP="run.py" \
    FLASK_ENV="production" \
    PYTHONPATH="/app/state:/app"

# Expose port
EXPOSE 5500

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5500/ || exit 1

# Entrypoint
ENTRYPOINT ["/usr/local/bin/nyaav3-entrypoint.sh"]

# Default command (production uWSGI)
CMD ["uwsgi", "--ini", "/app/.docker/configs/uwsgi.ini"]
