import { toast } from '../ui/toast.js';

const unitLogBox = document.getElementById("unitLogBox");
const globalLogBox = document.getElementById("globalLogBox");

let socket = null;

export function sysLog(msg, level = "info") {
    if (!globalLogBox) return;
    const ts = new Date().toLocaleTimeString();
    const line = document.createElement("div");
    line.innerHTML = `<span style="color:var(--text-muted)">[${ts}]</span> <span style="color:var(--info)">[SYS]</span> ${msg}`;
    if (level === "error") line.style.color = "var(--error)";
    globalLogBox.appendChild(line);
    globalLogBox.scrollTop = globalLogBox.scrollHeight;
}

export function initLogs() {
    connectLogs();
    
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

    const viewTitle = document.getElementById("viewTitle");
    if (unitLogBox && viewTitle && viewTitle.textContent.includes(target)) {
        const line = document.createElement("div");
        line.style.marginBottom = "4px";
        line.innerHTML = `<span style="color:var(--text-muted)">${ts}</span> <span style="color:var(--primary)">${msg}</span>`;
        unitLogBox.appendChild(line);
        unitLogBox.scrollTop = unitLogBox.scrollHeight;
    }
}

function appendRawLog(data) {
    if (globalLogBox) {
        const line = document.createElement("div");
        line.textContent = data;
        globalLogBox.appendChild(line);
    }
}
