import { Auth } from './auth.js';
import { LearningDB } from './db.js';
import { generateLearningPlan, inferTitleFromUrl, templates } from './planner.js';

const db = new LearningDB();
let currentView = 'dashboard';
let currentPlanId = null;
let planCache = {}; // plan_id -> {plan, milestones, logs}

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
function toast(msg) { const t = $('#toast'); t.textContent = msg; t.classList.remove('hidden'); setTimeout(() => t.classList.add('hidden'), 2200); }
function showLoading(msg = '加载中...') { $('#loading-text').textContent = msg; $('#loading').classList.remove('hidden'); }
function hideLoading() { $('#loading').classList.add('hidden'); }
function minutes(m) { const h = Math.floor((m || 0) / 60); const min = (m || 0) % 60; return h ? `${h}h ${min}m` : `${min}m`; }
function statusText(s) { return ({not_started:'未开始', in_progress:'进行中', paused:'暂停', completed:'已完成', todo:'待办', doing:'进行中', done:'已完成'})[s] || s; }
function pctClass(v) { const n = Number(v || 0); return n >= 70 ? 'pct-high' : n >= 30 ? 'pct-mid' : 'pct-low'; }
function progBarClass(v) { const n = Number(v || 0); return n >= 70 ? 'progress-high' : n >= 30 ? 'progress-mid' : 'progress-low'; }

async function boot() {
  bindAuth();
  if (Auth.isLoggedIn()) {
    const user = await Auth.refreshUser();
    if (user) return await showApp();
  }
  showLogin();
}

function bindAuth() {
  $('#login-form').addEventListener('submit', async (e) => {
    e.preventDefault(); $('#login-error').textContent = '';
    const uname = $('#username').value.trim();
    const pwd = $('#password').value;
    if (!uname || !pwd) { $('#login-error').textContent = '请输入用户名和密码'; return; }
    showLoading('登录中...');
    const result = await Auth.login(uname, pwd);
    hideLoading();
    if (result.ok) await showApp();
    else if (result.error.includes('激活')) {
      $('#login-error').textContent = '账号未激活，请联系管理员';
      $('#session-warning').textContent = '需要管理员在「用户管理」中激活你的账号才能登录。';
      $('#session-warning').classList.remove('hidden');
    } else {
      $('#login-error').textContent = result.error;
    }
  });
  $('#username').oninput = () => $('#login-error').textContent = '';
  $('#password').oninput = () => $('#login-error').textContent = '';

  $('#register-form').addEventListener('submit', async (e) => {
    e.preventDefault(); $('#register-error').textContent = '';
    const uname = $('#reg-username').value.trim();
    const pwd = $('#reg-password').value;
    if (uname.length < 2 || pwd.length < 4) { $('#register-error').textContent = '用户名至少2字符，密码至少4字符'; return; }
    showLoading('注册中...');
    const result = await Auth.register(uname, pwd, $('#reg-email').value.trim());
    hideLoading();
    if (result.ok) {
      if (result.user?.active) { toast('注册成功，已自动登录'); await showApp(); }
      else { toast('注册成功！等待管理员激活'); $('#show-login').click(); }
    } else {
      $('#register-error').textContent = result.error;
    }
  });

  $('#show-register').onclick = (e) => { e.preventDefault(); showRegisterCard(); };
  $('#show-login').onclick = (e) => { e.preventDefault(); showLoginCard(); };
  $('#logout-btn').addEventListener('click', async () => { await Auth.logout(); showLogin(); });
}

function showRegisterCard() { $('#login-card').classList.add('hidden'); $('#register-card').classList.remove('hidden'); $('#login-error').textContent = ''; $('#register-error').textContent = ''; $('#session-warning').classList.add('hidden'); }
function showLoginCard() { $('#register-card').classList.add('hidden'); $('#login-card').classList.remove('hidden'); $('#login-error').textContent = ''; $('#register-error').textContent = ''; }

