// Main Entry Point

import './diag.js';

import { toast } from './ui/toast.js';
import { fetchJson } from './utils/api.js';
import { initDevices, closeDetail } from './features/devices.js';
import { initAiWorkspace } from './features/ai_workspace.js';
import { initLogs } from './features/logs.js';
import { initTasks } from './features/tasks.js';
import { initDrafts } from './features/drafts.js';
import { initConfig } from './features/config.js';
import { initAccounts } from './features/accounts.js';
import { initMetrics } from './features/metrics.js';

const $ = (id) => document.getElementById(id);
const TAB_META = {
    "tab-main": {
        title: "设备集群",
        subtitle: "实时监控设备状态、执行占用与节点级控制动作。",
    },
    "tab-ai": {
        title: "AI 工作台",
        subtitle: "统一查看 AI 设计、草稿沉淀、执行协作与复用洞察。",
    },
    "tab-tasks": {
        title: "任务队列",
        subtitle: "围绕插件白名单构建任务，并持续观察执行流水。",
    },
    "tab-accounts": {
        title: "资源仓库",
        subtitle: "统一维护账号资产、库存状态与批量分发策略。",
    },
    "tab-config": {
        title: "系统偏好",
        subtitle: "调整网络扫描、鉴权令牌与行为拟真策略。",
    },
};

function setViewMeta(tabId) {
    const meta = TAB_META[tabId] || TAB_META["tab-main"];
    const titleEl = $("viewTitle");
    const subtitleEl = $("viewSubtitle");
    if (titleEl) titleEl.textContent = meta.title;
    if (subtitleEl) subtitleEl.textContent = meta.subtitle;
}

function renderHealthUnavailable() {
    const apiEl = $("apiStatus");
    if (apiEl) {
        apiEl.className = "status-badge status-warn";
        apiEl.innerHTML = '<span class="dot"></span> 未连接';
    }

    const rpcEl = $("rpcStatus");
    if (rpcEl) {
        rpcEl.className = "status-badge status-warn";
        rpcEl.innerHTML = '<span class="dot"></span> 状态未知';
    }

    const runtimeEl = $("heroRuntimeMode");
    if (runtimeEl) runtimeEl.textContent = "后端不可达";
}

async function init() {
    console.log("WebRPA 控制中心启动...");

    // 1. 基础导航初始化
    try {
        setupNavigation();
    } catch (e) {
        console.error("Navigation init failed:", e);
    }

    // 2. 各功能模块初始化
    const modules = [
        { name: "Devices", fn: initDevices },
        { name: "AIWorkspace", fn: initAiWorkspace },
        { name: "Logs", fn: initLogs },
        { name: "Tasks", fn: initTasks },
        { name: "Drafts", fn: initDrafts },
        { name: "Config", fn: initConfig },
        { name: "Accounts", fn: initAccounts },
        { name: "Metrics", fn: initMetrics }
    ];

    for (const mod of modules) {
        try {
            mod.fn();
        } catch (e) {
            console.warn(`Module [${mod.name}] init failed:`, e);
        }
    }

    loadHealth();
    toast.info("系统就绪");
}

function setupNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    const panes = document.querySelectorAll('.tab-pane');

    navItems.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetId = btn.getAttribute('data-tab');
            if(!targetId) return;

            navItems.forEach((b) => {
                b.classList.remove('active');
            });
            panes.forEach((p) => {
                p.classList.remove('active');
                p.style.display = 'none';
            });

            btn.classList.add('active');
            const targetPane = document.getElementById(targetId);
            if(targetPane) {
                targetPane.classList.add('active');
                targetPane.style.display = 'block';
            }

            setViewMeta(targetId);
            closeDetail(false);
        });
    });

    const active = document.querySelector('.nav-item.active');
    setViewMeta(active?.getAttribute('data-tab') || 'tab-main');
}

async function loadHealth() {
    try {
        const r = await fetchJson("/health", { silentErrors: true });
        if (!r.ok || !r.data) {
            renderHealthUnavailable();
            return;
        }

        const apiEl = $("apiStatus");
        if (apiEl) {
            apiEl.className = "status-badge status-ok";
            apiEl.innerHTML = '<span class="dot"></span> 已连接';
        }
        const rpcEl = $("rpcStatus");
        const runtimeEl = $("heroRuntimeMode");
        if (rpcEl) {
            if (r.data.rpc_enabled) {
                rpcEl.className = "status-badge status-ok";
                rpcEl.innerHTML = '<span class="dot"></span> RPC 已启用';
                if (runtimeEl) runtimeEl.textContent = "API + RPC 双通道";
            } else {
                rpcEl.className = "status-badge status-warn";
                rpcEl.innerHTML = '<span class="dot"></span> RPC 已禁用';
                if (runtimeEl) runtimeEl.textContent = "纯 Web 兼容路径";
            }
        }
    } catch (e) {
        console.warn("Health check failed:", e);
        renderHealthUnavailable();
    }
}

document.addEventListener('DOMContentLoaded', init);
