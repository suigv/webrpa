import { fetchJson } from '../utils/api.js';
import { toast } from '../ui/toast.js';
import { renderCommonFields } from '../utils/ui_utils.js';
import {
    getTaskCatalog,
    apiSubmitTask,
    buildTaskRequest,
    collectTaskPayload,
    sanitizePayloadForTask,
} from './task_service.js';
import { FetchSseClient } from '../utils/sse.js';

const $ = (id) => document.getElementById(id);

let pluginCatalog = [];
let selectedTaskName = '';
let currentEventStream = null;
let taskSubmissionListenerBound = false;

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
    row.style.cssText = 'margin-bottom: 12px;';

    const label = document.createElement('div');
    label.className = 'text-xs text-muted mb-1';
    label.textContent = labelText;

    const value = document.createElement('div');
    value.className = 'text-sm font-medium break-all';
    value.textContent = valueText;

    row.append(label, value);
    return row;
}

const closeTaskModal = () => {
    const modal = $('taskModal');
    if (modal) modal.style.display = 'none';
    if (currentEventStream) {
        currentEventStream.close();
        currentEventStream = null;
    }
};

function updateTaskModalStatus(status) {
    const badge = $('taskModalStatusBadge');
    if (!badge) return;
    const normalized = String(status || 'pending').toLowerCase();
    const variant = normalized === 'completed'
        ? 'ok'
        : (normalized === 'failed' || normalized === 'cancelled' ? 'warn' : 'default');
    badge.className = `badge badge-${variant}`;
    badge.textContent = normalized.toUpperCase();
}

function createSummaryCard(title, text, badgeText = '', badgeVariant = 'default') {
    const card = document.createElement('div');
    card.className = 'task-summary-card';

    const header = document.createElement('div');
    header.className = 'task-summary-target-header';

    const titleEl = document.createElement('div');
    titleEl.className = 'task-summary-title';
    titleEl.textContent = title;
    header.appendChild(titleEl);

    if (badgeText) {
        const badge = document.createElement('span');
        badge.className = `badge badge-${badgeVariant}`;
        badge.textContent = badgeText;
        header.appendChild(badge);
    }

    const body = document.createElement('div');
    body.className = 'task-summary-text';
    body.textContent = text;
    card.append(header, body);
    return card;
}

function normalizeTargetResults(task) {
    const rawTargets = Array.isArray(task?.result?.targets) ? task.result.targets : [];
    return rawTargets.map((entry) => {
        const target = entry?.target || {};
        const result = entry?.result || {};
        const ok = Boolean(result?.ok);
        const label = `#${target.device_id ?? '?'}-${target.cloud_id ?? '?'}`;
        const message = String(
            result?.message || result?.error || result?.status || task?.error || '未返回详细信息'
        );
        return { label, ok, message };
    });
}

function buildTaskSummary(task) {
    const targetResults = normalizeTargetResults(task);
    const successCount = targetResults.filter(item => item.ok).length;
    const failureCount = targetResults.length - successCount;

    if (task.status === 'completed') {
        if (targetResults.length > 0) {
            return {
                title: '执行完成',
                badgeText: `${successCount}/${targetResults.length} 成功`,
                badgeVariant: failureCount === 0 ? 'ok' : 'warn',
                text: failureCount === 0
                    ? '全部目标节点已经完成执行，结果已归档。'
                    : `执行已结束，其中 ${failureCount} 个目标返回异常。`,
            };
        }
        return {
            title: '执行完成',
            badgeText: '成功',
            badgeVariant: 'ok',
            text: '任务已执行完成，未返回目标级明细。',
        };
    }
    if (task.status === 'failed') {
        return {
            title: '执行失败',
            badgeText: '失败',
            badgeVariant: 'warn',
            text: String(task.error || '任务执行失败，请查看下方轨迹和错误信息。'),
        };
    }
    if (task.status === 'cancelled') {
        return {
            title: '任务已取消',
            badgeText: '已取消',
            badgeVariant: 'warn',
            text: String(task.error || '任务被人工停止或系统取消。'),
        };
    }
    return {
        title: '执行中',
        badgeText: '进行中',
        badgeVariant: 'default',
        text: '任务正在执行，完成后这里会自动生成总结报告。',
    };
}

