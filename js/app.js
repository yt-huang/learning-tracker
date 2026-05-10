import { Auth } from './auth.js';
import { LearningDB } from './db.js';
import { generateLearningPlan, inferTitleFromUrl, templates } from './planner.js';

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
    const ok = await Auth.login($('#username').value.trim(), $('#password').value);
    if (ok) await showApp();
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
  $('#ai-analyze-plan').onclick = analyzeLinkWithAI;
  $('#plan-form').onsubmit = async (e) => {
    e.preventDefault();
    const plan = generateLearningPlan({ url: $('#source-url').value, title: $('#plan-title').value, category: $('#plan-category').value, goal: $('#plan-goal').value, difficulty: $('#plan-difficulty').value, hours: $('#plan-hours').value });
    currentPlanId = await db.createPlan(plan);
    resetPlanDialog(e.target);
    toast('快速计划已写入 SQLite'); switchView('detail');
  };
  $('#edit-plan-form').onsubmit = async (e) => {
    e.preventDefault();
    const pid = $('#edit-plan-id').value;
    await db.updatePlan(pid, {
      title: $('#edit-plan-title').value.trim(),
      description: $('#edit-plan-desc').value.trim(),
      category: $('#edit-plan-category').value.trim(),
      sourceUrl: $('#edit-plan-url').value.trim(),
      estimatedHours: Number($('#edit-plan-hours').value),
    });
    $('#edit-plan-dialog').close();
    toast('计划已更新');
    render();
  };
  $('#cancel-edit-plan').onclick = () => $('#edit-plan-dialog').close();
  $('#confirm-cancel').onclick = () => $('#confirm-dialog').close();
  $('#log-form').onsubmit = async (e) => {
    e.preventDefault();
    await db.createLog({ planId: $('#log-plan-id').value, taskId: $('#log-task-id').value, summary: $('#log-summary').value, durationMinutes: $('#log-duration').value, notes: $('#log-notes').value });
    e.target.reset(); $('#log-dialog').close(); toast('学习日志已保存到 SQLite'); render();
  };
}

function resetPlanDialog(form) {
  form.reset();
  $('#ai-analysis-preview').classList.add('hidden');
  $('#ai-analysis-preview').innerHTML = '';
  $('#ai-analyze-plan').disabled = false;
  $('#ai-analyze-plan').textContent = 'AI 深度分析';
  $('#plan-dialog').close();
}