async function showApp() {
  $('#login-screen').classList.add('hidden'); $('#app').classList.remove('hidden');
  await db.init();
  const user = Auth.getUser();
  $$('.admin-only').forEach(el => el.classList.toggle('hidden', !Auth.isAdmin()));
  $('#user-badge').innerHTML = user ? `<span style="font-size:13px;color:var(--muted)">${user.username}${user.role === 'admin' ? ' 🔑' : ''}</span>` : '';
  try {
    const s = JSON.parse(localStorage.getItem('learning_tracker_session') || 'null');
    if (s && s.expiresAt) { const d = (s.expiresAt - Date.now()) / 86400000; if (d < 0) toast('会话已过期'); else if (d < 1) toast(`会话将在${Math.round(d*24)}小时后过期`); }
  } catch (e) {}
  bindApp();
  await render();
}

function showLogin() { $('#app').classList.add('hidden'); $('#login-screen').classList.remove('hidden'); showLoginCard(); $('#password').value = ''; $('#reg-password').value = ''; }

function bindApp() {
  $$('.nav-btn').forEach(btn => btn.onclick = () => switchView(btn.dataset.view));
  $('#new-plan-btn').onclick = () => $('#plan-dialog').showModal();
  $('#cancel-plan').onclick = () => $('#plan-dialog').close();
  $('#cancel-log').onclick = () => $('#log-dialog').close();
  $('#source-url').addEventListener('input', () => { if (!$('#plan-title').value) $('#plan-title').placeholder = inferTitleFromUrl($('#source-url').value); });
  $('#ai-analyze-plan').onclick = analyzeLinkWithAI;
  $('#back-to-top').onclick = () => document.getElementById('plan-detail-view')?.scrollIntoView({behavior:'smooth'});

  $('#plan-form').onsubmit = async (e) => {
    e.preventDefault(); showLoading('正在生成计划...');
    const plan = generateLearningPlan({ url: $('#source-url').value, title: $('#plan-title').value, category: $('#plan-category').value, goal: $('#plan-goal').value, difficulty: $('#plan-difficulty').value, hours: $('#plan-hours').value });
    const id = await db.createPlan(plan);
    resetPlanDialog(e.target); hideLoading();
    if (id) { currentPlanId = id; toast('计划已保存到 MySQL'); await switchView('detail'); }
    else toast('保存失败');
  };

  $('#edit-plan-form').onsubmit = async (e) => {
    e.preventDefault();
    const ok = await db.updatePlan($('#edit-plan-id').value, {
      title: $('#edit-plan-title').value.trim(), description: $('#edit-plan-desc').value.trim(),
      category: $('#edit-plan-category').value.trim(), sourceUrl: $('#edit-plan-url').value.trim(),
      estimatedHours: Number($('#edit-plan-hours').value),
    });
    $('#edit-plan-dialog').close();
    if (ok) { toast('计划已更新'); await render(); }
    else toast('更新失败');
  };

  $('#cancel-edit-plan').onclick = () => $('#edit-plan-dialog').close();
  $('#confirm-cancel').onclick = () => $('#confirm-dialog').close();
  $('#cancel-edit-task').onclick = () => $('#edit-task-dialog').close();
  $('#cancel-edit-user').onclick = () => $('#edit-user-dialog').close();

  $('#edit-task-form').onsubmit = async (e) => {
    e.preventDefault();
    const tid = $('#edit-task-id').value;
    const ok = await db.updateTask(tid, { title: $('#edit-task-title').value.trim(), description: $('#edit-task-desc').value.trim(), estimated_minutes: Number($('#edit-task-estimated').value), priority: $('#edit-task-priority').value, plan_id: $('#edit-task-plan-id').value });
    $('#edit-task-dialog').close();
    if (ok) { toast('任务已更新'); await render(); }
    else toast('更新失败');
  };

  $('#log-form').onsubmit = async (e) => {
    e.preventDefault();
    await db.createLog({ planId: $('#log-plan-id').value, taskId: $('#log-task-id').value, summary: $('#log-summary').value, durationMinutes: $('#log-duration').value, notes: $('#log-notes').value });
    e.target.reset(); $('#log-dialog').close(); toast('学习日志已保存到 MySQL'); await render();
  };

  $('#edit-user-form').onsubmit = async (e) => {
    e.preventDefault();
    const uid = $('#edit-user-id').value;
    const body = { username: $('#edit-user-username').value.trim(), email: $('#edit-user-email').value.trim(), role: $('#edit-user-role').value };
    const pw = $('#edit-user-password').value;
    if (pw) body.password = pw;
    showLoading('保存中...');
    const res = await Auth.updateUser(uid, body);
    hideLoading(); $('#edit-user-dialog').close();
    toast(res.ok ? '用户已更新' : (res.error || '更新失败'));
    if (res.ok) await render();
  };
}