function renderTaskSummary(task) {
    const host = $('taskSummaryContent');
    if (!host) return;
    clearElement(host);

    const summary = buildTaskSummary(task);
    host.appendChild(
        createSummaryCard(summary.title, summary.text, summary.badgeText, summary.badgeVariant)
    );

    if (task.workflow_draft?.message) {
        host.appendChild(
            createSummaryCard('蒸馏状态', String(task.workflow_draft.message))
        );
    }

    const targetResults = normalizeTargetResults(task);
    if (targetResults.length > 0) {
        const wrapper = document.createElement('div');
        wrapper.className = 'task-summary-list';
        targetResults.forEach((item) => {
            const row = document.createElement('div');
            row.className = 'task-summary-target';

            const header = document.createElement('div');
            header.className = 'task-summary-target-header';

            const label = document.createElement('div');
            label.className = 'task-summary-target-label';
            label.textContent = item.label;

            const badge = document.createElement('span');
            badge.className = `badge badge-${item.ok ? 'ok' : 'warn'}`;
            badge.textContent = item.ok ? '成功' : '异常';

            const message = document.createElement('div');
            message.className = 'task-summary-target-message';
            message.textContent = item.message;

            header.append(label, badge);
            row.append(header, message);
            wrapper.appendChild(row);
        });
        host.appendChild(wrapper);
    }
}

function renderTaskSnapshot(task) {
    let finalName = task.display_name;
    if (!finalName && pluginCatalog.length > 0) {
        const matched = pluginCatalog.find(p => p.task === task.task_name);
        if (matched) finalName = matched.display_name;
    }

    const title = $('taskModalTitle');
    if (title) {
        title.textContent = finalName
            ? `任务追踪 - ${finalName}`
            : '任务追踪';
    }

    const infoBox = $('taskInfoContent');
    clearElement(infoBox);
    infoBox.append(
        createInfoRow('任务 ID', task.task_id),
        createInfoRow('驱动程序', finalName || task.task_name || '未知插件'),
        createInfoRow('指派节点', formatTargetText(task.targets)),
        createInfoRow('开始时间', task.started_at || '-'),
        createInfoRow('结束时间', task.finished_at || '-')
    );

    updateTaskModalStatus(task.status);
    renderTaskSummary(task);

    const cancelBtn = $('taskCancelBtn');
    if (cancelBtn) {
        cancelBtn.disabled = !['pending', 'running'].includes(task.status);
        cancelBtn.onclick = () => cancelTask(task.task_id);
    }
}

async function refreshTaskSnapshot(taskId) {
    const r = await fetchJson(`/api/tasks/${taskId}`);
    if (!r.ok) return null;
    renderTaskSnapshot(r.data);
    return r.data;
}

function handleTaskSubmitted(event) {
    const taskId = event?.detail?.taskId;
    if (!taskId) return;
    loadTaskDetail(taskId);
}

export function initTasks() {
    const submitBtn = $('submitTask');
    const refreshBtn = $('refreshTasks');
    const clearBtn = $('clearTasks');
    const cleanupFailedBtn = $('cleanupFailedTasks');
    const stopAllBtn = $('stopAllTasks');

    if (submitBtn) submitBtn.onclick = submitTask;
    if (refreshBtn) refreshBtn.onclick = loadTasks;
    if (clearBtn) clearBtn.onclick = clearAllTasks;
    if (cleanupFailedBtn) cleanupFailedBtn.onclick = cleanupFailedTasks;
    if (stopAllBtn) stopAllBtn.onclick = stopAllTasks;

    const refreshTargetsBtn = $('refreshTaskTargets');
    if (refreshTargetsBtn) refreshTargetsBtn.onclick = loadTaskTargets;
    loadTaskTargets();

    document.querySelectorAll('.close-task-modal-btn').forEach(btn => {
        btn.onclick = closeTaskModal;
    });

    if (!taskSubmissionListenerBound) {
        window.addEventListener('webrpa:task-submitted', handleTaskSubmitted);
        taskSubmissionListenerBound = true;
    }

    initAppSelector();
    initPluginSelector();
    loadTasks();
}

async function loadTaskDetail(taskId) {
    const modal = $('taskModal');
    if (modal) modal.style.display = 'flex';
    await refreshTaskSnapshot(taskId);
    startTaskEventStream(taskId);
}

