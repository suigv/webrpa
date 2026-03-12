import { toast } from '/static/js/ui/toast.js';

export async function fetchJson(url, opts = {}) {
    const { silentErrors = false, ...fetchOptions } = opts;
    try {
        const res = await fetch(url, fetchOptions);
        const txt = await res.text();
        let data = txt;
        try {
            data = txt ? JSON.parse(txt) : {};
        } catch (_) {}

        if (!res.ok) {
            console.error(`API Error: ${url}`, res.status, data);
            if (!silentErrors && res.status >= 500) {
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

export async function fetchText(url, opts = {}) {
    try {
        const res = await fetch(url, opts);
        const data = await res.text();
        return { ok: res.ok, status: res.status, data };
    } catch (e) {
        console.error("Network Error (Text):", e);
        return { ok: false, status: 0, data: null };
    }
}