function resetPlanDialog(form) {
  form.reset(); $('#ai-analysis-preview').classList.add('hidden'); $('#ai-analysis-preview').innerHTML = '';
  $('#ai-analyze-plan').disabled = false; $('#ai-analyze-plan').textContent = 'AI 深度分析'; $('#plan-dialog').close();
}

async function analyzeLinkWithAI() {
  const url = $('#source-url').value.trim();
  if (!url) return toast('请先输入学习链接');
  const preview = $('#ai-analysis-preview');
  const btn = $('#ai-analyze-plan');
  btn.disabled = true; btn.textContent = 'AI 分析中...';
  preview.classList.remove('hidden');
  preview.innerHTML = '<b>正在读取链接并生成阶段目标...</b>';
  try {
    showLoading('AI 分析中...');
    const res = await fetch('/api/analyze-link', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, goal: $('#plan-goal').value, level: $('#plan-difficulty').value, hoursPerWeek: Math.max(1, Math.round(Number($('#plan-hours').value || 12) / 3)) }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || 'AI 分析失败');
    const plan = data.plan;
    preview.innerHTML = `<b>${plan.aiUsed ? 'AI 已生成计划' : '已生成增强计划'}</b><p>${plan.analysisSummary || plan.description || ''}</p><ul><li>标题：${plan.title}</li><li>阶段：${plan.milestones?.length || 0} 个</li><li>预计：${plan.estimatedHours || 0} 小时</li></ul><button type="button" class="primary" id="save-ai-plan">保存到 MySQL</button>`;
    $('#save-ai-plan').onclick = async () => {
      const id = await db.createPlan(plan);
      resetPlanDialog($('#plan-form'));
      if (id) { currentPlanId = id; toast('AI 计划已保存到 MySQL'); await switchView('detail'); }
      else toast('保存失败');
    };
  } catch (err) {
    preview.innerHTML = `<b>AI 分析失败</b><p>${err.message}</p>`;
  } finally {
    hideLoading(); btn.disabled = false; btn.textContent = 'AI 深度分析';
  }
}

async function switchView(view) {
  currentView = view === 'detail' ? 'detail' : view;
  $$('.nav-btn').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  await render();
}

function showOnly(id) { $$('.view').forEach(v => v.classList.add('hidden')); $(id).classList.remove('hidden'); }

async function render() {
  $('#back-to-top').classList.add('hidden');
  if (currentView === 'dashboard') return await renderDashboard();
  if (currentView === 'plans') return await renderPlans();
  if (currentView === 'detail') return await renderPlanDetail();
  if (currentView === 'logs') return await renderLogs();
  if (currentView === 'users') return renderUsers();
  if (currentView === 'data') return renderData();
}

async function renderDashboard() {
  showOnly('#dashboard-view'); $('#view-title').textContent = '仪表盘'; $('#view-subtitle').textContent = 'MySQL 服务端存储 · 数据安全不丢失';
  showLoading('加载数据...');
  const [stats, plans, logs] = await Promise.all([db.getStats(), db.getPlans(), db.getLogs()]);
  hideLoading();
  const emptyPlans = plans.length === 0 ? '<div class="empty-state"><p>还没有学习计划</p><button class="hollow" id="empty-new-plan">+ 从链接生成计划</button></div>' : '';
  $('#dashboard-view').innerHTML = `
    <div class="stats-grid">
      <div class="stat"><b>${stats.total || 0}</b><span>学习计划</span></div>
      <div class="stat"><b>${stats.completed || 0}</b><span>已完成</span></div>
      <div class="stat"><b>${Math.round(Number(stats.avg_progress) || 0)}%</b><span>平均进度</span></div>
      <div class="stat"><b>${minutes(stats.total_minutes || 0)}</b><span>总学习时长</span></div>
    </div>
    <div class="grid-2 layout-gap">
      <section class="panel"><h3>进行中的计划</h3>${emptyPlans || plans.slice(0,4).map(planCard).join('') || '<p class="muted">暂无计划</p>'}</section>
      <section class="panel"><h3>最近学习日志</h3>${(logs || []).slice(0,6).map(logItem).join('') || '<p class="muted">暂无日志</p>'}</section>
    </div>`;
  bindPlanCards();
  $('#empty-new-plan')?.addEventListener('click', () => $('#plan-dialog').showModal());
}

