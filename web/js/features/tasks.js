import { fetchJson } from '../utils/api.js';
import { toast } from '../ui/toast.js';
import { renderTaskFormPanel, toggleAdvancedTaskFields } from '../utils/task_form_ui.js';
import {
    getTaskCatalog,
    apiSubmitTask,
    buildTaskRequest,
    collectTaskPayload,
    prepareTaskPayload,
    resolveTaskDisplayName,
    resolveTaskAppContext,
    taskAcceptsAccount,
} from './task_service.js';
import { FetchSseClient } from '../utils/sse.js';
import { getDevicesSnapshot, refreshDevicesSnapshot } from '../state/devices.js';

const $ = (id) => document.getElementById(id);

let pluginCatalog = [];
let selectedTaskName = '';
let currentEventStream = null;
let taskSubmissionListenerBound = false;
const submittedTaskMonitors = new Map();
let taskAccounts = [];

let submissionOverrides = null;
let pipelineComposerState = [];
let pipelineDraggedIndex = null;

function clearElement(element) {
    if (element) {
        element.replaceChildren();
    }
}

function renderEmptyTaskAccountSelect(label) {
    const select = $('taskAccountSelect');
    if (!select) return;
    select.replaceChildren();
    const emptyOpt = document.createElement('option');
    emptyOpt.value = '';
    emptyOpt.textContent = label;
    select.appendChild(emptyOpt);
}

async function loadTaskAccounts(appId = '') {
    const select = $('taskAccountSelect');
    const hint = $('taskAccountHint');
    if (!select) return;
    const normalizedAppId = String(appId || '').trim();
    const params = new URLSearchParams();
    if (normalizedAppId) {
        params.set('app_id', normalizedAppId);
    }
    try {
        const query = params.toString();
        const response = await fetchJson(`/api/data/accounts/parsed${query ? `?${query}` : ''}`);
        if (!response.ok) {
            taskAccounts = [];
            renderEmptyTaskAccountSelect('-- 账号加载失败 --');
            if (hint) hint.textContent = '加载账号失败';
            return;
        }
        taskAccounts = (response.data?.accounts || []).filter((account) => account.status === 'ready');
        select.replaceChildren();
        const emptyOpt = document.createElement('option');
        emptyOpt.value = '';
        emptyOpt.textContent = `-- 不绑定账号 (${taskAccounts.length} 个就绪) --`;
        select.appendChild(emptyOpt);
        taskAccounts.forEach((account, index) => {
            const option = document.createElement('option');
            option.value = String(index);
            option.textContent = account.account;
            select.appendChild(option);
        });
        if (hint) {
            hint.textContent = normalizedAppId
                ? `${normalizedAppId} 账号池共 ${taskAccounts.length} 个就绪账号`
                : `全部账号池共 ${taskAccounts.length} 个就绪账号`;
        }
    } catch (_error) {
        taskAccounts = [];
        renderEmptyTaskAccountSelect('-- 账号加载失败 --');
        if (hint) hint.textContent = '加载账号失败';
    }
}

function getSelectedTaskAccount() {
    const select = $('taskAccountSelect');
    if (!select || select.value === '') return null;
    return taskAccounts[Number.parseInt(select.value, 10)] || null;
}

function pipelineChildCatalog() {
    return Array.isArray(pluginCatalog)
        ? pluginCatalog.filter((item) => item?.task && item.task !== '_pipeline')
        : [];
}

function pipelineOptionLabel(taskName) {
    const matched = pipelineChildCatalog().find((item) => item.task === taskName);
    return matched?.display_name || taskName;
}

function setPipelineComposerSteps(steps) {
    pipelineComposerState = Array.isArray(steps)
        ? steps
            .filter((item) => item && typeof item === 'object' && String(item.plugin || item.task || '').trim())
            .map((item) => ({
                plugin: String(item.plugin || item.task || '').trim(),
                label: String(item.label || item.display_name || item.plugin || item.task || '').trim(),
                payloadText: item.payload && typeof item.payload === 'object'
                    ? JSON.stringify(item.payload, null, 2)
                    : '',
            }))
        : [];
}

