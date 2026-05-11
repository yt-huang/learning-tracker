from __future__ import annotations

import base64, hashlib, html, json, os, re, secrets, sqlite3, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    import pymysql
    import pymysql.cursors
except Exception:  # pragma: no cover - local fallback when PyMySQL is not installed
    pymysql = None

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
PORT = int(os.getenv("PORT", "8020"))
DB_ENGINE = os.getenv("DB_ENGINE", "mysql").lower()
DB_PATH = os.getenv("DB_PATH", "/data/ai_hub.db")
DB_HOST = os.getenv("DB_HOST", "mysql")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "ai_hub")
DB_USER = os.getenv("DB_USER", "ai_hub")
DB_PASSWORD = os.getenv("DB_PASSWORD", "ai_hub_password")
USE_MYSQL = DB_ENGINE != "sqlite" and pymysql is not None
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
ADMIN_TOKEN = os.getenv("AI_HUB_ADMIN_TOKEN", "dev-admin-token")
INTERNAL_TOKEN = os.getenv("AI_HUB_INTERNAL_TOKEN", "dev-internal-token")
MASTER_KEY = os.getenv("AI_HUB_MASTER_KEY", "dev-master-key-change-me")
MAX_CONTENT_CHARS = 14000
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "30"))


def now(): return datetime.utcnow().isoformat()

def _sql(sql: str) -> str:
    """Use sqlite-style ? placeholders in code and translate them for MySQL."""
    return sql.replace('?', '%s') if USE_MYSQL else sql


DB_INTEGRITY_ERROR = (sqlite3.IntegrityError,) + ((pymysql.err.IntegrityError,) if pymysql else ())
DB_OPERATION_ERROR = (sqlite3.OperationalError,) + ((pymysql.err.OperationalError,) if pymysql else ())


def db():
    if USE_MYSQL:
        return pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            charset='utf8mb4',
            autocommit=False,
            cursorclass=pymysql.cursors.DictCursor,
        )
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def execute(con, sql, params=()):
    if USE_MYSQL:
        cur = con.cursor()
        cur.execute(_sql(sql), params)
        return cur
    return con.execute(_sql(sql), params)


def scalar(con, sql, params=()):
    row = execute(con, sql, params).fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]


def _executescript(con, script: str):
    if USE_MYSQL:
        for stmt in [s.strip() for s in script.split(';') if s.strip()]:
            execute(con, stmt)
    else:
        con.executescript(script)


def init_db():
    mysql_schema = '''
        CREATE TABLE IF NOT EXISTS providers(
          id INTEGER PRIMARY KEY AUTO_INCREMENT,
          name VARCHAR(191) UNIQUE NOT NULL,
          base_url TEXT NOT NULL,
          api_key_encrypted TEXT NOT NULL,
          proxy TEXT DEFAULT NULL,
          enabled TINYINT NOT NULL DEFAULT 1,
          created_at VARCHAR(64) NOT NULL,
          updated_at VARCHAR(64) NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        CREATE TABLE IF NOT EXISTS models(
          id INTEGER PRIMARY KEY AUTO_INCREMENT,
          provider_id INTEGER NOT NULL,
          model_id VARCHAR(191) NOT NULL,
          display_name TEXT DEFAULT NULL,
          purpose VARCHAR(128) DEFAULT 'learning_plan',
          temperature DOUBLE DEFAULT 0.3,
          max_tokens INTEGER DEFAULT 4096,
          is_default TINYINT DEFAULT 0,
          enabled TINYINT DEFAULT 1,
          created_at VARCHAR(64) NOT NULL,
          updated_at VARCHAR(64) NOT NULL,
          INDEX idx_models_provider_id(provider_id),
          UNIQUE KEY uq_models_provider_model(provider_id, model_id),
          CONSTRAINT fk_models_provider FOREIGN KEY(provider_id) REFERENCES providers(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        CREATE TABLE IF NOT EXISTS call_logs(
          id INTEGER PRIMARY KEY AUTO_INCREMENT,
          client_name VARCHAR(191) DEFAULT 'unknown',
          template VARCHAR(128) DEFAULT 'learning_plan',
          provider_name VARCHAR(191) DEFAULT '',
          model_id VARCHAR(191) DEFAULT '',
          success TINYINT DEFAULT 0,
          latency_ms INTEGER DEFAULT 0,
          error_message TEXT DEFAULT NULL,
          error_detail TEXT DEFAULT NULL,
          created_at VARCHAR(64) NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    '''
    sqlite_schema = '''
        CREATE TABLE IF NOT EXISTS providers(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT UNIQUE NOT NULL,
          base_url TEXT NOT NULL,
          api_key_encrypted TEXT NOT NULL,
          proxy TEXT DEFAULT '',
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
          updated_at TEXT NOT NULL,
          UNIQUE(provider_id, model_id)
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
          error_detail TEXT DEFAULT '',
          created_at TEXT NOT NULL
        );
    '''
    last_error = None
    for attempt in range(30 if USE_MYSQL else 1):
        try:
            with db() as con:
                _executescript(con, mysql_schema if USE_MYSQL else sqlite_schema)
                # Migrate older SQLite/MySQL data volumes.
                try: execute(con, 'ALTER TABLE providers ADD COLUMN proxy TEXT' if USE_MYSQL else 'ALTER TABLE providers ADD COLUMN proxy TEXT DEFAULT ""')
                except DB_OPERATION_ERROR: pass
                try: execute(con, 'ALTER TABLE call_logs ADD COLUMN error_detail TEXT' if USE_MYSQL else 'ALTER TABLE call_logs ADD COLUMN error_detail TEXT DEFAULT ""')
                except DB_OPERATION_ERROR: pass
                con.commit()
                return
        except Exception as e:
            last_error = e
            if not USE_MYSQL:
                raise
            time.sleep(1)
    raise RuntimeError(f'MySQL 初始化失败，请检查 mysql 服务是否健康: {last_error}')


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