function planCard(p) {
  const pct = Number(p.progress || 0);
  return `<article class="plan-card" data-plan="${p.id}"><div><h3>${p.title}</h3><p>${p.description || ''}</p><small>${p.category || '未分类'} · ${statusText(p.status)} · ${p.task_count || 0} 任务</small><div class="plan-actions"><button class="ghost-sm" data-edit-plan="${p.id}">编辑</button><button class="ghost-sm" data-duplicate-plan="${p.id}">复制</button><button class="ghost-sm danger" data-delete-plan="${p.id}">删除</button></div></div><div class="progress ${progBarClass(pct)}"><span style="width:${pct}%"></span></div><b class="${pctClass(pct)}">${pct}%</b></article>`;
}
function logItem(l) { return `<div class="log-item" data-log-nav="${l.id}" data-log-plan="${l.plan_id}" style="cursor:pointer"><b>${l.summary}</b><span>${l.plan_title || ''}${l.task_title ? ' · ' + l.task_title : ''}</span><small>${l.date} · ${minutes(l.duration_minutes)}</small></div>`; }
function bindPlanCards() {
  $$('[data-plan]').forEach(el => el.onclick = async (e) => {
    if (e.target.closest('[data-edit-plan],[data-duplicate-plan],[data-delete-plan]')) return;
    currentPlanId = el.dataset.plan; currentView = 'detail'; await render();
  });
  $$('[data-edit-plan]').forEach(b => b.onclick = async (e) => { e.stopPropagation(); editPlanDialog(b.dataset.editPlan); });
  $$('[data-duplicate-plan]').forEach(b => b.onclick = async (e) => {
    e.stopPropagation();
    const nid = await db.duplicatePlan(b.dataset.duplicatePlan);
    toast(nid ? '计划已复制' : '复制失败');
    if (nid) await render();
  });
  $$('[data-delete-plan]').forEach(b => b.onclick = async (e) => {
    e.stopPropagation();
    const pid = b.dataset.deletePlan;
    $('#confirm-msg').textContent = '确认删除此计划？不可恢复。';
    $('#confirm-action').onclick = async () => {
      await db.deletePlan(pid);
      if (currentPlanId === pid) { currentPlanId = null; currentView = 'plans'; }
      $('#confirm-dialog').close(); toast('计划已删除'); await render();
    };
    $('#confirm-dialog').showModal();
  });
}

function editPlanDialog(planId) {
  const p = planCache[planId]?.plan;
  if (!p) return;
  $('#edit-plan-id').value = planId;
  $('#edit-plan-title').value = p.title;
  $('#edit-plan-desc').value = p.description || '';
  $('#edit-plan-category').value = p.category || '';
  $('#edit-plan-url').value = p.source_url || '';
  $('#edit-plan-hours').value = p.estimated_hours || 0;
  $('#edit-plan-dialog').showModal();
}

