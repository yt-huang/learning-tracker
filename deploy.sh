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
MYSQL_ROOT_PASSWORD=$(python3 - <<'PY'
import secrets; print(secrets.token_urlsafe(32))
PY
)
DB_NAME=ai_hub
DB_USER=ai_hub
DB_PASSWORD=$(python3 - <<'PY'
import secrets; print(secrets.token_urlsafe(32))
PY
)
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
      ai-hub:
        condition: service_healthy
    ports:
      - "${APP_PORT}:8010"
    environment:
      PORT: "8010"
      AI_HUB_URL: http://ai-hub:8020
      AI_HUB_TOKEN: \${AI_HUB_INTERNAL_TOKEN}

  mysql:
    image: mysql:8.4
    container_name: learning-tracker-mysql
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: \${MYSQL_ROOT_PASSWORD:-ai_hub_root_password}
      MYSQL_DATABASE: \${DB_NAME:-ai_hub}
      MYSQL_USER: \${DB_USER:-ai_hub}
      MYSQL_PASSWORD: \${DB_PASSWORD:-ai_hub_password}
    command: ["mysqld", "--character-set-server=utf8mb4", "--collation-server=utf8mb4_unicode_ci"]
    volumes:
      - ai_hub_mysql:/var/lib/mysql
    healthcheck:
      test: ["CMD-SHELL", "mysqladmin ping -h 127.0.0.1 -u\$\${MYSQL_USER} -p\$\${MYSQL_PASSWORD} --silent"]
      interval: 10s
      timeout: 5s
      retries: 20
      start_period: 30s

  ai-hub:
    image: ${AI_HUB_IMAGE}
    container_name: ai-analysis-hub
    restart: unless-stopped
    depends_on:
      mysql:
        condition: service_healthy
    ports:
      - "${AI_HUB_PORT}:8020"
    environment:
      PORT: "8020"
      DB_ENGINE: mysql
      DB_HOST: mysql
      DB_PORT: "3306"
      DB_NAME: \${DB_NAME:-ai_hub}
      DB_USER: \${DB_USER:-ai_hub}
      DB_PASSWORD: \${DB_PASSWORD:-ai_hub_password}
      ADMIN_USERNAME: \${ADMIN_USERNAME:-admin}
      ADMIN_PASSWORD: \${ADMIN_PASSWORD:-admin}
      AI_HUB_ADMIN_TOKEN: \${AI_HUB_ADMIN_TOKEN}
      AI_HUB_INTERNAL_TOKEN: \${AI_HUB_INTERNAL_TOKEN}
      AI_HUB_MASTER_KEY: \${AI_HUB_MASTER_KEY}
    healthcheck:
      test: ["CMD-SHELL", "python3 - <<'PY'\nimport urllib.request\nurllib.request.urlopen('http://127.0.0.1:8020/health', timeout=3).read()\nPY"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 20s

volumes:
  ai_hub_mysql:
COMPOSE

sudo docker compose pull
sudo docker rm -f learning-tracker ai-analysis-hub 2>/dev/null || true
sudo docker compose up -d
sudo docker image prune -f
sudo docker compose ps
