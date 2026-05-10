# Learning Tracker

一个产品化的学习计划跟踪系统：输入学习链接，自动生成阶段、任务和学习日志跟踪体系。业务数据使用 **SQLite（sql.js）** 存储在浏览器中，并以 `.db` 文件形式持久化到 IndexedDB，不依赖 Firebase/Supabase 等实时数据库。

## 登录

- 用户名：`admin`
- 密码：`admin`

## 功能

- 从学习链接自动生成学习计划
- 阶段 / 任务 / 进度 / 学习日志跟踪
- 仪表盘统计：计划数、完成数、平均进度、学习时长
- 搜索、状态筛选
- SQLite `.db` 导入 / 导出备份
- 响应式深色 UI
- Docker + GitHub Actions 云服务器部署

## 本地运行

```bash
python3 -m http.server 8010
open http://127.0.0.1:8010/
```

> 首次加载需要访问 CDN 获取 `sql.js` 和 wasm 文件。

## Docker

```bash
docker build -t learning-tracker:local .
docker run --rm -p 8010:80 learning-tracker:local
```

## 数据说明

业务数据表：

- `plans`
- `milestones`
- `tasks`
- `logs`

每次新增/修改/删除都会写入 SQLite，并立即 `db.export()` 保存到 IndexedDB。只有登录 session 使用 localStorage。

## 部署

GitHub Actions 会构建镜像并推送到：

```text
ghcr.io/yt-huang/learning-tracker:latest
```

云服务器默认路径：`/opt/learning-tracker`  
公网端口：`8010`
