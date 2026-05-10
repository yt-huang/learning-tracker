#!/usr/bin/env bash
set -euo pipefail
APP_DIR=/opt/learning-tracker
IMAGE=ghcr.io/yt-huang/learning-tracker:latest
sudo mkdir -p "$APP_DIR"
sudo tee "$APP_DIR/docker-compose.yml" >/dev/null <<YAML
services:
  learning-tracker:
    image: $IMAGE
    container_name: learning-tracker
    restart: unless-stopped
    ports:
      - "8010:80"
YAML
cd "$APP_DIR"
sudo docker compose pull
sudo docker compose up -d
sudo docker ps --filter name=learning-tracker
