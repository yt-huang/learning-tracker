#!/usr/bin/env python3
"""Learning Tracker AI backend with multi-user support.

A dependency-free HTTP server that serves the static SPA, exposes
user registration/login/CRUD, and POST /api/analyze-link.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
import sqlite3
import sys
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = int(os.getenv("PORT", "8010"))
MAX_CONTENT_CHARS = 14000
USER_DB = Path(__file__).resolve().parent / "users.db"
SECRET = os.getenv("AUTH_SECRET", "learning-tracker-secret-change-me")
TOKEN_EXPIRY = 7 * 24 * 3600  # 7 days


# ---------------------------------------------------------------------------
# User database helpers
# ---------------------------------------------------------------------------

def get_user_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(USER_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT DEFAULT '',
            role TEXT DEFAULT 'user',
            active INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            expires_at REAL NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    return conn


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


def get_user_by_token(token: str) -> dict | None:
    if not token:
        return None
    db = get_user_db()
    row = db.execute(
        "SELECT u.* FROM users u JOIN tokens t ON t.user_id=u.id WHERE t.token=? AND t.expires_at>?",
        (token, time.time()),
    ).fetchone()
    db.close()
    return dict(row) if row else None


def require_auth(headers) -> dict | None:
    """Extract Bearer token and return user dict or None."""
    auth = headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    return get_user_by_token(auth[7:])


# ---------------------------------------------------------------------------
# URL fetching / AI analysis
# ---------------------------------------------------------------------------

def fetch_url(url: str, timeout: int = 18) -> tuple[str, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "LearningTrackerBot/1.0 (+https://github.com/yt-huang/learning-tracker)",
            "Accept": "text/html,application/xhtml+xml,text/markdown,text/plain,application/json;q=0.8,*/*;q=0.5",
        },
    )
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
    api = f"https://api.github.com/repos/{owner}/{repo}/readme"
    try:
        data, _ = fetch_url(api)
        payload = json.loads(data)
        content = payload.get("content", "")
        readme = base64.b64decode(content).decode("utf-8", errors="replace") if content else ""
        repo_api = f"https://api.github.com/repos/{owner}/{repo}"
        repo_meta, _ = fetch_url(repo_api)
        meta = json.loads(repo_meta)
        return {
            "kind": "github",
            "title": f"{owner}/{repo}",
            "description": meta.get("description") or "",
            "content": readme,
            "topics": meta.get("topics") or [],
            "language": meta.get("language") or "",
            "stars": meta.get("stargazers_count") or 0,
        }
    except Exception:
        raw = f"https://raw.githubusercontent.com/{owner}/{repo}/main/README.md"
        try:
            readme, _ = fetch_url(raw)
            return {"kind": "github", "title": f"{owner}/{repo}", "description": "", "content": readme, "topics": [], "language": "", "stars": 0}
        except Exception:
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
    return {
        "kind": "web",
        "url": url,
        "title": title or parsed.netloc,
        "description": "",
        "content": text[:MAX_CONTENT_CHARS],
        "headings": headings,
        "topics": [],
        "language": "",
        "stars": 0,
    }


def fallback_plan(ctx: dict, goal: str = "", level: str = "进阶", hours_per_week: int = 5) -> dict:
    headings = [h for h in ctx.get("headings", []) if 3 <= len(h) <= 80]
    title = ctx.get("title") or "AI 生成学习计划"
    if len(headings) >= 4:
        phase_titles = headings[:5]
    else:
        phase_titles = ["内容概览与学习目标", "核心概念精读", "实践复现与案例分析", "总结输出与迁移应用"]
    total_hours = max(8, min(40, len(phase_titles) * max(2, int(hours_per_week or 5))))
    per_phase = max(90, round(total_hours * 60 / len(phase_titles)))
    milestones = []
    for i, phase in enumerate(phase_titles, 1):
        milestones.append({
            "title": f"阶段{i}：{phase}",
            "description": f"围绕 {title} 的“{phase}”建立阶段性理解和可验证产出。",
            "goal": f"掌握 {phase}，并形成可复用笔记/实践记录。",
            "tasks": [
                {"title": f"阅读并梳理：{phase}", "description": "提取关键概念、术语、依赖关系和疑问点。", "estimatedMinutes": round(per_phase * 0.35), "acceptance": "完成结构化笔记，列出不少于 5 个关键点。"},
                {"title": f"实践验证：{phase}", "description": "根据资料内容完成示例、命令、代码或操作演练。", "estimatedMinutes": round(per_phase * 0.45), "acceptance": "有可截图、可运行或可复述的实践结果。"},
                {"title": f"复盘输出：{phase}", "description": "总结本阶段收获、阻塞和下一步计划。", "estimatedMinutes": round(per_phase * 0.2), "acceptance": "写出阶段总结，并更新学习日志。"},
            ],
        })
    return {
        "title": title,
        "sourceUrl": ctx.get("url", ""),
        "description": goal or ctx.get("description") or f"基于链接内容自动生成的 {title} 学习计划。",
        "category": "GitHub 项目" if ctx.get("kind") == "github" else "在线资料",
        "difficulty": level or "进阶",
        "estimatedHours": total_hours,
        "milestones": milestones,
        "aiUsed": False,
        "analysisSummary": "未配置 AI API Key，已使用链接标题/目录结构生成启发式学习计划。",
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
    body = {
        "clientName": "learning-tracker",
        "template": "learning_plan",
        "url": url,
        "goal": goal,
        "level": level,
        "hoursPerWeek": hours_per_week,
    }
    req = urllib.request.Request(
        hub_url + "/api/v1/analyze-learning-link",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {hub_token}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    plan = payload.get("plan")
    if isinstance(plan, dict):
        plan.setdefault("analysisSummary", f"由 AI Hub 内网服务生成：{payload.get('provider', '')}/{payload.get('model', '')}")
        return plan
    return None


def call_ai(ctx: dict, goal: str, level: str, hours_per_week: int) -> dict | None:
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("AI_API_KEY")
    if not api_key:
        return None
    base_url = os.getenv("OPENAI_BASE_URL") or ("https://api.deepseek.com/v1" if os.getenv("DEEPSEEK_API_KEY") else "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL") or os.getenv("AI_MODEL") or ("deepseek-chat" if os.getenv("DEEPSEEK_API_KEY") else "gpt-4o-mini")
    prompt = f"""你是学习规划专家和产品经理。请根据链接内容生成适合 Learning Tracker 的学习计划。
