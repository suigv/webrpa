import { toast } from '../ui/toast.js';
import { getAuthToken } from '../state/auth.js';

function buildAuthHeaders(existingHeaders) {
    const headers = new Headers(existingHeaders || {});
    const token = getAuthToken();
    if (token && !headers.has('Authorization')) {
        headers.set('Authorization', `Bearer ${token}`);
    }
    return headers;
}

export async function authFetch(url, opts = {}) {
    const nextOpts = { ...opts };
    nextOpts.headers = buildAuthHeaders(nextOpts.headers);
    return fetch(url, nextOpts);
}

export async function fetchJson(url, opts = {}) {
    const { silentErrors = false, ...fetchOptions } = opts;
    try {
        fetchOptions.headers = buildAuthHeaders(fetchOptions.headers);
        const res = await fetch(url, fetchOptions);
        const txt = await res.text();
        const data = txt ? tryParseJson(txt) : {};

        if (!res.ok) {
            console.error(`API Error: ${url}`, res.status, data);
            if (!silentErrors && res.status === 401) {
                toast.error("未授权：请在「系统偏好」中设置 API Token");
            } else if (!silentErrors && res.status >= 500) {
                toast.error(`Server Error (${res.status}): ${data.detail || 'Unknown error'}`);
            }
        }

        return { ok: res.ok, status: res.status, data };
    } catch (e) {
        console.error("Network Error:", e);
        if (!silentErrors) {
            toast.error(`Network Error: ${e.message}`);
        }
        return { ok: false, status: 0, data: null };
    }
}

function tryParseJson(txt) {
    try {
        return JSON.parse(txt);
    } catch {
        return txt;
    }
}

export async function fetchText(url, opts = {}) {
    try {
        const nextOpts = { ...opts, headers: buildAuthHeaders(opts.headers) };
        const res = await fetch(url, nextOpts);
        const data = await res.text();
        return { ok: res.ok, status: res.status, data };
    } catch (e) {
        console.error("Network Error (Text):", e);
        return { ok: false, status: 0, data: null };
    }
}
