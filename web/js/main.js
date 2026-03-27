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
        title: "指挥台",
        subtitle: "先看节点态势，再进入任务设计、执行队列与异常接管。",
    },
    "tab-ai": {
        title: "任务设计",
        subtitle: "围绕目标、资源、接管与成功出口完成任务图设计。",
    },
    "tab-tasks": {
        title: "执行队列",
        subtitle: "绑定目标节点、设置调度策略，并持续观察运行与异常状态。",
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

function setRuntimeMode(text) {
    const runtimeEl = $("heroRuntimeMode");
    const commandRuntimeEl = $("commandRuntimeMode");
    if (runtimeEl) runtimeEl.textContent = text;
    if (commandRuntimeEl) commandRuntimeEl.textContent = text;
}

function renderHealthUnavailable() {
    const apiEl = $("apiStatus");
    if (apiEl) {
        apiEl.className = "status-badge status-warning";
        apiEl.innerHTML = '<span class="dot"></span> 未连接';
    }

    const rpcEl = $("rpcStatus");
    if (rpcEl) {
        rpcEl.className = "status-badge status-warning";
        rpcEl.innerHTML = '<span class="dot"></span> 状态未知';
    }

    setRuntimeMode("后端不可达");
}

function activateTab(targetId) {
    if (!targetId) return;
    const navItems = document.querySelectorAll('.nav-item');
    const panes = document.querySelectorAll('.tab-pane');

    navItems.forEach((b) => {
        b.classList.toggle('active', b.getAttribute('data-tab') === targetId);
    });
    panes.forEach((p) => {
        const isActive = p.id === targetId;
        p.classList.toggle('active', isActive);
        p.style.display = isActive ? 'block' : 'none';
    });

    setViewMeta(targetId);
    closeDetail(false);
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

    navItems.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetId = btn.getAttribute('data-tab');
            activateTab(targetId);
        });
    });

    document.addEventListener('click', (event) => {
        const trigger = event.target instanceof Element ? event.target.closest('[data-nav-target]') : null;
        if (!trigger) return;
        const targetId = trigger.getAttribute('data-nav-target');
        if (!targetId) return;
        activateTab(targetId);
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
        if (rpcEl) {
            if (r.data.rpc_enabled) {
                rpcEl.className = "status-badge status-ok";
                rpcEl.innerHTML = '<span class="dot"></span> RPC 已启用';
                setRuntimeMode("API + RPC 双通道");
            } else {
                rpcEl.className = "status-badge status-warning";
                rpcEl.innerHTML = '<span class="dot"></span> RPC 已禁用';
                setRuntimeMode("纯 Web 兼容路径");
            }
        }
    } catch (e) {
        console.warn("Health check failed:", e);
        renderHealthUnavailable();
    }
}

document.addEventListener('DOMContentLoaded', init);