async function renderPlans() {
  showOnly('#plans-view'); $('#view-title').textContent = '学习计划'; $('#view-subtitle').textContent = '搜索、筛选、进入详情跟踪任务';
  showLoading('加载计划...');
  const plans = await db.getPlans();
  hideLoading();
  $('#plans-view').innerHTML = `<div class="toolbar"><input id="search" placeholder="搜索标题/分类/链接" /><select id="status-filter"><option value="">全部状态</option><option value="not_started">未开始</option><option value="in_progress">进行中</option><option value="completed">已完成</option></select></div><div id="plans-list" class="plans-list"></div>`;
  const draw = () => {
    const q = $('#search').value.toLowerCase(), s = $('#status-filter').value;
    $('#plans-list').innerHTML = plans.filter(p => (!s || p.status === s) && JSON.stringify(p).toLowerCase().includes(q)).map(planCard).join('') || '<p class="muted">没有匹配计划</p>';
    bindPlanCards();
  };
  $('#search').oninput = draw; $('#status-filter').onchange = draw; draw();
}

async function renderPlanDetail() {
  if (!currentPlanId) { currentView = 'plans'; return await renderPlans(); }
  showLoading('加载计划详情...');
  const planData = await db.getPlan(currentPlanId);
  hideLoading();
  if (!planData) { currentPlanId = null; currentView = 'plans'; return await renderPlans(); }
  planCache[currentPlanId] = planData;

  showOnly('#plan-detail-view'); $('#view-title').textContent = planData.title; $('#view-subtitle').textContent = planData.source_url || '计划详情';
  $('#back-to-top').classList.remove('hidden');

  const milestones = planData.milestones || [];
  const logs = planData.logs || [];
  // Group logs by task
  const logsByTask = {};
  logs.forEach(l => { if (l.task_id) { if (!logsByTask[l.task_id]) logsByTask[l.task_id] = []; logsByTask[l.task_id].push(l); } });
  // All plan logs (not tied to a task)
  const planLogs = logs.filter(l => !l.task_id);
  const tmplKeys = Object.keys(templates);

  $('#plan-detail-view').innerHTML = `
    <button class="ghost" id="back-plans">← 返回计划</button>
    <section class="panel hero"><div><h2>${planData.title}</h2><p>${planData.description || ''}</p><a href="${planData.source_url}" target="_blank">${planData.source_url || ''}</a></div><div class="big-progress"><b>${planData.progress}%</b><span>完成进度</span></div></section>
    <div class="milestone-toolbar"><select id="template-select"><option value="">套用模板</option>${tmplKeys.map(k => `<option value="${k}">${k}</option>`).join('')}</select><button class="ghost" id="add-milestone-btn">+ 添加阶段</button></div>
    <div class="milestones">${milestones.map(m => milestoneCard(m, logsByTask)).join('')}</div>
    <section class="panel"><h3>本计划日志 <button class="ghost-sm" id="add-plan-log-btn" style="margin-left:8px">+ 添加日志</button></h3>${planLogs.concat(logs.filter(l => l.task_id)).slice(0,20).map(logItem).join('') || '<p class="muted">暂无日志</p>'}</section>`;

  $('#back-plans').onclick = () => switchView('plans');
  $('#back-to-top').onclick = () => document.getElementById('plan-detail-view')?.scrollIntoView({behavior:'smooth'});
  bindPlanDetailMilestones(planData.id, milestones);
  bindTaskButtons();
}

function milestoneCard(m, logsByTask) {
  const tasks = m.tasks || [];
  return `<section class="panel" data-milestone="${m.id}">
    <div class="milestone-header">
      <span class="milestone-title" data-milestone-edit="${m.id}">${m.title}</span>
      <div class="milestone-actions">
        <button class="ghost-sm" data-milestone-up="${m.id}" title="上移">↑</button>
        <button class="ghost-sm" data-milestone-down="${m.id}" title="下移">↓</button>
        <button class="ghost-sm danger" data-milestone-del="${m.id}" title="删除">✕</button>
      </div>
    </div>
    <p class="muted">${m.description || ''}</p>${tasks.map(t => taskCard(t, logsByTask[t.id] || [])).join('')}</section>`;
}