必须只输出 JSON，不要 Markdown，不要解释。
JSON 字段必须为：title, sourceUrl, description, category, difficulty, estimatedHours, analysisSummary, milestones。
milestones 每项字段：title, description, goal, tasks。
tasks 每项字段：title, description, estimatedMinutes, acceptance。
要求：
- 拆成 4-6 个阶段。
- 每个阶段 3-5 个任务。
- 任务要具体、可执行、可记录日志。
- 如果是 GitHub 项目，需要包含环境准备、核心代码/文档理解、实践验证、总结输出。
- estimatedHours 要结合内容复杂度和用户每周学习时间。

用户目标：{goal or '未填写'}
用户水平：{level or '进阶'}
每周可投入小时：{hours_per_week or 5}
链接上下文 JSON：
{json.dumps(ctx, ensure_ascii=False)[:MAX_CONTENT_CHARS]}
""".strip()
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You output strict JSON only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    content = payload["choices"][0]["message"]["content"]
    plan = extract_json(content)
    plan["aiUsed"] = True
    return plan


def normalize_plan(plan: dict, source_url: str) -> dict:
    plan.setdefault("sourceUrl", source_url)
    plan.setdefault("title", "AI 生成学习计划")
    plan.setdefault("description", "AI 根据链接内容生成的学习计划")
    plan.setdefault("category", "AI 分析")
    plan.setdefault("difficulty", "进阶")
    plan.setdefault("estimatedHours", 12)
    clean_milestones = []
    for idx, m in enumerate(plan.get("milestones") or [], 1):
        tasks = []
        for t in m.get("tasks") or []:
            tasks.append({
                "title": str(t.get("title") or "学习任务"),
                "description": str(t.get("description") or t.get("acceptance") or "完成该任务并记录学习日志。"),
                "estimatedMinutes": int(t.get("estimatedMinutes") or 60),
                "priority": t.get("priority") or "medium",
                "acceptance": t.get("acceptance") or "完成后能清楚说明学习收获。",
            })
        clean_milestones.append({
            "title": str(m.get("title") or f"阶段{idx}"),
            "description": str(m.get("description") or m.get("goal") or "阶段学习目标"),
            "goal": str(m.get("goal") or m.get("description") or "完成阶段目标"),
            "orderIndex": idx,
            "tasks": tasks[:5],
        })
    plan["milestones"] = clean_milestones[:6]
    return plan


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store" if self.path.startswith("/api/") else "no-cache")
        super().end_headers()

    def send_json(self, status: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
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
        """Return (base_path, path_parts) from self.path."""
        parsed = urllib.parse.urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        base = "/" + "/".join(parts[:3]) if parts else "/"
        return base, parts

    # ---- Auth endpoints ----

    def handle_auth_register(self):
        try:
            body = self.read_body()
            username = str(body.get("username", "")).strip()
            password = str(body.get("password", "")).strip()
            email = str(body.get("email", "")).strip()
            if not username or len(username) < 2:
                return self.send_json(400, {"ok": False, "error": "用户名至少 2 个字符"})
            if not password or len(password) < 4:
                return self.send_json(400, {"ok": False, "error": "密码至少 4 个字符"})
            db = get_user_db()
            existing = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            if existing:
                db.close()
                return self.send_json(409, {"ok": False, "error": "用户名已存在"})
            # First user is admin & auto-active
            user_count = db.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
            role = "admin" if user_count == 0 else "user"
            active = 1 if user_count == 0 else 0  # requires activation for non-admin
            uid = uuid.uuid4().hex[:16]
            pwh = hash_password(password)
            ts = now_iso()
            db.execute(
                "INSERT INTO users (id, username, password_hash, email, role, active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (uid, username, pwh, email, role, active, ts, ts),
            )
            db.commit()
            # Auto-login: generate token
            token = generate_token()
            db.execute("INSERT INTO tokens (token, user_id, expires_at) VALUES (?, ?, ?)", (token, uid, time.time() + TOKEN_EXPIRY))
            db.commit()
            db.close()
            return self.send_json(201, {
                "ok": True,
                "message": "注册成功" if active else "注册成功，等待管理员激活",
                "token": token,
                "user": {"id": uid, "username": username, "email": email, "role": role, "active": active},
            })
        except Exception as e:
            return self.send_json(500, {"ok": False, "error": str(e)})

    def handle_auth_login(self):
        try:
            body = self.read_body()
            username = str(body.get("username", "")).strip()
            password = str(body.get("password", "")).strip()
            if not username or not password:
                return self.send_json(400, {"ok": False, "error": "请输入用户名和密码"})
            db = get_user_db()
            row = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            if not row:
                db.close()
                return self.send_json(401, {"ok": False, "error": "用户名或密码错误"})
            user = dict(row)
            if not verify_password(password, user["password_hash"]):
                db.close()
                return self.send_json(401, {"ok": False, "error": "用户名或密码错误"})
            if not user["active"]:
                db.close()
                return self.send_json(403, {"ok": False, "error": "账号未激活，请联系管理员"})
            # Generate token
            token = generate_token()
            db.execute("INSERT INTO tokens (token, user_id, expires_at) VALUES (?, ?, ?)", (token, user["id"], time.time() + TOKEN_EXPIRY))
            db.commit()
            db.close()
            return self.send_json(200, {
                "ok": True,
                "token": token,
                "user": {"id": user["id"], "username": user["username"], "email": user["email"], "role": user["role"], "active": user["active"]},
            })
        except Exception as e:
            return self.send_json(500, {"ok": False, "error": str(e)})

    def handle_auth_me(self):
        user = require_auth(self.headers)
        if not user:
            return self.send_json(401, {"ok": False, "error": "未登录或 token 已过期"})
        return self.send_json(200, {
            "ok": True,
            "user": {"id": user["id"], "username": user["username"], "email": user["email"], "role": user["role"], "active": user["active"]},
        })

    def handle_auth_logout(self):
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            db = get_user_db()
            db.execute("DELETE FROM tokens WHERE token=?", (auth[7:],))
            db.commit()
            db.close()
        return self.send_json(200, {"ok": True, "message": "已退出"})

    # ---- Admin user management ----

    def handle_admin_list_users(self):
        user = require_auth(self.headers)
        if not user:
            return self.send_json(401, {"ok": False, "error": "未登录"})
        if user["role"] != "admin":
            return self.send_json(403, {"ok": False, "error": "需要管理员权限"})
        db = get_user_db()
        rows = db.execute("SELECT id, username, email, role, active, created_at, updated_at FROM users ORDER BY created_at DESC").fetchall()
        db.close()
        return self.send_json(200, {"ok": True, "users": [dict(r) for r in rows]})

    def handle_admin_update_user(self, user_id: str):
        current_user = require_auth(self.headers)
        if not current_user:
            return self.send_json(401, {"ok": False, "error": "未登录"})
        if current_user["role"] != "admin":
            return self.send_json(403, {"ok": False, "error": "需要管理员权限"})
        try:
            body = self.read_body()
            db = get_user_db()
            existing = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if not existing:
                db.close()
                return self.send_json(404, {"ok": False, "error": "用户不存在"})
            updates = {}
            if "username" in body and str(body["username"]).strip():
                updates["username"] = str(body["username"]).strip()
            if "email" in body:
                updates["email"] = str(body["email"]).strip()
            if "role" in body and str(body["role"]).strip() in ("admin", "user"):
                updates["role"] = str(body["role"]).strip()
            if "password" in body and str(body["password"]).strip():
                updates["password_hash"] = hash_password(str(body["password"]).strip())
            if updates:
                updates["updated_at"] = now_iso()
                sets = ", ".join(f"{k}=?" for k in updates)
                vals = list(updates.values()) + [user_id]
                db.execute(f"UPDATE users SET {sets} WHERE id=?", vals)
                db.commit()
            updated = dict(db.execute("SELECT id, username, email, role, active, created_at, updated_at FROM users WHERE id=?", (user_id,)).fetchone())
            db.close()
            return self.send_json(200, {"ok": True, "user": updated})
        except Exception as e:
            return self.send_json(500, {"ok": False, "error": str(e)})

    def handle_admin_toggle_active(self, user_id: str, activate: bool):
        current_user = require_auth(self.headers)
        if not current_user:
            return self.send_json(401, {"ok": False, "error": "未登录"})
        if current_user["role"] != "admin":
            return self.send_json(403, {"ok": False, "error": "需要管理员权限"})
        # Prevent deactivating yourself
        if not activate and current_user["id"] == user_id:
            return self.send_json(400, {"ok": False, "error": "不能禁用自己"})
        db = get_user_db()
        existing = db.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone()
        if not existing:
            db.close()
            return self.send_json(404, {"ok": False, "error": "用户不存在"})
        db.execute("UPDATE users SET active=?, updated_at=? WHERE id=?", (1 if activate else 0, now_iso(), user_id))
        db.commit()
        db.close()
        return self.send_json(200, {"ok": True, "message": "已激活" if activate else "已禁用"})

    def handle_admin_delete_user(self, user_id: str):
        current_user = require_auth(self.headers)
        if not current_user:
            return self.send_json(401, {"ok": False, "error": "未登录"})
        if current_user["role"] != "admin":
            return self.send_json(403, {"ok": False, "error": "需要管理员权限"})
        if current_user["id"] == user_id:
            return self.send_json(400, {"ok": False, "error": "不能删除自己"})
        db = get_user_db()
        existing = db.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone()
        if not existing:
            db.close()
            return self.send_json(404, {"ok": False, "error": "用户不存在"})
        db.execute("DELETE FROM tokens WHERE user_id=?", (user_id,))
        db.execute("DELETE FROM users WHERE id=?", (user_id,))
        db.commit()
        db.close()
        return self.send_json(200, {"ok": True, "message": "已删除用户"})

    # ---- Plan analysis endpoint ----

    def handle_analyze_link(self):
        try:
            payload = self.read_body()
            url = str(payload.get("url") or "").strip()
            if not re.match(r"^https?://", url):
                return self.send_json(400, {"error": "请输入 http/https 学习链接"})
            goal = str(payload.get("goal") or "").strip()
            level = str(payload.get("level") or "进阶").strip()
            hours = int(payload.get("hoursPerWeek") or 5)
            try:
                hub_plan = call_ai_hub(url, goal, level, hours)
            except Exception as hub_error:
                print(f"AI Hub unavailable, fallback to local analyzer: {hub_error}", file=sys.stderr, flush=True)
                hub_plan = None
            if hub_plan:
                plan = normalize_plan(hub_plan, url)
                return self.send_json(200, {"ok": True, "plan": plan, "fetched": {"kind": "ai-hub", "title": plan.get("title"), "headings": []}})
            ctx = collect_link_context(url)
            plan = call_ai(ctx, goal, level, hours) or fallback_plan(ctx, goal, level, hours)
            plan = normalize_plan(plan, url)
            return self.send_json(200, {"ok": True, "plan": plan, "fetched": {"kind": ctx.get("kind"), "title": ctx.get("title"), "headings": ctx.get("headings", [])[:10]}})
        except urllib.error.HTTPError as e:
            return self.send_json(502, {"ok": False, "error": f"链接读取失败：HTTP {e.code}"})
        except Exception as e:
            return self.send_json(500, {"ok": False, "error": str(e)})

    # ---- Router ----

    def do_GET(self):
        base, parts = self.parse_path()
        if base == "/api/auth/me":
            return self.handle_auth_me()
        if base == "/api/admin/users":
            return self.handle_admin_list_users()
        return self.send_json(404, {"error": "not_found"})

    def do_POST(self):
        base, parts = self.parse_path()
        if base == "/api/auth/register":
            return self.handle_auth_register()
        if base == "/api/auth/login":
            return self.handle_auth_login()
        if base == "/api/auth/logout":
            return self.handle_auth_logout()
        if base == "/api/analyze-link":
            return self.handle_analyze_link()
        # admin routes with path params
        if len(parts) >= 4 and "/".join(parts[:3]) == "api/admin/users":
            action = parts[3] if len(parts) > 3 else ""
            if action == "activate" and len(parts) >= 5:
                return self.handle_admin_toggle_active(parts[4], True)
            if action == "deactivate" and len(parts) >= 5:
                return self.handle_admin_toggle_active(parts[4], False)
        return self.send_json(404, {"error": "not_found"})

    def do_PUT(self):
        base, parts = self.parse_path()
        if len(parts) >= 4 and "/".join(parts[:3]) == "api/admin/users":
            # PUT /api/admin/users/<id>
            user_id = parts[3]
            return self.handle_admin_update_user(user_id)
        return self.send_json(404, {"error": "not_found"})

    def do_DELETE(self):
        base, parts = self.parse_path()
        if len(parts) >= 4 and "/".join(parts[:3]) == "api/admin/users":
            return self.handle_admin_delete_user(parts[3])
        return self.send_json(404, {"error": "not_found"})


def main():
    # Ensure initial admin user if DB is empty
    db = get_user_db()
    count = db.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
    if count == 0:
        uid = uuid.uuid4().hex[:16]
        pwh = hash_password("admin123")
        ts = now_iso()
        db.execute(
            "INSERT INTO users (id, username, password_hash, email, role, active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (uid, "admin", pwh, "", "admin", 1, ts, ts),
        )
        db.commit()
        print("ℹ️  Created default admin user: admin / admin123", file=sys.stderr, flush=True)
    db.close()

    os.chdir(ROOT)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Learning Tracker server listening on http://0.0.0.0:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
