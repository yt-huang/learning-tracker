let token = localStorage.getItem('aiHubToken') || '';
const $ = (id) => document.getElementById(id);
async function api(path, opts={}){
  const res = await fetch(path,{...opts,headers:{'Content-Type':'application/json','Authorization':`Bearer ${token}`,...(opts.headers||{})}});
  const data = await res.json().catch(()=>({}));
  if(!res.ok) throw new Error(data.detail || data.error || res.statusText);
  return data;
}
function showApp(){ $('loginView').classList.add('hidden'); $('appView').classList.remove('hidden'); $('logoutBtn').classList.remove('hidden'); loadAll(); }
function showLogin(){ $('loginView').classList.remove('hidden'); $('appView').classList.add('hidden'); $('logoutBtn').classList.add('hidden'); }
$('loginBtn').onclick = async()=>{ try{ const d=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:$('username').value,password:$('password').value})}).then(r=>{if(!r.ok)throw new Error('登录失败');return r.json()}); token=d.token; localStorage.setItem('aiHubToken',token); showApp(); }catch(e){$('loginMsg').textContent=e.message;} };
$('logoutBtn').onclick=()=>{localStorage.removeItem('aiHubToken');token='';showLogin();};
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tab,.panel').forEach(x=>x.classList.remove('active'));b.classList.add('active');$(b.dataset.tab).classList.add('active'); if(b.dataset.tab==='logs') loadLogs();});
async function loadAll(){ await loadProviders(); await loadModels(); await loadLogs(); }
async function loadProviders(){ const d=await api('/api/admin/providers'); $('providerList').innerHTML=d.items.map(p=>`<div class="item"><div><b>${p.name}</b><br><small>${p.baseUrl}<br>Key: ${p.apiKeyMasked} · ${p.enabled?'启用':'停用'}</small></div><button class="danger" onclick="delProvider(${p.id})">删除</button></div>`).join('')||'<p class="muted">暂无 Provider</p>'; $('mProvider').innerHTML=d.items.map(p=>`<option value="${p.id}">${p.name}</option>`).join(''); }
async function loadModels(){ const d=await api('/api/admin/models'); $('modelList').innerHTML=d.items.map(m=>`<div class="item"><div><b>${m.displayName||m.modelId}</b> ${m.isDefault?'⭐默认':''}<br><small>${m.providerName} / ${m.modelId} · ${m.purpose} · ${m.enabled?'启用':'停用'}</small></div><button class="danger" onclick="delModel(${m.id})">删除</button></div>`).join('')||'<p class="muted">暂无 Model</p>'; }
async function loadLogs(){ const d=await api('/api/admin/logs'); $('logList').innerHTML=d.items.map(l=>`<div class="item"><div><b>${l.success?'✅':'❌'} ${l.clientName}</b><br><small>${l.provider}/${l.model} · ${l.latencyMs}ms · ${l.createdAt}<br>${l.error||''}</small></div></div>`).join('')||'<p class="muted">暂无日志</p>'; }
$('addProviderBtn').onclick=async()=>{await api('/api/admin/providers',{method:'POST',body:JSON.stringify({name:$('pName').value,baseUrl:$('pBase').value,apiKey:$('pKey').value,enabled:$('pEnabled').checked})}); $('pKey').value=''; await loadProviders();};
$('addModelBtn').onclick=async()=>{await api('/api/admin/models',{method:'POST',body:JSON.stringify({providerId:Number($('mProvider').value),modelId:$('mId').value,displayName:$('mName').value,purpose:$('mPurpose').value,isDefault:$('mDefault').checked,enabled:true})}); await loadModels();};
window.delProvider=async(id)=>{if(confirm('删除 Provider 及其模型？')){await api(`/api/admin/providers/${id}`,{method:'DELETE'}); await loadAll();}};
window.delModel=async(id)=>{await api(`/api/admin/models/${id}`,{method:'DELETE'}); await loadModels();};
$('refreshLogsBtn').onclick=loadLogs;
$('testBtn').onclick=async()=>{ $('testResult').textContent='测试中...'; try{ const d=await api('/api/admin/test-model',{method:'POST',body:'{}'}); $('testResult').textContent=JSON.stringify(d,null,2);}catch(e){$('testResult').textContent=e.message;} };
if(token) showApp(); else showLogin();