function startTaskEventStream(taskId) {
    if (currentEventStream) currentEventStream.close();

    const timeline = $('taskEventTimeline');
    const statusText = $('eventStreamStatus');
    clearElement(timeline);
    statusText.textContent = '连接中...';

    let streamClosed = false;

    // 监听所有自定义事件
    const eventTypes = [
        'task.created', 'task.started', 'task.completed', 'task.failed', 'task.cancelled', 'task.dispatch_result',
        'interpreter.step_start', 'interpreter.step_result',
        'action.executing', 'action.success', 'action.failed',
        'humanized.click', 'humanized.typing'
    ];

    currentEventStream = new FetchSseClient(`/api/tasks/${taskId}/events`, {
        onOpen: () => {
            statusText.textContent = '🟢 实时同步中';
        },
        onEvent: (type, raw) => {
            if (type === 'message') return;
            if (!eventTypes.includes(type)) return;
            let data;
            try {
                data = raw ? JSON.parse(raw) : {};
            } catch {
                data = { raw };
            }
            appendEventToTimeline(type, data);
            if (['task.completed', 'task.failed', 'task.cancelled'].includes(type)) {
                streamClosed = true;
                statusText.textContent = '🏁 执行结束';
                refreshTaskSnapshot(taskId);
                loadTasks();
            }
        },
        onError: () => {
            if (!streamClosed) statusText.textContent = '⚪ 连接已断开';
        },
    });
}

function appendEventToTimeline(type, data) {
    const timeline = $('taskEventTimeline');
    const line = document.createElement('div');
    line.style.marginBottom = '8px';
    line.style.borderLeft = '2px solid var(--border)';
    line.style.paddingLeft = '8px';

    const timestamp = new Date().toLocaleTimeString();
    const tsSpan = document.createElement('span');
    tsSpan.className = 'text-muted';
    tsSpan.textContent = `[${timestamp}] `;
    line.appendChild(tsSpan);

    const tagSpan = document.createElement('span');
    const msgSpan = document.createElement('span');

    // 根据事件类型定制显示（避免 innerHTML 注入）
    if (type.startsWith('humanized.')) {
        tagSpan.style.color = 'var(--primary-soft)';
        tagSpan.textContent = '[仿真] ';
        if (type === 'humanized.click') {
            msgSpan.textContent = `点击偏移: ${data.offset}, 按压: ${data.hold_ms}ms`;
        } else {
            msgSpan.textContent = `打字序列生成, 平均延迟: ${data.avg_delay_ms}ms`;
        }
        line.append(tagSpan, msgSpan);
    } else if (type === 'interpreter.step_start') {
        tagSpan.style.color = 'var(--info)';
        tagSpan.textContent = '[步骤] ';
        msgSpan.textContent = `执行: ${data.label || data.pc || ''}`;
        line.append(tagSpan, msgSpan);
    } else if (type === 'action.failed') {
        tagSpan.className = 'text-error';
        tagSpan.textContent = '[错误] ';
        msgSpan.textContent = String(data.message || '动作执行失败');
        line.append(tagSpan, msgSpan);
    } else if (type === 'task.completed') {
        tagSpan.className = 'text-success';
        tagSpan.textContent = '[成功] ';
        msgSpan.textContent = '任务已圆满结束';
        line.append(tagSpan, msgSpan);
    } else if (type === 'task.failed') {
        tagSpan.className = 'text-error';
        tagSpan.textContent = '[失败] ';
        msgSpan.textContent = String(data.error || data.message || '任务执行失败');
        line.append(tagSpan, msgSpan);
    } else if (type === 'task.cancelled') {
        tagSpan.className = 'text-muted';
        tagSpan.textContent = '[取消] ';
        msgSpan.textContent = String(data.message || '任务已取消');
        line.append(tagSpan, msgSpan);
    } else if (type === 'task.dispatch_result') {
        tagSpan.style.color = 'var(--info)';
        tagSpan.textContent = '[汇总] ';
        msgSpan.textContent = String(data.checkpoint || data.status || '已生成本轮执行结果');
        line.append(tagSpan, msgSpan);
    } else {
        msgSpan.textContent = `${type}: ${JSON.stringify(data)}`;
        line.appendChild(msgSpan);
    }

    timeline.appendChild(line);
    timeline.scrollTop = timeline.scrollHeight;
}

export async function loadTasks() {
    const r = await fetchJson('/api/tasks/');
    if (r.ok) renderTasksList(r.data);
}

