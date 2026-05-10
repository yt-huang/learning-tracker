# Learning Tracker 项目规划

## 项目概述
一个基于 Web 的学习进度跟踪系统，用于记录和追踪学习内容、进度、时间日志等信息。数据使用 sql.js（浏览器端 SQLite）存储，可部署到 GitHub Pages。

## 技术栈
- **前端**: 纯 HTML + CSS + JavaScript（无框架依赖，轻量部署）
- **数据库**: sql.js（SQLite 编译为 WebAssembly，完全浏览器端运行）
- **存储**: IndexedDB（持久化 sql.js 数据库文件）
- **部署**: GitHub Pages（纯静态托管）
- **样式**: 暗色主题，现代 UI

## 功能需求

### 1. 学习内容管理
- 添加学习项目（标题、描述、分类、来源链接如 GitHub repo）
- 编辑/删除学习项目
- 学习项目状态：未开始 / 进行中 / 已完成 / 暂停

### 2. 学习进度追踪
- 每个学习项目的完成百分比（0-100%）
- 进度条可视化

### 3. 学习日志
- 每次学习记录：日期时间、时长、学习内容摘要、笔记
- 自动累计总学习时间

### 4. 完成记录
- 完成时间戳
- 完成心得/总结
- 总学习时长统计

### 5. 数据持久化
- sql.js 在浏览器中创建 SQLite 数据库
- 数据自动保存到 IndexedDB
- 支持导出/导入 .db 文件（方便备份迁移）

### 6. 统计看板
- 总学习项目数 / 已完成数 / 进行中数
- 总学习时长
- 最近学习记录时间线
- 各分类学习进度概览

## 数据库设计 (SQLite)

```sql
-- 学习项目
CREATE TABLE learning_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    category TEXT DEFAULT '',
    source_url TEXT DEFAULT '',
    status TEXT DEFAULT 'not_started',  -- not_started, in_progress, paused, completed
    progress INTEGER DEFAULT 0,          -- 0-100
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME NULL
);

-- 学习日志
CREATE TABLE learning_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    log_date DATE NOT NULL,
    duration_minutes INTEGER DEFAULT 0,
    summary TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES learning_items(id) ON DELETE CASCADE
);

-- 完成记录
CREATE TABLE completion_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL UNIQUE,
    total_duration_minutes INTEGER DEFAULT 0,
    summary_notes TEXT DEFAULT '',
    completed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES learning_items(id) ON DELETE CASCADE
);
```

## 页面结构
```
index.html          → 单页应用（SPA），所有功能集成在一个页面
├── 侧边栏          → 导航（看板、学习列表、统计）
├── 看板视图         → 统计卡片 + 最近活动
├── 学习列表         → 学习项目卡片，带进度条
├── 学习详情         → 日志列表 + 添加日志表单
└── 统计页面         → 图表和数据统计
```

## 文件结构
```
learning-tracker/
├── index.html           # 主页面
├── css/
│   └── style.css        # 暗色主题样式
├── js/
│   ├── app.js           # 主应用逻辑（路由、状态管理）
│   ├── db.js            # sql.js 数据库初始化与操作
│   ├── models.js        # 数据模型（CRUD 操作）
│   └── views.js         # 视图渲染
├── lib/
│   └── sql.js           # sql.js WASM 文件（从 CDN 加载）
└── README.md            # 项目说明
```

## 部署方案
1. 推送到 GitHub 仓库
2. 启用 GitHub Pages（source: main branch, root: /）
3. 由于 sql.js 完全在浏览器运行，无需服务端
4. 数据存在用户浏览器 IndexedDB 中，通过导出/导入 .db 文件备份

## 初始示例数据
导入 https://github.com/luongnv89/claude-howto 作为第一个学习项目。