async function buildPipelineComposerPayload() {
    if (!Array.isArray(pipelineComposerState) || pipelineComposerState.length === 0) {
        return { ok: false, error: '请至少添加一个 Pipeline 步骤' };
    }
    const steps = [];
    for (const [index, step] of pipelineComposerState.entries()) {
        const plugin = String(step?.plugin || '').trim();
        if (!plugin) {
            return { ok: false, error: `第 ${index + 1} 个步骤缺少插件` };
        }
        const label = String(step?.label || pipelineOptionLabel(plugin) || plugin).trim();
        const rawPayload = String(step?.payloadText || '').trim();
        let payload = {};
        if (rawPayload) {
            try {
                payload = JSON.parse(rawPayload);
            } catch {
                return { ok: false, error: `第 ${index + 1} 个步骤的 JSON payload 格式无效` };
            }
            if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
                return { ok: false, error: `第 ${index + 1} 个步骤的 payload 必须是 JSON 对象` };
            }
        }
        const sanitizedPayload = await prepareTaskPayload(plugin, {
            rawPayload: payload,
            stripRuntimeOnly: true,
        });
        steps.push({ plugin, label, payload: sanitizedPayload });
    }
    return { ok: true, steps };
}

function renderPipelineComposer(container) {
    if (!container) return;

    const composer = document.createElement('div');
    composer.className = 'pipeline-composer';

    const intro = document.createElement('div');
    intro.className = 'text-muted';
    intro.style.fontSize = '12px';
    intro.textContent = '把多个插件串成一条任务链。可拖拽排序；每一步的 payload 会按目标插件 manifest 自动过滤，运行时字段不会透传。';
    composer.appendChild(intro);

    const selectorTitle = document.createElement('div');
    selectorTitle.className = 'text-sm font-medium';
    selectorTitle.textContent = '勾选要纳入编排的任务';
    composer.appendChild(selectorTitle);

    const selectorGrid = document.createElement('div');
    selectorGrid.className = 'form-grid columns-2';
    pipelineChildCatalog().forEach((task) => {
        const label = document.createElement('label');
        label.className = 'custom-checkbox inline-flex items-center gap-1';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = pipelineComposerState.some((item) => item.plugin === task.task);
        checkbox.onchange = () => {
            const taskName = String(task.task || '').trim();
            if (!taskName) return;
            if (checkbox.checked) {
                if (!pipelineComposerState.some((item) => item.plugin === taskName)) {
                    pipelineComposerState.push({
                        plugin: taskName,
                        label: pipelineOptionLabel(taskName),
                        payloadText: '',
                    });
                }
            } else {
                pipelineComposerState = pipelineComposerState.filter(
                    (item) => item.plugin !== taskName
                );
            }
            renderFields();
        };

        const checkmark = document.createElement('span');
        checkmark.className = 'checkmark';

        const text = document.createElement('span');
        text.textContent = String(task.display_name || task.task || '');

        label.append(checkbox, checkmark, text);
        selectorGrid.appendChild(label);
    });
    composer.appendChild(selectorGrid);

    const list = document.createElement('div');
    list.className = 'pipeline-step-list';

    if (pipelineComposerState.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'text-muted';
        empty.style.fontSize = '12px';
        empty.textContent = '当前没有步骤，先从上方选择一个插件加入编排。';
        list.appendChild(empty);
    }

    pipelineComposerState.forEach((step, index) => {
        const card = document.createElement('div');
        card.className = 'pipeline-step-card';
        card.draggable = true;
        card.dataset.index = String(index);
        card.addEventListener('dragstart', () => {
            pipelineDraggedIndex = index;
            card.classList.add('dragging');
        });
        card.addEventListener('dragend', () => {
            pipelineDraggedIndex = null;
            card.classList.remove('dragging');
        });
        card.addEventListener('dragover', (event) => {
            event.preventDefault();
        });
        card.addEventListener('drop', (event) => {
            event.preventDefault();
            if (pipelineDraggedIndex === null || pipelineDraggedIndex === index) return;
            const next = [...pipelineComposerState];
            const [moved] = next.splice(pipelineDraggedIndex, 1);
            next.splice(index, 0, moved);
            pipelineComposerState = next;
            pipelineDraggedIndex = null;
            renderFields();
        });

        const header = document.createElement('div');
        header.className = 'pipeline-step-header';

        const title = document.createElement('div');
        title.className = 'task-summary-target-label';
        title.textContent = `步骤 ${index + 1}`;
        header.appendChild(title);

        const removeButton = document.createElement('button');
        removeButton.type = 'button';
        removeButton.className = 'btn btn-text btn-sm text-error';
        removeButton.textContent = '移除';
        removeButton.onclick = () => {
            pipelineComposerState.splice(index, 1);
            renderFields();
        };
        header.appendChild(removeButton);
        card.appendChild(header);

        const pluginLabel = document.createElement('label');
        pluginLabel.textContent = '插件';
        card.appendChild(pluginLabel);

        const pluginSelect = document.createElement('select');
        pipelineChildCatalog().forEach((task) => {
            const option = document.createElement('option');
            option.value = String(task.task || '');
            option.textContent = String(task.display_name || task.task || '');
            if (option.value === step.plugin) {
                option.selected = true;
            }
            pluginSelect.appendChild(option);
        });
        pluginSelect.onchange = () => {
            const previousPlugin = step.plugin;
            step.plugin = String(pluginSelect.value || '').trim();
            if (
                !String(step.label || '').trim()
                || step.label === pipelineOptionLabel(previousPlugin)
            ) {
                step.label = pipelineOptionLabel(step.plugin);
            }
            renderFields();
        };
        card.appendChild(pluginSelect);

        const nameLabel = document.createElement('label');
        nameLabel.textContent = '显示名称';
        card.appendChild(nameLabel);

        const nameInput = document.createElement('input');
        nameInput.type = 'text';
        nameInput.value = String(step.label || pipelineOptionLabel(step.plugin));
        nameInput.oninput = () => {
            step.label = nameInput.value;
        };
        card.appendChild(nameInput);

        const payloadLabel = document.createElement('label');
        payloadLabel.textContent = '步骤 payload JSON';
        card.appendChild(payloadLabel);

        const payloadInput = document.createElement('textarea');
        payloadInput.className = 'textarea-large';
        payloadInput.style.minHeight = '96px';
        payloadInput.placeholder = '{\n  "screen_name": "jack"\n}';
        payloadInput.value = String(step.payloadText || '');
        payloadInput.oninput = () => {
            step.payloadText = payloadInput.value;
        };
        card.appendChild(payloadInput);

        list.appendChild(card);
    });

    composer.appendChild(list);
    container.prepend(composer);
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

function createSummaryActions(buttons) {
    const row = document.createElement('div');
    row.className = 'flex flex-wrap gap-2 mt-3';
    buttons.forEach((button) => {
        row.appendChild(button);
    });
    return row;
}

function createSummaryButton(text, onClick, { disabled = false, primary = false } = {}) {
    const button = document.createElement('button');
    button.className = primary ? 'btn btn-primary btn-sm' : 'btn btn-secondary btn-sm';
    button.textContent = text;
    button.disabled = disabled;
    button.onclick = onClick;
    return button;
}

function workflowDraftActionLabel(action) {
    switch (String(action || '')) {
        case 'continue_validation':
            return '继续验证';
        case 'distill':
            return '生成草稿';
        case 'review_distilled':
            return '查看草稿';
        case 'apply_suggestion':
            return '应用建议';
        default:
            return '待处理';
    }
}

function extractErrorText(response, fallback) {
    if (!response) return fallback;
    if (typeof response.data === 'string' && response.data.trim()) return response.data.trim();
    if (response.data?.detail) return String(response.data.detail);
    if (response.data?.message) return String(response.data.message);
    if (response.data?.stderr) return String(response.data.stderr);
    return fallback;
}

async function continueWorkflowDraft(draft, task) {
    const draftId = String(draft?.draft_id || '').trim();
    if (!draftId) return;
    const displayName = String(draft?.display_name || task?.display_name || task?.task_name || '当前草稿');
    const response = await fetchJson(`/api/tasks/drafts/${draftId}/continue`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ count: 1 }),
        silentErrors: true,
    });
    if (!response.ok) {
        toast.error(extractErrorText(response, '继续验证失败'));
        return;
    }
    const [nextTask] = Array.isArray(response.data) ? response.data : [];
    toast.success(`${displayName} 已创建新的验证任务`);
    await loadTasks();
    if (nextTask?.task_id) {
        loadTaskDetail(nextTask.task_id);
    } else if (task?.task_id) {
        await refreshTaskSnapshot(task.task_id);
    }
}

