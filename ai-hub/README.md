# AI Analysis Hub

独立 AI 分析管理系统，用于统一配置 OpenCode Go / DeepSeek / OpenAI 等 OpenAI-Compatible Provider、模型和 API Key，并通过内网 API 给 `learning-tracker` 调用。

## 默认地址

- Admin UI: `http://服务器IP:8020/`
- Health: `http://服务器IP:8020/health`
- 默认账号：`admin / admin`

## Docker 环境变量

```bash
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin
AI_HUB_ADMIN_TOKEN=change-admin-token
AI_HUB_INTERNAL_TOKEN=change-internal-token
AI_HUB_MASTER_KEY=change-master-key
DB_PATH=/data/ai_hub.db
```

说明：

- `AI_HUB_MASTER_KEY` 用于加密数据库里的 API Key。
- `AI_HUB_INTERNAL_TOKEN` 是业务系统内网调用 API 时使用的 Bearer Token。
- SQLite 数据库默认保存到 Docker volume `/data/ai_hub.db`。

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

`learning-tracker` Docker 服务只需要配置：

```yaml
environment:
  AI_HUB_URL: http://ai-hub:8020
  AI_HUB_TOKEN: ${AI_HUB_INTERNAL_TOKEN}
```

`learning-tracker` 不再需要保存任何第三方模型 API Key。
