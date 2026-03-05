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

// --- Initialization ---
async function init() {
    console.log("MYT 控制台初始化中...");
    
    // Setup Navigation
    setupNavigation();
    
    // Initialize Features
    initDevices();
    initLogs();
    initTasks();
    initConfig();
    initAccounts();
    
    // Initial Data Load (some are loaded by their init functions, but global refresh can handle others)
    await loadHealth();
    
    // Setup Global Refresh
    const refreshBtn = $("refreshAll");
    if(refreshBtn) {
        refreshBtn.addEventListener("click", async () => {
             const btn = refreshBtn;
             btn.disabled = true;
             btn.innerHTML = '<span class="loading-spinner"></span> 刷新中';
             try {
                 await Promise.all([
                     loadHealth(),
                     loadDevices(),
                     loadTasks(),
                     loadConfig(),
                     // Accounts usually don't need frequent refresh
                 ]);
                 toast.success("全局刷新完成");
             } catch(e) {
                 toast.error("刷新失败");
             } finally {
                 btn.disabled = false;
                 btn.textContent = "刷新全局";
             }
        });
    }

    toast.info("系统初始化完成");
}

function setupNavigation() {
    document.querySelectorAll('.nav-item').forEach(btn => {
        btn.addEventListener('click', (e) => {
            // UI Update
            document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-pane').forEach(tab => tab.classList.remove('active'));
            
            const currentBtn = e.currentTarget;
            currentBtn.classList.add('active');
            
            const targetId = currentBtn.getAttribute('data-tab');
            const targetPane = document.getElementById(targetId);
            if(targetPane) targetPane.classList.add('active');

            // State Update
            store.setState({ currentTab: targetId });
        });
    });
}

// --- Basic API Calls (will be moved to services) ---
async function loadHealth() {
    const r = await fetchJson("/health");
    const isOk = r.ok;
    store.setState({ apiStatus: isOk });
    updateApiStatusUI(isOk);
}

function updateApiStatusUI(ok) {
    const el = $("apiStatus");
    if(el) {
        el.className = `badge ${ok ? "badge-ok" : "badge-warn"}`;
        el.textContent = ok ? "服务状态：在线" : "服务状态：离线";
    }
}

// Start
document.addEventListener('DOMContentLoaded', init);