async function distillWorkflowDraft(draft, task) {
    const draftId = String(draft?.draft_id || '').trim();
    if (!draftId) return;
    const displayName = String(draft?.display_name || task?.display_name || task?.task_name || '当前草稿');
    const response = await fetchJson(`/api/tasks/drafts/${draftId}/distill`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force: false }),
        silentErrors: true,
    });
    if (!response.ok || response.data?.ok === false) {
        toast.error(extractErrorText(response, '草稿蒸馏失败'));
        return;
    }
    const pluginName = String(response.data?.plugin_name || '').trim();
    toast.success(
        pluginName
            ? `${displayName} 已生成草稿 ${pluginName}`
            : `${displayName} 已生成工作流草稿`
    );
    if (task?.task_id) {
        await refreshTaskSnapshot(task.task_id);
    }
    await loadTasks();
}

function renderWorkflowDraftSummary(host, task) {
    const draft = task?.workflow_draft;
    if (!host || !draft || typeof draft !== 'object') return;

    const progressText = `${draft.success_count || 0}/${draft.success_threshold || 0}`;
    const nextAction = workflowDraftActionLabel(draft.next_action);
    const message = String(draft.message || '').trim();
    const overview = [
        `状态：${draft.status || 'unknown'}`,
        `进度：${progressText}`,
        `下一步：${nextAction}`,
        message ? `说明：${message}` : '',
    ].filter(Boolean).join(' · ');

    const overviewCard = createSummaryCard(
        '工作流草稿',
        overview,
        draft.can_distill ? '可蒸馏' : `${progressText} 样本`,
        draft.can_distill ? 'ok' : 'default'
    );

    const actionButtons = [];
    if (draft.can_continue) {
        actionButtons.push(
            createSummaryButton('继续验证', () => {
                void continueWorkflowDraft(draft, task);
            })
        );
    }
    if (draft.can_distill) {
        actionButtons.push(
            createSummaryButton(
                '生成草稿',
                () => {
                    void distillWorkflowDraft(draft, task);
                },
                { primary: true }
            )
        );
    }
    if (actionButtons.length > 0) {
        overviewCard.appendChild(createSummaryActions(actionButtons));
    }
    host.appendChild(overviewCard);

    const failureAdvice = draft.latest_failure_advice;
    if (failureAdvice?.summary) {
        const adviceLines = [String(failureAdvice.summary)];
        if (Array.isArray(failureAdvice.suggestions) && failureAdvice.suggestions.length > 0) {
            adviceLines.push(`建议：${failureAdvice.suggestions.join('；')}`);
        }
        if (failureAdvice.suggested_prompt) {
            adviceLines.push(`推荐提示词：${failureAdvice.suggested_prompt}`);
        }
        host.appendChild(createSummaryCard('失败建议', adviceLines.join(' ')));
    }
}

