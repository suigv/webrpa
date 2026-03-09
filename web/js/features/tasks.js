import { fetchJson } from '../utils/api.js';
import { toast } from '../ui/toast.js';
import { renderCommonFields } from '../utils/ui_utils.js';
import { getTaskCatalog, apiSubmitTask } from './task_service.js';

const $ = (id) => document.getElementById(id);

let pluginCatalog = [];
let selectedTaskName = '';

export function initTasks() {
    const submitBtn = $('submitTask');
    const refreshBtn = $('refreshTasks');
    const clearBtn = $('clearTasks');

    if (submitBtn) submitBtn.onclick = submitTask;
    if (refreshBtn) refreshBtn.onclick = loadTasks;
    if (clearBtn) clearBtn.onclick = clearAllTasks;
    
    const toggleBtn = $('toggleTasksAdvancedBtn');
    if (toggleBtn) {
        toggleBtn.onclick = () => {
            const el = $('tasksAdvanced');
            if (el) el.style.display = (el.style.display === 'block') ? 'none' : 'block';
        };
    }

    const clearLogBtn = $('clearGlobalLogBtn');
    if (clearLogBtn) {
        clearLogBtn.onclick = () => {
            const el = $('globalLogBox');
            if (el) el.innerHTML = '';
        };
    }

    document.querySelectorAll('.close-task-modal-btn').forEach(btn => {
        btn.onclick = closeTaskModal;
    });
    
    initPluginSelector();
    loadTasks();
}

const closeTaskModal = () => {
    const modal = $('taskModal');
    if (modal) modal.style.display = 'none';
};

async function clearAllTasks() {
    if (!confirm('此操作将永久清空所有历史流水记录，是否继续？')) return;
    const btn = $('clearTasks');
    if (btn) btn.disabled = true;
    try {
        const r = await fetchJson('/api/tasks/', { method: 'DELETE' });
        if (r.ok) {
            toast.success('执行流水已安全归零');
            const list = $('tasksList');
            if(list) list.innerHTML = ''; 
            await loadTasks(); 
        }
    } catch (e) { toast.error('清空指令被拒绝'); }
    finally { if (btn) btn.disabled = false; }
}

async function initPluginSelector() {
    pluginCatalog = await getTaskCatalog();
    renderPluginSelector();
}

function renderPluginSelector() {
    const host = $('taskPluginHost');
    if (!host) return;
    host.innerHTML = '';
    pluginCatalog.forEach(p => {
        const btn = document.createElement('div');
        btn.className = 'plugin-item';
        if (selectedTaskName === p.task) btn.classList.add('selected');
        btn.textContent = p.display_name || p.task;
        btn.onclick = () => {
            selectedTaskName = p.task;
            renderPluginSelector();
            renderFields();
        };
        host.appendChild(btn);
    });
}

function renderFields() {
    const p = pluginCatalog.find(x => x.task === selectedTaskName);
    const container = $('taskPayloadFields');
    renderCommonFields(container, p, false);
    
    const showMoreFields = $('showMoreFields');
    if (showMoreFields && container) {
        showMoreFields.onclick = () => {
            const fields = container.querySelectorAll('.field-optional');
            const isHidden = fields[0]?.style.display === 'none';
            fields.forEach(el => el.style.display = isHidden ? 'flex' : 'none');
            showMoreFields.textContent = isHidden ? '收起可选参数' : '显示高级参数';
        };
    }
}

export async function loadTasks() {
    const r = await fetchJson('/api/tasks/');
    if (r.ok) renderTasksList(r.data);
}

function renderTasksList(tasks) {
    const list = $('tasksList');
    if (!list) return;
    list.innerHTML = '';
    tasks.forEach(t => {
        const item = document.createElement('div');
        item.className = 'list-item';
        item.innerHTML = `
            <div class="list-item-content">
                <span class="list-item-title">${t.display_name || t.task}</span>
                <span class="list-item-meta">ID: ${t.task_id} | ${t.status} | ${t.created_at}</span>
            </div>
            <button class="btn btn-secondary btn-sm">详情</button>
        `;
        item.querySelector('button').onclick = () => loadTaskDetail(t.task_id);
        list.appendChild(item);
    });
}

async function loadTaskDetail(taskId) {
    const r = await fetchJson(`/api/tasks/${taskId}`);
    if (!r.ok) return;
    const t = r.data;
    const modal = $('taskModal');
    const body = $('taskDetailBody');
    if (modal) modal.style.display = 'flex';
    if (body) {
        body.innerHTML = `
            <div class="info-grid">
                <div class="info-row"><span class="info-label">任务 ID</span><span class="info-value">${t.task_id}</span></div>
                <div class="info-row"><span class="info-label">当前状态</span><span class="info-value">${t.status}</span></div>
                <div class="info-row"><span class="info-label">目标设备</span><span class="info-value">#${t.targets?.[0]?.device_id || '?'}-${t.targets?.[0]?.cloud_id || '?'}</span></div>
            </div>
            <div class="code-block">${JSON.stringify(t.payload, null, 2)}</div>
            ${t.message ? `<div class="mt-4 p-3 bg-app rounded border border-error text-error text-xs">${t.message}</div>` : ''}
        `;
    }
}

async function submitTask() {
    if (!selectedTaskName) return toast.warn('请选定作业驱动');
    const btn = $('submitTask');
    if (btn) btn.disabled = true;
    
    const p = {};
    const container = $('taskPayloadFields');
    if(container) {
        container.querySelectorAll('input').forEach(i => { p[i.dataset.payloadKey] = i.value; });
    }
    
    const taskData = {
        task: selectedTaskName,
        payload: p,
        priority: Number($('taskPriority')?.value || 50),
        max_retries: Number($('taskMaxRetries')?.value || 0),
        run_at: $('taskRunAt')?.value || null
    };
    
    const success = await apiSubmitTask(taskData);
    if (success) loadTasks();
    if (btn) btn.disabled = false;
}
