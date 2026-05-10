from __future__ import annotations

import base64, hashlib, html, json, os, re, secrets, sqlite3, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
PORT = int(os.getenv("PORT", "8020"))
DB_PATH = os.getenv("DB_PATH", "/data/ai_hub.db")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
ADMIN_TOKEN = os.getenv("AI_HUB_ADMIN_TOKEN", "dev-admin-token")
INTERNAL_TOKEN = os.getenv("AI_HUB_INTERNAL_TOKEN", "dev-internal-token")
MASTER_KEY = os.getenv("AI_HUB_MASTER_KEY", "dev-master-key-change-me")
MAX_CONTENT_CHARS = 14000


def now(): return datetime.utcnow().isoformat()

def db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS providers(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT UNIQUE NOT NULL,
          base_url TEXT NOT NULL,
          api_key_encrypted TEXT NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS models(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          provider_id INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
          model_id TEXT NOT NULL,
          display_name TEXT DEFAULT '',
          purpose TEXT DEFAULT 'learning_plan',
          temperature REAL DEFAULT 0.3,
          max_tokens INTEGER DEFAULT 4096,
          is_default INTEGER DEFAULT 0,
          enabled INTEGER DEFAULT 1,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS call_logs(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          client_name TEXT DEFAULT 'unknown',
          template TEXT DEFAULT 'learning_plan',
          provider_name TEXT DEFAULT '',
          model_id TEXT DEFAULT '',
          success INTEGER DEFAULT 0,
          latency_ms INTEGER DEFAULT 0,
          error_message TEXT DEFAULT '',
          created_at TEXT NOT NULL
        );
        ''')


def keystream(n:int)->bytes:
    out=b''; i=0; seed=MASTER_KEY.encode()
    while len(out)<n:
        out += hashlib.sha256(seed + str(i).encode()).digest(); i+=1
    return out[:n]

def encrypt_secret(s:str)->str:
    b=s.encode(); k=keystream(len(b)); return base64.urlsafe_b64encode(bytes(x^y for x,y in zip(b,k))).decode()

def decrypt_secret(s:str)->str:
    b=base64.urlsafe_b64decode(s.encode()); k=keystream(len(b)); return bytes(x^y for x,y in zip(b,k)).decode()


def read_json(handler):
    length = int(handler.headers.get('content-length','0'))
    return json.loads(handler.rfile.read(length).decode('utf-8') or '{}')

def bearer(handler): return (handler.headers.get('authorization') or '').removeprefix('Bearer ').strip()

def require_admin(handler):
    if not secrets.compare_digest(bearer(handler), ADMIN_TOKEN):
        handler.send_json(401, {'detail':'admin token invalid'}); return False
    return True

def require_internal(handler):
    if not secrets.compare_digest(bearer(handler), INTERNAL_TOKEN):
        handler.send_json(401, {'detail':'internal token invalid'}); return False
    return True


def fetch_url(url, timeout=20):
    req=urllib.request.Request(url,headers={'User-Agent':'AIAnalysisHub/0.1','Accept':'text/html,text/markdown,text/plain,application/json,*/*;q=0.5'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        ctype=resp.headers.get('content-type',''); raw=resp.read(512_000)
    enc='utf-8'; m=re.search(r'charset=([^;]+)',ctype,re.I)
    if m: enc=m.group(1).strip()
    return raw.decode(enc,errors='replace'), ctype

def markdown_headings(text):
    out=[]
    for line in text.splitlines():
        m=re.match(r'^#{1,3}\s+(.+?)\s*$',line)
        if m:
            h=re.sub(r'[#`*_\[\]]','',m.group(1)).strip()
            if h and h not in out: out.append(h)
        if len(out)>=24: break
    return out

def html_to_text(markup):
    title=''; tm=re.search(r'<title[^>]*>(.*?)</title>',markup,re.I|re.S)
    if tm: title=html.unescape(re.sub(r'\s+',' ',tm.group(1))).strip()
    headings=[]
    for m in re.finditer(r'<h[1-3][^>]*>(.*?)</h[1-3]>',markup,re.I|re.S):
        h=html.unescape(re.sub(r'<[^>]+>',' ',m.group(1))).strip()
        if h and h not in headings: headings.append(h)
    text=re.sub(r'<script[\s\S]*?</script>|<style[\s\S]*?</style>',' ',markup,flags=re.I)
    text=html.unescape(re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',text))).strip()
    return text, headings[:24], title

def collect_context(url):
    parsed=urllib.parse.urlparse(url)
    if parsed.netloc.lower() in {'github.com','www.github.com'}:
        parts=[p for p in parsed.path.split('/') if p]
        if len(parts)>=2:
            owner,repo=parts[0],parts[1]; meta={}; readme=''
            try:
                d,_=fetch_url(f'https://api.github.com/repos/{owner}/{repo}'); meta=json.loads(d)
                r,_=fetch_url(f'https://api.github.com/repos/{owner}/{repo}/readme'); readme=base64.b64decode(json.loads(r).get('content','')).decode('utf-8',errors='replace')
            except Exception: pass
            return {'kind':'github','url':url,'title':f'{owner}/{repo}','description':meta.get('description') or '', 'topics':meta.get('topics') or [], 'language':meta.get('language') or '', 'stars':meta.get('stargazers_count') or 0, 'headings':markdown_headings(readme), 'content':readme[:MAX_CONTENT_CHARS]}
    data,ctype=fetch_url(url)
    if 'html' in ctype.lower() or '<html' in data[:500].lower(): text,headings,title=html_to_text(data)
    else: text,headings,title=data,markdown_headings(data),parsed.netloc
    return {'kind':'web','url':url,'title':title or parsed.netloc,'description':'','topics':[],'language':'','stars':0,'headings':headings,'content':text[:MAX_CONTENT_CHARS]}

def extract_json(text):
    text=re.sub(r'^```(?:json)?\s*|\s*```$','',text.strip(),flags=re.I|re.S).strip()
    try: return json.loads(text)
    except json.JSONDecodeError: return json.loads(text[text.find('{'):text.rfind('}')+1])

def select_model(con):
    q='''SELECT m.*, p.name provider_name, p.base_url, p.api_key_encrypted FROM models m JOIN providers p ON p.id=m.provider_id WHERE m.enabled=1 AND p.enabled=1 ORDER BY m.is_default DESC, m.id DESC LIMIT 1'''
    row=con.execute(q).fetchone()
    if not row: raise RuntimeError('请先在 AI Hub 后台配置并启用 Provider 和 Model')
    return dict(row)

def call_model(m, ctx, data):
    key=decrypt_secret(m['api_key_encrypted'])
    prompt=f'''你是学习规划专家和产品经理。根据链接内容生成适合 Learning Tracker 的学习计划。\n只输出 JSON，不要 Markdown。字段：title, sourceUrl, description, category, difficulty, estimatedHours, analysisSummary, milestones。\nmilestones 每项字段：title, description, goal, tasks。tasks 每项字段：title, description, estimatedMinutes, acceptance。\n要求：4-6 个阶段，每阶段 3-5 个具体可执行任务，可记录学习日志。\n用户目标：{data.get('goal') or '未填写'}\n用户水平：{data.get('level') or '进阶'}\n每周可投入小时：{data.get('hoursPerWeek') or 5}\n链接上下文：{json.dumps(ctx, ensure_ascii=False)[:MAX_CONTENT_CHARS]}'''
    body={'model':m['model_id'],'messages':[{'role':'system','content':'You output strict JSON only.'},{'role':'user','content':prompt}], 'temperature':float(m['temperature'] or 0.3),'response_format':{'type':'json_object'}}
    req=urllib.request.Request(m['base_url'].rstrip('/')+'/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':f'Bearer {key}'},method='POST')
    with urllib.request.urlopen(req,timeout=90) as resp: payload=json.loads(resp.read().decode())
    plan=extract_json(payload['choices'][0]['message']['content']); plan['aiUsed']=True
    plan.setdefault('analysisSummary',f"由 AI Hub 使用 {m['provider_name']}/{m['model_id']} 生成。")
    return plan

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw): super().__init__(*a,directory=str(STATIC),**kw)
    def send_json(self,status,payload):
        b=json.dumps(payload,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path in {'/', '/admin'}:
            self.path = '/admin.html'
            return super().do_GET()
        if self.path=='/health':
            with db() as con: return self.send_json(200, {'ok':True,'providers':con.execute('select count(*) from providers').fetchone()[0],'models':con.execute('select count(*) from models').fetchone()[0]})
        if self.path.startswith('/api/admin/'):
            if not require_admin(self): return
            with db() as con:
                if self.path=='/api/admin/providers':
                    rows=con.execute('select * from providers order by id desc').fetchall(); return self.send_json(200, {'items':[{'id':r['id'],'name':r['name'],'baseUrl':r['base_url'],'apiKeyMasked':'********' if r['api_key_encrypted'] else '', 'enabled':bool(r['enabled']),'createdAt':r['created_at'],'updatedAt':r['updated_at']} for r in rows]})
                if self.path=='/api/admin/models':
                    rows=con.execute('select m.*,p.name provider_name from models m join providers p on p.id=m.provider_id order by m.is_default desc,m.id desc').fetchall(); return self.send_json(200, {'items':[{'id':r['id'],'providerId':r['provider_id'],'providerName':r['provider_name'],'modelId':r['model_id'],'displayName':r['display_name'],'purpose':r['purpose'],'temperature':r['temperature'],'maxTokens':r['max_tokens'],'isDefault':bool(r['is_default']),'enabled':bool(r['enabled'])} for r in rows]})
                if self.path=='/api/admin/logs':
                    rows=con.execute('select * from call_logs order by id desc limit 80').fetchall(); return self.send_json(200, {'items':[{'id':r['id'],'clientName':r['client_name'],'template':r['template'],'provider':r['provider_name'],'model':r['model_id'],'success':bool(r['success']),'latencyMs':r['latency_ms'],'error':r['error_message'],'createdAt':r['created_at']} for r in rows]})
        return super().do_GET()
    def do_POST(self):
        try:
            if self.path=='/api/auth/login':
                d=read_json(self); ok=secrets.compare_digest(d.get('username',''),ADMIN_USERNAME) and secrets.compare_digest(d.get('password',''),ADMIN_PASSWORD)
                return self.send_json(200 if ok else 401, {'ok':ok,'token':ADMIN_TOKEN} if ok else {'detail':'用户名或密码错误'})
            if self.path=='/api/admin/providers':
                if not require_admin(self): return
                d=read_json(self); t=now()
                with db() as con:
                    cur=con.execute('insert into providers(name,base_url,api_key_encrypted,enabled,created_at,updated_at) values(?,?,?,?,?,?)',(d['name'].strip(),d['baseUrl'].strip().rstrip('/'),encrypt_secret(d.get('apiKey','').strip()),1 if d.get('enabled',True) else 0,t,t)); con.commit()
                    return self.send_json(200, {'id':cur.lastrowid,'name':d['name'],'baseUrl':d['baseUrl'],'apiKeyMasked':'********','enabled':d.get('enabled',True),'createdAt':t,'updatedAt':t})
            if self.path=='/api/admin/models':
                if not require_admin(self): return
                d=read_json(self); t=now()
                with db() as con:
                    if d.get('isDefault'): con.execute('update models set is_default=0')
                    cur=con.execute('insert into models(provider_id,model_id,display_name,purpose,temperature,max_tokens,is_default,enabled,created_at,updated_at) values(?,?,?,?,?,?,?,?,?,?)',(d['providerId'],d['modelId'].strip(),d.get('displayName','').strip(),d.get('purpose','learning_plan'),float(d.get('temperature',0.3)),int(d.get('maxTokens',4096)),1 if d.get('isDefault') else 0,1 if d.get('enabled',True) else 0,t,t)); con.commit()
                    return self.send_json(200, {'id':cur.lastrowid})
            if self.path=='/api/admin/test-model':
                if not require_admin(self): return
                start=time.time()
                with db() as con: m=select_model(con)
                key=decrypt_secret(m['api_key_encrypted']); body={'model':m['model_id'],'messages':[{'role':'user','content':'Return exactly: pong'}],'temperature':0}
                req=urllib.request.Request(m['base_url'].rstrip('/')+'/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':f'Bearer {key}'},method='POST')
                with urllib.request.urlopen(req,timeout=30) as resp: payload=json.loads(resp.read().decode())
                return self.send_json(200, {'ok':True,'provider':m['provider_name'],'model':m['model_id'],'latencyMs':int((time.time()-start)*1000),'response':payload['choices'][0]['message']['content']})
            if self.path=='/api/v1/analyze-learning-link':
                if not require_internal(self): return
                start=time.time(); data=read_json(self); model=None
                try:
                    if not re.match(r'^https?://',data.get('url','')): raise RuntimeError('请输入 http/https 学习链接')
                    with db() as con: model=select_model(con)
                    ctx=collect_context(data['url']); plan=call_model(model,ctx,data)
                    with db() as con: con.execute('insert into call_logs(client_name,template,provider_name,model_id,success,latency_ms,error_message,created_at) values(?,?,?,?,?,?,?,?)',(data.get('clientName','learning-tracker'),data.get('template','learning_plan'),model['provider_name'],model['model_id'],1,int((time.time()-start)*1000),'',now())); con.commit()
                    return self.send_json(200, {'ok':True,'plan':plan,'provider':model['provider_name'],'model':model['model_id'],'fetched':{'kind':ctx.get('kind'),'title':ctx.get('title'),'headings':ctx.get('headings',[])[:10]}})
                except Exception as e:
                    with db() as con: con.execute('insert into call_logs(client_name,template,provider_name,model_id,success,latency_ms,error_message,created_at) values(?,?,?,?,?,?,?,?)',(data.get('clientName','learning-tracker'),data.get('template','learning_plan'),model['provider_name'] if model else '',model['model_id'] if model else '',0,int((time.time()-start)*1000),str(e),now())); con.commit()
                    return self.send_json(500, {'ok':False,'error':str(e)})
            return self.send_json(404, {'error':'not_found'})
        except urllib.error.HTTPError as e: return self.send_json(502, {'ok':False,'error':f'upstream HTTP {e.code}: {e.read().decode(errors="replace")[:500]}'})
        except Exception as e: return self.send_json(500, {'ok':False,'error':str(e)})
    def do_DELETE(self):
        if not require_admin(self): return
        with db() as con:
            m=re.match(r'/api/admin/providers/(\d+)$',self.path)
            if m: con.execute('delete from providers where id=?',(m.group(1),)); con.commit(); return self.send_json(200, {'ok':True})
            m=re.match(r'/api/admin/models/(\d+)$',self.path)
            if m: con.execute('delete from models where id=?',(m.group(1),)); con.commit(); return self.send_json(200, {'ok':True})
        return self.send_json(404, {'error':'not_found'})


def main():
    init_db(); print(f'AI Analysis Hub listening on http://0.0.0.0:{PORT}', flush=True); ThreadingHTTPServer(('0.0.0.0',PORT),Handler).serve_forever()
if __name__=='__main__': main()