function createReportDetailList(report) {
    const entries = [
        ['切换前机型', report.before_model],
        ['选中机型', report.selected_model],
        ['切换后机型', report.after_model],
        ['机型来源', report.model_source],
        ['地区', report.generated_country],
        ['语言', report.generated_language],
        ['时区', report.generated_timezone],
        ['联系人数量', Array.isArray(report.contact_count) ? report.contact_count.length : report.contact_count],
        ['写入 Google ID', report.google_id_written],
        ['写入联系人', report.contacts_written],
        ['完成截图', report.screenshot_taken],
        ['选择器降级', report.selector_fallback_used],
    ].filter(([, value]) => value !== undefined && value !== null && value !== '');

    if (entries.length === 0) return null;

    const wrapper = document.createElement('div');
    wrapper.className = 'task-summary-list';
    entries.forEach(([labelText, value]) => {
        const row = document.createElement('div');
        row.className = 'task-summary-target';

        const label = document.createElement('div');
        label.className = 'task-summary-title';
        label.textContent = labelText;

        const valueEl = document.createElement('div');
        valueEl.className = 'task-summary-target-message';
        valueEl.textContent = String(value);

        row.append(label, valueEl);
        wrapper.appendChild(row);
    });
    return wrapper;
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
        const report = result?.data?.report && typeof result.data.report === 'object'
            ? result.data.report
            : null;
        return { label, ok, message, report };
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

    renderWorkflowDraftSummary(host, task);

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
            const reportDetails = item.report ? createReportDetailList(item.report) : null;
            if (reportDetails) {
                row.appendChild(reportDetails);
            }
            wrapper.appendChild(row);
        });
        host.appendChild(wrapper);
    }
}

