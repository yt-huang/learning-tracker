# AI Analysis Hub + Docker Compose Implementation Plan

> **For Hermes:** Use opencode plan→execute workflow or implement task-by-task with verification.

**Goal:** Split AI provider/key/model management into an independent `ai-hub` service with a web admin console, SQLite persistence, and internal API consumed by `learning-tracker`.

**Architecture:** `learning-tracker` remains the public product app on port 8010. `ai-hub` runs as a second Docker service on the same Docker network, persists configuration in a SQLite volume, exposes an admin UI on port 8020, and provides internal `/api/v1/analyze-learning-link` for AI analysis. `learning-tracker` calls `http://ai-hub:8020` from inside Docker and falls back to local heuristic generation if the hub is unavailable.

**Tech Stack:** Python 3.12, FastAPI, SQLite, SQLAlchemy, cryptography/Fernet for API key encryption, Docker Compose, vanilla HTML/CSS/JS admin UI.

---

## Task 1: Create AI Hub backend skeleton

**Objective:** Add an independent `ai-hub` service with FastAPI, health check, SQLite DB initialization, and Dockerfile.

**Files:**
- Create: `ai-hub/requirements.txt`
- Create: `ai-hub/Dockerfile`
- Create: `ai-hub/app/main.py`
- Create: `ai-hub/app/db.py`
- Create: `ai-hub/app/security.py`

**Verification:**

```bash
docker compose build ai-hub
docker compose up -d ai-hub
curl http://127.0.0.1:8020/health
```

Expected: JSON with `ok: true`.

---

## Task 2: Implement provider/model/key management

**Objective:** Store OpenAI-compatible providers and models in SQLite, encrypt API keys, and expose admin CRUD endpoints.

**Files:**
- Modify: `ai-hub/app/main.py`
- Modify: `ai-hub/app/db.py`
- Modify: `ai-hub/app/security.py`

**Data model:**
- `providers`: id, name, base_url, api_key_encrypted, enabled, created_at, updated_at
- `models`: id, provider_id, model_id, display_name, purpose, temperature, max_tokens, is_default, enabled, created_at, updated_at
- `call_logs`: id, client_name, template, provider_name, model_id, success, latency_ms, error_message, created_at

**Verification:**

```bash
curl -X POST http://127.0.0.1:8020/api/admin/providers \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer dev-admin-token' \
  -d '{"name":"OpenCode Go","baseUrl":"https://opencode.ai/zen/go/v1","apiKey":"test","enabled":true}'
```

Expected: provider created and API key not returned in plain text.

---

## Task 3: Add admin UI and guide page

**Objective:** Provide browser-based admin console for configuring providers, models, testing connection, reading setup instructions, and copying integration examples.

**Files:**
- Create: `ai-hub/app/static/admin.html`
- Create: `ai-hub/app/static/admin.css`
- Create: `ai-hub/app/static/admin.js`
- Create: `ai-hub/README.md`

**UI sections:**
1. 登录：admin/admin
2. Provider 配置：名称、Base URL、API Key、启用状态
3. Model 配置：模型 ID、显示名、用途、默认模型
4. 连接测试：调用 selected model 返回 pong
5. 配置引导：OpenCode Go 示例、Docker Compose 调用方式、learning-tracker 接入方式
6. 调用日志：最近 50 条

**Verification:**

Open `http://127.0.0.1:8020/`, login, create provider/model, open guide tab.

---

## Task 4: Implement AI analysis internal API

**Objective:** Add `/api/v1/analyze-learning-link` that fetches link context, selects default model, calls OpenAI-compatible provider, logs result, and falls back safely.

**Files:**
- Modify: `ai-hub/app/main.py`

**Request:**

```json
{
  "clientName": "learning-tracker",
  "url": "https://github.com/owner/repo",
  "goal": "学习这个项目",
  "level": "进阶",
  "hoursPerWeek": 5
}
```

**Response:**

```json
{
  "ok": true,
  "plan": { "aiUsed": true, "milestones": [] },
  "provider": "OpenCode Go",
  "model": "deepseek-v4-pro"
}
```

**Verification:**

```bash
curl -X POST http://127.0.0.1:8020/api/v1/analyze-learning-link \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer dev-internal-token' \
  -d '{"url":"https://github.com/yt-huang/learning-tracker","goal":"学习架构","level":"进阶","hoursPerWeek":5}'
```

---

## Task 5: Modify learning-tracker to call AI Hub

**Objective:** Make `learning-tracker` call `AI_HUB_URL` + `AI_HUB_TOKEN` first, while retaining current local AI/fallback path if hub is not configured or unavailable.

**Files:**
- Modify: `server/server.py`
- Modify: `README.md`

**Verification:**

```bash
docker compose up -d --build
curl -X POST http://127.0.0.1:8010/api/analyze-link \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://github.com/yt-huang/learning-tracker","goal":"学习架构","level":"进阶","hoursPerWeek":5}'
```

Expected: response returns a plan and includes hub-powered `analysisSummary` when configured.

---

## Task 6: Docker Compose two-service deployment

**Objective:** Run both services through Docker Compose with persistent volumes and no direct API key env in `learning-tracker`.

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.github/workflows/build-and-deploy.yml`
- Modify: `deploy.sh`
- Create: `.env.example`

**Compose services:**
- `learning-tracker`: public `8010:8010`, env `AI_HUB_URL=http://ai-hub:8020`, `AI_HUB_TOKEN=${AI_HUB_INTERNAL_TOKEN}`
- `ai-hub`: admin `8020:8020`, volume `ai_hub_data:/data`, env `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `AI_HUB_MASTER_KEY`, `AI_HUB_INTERNAL_TOKEN`

**Verification:**

```bash
docker compose ps
curl http://127.0.0.1:8010/
curl http://127.0.0.1:8020/health
```

---

## Task 7: Deploy and verify on cloud server

**Objective:** Push code to GitHub, deploy to Tencent server with Docker Compose, and verify public URLs.

**Commands:**

```bash
git add .
git commit -m "feat: add dockerized ai analysis hub"
git push origin main
ssh -i ~/tencent/cloud.pem ubuntu@106.54.242.3 'cd /opt/learning-tracker && sudo docker compose up -d --build'
```

**Verification:**
- `http://106.54.242.3:8010/` opens product app
- `http://106.54.242.3:8020/` opens AI Hub admin UI if port exposed
- `curl http://106.54.242.3:8020/health` returns ok
- `learning-tracker` can generate AI plans through `ai-hub`
