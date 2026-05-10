let token = localStorage.getItem('aiHubToken') || '';
const $ = (id) => document.getElementById(id);
function toast(msg, type='error') {
  const c = $('toast-container') || (()=>{const d=document.createElement('div');d.id='toast-container';document.body.appendChild(d);return d})();
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.innerHTML = `<span class="toast-dismiss" onclick="this.parentElement.remove()">✕</span>${msg}`;
  c.appendChild(el);
  setTimeout(()=>{el.style.opacity='0';el.style.transition='opacity .3s';setTimeout(()=>el.remove(),300)}, type==='error'?6000:4000);
}
async function api(path, opts={}){
  const res = await fetch(path,{...opts,headers:{'Content-Type':'application/json','Authorization':`Bearer ${token}`,...(opts.headers||{})}});
  let data;
  try{data=await res.json()}catch(e){data={}}
  if(!res.ok) throw new Error(data.error || data.detail || res.statusText);
  return data;
}
function showApp(){ $('loginView').classList.add('hidden'); $('appView').classList.remove('hidden'); $('logoutBtn').classList.remove('hidden'); loadAll(); }
function showLogin(){ $('loginView').classList.remove('hidden'); $('appView').classList.add('hidden'); $('logoutBtn').classList.add('hidden'); }
$('loginBtn').onclick = async()=>{ try{ const d=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:$('username').value,password:$('password').value})}).then(r=>{if(!r.ok)throw new Error('登录失败');return r.json()}); token=d.token; localStorage.setItem('aiHubToken',token); showApp(); }catch(e){$('loginMsg').textContent=e.message;} };
$('logoutBtn').onclick=()=>{localStorage.removeItem('aiHubToken');token='';showLogin();};
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tab,.panel').forEach(x=>x.classList.remove('active'));b.classList.add('active');$(b.dataset.tab).classList.add('active'); if(b.dataset.tab==='logs') loadLogs();});
async function loadAll(){ await loadProviders(); await loadModels(); await loadLogs(); }

// Provider editing state
let editingProviderId = null;
let editingModelId = null;
let fetchModelsResult = [];

function closeModal(id){ $(id).classList.add('hidden'); }

async function loadProviders(){
  const d=await api('/api/admin/providers');
  $('providerList').innerHTML=d.items.map(p=>{
    const hasActions = `<div class="actions">
      <button class="btn-sm btn-outline" onclick="testConnection(${p.id})">测试连接</button>
      <button class="btn-sm btn-outline" onclick="editProvider(${p.id})">编辑</button>
      <button class="btn-sm danger" onclick="delProvider(${p.id})">删除</button>
    </div>`;
    return `<div class="item wrap"><div class="item-body"><b>${p.name}</b><br><small>${p.baseUrl}<br>Key: ${p.apiKeyMasked} · ${p.enabled?'启用':'停用'}${p.proxy?' · 代理: '+p.proxy:''}</small></div>${hasActions}</div>`;
  }).join('')||'<p class="muted">暂无 Provider</p>';
  $('mProvider').innerHTML=d.items.map(p=>`<option value="${p.id}">${p.name}</option>`).join('');
  $('mProviderFetch').innerHTML=d.items.map(p=>`<option value="${p.id}">${p.name}</option>`).join('');
}

async function loadModels(){
  const d=await api('/api/admin/models');
  $('modelList').innerHTML=d.items.map(m=>{
    const hasActions = `<div class="actions">
      <button class="btn-sm btn-outline" onclick="editModel(${m.id})">编辑</button>
      <button class="btn-sm danger" onclick="delModel(${m.id})">删除</button>
    </div>`;
    return `<div class="item wrap"><div class="item-body"><b>${m.displayName||m.modelId}</b> ${m.isDefault?'⭐默认':''}<br><small>${m.providerName} / ${m.modelId} · ${m.purpose} · ${m.enabled?'启用':'停用'}</small></div>${hasActions}</div>`;
  }).join('')||'<p class="muted">暂无 Model</p>';
}

async function loadLogs(){
  const d=await api('/api/admin/logs');
  $('logList').innerHTML=d.items.map(l=>{
    const errHtml = l.error ? `<br><span style="color:var(--danger)">${l.error}</span>` : '';
    const detailHtml = l.errorDetail ? `<br><small style="color:var(--muted);font-size:11px">${l.errorDetail}</small>` : '';
    return `<div class="item"><div><b>${l.success?'✅':'❌'} ${l.clientName}</b><br><small>${l.provider}/${l.model} · ${l.latencyMs}ms · ${l.createdAt}${errHtml}${detailHtml}</small></div></div>`;
  }).join('')||'<p class="muted">暂无日志</p>';
}