function renderTaskSnapshot(task) {
    const finalName = resolveTaskDisplayName(task, pluginCatalog);

    const title = $('taskModalTitle');
    if (title) {
        const prefix = ['completed', 'failed', 'cancelled'].includes(task.status)
            ? '任务汇总'
            : '任务执行中';
        title.textContent = finalName
            ? `${prefix} - ${finalName}`
            : prefix;
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
    const displayName = event?.detail?.displayName || event?.detail?.taskName || '任务';
    if (!taskId) return;
    trackSubmittedTask(taskId, displayName);
}

function trackSubmittedTask(taskId, displayName) {
    if (submittedTaskMonitors.has(taskId)) return;

    const client = new FetchSseClient(`/api/tasks/${taskId}/events`, {
        onEvent: (type, raw) => {
            if (type === 'message') return;
            let data;
            try {
                data = raw ? JSON.parse(raw) : {};
            } catch {
                data = { raw };
            }
            if (!['task.completed', 'task.failed', 'task.cancelled'].includes(type)) return;
            client.close();
            submittedTaskMonitors.delete(taskId);
            loadTaskDetail(taskId);
            if (type === 'task.completed') {
                toast.success(`${displayName} 已完成，已生成任务汇总`);
            } else if (type === 'task.failed') {
                toast.warn(`${displayName} 执行失败，已弹出结果汇总`);
            } else {
                toast.info(`${displayName} 已结束，已弹出结果汇总`);
            }
        },
        onError: async () => {
            const snapshot = await refreshTaskSnapshot(taskId);
            if (!snapshot || !['completed', 'failed', 'cancelled'].includes(snapshot.status)) return;
            client.close();
            submittedTaskMonitors.delete(taskId);
            loadTaskDetail(taskId);
        },
    });
    submittedTaskMonitors.set(taskId, client);
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

    const accountRefreshBtn = $('taskAccountRefresh');
    if (accountRefreshBtn) {
        accountRefreshBtn.onclick = () => {
            void syncTaskAccountScope(selectedTaskName);
        };
    }
    const appSelector = $('taskAppSelector');
    if (appSelector) {
        appSelector.onchange = () => {
            void syncTaskAccountScope(selectedTaskName);
        };
    }

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
        'task.created', 'task.started', 'task.completed', 'task.failed', 'task.cancelled', 'task.dispatch_result', 'task.action_result',
        'workflow_draft.updated',
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
            } else if (type === 'workflow_draft.updated') {
                refreshTaskSnapshot(taskId);
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
    } else if (type === 'workflow_draft.updated') {
        tagSpan.style.color = 'var(--primary)';
        tagSpan.textContent = '[草稿] ';
        msgSpan.textContent = String(data.message || '工作流草稿状态已更新');
        line.append(tagSpan, msgSpan);
    } else if (type === 'task.action_result') {
        tagSpan.style.color = data.ok ? 'var(--success)' : 'var(--warning, #f59e0b)';
        tagSpan.textContent = `[步骤 ${data.step ?? '?'}] `;
        const label = String(data.label || '未命名步骤');
        const message = String(data.message || '').trim();
        msgSpan.textContent = message
            ? `${label}: ${message}`
            : `${label}: ${data.ok ? '成功' : '失败'}`;
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
        const defaultOpt = document.createElement('option');
        defaultOpt.value = 'default';
        defaultOpt.textContent = '系统资产 / default';
        select.appendChild(defaultOpt);
        (r.data.apps || []).forEach(app => {
            if (String(app.id || '').trim() === 'default') return;
            const opt = document.createElement('option');
            opt.value = app.id;
            opt.textContent = app.name;
            select.appendChild(opt);
        });
    }
}

