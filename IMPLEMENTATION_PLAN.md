# Learning Tracker 产品化实施计划

> OpenCode 工作流：先由 Plan Builder 规划，再由 Plan Executor 按本文件执行。当前仓库为纯静态 Web App，目标部署到 GitHub + 云服务器 Docker。

## 目标
把 `learning-tracker` 完善为一个可直接使用的学习计划跟踪系统：用户登录后输入一个学习链接，系统自动生成学习计划（阶段、任务、预计时长），并支持实时保存、进度跟踪、学习日志、统计看板、导入导出和云服务器部署。

## 技术方案
- 前端：Vanilla HTML/CSS/JavaScript SPA，无构建依赖，便于 Docker 静态部署。
- 数据：使用 SQLite（`sql.js` 浏览器端 SQLite WASM）作为主数据库；数据库文件通过 IndexedDB 持久化。禁止把业务数据存到实时数据库或只存 localStorage。每次 CRUD 后立即导出 SQLite DB bytes 写入 IndexedDB 并重渲染 UI。
- 登录：静态演示型登录，用户名/密码 `admin/admin`，仅 session 状态可写入 `sessionStorage/localStorage`，支持退出。
- 部署：Docker 使用 `busybox:1.36` 静态 HTTP 服务，GitHub Actions 构建并推送 GHCR，再 SSH 到腾讯云服务器部署。

## 文件结构
- `index.html`：SPA 入口，登录页、应用骨架、模态框容器。
- `css/style.css`：响应式深色产品 UI。
- `js/db.js`：sql.js 初始化、SQLite schema、SQL CRUD、IndexedDB 持久化、`.db` 导入导出。
- `js/auth.js`：admin/admin 登录、session、路由守卫。
- `js/planner.js`：从学习链接生成计划、里程碑、任务。
- `js/app.js`：状态管理、渲染、交互绑定、CRUD。
- `README.md`：使用说明、账号、部署地址、数据说明。
- `.gitignore`：忽略 `.opencode/`、`.sisyphus/`、系统文件。
- `Dockerfile`：busybox 静态服务。
- `docker-compose.yml`：生产容器，默认端口 `8010:80`，避免与现有 k8s 项目 8000 冲突。
- `.github/workflows/build-and-deploy.yml`：GHCR + SSH 自动部署。
- `deploy.sh`：手动部署 fallback。

## 数据模型
```js
{
  plans: [{
    id, title, sourceUrl, description, category, difficulty,
    status: 'not_started'|'in_progress'|'paused'|'completed',
    progress, estimatedHours, createdAt, updatedAt, completedAt,
    milestones: [{ id, title, description, order, tasks: [taskId] }]
  }],
  tasks: [{
    id, planId, milestoneId, title, description, status,
    progress, estimatedMinutes, spentMinutes, priority, createdAt, updatedAt, completedAt
  }],
  logs: [{ id, planId, taskId, date, durationMinutes, summary, notes, createdAt }]
}
```

## 实施步骤

### 1. 基础项目文件
创建 `.gitignore`、`index.html`、`css/style.css`、`js/*.js`、`README.md`，保证无构建依赖，`python3 -m http.server` 可直接运行。

### 2. 登录系统
实现 `auth.js`：
- 登录表单校验 `admin/admin`。
- 登录成功写入 `learning_tracker_session`。
- 未登录只显示登录页。
- 退出清除 session 并回到登录页。

验收：刷新页面后保持登录；退出后看不到主应用。

### 3. SQLite 数据存取
实现 `storage.js` / `db.js`：
- 使用 CDN 加载 `sql.js`：`https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.10.3/sql-wasm.js`，并配置 wasm 路径。
- 首次启动创建 SQLite schema：`plans`、`milestones`、`tasks`、`logs`。
- IndexedDB 保存导出的 SQLite 数据库文件 bytes；启动时从 IndexedDB 恢复 DB。
- 默认 seed 一个示例计划。
- `createPlan/updatePlan/deletePlan/createTask/updateTask/createLog/deleteLog` 使用 SQL 事务写入 SQLite；每次操作后立即 `db.export()` 并保存到 IndexedDB。
- 支持导出 `.db` 文件、导入 `.db` 文件恢复数据。
- `getStats()` 通过 SQL 聚合计算总计划、完成率、学习时长、今日学习。

验收：新增/修改任务后刷新页面数据仍在；浏览器 IndexedDB 中存在 SQLite DB；导入导出 `.db` 可用。

### 4. 链接生成学习计划
实现 `planner.js`：
- 从 URL 推断标题：GitHub 链接用 `owner/repo`，普通 URL 用 hostname/path。
- 自动生成 4 个阶段：了解背景、环境与资料梳理、核心内容学习、实践与总结。
- 每阶段 3 个任务，包含预计时间、描述、优先级。
- 允许用户编辑标题、分类、难度、目标。

验收：输入 `https://github.com/luongnv89/claude-howto` 可生成包含 4 个阶段和 12 个任务的计划。

### 5. 产品化 UI
实现 `app.js` 渲染：
- 仪表盘：统计卡片、最近日志、进行中计划。
- 计划列表：搜索、状态筛选、卡片、进度条。
- 计划详情：阶段/任务看板、任务状态切换、进度滑块、添加学习日志。
- 日志页：按时间倒序展示。
- 响应式：桌面侧边栏，移动端单列。

验收：所有按钮可点击，新增计划/日志/任务状态实时更新页面。

### 6. Docker 与 CI/CD
- `Dockerfile` 使用 `busybox:1.36`，复制静态文件到 `/www`，启动 `httpd -f -p 80 -h /www`。
- `docker-compose.yml` 服务名 `learning-tracker`，端口 `8010:80`。
- GitHub Actions：push main 后构建 `ghcr.io/yt-huang/learning-tracker:latest`，SSH 到 `ubuntu@106.54.242.3`，目录 `/opt/learning-tracker`，`sudo docker compose pull && up -d`。

验收：服务器 `curl http://106.54.242.3:8010/` 返回 HTML。

## 测试命令
```bash
python3 -m http.server 8010
curl -I http://127.0.0.1:8010/
docker build -t learning-tracker:local .
docker run --rm -d --name learning-tracker-test -p 8011:80 learning-tracker:local
curl -I http://127.0.0.1:8011/
docker rm -f learning-tracker-test
```

## GitHub/部署步骤
```bash
gh repo create yt-huang/learning-tracker --public --source=. --remote=origin --push
gh secret set SERVER_HOST -b '106.54.242.3'
gh secret set SERVER_USER -b 'ubuntu'
gh secret set SERVER_SSH_KEY < ~/tencent/cloud.pem
git push origin main
```

## 产品验收清单
- [ ] 登录账号 `admin/admin` 可用。
- [ ] 未登录无法访问主应用。
- [ ] 输入学习链接可自动生成结构化计划。
- [ ] 计划、任务、日志的增删改会立即写入 SQLite，并把 SQLite DB 文件持久化到 IndexedDB，刷新不丢失。
- [ ] 仪表盘统计随数据实时变化。
- [ ] 搜索、筛选、导入、导出可用。
- [ ] GitHub 仓库已推送。
- [ ] 云服务器公网地址可访问。
