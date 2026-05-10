const SESSION_KEY = 'learning_tracker_session';

export const Auth = {
  isLoggedIn() {
    try {
      const session = JSON.parse(localStorage.getItem(SESSION_KEY) || 'null');
      return Boolean(session && session.user === 'admin' && session.expiresAt > Date.now());
    } catch {
      return false;
    }
  },
  login(username, password) {
    if (username === 'admin' && password === 'admin') {
      localStorage.setItem(SESSION_KEY, JSON.stringify({
        user: 'admin',
        loginAt: Date.now(),
        expiresAt: Date.now() + 7 * 24 * 60 * 60 * 1000,
      }));
      return true;
    }
    return false;
  },
  logout() {
    localStorage.removeItem(SESSION_KEY);
  }
};
