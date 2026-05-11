# Learning Tracker

一个产品化的学习计划跟踪系统：输入学习链接，自动生成阶段、任务和学习日志跟踪体系。业务数据使用 **SQLite（sql.js）** 存储在浏览器中，并以 `.db` 文件形式持久化到 IndexedDB，不依赖 Firebase/Supabase 等实时数据库。

## 登录

- Learning Tracker 用户名：`admin`
- Learning Tracker 密码：`admin`
- AI Hub 管理后台默认用户名：`admin`
- AI Hub 管理后台默认密码：`admin`

## 功能

- 从学习链接自动生成学习计划
- AI 深度分析学习链接：通过独立 `AI Analysis Hub` 管理 Provider / Model / API Key，并由 `learning-tracker` 通过 Docker 内网调用
- 后端未配置 AI Hub 或 AI Hub 不可用时，自动降级为 GitHub README / 网页目录启发式生成
- 阶段 / 任务 / 进度 / 学习日志跟踪
- 仪表盘统计：计划数、完成数、平均进度、学习时长
- 搜索、状态筛选
- SQLite `.db` 导入 / 导出备份
- 响应式深色 UI
- Docker Compose 双服务部署

## 架构

```text
浏览器
  ↓
learning-tracker :8010
  ↓ Docker 内网 HTTP
ai-hub :8020
  ↔ MySQL :3306（持久化 Provider/Model/Key/Log）
  ↓ OpenAI-compatible API
OpenCode Go / DeepSeek / OpenAI / Kimi / Qwen
```

`learning-tracker` 不再直接保存第三方模型 Key；所有 API URL、Key、模型和调用日志通过 `AI Hub` 后台写入 MySQL，并用 `AI_HUB_MASTER_KEY` 加密 Key。

## 本地 Docker 运行

```bash
docker compose up -d --build
```

默认 Compose 已内置 MySQL 和开发可用账号密码；第三方模型 API URL/Key 在 AI Hub 页面录入，不需要写入环境变量。

访问：

```text
Learning Tracker: http://127.0.0.1:8010/
AI Hub Admin:    http://127.0.0.1:8020/
```

## AI Hub 配置 OpenCode Go

1. 打开 `http://127.0.0.1:8020/`
2. 登录 `admin / admin`
3. 在 Provider 页面添加：

```text
名称：OpenCode Go
Base URL：https://opencode.ai/zen/go/v1
API Key：你的 OpenCode Go API Key
启用：是
```

4. 在 Model 页面添加：

```text
Provider：OpenCode Go
模型 ID：deepseek-v4-pro
显示名称：DeepSeek V4 Pro
用途：learning_plan
默认：是
```

5. 回到“配置引导”页面点击“测试默认模型”，返回 `pong` 即成功。

可选模型：

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

## 内网 API

`learning-tracker` 默认通过 Docker 内网接入：

```yaml
environment:
  AI_HUB_URL: http://ai-hub:8020
  AI_HUB_TOKEN: dev-internal-token
```

手动测试：

```bash
curl -X POST http://127.0.0.1:8020/api/v1/analyze-learning-link \
  -H "Authorization: Bearer $AI_HUB_INTERNAL_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "clientName":"learning-tracker",
    "url":"https://github.com/yt-huang/learning-tracker",
    "goal":"学习这个项目的架构和实现",
    "level":"进阶",
    "hoursPerWeek":5
  }'
```

## 数据说明

Learning Tracker 业务数据表：

- `plans`
- `milestones`
- `tasks`
- `logs`

每次新增/修改/删除都会写入浏览器内 SQLite，并立即 `db.export()` 保存到 IndexedDB。只有登录 session 使用 localStorage。

AI Hub 数据库：

```text
Docker volume: ai_hub_mysql
MySQL database: ai_hub
```

包含：

- `providers`
- `models`
- `call_logs`

## 部署

GitHub Actions 会构建两个镜像并推送到：

```text
ghcr.io/yt-huang/learning-tracker:latest
ghcr.io/yt-huang/learning-tracker-ai-hub:latest
```

云服务器默认路径：`/opt/learning-tracker`

公网端口：

```text
Learning Tracker: 8010
AI Hub Admin:    8020
```

> 生产建议：AI Hub 管理后台只允许可信 IP 访问，或者放到内网/反向代理认证之后。
