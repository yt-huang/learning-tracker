# AI Analysis Hub

独立 AI 分析管理系统，用于统一配置 OpenCode Go / DeepSeek / OpenAI 等 OpenAI-Compatible Provider、模型和 API Key，并通过内网 API 给 `learning-tracker` 调用。

## Docker Compose 默认部署（MySQL 持久化）

`docker-compose.yml` 已内置 MySQL 8.4，默认账号密码会自动创建，不需要为了第三方模型 Key 编写 `.env`：

```bash
docker compose up -d --build
```

- Admin UI: `http://服务器IP:8020/`
- Health: `http://服务器IP:8020/health`
- 默认账号：`admin / admin`
- MySQL 数据卷：`ai_hub_mysql`

首次进入后台后，在页面中完成配置：

1. Provider 页面输入名称、API URL（Base URL）和 API Key。
2. Models 页面手动添加模型 ID，或点击“从 API 拉取模型”批量导入。
3. 勾选默认模型后点击“测试默认模型”。

## 可选环境变量

通常不需要设置。只有需要覆盖默认 MySQL/管理员配置时才使用：

```bash
DB_ENGINE=mysql
DB_HOST=mysql
DB_PORT=3306
DB_NAME=ai_hub
DB_USER=ai_hub
DB_PASSWORD=ai_hub_password
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin
AI_HUB_ADMIN_TOKEN=dev-admin-token
AI_HUB_INTERNAL_TOKEN=dev-internal-token
AI_HUB_MASTER_KEY=dev-master-key-change-me
```

说明：

- `AI_HUB_MASTER_KEY` 用于加密数据库里的 API Key。
- `AI_HUB_INTERNAL_TOKEN` 是业务系统内网调用 API 时使用的 Bearer Token。
- 本地开发如未安装 PyMySQL，或显式设置 `DB_ENGINE=sqlite`，会 fallback 到 SQLite：`/data/ai_hub.db`。

## OpenCode Go 配置

在后台页面添加 Provider：

```text
名称：OpenCode Go
Base URL：https://opencode.ai/zen/go/v1
API Key：你的 OpenCode Go API Key
启用：是
```

添加 Model：

```text
Provider：OpenCode Go
模型 ID：deepseek-v4-pro
显示名称：DeepSeek V4 Pro
用途：learning_plan
默认：是
```

可选模型包括：

```text
deepseek-v4-flash
deepseek-v4-pro
glm-5
glm-5.1
kimi-k2.5
kimi-k2.6
mimo-v2.5
mimo-v2.5-pro
minimax-m2.5
minimax-m2.7
qwen3.5-plus
qwen3.6-plus
```

## 内网调用 API

```bash
curl -X POST http://127.0.0.1:8020/api/v1/analyze-learning-link \
  -H 'Authorization: Bearer change-internal-token' \
  -H 'Content-Type: application/json' \
  -d '{
    "clientName":"learning-tracker",
    "url":"https://github.com/yt-huang/learning-tracker",
    "goal":"学习架构和实现",
    "level":"进阶",
    "hoursPerWeek":5
  }'
```

## learning-tracker 接入

`learning-tracker` Docker 服务默认已经在 `docker-compose.yml` 中接入 AI Hub：

```yaml
environment:
  AI_HUB_URL: http://ai-hub:8020
  AI_HUB_TOKEN: dev-internal-token
```

`learning-tracker` 不再需要保存任何第三方模型 API Key；第三方 API URL 和 Key 都在 AI Hub 后台页面录入并保存到 MySQL。
