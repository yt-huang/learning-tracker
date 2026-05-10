#!/usr/bin/env python3
"""Learning Tracker AI backend.

A dependency-free HTTP server that serves the static SPA and exposes
POST /api/analyze-link. Business data remains in browser SQLite; this server only
fetches/analyzes a link and returns structured plan JSON.
"""
from __future__ import annotations

import base64
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = int(os.getenv("PORT", "8010"))
MAX_CONTENT_CHARS = 14000


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


def call_ai(ctx: dict, goal: str, level: str, hours_per_week: int) -> dict | None:
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("AI_API_KEY")
    if not api_key:
        return None
    base_url = os.getenv("OPENAI_BASE_URL") or ("https://api.deepseek.com/v1" if os.getenv("DEEPSEEK_API_KEY") else "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL") or os.getenv("AI_MODEL") or ("deepseek-chat" if os.getenv("DEEPSEEK_API_KEY") else "gpt-4o-mini")
    prompt = f"""
你是学习规划专家和产品经理。请根据链接内容生成适合 Learning Tracker 的学习计划。
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

    def do_POST(self):
        if self.path != "/api/analyze-link":
            return self.send_json(404, {"error": "not_found"})
        try:
            length = int(self.headers.get("content-length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            url = str(payload.get("url") or "").strip()
            if not re.match(r"^https?://", url):
                return self.send_json(400, {"error": "请输入 http/https 学习链接"})
            goal = str(payload.get("goal") or "").strip()
            level = str(payload.get("level") or "进阶").strip()
            hours = int(payload.get("hoursPerWeek") or 5)
            ctx = collect_link_context(url)
            plan = call_ai(ctx, goal, level, hours) or fallback_plan(ctx, goal, level, hours)
            plan = normalize_plan(plan, url)
            return self.send_json(200, {"ok": True, "plan": plan, "fetched": {"kind": ctx.get("kind"), "title": ctx.get("title"), "headings": ctx.get("headings", [])[:10]}})
        except urllib.error.HTTPError as e:
            return self.send_json(502, {"ok": False, "error": f"链接读取失败：HTTP {e.code}"})
        except Exception as e:
            return self.send_json(500, {"ok": False, "error": str(e)})


def main():
    os.chdir(ROOT)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Learning Tracker server listening on http://0.0.0.0:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