def build_opener(proxy=''):
    """Build urllib opener with optional proxy support."""
    if proxy:
        handler = urllib.request.ProxyHandler({'http': proxy, 'https': proxy})
        return urllib.request.build_opener(handler)
    return urllib.request.build_opener()

def fetch_url(url, timeout=45, proxy=''):
    opener = build_opener(proxy)
    req=urllib.request.Request(url,headers={'User-Agent':'AIAnalysisHub/0.1','Accept':'text/html,text/markdown,text/plain,application/json,*/*;q=0.5'})
    with opener.open(req, timeout=timeout) as resp:
        ctype=resp.headers.get('content-type',''); raw=resp.read(512_000)
    enc='utf-8'; m=re.search(r'charset=([^;]+)',ctype,re.I)
    if m: enc=m.group(1).strip()
    return raw.decode(enc,errors='replace'), ctype

def fetch_provider_json(base_url, api_key, path, timeout=HTTP_TIMEOUT, proxy=''):
    opener = build_opener(proxy)
    headers = {'User-Agent':'AIAnalysisHub/0.1','Accept':'application/json'}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    req = urllib.request.Request(base_url.rstrip('/') + path, headers=headers)
    with opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


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

def collect_context(url, proxy=''):
    parsed=urllib.parse.urlparse(url)
    if parsed.netloc.lower() in {'github.com','www.github.com'}:
        parts=[p for p in parsed.path.split('/') if p]
        if len(parts)>=2:
            owner,repo=parts[0],parts[1]; meta={}; readme=''
            try:
                d,_=fetch_url(f'https://api.github.com/repos/{owner}/{repo}', proxy=proxy); meta=json.loads(d)
                r,_=fetch_url(f'https://api.github.com/repos/{owner}/{repo}/readme', proxy=proxy); readme=base64.b64decode(json.loads(r).get('content','')).decode('utf-8',errors='replace')
            except Exception: pass
            return {'kind':'github','url':url,'title':f'{owner}/{repo}','description':meta.get('description') or '', 'topics':meta.get('topics') or [], 'language':meta.get('language') or '', 'stars':meta.get('stargazers_count') or 0, 'headings':markdown_headings(readme), 'content':readme[:MAX_CONTENT_CHARS]}
    data,ctype=fetch_url(url, proxy=proxy)
    if 'html' in ctype.lower() or '<html' in data[:500].lower(): text,headings,title=html_to_text(data)
    else: text,headings,title=data,markdown_headings(data),parsed.netloc
    return {'kind':'web','url':url,'title':title or parsed.netloc,'description':'','topics':[],'language':'','stars':0,'headings':headings,'content':text[:MAX_CONTENT_CHARS]}

