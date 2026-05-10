import { Auth } from './auth.js';
import { LearningDB } from './db.js';
import { generateLearningPlan, inferTitleFromUrl } from './planner.js';

const db = new LearningDB();
let currentView = 'dashboard';
let currentPlanId = null;

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
function toast(msg) { $('#toast').textContent = msg; $('#toast').classList.remove('hidden'); setTimeout(() => $('#toast').classList.add('hidden'), 2200); }
function minutes(m) { const h = Math.floor((m || 0) / 60); const min = (m || 0) % 60; return h ? `${h}h ${min}m` : `${min}m`; }
function statusText(s) { return ({not_started:'未开始', in_progress:'进行中', paused:'暂停', completed:'已完成', todo:'待办', doing:'进行中', done:'已完成'})[s] || s; }

async function boot() {
  bindAuth();
  if (Auth.isLoggedIn()) await showApp(); else showLogin();
}

function bindAuth() {
  $('#login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (Auth.login($('#username').value.trim(), $('#password').value)) await showApp();
    else $('#login-error').textContent = '用户名或密码错误';
  });
  $('#logout-btn').addEventListener('click', () => { Auth.logout(); showLogin(); });
}

async function showApp() {
  $('#login-screen').classList.add('hidden'); $('#app').classList.remove('hidden');
  await db.init(); bindApp(); render();
}
function showLogin() { $('#app').classList.add('hidden'); $('#login-screen').classList.remove('hidden'); }

function bindApp() {
  $$('.nav-btn').forEach(btn => btn.onclick = () => switchView(btn.dataset.view));
  $('#new-plan-btn').onclick = () => $('#plan-dialog').showModal();
  $('#cancel-plan').onclick = () => $('#plan-dialog').close();
  $('#cancel-log').onclick = () => $('#log-dialog').close();
  $('#source-url').addEventListener('input', () => { if (!$('#plan-title').value) $('#plan-title').placeholder = inferTitleFromUrl($('#source-url').value); });
  $('#plan-form').onsubmit = async (e) => {
    e.preventDefault();
    const plan = generateLearningPlan({ url: $('#source-url').value, title: $('#plan-title').value, category: $('#plan-category').value, goal: $('#plan-goal').value, difficulty: $('#plan-difficulty').value, hours: $('#plan-hours').value });
    currentPlanId = await db.createPlan(plan);
    e.target.reset(); $('#plan-dialog').close(); toast('计划已写入 SQLite'); switchView('detail');
  };
  $('#log-form').onsubmit = async (e) => {
    e.preventDefault();
    await db.createLog({ planId: $('#log-plan-id').value, taskId: $('#log-task-id').value, summary: $('#log-summary').value, durationMinutes: $('#log-duration').value, notes: $('#log-notes').value });
    e.target.reset(); $('#log-dialog').close(); toast('学习日志已保存到 SQLite'); render();
  };
}

function switchView(view) {
  currentView = view === 'detail' ? 'detail' : view;
  $$('.nav-btn').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  render();
}

function showOnly(id) { $$('.view').forEach(v => v.classList.add('hidden')); $(id).classList.remove('hidden'); }

function render() {
  if (currentView === 'dashboard') return renderDashboard();
  if (currentView === 'plans') return renderPlans();
  if (currentView === 'detail') return renderPlanDetail();
  if (currentView === 'logs') return renderLogs();
  if (currentView === 'data') return renderData();
}

function renderDashboard() {
  showOnly('#dashboard-view'); $('#view-title').textContent = '仪表盘'; $('#view-subtitle').textContent = '学习数据来自浏览器 SQLite 数据库';
  const stats = db.getStats(); const plans = db.getPlans(); const logs = db.getLogs().slice(0, 6);
  $('#dashboard-view').innerHTML = `
    <div class="stats-grid">
      <div class="stat"><b>${stats.total || 0}</b><span>学习计划</span></div>
      <div class="stat"><b>${stats.completed || 0}</b><span>已完成</span></div>
      <div class="stat"><b>${Math.round(stats.avg_progress || 0)}%</b><span>平均进度</span></div>
      <div class="stat"><b>${minutes(stats.total_minutes || 0)}</b><span>总学习时长</span></div>
    </div>
    <div class="grid-2 layout-gap">
      <section class="panel"><h3>进行中的计划</h3>${plans.slice(0,4).map(planCard).join('') || '<p class="muted">暂无计划</p>'}</section>
      <section class="panel"><h3>最近学习日志</h3>${logs.map(logItem).join('') || '<p class="muted">暂无日志</p>'}</section>
    </div>`;
  bindPlanCards();
}

function planCard(p) {
  return `<article class="plan-card" data-plan="${p.id}"><div><h3>${p.title}</h3><p>${p.description || ''}</p><small>${p.category || '未分类'} · ${statusText(p.status)} · ${p.task_count || 0} 任务</small></div><div class="progress"><span style="width:${p.progress || 0}%"></span></div><b>${p.progress || 0}%</b></article>`;
}
function logItem(l) { return `<div class="log-item"><b>${l.summary}</b><span>${l.plan_title || ''}${l.task_title ? ' · ' + l.task_title : ''}</span><small>${l.date} · ${minutes(l.duration_minutes)}</small></div>`; }
function bindPlanCards() { $$('[data-plan]').forEach(el => el.onclick = () => { currentPlanId = el.dataset.plan; currentView = 'detail'; render(); }); }

