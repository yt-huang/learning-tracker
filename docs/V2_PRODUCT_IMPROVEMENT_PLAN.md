# V2 Product Improvement Plan

> For Hermes: Use opencode (Atlas - Plan Executor) to implement task by task.

## Overview
Five improvements to the learning-tracker web app with a product-centric approach.

## Task 1: Password Hardening + Transition to admin/admin123

**Files:**
- Modify: `js/auth.js`
- Modify: `index.html` (minor placeholder)

**Changes in auth.js:**
```js
// Replace plaintext comparison with SHA-256 hash
const ADMIN_HASH = '240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9'; // sha256('admin123')
login(username, password) {
  return username === 'admin' && this.hash(password) === ADMIN_HASH;
}
hash(s) { return crypto.subtle ? ... : fallback; }
```

**AI Hub frontend:** Already reads ADMIN_PASSWORD env var - just confirm `.env` has it.

**Verify:** Login with admin/admin123 works, admin/admin fails.

---

## Task 2: Plan Full CRUD

**Files:**
- Modify: `js/db.js` - verify updatePlan/deletePlan exist
- Modify: `js/app.js` - add edit/delete/duplicate handlers
- Modify: `index.html` - add edit plan dialog, delete confirm
- Modify: `css/style.css` - edit action styles

**Current db.js has:**
- `createPlan()`, `getPlans()`, `getPlan()`, `updatePlan()`, `deletePlan()`
- Need to verify and add `duplicatePlan()`

**UI additions:**
- Plan card action buttons: 编辑 | 复制 | 删除
- Edit plan dialog (reuse plan-dialog modal)
- Delete confirmation modal
- Plan list refresh after operations

**Verify:** Create plan → edit title → delete → duplicate.

---

## Task 3: Milestone CRUD + Templates + AI Stages

**Files:**
- Modify: `js/app.js` - milestone add/edit/delete/reorder handlers
- Modify: `js/db.js` - add milestone CRUD methods (verify exist)
- Modify: `index.html` - milestone management UI
- Modify: `css/style.css` - milestone controls
- Modify: `js/planner.js` - add template library

**New features:**
- 入门模板: 4 generic phases
- 实战模板: 5 hands-on phases
- 深度模板: 6 research phases
- "+ 添加阶段" button in plan detail
- Inline edit (click title to rename)
- Up/down arrows for reorder
- Stage deletion with task cascade
- AI-generated stages already work; ensure they render properly

**Verify:** Apply template → add stage → edit title → reorder → delete.

---

## Task 4: Tasks with Progress Sliders

**Files:**
- Modify: `js/app.js` - render progress slider, handle drag events
- Modify: `index.html` - update task template
- Modify: `css/style.css` - slider styling

**Implementation:**
- `<input type="range" min="0" max="100" value="${task.progress}">` for each task
- `oninput` handler calls `db.updateTask(…)` and re-renders progress bar
- Visual: track color fills based on value (0% gray, 1-99% blue, 100% green)
- Show percentage number beside slider

**Verify:** Drag slider → refresh page → value persists.

---

## Task 5: Logs Under Tasks + Clickable Navigation

**Files:**
- Modify: `js/app.js` - render task logs inline, add navigation links
- Modify: `index.html` - log section layout
- Modify: `css/style.css` - log display under tasks

**Implementation:**
- Each task in plan detail shows: "[📝 3 条日志 | 添加日志]"
- Click "📝 N 条日志" → inline expand showing logs for that task
- Click log entry → switches to 日志 tab with that plan/task highlighted
- "添加日志" button opens log dialog pre-filled with plan_id + task_id
- Global logs tab: filter by plan, filter by task

**Verify:** Add log to a task → see count update → click to expand → navigate to logs tab.  