async function initAppSelector() {
    const r = await fetchJson('/api/tasks/catalog/apps');
    if (!r.ok) return;
    const select = $('taskAppSelector');
    if (select) {
        clearElement(select);
        (r.data.apps || []).forEach(app => {
            const opt = document.createElement('option');
            opt.value = app.id;
            opt.textContent = app.name;
            select.appendChild(opt);
        });
    }
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
        
        let finalName = t.display_name;
        if (!finalName && pluginCatalog.length > 0) {
            const matched = pluginCatalog.find(p => p.task === t.task_name);
            if (matched) finalName = matched.display_name;
        }
        
        title.textContent = finalName || t.task_name || '未知任务';

        const meta = document.createElement('span');
        meta.className = 'list-item-meta';
        meta.textContent = `ID: ${t.task_id} | ${t.status} | ${formatTargetText(t.targets)}`;

        content.append(title, meta);

        const buttonGroup = document.createElement('div');
        buttonGroup.className = 'flex gap-2';

        const detailBtn = document.createElement('button');
        detailBtn.className = 'btn btn-secondary btn-sm';
        detailBtn.textContent = '追踪轨迹';
        detailBtn.onclick = () => loadTaskDetail(t.task_id);
        buttonGroup.appendChild(detailBtn);

        if (['pending', 'running'].includes(t.status)) {
            const cancelBtn = document.createElement('button');
            cancelBtn.className = 'btn btn-danger btn-sm';
            cancelBtn.textContent = '停止';
            cancelBtn.onclick = (e) => {
                e.stopPropagation();
                cancelTask(t.task_id);
            };
            buttonGroup.appendChild(cancelBtn);
        }

        item.append(content, buttonGroup);
        list.appendChild(item);
    });
}

async function cancelTask(taskId) {
    const res = await fetchJson(`/api/tasks/${taskId}/cancel`, { method: "POST", silentErrors: true });
    if (res.ok) {
        toast.success('正在停止任务并回收资源...');
        await loadTasks();
        // 如果正在看详情，刷新状态
        const badge = $('taskModalStatusBadge');
        if (badge) badge.textContent = 'CANCELLING';
    } else {
        toast.error('任务停止失败');
    }
}

async function clearAllTasks() {
    if (!confirm('此操作会清空托管任务状态与事件流水，运行中的任务不会被清空，是否继续？')) return;
    const btn = $('clearTasks');
    if (btn) btn.disabled = true;
    try {
        const r = await fetchJson('/api/tasks/', { method: 'DELETE', silentErrors: true });
        if (r.ok) {
            toast.success('任务历史已清理');
            await loadTasks();
            return;
        }
        toast.error(r.data?.detail || '清理任务历史失败');
    } finally { if (btn) btn.disabled = false; }
}

async function cleanupFailedTasks(event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    if (!confirm('确定要清理所有未成功的任务轨迹与记录吗？')) return;
    const btn = $('cleanupFailedTasks');
    if (btn) btn.disabled = true;
    try {
        const r = await fetchJson('/api/tasks/cleanup_failed', { method: 'POST', silentErrors: true });
        if (r.ok) {
            toast.success(`已清理 ${r.data.count} 条无效任务`);
            await loadTasks();
            return;
        }
        toast.error(r.data?.detail || '清理无效任务失败');
    } finally { if (btn) btn.disabled = false; }
}