function taskCard(t, taskLogs = []) {
  const pct = Number(t.progress || 0);
  const safeId = (t.id || '').replace(/[^a-zA-Z0-9]/g,'_');
  const pCls = pctClass(pct);
  const bCls = progBarClass(pct);
  return `<div class="task" id="task-${safeId}"><div><b>${t.title}</b><p>${t.description || ''}</p><small>${statusText(t.status)} · 预计 ${minutes(t.estimated_minutes)} · 已学 ${minutes(t.spent_minutes)}</small><div class="progress ${bCls}"><span style="width:${pct}%"></span></div></div><div class="task-actions"><button data-task-log="${t.id}">记日志</button><label class="slider-label"><input type="range" min="0" max="100" value="${pct}" class="progress-slider" data-task-progress="${t.id}" /><span class="slider-val ${pCls}" id="slider-val-${safeId}">${pct}%</span></label><div><button class="ghost-sm task-edit-btn" data-task-edit="${t.id}" title="编辑任务">✎</button><button class="ghost-sm" data-task-logs-toggle="${t.id}" title="查看日志">📝 ${taskLogs.length}</button></div></div><div class="task-logs hidden" id="task-logs-${safeId}">${taskLogs.map(l => `<div class="task-log-entry" data-log-nav="${l.id}" data-log-plan="${l.plan_id}"><span>${l.summary}</span><small>${l.date} · ${minutes(l.duration_minutes)}</small></div>`).join('') || '<small class="muted">暂无日志</small>'}</div></div>`;
}

function bindTaskButtons() {
  $$('[data-task-log]').forEach(b => b.onclick = () => { $('#log-plan-id').value = currentPlanId; $('#log-task-id').value = b.dataset.taskLog; $('#log-dialog').showModal(); });
  $$('.progress-slider').forEach(slider => {
    slider.oninput = async () => {
      const val = Number(slider.value);
      const status = val >= 100 ? 'done' : val > 0 ? 'doing' : 'todo';
      await db.updateTask(slider.dataset.taskProgress, { progress: val, status, plan_id: currentPlanId });
      const safeId = slider.dataset.taskProgress.replace(/[^a-zA-Z0-9]/g,'_');
      const valSpan = document.getElementById('slider-val-' + safeId);
      if (valSpan) { valSpan.textContent = val + '%'; valSpan.className = 'slider-val ' + pctClass(val); }
      const taskEl = slider.closest('.task');
      if (taskEl) {
        const bar = taskEl.querySelector('.progress');
        if (bar) { bar.className = 'progress ' + progBarClass(val); const span = bar.querySelector('span'); if (span) span.style.width = val + '%'; }
      }
    };
  });
  $$('[data-task-logs-toggle]').forEach(b => b.onclick = () => { const el = document.getElementById('task-logs-' + b.dataset.taskLogsToggle.replace(/[^a-zA-Z0-9]/g,'_')); if (el) el.classList.toggle('hidden'); });
  $$('[data-log-nav]').forEach(el => el.onclick = async () => { const pid = el.dataset.logPlan; if (pid) { currentPlanId = pid; currentView = 'detail'; await render(); } });
  $$('[data-task-edit]').forEach(b => b.onclick = async (e) => {
    e.stopPropagation();
    const pid = currentPlanId;
    const planData = await db.getPlan(pid);
    if (!planData) return;
    let task = null;
    for (const m of (planData.milestones || [])) { const t = (m.tasks || []).find(x => x.id === b.dataset.taskEdit); if (t) { task = t; break; } }
    if (!task) return;
    $('#edit-task-id').value = task.id;
    $('#edit-task-plan-id').value = pid;
    $('#edit-task-title').value = task.title;
    $('#edit-task-desc').value = task.description || '';
    $('#edit-task-estimated').value = task.estimated_minutes || 60;
    $('#edit-task-priority').value = task.priority || 'medium';
    $('#edit-task-dialog').showModal();
  });
}

