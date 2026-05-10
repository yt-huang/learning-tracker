#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/learning-tracker}"
APP_PORT="${APP_PORT:-8010}"
AI_HUB_PORT="${AI_HUB_PORT:-8020}"
IMAGE="${IMAGE:-ghcr.io/yt-huang/learning-tracker:latest}"
AI_HUB_IMAGE="${AI_HUB_IMAGE:-ghcr.io/yt-huang/learning-tracker-ai-hub:latest}"

sudo mkdir -p "$APP_DIR"
sudo chown "$USER:$USER" "$APP_DIR"
cd "$APP_DIR"

if [ ! -f .env ]; then
  cat > .env <<ENV
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin
AI_HUB_ADMIN_TOKEN=$(python3 - <<'PY'
import secrets; print(secrets.token_urlsafe(32))
PY
)
AI_HUB_INTERNAL_TOKEN=$(python3 - <<'PY'
import secrets; print(secrets.token_urlsafe(32))
PY
)
AI_HUB_MASTER_KEY=$(python3 - <<'PY'
import secrets; print(secrets.token_urlsafe(48))
PY
)
ENV
  chmod 600 .env
fi

cat > docker-compose.yml <<COMPOSE
services:
  learning-tracker:
    image: ${IMAGE}
    container_name: learning-tracker
    restart: unless-stopped
    depends_on:
      - ai-hub
    ports:
      - "${APP_PORT}:8010"
    environment:
      PORT: "8010"
      AI_HUB_URL: http://ai-hub:8020
      AI_HUB_TOKEN: \${AI_HUB_INTERNAL_TOKEN}
  ai-hub:
    image: ${AI_HUB_IMAGE}
    container_name: ai-analysis-hub
    restart: unless-stopped
    ports:
      - "${AI_HUB_PORT}:8020"
    environment:
      PORT: "8020"
      DB_PATH: /data/ai_hub.db
      ADMIN_USERNAME: \${ADMIN_USERNAME:-admin}
      ADMIN_PASSWORD: \${ADMIN_PASSWORD:-admin}
      AI_HUB_ADMIN_TOKEN: \${AI_HUB_ADMIN_TOKEN}
      AI_HUB_INTERNAL_TOKEN: \${AI_HUB_INTERNAL_TOKEN}
      AI_HUB_MASTER_KEY: \${AI_HUB_MASTER_KEY}
    volumes:
      - ai_hub_data:/data
volumes:
  ai_hub_data:
COMPOSE

sudo docker compose pull
sudo docker compose up -d
sudo docker image prune -f
sudo docker compose ps
