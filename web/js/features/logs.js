import { toast } from '../ui/toast.js';

const unitLogBox = document.getElementById("unitLogBox");
const globalDebugLog = document.getElementById("globalDebugLog");

let socket = null;

export function initLogs() {
    connectLogs();
    
    // 允许通过控制台开启全局调试日志
    window.showDebug = () => globalDebugLog.style.display = "block";
}

function connectLogs() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const wsUrl = `${proto}://${location.host}/ws/logs`;
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

    // 1. 全局调试框 (极简单行)
    const debugLine = document.createElement("div");
    debugLine.textContent = `[${ts}] [${target}] ${msg}`;
    if (level === "error") debugLine.style.color = "#f87171";
    globalDebugLog.appendChild(debugLine);
    if (globalDebugLog.children.length > 200) globalDebugLog.removeChild(globalDebugLog.firstChild);
    globalDebugLog.scrollTop = globalDebugLog.scrollHeight;

    // 2. 详情页日志 (仅显示当前正在看的那台机器)
    const currentViewTitle = document.getElementById("viewTitle").textContent;
    if (currentViewTitle.includes(target)) {
        const line = document.createElement("div");
        line.style.marginBottom = "4px";
        line.innerHTML = `<span style="color:var(--text-muted)">${ts}</span> <span style="color:var(--primary)">${msg}</span>`;
        unitLogBox.appendChild(line);
        unitLogBox.scrollTop = unitLogBox.scrollHeight;
    }
}

function appendRawLog(data) {
    const line = document.createElement("div");
    line.textContent = data;
    globalDebugLog.appendChild(line);
}
