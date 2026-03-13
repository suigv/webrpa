import { store } from '/static/js/state/store.js';

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

/**
 * 向当前单机接管视图插入即时日志
 */
export function unitLog(msg, level = "info") {
    if (!unitLogBox) return;
    const ts = new Date().toLocaleTimeString();
    appendSegments(unitLogBox, [
        { text: `${ts} `, color: 'var(--text-muted)' },
        { text: String(msg ?? ''), color: 'var(--primary)' },
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
    const eventType = log.event_type;
    const now = new Date();
    const ts = now.getHours().toString().padStart(2, '0') + ':' + 
               now.getMinutes().toString().padStart(2, '0') + ':' + 
               now.getSeconds().toString().padStart(2, '0');

    const data = log.data || {};
    const target = log.target || "SYS";
    const msg = log.message || "";
    const level = log.level || "info";

    // --- 核心修复：绝对互斥逻辑 ---
    
    // 情况 A0：观察事件
    if (eventType === "task.observation") {
        if (unitLogBox && store.getState().currentUnitLogTarget) {
            const step = data.step || "?";
            const modality = data.modality || "unknown";
            const stateIds = Array.isArray(data.observed_state_ids) && data.observed_state_ids.length
                ? data.observed_state_ids.join(", ")
                : (data.ok ? "已识别" : "未识别");
            appendSegments(unitLogBox, [
                { text: `${ts} `, color: 'var(--text-muted)' },
                { text: `[步骤 ${step}] 观察: ${stateIds}`, color: 'var(--text-muted)' },
                { text: ` (${modality})`, color: '#555' },
            ]);
        }
        return;
    }

    // 情况 A1：规划事件
    if (eventType === "task.planning") {
        if (unitLogBox && store.getState().currentUnitLogTarget) {
            const step = data.step || "?";
            const action = data.action || "?";
            const params = data.params || {};
            const paramStr = Object.entries(params).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ");
            appendSegments(unitLogBox, [
                { text: `${ts} `, color: 'var(--text-muted)' },
                { text: `[步骤 ${step}] AI决策: `, color: 'var(--info)' },
                { text: `${action}(${paramStr})`, color: 'var(--primary)' },
            ]);
        }
        return;
    }

    // 情况 A：这是结构化的任务步骤结果
    if (eventType === "task.action_result") {
        if (unitLogBox) {
            const stepNum = data.step || "?";
            const label = data.label || "未知动作";
            const isOk = data.ok;
            
            // 统一使用最直观的 [步骤 X] 格式
            const mainMsg = `[步骤 ${stepNum}] ${label}: ${isOk ? '✅ 成功' : '❌ 失败'}`;
            const errorMsg = isOk ? "" : ` (${data.message || '未知错误'})`;
            
            appendSegments(unitLogBox, [
                { text: `${ts} `, color: 'var(--text-muted)' },
                { text: mainMsg, color: isOk ? 'var(--success)' : 'var(--error)' },
                { text: errorMsg, color: '#666' }
            ]);
        }
        return; // 强制截断，绝不向下执行
    }

    // 情况 B1：任务终态事件（task.failed / task.completed / task.dispatch_result / task.retry_scheduled）
    // 这些事件没有 target 字段，但需要显示在当前打开的云机日志窗口中
    const terminalEvents = new Set(["task.failed", "task.completed", "task.dispatch_result", "task.retry_scheduled", "task.cancelled"]);
    if (terminalEvents.has(eventType) && unitLogBox && store.getState().currentUnitLogTarget) {
        const isOk = eventType === "task.completed";
        const status = data.status || eventType.replace("task.", "");
        const error = data.error || "";
        const mainMsg = `[${status}]${error ? ': ' + error : ''}`;
        appendSegments(unitLogBox, [
            { text: `${ts} `, color: 'var(--text-muted)' },
            { text: mainMsg, color: isOk ? 'var(--success)' : 'var(--error)' },
        ]);
        unitLogBox.scrollTop = unitLogBox.scrollHeight;
        return;
    }

    // 情况 B：普通文本日志（如：业务已启动、同步环境等）
    if (msg) {
        // 如果后端发出了冗余的包含 event_type 的字符串日志，直接丢弃
        if (msg.includes("[task.action_result]")) return;
        const debugLine = document.createElement("div");
        debugLine.style.fontSize = "0.75rem";
        debugLine.innerHTML = `<span style="color:var(--text-muted)">[${ts}]</span> <span style="color:var(--info)">[${target}]</span> ${msg}`;
        if (level === "error") debugLine.style.color = "var(--error)";
        globalLogBox.appendChild(debugLine);
        if (globalLogBox.children.length > 300) globalLogBox.removeChild(globalLogBox.firstChild);
        globalLogBox.scrollTop = globalLogBox.scrollHeight;
    }

    // 将不属于任务步骤的系统反馈也显示在云机窗口中
    const currentUnitLogTarget = store.getState().currentUnitLogTarget;
    if (unitLogBox && currentUnitLogTarget && currentUnitLogTarget === target) {
        appendSegments(unitLogBox, [
            { text: `${ts} `, color: 'var(--text-muted)' },
            { text: String(msg), color: 'var(--primary)' },
        ], level);
    }
}

function appendRawLog(data) {
    if (globalLogBox) {
        const line = document.createElement("div");
        line.textContent = data;
        globalLogBox.appendChild(line);
    }
}
