# Learning Tracker

一个产品化的多用户学习计划跟踪系统：输入学习链接，自动生成阶段、任务和学习日志跟踪体系。业务数据、AI Provider/Model 配置和调用日志都持久化到 VM 现有 MySQL。

## 登录

- Learning Tracker 用户名：`admin@cpaas.io`
- Learning Tracker 初始密码：请以部署环境为准

## 功能

- 从学习链接自动生成学习计划
- AI 深度分析学习链接：通过内置管理页统一配置 Provider / Model / API Key，并由 `learning-tracker` 通过 Docker 内网调用 `AI Analysis Hub`
- 普通用户分析时可选择管理员启用的具体模型，提高分析针对性
- 只有管理员能配置 DeepSeek / Kimi / OpenCode Go 等 Provider 和模型
- AI Hub 不对公网暴露管理端口；第三方 API Key 不进入浏览器普通用户页面，也不写入 Docker 环境变量
- 后端未配置 AI Hub 或 AI Hub 不可用时，自动降级为 GitHub README / 网页目录启发式生成
- 阶段 / 任务 / 进度 / 学习日志跟踪
- 仪表盘统计：计划数、完成数、平均进度、学习时长
- 搜索、状态筛选、用户管理
- Docker Compose 双服务部署，复用 VM 现有 MySQL

## 架构

```text
浏览器
  ↓ 登录后的 Learning Tracker 前端
learning-tracker :8010
  ├─ 管理员：/api/admin/ai/* 代理 AI Hub 管理接口
  ├─ 普通用户：/api/ai/models 只读可用模型列表
  └─ 分析请求：/api/analyze-link 携带所选 modelId
      ↓ Docker 内网 HTTP + 内部 token
ai-hub :8020（仅 Docker 内网 expose，不映射公网端口）
  ↔ VM 现有 MySQL :3306（持久化 Provider/Model/Key/Log）
  ↓ OpenAI-compatible API
OpenCode Go / DeepSeek / Kimi / OpenAI / Qwen
```

`learning-tracker` 不直接保存第三方模型 Key；所有 API URL、Key、模型和调用日志由 AI Hub 写入 MySQL，并用 `AI_HUB_MASTER_KEY` 加密 Key。公网只暴露 `8010`，AI Hub 的 `8020` 只在 Docker 网络内可访问。

## 本地 Docker 运行

```bash
docker compose up -d --build
```

默认 Compose 复用虚拟机现有 MySQL；第三方模型 API URL/Key 在 Learning Tracker 的「AI 模型配置」页面录入，不需要写入环境变量。

访问：

```text
Learning Tracker: http://127.0.0.1:8010/
AI 模型配置: 登录 Learning Tracker 后，管理员进入左侧「AI 模型配置」
```

## 配置 DeepSeek / Kimi / OpenCode Go

管理员登录 Learning Tracker 后进入「AI 模型配置」。

### DeepSeek

Provider：

```text
名称：DeepSeek
Base URL：https://api.deepseek.com
API Key：你的 DeepSeek API Key
启用：是
```

推荐模型：

```text
deepseek-chat       # 通用学习计划分析
deepseek-reasoner   # 更强推理，适合复杂论文/架构分析
```

说明：DeepSeek 的接口兼容 OpenAI Chat Completions；AI Hub 会避免对 DeepSeek 强制传 `response_format`，减少兼容性问题。

### Kimi / Moonshot

Provider：

```text
名称：Kimi / Moonshot
Base URL：https://api.moonshot.cn/v1
API Key：你的 Moonshot API Key
启用：是
```

推荐操作：先点击「从 Provider 拉取模型」，以接口实际返回为准；也可手动添加：

```text
kimi-k2-0905-preview
kimi-latest
```

### OpenCode Go

Provider：

```text
名称：OpenCode Go
Base URL：https://opencode.ai/zen/go/v1
API Key：你的 OpenCode Go API Key
启用：是
```

推荐模型：

```text
deepseek-v4-pro
```

## 用户分析流程

1. 普通用户点击「从链接生成计划」。
2. 填写学习链接、目标、难度和预计小时。
3. 在「分析模型」下拉框选择管理员启用的模型；不选则使用默认模型。
4. 点击「AI 深度分析」。
5. 生成结果确认后保存到 MySQL。

普通用户只能看到模型显示名和 Provider 名称，不能看到 Base URL / API Key。

## 内网 API

`learning-tracker` 默认通过 Docker 内网接入：

```yaml
environment:
  AI_HUB_URL: http://ai-hub:8020
  AI_HUB_TOKEN: dev-internal-token
  AI_HUB_ADMIN_TOKEN: dev-admin-token
  AI_HUB_TIMEOUT: 300          # learning-tracker 等待 AI Hub 分析结果
  AI_PROVIDER_TIMEOUT: 180     # AI Hub 等待 DeepSeek/Kimi/OpenCode Go 返回
```

AI Hub 内部分析接口支持可选 `modelId`：

```json
{
  "clientName": "learning-tracker",
  "url": "https://github.com/yt-huang/learning-tracker",
  "goal": "学习这个项目的架构和实现",
  "level": "进阶",
  "hoursPerWeek": 5,
  "modelId": "1"
}
```

## 数据说明

Learning Tracker 业务数据表：

- `users`
- `sessions`
- `plans`
- `milestones`
- `tasks`
- `logs`

AI Hub 数据表：

- `providers`
- `models`
- `call_logs`

数据库：VM existing backend MySQL，默认库名 `learning_tracker`（可通过 `DB_NAME` 覆盖）。

## 部署

GitHub Actions 会构建两个镜像并推送到：

```text
ghcr.io/yt-huang/learning-tracker:latest
ghcr.io/yt-huang/learning-tracker-ai-hub:latest
```

云服务器默认路径：`/opt/learning-tracker`。推送到 `main` 后 GitHub Action 自动构建并 SSH 到 VM 部署。

公网端口：

```text
Learning Tracker: 8010
AI Hub: 不映射公网端口，仅 Docker 内网访问
```
