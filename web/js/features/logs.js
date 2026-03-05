import { toast } from '../ui/toast.js';

const logBox = document.getElementById("logBox");
const clearBtn = document.getElementById("clearLogs");

export function initLogs() {
    if (clearBtn) {
        clearBtn.addEventListener("click", () => {
            logBox.textContent = "";
            toast.info("日志已清空");
        });
    }
    connectLogs();
}

function connectLogs() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/logs`);

    ws.onopen = () => {
        appendLog("[日志通道] 已连接");
    };
    ws.onmessage = (e) => {
        appendLog(e.data);
    };
    ws.onclose = () => {
        appendLog("[日志通道] 已断开，正在重连...");
        setTimeout(connectLogs, 1500);
    };
    ws.onerror = (e) => {
        console.error("日志通道错误:", e);
    };
}

function appendLog(msg) {
    if (!logBox) return;
    
    // Performance: Limit lines?
    // For now, just append text content
    // We could optimize by appending elements instead of textContent +=
    // But let's stick to original behavior for now, maybe add a limit check
    
    // Simple line limit
    if (logBox.textContent.length > 50000) {
        logBox.textContent = logBox.textContent.slice(-20000); // Keep last chunk
    }

    logBox.textContent += `${msg}\n`;
    logBox.scrollTop = logBox.scrollHeight;
}
