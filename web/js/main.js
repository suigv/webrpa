// Main Entry Point

import { store } from '/static/js/state/store.js';
import { toast } from '/static/js/ui/toast.js';
import { fetchJson } from '/static/js/utils/api.js';
import { initDevices, loadDevices, closeDetail } from '/static/js/features/devices.js';
import { initLogs } from '/static/js/features/logs.js';
import { initTasks, loadTasks } from '/static/js/features/tasks.js';
import { initConfig, loadConfig } from '/static/js/features/config.js';
import { initAccounts, loadAccounts } from '/static/js/features/accounts.js';
import { initMetrics, loadMetrics } from '/static/js/features/metrics.js';

const $ = (id) => document.getElementById(id);

function setRefreshButtonLoading(refreshBtn, loading) {
    if (!refreshBtn) return;
    if (!loading) {
        refreshBtn.disabled = false;
        refreshBtn.replaceChildren('同步');
        return;
    }

    refreshBtn.disabled = true;
    const dot = document.createElement('span');
    dot.className = 'dot pulse';
    refreshBtn.replaceChildren(dot, document.createTextNode(' 正在全局同步...'));
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
        { name: "Logs", fn: initLogs },
        { name: "Tasks", fn: initTasks },
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

            navItems.forEach(b => b.classList.remove('active'));
            panes.forEach(p => {
                p.classList.remove('active');
                p.style.display = 'none';
            });

            btn.classList.add('active');
            const targetPane = document.getElementById(targetId);
            if(targetPane) {
                targetPane.classList.add('active');
                targetPane.style.display = 'block';
            }

            closeDetail(false);
        });
    });
}

async function loadHealth() {
    try {
        const r = await fetchJson("/health", { silentErrors: true });
        if (r.ok && r.data) {
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
                } else {
                    rpcEl.className = "status-badge status-warn";
                    rpcEl.innerHTML = '<span class="dot"></span> RPC 已禁用';
                }
            }
        }
    } catch (e) {}
}

document.addEventListener('DOMContentLoaded', init);
