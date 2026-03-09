import { fetchJson } from '../utils/api.js';
import { toast } from '../ui/toast.js';
import { renderCommonFields } from '../utils/ui_utils.js';
import { getTaskCatalog, apiSubmitTask, buildTaskRequest, collectTaskPayload } from './task_service.js';

const $ = (id) => document.getElementById(id);

let pluginCatalog = [];
let selectedTaskName = '';

function clearElement(element) {
    if (element) {
        element.replaceChildren();
    }
}

function formatTargetText(targets) {
    return Array.isArray(targets) && targets.length
        ? targets.map(target => `#${target.device_id}-${target.cloud_id}`).join(', ')
        : '未指定目标';
}

function createInfoRow(labelText, valueText) {
    const row = document.createElement('div');
    row.className = 'info-row';

    const label = document.createElement('span');
    label.className = 'info-label';
    label.textContent = labelText;

    const value = document.createElement('span');
    value.className = 'info-value';
    value.textContent = valueText;

    row.append(label, value);
    return row;
}

function resolveTargetsFromForm() {
    const deviceValue = ($('targetDeviceId')?.value || '').trim();
    const cloudValue = ($('targetCloudId')?.value || '').trim();

    if (!deviceValue && !cloudValue) {
        toast.warn('请明确填写设备 ID 和云机 ID');
        return { ok: false };
    }

    if (!deviceValue || !cloudValue) {
        toast.warn('设备 ID 和云机 ID 需要同时填写');
        return { ok: false };
    }

    const deviceId = Number(deviceValue);
    const cloudId = Number(cloudValue);
    if (!Number.isInteger(deviceId) || deviceId < 1 || !Number.isInteger(cloudId) || cloudId < 1) {
        toast.warn('目标设备参数必须是大于 0 的整数');
        return { ok: false };
    }

    return {
        ok: true,
        targets: [{ device_id: deviceId, cloud_id: cloudId }],
    };
}

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
    if (!confirm('此操作会清空托管任务状态与事件流水，运行中的任务不会被清空，是否继续？')) return;
    const btn = $('clearTasks');
    if (btn) btn.disabled = true;
    try {
        const r = await fetchJson('/api/tasks/', { method: 'DELETE', silentErrors: true });
        if (r.ok) {
            toast.success('托管任务状态已清空');
            clearElement($('tasksList'));
            await loadTasks();
            return;
        }
        toast.error(r.data?.detail || '清空托管任务状态失败');
    } finally { if (btn) btn.disabled = false; }
}

async function initPluginSelector() {
    pluginCatalog = await getTaskCatalog();
    renderPluginSelector();
}

function renderPluginSelector() {
    const host = $('taskPluginHost');
    if (!host) return;
    clearElement(host);
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
    clearElement(list);
    tasks.forEach(t => {
        const item = document.createElement('div');
        item.className = 'list-item';

        const content = document.createElement('div');
        content.className = 'list-item-content';

        const title = document.createElement('span');
        title.className = 'list-item-title';
        title.textContent = t.task_name || t.task || 'anonymous';

        const meta = document.createElement('span');
        meta.className = 'list-item-meta';
        meta.textContent = `ID: ${t.task_id} | ${t.status} | ${formatTargetText(t.targets)} | ${t.created_at}`;

        content.append(title, meta);

        const button = document.createElement('button');
        button.className = 'btn btn-secondary btn-sm';
        button.textContent = '详情';
        button.onclick = () => loadTaskDetail(t.task_id);

        item.append(content, button);
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
        clearElement(body);

        const infoGrid = document.createElement('div');
        infoGrid.className = 'info-grid';
        infoGrid.append(
            createInfoRow('任务 ID', t.task_id),
            createInfoRow('任务名称', t.task_name || t.task || 'anonymous'),
            createInfoRow('当前状态', t.status),
            createInfoRow('目标设备', formatTargetText(t.targets)),
        );
        body.appendChild(infoGrid);

        if (t.result !== undefined) {
            const wrapper = document.createElement('div');
            wrapper.className = 'mt-4';

            const label = document.createElement('div');
            label.className = 'info-label mb-2';
            label.textContent = '执行结果';

            const code = document.createElement('div');
            code.className = 'code-block';
            code.textContent = JSON.stringify(t.result, null, 2);

            wrapper.append(label, code);
            body.appendChild(wrapper);
        }

        if (t.error) {
            const error = document.createElement('div');
            error.className = 'mt-4 p-3 bg-app rounded border border-error text-error text-xs';
            error.textContent = t.error;
            body.appendChild(error);
        }
    }
}

async function submitTask() {
    if (!selectedTaskName) return toast.warn('请选定作业驱动');

    const resolvedTargets = resolveTargetsFromForm();
    if (!resolvedTargets.ok) return;

    const btn = $('submitTask');
    if (btn) btn.disabled = true;

    try {
        const taskData = buildTaskRequest({
            task: selectedTaskName,
            payload: collectTaskPayload($('taskPayloadFields')),
            targets: resolvedTargets.targets,
            priority: $('taskPriority')?.value || 50,
            maxRetries: $('taskMaxRetries')?.value || 0,
            runAt: $('taskRunAt')?.value || null,
        });

        const result = await apiSubmitTask(taskData);
        if (result?.ok) {
            await loadTasks();
        }
    } finally {
        if (btn) btn.disabled = false;
    }
}