function renderPlans() {
  showOnly('#plans-view'); $('#view-title').textContent = '学习计划'; $('#view-subtitle').textContent = '搜索、筛选、进入详情跟踪任务';
  const plans = db.getPlans();
  $('#plans-view').innerHTML = `<div class="toolbar"><input id="search" placeholder="搜索标题/分类/链接" /><select id="status-filter"><option value="">全部状态</option><option value="not_started">未开始</option><option value="in_progress">进行中</option><option value="completed">已完成</option></select></div><div id="plans-list" class="plans-list"></div>`;
  const draw = () => {
    const q = $('#search').value.toLowerCase(), s = $('#status-filter').value;
    $('#plans-list').innerHTML = plans.filter(p => (!s || p.status === s) && JSON.stringify(p).toLowerCase().includes(q)).map(planCard).join('') || '<p class="muted">没有匹配计划</p>';
    bindPlanCards();
  };
  $('#search').oninput = draw; $('#status-filter').onchange = draw; draw();
}

function renderPlanDetail() {
  if (!currentPlanId) { currentView = 'plans'; return renderPlans(); }
  const plan = db.getPlan(currentPlanId); if (!plan) { currentPlanId = null; return renderPlans(); }
  showOnly('#plan-detail-view'); $('#view-title').textContent = plan.title; $('#view-subtitle').textContent = plan.source_url || '计划详情';
  const milestones = db.getMilestones(plan.id); const tasks = db.getTasks(plan.id); const logs = db.getLogs(plan.id);
  $('#plan-detail-view').innerHTML = `<button class="ghost" id="back-plans">← 返回计划</button><section class="panel hero"><div><h2>${plan.title}</h2><p>${plan.description || ''}</p><a href="${plan.source_url}" target="_blank">${plan.source_url || ''}</a></div><div class="big-progress"><b>${plan.progress}%</b><span>完成进度</span></div></section><div class="milestones">${milestones.map(m => `<section class="panel"><h3>${m.title}</h3><p class="muted">${m.description || ''}</p>${tasks.filter(t => t.milestone_id === m.id).map(taskCard).join('')}</section>`).join('')}</div><section class="panel"><h3>本计划日志</h3>${logs.map(logItem).join('') || '<p class="muted">暂无日志</p>'}</section>`;
  $('#back-plans').onclick = () => switchView('plans'); bindTaskButtons();
}

function taskCard(t) {
  return `<div class="task"><div><b>${t.title}</b><p>${t.description || ''}</p><small>${statusText(t.status)} · 预计 ${minutes(t.estimated_minutes)} · 已学 ${minutes(t.spent_minutes)}</small><div class="progress"><span style="width:${t.progress}%"></span></div></div><div class="task-actions"><button data-task-log="${t.id}">记日志</button><button data-task-doing="${t.id}">进行中</button><button data-task-done="${t.id}">完成</button></div></div>`;
}
function bindTaskButtons() {
  $$('[data-task-log]').forEach(b => b.onclick = () => { $('#log-plan-id').value = currentPlanId; $('#log-task-id').value = b.dataset.taskLog; $('#log-dialog').showModal(); });
  $$('[data-task-doing]').forEach(b => b.onclick = async () => { await db.updateTask(b.dataset.taskDoing, { status: 'doing', progress: 50 }); toast('任务已更新'); render(); });
  $$('[data-task-done]').forEach(b => b.onclick = async () => { await db.updateTask(b.dataset.taskDone, { status: 'done', progress: 100 }); toast('任务已完成'); render(); });
}

function renderLogs() {
  showOnly('#logs-view'); $('#view-title').textContent = '学习日志'; $('#view-subtitle').textContent = '按时间倒序展示所有学习记录';
  $('#logs-view').innerHTML = `<section class="panel">${db.getLogs().map(logItem).join('') || '<p class="muted">暂无日志</p>'}</section>`;
}

function renderData() {
  showOnly('#data-view'); $('#view-title').textContent = '数据管理'; $('#view-subtitle').textContent = 'SQLite .db 文件导入导出，业务数据不使用实时数据库';
  $('#data-view').innerHTML = `<section class="panel"><h3>SQLite 数据库</h3><p>业务数据保存在浏览器 SQLite（sql.js）中，并以 .db 文件形式持久化到 IndexedDB。</p><div class="toolbar"><button id="export-db" class="primary">导出 .db</button><label class="file-btn">导入 .db<input id="import-db" type="file" accept=".db,.sqlite,application/x-sqlite3" hidden /></label></div></section>`;
  $('#export-db').onclick = () => db.exportDb();
  $('#import-db').onchange = async (e) => { if (e.target.files[0]) { await db.importDb(e.target.files[0]); toast('SQLite 数据库已导入'); renderDashboard(); } };
}

boot().catch(err => { console.error(err); document.body.innerHTML = `<pre class="fatal">初始化失败：${err.message}</pre>`; });