async function analyzeLinkWithAI() {
  const url = $('#source-url').value.trim();
  if (!url) return toast('请先输入学习链接');
  const preview = $('#ai-analysis-preview');
  const btn = $('#ai-analyze-plan');
  btn.disabled = true;
  btn.textContent = 'AI 分析中...';
  preview.classList.remove('hidden');
  preview.innerHTML = '<b>正在读取链接并生成阶段目标...</b><p>如果服务器没有配置 AI Key，会自动使用链接标题/目录生成增强计划。</p>';
  try {
    const res = await fetch('/api/analyze-link', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url,
        goal: $('#plan-goal').value,
        level: $('#plan-difficulty').value,
        hoursPerWeek: Math.max(1, Math.round(Number($('#plan-hours').value || 12) / 3)),
      }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || 'AI 分析失败');
    const plan = data.plan;
    preview.innerHTML = `<b>${plan.aiUsed ? 'AI 已生成计划' : '已生成增强计划'}</b><p>${plan.analysisSummary || plan.description || ''}</p><ul><li>标题：${plan.title}</li><li>阶段：${plan.milestones?.length || 0} 个</li><li>预计：${plan.estimatedHours || 0} 小时</li></ul><button type="button" class="primary" id="save-ai-plan">保存 AI 计划到 SQLite</button>`;
    $('#save-ai-plan').onclick = async () => {
      currentPlanId = await db.createPlan(plan);
      resetPlanDialog($('#plan-form'));
      toast('AI 计划已写入 SQLite');
      switchView('detail');
    };
  } catch (err) {
    preview.innerHTML = `<b>AI 分析失败</b><p>${err.message}</p><p>可以先使用“快速生成并保存”。</p>`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'AI 深度分析';
  }
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
  return `<article class="plan-card" data-plan="${p.id}"><div><h3>${p.title}</h3><p>${p.description || ''}</p><small>${p.category || '未分类'} · ${statusText(p.status)} · ${p.task_count || 0} 任务</small><div class="plan-actions"><button class="ghost-sm" data-edit-plan="${p.id}">编辑</button><button class="ghost-sm" data-duplicate-plan="${p.id}">复制</button><button class="ghost-sm danger" data-delete-plan="${p.id}">删除</button></div></div><div class="progress"><span style="width:${p.progress || 0}%"></span></div><b>${p.progress || 0}%</b></article>`;
}
function logItem(l) { return `<div class="log-item" data-log-nav="${l.id}" data-log-plan="${l.plan_id}" style="cursor:pointer"><b>${l.summary}</b><span>${l.plan_title || ''}${l.task_title ? ' · ' + l.task_title : ''}</span><small>${l.date} · ${minutes(l.duration_minutes)}</small></div>`; }
function bindPlanCards() {
  $$('[data-plan]').forEach(el => el.onclick = (e) => {
    if (e.target.closest('[data-edit-plan],[data-duplicate-plan],[data-delete-plan]')) return;
    currentPlanId = el.dataset.plan; currentView = 'detail'; render();
  });
  $$('[data-edit-plan]').forEach(b => b.onclick = async (e) => {
    e.stopPropagation();
    editPlanDialog(b.dataset.editPlan);
  });
  $$('[data-duplicate-plan]').forEach(b => b.onclick = async (e) => {
    e.stopPropagation();
    await db.duplicatePlan(b.dataset.duplicatePlan);
    toast('计划已复制');
    render();
  });
  $$('[data-delete-plan]').forEach(b => b.onclick = async (e) => {
    e.stopPropagation();
    const pid = b.dataset.deletePlan;
    $('#confirm-msg').textContent = '确认删除此计划？关联的阶段和任务将一并删除，不可恢复。';
    $('#confirm-action').onclick = async () => {
      await db.deletePlan(pid);
      if (currentPlanId === pid) { currentPlanId = null; currentView = 'plans'; }
      $('#confirm-dialog').close();
      toast('计划已删除');
      render();
    };
    $('#confirm-dialog').showModal();
  });
}

function editPlanDialog(planId) {
  const plan = db.getPlan(planId);
  if (!plan) return;
  $('#edit-plan-id').value = planId;
  $('#edit-plan-title').value = plan.title;
  $('#edit-plan-desc').value = plan.description || '';
  $('#edit-plan-category').value = plan.category || '';
  $('#edit-plan-url').value = plan.source_url || '';
  $('#edit-plan-hours').value = plan.estimated_hours || 0;
  $('#edit-plan-dialog').showModal();
}

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
  const tmplKeys = Object.keys(templates);
  $('#plan-detail-view').innerHTML = `<button class="ghost" id="back-plans">← 返回计划</button><section class="panel hero"><div><h2>${plan.title}</h2><p>${plan.description || ''}</p><a href="${plan.source_url}" target="_blank">${plan.source_url || ''}</a></div><div class="big-progress"><b>${plan.progress}%</b><span>完成进度</span></div></section><div class="milestone-toolbar"><select id="template-select"><option value="">套用模板</option>${tmplKeys.map(k => `<option value="${k}">${k}</option>`).join('')}</select><button class="ghost" id="add-milestone-btn">+ 添加阶段</button></div><div class="milestones">${milestones.map(m => milestoneCard(m, tasks.filter(t => t.milestone_id === m.id))).join('')}</div><section class="panel"><h3>本计划日志 <button class="ghost-sm" id="add-plan-log-btn" style="margin-left:8px">+ 添加日志</button></h3>${logs.map(logItem).join('') || '<p class="muted">暂无日志</p>'}</section>`;
  $('#back-plans').onclick = () => switchView('plans');
  bindPlanDetailMilestones(plan.id, milestones);
  bindTaskButtons();
}

function milestoneCard(m, ms) {
  return `<section class="panel" data-milestone="${m.id}">
    <div class="milestone-header">
      <span class="milestone-title" data-milestone-edit="${m.id}">${m.title}</span>
      <div class="milestone-actions">
        <button class="ghost-sm" data-milestone-up="${m.id}" title="上移">↑</button>
        <button class="ghost-sm" data-milestone-down="${m.id}" title="下移">↓</button>
        <button class="ghost-sm danger" data-milestone-del="${m.id}" title="删除">✕</button>
      </div>
    </div>
    <p class="muted">${m.description || ''}</p>${ms.map(taskCard).join('')}</section>`;
}

