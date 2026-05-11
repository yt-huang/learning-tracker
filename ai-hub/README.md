# AI Analysis Hub

独立 AI 分析服务，用于统一配置 OpenCode Go / DeepSeek / Kimi / OpenAI 等 OpenAI-Compatible Provider、模型和 API Key，并通过 Docker 内网 API 给 `learning-tracker` 调用。

## 部署方式

生产环境中 AI Hub 不再直接暴露公网 Admin UI。`docker-compose.yml` 只 `expose: 8020`，由 `learning-tracker` 后端代理管理接口：

- 管理入口：登录 `Learning Tracker` 后，管理员进入「AI 模型配置」
- 普通用户入口：创建学习计划时，在「分析模型」下拉框选择已启用模型
- MySQL：复用虚拟机现有后端 MySQL（默认 `host.docker.internal:3306`）

```bash
docker compose up -d --build
```

第三方模型 Key 不需要写入 `.env`。管理员在前端页面录入后，AI Hub 加密保存到 MySQL。

## 可选环境变量

通常不需要设置。只有需要覆盖现有 MySQL/管理员配置时才使用：

```bash
DB_ENGINE=mysql
DB_HOST=host.docker.internal
DB_PORT=3306
DB_NAME=learning_tracker
DB_USER=lt_user
DB_PASSWORD=change-me
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin
AI_HUB_ADMIN_TOKEN=dev-admin-token
AI_HUB_INTERNAL_TOKEN=dev-internal-token
AI_HUB_MASTER_KEY=dev-master-key-change-me
AI_HUB_TIMEOUT=300          # learning-tracker 等待 AI Hub 分析结果
AI_PROVIDER_TIMEOUT=180     # AI Hub 等待第三方大模型返回
AI_DIRECT_TIMEOUT=180       # legacy direct-provider fallback timeout
```

说明：

- `AI_HUB_MASTER_KEY` 用于加密数据库里的 API Key。
- `AI_HUB_INTERNAL_TOKEN` 是业务系统内网调用分析 API 和只读模型列表时使用的 Bearer Token。
- `AI_HUB_ADMIN_TOKEN` 仅供 `learning-tracker` 后端代理管理员配置接口使用，不给浏览器普通用户。
- 本地开发如未安装 PyMySQL，或显式设置 `DB_ENGINE=sqlite`，会 fallback 到 SQLite：`/data/ai_hub.db`。

## Provider 对接方式

### DeepSeek

```text
名称：DeepSeek
Base URL：https://api.deepseek.com
模型：deepseek-chat / deepseek-reasoner
```

AI Hub 兼容 DeepSeek Chat Completions，并对 DeepSeek 跳过强制 `response_format`，避免兼容问题。

### Kimi / Moonshot

```text
名称：Kimi / Moonshot
Base URL：https://api.moonshot.cn/v1
模型：建议从 API 拉取；可手动添加 kimi-k2-0905-preview / kimi-latest
```

### OpenCode Go

```text
名称：OpenCode Go
Base URL：https://opencode.ai/zen/go/v1
模型：deepseek-v4-pro
```

## 内网调用 API

分析接口支持可选 `modelId`，不传则使用默认模型：

```bash
curl -X POST http://ai-hub:8020/api/v1/analyze-learning-link \
  -H 'Authorization: Bearer change...ken' \
  -H 'Content-Type: application/json' \
  -d '{
    "clientName":"learning-tracker",
    "url":"https://github.com/yt-huang/learning-tracker",
    "goal":"学习架构和实现",
    "level":"进阶",
    "hoursPerWeek":5,
    "modelId":"1"
  }'
```

只读模型列表接口：

```bash
curl http://ai-hub:8020/api/v1/models -H 'Authorization: Bearer change...ken'
```

管理员配置接口仍在 AI Hub 内部存在，但生产环境应只通过 `learning-tracker` 的 `/api/admin/ai/*` 代理访问。
