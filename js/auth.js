const SESSION_KEY = 'learning_tracker_session';

function apiBase() {
  return window.location.origin;
}

async function apiPost(path, body) {
  const headers = { 'Content-Type': 'application/json' };
  const token = localStorage.getItem('lt_token');
  if (token) headers['Authorization'] = 'Bearer ' + token;
  const res = await fetch(apiBase() + path, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });
  return res.json();
}

async function apiGet(path) {
  const headers = {};
  const token = localStorage.getItem('lt_token');
  if (token) headers['Authorization'] = 'Bearer ' + token;
  const res = await fetch(apiBase() + path, { headers });
  return res.json();
}

async function apiPut(path, body) {
  const headers = { 'Content-Type': 'application/json' };
  const token = localStorage.getItem('lt_token');
  if (token) headers['Authorization'] = 'Bearer ' + token;
  const res = await fetch(apiBase() + path, {
    method: 'PUT',
    headers,
    body: JSON.stringify(body),
  });
  return res.json();
}

async function apiDelete(path) {
  const headers = {};
  const token = localStorage.getItem('lt_token');
  if (token) headers['Authorization'] = 'Bearer ' + token;
  const res = await fetch(apiBase() + path, { method: 'DELETE', headers });
  return res.json();
}

export const Auth = {
  async login(username, password) {
    try {
      const data = await apiPost('/api/auth/login', { username, password });
      if (data.ok) {
        localStorage.setItem('lt_token', data.token);
        localStorage.setItem('lt_user', JSON.stringify(data.user));
        localStorage.setItem(SESSION_KEY, JSON.stringify({
          user: data.user.username,
          role: data.user.role,
          loginAt: Date.now(),
          expiresAt: Date.now() + 7 * 24 * 60 * 60 * 1000,
        }));
        return { ok: true, user: data.user };
      }
      return { ok: false, error: data.error || '登录失败' };
    } catch (e) {
      return { ok: false, error: '网络错误：无法连接到服务器' };
    }
  },

  async register(username, password, email) {
    try {
      const data = await apiPost('/api/auth/register', { username, password, email });
      if (data.ok) {
        if (data.token) {
          localStorage.setItem('lt_token', data.token);
          localStorage.setItem('lt_user', JSON.stringify(data.user));
          localStorage.setItem(SESSION_KEY, JSON.stringify({
            user: data.user.username,
            role: data.user.role,
            loginAt: Date.now(),
            expiresAt: Date.now() + 7 * 24 * 60 * 60 * 1000,
          }));
        }
        return { ok: true, message: data.message, user: data.user };
      }
      return { ok: false, error: data.error || '注册失败' };
    } catch (e) {
      return { ok: false, error: '网络错误：无法连接到服务器' };
    }
  },

  isLoggedIn() {
    try {
      const session = JSON.parse(localStorage.getItem(SESSION_KEY) || 'null');
      const token = localStorage.getItem('lt_token');
      return Boolean(token && session && session.user && session.expiresAt > Date.now());
    } catch {
      return false;
    }
  },

  getUser() {
    try {
      return JSON.parse(localStorage.getItem('lt_user') || 'null');
    } catch {
      return null;
    }
  },

  getToken() {
    return localStorage.getItem('lt_token');
  },

  isAdmin() {
    const user = this.getUser();
    return user && user.role === 'admin';
  },

  async logout() {
    try {
      await apiPost('/api/auth/logout', {});
    } catch (e) { /* ignore */ }
    localStorage.removeItem('lt_token');
    localStorage.removeItem('lt_user');
    localStorage.removeItem(SESSION_KEY);
  },

  async refreshUser() {
    const token = localStorage.getItem('lt_token');
    if (!token) return null;
    try {
      const data = await apiGet('/api/auth/me');
      if (data.ok && data.user) {
        localStorage.setItem('lt_user', JSON.stringify(data.user));
        return data.user;
      }
      // Token expired
      localStorage.removeItem('lt_token');
      localStorage.removeItem('lt_user');
      localStorage.removeItem(SESSION_KEY);
      return null;
    } catch {
      return null;
    }
  },

  // Admin API
  async listUsers() {
    return apiGet('/api/admin/users');
  },

  async updateUser(userId, data) {
    return apiPut(`/api/admin/users/${userId}`, data);
  },

  async activateUser(userId) {
    return apiPost(`/api/admin/users/activate/${userId}`, {});
  },

  async deactivateUser(userId) {
    return apiPost(`/api/admin/users/deactivate/${userId}`, {});
  },

  async deleteUser(userId) {
    return apiDelete(`/api/admin/users/${userId}`);
  },
};