def extract_json(text):
    text=re.sub(r'^```(?:json)?\s*|\s*```$','',text.strip(),flags=re.I|re.S).strip()
    try: return json.loads(text)
    except json.JSONDecodeError: return json.loads(text[text.find('{'):text.rfind('}')+1])

def select_model(con):
    q='''SELECT m.*, p.name provider_name, p.base_url, p.api_key_encrypted, p.proxy FROM models m JOIN providers p ON p.id=m.provider_id WHERE m.enabled=1 AND p.enabled=1 ORDER BY m.is_default DESC, m.id DESC LIMIT 1'''
    row=execute(con, q).fetchone()
    if not row: raise RuntimeError('请先在 AI Hub 后台配置并启用 Provider 和 Model')
    return dict(row)

def call_model(m, ctx, data, proxy=''):
    key=decrypt_secret(m['api_key_encrypted'])
    prompt=f'''你是学习规划专家和产品经理。根据链接内容生成适合 Learning Tracker 的学习计划。\n只输出 JSON，不要 Markdown。字段：title, sourceUrl, description, category, difficulty, estimatedHours, analysisSummary, milestones。\nmilestones 每项字段：title, description, goal, tasks。tasks 每项字段：title, description, estimatedMinutes, acceptance。\n要求：4-6 个阶段，每阶段 3-5 个具体可执行任务，可学习日志。\n用户目标：{data.get('goal') or '未填写'}\n用户水平：{data.get('level') or '进阶'}\n每周可投入小时：{data.get('hoursPerWeek') or 5}\n链接上下文：{json.dumps(ctx, ensure_ascii=False)[:MAX_CONTENT_CHARS]}'''
    body={'model':m['model_id'],'messages':[{'role':'system','content':'You output strict JSON only.'},{'role':'user','content':prompt}], 'temperature':float(m['temperature'] or 0.3),'response_format':{'type':'json_object'}}
    opener = build_opener(proxy)
    req=urllib.request.Request(m['base_url'].rstrip('/')+'/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':f'Bearer {key}'},method='POST')
    with opener.open(req,timeout=HTTP_TIMEOUT) as resp: payload=json.loads(resp.read().decode())
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
            with db() as con: return self.send_json(200, {'ok':True,'dbEngine':'mysql' if USE_MYSQL else 'sqlite','providers':scalar(con, 'select count(*) from providers'),'models':scalar(con, 'select count(*) from models')})
        if self.path.startswith('/api/admin/'):
            if not require_admin(self): return
            with db() as con:
                if self.path=='/api/admin/providers':
                    rows=execute(con, 'select * from providers order by id desc').fetchall(); return self.send_json(200, {'items':[dict(id=r['id'],name=r['name'],baseUrl=r['base_url'],apiKeyMasked='********' if r['api_key_encrypted'] else '', proxy=r['proxy'] or '', enabled=bool(r['enabled']),createdAt=r['created_at'],updatedAt=r['updated_at']) for r in rows]})
                if self.path=='/api/admin/models':
                    rows=execute(con, 'select m.*,p.name provider_name from models m join providers p on p.id=m.provider_id order by m.is_default desc,m.id desc').fetchall(); return self.send_json(200, {'items':[dict(id=r['id'],providerId=r['provider_id'],providerName=r['provider_name'],modelId=r['model_id'],displayName=r['display_name'],purpose=r['purpose'],temperature=r['temperature'],maxTokens=r['max_tokens'],isDefault=bool(r['is_default']),enabled=bool(r['enabled'])) for r in rows]})
                if self.path=='/api/admin/logs':
                    rows=execute(con, 'select * from call_logs order by id desc limit 80').fetchall(); return self.send_json(200, {'items':[dict(id=r['id'],clientName=r['client_name'],template=r['template'],provider=r['provider_name'],model=r['model_id'],success=bool(r['success']),latencyMs=r['latency_ms'],error=r['error_message'],errorDetail=r['error_detail'] or '',createdAt=r['created_at']) for r in rows]})
        return super().do_GET()
    def do_POST(self):
        try:
            if self.path=='/api/auth/login':
                d=read_json(self); ok=secrets.compare_digest(d.get('username',''),ADMIN_USERNAME) and secrets.compare_digest(d.get('password',''),ADMIN_PASSWORD)
                return self.send_json(200 if ok else 401, {'ok':ok,'token':ADMIN_TOKEN} if ok else {'detail':'用户名或密码错误'})
            if self.path=='/api/admin/providers':
                if not require_admin(self): return
                d=read_json(self); t=now()
                name = (d.get('name') or '').strip()
                base_url = (d.get('baseUrl') or '').strip().rstrip('/')
                api_key = (d.get('apiKey') or '').strip()
                if not name: return self.send_json(400, {'error':'名称不能为空'})
                if not base_url: return self.send_json(400, {'error':'Base URL 不能为空'})
                if not api_key: return self.send_json(400, {'error':'API Key 不能为空'})
                proxy = (d.get('proxy') or '').strip()
                try:
                    with db() as con:
                        cur=execute(con, 'insert into providers(name,base_url,api_key_encrypted,proxy,enabled,created_at,updated_at) values(?,?,?,?,?,?,?)',(name,base_url,encrypt_secret(api_key),proxy,1 if d.get('enabled',True) else 0,t,t)); con.commit()
                        return self.send_json(200, {'id':cur.lastrowid,'name':name,'baseUrl':base_url,'apiKeyMasked':'********','proxy':proxy,'enabled':d.get('enabled',True),'createdAt':t,'updatedAt':t})
                except DB_INTEGRITY_ERROR:
                    return self.send_json(409, {'error':f'Provider "{name}" 已存在'})
            if self.path=='/api/admin/models':
                if not require_admin(self): return
                d=read_json(self); t=now()
                model_id = (d.get('modelId') or '').strip()
                if not model_id: return self.send_json(400, {'error':'模型 ID 不能为空'})
                if not d.get('providerId'): return self.send_json(400, {'error':'请选择 Provider'})
                try:
                    with db() as con:
                        if d.get('isDefault'): execute(con, 'update models set is_default=0')
                        cur=execute(con, 'insert into models(provider_id,model_id,display_name,purpose,temperature,max_tokens,is_default,enabled,created_at,updated_at) values(?,?,?,?,?,?,?,?,?,?)',(d['providerId'],model_id,d.get('displayName','').strip(),d.get('purpose','learning_plan'),float(d.get('temperature',0.3)),int(d.get('maxTokens',4096)),1 if d.get('isDefault') else 0,1 if d.get('enabled',True) else 0,t,t)); con.commit()
                        return self.send_json(200, {'id':cur.lastrowid})
                except DB_INTEGRITY_ERROR:
                    return self.send_json(409, {'error':'该模型已存在'})
            if self.path=='/api/admin/test-model':
                if not require_admin(self): return
                start=time.time()
                with db() as con: m=select_model(con)
                key=decrypt_secret(m['api_key_encrypted']); body={'model':m['model_id'],'messages':[{'role':'user','content':'Return exactly: pong'}],'temperature':0}
                proxy = m.get('proxy') or os.getenv('HTTP_PROXY', '') or os.getenv('HTTPS_PROXY', '')
                opener = build_opener(proxy)
                req=urllib.request.Request(m['base_url'].rstrip('/')+'/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':f'Bearer {key}'},method='POST')
                with opener.open(req,timeout=HTTP_TIMEOUT) as resp: payload=json.loads(resp.read().decode())
                return self.send_json(200, {'ok':True,'provider':m['provider_name'],'model':m['model_id'],'latencyMs':int((time.time()-start)*1000),'response':payload['choices'][0]['message']['content']})
            if self.path=='/api/admin/test-connection':
                if not require_admin(self): return
                d=read_json(self); pid=d.get('providerId')
                if not pid: return self.send_json(400, {'error':'providerId 必填'})
                start=time.time()
                with db() as con:
                    row=execute(con, 'select * from providers where id=?',(pid,)).fetchone()
                    if not row: return self.send_json(404, {'error':'Provider 未找到'})
                    m=dict(row)
                    proxy = m.get('proxy') or os.getenv('HTTP_PROXY', '') or os.getenv('HTTPS_PROXY', '')
                    try:
                        payload=fetch_provider_json(m['base_url'], decrypt_secret(m['api_key_encrypted']), '/models', timeout=HTTP_TIMEOUT, proxy=proxy)
                        models_list = payload.get('data', []) if isinstance(payload.get('data'), list) else []
                        return self.send_json(200, {'ok':True,'provider':m['name'],'latencyMs':int((time.time()-start)*1000),'modelCount':len(models_list)})
                    except urllib.error.URLError as e:
                        return self.send_json(502, {'ok':False,'error':'无法连接 API，请检查网络或配置代理','detail':str(e.reason)})
                    except Exception as e:
                        return self.send_json(502, {'ok':False,'error':f'连接测试失败: {str(e)}'})
            if self.path=='/api/admin/fetch-models':
                if not require_admin(self): return
                d=read_json(self); pid=d.get('providerId')
                if not pid: return self.send_json(400, {'error':'providerId 必填'})
                with db() as con:
                    row=execute(con, 'select * from providers where id=?',(pid,)).fetchone()
                    if not row: return self.send_json(404, {'error':'Provider 未找到'})
                    m=dict(row)
                    proxy = m.get('proxy') or os.getenv('HTTP_PROXY', '') or os.getenv('HTTPS_PROXY', '')
                    try:
                        payload=fetch_provider_json(m['base_url'], decrypt_secret(m['api_key_encrypted']), '/models', timeout=HTTP_TIMEOUT, proxy=proxy)
                        models_list = payload.get('data', [])
                        if not isinstance(models_list, list):
                            return self.send_json(500, {'error':'API 返回格式异常，未找到模型列表'})
                        result=[]
                        for mdl in models_list:
                            mid = mdl.get('id', '')
                            if mid:
                                result.append({'modelId':mid,'displayName':mdl.get('display_name') or mdl.get('id',''),'owned_by':mdl.get('owned_by','')})
                        return self.send_json(200, {'ok':True,'provider':m['name'],'providerId':m['id'],'models':result})
                    except urllib.error.HTTPError as e:
                        return self.send_json(502, {'ok':False,'error':f'API 请求失败 (HTTP {e.code})','detail':e.read().decode(errors='replace')[:500]})
                    except urllib.error.URLError as e:
                        return self.send_json(502, {'ok':False,'error':'无法连接 API，请检查网络或配置代理','detail':str(e.reason)})
                    except json.JSONDecodeError:
                        return self.send_json(502, {'ok':False,'error':'API 返回非 JSON 数据，请检查 Base URL 是否正确'})
                    except Exception as e:
                        return self.send_json(502, {'ok':False,'error':f'拉取模型列表失败: {str(e)}'})
            if self.path=='/api/admin/batch-import-models':
                if not require_admin(self): return
                d=read_json(self); pid=d.get('providerId'); models_data=d.get('models', [])
                if not pid: return self.send_json(400, {'error':'providerId 必填'})
                if not models_data: return self.send_json(400, {'error':'请选择要导入的模型'})
                t=now(); imported=[]
                with db() as con:
                    for mdl in models_data:
                        mid = (mdl.get('modelId') or '').strip()
                        if not mid: continue
                        dn = (mdl.get('displayName') or mid).strip()
                        try:
                            cur=execute(con, 'insert into models(provider_id,model_id,display_name,purpose,temperature,max_tokens,is_default,enabled,created_at,updated_at) values(?,?,?,?,?,?,?,?,?,?)',(pid,mid,dn,'learning_plan',0.3,4096,0,1,t,t))
                            imported.append({'id':cur.lastrowid,'modelId':mid,'displayName':dn})
                        except DB_INTEGRITY_ERROR:
                            pass
                    con.commit()
                return self.send_json(200, {'ok':True,'imported':imported,'count':len(imported)})
            if self.path=='/api/v1/analyze-learning-link':
                if not require_internal(self): return
                start=time.time(); data=read_json(self); model=None
                try:
                    if not re.match(r'^https?://',data.get('url','')): raise RuntimeError('请输入 http/https 学习链接')
                    with db() as con: model=select_model(con)
                    proxy = model.get('proxy') or os.getenv('HTTP_PROXY', '') or os.getenv('HTTPS_PROXY', '')
                    ctx=collect_context(data['url'], proxy=proxy); plan=call_model(model,ctx,data, proxy=proxy)
                    with db() as con: execute(con, 'insert into call_logs(client_name,template,provider_name,model_id,success,latency_ms,error_message,error_detail,created_at) values(?,?,?,?,?,?,?,?,?)',(data.get('clientName','learning-tracker'),data.get('template','learning_plan'),model['provider_name'],model['model_id'],1,int((time.time()-start)*1000),'','',now())); con.commit()
                    return self.send_json(200, {'ok':True,'plan':plan,'provider':model['provider_name'],'model':model['model_id'],'fetched':{'kind':ctx.get('kind'),'title':ctx.get('title'),'headings':ctx.get('headings',[])[:10]}})
                except Exception as e:
                    detail = f'{type(e).__name__}: {str(e)}'
                    with db() as con: execute(con, 'insert into call_logs(client_name,template,provider_name,model_id,success,latency_ms,error_message,error_detail,created_at) values(?,?,?,?,?,?,?,?,?)',(data.get('clientName','learning-tracker'),data.get('template','learning_plan'),model['provider_name'] if model else '',model['model_id'] if model else '',0,int((time.time()-start)*1000),str(e),detail[:2000],now())); con.commit()
                    return self.send_json(500, {'ok':False,'error':str(e)})
            return self.send_json(404, {'error':'not_found'})
        except urllib.error.HTTPError as e: return self.send_json(502, {'ok':False,'error':f'upstream HTTP {e.code}: {e.read().decode(errors="replace")[:500]}'})
        except Exception as e: return self.send_json(500, {'ok':False,'error':str(e)})
    def do_PUT(self):
        try:
            if not require_admin(self): return
            d=read_json(self); t=now()
            m1=re.match(r'/api/admin/providers/(\d+)$',self.path)
            if m1:
                pid=int(m1.group(1))
                name=(d.get('name') or '').strip()
                base_url=(d.get('baseUrl') or '').strip().rstrip('/')
                proxy=(d.get('proxy') or '').strip()
                enabled=1 if d.get('enabled',True) else 0
                with db() as con:
                    row=execute(con, 'select * from providers where id=?',(pid,)).fetchone()
                    if not row: return self.send_json(404, {'error':'Provider 未找到'})
                    api_key_encrypted = row['api_key_encrypted']
                    if d.get('apiKey'):
                        api_key_encrypted = encrypt_secret(d['apiKey'].strip())
                    execute(con, 'update providers set name=?,base_url=?,api_key_encrypted=?,proxy=?,enabled=?,updated_at=? where id=?',(name or row['name'],base_url or row['base_url'],api_key_encrypted,proxy,enabled,t,pid))
                    con.commit()
                    return self.send_json(200, {'ok':True,'id':pid,'name':name or row['name'],'baseUrl':base_url or row['base_url'],'apiKeyMasked':'********','proxy':proxy,'enabled':bool(enabled),'updatedAt':t})
            m2=re.match(r'/api/admin/models/(\d+)$',self.path)
            if m2:
                mid=int(m2.group(1))
                with db() as con:
                    row=execute(con, 'select * from models where id=?',(mid,)).fetchone()
                    if not row: return self.send_json(404, {'error':'Model 未找到'})
                    model_id=(d.get('modelId') or row['model_id']).strip()
                    display_name=(d.get('displayName') or row['display_name']).strip()
                    purpose=d.get('purpose') or row['purpose']
                    temperature=float(d.get('temperature', row['temperature']))
                    max_tokens=int(d.get('maxTokens', row['max_tokens']))
                    is_default=1 if d.get('isDefault', row['is_default']) else 0
                    enabled=1 if d.get('enabled', row['enabled']) else 0
                    if d.get('isDefault'): execute(con, 'update models set is_default=0')
                    execute(con, 'update models set model_id=?,display_name=?,purpose=?,temperature=?,max_tokens=?,is_default=?,enabled=?,updated_at=? where id=?',(model_id,display_name,purpose,temperature,max_tokens,is_default,enabled,t,mid))
                    con.commit()
                    return self.send_json(200, {'ok':True,'id':mid})
            return self.send_json(404, {'error':'not_found'})
        except Exception as e: return self.send_json(500, {'ok':False,'error':str(e)})
    def do_DELETE(self):
        if not require_admin(self): return
        with db() as con:
            m=re.match(r'/api/admin/providers/(\d+)$',self.path)
            if m: execute(con, 'delete from providers where id=?',(m.group(1),)); con.commit(); return self.send_json(200, {'ok':True})
            m=re.match(r'/api/admin/models/(\d+)$',self.path)
            if m: execute(con, 'delete from models where id=?',(m.group(1),)); con.commit(); return self.send_json(200, {'ok':True})
        return self.send_json(404, {'error':'not_found'})


def main():
    init_db(); print(f'AI Analysis Hub listening on http://0.0.0.0:{PORT}', flush=True); ThreadingHTTPServer(('0.0.0.0',PORT),Handler).serve_forever()
if __name__=='__main__': main()
