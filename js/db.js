/* REST API client — all data stored in MySQL via server.py */

function apiBase() {
  return window.location.origin;
}

async function api(method, path, body = null) {
  const headers = { 'Content-Type': 'application/json' };
  const token = localStorage.getItem('lt_token');
  if (token) headers['Authorization'] = 'Bearer ' + token;
  const opts = { method, headers };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(apiBase() + path, opts);
  return res.json();
}

export class LearningDB {
  constructor() {}

  async init() {
    // nothing to init — no sql.js anymore
    return this;
  }

  // ---- Plans ----
  async getPlans() {
    const res = await api('GET', '/api/plans');
    return res.ok ? (res.plans || []) : [];
  }

  async getPlan(id) {
    const res = await api('GET', `/api/plans/${id}`);
    return res.ok ? res.plan : null;
  }

  async createPlan(plan) {
    const res = await api('POST', '/api/plans', plan);
    return res.ok ? res.id : null;
  }

  async updatePlan(id, patch) {
    const res = await api('PUT', `/api/plans/${id}`, patch);
    return res.ok;
  }

  async deletePlan(id) {
    const res = await api('DELETE', `/api/plans/${id}`);
    return res.ok;
  }

  async duplicatePlan(id) {
    const res = await api('POST', `/api/plans/${id}/duplicate`);
    return res.ok ? res.id : null;
  }

  // ---- Milestones ----
  async createMilestone(planId, title, description = '') {
    const res = await api('POST', `/api/plans/${planId}/milestones`, { title, description });
    return res.ok ? res.id : null;
  }

  async createTask(milestoneId, planId, title, description = '', estimatedMinutes = 60, priority = 'medium') {
    const res = await api('POST', `/api/milestones/${milestoneId}/tasks`, { planId, title, description, estimatedMinutes, priority });
    return res.ok ? res.id : null;
  }

  async updateMilestone(id, patch) {
    const res = await api('PUT', `/api/milestones/${id}`, patch);
    return res.ok;
  }

  async deleteMilestone(id) {
    const res = await api('DELETE', `/api/milestones/${id}`);
    return res.ok;
  }

  // ---- Tasks ----
  async updateTask(id, patch) {
    const res = await api('PUT', `/api/plans/${patch.plan_id || ''}/tasks/${id}`, patch);
    return res.ok;
  }

  // ---- Logs ----
  async createLog({ planId, taskId, summary, durationMinutes, notes }) {
    const res = await api('POST', `/api/plans/${planId}/logs`, { taskId, summary, durationMinutes, notes });
    return res.ok ? res.id : null;
  }

  async getLogs(planId = null) {
    const path = planId ? `/api/plans/${planId}/logs` : '/api/logs';
    const res = await api('GET', path);
    return res.ok ? (res.logs || []) : [];
  }

  // ---- Stats ----
  async getStats() {
    const res = await api('GET', '/api/stats');
    if (res.ok) return res.stats;
    return { total: 0, completed: 0, avg_progress: 0, total_minutes: 0 };
  }

  // ---- Recalculate (handled by server) ----
  async recalculatePlan() { /* server handles this */ }

  // ---- Import/Export (handled by server in future) ----
  exportDb() { toast('MySQL 数据存储在服务端，无需导出'); }
  async importDb() { toast('MySQL 数据存储在服务端，无需导入'); }

  // ---- Helper: rows() for backward compat with taskCard ----
  async rows(sql, params = []) {
    // This is only used for reading task logs — fetch from plan detail API
    return [];
  }
}