// ---- Provider CRUD ----
$('addProviderBtn').onclick=async()=>{
  if(editingProviderId) return saveProviderEdit();
  try{
    await api('/api/admin/providers',{method:'POST',body:JSON.stringify({
      name:$('pName').value,baseUrl:$('pBase').value,apiKey:$('pKey').value,
      proxy:$('pProxy').value,enabled:$('pEnabled').checked
    })});
    $('pKey').value=''; $('pProxy').value='';
    await loadProviders();
    toast('Provider 已添加','success');
  }catch(e){toast(e.message);}
};

function editProvider(id){
  editingProviderId = id;
  $('addProviderBtn').textContent = '保存修改';
  $('formProviderTitle').textContent = '编辑 Provider';
  $('pCancelEdit').classList.remove('hidden');
  loadProviderForEdit(id);
}

async function loadProviderForEdit(id){
  try{
    const d=await api('/api/admin/providers');
    const p = d.items.find(x=>x.id===id);
    if(!p) return toast('Provider 未找到');
    $('pName').value=p.name;
    $('pBase').value=p.baseUrl;
    $('pKey').value='';
    $('pKey').placeholder='留空不修改密钥';
    $('pProxy').value=p.proxy||'';
    $('pEnabled').checked=p.enabled;
  }catch(e){toast(e.message);}
}

async function saveProviderEdit(){
  try{
    const body={name:$('pName').value,baseUrl:$('pBase').value,proxy:$('pProxy').value,enabled:$('pEnabled').checked};
    if($('pKey').value) body.apiKey=$('pKey').value;
    await api(`/api/admin/providers/${editingProviderId}`,{method:'PUT',body:JSON.stringify(body)});
    cancelProviderEdit();
    await loadProviders();
    toast('Provider 已更新','success');
  }catch(e){toast(e.message);}
}

function cancelProviderEdit(){
  editingProviderId=null;
  $('addProviderBtn').textContent='保存 Provider';
  $('formProviderTitle').textContent='添加 Provider';
  $('pCancelEdit').classList.add('hidden');
  $('pKey').value='';
  $('pKey').placeholder='API Key';
  $('pName').value='';$('pBase').value='';$('pProxy').value='';$('pEnabled').checked=true;
}

window.delProvider=async(id)=>{
  if(confirm('删除 Provider 及其模型？')){
    try{await api(`/api/admin/providers/${id}`,{method:'DELETE'});await loadAll();toast('Provider 已删除','info');}catch(e){toast(e.message);}
  }
};

// ---- Test Connection ----
window.testConnection=async(id)=>{
  const btn = event.target;
  btn.disabled=true; btn.textContent='测试中...';
  try{
    const d=await api('/api/admin/test-connection',{method:'POST',body:JSON.stringify({providerId:id})});
    if(d.ok) toast(`连接成功！延迟 ${d.latencyMs}ms，可用模型 ${d.modelCount||'?'} 个`,'success');
    else toast(d.error||'连接失败','error');
  }catch(e){toast(e.message);}
  btn.disabled=false; btn.textContent='测试连接';
};

// ---- Fetch Models ----
$('fetchModelsBtn').onclick=async()=>{
  const pid = Number($('mProviderFetch').value);
  if(!pid) return toast('请先选择 Provider','error');
  $('fetchModelsBtn').disabled=true; $('fetchModelsBtn').textContent='拉取中...';
  $('fetchResult').innerHTML='<p class="muted">正在拉取模型列表...</p>';
  $('fetchResultPanel').classList.remove('hidden');
  try{
    const d=await api('/api/admin/fetch-models',{method:'POST',body:JSON.stringify({providerId:pid})});
    if(!d.ok) { toast(d.error||'拉取失败','error'); $('fetchResult').innerHTML=''; return; }
    if(!d.models||!d.models.length){
      $('fetchResult').innerHTML='<p class="muted">API 返回的模型列表为空</p>';
      return;
    }
    fetchModelsResult = d.models.map(m=>({...m,selected:false}));
    renderFetchResults();
    toast(`拉取到 ${d.models.length} 个模型`,'success');
  }catch(e){$('fetchResult').innerHTML=`<p style="color:var(--danger)">${e.message}</p>`;toast(e.message);}
  $('fetchModelsBtn').disabled=false; $('fetchModelsBtn').textContent='从 API 拉取模型';
};

