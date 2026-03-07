// Main Entry Point
import { store } from './state/store.js';
import { toast } from './ui/toast.js';
import { fetchJson } from './utils/api.js';
import { initDevices, loadDevices } from './features/devices.js';
import { initLogs } from './features/logs.js';
import { initTasks, loadTasks } from './features/tasks.js';
import { initConfig, loadConfig } from './features/config.js';
import { initAccounts } from './features/accounts.js';

const $ = (id) => document.getElementById(id);

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
             refreshBtn.disabled = true;
             const oldInner = refreshBtn.innerHTML;
             refreshBtn.innerHTML = '<span class="dot pulse"></span> 正在全局同步...';
             try {
                 await Promise.all([
                     loadHealth(), 
                     loadDevices(), 
                     loadTasks(), 
                     loadConfig(),
                     import('./features/accounts.js').then(m => m.loadAccounts())
                 ]);
                 toast.success("全局数据与状态已同步");
             } catch(e) {
                 toast.error("同步过程中发生异常");
             } finally {
                 refreshBtn.disabled = false;
                 refreshBtn.innerHTML = oldInner;
             }
        };
    }
    toast.info("系统就绪");
}

function setupNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    const panes = document.querySelectorAll('.tab-pane');
    const detailView = document.getElementById('unitDetailView');

    navItems.forEach(btn => {
        btn.addEventListener('click', (e) => {
            const targetId = btn.getAttribute('data-tab');
            if(!targetId) return;

            // 1. 清除所有状态
            navItems.forEach(b => b.classList.remove('active'));
            panes.forEach(p => {
                p.classList.remove('active');
                p.style.display = ''; // 强行清除之前可能存在的内联样式
            });

            // 2. 激活当前
            btn.classList.add('active');
            const targetPane = document.getElementById(targetId);
            if(targetPane) targetPane.classList.add('active');

            // 3. 切换标签时必须关闭详情页
            if(detailView) detailView.style.display = 'none';

            // 4. 更新标题
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
