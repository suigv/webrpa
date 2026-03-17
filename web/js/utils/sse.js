import { authFetch } from './api.js';

function defaultOnError(err) {
    console.warn('SSE error', err);
}

export class FetchSseClient {
    constructor(url, handlers = {}) {
        this.url = url;
        this.handlers = handlers;
        this.abortController = new AbortController();
        this.closed = false;
        this._run();
    }

    close() {
        if (this.closed) return;
        this.closed = true;
        try {
            this.abortController.abort();
        } catch {
            // ignore
        }
    }

    async _run() {
        const onOpen = this.handlers.onOpen;
        const onEvent = this.handlers.onEvent;
        const onError = this.handlers.onError || defaultOnError;

        try {
            const res = await authFetch(this.url, {
                method: 'GET',
                headers: { 'Accept': 'text/event-stream' },
                signal: this.abortController.signal,
            });
            if (!res.ok) {
                const txt = await res.text().catch(() => '');
                throw new Error(`HTTP ${res.status} ${txt || ''}`.trim());
            }
            if (typeof onOpen === 'function') onOpen();

            if (!res.body) {
                throw new Error('missing response body');
            }

            const reader = res.body.getReader();
            const decoder = new TextDecoder('utf-8');

            let buf = '';
            let eventName = '';
            let dataLines = [];

            const dispatch = () => {
                if (!eventName && dataLines.length === 0) return;
                const payload = dataLines.join('\n');
                const name = eventName || 'message';
                eventName = '';
                dataLines = [];
                if (typeof onEvent === 'function') onEvent(name, payload);
            };

            while (!this.closed) {
                const { value, done } = await reader.read();
                if (done) break;
                buf += decoder.decode(value, { stream: true });
                const lines = buf.split(/\r?\n/);
                buf = lines.pop() || '';

                for (const line of lines) {
                    if (!line) {
                        dispatch();
                        continue;
                    }
                    if (line.startsWith(':')) {
                        // comment / keep-alive
                        continue;
                    }
                    if (line.startsWith('event:')) {
                        eventName = line.slice(6).trim();
                        continue;
                    }
                    if (line.startsWith('data:')) {
                        dataLines.push(line.slice(5).trimStart());
                        continue;
                    }
                    // ignore other fields like id:, retry:
                }
            }
        } catch (err) {
            if (!this.closed) onError(err);
        }
    }
}

