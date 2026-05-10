const SESSION_KEY = 'learning_tracker_session';
// hash of 'admin123' using simpleHash (works on HTTP where crypto.subtle is unavailable)
const ADMIN_HASH = '39c43b7d39c43b7d39c43b7d39c43b7d39c43b7d39c43b7d39c43b7d39c43b7d'; // simpleHash('admin123')

function simpleHash(s) {
  let hash = 0;
  for (let i = 0; i < s.length; i++) {
    const chr = s.charCodeAt(i);
    hash = ((hash << 5) - hash) + chr;
    hash |= 0;
  }
  // convert to hex string padded to 64 chars (SHA-256 hex length)
  const n = Math.abs(hash);
  const hex = n.toString(16).padStart(8, '0');
  // repeat to match 64-char hex length (simple hash is weak but same format)
  return hex.repeat(8);
}

async function hashPassword(s) {
  if (window.crypto?.subtle?.digest) {
    const encoder = new TextEncoder();
    const data = encoder.encode(s);
    const hashBuffer = await crypto.subtle.digest('SHA-256', data);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  }
  return simpleHash(s);
}

export const Auth = {
  isLoggedIn() {
    try {
      const session = JSON.parse(localStorage.getItem(SESSION_KEY) || 'null');
      return Boolean(session && session.user === 'admin' && session.expiresAt > Date.now());
    } catch {
      return false;
    }
  },
  async login(username, password) {
    if (username === 'admin' && (await hashPassword(password)) === ADMIN_HASH) {
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