function bindPlanDetailMilestones(planId, milestones) {
  $('#template-select').onchange = async () => {
    const key = $('#template-select').value; if (!key) return;
    const tmpl = templates[key]; if (!tmpl) return;
    showLoading('应用模板...');
    for (const phase of tmpl) {
      const mid = await db.createMilestone(planId, phase.title, '');
      if (!mid) continue;
      for (const t of (phase.tasks || [])) {
        await db.createTask(mid, planId, typeof t === 'string' ? t : t.title || '任务', typeof t === 'string' ? '' : (t.description || ''), 60, 'medium');
      }
    }
    hideLoading();
    toast('模板已应用'); await render();
  };
  $('#add-plan-log-btn')?.addEventListener('click', () => { $('#log-plan-id').value = planId; $('#log-task-id').value = ''; $('#log-dialog').showModal(); });
  $('#add-milestone-btn').onclick = async () => { await db.createMilestone(planId, '新阶段', ''); toast('已添加新阶段'); await render(); };
  $$('[data-milestone-edit]').forEach(el => el.onclick = () => {
    const mid = el.dataset.milestoneEdit;
    const input = document.createElement('input'); input.value = el.textContent; input.className = 'inline-edit';
    el.replaceWith(input); input.focus();
    input.onblur = async () => { await db.updateMilestone(mid, { title: input.value.trim() || el.textContent }); await render(); };
    input.onkeydown = (e) => { if (e.key === 'Enter') input.blur(); if (e.key === 'Escape') { input.value = el.textContent; input.blur(); } };
  });
  $$('[data-milestone-up]').forEach(async b => b.onclick = async () => { /* TODO: reorder */ await render(); });
  $$('[data-milestone-down]').forEach(async b => b.onclick = async () => { /* TODO: reorder */ await render(); });
  $$('[data-milestone-del]').forEach(b => b.onclick = () => {
    $('#confirm-msg').textContent = '确认删除此阶段及其所有任务？';
    $('#confirm-action').onclick = async () => { await db.deleteMilestone(b.dataset.milestoneDel); $('#confirm-dialog').close(); toast('已删除'); await render(); };
    $('#confirm-dialog').showModal();
  });
}

async function renderLogs() {
  showOnly('#logs-view'); $('#view-title').textContent = '学习日志'; $('#view-subtitle').textContent = '按时间倒序展示所有学习记录';
  showLoading('加载日志...');
  const [plans, allLogs] = await Promise.all([db.getPlans(), db.getLogs()]);
  hideLoading();
  $('#logs-view').innerHTML = `<div class="toolbar"><select id="logs-plan-filter"><option value="">全部计划</option>${plans.map(p => `<option value="${p.id}">${p.title}</option>`).join('')}</select><button class="ghost" id="add-log-global">+ 添加日志</button></div><section class="panel" id="logs-list">${allLogs.map(logItem).join('') || '<p class="muted">暂无日志</p>'}</section>`;
  const filterDraw = () => { const pid = $('#logs-plan-filter').value; const filtered = pid ? allLogs.filter(l => l.plan_id === pid) : allLogs; $('#logs-list').innerHTML = filtered.map(logItem).join('') || '<p class="muted">暂无日志</p>'; };
  $('#logs-plan-filter').onchange = filterDraw;
  $('#add-log-global').onclick = () => { $('#log-plan-id').value = ''; $('#log-task-id').value = ''; $('#log-dialog').showModal(); };
  $$('[data-log-nav]').forEach(el => el.onclick = async () => { const pid = el.dataset.logPlan; if (pid) { currentPlanId = pid; currentView = 'detail'; await render(); } });
}

function renderUsers() {
  showOnly('#users-view'); $('#view-title').textContent = '用户管理'; $('#view-subtitle').textContent = '管理所有注册用户（仅管理员可见）';
  if (!Auth.isAdmin()) { $('#users-view').innerHTML = '<div class="panel"><p class="muted">仅管理员可访问</p></div>'; return; }
  showLoading('加载用户列表...');
  Auth.listUsers().then(async res => {
    hideLoading();
    if (!res.ok) { $('#users-view').innerHTML = `<div class="panel"><p class="muted">${res.error || '加载失败'}</p></div>`; return; }
    const users = res.users || [];
    $('#users-view').innerHTML = `<section class="panel"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px"><h3>用户列表（${users.length}）</h3></div><div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:14px"><thead><tr style="border-bottom:1px solid var(--line)"><th style="text-align:left;padding:8px;color:var(--muted)">用户名</th><th style="text-align:left;padding:8px;color:var(--muted)">邮箱</th><th style="text-align:left;padding:8px;color:var(--muted)">角色</th><th style="text-align:center;padding:8px;color:var(--muted)">状态</th><th style="text-align:left;padding:8px;color:var(--muted)">注册时间</th><th style="text-align:right;padding:8px;color:var(--muted)">操作</th></tr></thead><tbody>${users.map(userRow).join('')}</tbody></table></div></section>`;
    bindUserActions();
  }).catch(() => { hideLoading(); $('#users-view').innerHTML = '<div class="panel"><p class="muted">加载失败</p></div>'; });
}

