import { store } from '../state/store.js';

const unitLogBox = document.getElementById("unitLogBox");
const globalLogBox = document.getElementById("globalLogBox");

let socket = null;

function clearElement(element) {
    if (element) {
        element.replaceChildren();
    }
}

function appendSegments(container, segments, level = 'info') {
    if (!container) return;
    const line = document.createElement('div');
    segments.forEach(segment => {
        const span = document.createElement('span');
        span.textContent = segment.text;
        if (segment.color) {
            span.style.color = segment.color;
        }
        line.appendChild(span);
    });
    if (level === 'error') {
        line.style.color = 'var(--error)';
    }
    container.appendChild(line);
    container.scrollTop = container.scrollHeight;
}

export function sysLog(msg, level = "info") {
    if (!globalLogBox) return;
    const ts = new Date().toLocaleTimeString();
    appendSegments(globalLogBox, [
        { text: `[${ts}] `, color: 'var(--text-muted)' },
        { text: '[SYS] ', color: 'var(--info)' },
        { text: String(msg ?? '') },
    ], level);
}

export function initLogs() {
    connectLogs();

    const clearLogBtn = document.getElementById('clearGlobalLogBtn');
    if (clearLogBtn) {
        clearLogBtn.onclick = () => clearElement(globalLogBox);
    }

    // 允许通过控制台开启全局调试日志
    window.showDebug = () => {
        if(globalLogBox) globalLogBox.style.display = "block";
    };
}

function connectLogs() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const host = location.host;
    if (!host) return; // For local file testing
    const wsUrl = `${proto}://${host}/ws/logs`;
    socket = new WebSocket(wsUrl);

    socket.onmessage = (e) => {
        try {
            const log = JSON.parse(e.data);
            appendDetailedLog(log);
        } catch (err) {
            appendRawLog(e.data);
        }
    };

    socket.onclose = () => setTimeout(connectLogs, 2000);
}

function appendDetailedLog(log) {
    const ts = log.timestamp || "";
    const target = log.target || "SYS";
    const msg = log.message || "";
    const level = log.level || "info";

    if (globalLogBox) {
        const debugLine = document.createElement("div");
        debugLine.textContent = `[${ts}] [${target}] ${msg}`;
        if (level === "error") debugLine.style.color = "#f87171";
        globalLogBox.appendChild(debugLine);
        if (globalLogBox.children.length > 200) globalLogBox.removeChild(globalLogBox.firstChild);
        globalLogBox.scrollTop = globalLogBox.scrollHeight;
    }

    const currentUnitLogTarget = store.getState().currentUnitLogTarget;
    if (unitLogBox && currentUnitLogTarget && currentUnitLogTarget === target) {
        appendSegments(unitLogBox, [
            { text: `${ts} `, color: 'var(--text-muted)' },
            { text: String(msg ?? ''), color: 'var(--primary)' },
        ], level);
        if (unitLogBox.children.length > 200) unitLogBox.removeChild(unitLogBox.firstChild);
    }
}

function appendRawLog(data) {
    if (globalLogBox) {
        const line = document.createElement("div");
        line.textContent = data;
        globalLogBox.appendChild(line);
    }
}
