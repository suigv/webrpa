import { toast } from '../ui/toast.js';

export async function fetchJson(url, opts = {}) {
    try {
        const res = await fetch(url, opts);
        const txt = await res.text();
        let data = txt;
        try {
            data = txt ? JSON.parse(txt) : {};
        } catch (_) {}

        if (!res.ok) {
            console.error(`API Error: ${url}`, res.status, data);
            // Optionally show toast for critical errors (500)
            if (res.status >= 500) {
                toast.error(`Server Error (${res.status}): ${data.detail || 'Unknown error'}`);
            }
        }

        return { ok: res.ok, status: res.status, data };
    } catch (e) {
        console.error("Network Error:", e);
        toast.error(`Network Error: ${e.message}`);
        return { ok: false, status: 0, data: null };
    }
}