async function stopAllTasks() {
    if (!confirm('确定要停止所有正在运行或等待中的任务吗？')) return;
    const btn = $('stopAllTasks');
    if (btn) btn.disabled = true;

    try {
        const r = await fetchJson('/api/tasks/');
        if (!r.ok) return;
        const tasks = r.data;
        const activeTasks = tasks.filter(t => ['pending', 'running'].includes(t.status));
        
        if (activeTasks.length === 0) {
            toast.info('当前没有需要停止的任务');
            return;
        }

        let successCount = 0;
        for (const t of activeTasks) {
            const res = await fetchJson(`/api/tasks/${t.task_id}/cancel`, { method: 'POST', silentErrors: true });
            if (res.ok) successCount++;
        }
        
        toast.success(`正在强制终止任务: ${successCount}/${activeTasks.length}`);
        await loadTasks();
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function initPluginSelector() {
    pluginCatalog = await getTaskCatalog();
    renderPluginSelector();
}

function renderPluginSelector() {
    const host = $('taskPluginHost');
    if (!host) return;
    clearElement(host);

    // Group by category
    const groups = {};
    pluginCatalog.forEach(p => {
        const cat = p.category || '其他';
        if (!groups[cat]) groups[cat] = [];
        groups[cat].push(p);
    });

    Object.entries(groups).forEach(([cat, plugins]) => {
        const label = document.createElement('div');
        label.className = 'plugin-category-label';
        label.textContent = cat;
        host.appendChild(label);

        const grid = document.createElement('div');
        grid.className = 'plugin-grid';
        plugins.forEach(p => {
            const btn = document.createElement('div');
            btn.className = 'plugin-item';
            if (selectedTaskName === p.task) btn.classList.add('selected');
            btn.textContent = p.display_name || p.task;
            btn.onclick = () => {
                selectedTaskName = p.task;
                renderPluginSelector();
                renderFields();
            };
            grid.appendChild(btn);
        });
        host.appendChild(grid);
    });
}

function renderFields() {
    const p = pluginCatalog.find(x => x.task === selectedTaskName);
    const container = $('taskPayloadFields');
    renderCommonFields(container, p, false);

    const showMoreFields = $('showMoreFields');
    if (showMoreFields && container) {
        const optionalFields = container.querySelectorAll('.field-optional');
        showMoreFields.style.display = optionalFields.length > 0 ? 'inline-flex' : 'none';
        showMoreFields.onclick = () => {
            const fields = container.querySelectorAll('.field-optional');
            const isHidden = fields[0]?.style.display === 'none';
            fields.forEach(el => el.style.display = isHidden ? 'flex' : 'none');
            showMoreFields.textContent = isHidden ? '收起可选参数' : '显示高级参数';
        };
    }
}

async function submitTask() {
    if (!selectedTaskName) return toast.warn('请选定作业驱动');

    const resolvedTargets = resolveTargetsFromForm();
    if (!resolvedTargets.ok) return;

    const appId = $('taskAppSelector')?.value || 'default';

    const btn = $('submitTask');
    if (btn) btn.disabled = true;

    try {
        const rawPayload = collectTaskPayload($('taskPayloadFields'));
        // 显式注入应用上下文
        rawPayload.app_id = appId;
        const payload = await sanitizePayloadForTask(selectedTaskName, rawPayload);

        const taskData = buildTaskRequest({
            task: selectedTaskName,
            payload: payload,
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

async function loadTaskTargets() {
    const container = $('taskTargetList');
    const hint = $('taskTargetHint');
    if (!container) return;
    try {
        const r = await fetchJson('/api/devices/');
        if (!r.ok) return;
        const units = [];
        (r.data || []).forEach(d => {
            (d.cloud_machines || []).forEach(u => {
                if (u.availability_state === 'available') {
                    units.push({ device_id: d.device_id, cloud_id: u.cloud_id, label: `#${d.device_id}-${u.cloud_id}` });
                }
            });
        });
        container.replaceChildren();
        if (units.length === 0) {
            const empty = document.createElement('span');
            empty.className = 'text-muted';
            empty.style.fontSize = '12px';
            empty.textContent = '暂无在线节点';
            container.appendChild(empty);
            return;
        }
        units.forEach(u => {
            const label = document.createElement('label');
            label.className = 'custom-checkbox inline-flex items-center gap-1';
            const input = document.createElement('input');
            input.type = 'checkbox';
            input.className = 'task-target-cb';
            input.dataset.device = String(u.device_id);
            input.dataset.cloud = String(u.cloud_id);

            const checkmark = document.createElement('span');
            checkmark.className = 'checkmark';

            const text = document.createElement('span');
            text.textContent = u.label;

            label.append(input, checkmark, text);
            container.appendChild(label);
        });
        if (hint) hint.textContent = `共 ${units.length} 个在线节点，可多选`;
    } catch(e) {
        if (hint) hint.textContent = '加载节点失败';
    }
}

function resolveTargetsFromForm() {
    const checked = document.querySelectorAll('.task-target-cb:checked');
    if (checked.length === 0) {
        toast.warn('请至少勾选一个目标节点');
        return { ok: false };
    }
    const targets = Array.from(checked).map(cb => ({
        device_id: parseInt(cb.dataset.device),
        cloud_id: parseInt(cb.dataset.cloud),
    }));
    return { ok: true, targets };
}