function bindPlanDetailMilestones(planId, milestones) {
  $('#template-select').onchange = async () => {
    const key = $('#template-select').value;
    if (!key) return;
    const tmpl = templates[key];
    if (!tmpl) return;
    for (const phase of tmpl) {
      const mid = await db.createMilestone(planId, phase.title, '');
      for (const t of phase.tasks) {
        await db.addTaskToMilestone(planId, mid, t, '');
      }
    }
    await db.persist();
    toast('模板已应用');
    render();
  };

  $('#add-plan-log-btn')?.addEventListener('click', () => {
    $('#log-plan-id').value = planId;
    $('#log-task-id').value = '';
    $('#log-dialog').showModal();
  });

  $('#add-milestone-btn').onclick = async () => {
    await db.createMilestone(planId, '新阶段', '');
    toast('已添加新阶段');
    render();
  };

  $$('[data-milestone-edit]').forEach(el => el.onclick = () => {
    const mid = el.dataset.milestoneEdit;
    const input = document.createElement('input');
    input.value = el.textContent;
    input.className = 'inline-edit';
    el.replaceWith(input);
    input.focus();
    input.onblur = async () => {
      const val = input.value.trim() || el.textContent;
      await db.updateMilestone(mid, { title: val });
      render();
    };
    input.onkeydown = (e) => {
      if (e.key === 'Enter') input.blur();
      if (e.key === 'Escape') { input.value = el.textContent; input.blur(); }
    };
  });

  $$('[data-milestone-up]').forEach(b => b.onclick = async () => {
    const mid = b.dataset.milestoneUp;
    const ms = db.getMilestones(planId);
    const idx = ms.findIndex(m => m.id === mid);
    if (idx <= 0) return;
    const a = ms[idx]; const b2 = ms[idx - 1];
    await db.updateMilestone(a.id, { order_index: b2.order_index });
    await db.updateMilestone(b2.id, { order_index: a.order_index });
    render();
  });

  $$('[data-milestone-down]').forEach(b => b.onclick = async () => {
    const mid = b.dataset.milestoneDown;
    const ms = db.getMilestones(planId);
    const idx = ms.findIndex(m => m.id === mid);
    if (idx < 0 || idx >= ms.length - 1) return;
    const a = ms[idx]; const b2 = ms[idx + 1];
    await db.updateMilestone(a.id, { order_index: b2.order_index });
    await db.updateMilestone(b2.id, { order_index: a.order_index });
    render();
  });

  $$('[data-milestone-del]').forEach(b => b.onclick = async () => {
    const mid = b.dataset.milestoneDel;
    $('#confirm-msg').textContent = '确认删除此阶段及其所有任务？不可恢复。';
    $('#confirm-action').onclick = async () => {
      await db.deleteMilestone(mid);
      $('#confirm-dialog').close();
      toast('阶段已删除');
      render();
    };
    $('#confirm-dialog').showModal();
  });
}