function renderFetchResults(){
  const items = fetchModelsResult;
  if(!items.length){ $('fetchResult').innerHTML='<p class="muted">无模型数据</p>'; return; }
  const allChecked = items.every(m=>m.selected);
  $('fetchResult').innerHTML=`
    <div class="flex items-center gap-8 mb-8">
      <label><input type="checkbox" id="selectAllFetch" ${allChecked?'checked':''} onchange="toggleAllFetch()" /> 全选</label>
      <button class="btn-sm success" id="batchImportBtn" onclick="batchImportModels()">批量添加选中 (${items.filter(m=>m.selected).length})</button>
    </div>
    <div class="overflow-auto">
    <table class="model-table">
      <thead><tr><th style="width:40px"></th><th>模型 ID</th><th>显示名称</th><th>所属</th></tr></thead>
      <tbody>${items.map((m,i)=>`<tr>
        <td><input type="checkbox" ${m.selected?'checked':''} onchange="toggleFetchModel(${i},this.checked)" /></td>
        <td><code>${m.modelId}</code></td>
        <td>${m.displayName}</td>
        <td>${m.owned_by||'-'}</td>
      </tr>`).join('')}</tbody>
    </table>
    </div>
  `;
}

window.toggleAllFetch=function(){
  const checked = document.getElementById('selectAllFetch').checked;
  fetchModelsResult.forEach(m=>m.selected=checked);
  renderFetchResults();
};
window.toggleFetchModel=function(idx,checked){
  fetchModelsResult[idx].selected=checked;
  const selected = fetchModelsResult.filter(m=>m.selected).length;
  const btn=document.getElementById('batchImportBtn');
  if(btn) btn.textContent=`批量添加选中 (${selected})`;
};
window.batchImportModels=async function(){
  const selected = fetchModelsResult.filter(m=>m.selected);
  if(!selected.length) return toast('请先勾选要导入的模型','error');
  const pid = Number($('mProviderFetch').value);
  try{
    const d=await api('/api/admin/batch-import-models',{method:'POST',body:JSON.stringify({providerId:pid,models:selected})});
    toast(`成功导入 ${d.count} 个模型`,'success');
    fetchModelsResult.forEach(m=>m.selected=false);
    renderFetchResults();
    $('fetchResultPanel').classList.add('hidden');
    await loadModels();
  }catch(e){toast(e.message);}
};

// ---- Model CRUD ----
$('addModelBtn').onclick=async()=>{
  if(editingModelId) return saveModelEdit();
  try{
    await api('/api/admin/models',{method:'POST',body:JSON.stringify({
      providerId:Number($('mProvider').value),modelId:$('mId').value,
      displayName:$('mName').value,purpose:$('mPurpose').value,
      isDefault:$('mDefault').checked,enabled:true
    })});
    await loadModels();
    toast('Model 已添加','success');
  }catch(e){toast(e.message);}
};

function editModel(id){
  editingModelId = id;
  $('addModelBtn').textContent = '保存修改';
  $('formModelTitle').textContent = '编辑 Model';
  $('mCancelEdit').classList.remove('hidden');
  loadModelForEdit(id);
}

async function loadModelForEdit(id){
  try{
    const d=await api('/api/admin/models');
    const m = d.items.find(x=>x.id===id);
    if(!m) return toast('Model 未找到');
    $('mProvider').value=m.providerId;
    $('mId').value=m.modelId;
    $('mName').value=m.displayName||'';
    $('mPurpose').value=m.purpose||'learning_plan';
    $('mDefault').checked=m.isDefault;
  }catch(e){toast(e.message);}
}

async function saveModelEdit(){
  try{
    const body={
      providerId:Number($('mProvider').value),
      modelId:$('mId').value,
      displayName:$('mName').value,
      purpose:$('mPurpose').value,
      isDefault:$('mDefault').checked,
      enabled:true
    };
    await api(`/api/admin/models/${editingModelId}`,{method:'PUT',body:JSON.stringify(body)});
    cancelModelEdit();
    await loadModels();
    toast('Model 已更新','success');
  }catch(e){toast(e.message);}
}

function cancelModelEdit(){
  editingModelId=null;
  $('addModelBtn').textContent='保存 Model';
  $('formModelTitle').textContent='添加 Model';
  $('mCancelEdit').classList.add('hidden');
  $('mId').value='';$('mName').value='';$('mPurpose').value='learning_plan';$('mDefault').checked=false;
}

window.delModel=async(id)=>{
  try{await api(`/api/admin/models/${id}`,{method:'DELETE'});await loadModels();toast('Model 已删除','info');}catch(e){toast(e.message);}
};

$('refreshLogsBtn').onclick=loadLogs;
$('testBtn').onclick=async()=>{ $('testResult').textContent='测试中...'; try{ const d=await api('/api/admin/test-model',{method:'POST',body:'{}'}); $('testResult').textContent=JSON.stringify(d,null,2);}catch(e){$('testResult').textContent=e.message;} };
$('pCancelEdit').onclick=cancelProviderEdit;
$('mCancelEdit').onclick=cancelModelEdit;

if(token) showApp(); else showLogin();