#!/usr/bin/env bash
set -euo pipefail

# Helper for Linux/WSL users to ensure docker entrypoint scripts are executable.
#
# NOTE:
# - On Windows bind mounts, executable bits may not be preserved.
# - The Dockerfile in this repo copies entrypoints into /usr/local/bin to avoid
#   bind-mount shadowing issues.
# - This script is still useful to keep the repo in a sane state.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

FILES=(
  .docker/entrypoint.sh
  .docker/sync_es_entrypoint.sh
  .docker/wait-for-services.sh
  create_es.sh
)

echo "Setting executable bit on: ${FILES[*]}"
chmod +x "${FILES[@]}"

if command -v git >/dev/null 2>&1; then
  echo "Updating git index to record executable bit (if supported)..."
  for f in "${FILES[@]}"; do
    git update-index --chmod=+x "$f" || true
  done
fi

echo "Done. Rebuild with: docker compose up --build"