async function syncTaskAppSelector(taskName) {
    const select = $('taskAppSelector');
    if (!select || !taskName) return;
    if (select.options.length <= 1) {
        await initAppSelector();
    }
    const currentAppId = String(select.value || '').trim();
    const desiredAppId = await resolveTaskAppContext(taskName, {
        fallbackAppId: currentAppId && currentAppId !== 'default' ? currentAppId : '',
    });
    if (!desiredAppId) return;
    const hasOption = Array.from(select.options).some((option) => option.value === desiredAppId);
    if (hasOption) {
        select.value = desiredAppId;
    }
}

async function syncTaskAccountScope(taskName) {
    const accountRow = $('taskAccountGroup');
    const fieldsContainer = $('taskPayloadFields');
    if (!fieldsContainer) return;
    const acceptsAccount = await taskAcceptsAccount(taskName);
    if (accountRow) {
        accountRow.style.display = acceptsAccount ? '' : 'none';
    }
    if (!acceptsAccount) {
        taskAccounts = [];
        renderEmptyTaskAccountSelect('-- 当前任务不支持绑定账号 --');
        const hint = $('taskAccountHint');
        if (hint) hint.textContent = '当前任务不支持绑定账号';
        return;
    }
    const appId = await resolveTaskAppContext(taskName, {
        rawPayload: collectTaskPayload(fieldsContainer),
        fallbackAppId: $('taskAppSelector')?.value || '',
    });
    await loadTaskAccounts(appId);
    const appField = fieldsContainer.querySelector('[data-payload-key="app_id"]');
    if (appField && !appField.dataset.accountScopeBound) {
        appField.dataset.accountScopeBound = 'true';
        const reload = async () => {
            const nextAppId = await resolveTaskAppContext(taskName, {
                rawPayload: collectTaskPayload(fieldsContainer),
                fallbackAppId: $('taskAppSelector')?.value || '',
            });
            await loadTaskAccounts(nextAppId);
        };
        appField.addEventListener('change', () => { void reload(); });
        appField.addEventListener('input', () => { void reload(); });
    }
}

