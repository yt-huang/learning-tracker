const IDB_NAME = 'learning-tracker-sqlite';
const IDB_STORE = 'database';
const DB_KEY = 'learning-tracker.db';

function now() { return new Date().toISOString(); }
function uid(prefix) { return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2)}`; }

export class LearningDB {
  constructor() { this.SQL = null; this.db = null; }

  async init() {
    this.SQL = await window.initSqlJs({ locateFile: f => `https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.10.3/${f}` });
    const bytes = await this.loadBytes();
    this.db = bytes ? new this.SQL.Database(bytes) : new this.SQL.Database();
    this.createSchema();
    if (!this.getPlans().length) await this.seed();
  }

  createSchema() {
    this.db.run(`
      PRAGMA foreign_keys = ON;
      CREATE TABLE IF NOT EXISTS plans (
        id TEXT PRIMARY KEY, title TEXT NOT NULL, source_url TEXT, description TEXT,
        category TEXT, difficulty TEXT, status TEXT, progress INTEGER DEFAULT 0,
        estimated_hours REAL DEFAULT 0, created_at TEXT, updated_at TEXT, completed_at TEXT
      );
      CREATE TABLE IF NOT EXISTS milestones (
        id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, title TEXT NOT NULL, description TEXT,
        order_index INTEGER DEFAULT 0,
        FOREIGN KEY(plan_id) REFERENCES plans(id) ON DELETE CASCADE
      );
      CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, milestone_id TEXT NOT NULL,
        title TEXT NOT NULL, description TEXT, status TEXT DEFAULT 'todo', progress INTEGER DEFAULT 0,
        estimated_minutes INTEGER DEFAULT 0, spent_minutes INTEGER DEFAULT 0, priority TEXT DEFAULT 'medium',
        order_index INTEGER DEFAULT 0, created_at TEXT, updated_at TEXT, completed_at TEXT,
        FOREIGN KEY(plan_id) REFERENCES plans(id) ON DELETE CASCADE,
        FOREIGN KEY(milestone_id) REFERENCES milestones(id) ON DELETE CASCADE
      );
      CREATE TABLE IF NOT EXISTS logs (
        id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, task_id TEXT,
        date TEXT NOT NULL, duration_minutes INTEGER DEFAULT 0, summary TEXT, notes TEXT, created_at TEXT,
        FOREIGN KEY(plan_id) REFERENCES plans(id) ON DELETE CASCADE,
        FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE SET NULL
      );
    `);
  }

  rows(sql, params = []) {
    const stmt = this.db.prepare(sql);
    stmt.bind(params);
    const out = [];
    while (stmt.step()) out.push(stmt.getAsObject());
    stmt.free();
    return out;
  }

  async persist() {
    const bytes = this.db.export();
    await new Promise((resolve, reject) => {
      const req = indexedDB.open(IDB_NAME, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(IDB_STORE);
      req.onerror = () => reject(req.error);
      req.onsuccess = () => {
        const tx = req.result.transaction(IDB_STORE, 'readwrite');
        tx.objectStore(IDB_STORE).put(bytes, DB_KEY);
        tx.oncomplete = () => { req.result.close(); resolve(); };
        tx.onerror = () => reject(tx.error);
      };
    });
  }

  async loadBytes() {
    return new Promise((resolve) => {
      const req = indexedDB.open(IDB_NAME, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(IDB_STORE);
      req.onerror = () => resolve(null);
      req.onsuccess = () => {
        const db = req.result;
        const tx = db.transaction(IDB_STORE, 'readonly');
        const get = tx.objectStore(IDB_STORE).get(DB_KEY);
        get.onsuccess = () => resolve(get.result || null);
        get.onerror = () => resolve(null);
        tx.oncomplete = () => db.close();
      };
    });
  }

  async seed() {
    await this.createPlan({
      title: 'luongnv89/claude-howto', sourceUrl: 'https://github.com/luongnv89/claude-howto',
      description: 'Claude 使用指南学习计划示例', category: 'AI 工具', difficulty: '进阶', estimatedHours: 10,
      milestones: [
        { title: '快速理解', description: '理解项目目标与目录', orderIndex: 1, tasks: [
          { title: '阅读 README', description: '整理核心章节', estimatedMinutes: 60, priority: 'high' },
          { title: '梳理使用场景', description: '记录适合自己的实践场景', estimatedMinutes: 45, priority: 'medium' }
        ]},
        { title: '实践输出', description: '复现实例并总结', orderIndex: 2, tasks: [
          { title: '复现关键示例', description: '运行或手动演练关键步骤', estimatedMinutes: 120, priority: 'high' },
          { title: '完成学习总结', description: '输出一页笔记', estimatedMinutes: 60, priority: 'medium' }
        ]}
      ]
    });
  }

  async createPlan(plan) {
    const id = uid('plan');
    const created = now();
    this.db.run('BEGIN');
    try {
      this.db.run(`INSERT INTO plans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`, [id, plan.title, plan.sourceUrl, plan.description, plan.category, plan.difficulty, 'not_started', 0, plan.estimatedHours || 0, created, created, null]);
      for (const [mIdx, m] of (plan.milestones || []).entries()) {
        const mid = uid('milestone');
        this.db.run(`INSERT INTO milestones VALUES (?, ?, ?, ?, ?)`, [mid, id, m.title, m.description || '', m.orderIndex || mIdx + 1]);
        for (const [tIdx, t] of (m.tasks || []).entries()) {
          const tid = uid('task');
          this.db.run(`INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`, [tid, id, mid, t.title, t.description || '', t.status || 'todo', t.progress || 0, t.estimatedMinutes || 0, t.spentMinutes || 0, t.priority || 'medium', t.orderIndex || tIdx + 1, created, created, null]);
        }
      }
      this.db.run('COMMIT');
      await this.persist();
      return id;
    } catch (e) { this.db.run('ROLLBACK'); throw e; }
  }

  getPlans() {
    return this.rows(`SELECT p.*, COALESCE(SUM(t.spent_minutes),0) spent_minutes, COUNT(t.id) task_count,
      SUM(CASE WHEN t.status='done' THEN 1 ELSE 0 END) done_count
      FROM plans p LEFT JOIN tasks t ON p.id=t.plan_id GROUP BY p.id ORDER BY p.updated_at DESC`);
  }
  getPlan(id) { return this.rows('SELECT * FROM plans WHERE id=?', [id])[0]; }
  getMilestones(planId) { return this.rows('SELECT * FROM milestones WHERE plan_id=? ORDER BY order_index', [planId]); }
  getTasks(planId) { return this.rows('SELECT * FROM tasks WHERE plan_id=? ORDER BY order_index', [planId]); }
  getLogs(planId = null) { return this.rows(`SELECT l.*, p.title plan_title, t.title task_title FROM logs l JOIN plans p ON p.id=l.plan_id LEFT JOIN tasks t ON t.id=l.task_id ${planId ? 'WHERE l.plan_id=?' : ''} ORDER BY l.created_at DESC`, planId ? [planId] : []); }

  async updateTask(id, patch) {
    const task = this.rows('SELECT * FROM tasks WHERE id=?', [id])[0];
    if (!task) return;
    const next = { ...task, ...patch, updated_at: now() };
    if (next.status === 'done' && !next.completed_at) next.completed_at = now();
    if (next.status !== 'done') next.completed_at = null;
    this.db.run(`UPDATE tasks SET status=?, progress=?, spent_minutes=?, updated_at=?, completed_at=? WHERE id=?`, [next.status, next.progress, next.spent_minutes, next.updated_at, next.completed_at, id]);
    await this.recalculatePlan(task.plan_id);
    await this.persist();
  }

  async createLog({ planId, taskId, summary, durationMinutes, notes }) {
    const id = uid('log');
    const created = now();
    this.db.run(`INSERT INTO logs VALUES (?, ?, ?, ?, ?, ?, ?, ?)`, [id, planId, taskId || null, created.slice(0, 10), Number(durationMinutes || 0), summary, notes || '', created]);
    if (taskId) {
      const t = this.rows('SELECT spent_minutes FROM tasks WHERE id=?', [taskId])[0];
      this.db.run('UPDATE tasks SET spent_minutes=?, updated_at=? WHERE id=?', [Number(t?.spent_minutes || 0) + Number(durationMinutes || 0), created, taskId]);
    }
    await this.recalculatePlan(planId);
    await this.persist();
  }

  async deletePlan(id) { this.db.run('DELETE FROM plans WHERE id=?', [id]); await this.persist(); }

  async recalculatePlan(planId) {
    const tasks = this.getTasks(planId);
    const progress = tasks.length ? Math.round(tasks.reduce((s, t) => s + Number(t.progress || 0), 0) / tasks.length) : 0;
    const status = progress >= 100 ? 'completed' : progress > 0 ? 'in_progress' : 'not_started';
    this.db.run('UPDATE plans SET progress=?, status=?, updated_at=?, completed_at=? WHERE id=?', [progress, status, now(), status === 'completed' ? now() : null, planId]);
  }

  getStats() {
    const planStats = this.rows(`SELECT COUNT(*) total, SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) completed, AVG(progress) avg_progress FROM plans`)[0];
    const time = this.rows(`SELECT COALESCE(SUM(duration_minutes),0) total_minutes, COALESCE(SUM(CASE WHEN date=date('now') THEN duration_minutes ELSE 0 END),0) today_minutes FROM logs`)[0];
    return { ...planStats, ...time };
  }

  exportDb() {
    const blob = new Blob([this.db.export()], { type: 'application/x-sqlite3' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `learning-tracker-${new Date().toISOString().slice(0,10)}.db`;
    a.click(); URL.revokeObjectURL(a.href);
  }

  async importDb(file) {
    const bytes = new Uint8Array(await file.arrayBuffer());
    this.db.close();
    this.db = new this.SQL.Database(bytes);
    this.createSchema();
    await this.persist();
  }
}
