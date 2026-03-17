const STORAGE_KEY = 'webrpa.jwt';

function normalizeToken(raw) {
    const txt = String(raw ?? '').trim();
    if (!txt) return '';
    if (txt.toLowerCase().startsWith('bearer ')) return txt.slice(7).trim();
    return txt;
}

export function getAuthToken() {
    try {
        return normalizeToken(localStorage.getItem(STORAGE_KEY) || '');
    } catch {
        return '';
    }
}

export function setAuthToken(rawToken) {
    const token = normalizeToken(rawToken);
    try {
        if (!token) {
            localStorage.removeItem(STORAGE_KEY);
        } else {
            localStorage.setItem(STORAGE_KEY, token);
        }
    } catch {
        // ignore storage errors (private mode, quota, etc.)
    }
    return token;
}

export function clearAuthToken() {
    return setAuthToken('');
}