function userRow(u) {
  const canToggle = !(u.role === 'admin' && u.active);
  return `<tr style="border-bottom:1px solid var(--line)"><td style="padding:8px"><b>${u.username}</b></td><td style="padding:8px;color:var(--muted)">${u.email || '-'}</td><td style="padding:8px">${u.role === 'admin' ? '🔑 管理员' : '普通用户'}</td><td style="text-align:center;padding:8px"><span class="${u.active ? 'pct-high' : 'pct-low'}">● ${u.active ? '已激活' : '已禁用'}</span></td><td style="padding:8px;color:var(--muted);font-size:13px">${(u.created_at || '').slice(0,10)}</td><td style="text-align:right;padding:8px"><button class="ghost-sm" data-edit-user="${u.id}">编辑</button>${u.active ? `<button class="ghost-sm" data-deactivate-user="${u.id}" ${u.role === 'admin' ? 'disabled' : ''}>禁用</button>` : `<button class="ghost-sm" data-activate-user="${u.id}" style="color:var(--ok)">激活</button>`}${u.role !== 'admin' ? `<button class="ghost-sm danger" data-delete-user="${u.id}">删除</button>` : ''}</td></tr>`;
}

function bindUserActions() {
  $$('[data-edit-user]').forEach(b => b.onclick = async () => {
    const res = await Auth.listUsers(); const u = (res.users || []).find(x => x.id === b.dataset.editUser); if (!u) return;
    $('#edit-user-id').value = u.id; $('#edit-user-username').value = u.username; $('#edit-user-email').value = u.email || '';
    $('#edit-user-role').value = u.role; $('#edit-user-password').value = ''; $('#edit-user-dialog').showModal();
  });
  $$('[data-activate-user]').forEach(b => b.onclick = async () => { showLoading('激活中...'); const r = await Auth.activateUser(b.dataset.activateUser); hideLoading(); toast(r.ok ? '已激活' : (r.error || '失败')); await render(); });
  $$('[data-deactivate-user]').forEach(b => b.onclick = () => {
    $('#confirm-msg').textContent = '确认禁用此用户？';
    $('#confirm-action').onclick = async () => { showLoading('禁用中...'); const r = await Auth.deactivateUser(b.dataset.deactivateUser); hideLoading(); $('#confirm-dialog').close(); toast(r.ok ? '已禁用' : (r.error || '失败')); await render(); };
    $('#confirm-dialog').showModal();
  });
  $$('[data-delete-user]').forEach(b => b.onclick = () => {
    $('#confirm-msg').textContent = '确认删除此用户？不可恢复。';
    $('#confirm-action').onclick = async () => { showLoading('删除中...'); const r = await Auth.deleteUser(b.dataset.deleteUser); hideLoading(); $('#confirm-dialog').close(); toast(r.ok ? '已删除' : (r.error || '失败')); await render(); };
    $('#confirm-dialog').showModal();
  });
}

function renderData() {
  showOnly('#data-view'); $('#view-title').textContent = '数据管理'; $('#view-subtitle').textContent = '所有数据存储在 MySQL，服务端自动备份';
  $('#data-view').innerHTML = `<section class="panel"><h3>MySQL 数据库</h3><p>所有计划、任务、日志数据存储在云服务器 MySQL 8.0 中。清除浏览器缓存不会丢失任何数据。</p><div class="toolbar"><button class="primary" disabled>数据自动持久化 · 无需操作</button></div></section>`;
}

boot().catch(err => { console.error(err); document.body.innerHTML = `<pre class="fatal">初始化失败：${err.message}</pre>`; });