function taskCard(t) {
  const pct = Number(t.progress || 0);
  const safeId = t.id.replace(/[^a-zA-Z0-9]/g,'_');
  const taskLogs = db.rows(`SELECT id, summary, date, duration_minutes, plan_id FROM logs WHERE task_id=? ORDER BY created_at DESC`, [t.id]);
  return `<div class="task" id="task-${safeId}"><div><b>${t.title}</b><p>${t.description || ''}</p><small>${statusText(t.status)} · 预计 ${minutes(t.estimated_minutes)} · 已学 ${minutes(t.spent_minutes)}</small><div class="progress"><span style="width:${pct}%"></span></div></div><div class="task-actions"><button data-task-log="${t.id}">记日志</button><label class="slider-label"><input type="range" min="0" max="100" value="${pct}" class="progress-slider" data-task-progress="${t.id}" /><span class="slider-val" id="slider-val-${safeId}">${pct}%</span></label><button class="ghost-sm" data-task-logs-toggle="${t.id}">📝 ${taskLogs.length}</button></div><div class="task-logs hidden" id="task-logs-${safeId}">${taskLogs.map(l => `<div class="task-log-entry" data-log-nav="${l.id}" data-log-plan="${l.plan_id}"><span>${l.summary}</span><small>${l.date} · ${minutes(l.duration_minutes)}</small></div>`).join('') || '<small class="muted">暂无日志</small>'}</div></div>`;
}
function bindTaskButtons() {
  $$('[data-task-log]').forEach(b => b.onclick = () => { $('#log-plan-id').value = currentPlanId; $('#log-task-id').value = b.dataset.taskLog; $('#log-dialog').showModal(); });
  $$('[data-task-progress]').forEach(slider => {
    slider.oninput = async () => {
      const val = Number(slider.value);
      const status = val >= 100 ? 'done' : val > 0 ? 'doing' : 'todo';
      await db.updateTask(slider.dataset.taskProgress, { progress: val, status });
      const safeId = slider.dataset.taskProgress.replace(/[^a-zA-Z0-9]/g,'_');
      const valSpan = document.getElementById('slider-val-' + safeId);
      if (valSpan) valSpan.textContent = val + '%';
    };
  });
  $$('[data-task-logs-toggle]').forEach(b => b.onclick = () => {
    const safeId = b.dataset.taskLogsToggle.replace(/[^a-zA-Z0-9]/g,'_');
    const el = document.getElementById('task-logs-' + safeId);
    if (el) el.classList.toggle('hidden');
  });
  $$('[data-log-nav]').forEach(el => el.onclick = () => {
    const planId = el.dataset.logPlan;
    if (planId) { currentPlanId = planId; currentView = 'detail'; }
    else { currentView = 'logs'; }
    render();
  });
}

function renderLogs() {
  showOnly('#logs-view'); $('#view-title').textContent = '学习日志'; $('#view-subtitle').textContent = '按时间倒序展示所有学习记录';
  const plans = db.getPlans();
  const allLogs = db.getLogs();
  $('#logs-view').innerHTML = `<div class="toolbar"><select id="logs-plan-filter"><option value="">全部计划</option>${plans.map(p => `<option value="${p.id}">${p.title}</option>`).join('')}</select><button class="ghost" id="add-log-global">+ 添加日志</button></div><section class="panel" id="logs-list">${allLogs.map(logItem).join('') || '<p class="muted">暂无日志</p>'}</section>`;
  const filterDraw = () => {
    const pid = $('#logs-plan-filter').value;
    const filtered = pid ? allLogs.filter(l => l.plan_id === pid) : allLogs;
    $('#logs-list').innerHTML = filtered.map(logItem).join('') || '<p class="muted">暂无日志</p>';
  };
  $('#logs-plan-filter').onchange = filterDraw;
  $('#add-log-global').onclick = () => {
    $('#log-plan-id').value = '';
    $('#log-task-id').value = '';
    $('#log-dialog').showModal();
  };
  bindLogNav();
}

function bindLogNav() {
  $$('[data-log-nav]').forEach(el => el.onclick = () => {
    const planId = el.dataset.logPlan;
    if (planId) { currentPlanId = planId; currentView = 'detail'; render(); }
  });
}

function renderData() {
  showOnly('#data-view'); $('#view-title').textContent = '数据管理'; $('#view-subtitle').textContent = 'SQLite .db 文件导入导出，业务数据不使用实时数据库';
  $('#data-view').innerHTML = `<section class="panel"><h3>SQLite 数据库</h3><p>业务数据保存在浏览器 SQLite（sql.js）中，并以 .db 文件形式持久化到 IndexedDB。</p><div class="toolbar"><button id="export-db" class="primary">导出 .db</button><label class="file-btn">导入 .db<input id="import-db" type="file" accept=".db,.sqlite,application/x-sqlite3" hidden /></label></div></section>`;
  $('#export-db').onclick = () => db.exportDb();
  $('#import-db').onchange = async (e) => { if (e.target.files[0]) { await db.importDb(e.target.files[0]); toast('SQLite 数据库已导入'); renderDashboard(); } };
}

boot().catch(err => { console.error(err); document.body.innerHTML = `<pre class="fatal">初始化失败：${err.message}</pre>`; });