async function syncTaskContextControls(taskName) {
    await syncTaskAppSelector(taskName);
    await syncTaskAccountScope(taskName);
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

        const finalName = resolveTaskDisplayName(t, pluginCatalog);

        title.textContent = finalName || t.task_name || '未知任务';

        const meta = document.createElement('span');
        meta.className = 'list-item-meta';
        meta.textContent = `ID: ${t.task_id} | ${t.status} | ${formatTargetText(t.targets)}`;

        content.append(title, meta);

        const buttonGroup = document.createElement('div');
        buttonGroup.className = 'flex gap-2';

        const detailBtn = document.createElement('button');
        detailBtn.className = 'btn btn-secondary btn-sm';
        detailBtn.textContent = ['completed', 'failed', 'cancelled'].includes(t.status)
            ? '查看报告'
            : '查看进度';
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
    const showMoreFields = $('showMoreFields');
    const preservedPayload = collectTaskPayload(container);
    renderTaskFormPanel({
        task: p || null,
        guideCard: $('taskGuideCard'),
        fieldsContainer: container,
        toggleButton: showMoreFields,
        collapsedText: '显示高级参数',
        expandedText: '收起高级参数',
    });
    if (selectedTaskName === '_pipeline') {
        renderPipelineComposer(container);
    }
    setFormValuesFromPayload(container, preservedPayload);
    void syncTaskContextControls(selectedTaskName);
    if (showMoreFields && container) {
        showMoreFields.onclick = () => {
            toggleAdvancedTaskFields(container, showMoreFields);
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
        const rawPayload = {
            ...collectTaskPayload($('taskPayloadFields')),
            ...collectTaskPayload($('taskRuntimePayloadFields')),
        };
        if (selectedTaskName === '_pipeline') {
            const pipelinePayload = await buildPipelineComposerPayload();
            if (!pipelinePayload.ok) {
                toast.warn(pipelinePayload.error);
                return;
            }
            rawPayload.steps = pipelinePayload.steps;
        }
        const payload = await prepareTaskPayload(selectedTaskName, {
            rawPayload,
            appId,
            account: getSelectedTaskAccount(),
        });

        const taskData = buildTaskRequest({
            task: selectedTaskName,
            payload: payload,
            targets: resolvedTargets.targets,
            priority: $('taskPriority')?.value || 50,
            maxRetries: $('taskMaxRetries')?.value || 0,
            runAt: $('taskRunAt')?.value || null,
        });

        if (submissionOverrides && typeof submissionOverrides === 'object') {
            if (submissionOverrides.display_name) taskData.display_name = submissionOverrides.display_name;
            if (submissionOverrides.draft_id) taskData.draft_id = submissionOverrides.draft_id;
            if (typeof submissionOverrides.success_threshold === 'number') {
                taskData.success_threshold = submissionOverrides.success_threshold;
            }
        }

        const result = await apiSubmitTask(taskData);
        if (result?.ok) {
            submissionOverrides = null;
            await loadTasks();
        }
    } finally {
        if (btn) btn.disabled = false;
    }
}

function setFormValuesFromPayload(container, payload) {
    if (!container || !payload || typeof payload !== 'object') return;
    container.querySelectorAll('[data-payload-key]').forEach((input) => {
        const key = input?.dataset?.payloadKey;
        if (!key) return;
        if (!(key in payload)) return;
        const value = payload[key];

        const type = input.dataset?.payloadType || 'string';
        if (type === 'boolean' || input.type === 'checkbox') {
            input.checked = Boolean(value);
            return;
        }
        if (value === null || value === undefined) {
            input.value = '';
            return;
        }
        if (typeof value === 'object') {
            return;
        }
        input.value = String(value);
    });
}

function selectTargetsFromSnapshot(targets) {
    if (!Array.isArray(targets)) return;
    const desired = new Set(
        targets
            .map((t) => `${Number(t?.device_id || 0)}-${Number(t?.cloud_id || 0)}`)
            .filter((k) => !k.startsWith('0-'))
    );
    if (desired.size === 0) return;
    document.querySelectorAll('.task-target-cb').forEach((cb) => {
        const key = `${Number(cb.dataset.device || 0)}-${Number(cb.dataset.cloud || 0)}`;
        cb.checked = desired.has(key);
    });
}

export async function prefillTaskFromDraft({
    taskName,
    payload,
    targets,
    priority,
    maxRetries,
    appId,
    displayName,
    draftId,
    successThreshold,
} = {}) {
    const resolvedTaskName = String(taskName || '').trim();
    if (!resolvedTaskName) return;

    if (!Array.isArray(pluginCatalog) || pluginCatalog.length === 0) {
        pluginCatalog = await getTaskCatalog();
        renderPluginSelector();
    }

    selectedTaskName = resolvedTaskName;
    if (resolvedTaskName === '_pipeline') {
        setPipelineComposerSteps(payload?.steps);
    }
    renderPluginSelector();
    renderFields();

    const appSelect = $('taskAppSelector');
    if (appSelect && appSelect.options.length <= 1) {
        await initAppSelector();
    }
    if (appSelect) {
        const desired = await resolveTaskAppContext(resolvedTaskName, {
            rawPayload: payload,
            fallbackAppId: appId,
        });
        if (desired) {
            const has = Array.from(appSelect.options).some((opt) => opt.value === desired);
            if (has) {
                appSelect.value = desired;
            }
        }
    }

    const container = $('taskPayloadFields');
    setFormValuesFromPayload(container, payload);
    const runtimeContainer = $('taskRuntimePayloadFields');
    setFormValuesFromPayload(runtimeContainer, payload);

    if (typeof priority === 'number' || (typeof priority === 'string' && String(priority).trim())) {
        const el = $('taskPriority');
        if (el) el.value = String(priority);
    }
    if (typeof maxRetries === 'number' || (typeof maxRetries === 'string' && String(maxRetries).trim())) {
        const el = $('taskMaxRetries');
        if (el) el.value = String(maxRetries);
    }

    await loadTaskTargets();
    selectTargetsFromSnapshot(targets);

    submissionOverrides = {
        display_name: String(displayName || '').trim() || null,
        draft_id: String(draftId || '').trim() || null,
        success_threshold: Number.isFinite(Number(successThreshold)) ? Number(successThreshold) : null,
    };
}

async function loadTaskTargets() {
    const container = $('taskTargetList');
    const hint = $('taskTargetHint');
    if (!container) return;
    try {
        const r = await refreshDevicesSnapshot({ silentErrors: true, maxAgeMs: 5000 });
        if (!r.ok) {
            if (hint) hint.textContent = '加载节点失败';
            return;
        }
        const units = [];
        (r.data || getDevicesSnapshot()).forEach(d => {
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
