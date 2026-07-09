# E2E 冒烟测试 — TestZeus Hercules

> 基于 AI 的 Gherkin 自然语言 E2E 测试框架，用自然语言写测试步骤，AI Agent 自动执行浏览器操作。

## 目录结构

```
e2e/
├── smoke.feature              # Gherkin 冒烟测试用例（8 个场景）
├── agents_llm_config.json     # Hercules LLM 配置（DeepSeek，envsubst 模板）
├── run_smoke.sh               # 测试运行脚本
├── README.md                  # 本文档
├── output/                    # 运行结果（JUnit XML + HTML 报告）— gitignore
├── proofs/                    # 截图、录屏、网络日志 — gitignore
└── log_files/                 # AI 推理日志 — gitignore
```

## 测试覆盖场景

| # | 场景 | 描述 |
|---|------|------|
| 1 | 登录页面正常加载 | 验证页面标题和副标题可见 |
| 2 | 错误密码登录失败 | 验证错误凭据被拒绝 |
| 3 | 正确凭据登录成功 | 验证能进入仪表盘 |
| 4 | 导航到学习计划视图 | 验证侧边栏导航功能 |
| 5 | 导航到学习日志视图 | 验证侧边栏导航功能 |
| 6 | 导航到数据管理视图 | 验证侧边栏导航功能 |
| 7 | 管理员导航到 AI 模型配置 | 验证管理员专属视图可访问 |
| 8 | 退出登录返回登录页 | 验证 logout 功能 |

## 本地运行

### 前置条件

```bash
# 安装 Hercules + Playwright
pip install testzeus-hercules
python -m playwright install chromium

# 安装 envsubst（macOS 通常自带，Linux 需要 gettext-base）
# Ubuntu: sudo apt install gettext-base
```

### 运行

确保 Learning Tracker 服务已启动（默认 `http://127.0.0.1:8010`）：

```bash
# 设置 DeepSeek API Key
export DEEPSEEK_API_KEY="your_key_here"

# 运行冒烟测试
./e2e/run_smoke.sh

# 指定自定义目标 URL
E2E_BASE_URL=http://192.168.1.100:8010 ./e2e/run_smoke.sh

# 显示浏览器（调试用）
HEADLESS=false ./e2e/run_smoke.sh

# 关闭录屏截图（提速）
HEADLESS=false RECORD_VIDEO=false TAKE_SCREENSHOTS=false ./e2e/run_smoke.sh
```

### 查看报告

```bash
open e2e/output/run_*/*_result.html
```

## CI 运行

GitHub Actions workflow：`.github/workflows/e2e-smoke.yml`

- 触发：push/PR 到 `main`，或手动触发
- 流程：MySQL → Learning Tracker 服务 → Hercules E2E 测试 → 上传产物
- 产物保留 14 天，包含 HTML 报告、截图、录屏、推理日志

### 所需 GitHub Secrets

| Secret Name | 用途 |
|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek API Key，驱动 Hercules Agent 推理 |

在仓库 Settings → Secrets and variables → Actions 中添加。

## 为什么用 Hercules 而不是 Playwright 脚本？

```
传统 Playwright：     需要 CSS 选择器 / XPath → UI 变化后维护成本高
TestZeus Hercules：   Gherkin 自然语言 → AI Agent 读 DOM + 截图理解页面 → 不怕 UI 变化
```

面试谈资：

> "我用 TestZeus Hercules 做了 Gherkin → E2E 冒烟测试并接入 GitHub Actions CI。它的多 Agent 架构（Planner → Nav Agent → Executor）基于 autogen，通过读取 DOM + 截图来理解页面并执行操作。探索性测试和快速冒烟场景特别适合，后续 UI 改版不需要改选择器。"