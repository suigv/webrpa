// Main Entry Point
import { store } from './state/store.js';
import { toast } from './ui/toast.js';
import { fetchJson } from './utils/api.js';
import { initDevices, loadDevices, closeDetail } from './features/devices.js';
import { initLogs } from './features/logs.js';
import { initTasks, loadTasks } from './features/tasks.js';
import { initConfig, loadConfig } from './features/config.js';
import { initAccounts, loadAccounts } from './features/accounts.js';

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

    setupNavigation();

    initDevices();
    initLogs();
    initTasks();
    initConfig();
    initAccounts();

    await loadHealth();

    const refreshBtn = $("refreshAll");
    if(refreshBtn) {
        refreshBtn.onclick = async () => {
             setRefreshButtonLoading(refreshBtn, true);
             try {
                 await Promise.all([
                     loadHealth(),
                     loadDevices(),
                     loadTasks(),
                     loadConfig(),
                     loadAccounts(),
                 ]);
                 toast.success("全局数据与状态已同步");
             } catch(e) {
                 toast.error("同步过程中发生异常");
             } finally {
                 setRefreshButtonLoading(refreshBtn, false);
             }
        };
    }
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
                p.style.display = '';
            });

            btn.classList.add('active');
            const targetPane = document.getElementById(targetId);
            if(targetPane) targetPane.classList.add('active');

            closeDetail(false);

            const titleMap = {
                'tab-main': '仪表盘',
                'tab-tasks': '任务中心',
                'tab-accounts': '账号池',
                'tab-config': '系统设置'
            };
            const viewTitle = document.getElementById('viewTitle');
            if(viewTitle && titleMap[targetId]) {
                viewTitle.textContent = titleMap[targetId];
            }

            store.setState({ currentTab: targetId });
        });
    });
}

async function loadHealth() {
    const r = await fetchJson("/health");
    const ok = r.ok;
    const el = $("apiStatus");
    if(el) {
        el.className = `badge ${ok ? "badge-ok" : "badge-error"}`;
        el.textContent = ok ? "服务在线" : "连接中断";
    }
}

document.addEventListener('DOMContentLoaded', init);
