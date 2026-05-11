#!/usr/bin/env python3
"""Learning Tracker — MySQL backend with full REST API.

All data stored in MySQL. Zero browser-side persistence.
"""
from __future__ import annotations

import base64
import datetime
import decimal
import hashlib
import html
import json
import os
import re
import sys
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    import pymysql
    import pymysql.cursors
except ImportError:
    pymysql = None

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
PORT = int(os.getenv("PORT", "8010"))
MAX_CONTENT_CHARS = 14000
TOKEN_EXPIRY = 7 * 24 * 3600

MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "lt_user")
MYSQL_PASS = os.getenv("MYSQL_PASS", "LtPass2024!")
MYSQL_DB = os.getenv("MYSQL_DB", "learning_tracker")


# ---------------------------------------------------------------------------
# MySQL helpers
# ---------------------------------------------------------------------------
def get_db():
    if pymysql is None:
        raise RuntimeError("pymysql not installed. Run: pip install pymysql")
    conn = pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, password=MYSQL_PASS,
        database=MYSQL_DB, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
    return conn


def init_mysql():
    conn = get_db()
    cur = conn.cursor()
    tables = {
        "users": """
            CREATE TABLE IF NOT EXISTS users (
                id VARCHAR(64) PRIMARY KEY,
                username VARCHAR(100) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                email VARCHAR(200) DEFAULT '',
                role VARCHAR(20) DEFAULT 'user',
                active TINYINT DEFAULT 1,
                created_at DATETIME,
                updated_at DATETIME
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        "tokens": """
            CREATE TABLE IF NOT EXISTS tokens (
                token VARCHAR(128) PRIMARY KEY,
                user_id VARCHAR(64) NOT NULL,
                expires_at BIGINT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        "plans": """
            CREATE TABLE IF NOT EXISTS plans (
                id VARCHAR(64) PRIMARY KEY,
                user_id VARCHAR(64) NOT NULL,
                title VARCHAR(500) NOT NULL,
                source_url TEXT,
                description TEXT,
                category VARCHAR(100),
                difficulty VARCHAR(50),
                status VARCHAR(50) DEFAULT 'not_started',
                progress INT DEFAULT 0,
                estimated_hours DECIMAL(5,1) DEFAULT 0,
                created_at DATETIME,
                updated_at DATETIME,
                completed_at DATETIME NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_plans_user (user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        "milestones": """
            CREATE TABLE IF NOT EXISTS milestones (
                id VARCHAR(64) PRIMARY KEY,
                plan_id VARCHAR(64) NOT NULL,
                user_id VARCHAR(64) NOT NULL,
                title VARCHAR(500) NOT NULL,
                description TEXT,
                order_index INT DEFAULT 0,
                FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_milestones_plan (plan_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        "tasks": """
            CREATE TABLE IF NOT EXISTS tasks (
                id VARCHAR(64) PRIMARY KEY,
                plan_id VARCHAR(64) NOT NULL,
                milestone_id VARCHAR(64) NOT NULL,
                user_id VARCHAR(64) NOT NULL,
                title VARCHAR(500) NOT NULL,
                description TEXT,
                status VARCHAR(50) DEFAULT 'todo',
                progress INT DEFAULT 0,
                estimated_minutes INT DEFAULT 0,
                spent_minutes INT DEFAULT 0,
                priority VARCHAR(20) DEFAULT 'medium',
                order_index INT DEFAULT 0,
                created_at DATETIME,
                updated_at DATETIME,
                completed_at DATETIME NULL,
                FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE CASCADE,
                FOREIGN KEY (milestone_id) REFERENCES milestones(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_tasks_plan (plan_id),
                INDEX idx_tasks_milestone (milestone_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        "logs": """
            CREATE TABLE IF NOT EXISTS logs (
                id VARCHAR(64) PRIMARY KEY,
                plan_id VARCHAR(64) NOT NULL,
                task_id VARCHAR(64) NULL,
                user_id VARCHAR(64) NOT NULL,
                date DATE NOT NULL,
                duration_minutes INT DEFAULT 0,
                summary TEXT,
                notes TEXT,
                created_at DATETIME,
                FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE CASCADE,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_logs_plan (plan_id),
                INDEX idx_logs_user (user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    }
    for name, ddl in tables.items():
        cur.execute(ddl)
    # Seed admin user if empty
    cur.execute("SELECT COUNT(*) cnt FROM users")
    if cur.fetchone()["cnt"] == 0:
        uid = uuid.uuid4().hex[:16]
        pwh = hash_password("07Apples@")
        ts = now_dt()
        cur.execute(
            "INSERT INTO users (id, username, password_hash, email, role, active, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (uid, "admin@cpaas.io", pwh, "", "admin", 1, ts, ts),
        )
        print("ℹ️  Created admin user: admin@cpaas.io / 07Apples@", flush=True)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Crypto helpers
# ---------------------------------------------------------------------------
def hash_password(password: str, salt: str | None = None) -> str:
    if not salt:
        salt = uuid.uuid4().hex[:16]
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{h}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, h = stored.split(":", 1)
        return hash_password(password, salt) == stored
    except (ValueError, AttributeError):
        return False


def generate_token() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def now_dt() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())


# ---------------------------------------------------------------------------
# Auth middleware
# ---------------------------------------------------------------------------
def get_user_by_token(token: str) -> dict | None:
    if not token:
        return None
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT u.* FROM users u JOIN tokens t ON t.user_id=u.id WHERE t.token=%s AND t.expires_at>%s",
        (token, int(time.time())),
    )
    row = cur.fetchone()
    conn.close()
    return row


def require_auth(headers) -> dict | None:
    auth = headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    return get_user_by_token(auth[7:])


def api_error(msg: str, status: int = 400) -> dict:
    return {"_error": msg, "_status": status}


# ---------------------------------------------------------------------------
# URL fetching / AI analysis (unchanged from before)
# ---------------------------------------------------------------------------
def fetch_url(url: str, timeout: int = 18) -> tuple[str, str]:
    req = urllib.request.Request(url, headers={
        "User-Agent": "LearningTrackerBot/1.0",
        "Accept": "text/html,application/xhtml+xml,text/markdown,text/plain,application/json;q=0.8,*/*;q=0.5",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        ctype = resp.headers.get("content-type", "")
        raw = resp.read(512_000)
    charset = "utf-8"
    m = re.search(r"charset=([^;]+)", ctype, re.I)
    if m:
        charset = m.group(1).strip()
    return raw.decode(charset, errors="replace"), ctype


def fetch_github_readme(url: str) -> dict | None:
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    try:
        data, _ = fetch_url(f"https://api.github.com/repos/{owner}/{repo}/readme")
        payload = json.loads(data)
        readme = base64.b64decode(payload.get("content", "")).decode("utf-8", errors="replace") if payload.get("content") else ""
        try:
            meta, _ = fetch_url(f"https://api.github.com/repos/{owner}/{repo}")
            meta = json.loads(meta)
            return {"kind": "github", "title": f"{owner}/{repo}", "description": meta.get("description", ""), "content": readme, "topics": meta.get("topics", []), "language": meta.get("language", ""), "stars": meta.get("stargazers_count", 0)}
        except Exception:
            return {"kind": "github", "title": f"{owner}/{repo}", "description": "", "content": readme, "topics": [], "language": "", "stars": 0}
    except Exception:
        # Try raw.githubusercontent.com as fallback (no API key needed)
        for branch in ("main", "master", "trunk"):
            try:
                readme, _ = fetch_url(f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/README.md")
                return {"kind": "github", "title": f"{owner}/{repo}", "description": "", "content": readme, "topics": [], "language": "", "stars": 0}
            except Exception:
                continue
        # Last resort — try other common filenames
        for name in ("readme.md", "Readme.md", "README.markdown", "README.rst", "index.md"):
            for branch in ("main", "master"):
                try:
                    readme, _ = fetch_url(f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{name}")
                    return {"kind": "github", "title": f"{owner}/{repo}", "description": "", "content": readme, "topics": [], "language": "", "stars": 0}
                except Exception:
                    continue
        return None


def html_to_text(markup: str) -> tuple[str, list[str], str]:
    title = ""
    tm = re.search(r"<title[^>]*>(.*?)</title>", markup, re.I | re.S)
    if tm:
        title = html.unescape(re.sub(r"\s+", " ", tm.group(1))).strip()
    headings = []
    for m in re.finditer(r"<h[1-3][^>]*>(.*?)</h[1-3]>", markup, re.I | re.S):
        h = re.sub(r"<[^>]+>", " ", m.group(1))
        h = html.unescape(re.sub(r"\s+", " ", h)).strip()
        if h and h not in headings:
            headings.append(h)
        if len(headings) >= 24:
            break
    text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", markup, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return text, headings, title


def markdown_headings(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        m = re.match(r"^#{1,3}\s+(.+?)\s*$", line)
        if m:
            h = re.sub(r"[#`*_\[\]]", "", m.group(1)).strip()
            if h and h not in out:
                out.append(h)
        if len(out) >= 24:
            break
    return out


def collect_link_context(url: str) -> dict:
    gh = fetch_github_readme(url)
    if gh:
        headings = markdown_headings(gh["content"])
        return {**gh, "url": url, "headings": headings, "content": gh["content"][:MAX_CONTENT_CHARS]}
    data, ctype = fetch_url(url)
    if "html" in ctype.lower() or "<html" in data[:500].lower():
        text, headings, title = html_to_text(data)
    else:
        text, headings, title = data, markdown_headings(data), ""
    parsed = urllib.parse.urlparse(url)
    return {"kind": "web", "url": url, "title": title or parsed.netloc, "description": "", "content": text[:MAX_CONTENT_CHARS], "headings": headings, "topics": [], "language": "", "stars": 0}


def fallback_plan(ctx: dict, goal: str = "", level: str = "进阶", hours_per_week: int = 5) -> dict:
    headings = [h for h in ctx.get("headings", []) if 3 <= len(h) <= 80]
    title = ctx.get("title") or "AI 生成学习计划"
    desc = ctx.get("description", "") or goal or f"基于 {title} 的学习计划"
    content = ctx.get("content", "")
    topics = ctx.get("topics", [])
    language = ctx.get("language", "")
    stars = ctx.get("stars", 0)

    # Determine phases from headings or use smart defaults
    if len(headings) >= 4:
        phase_titles = headings[:6]
    else:
        phase_titles = ["内容概览与学习目标", "核心概念精读", "实践复现与案例分析", "总结输出与迁移应用"]
        if ctx.get("kind") == "github":
            phase_titles = ["项目背景与结构理解", "环境搭建与快速上手", "核心功能精读与实验", "代码/配置深度分析", "最佳实践与总结输出"]
            if stars > 1000:
                phase_titles.append("社区生态与进阶方向")

    # Analyze content for better task descriptions
    has_code = bool(re.search(r"```|def |function |class |import |const |let |var ", content))
    has_commands = bool(re.search(r"(?:^|\n)\s*[\$#>]\s", content))
    has_steps = bool(re.search(r"(?:步骤|step|第[一二三四五六七八九十]|首先|然后|最后)", content))

    total_hours = max(6, min(40, len(phase_titles) * max(2, int(hours_per_week or 5))))
    per_phase = max(60, round(total_hours * 60 / len(phase_titles)))

    milestones = []
    for i, phase in enumerate(phase_titles, 1):
        tasks = [
            {
                "title": f"阅读与梳理：{phase}",
                "description": f"仔细阅读 {title} 中与「{phase}」相关的内容，提取关键概念、术语和流程图。",
                "estimatedMinutes": round(per_phase * 0.3),
                "acceptance": "完成不少于5个关键点的结构化笔记",
            },
            {
                "title": f"实践验证：{phase}",
                "description": f"根据资料内容完成{'代码示例/命令' if has_code or has_commands else '操作演练/案例分析'}，验证理解。",
                "estimatedMinutes": round(per_phase * 0.4),
                "acceptance": "有可运行的结果或可复述的实践过程",
            },
            {
                "title": f"复盘输出：{phase}",
                "description": f"总结本阶段学习收获、遇到的问题和下一步计划。{'记录关键代码片段和运行结果。' if has_code else ''}",
                "estimatedMinutes": round(per_phase * 0.3),
                "acceptance": "写出阶段总结并更新学习日志",
            },
        ]
        milestones.append({
            "title": f"阶段{i}：{phase}",
            "description": f"围绕 {title} 的「{phase}」建立理解并产出可验证结果。{'包含 ' + language + ' 代码实践' if language and has_code else ''}",
            "goal": f"掌握 {phase} 相关知识，完成笔记和实践记录。",
            "tasks": tasks,
        })

    category = "在线资料"
    if ctx.get("kind") == "github":
        category = f"GitHub · {language}" if language else "GitHub 项目"
    if topics:
        category += f" ({', '.join(topics[:3])})"

    return {
        "title": title,
        "sourceUrl": ctx.get("url", ""),
        "description": desc,
        "category": category,
        "difficulty": level or "进阶",
        "estimatedHours": total_hours,
        "milestones": milestones,
        "aiUsed": False,
        "aiStrategy": "fallback",
        "analysisSummary": f"已基于链接内容（{len(headings)} 个章节）生成启发式学习计划。{'配置 AI API Key 可获得更精准的计划。' if not os.getenv('OPENAI_API_KEY') and not os.getenv('DEEPSEEK_API_KEY') and not os.getenv('AI_API_KEY') else ''}",
    }


def extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


def call_ai_hub(url: str, goal: str, level: str, hours_per_week: int) -> dict | None:
    hub_url = os.getenv("AI_HUB_URL", "").strip().rstrip("/")
    hub_token = os.getenv("AI_HUB_TOKEN", "").strip()
    if not hub_url or not hub_token:
        return None
    body = {"clientName": "learning-tracker", "template": "learning_plan", "url": url, "goal": goal, "level": level, "hoursPerWeek": hours_per_week}
    req = urllib.request.Request(hub_url + "/api/v1/analyze-learning-link", data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json", "Authorization": f"Bearer {hub_token}"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    plan = payload.get("plan")
    if isinstance(plan, dict):
        plan.setdefault("analysisSummary", f"由 AI Hub 生成")
        return plan
    return None


def call_ai(ctx: dict, goal: str, level: str, hours_per_week: int) -> dict | None:
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("AI_API_KEY")
    if not api_key:
        return None
    # Detect provider
    use_deepseek = bool(os.getenv("DEEPSEEK_API_KEY"))
    use_openai = bool(os.getenv("OPENAI_API_KEY")) and not use_deepseek
    base_url = os.getenv("OPENAI_BASE_URL") or ("https://api.deepseek.com/v1" if use_deepseek else "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL") or os.getenv("AI_MODEL") or ("deepseek-chat" if use_deepseek else "gpt-4o-mini")

    # Truncate context to avoid token overflow (rough: 1 token ≈ 2 chars for CJK)
    ctx_json = json.dumps(ctx, ensure_ascii=False)
    max_ctx = 6000 if use_deepseek else MAX_CONTENT_CHARS
    if len(ctx_json) > max_ctx:
        ctx_trimmed = dict(ctx)
        content = ctx_trimmed.get("content", "")
        if content and len(content) > max_ctx * 2:
            ctx_trimmed["content"] = content[:max_ctx * 2] + f"\n... [截断至 {max_ctx * 2} 字符]"
        ctx_json = json.dumps(ctx_trimmed, ensure_ascii=False)[:max_ctx + 200]

    prompt = f"""你是一个专业的学习规划师。根据用户提供的学习链接内容，生成结构化的学习计划。

## 输出要求
- 只输出 JSON，不要任何解释或 Markdown 代码块包裹
- JSON 必须包含以下字段：
  - title: 计划标题
  - description: 一句话描述
  - category: 分类（从内容推断）
  - difficulty: "{level}"
  - estimatedHours: 预计总学习小时数（整数）
  - analysisSummary: 一段总结说明
  - milestones: 阶段数组，每个阶段包含：
    - title: 阶段标题（中文，带编号如"阶段一：XXX"）
    - description: 本阶段目标
    - goal: 可验证的产出标准
    - tasks: 任务数组，每个任务包含：
      - title: 任务名称（中文，具体可执行）
      - description: 任务描述
      - estimatedMinutes: 预计耗时（分钟）
      - acceptance: 完成标准

## 计划设计要求
- 拆成 4-6 个阶段，由浅入深
- 每阶段 3-5 个具体任务
- 如果是 GitHub 项目，至少包含：环境准备 → 核心理解 → 实践验证 → 总结输出
- 如果是教程/文章，按：概念理解 → 精读重点 → 实践巩固 → 复盘输出
- 任务要具体到"阅读第X章"、"完成示例X"、"写一段总结"这种程度
- estimatedMinutes 要合理分配，总和不等于 estimatedHours × 60 也没关系，宁缺毋滥

## 用户信息
- 学习目标：{goal or '未填写'}
- 当前水平：{level or '进阶'}
- 每周可投入：{hours_per_week or 5} 小时

## 链接内容
{ctx_json}"""

    messages = [
        {"role": "system", "content": "你是一个严格输出 JSON 的学习规划助手。只输出 JSON 对象，不含任何其他文字。"},
        {"role": "user", "content": prompt},
    ]
    body = {"model": model, "messages": messages, "temperature": 0.3}

    # DeepSeek doesn't support response_format
    if not use_deepseek:
        body["response_format"] = {"type": "json_object"}

    print(f"[AI] Calling {model} via {base_url}... (ctx={len(ctx_json)} chars, goal={goal})", file=sys.stderr, flush=True)
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
        plan = extract_json(content)
        plan["aiUsed"] = True
        print(f"[AI] Success: {plan.get('title', '?')} ({len(plan.get('milestones',[]))} phases)", file=sys.stderr, flush=True)
        return plan
    except Exception as e:
        print(f"[AI] Error: {e}", file=sys.stderr, flush=True)
        return None


def normalize_plan(plan: dict, source_url: str) -> dict:
    plan.setdefault("sourceUrl", source_url)
    plan.setdefault("title", "AI 生成学习计划")
    plan.setdefault("description", "AI 根据链接内容生成的学习计划")
    plan.setdefault("category", "AI 分析")
    plan.setdefault("difficulty", "进阶")
    plan.setdefault("estimatedHours", 12)
    plan.setdefault("analysisSummary", "由 AI 生成的学习计划")
    clean_milestones = []
    for idx, m in enumerate(plan.get("milestones") or [], 1):
        tasks = []
        for t in m.get("tasks", [])[:5]:
            tasks.append({
                "title": str(t.get("title", "学习任务")),
                "description": str(t.get("description", t.get("acceptance", "完成该任务并记录学习日志。"))),
                "estimatedMinutes": int(t.get("estimatedMinutes", 60)),
                "priority": t.get("priority", "medium"),
            })
        clean_milestones.append({
            "title": str(m.get("title", f"阶段{idx}")),
            "description": str(m.get("description", m.get("goal", "阶段学习目标"))),
            "orderIndex": idx,
            "tasks": tasks,
        })
    plan["milestones"] = clean_milestones[:6]
    return plan


# ---------------------------------------------------------------------------
# HTTP Handler
# ---------------------------------------------------------------------------
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store" if self.path.startswith("/api/") else "no-cache")
        super().end_headers()

    def send_json(self, status: int, payload: dict):
        def safe(obj):
            if isinstance(obj, decimal.Decimal):
                return float(obj)
            if isinstance(obj, datetime.datetime):
                return obj.strftime("%Y-%m-%d %H:%M:%S")
            if isinstance(obj, datetime.date):
                return obj.isoformat()
            return str(obj)
        data = json.dumps(payload, ensure_ascii=False, default=safe).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_body(self) -> dict:
        length = int(self.headers.get("content-length", "0"))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def parse_path(self) -> tuple[str, list[str]]:
        parsed = urllib.parse.urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        base = "/" + "/".join(parts[:3]) if parts else "/"
        return base, parts

    # ---- Auth ----
    def handle_auth_register(self):
        try:
            body = self.read_body()
            username = str(body.get("username", "")).strip()
            password = str(body.get("password", "")).strip()
            email = str(body.get("email", "")).strip()
            if len(username) < 2:
                return self.send_json(400, {"ok": False, "error": "用户名至少 2 个字符"})
            if len(password) < 4:
                return self.send_json(400, {"ok": False, "error": "密码至少 4 个字符"})
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT id FROM users WHERE username=%s", (username,))
            if cur.fetchone():
                conn.close()
                return self.send_json(409, {"ok": False, "error": "用户名已存在"})
            cur.execute("SELECT COUNT(*) cnt FROM users")
            cnt = cur.fetchone()["cnt"]
            role = "admin" if cnt == 0 else "user"
            active = 1 if cnt == 0 else 0
            uid = uuid.uuid4().hex[:16]
            pwh = hash_password(password)
            ts = now_dt()
            cur.execute("INSERT INTO users (id,username,password_hash,email,role,active,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", (uid, username, pwh, email, role, active, ts, ts))
            token = generate_token()
            cur.execute("INSERT INTO tokens (token,user_id,expires_at) VALUES (%s,%s,%s)", (token, uid, int(time.time()) + TOKEN_EXPIRY))
            conn.commit()
            conn.close()
            return self.send_json(201, {"ok": True, "message": "注册成功" if active else "注册成功，等待管理员激活", "token": token, "user": {"id": uid, "username": username, "email": email, "role": role, "active": active}})
        except Exception as e:
            return self.send_json(500, {"ok": False, "error": str(e)})

    def handle_auth_login(self):
        try:
            body = self.read_body()
            username = str(body.get("username", "")).strip()
            password = str(body.get("password", "")).strip()
            if not username or not password:
                return self.send_json(400, {"ok": False, "error": "请输入用户名和密码"})
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE username=%s", (username,))
            row = cur.fetchone()
            if not row:
                conn.close()
                return self.send_json(401, {"ok": False, "error": "用户名或密码错误"})
            if not verify_password(password, row["password_hash"]):
                conn.close()
                return self.send_json(401, {"ok": False, "error": "用户名或密码错误"})
            if not row["active"]:
                conn.close()
                return self.send_json(403, {"ok": False, "error": "账号未激活，请联系管理员"})
            token = generate_token()
            cur.execute("INSERT INTO tokens (token,user_id,expires_at) VALUES (%s,%s,%s)", (token, row["id"], int(time.time()) + TOKEN_EXPIRY))
            conn.commit()
            conn.close()
            return self.send_json(200, {"ok": True, "token": token, "user": {"id": row["id"], "username": row["username"], "email": row["email"], "role": row["role"], "active": row["active"]}})
        except Exception as e:
            return self.send_json(500, {"ok": False, "error": str(e)})

    def handle_auth_me(self):
        user = require_auth(self.headers)
        if not user:
            return self.send_json(401, {"ok": False, "error": "未登录"})
        return self.send_json(200, {"ok": True, "user": {"id": user["id"], "username": user["username"], "email": user["email"], "role": user["role"], "active": user["active"]}})

    def handle_auth_logout(self):
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            conn = get_db()
            cur = conn.cursor()
            cur.execute("DELETE FROM tokens WHERE token=%s", (auth[7:],))
            conn.commit()
            conn.close()
        return self.send_json(200, {"ok": True, "message": "已退出"})

    # ---- Admin ----
    def handle_admin_list_users(self):
        user = require_auth(self.headers)
        if not user:
            return self.send_json(401, {"ok": False, "error": "未登录"})
        if user["role"] != "admin":
            return self.send_json(403, {"ok": False, "error": "需要管理员权限"})
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id,username,email,role,active,created_at,updated_at FROM users ORDER BY created_at DESC")
        rows = cur.fetchall()
        conn.close()
        return self.send_json(200, {"ok": True, "users": rows})

    def handle_admin_update_user(self, user_id: str):
        user = require_auth(self.headers)
        if not user or user["role"] != "admin":
            return self.send_json(403, {"ok": False, "error": "需要管理员权限"})
        try:
            body = self.read_body()
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT id FROM users WHERE id=%s", (user_id,))
            if not cur.fetchone():
                conn.close()
                return self.send_json(404, {"ok": False, "error": "用户不存在"})
            updates, vals = {}, []
            for k in ("username", "email", "role"):
                if k in body and str(body[k]).strip():
                    updates[k] = str(body[k]).strip()
            if "password" in body and str(body["password"]).strip():
                updates["password_hash"] = hash_password(str(body["password"]).strip())
            if updates:
                updates["updated_at"] = now_dt()
                sets = ", ".join(f"{k}=%s" for k in updates)
                vals = list(updates.values()) + [user_id]
                cur.execute(f"UPDATE users SET {sets} WHERE id=%s", vals)
                conn.commit()
            cur.execute("SELECT id,username,email,role,active,created_at,updated_at FROM users WHERE id=%s", (user_id,))
            updated = cur.fetchone()
            conn.close()
            return self.send_json(200, {"ok": True, "user": updated})
        except Exception as e:
            return self.send_json(500, {"ok": False, "error": str(e)})

    def handle_admin_toggle_active(self, user_id: str, activate: bool):
        user = require_auth(self.headers)
        if not user or user["role"] != "admin":
            return self.send_json(403, {"ok": False, "error": "需要管理员权限"})
        if not activate and user["id"] == user_id:
            return self.send_json(400, {"ok": False, "error": "不能禁用自己"})
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE users SET active=%s, updated_at=%s WHERE id=%s", (1 if activate else 0, now_dt(), user_id))
        conn.commit()
        conn.close()
        return self.send_json(200, {"ok": True, "message": "已激活" if activate else "已禁用"})

    def handle_admin_delete_user(self, user_id: str):
        user = require_auth(self.headers)
        if not user or user["role"] != "admin":
            return self.send_json(403, {"ok": False, "error": "需要管理员权限"})
        if user["id"] == user_id:
            return self.send_json(400, {"ok": False, "error": "不能删除自己"})
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM tokens WHERE user_id=%s", (user_id,))
        cur.execute("DELETE FROM logs WHERE user_id=%s", (user_id,))
        cur.execute("DELETE FROM tasks WHERE user_id=%s", (user_id,))
        cur.execute("DELETE FROM milestones WHERE user_id=%s", (user_id,))
        cur.execute("DELETE FROM plans WHERE user_id=%s", (user_id,))
        cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
        conn.commit()
        conn.close()
        return self.send_json(200, {"ok": True, "message": "已删除"})

    # ---- Plans CRUD ----
    def handle_list_plans(self):
        user = require_auth(self.headers)
        if not user:
            return self.send_json(401, {"ok": False, "error": "未登录"})
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT p.*, COALESCE(SUM(t.spent_minutes),0) spent_minutes, COUNT(t.id) task_count,
                   SUM(CASE WHEN t.status='done' THEN 1 ELSE 0 END) done_count
            FROM plans p LEFT JOIN tasks t ON p.id=t.plan_id
            WHERE p.user_id=%s GROUP BY p.id ORDER BY p.updated_at DESC
        """, (user["id"],))
        rows = cur.fetchall()
        conn.close()
        return self.send_json(200, {"ok": True, "plans": rows})

    def handle_get_plan(self, plan_id: str):
        user = require_auth(self.headers)
        if not user:
            return self.send_json(401, {"ok": False, "error": "未登录"})
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM plans WHERE id=%s AND user_id=%s", (plan_id, user["id"]))
        plan = cur.fetchone()
        if not plan:
            conn.close()
            return self.send_json(404, {"ok": False, "error": "计划不存在"})
        # milestones + tasks
        cur.execute("SELECT * FROM milestones WHERE plan_id=%s ORDER BY order_index", (plan_id,))
        milestones = cur.fetchall()
        for m in milestones:
            cur.execute("SELECT * FROM tasks WHERE milestone_id=%s AND plan_id=%s ORDER BY order_index", (m["id"], plan_id))
            m["tasks"] = cur.fetchall()
        cur.execute("SELECT * FROM logs WHERE plan_id=%s ORDER BY created_at DESC", (plan_id,))
        logs = cur.fetchall()
        conn.close()
        plan["milestones"] = milestones
        plan["logs"] = logs
        return self.send_json(200, {"ok": True, "plan": plan})

    def handle_create_plan(self):
        user = require_auth(self.headers)
        if not user:
            return self.send_json(401, {"ok": False, "error": "未登录"})
        try:
            body = self.read_body()
            plan_id = uuid.uuid4().hex[:16]
            ts = now_dt()
            conn = get_db()
            cur = conn.cursor()
            cur.execute("INSERT INTO plans (id,user_id,title,source_url,description,category,difficulty,estimated_hours,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (
                plan_id, user["id"], body.get("title", "新计划"), body.get("sourceUrl", ""), body.get("description", ""),
                body.get("category", "未分类"), body.get("difficulty", "进阶"), float(body.get("estimatedHours", 12)), ts, ts,
            ))
            # Milestones
            for mi, m in enumerate(body.get("milestones", []), 1):
                mid = uuid.uuid4().hex[:16]
                cur.execute("INSERT INTO milestones (id,plan_id,user_id,title,description,order_index) VALUES (%s,%s,%s,%s,%s,%s)", (
                    mid, plan_id, user["id"], m.get("title", f"阶段{mi}"), m.get("description", ""), mi,
                ))
                for ti, t in enumerate(m.get("tasks", []), 1):
                    tid = uuid.uuid4().hex[:16]
                    cur.execute("INSERT INTO tasks (id,plan_id,milestone_id,user_id,title,description,estimated_minutes,priority,order_index,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (
                        tid, plan_id, mid, user["id"], t.get("title", "任务"), t.get("description", ""),
                        int(t.get("estimatedMinutes", 60)), t.get("priority", "medium"), ti, ts, ts,
                    ))
            conn.commit()
            conn.close()
            return self.send_json(201, {"ok": True, "id": plan_id})
        except Exception as e:
            return self.send_json(500, {"ok": False, "error": str(e)})

    def handle_update_plan(self, plan_id: str):
        user = require_auth(self.headers)
        if not user:
            return self.send_json(401, {"ok": False, "error": "未登录"})
        try:
            body = self.read_body()
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT id FROM plans WHERE id=%s AND user_id=%s", (plan_id, user["id"]))
            if not cur.fetchone():
                conn.close()
                return self.send_json(404, {"ok": False, "error": "计划不存在"})
            updates = {}
            for k in ("title", "source_url", "description", "category", "difficulty"):
                if k in body:
                    updates[k] = str(body[k])
            if "estimatedHours" in body:
                updates["estimated_hours"] = float(body["estimatedHours"])
            updates["updated_at"] = now_dt()
            sets = ", ".join(f"{k}=%s" for k in updates)
            cur.execute(f"UPDATE plans SET {sets} WHERE id=%s", list(updates.values()) + [plan_id])
            conn.commit()
            conn.close()
            return self.send_json(200, {"ok": True, "message": "已更新"})
        except Exception as e:
            return self.send_json(500, {"ok": False, "error": str(e)})

    def handle_delete_plan(self, plan_id: str):
        user = require_auth(self.headers)
        if not user:
            return self.send_json(401, {"ok": False, "error": "未登录"})
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id FROM plans WHERE id=%s AND user_id=%s", (plan_id, user["id"]))
        if not cur.fetchone():
            conn.close()
            return self.send_json(404, {"ok": False, "error": "计划不存在"})
        cur.execute("DELETE FROM plans WHERE id=%s AND user_id=%s", (plan_id, user["id"]))
        conn.commit()
        conn.close()
        return self.send_json(200, {"ok": True, "message": "已删除"})

    def handle_duplicate_plan(self, plan_id: str):
        user = require_auth(self.headers)
        if not user:
            return self.send_json(401, {"ok": False, "error": "未登录"})
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM plans WHERE id=%s AND user_id=%s", (plan_id, user["id"]))
        plan = cur.fetchone()
        if not plan:
            conn.close()
            return self.send_json(404, {"ok": False, "error": "计划不存在"})
        cur.execute("SELECT * FROM milestones WHERE plan_id=%s ORDER BY order_index", (plan_id,))
        milestones = cur.fetchall()
        cur.execute("SELECT * FROM tasks WHERE plan_id=%s", (plan_id,))
        tasks = cur.fetchall()
        new_id = uuid.uuid4().hex[:16]
        ts = now_dt()
        cur.execute("INSERT INTO plans (id,user_id,title,source_url,description,category,difficulty,estimated_hours,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (
            new_id, user["id"], plan["title"] + " (副本)", plan["source_url"], plan["description"],
            plan["category"], plan["difficulty"], plan["estimated_hours"], ts, ts,
        ))
        mid_map = {}
        for m in milestones:
            mid = uuid.uuid4().hex[:16]
            mid_map[m["id"]] = mid
            cur.execute("INSERT INTO milestones (id,plan_id,user_id,title,description,order_index) VALUES (%s,%s,%s,%s,%s,%s)", (mid, new_id, user["id"], m["title"], m["description"], m["order_index"]))
        for t in tasks:
            tid = uuid.uuid4().hex[:16]
            cur.execute("INSERT INTO tasks (id,plan_id,milestone_id,user_id,title,description,estimated_minutes,priority,order_index,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (
                tid, new_id, mid_map.get(t["milestone_id"], ""), user["id"], t["title"], t["description"],
                t["estimated_minutes"], t["priority"], t["order_index"], ts, ts,
            ))
        conn.commit()
        conn.close()
        return self.send_json(201, {"ok": True, "id": new_id})

    # ---- Milestones ----
    def handle_update_milestone(self, milestone_id: str):
        user = require_auth(self.headers)
        if not user:
            return self.send_json(401, {"ok": False, "error": "未登录"})
        conn = get_db()
        cur = conn.cursor()
        try:
            body = self.read_body()
            updates = {}
            for k in ("title", "description", "order_index"):
                if k in body:
                    updates[k] = body[k]
            if updates:
                sets = ", ".join(f"{k}=%s" for k in updates)
                cur.execute(f"UPDATE milestones SET {sets} WHERE id=%s AND user_id=%s", list(updates.values()) + [milestone_id, user["id"]])
                conn.commit()
            conn.close()
            return self.send_json(200, {"ok": True, "message": "已更新"})
        except Exception as e:
            conn.close()
            return self.send_json(500, {"ok": False, "error": str(e)})

    def handle_delete_milestone(self, milestone_id: str):
        user = require_auth(self.headers)
        if not user:
            return self.send_json(401, {"ok": False, "error": "未登录"})
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM tasks WHERE milestone_id=%s AND user_id=%s", (milestone_id, user["id"]))
        cur.execute("DELETE FROM milestones WHERE id=%s AND user_id=%s", (milestone_id, user["id"]))
        conn.commit()
        conn.close()
        return self.send_json(200, {"ok": True, "message": "已删除"})

    def handle_create_milestone(self, plan_id: str):
        user = require_auth(self.headers)
        if not user:
            return self.send_json(401, {"ok": False, "error": "未登录"})
        try:
            body = self.read_body()
            mid = uuid.uuid4().hex[:16]
            conn = get_db()
            cur = conn.cursor()
            # Get next order_index
            cur.execute("SELECT COALESCE(MAX(order_index),0)+1 idx FROM milestones WHERE plan_id=%s", (plan_id,))
            idx = cur.fetchone()["idx"]
            cur.execute("INSERT INTO milestones (id,plan_id,user_id,title,description,order_index) VALUES (%s,%s,%s,%s,%s,%s)",
                        (mid, plan_id, user["id"], body.get("title", "新阶段"), body.get("description", ""), idx))
            conn.commit()
            conn.close()
            return self.send_json(201, {"ok": True, "id": mid})
        except Exception as e:
            return self.send_json(500, {"ok": False, "error": str(e)})

    def handle_create_task(self, milestone_id: str):
        user = require_auth(self.headers)
        if not user:
            return self.send_json(401, {"ok": False, "error": "未登录"})
        try:
            body = self.read_body()
            tid = uuid.uuid4().hex[:16]
            plan_id = body.get("planId", "")
            ts = now_dt()
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT COALESCE(MAX(order_index),0)+1 idx FROM tasks WHERE milestone_id=%s", (milestone_id,))
            idx = cur.fetchone()["idx"]
            cur.execute("INSERT INTO tasks (id,plan_id,milestone_id,user_id,title,description,estimated_minutes,priority,order_index,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (tid, plan_id, milestone_id, user["id"], body.get("title", "新任务"), body.get("description", ""),
                         int(body.get("estimatedMinutes", 60)), body.get("priority", "medium"), idx, ts, ts))
            conn.commit()
            conn.close()
            return self.send_json(201, {"ok": True, "id": tid})
        except Exception as e:
            return self.send_json(500, {"ok": False, "error": str(e)})

    # ---- Tasks ----
    def handle_update_task(self, task_id: str):
        user = require_auth(self.headers)
        if not user:
            return self.send_json(401, {"ok": False, "error": "未登录"})
        try:
            body = self.read_body()
            conn = get_db()
            cur = conn.cursor()
            updates = {}
            for k in ("title", "description", "status", "progress", "estimated_minutes", "spent_minutes", "priority", "order_index"):
                if k in body:
                    updates[k] = body[k]
            if "progress" in body and body["progress"] >= 100:
                updates["status"] = "done"
                updates["completed_at"] = now_dt()
            elif "progress" in body and body["progress"] > 0:
                updates["status"] = "doing"
            updates["updated_at"] = now_dt()
            if updates:
                sets = ", ".join(f"{k}=%s" for k in updates)
                cur.execute(f"UPDATE tasks SET {sets} WHERE id=%s AND user_id=%s", list(updates.values()) + [task_id, user["id"]])
                # Recalculate plan progress
                cur.execute("SELECT plan_id FROM tasks WHERE id=%s AND user_id=%s", (task_id, user["id"]))
                row = cur.fetchone()
                if row:
                    self._recalc_plan(cur, row["plan_id"])
                conn.commit()
            conn.close()
            return self.send_json(200, {"ok": True, "message": "已更新"})
        except Exception as e:
            return self.send_json(500, {"ok": False, "error": str(e)})

    def _recalc_plan(self, cur, plan_id: str):
        cur.execute("SELECT COALESCE(AVG(progress),0) avg_progress, COUNT(*) cnt FROM tasks WHERE plan_id=%s", (plan_id,))
        row = cur.fetchone()
        progress = round(row["avg_progress"]) if row["cnt"] else 0
        status = "completed" if progress >= 100 else ("in_progress" if progress > 0 else "not_started")
        cur.execute("UPDATE plans SET progress=%s, status=%s, updated_at=%s WHERE id=%s", (progress, status, now_dt(), plan_id))

    # ---- Logs ----
    def handle_create_log(self, plan_id: str):
        user = require_auth(self.headers)
        if not user:
            return self.send_json(401, {"ok": False, "error": "未登录"})
        try:
            body = self.read_body()
            lid = uuid.uuid4().hex[:16]
            ts = now_dt()
            conn = get_db()
            cur = conn.cursor()
            cur.execute("INSERT INTO logs (id,plan_id,task_id,user_id,date,duration_minutes,summary,notes,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (lid, plan_id, body.get("taskId") or None, user["id"], ts[:10], int(body.get("durationMinutes", 30)), body.get("summary", ""), body.get("notes", ""), ts))
            if body.get("taskId"):
                cur.execute("UPDATE tasks SET spent_minutes=spent_minutes+%s, updated_at=%s WHERE id=%s AND user_id=%s",
                            (int(body.get("durationMinutes", 30)), ts, body["taskId"], user["id"]))
                cur.execute("SELECT plan_id FROM tasks WHERE id=%s", (body["taskId"],))
                row = cur.fetchone()
                if row:
                    self._recalc_plan(cur, row["plan_id"])
            conn.commit()
            conn.close()
            return self.send_json(201, {"ok": True, "id": lid})
        except Exception as e:
            return self.send_json(500, {"ok": False, "error": str(e)})

    def handle_list_logs(self, plan_id: str = None):
        user = require_auth(self.headers)
        if not user:
            return self.send_json(401, {"ok": False, "error": "未登录"})
        conn = get_db()
        cur = conn.cursor()
        if plan_id:
            cur.execute("SELECT l.*, p.title plan_title, t.title task_title FROM logs l JOIN plans p ON p.id=l.plan_id LEFT JOIN tasks t ON t.id=l.task_id WHERE l.plan_id=%s AND l.user_id=%s ORDER BY l.created_at DESC", (plan_id, user["id"]))
        else:
            cur.execute("SELECT l.*, p.title plan_title, t.title task_title FROM logs l JOIN plans p ON p.id=l.plan_id LEFT JOIN tasks t ON t.id=l.task_id WHERE l.user_id=%s ORDER BY l.created_at DESC", (user["id"],))
        rows = cur.fetchall()
        conn.close()
        return self.send_json(200, {"ok": True, "logs": rows})

    # ---- Stats ----
    def handle_stats(self):
        user = require_auth(self.headers)
        if not user:
            return self.send_json(401, {"ok": False, "error": "未登录"})
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) total, SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) completed, AVG(progress) avg_progress FROM plans WHERE user_id=%s", (user["id"],))
        ps = cur.fetchone()
        cur.execute("SELECT COALESCE(SUM(duration_minutes),0) total_minutes FROM logs WHERE user_id=%s", (user["id"],))
        lm = cur.fetchone()
        conn.close()
        return self.send_json(200, {"ok": True, "stats": {"total": ps["total"], "completed": ps["completed"], "avg_progress": float(ps["avg_progress"] or 0), "total_minutes": lm["total_minutes"]}})

    # ---- AI Analyze ----
    def handle_analyze_link(self):
        try:
            body = self.read_body()
            url = str(body.get("url", "")).strip()
            if not re.match(r"^https?://", url):
                return self.send_json(400, {"error": "请输入 http/https 学习链接"})
            goal = str(body.get("goal", "")).strip()
            level = str(body.get("level", "进阶")).strip()
            hours = int(body.get("hoursPerWeek", 5))

            # Strategy 1: Try AI Hub (internal LLM service)
            try:
                hub_plan = call_ai_hub(url, goal, level, hours)
                if hub_plan:
                    plan = normalize_plan(hub_plan, url)
                    plan["aiStrategy"] = "ai-hub"
                    return self.send_json(200, {"ok": True, "plan": plan, "fetched": {"kind": "ai-hub", "title": plan.get("title", "")}})
            except Exception as e:
                print(f"[AI-Hub] Error: {e}", file=sys.stderr, flush=True)

            # Strategy 2: Collect link context and try direct AI call
            try:
                ctx = collect_link_context(url)
                fetched_info = {"kind": ctx.get("kind"), "title": ctx.get("title"), "headings": ctx.get("headings", [])[:10]}
            except Exception as e:
                print(f"[Fetch] Error reading link: {e}", file=sys.stderr, flush=True)
                return self.send_json(502, {"ok": False, "error": f"无法读取链接内容：{e}"})

            # Strategy 3: Direct AI (OpenAI/DeepSeek)
            try:
                ai_plan = call_ai(ctx, goal, level, hours)
                if ai_plan:
                    plan = normalize_plan(ai_plan, url)
                    plan["aiStrategy"] = "direct-ai"
                    return self.send_json(200, {"ok": True, "plan": plan, "fetched": fetched_info})
            except Exception as e:
                print(f"[AI-Direct] Error: {e}", file=sys.stderr, flush=True)

            # Strategy 4: Local fallback (heading-based heuristic)
            print(f"[AI] Fallback to heuristic for {url}", file=sys.stderr, flush=True)
            try:
                plan = fallback_plan(ctx, goal, level, hours)
                plan = normalize_plan(plan, url)
                plan["aiStrategy"] = "fallback"
                return self.send_json(200, {"ok": True, "plan": plan, "fetched": fetched_info})
            except Exception as e:
                print(f"[Fallback] Error: {e}", file=sys.stderr, flush=True)
                return self.send_json(500, {"ok": False, "error": f"生成计划失败：{e}"})

        except Exception as e:
            print(f"[Analyze] Unhandled error: {e}", file=sys.stderr, flush=True)
            return self.send_json(500, {"ok": False, "error": str(e)})

    # ---- Router ----
    def do_GET(self):
        base, parts = self.parse_path()
        try:
            if base == "/api/auth/me":
                return self.handle_auth_me()
            if base == "/api/admin/users":
                return self.handle_admin_list_users()
            if base == "/api/stats":
                return self.handle_stats()
            if base == "/api/plans" and len(parts) == 2:
                return self.handle_list_plans()
            if len(parts) >= 3 and parts[0] == "api" and parts[1] == "plans":
                pid = parts[2]
                if len(parts) == 3:
                    return self.handle_get_plan(pid)
                if len(parts) == 4 and parts[3] == "logs":
                    return self.handle_list_logs(pid)
            if base == "/api/logs" and len(parts) == 2:
                return self.handle_list_logs()
        except Exception as e:
            return self.send_json(500, {"ok": False, "error": str(e)})
        return super().do_GET()

    def do_POST(self):
        base, parts = self.parse_path()
        try:
            if base == "/api/auth/register":
                return self.handle_auth_register()
            if base == "/api/auth/login":
                return self.handle_auth_login()
            if base == "/api/auth/logout":
                return self.handle_auth_logout()
            if base == "/api/analyze-link":
                return self.handle_analyze_link()
            if base == "/api/plans" and len(parts) == 2:
                return self.handle_create_plan()
            if len(parts) >= 4 and parts[0] == "api" and parts[1] == "plans":
                pid = parts[2]
                if parts[3] == "duplicate":
                    return self.handle_duplicate_plan(pid)
                if parts[3] == "milestones":
                    return self.handle_create_milestone(pid)
                if parts[3] == "logs":
                    return self.handle_create_log(pid)
            if len(parts) >= 4 and parts[0] == "api" and parts[1] == "milestones":
                if parts[3] == "tasks":
                    return self.handle_create_task(parts[2])
            # Admin toggle
            if len(parts) >= 5 and "/".join(parts[:3]) == "api/admin/users":
                action = parts[3]
                if action == "activate":
                    return self.handle_admin_toggle_active(parts[4], True)
                if action == "deactivate":
                    return self.handle_admin_toggle_active(parts[4], False)
        except Exception as e:
            return self.send_json(500, {"ok": False, "error": str(e)})
        return self.send_json(404, {"error": "not_found"})

    def do_PUT(self):
        base, parts = self.parse_path()
        try:
            if "/".join(parts[:3]) == "api/admin/users":
                return self.handle_admin_update_user(parts[3])
            if len(parts) >= 4 and parts[0] == "api" and parts[1] == "plans":
                if parts[3] == "tasks":
                    return self.handle_update_task(parts[4])
            if len(parts) >= 4 and parts[0] == "api" and parts[1] == "milestones":
                return self.handle_update_milestone(parts[2])
        except Exception as e:
            return self.send_json(500, {"ok": False, "error": str(e)})
        return self.send_json(404, {"error": "not_found"})

    def do_DELETE(self):
        base, parts = self.parse_path()
        try:
            if "/".join(parts[:3]) == "api/admin/users":
                return self.handle_admin_delete_user(parts[3])
            if len(parts) >= 3 and parts[0] == "api" and parts[1] == "plans":
                pid = parts[2]
                if len(parts) == 3:
                    return self.handle_delete_plan(pid)
            if len(parts) >= 4 and parts[0] == "api" and parts[1] == "milestones":
                return self.handle_delete_milestone(parts[2])
        except Exception as e:
            return self.send_json(500, {"ok": False, "error": str(e)})
        return self.send_json(404, {"error": "not_found"})


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------
def main():
    print("Connecting to MySQL...", flush=True)
    init_mysql()
    print("MySQL tables ready.", flush=True)
    os.chdir(ROOT)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Learning Tracker listening on http://0.0.0.0:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
