import { fetchJson } from '../utils/api.js';
import { toast } from '../ui/toast.js';
import { openAiTaskOverlay } from './ai_task_overlay.js';
import { unitLog } from './logs.js';
import { setUnitTakeoverTraceContext } from './device_unit_detail.js';
import { apiSubmitTask, buildTaskRequest, prepareTaskPayload } from './task_service.js';

const $ = (id) => document.getElementById(id);

let aiDialogAccounts = [];
let currentAiDialogUnit = null;
let plannerTimer = null;
let plannerSignature = '';
let plannerResult = null;
let activeDraftId = '';
let activeSuccessThreshold = null;
const activeAiTaskByUnit = new Map();

function clearElement(element) {
    if (element) {
        element.replaceChildren();
    }
}

function unitTaskKey(unit) {
    if (!unit) return '';
    return `${Number(unit.parent_id || 0)}-${Number(unit.cloud_id || 0)}`;
}

function isActiveAiTaskStatus(status) {
    const normalized = String(status || '').trim().toLowerCase();
    return normalized === 'pending'
        || normalized === 'running'
        || normalized === 'paused'
        || normalized === 'pause_requested';
}

function buildOverlayTitleFromTask(task) {
    return `AI 正在执行：${task?.display_name || task?.task_name || plannerResult?.display_name || '当前任务'}`;
}

function buildTraceContextForTask(unit, taskId) {
    return {
        taskId,
        runId: `${taskId}-run-1`,
        targetLabel: `Unit #${unit.parent_id}-${unit.cloud_id}`,
        attemptNumber: 1,
        deviceId: unit.parent_id,
        cloudId: unit.cloud_id,
        takeoverRequested: false,
    };
}

function rememberActiveAiTask(unit, task) {
    const key = unitTaskKey(unit);
    const taskId = String(task?.task_id || '').trim();
    if (!key || !taskId) return null;
    const snapshot = {
        taskId,
        title: buildOverlayTitleFromTask(task),
        traceContext: buildTraceContextForTask(unit, taskId),
    };
    activeAiTaskByUnit.set(key, snapshot);
    return snapshot;
}

function clearRememberedAiTask(unit) {
    const key = unitTaskKey(unit);
    if (key) {
        activeAiTaskByUnit.delete(key);
    }
}

function taskMatchesUnit(task, unit) {
    if (!task || !unit) return false;
    const targets = Array.isArray(task.targets) ? task.targets : [];
    return targets.some((target) =>
        Number(target?.device_id || 0) === Number(unit.parent_id || 0)
        && Number(target?.cloud_id || 0) === Number(unit.cloud_id || 0)
    );
}

async function resolveActiveAiTaskForUnit(unit) {
    const key = unitTaskKey(unit);
    if (!key) return null;

    const remembered = activeAiTaskByUnit.get(key) || null;
    if (remembered?.taskId) {
        const response = await fetchJson(`/api/tasks/${encodeURIComponent(remembered.taskId)}`, { silentErrors: true });
        if (response.ok && isActiveAiTaskStatus(response.data?.status) && taskMatchesUnit(response.data, unit)) {
            return {
                taskId: remembered.taskId,
                title: buildOverlayTitleFromTask(response.data),
                traceContext: remembered.traceContext || buildTraceContextForTask(unit, remembered.taskId),
            };
        }
        activeAiTaskByUnit.delete(key);
    }

    const params = new URLSearchParams({
        device_id: String(unit.parent_id),
        cloud_id: String(unit.cloud_id),
        task_name: 'agent_executor',
    });
    const activeResponse = await fetchJson(`/api/tasks/active?${params.toString()}`, {
        silentErrors: true,
    });
    if (!activeResponse.ok || !activeResponse.data) {
        return null;
    }
    const candidate = activeResponse.data;
    if (!isActiveAiTaskStatus(candidate?.status) || !taskMatchesUnit(candidate, unit)) {
        return null;
    }
    return rememberActiveAiTask(unit, candidate);
}

function renderEmptyAccountSelect(select, label) {
    if (!select) return;
    select.replaceChildren();
    const emptyOpt = document.createElement('option');
    emptyOpt.value = '';
    emptyOpt.textContent = label;
    select.appendChild(emptyOpt);
}

function getSelectedAiDialogAppId() {
    return String($('unitAiAppSelect')?.value || '').trim();
}

function getSelectedAiDialogGoal() {
    return String($('unitAiGoal')?.value || '').trim();
}

function getSelectedAdvancedPrompt() {
    return String($('unitAiAdvancedPrompt')?.value || '').trim();
}

function getSelectedAiAccount() {
    const select = $('unitAiAccountSelect');
    if (!select || select.value === '') {
        return null;
    }
    const index = Number.parseInt(select.value, 10);
    if (!Number.isFinite(index) || index < 0) {
        return null;
    }
    return aiDialogAccounts[index] || null;
}

function getSelectedAiAccountName() {
    return String(getSelectedAiAccount()?.account || '').trim();
}

function updateAiAccountHint(appId, readyCount) {
    const hint = $('unitAiAccountHint');
    if (!hint) return;
    if (appId === 'default') {
        hint.textContent = `当前显示系统账号池，共 ${readyCount} 个就绪账号`;
        return;
    }
    hint.textContent = `当前显示 ${appId} 账号池，共 ${readyCount} 个就绪账号`;
}

function currentPlannerSignature() {
    return JSON.stringify({
        goal: getSelectedAiDialogGoal(),
        app_id: getSelectedAiDialogAppId(),
        selected_account: getSelectedAiAccountName(),
        advanced_prompt: getSelectedAdvancedPrompt(),
        draft_id: activeDraftId,
    });
}

function resetPlannerState() {
    plannerSignature = '';
    plannerResult = null;
}

function renderPlannerStateLoading() {
    const card = $('unitAiPlannerCard');
    const title = $('unitAiPlannerTitle');
    const summary = $('unitAiPlannerSummary');
    const badge = $('unitAiPlannerBadge');
    const followUp = $('unitAiPlannerFollowUp');
    if (card) card.style.display = 'block';
    if (title) title.textContent = 'AI 任务规划';
    if (summary) summary.textContent = '正在分析当前 goal 与应用上下文…';
    if (badge) {
        badge.className = 'badge';
        badge.textContent = '分析中';
    }
    clearElement(followUp);
}

function renderPlannerResult(plan) {
    const card = $('unitAiPlannerCard');
    const title = $('unitAiPlannerTitle');
    const summary = $('unitAiPlannerSummary');
    const badge = $('unitAiPlannerBadge');
    const followUp = $('unitAiPlannerFollowUp');
    if (card) card.style.display = plan ? 'block' : 'none';
    if (!plan) return;

    if (title) title.textContent = String(plan.display_name || 'AI 任务规划');
    if (summary) summary.textContent = String(plan.operator_summary || '').trim();
    if (badge) {
        const missing = Array.isArray(plan.follow_up?.missing) ? plan.follow_up.missing.length : 0;
        badge.className = `badge ${missing > 0 ? 'badge-error' : 'badge-ok'}`;
        badge.textContent = missing > 0 ? '待补充' : '已就绪';
    }

    clearElement(followUp);
    const lines = [];
    if (plan.resolved_app?.app_id) {
        lines.push(`应用上下文：${plan.resolved_app.app_id}`);
    }
    if (plan.account?.strategy === 'selected' && plan.account?.selected_account) {
        lines.push(`执行账号：${plan.account.selected_account}`);
    } else if (plan.account?.ready_count > 0) {
        lines.push(`账号池：当前有 ${plan.account.ready_count} 个可用账号`);
    }
    if (Array.isArray(plan.follow_up?.suggestions)) {
        plan.follow_up.suggestions.forEach((item) => {
            const text = String(item || '').trim();
            if (text) lines.push(text);
        });
    }
    lines.slice(0, 4).forEach((text) => {
        const row = document.createElement('div');
        row.className = 'task-summary-line';
        row.textContent = text;
        followUp?.appendChild(row);
    });
}

function clearPlannerCard() {
    const card = $('unitAiPlannerCard');
    if (card) card.style.display = 'none';
    clearElement($('unitAiPlannerFollowUp'));
}

function formatRelativeTime(value) {
    const text = String(value || '').trim();
    if (!text) return '刚刚';
    const parsed = new Date(text);
    if (Number.isNaN(parsed.getTime())) return text;
    return parsed.toLocaleString();
}

function clearHistoryList(message = '暂无 AI 对话快捷历史') {
    const host = $('unitAiHistoryList');
    if (!host) return;
    clearElement(host);
    const empty = document.createElement('div');
    empty.id = 'unitAiHistoryEmpty';
    empty.className = 'text-muted';
    empty.textContent = message;
    host.appendChild(empty);
}

async function loadAiDialogApps() {
    const select = $('unitAiAppSelect');
    if (!select) return;
    const previous = getSelectedAiDialogAppId() || 'default';

    try {
        const response = await fetchJson('/api/tasks/catalog/apps', { silentErrors: true });
        const apps = Array.isArray(response.data?.apps) ? response.data.apps : [];
        select.replaceChildren();
        const defaultOption = document.createElement('option');
        defaultOption.value = 'default';
        defaultOption.textContent = '系统资产 / default';
        select.appendChild(defaultOption);
        apps.forEach((app) => {
            if (String(app.id || '').trim() === 'default') return;
            const option = document.createElement('option');
            option.value = String(app.id || '').trim();
            option.textContent = String(app.name || app.id || '').trim();
            select.appendChild(option);
        });
        const hasPrevious = Array.from(select.options).some((option) => option.value === previous);
        select.value = hasPrevious ? previous : 'default';
    } catch (_error) {
        select.replaceChildren();
        const option = document.createElement('option');
        option.value = 'default';
        option.textContent = '系统资产 / default';
        select.appendChild(option);
        select.value = 'default';
    }
}

async function loadAiDialogAccounts(appId = getSelectedAiDialogAppId(), preferredAccount = '') {
    const select = $('unitAiAccountSelect');
    if (!select) return;
    const params = new URLSearchParams();
    if (appId) {
        params.set('app_id', appId);
    }
    const query = params.toString();
    try {
        const response = await fetchJson(`/api/data/accounts/parsed${query ? `?${query}` : ''}`);
        if (!response.ok) {
            aiDialogAccounts = [];
            renderEmptyAccountSelect(select, '-- 账号加载失败 --');
            return;
        }
        aiDialogAccounts = (response.data?.accounts || []).filter((account) => account.status === 'ready');
        select.replaceChildren();
        const emptyOpt = document.createElement('option');
        emptyOpt.value = '';
        emptyOpt.textContent = `-- 不绑定账号 (${aiDialogAccounts.length} 个就绪) --`;
        select.appendChild(emptyOpt);
        let preferredIndex = -1;
        aiDialogAccounts.forEach((account, index) => {
            const option = document.createElement('option');
            option.value = String(index);
            option.textContent = account.account;
            if (preferredAccount && String(account.account || '').trim() === preferredAccount) {
                preferredIndex = index;
            }
            select.appendChild(option);
        });
        select.value = preferredIndex >= 0 ? String(preferredIndex) : '';
        updateAiAccountHint(appId || 'default', aiDialogAccounts.length);
    } catch (_error) {
        aiDialogAccounts = [];
        renderEmptyAccountSelect(select, '-- 账号加载失败 --');
    }
}

async function requestPlanner({ force = false, silent = false } = {}) {
    if (!currentAiDialogUnit) return null;
    const goal = getSelectedAiDialogGoal();
    if (!goal) {
        resetPlannerState();
        clearPlannerCard();
        return null;
    }
    const signature = currentPlannerSignature();
    if (!force && plannerResult && signature === plannerSignature) {
        return plannerResult;
    }

    renderPlannerStateLoading();
    const response = await fetchJson('/api/ai_dialog/planner', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            goal,
            app_id: getSelectedAiDialogAppId(),
            selected_account: getSelectedAiAccountName() || null,
            advanced_prompt: getSelectedAdvancedPrompt() || null,
        }),
        silentErrors: true,
    });
    if (!response.ok) {
        if (!silent) {
            toast.error(String(response.data?.detail || 'AI 规划失败'));
        }
        clearPlannerCard();
        return null;
    }
    plannerSignature = signature;
    plannerResult = response.data;
    renderPlannerResult(plannerResult);
    return plannerResult;
}

function schedulePlanner() {
    if (plannerTimer) {
        clearTimeout(plannerTimer);
    }
    plannerTimer = setTimeout(() => {
        void requestPlanner({ silent: true });
    }, 300);
}

function buildAiTaskPayload() {
    const goal = getSelectedAiDialogGoal();
    if (!goal) {
        toast.warn('请填写任务描述');
        return null;
    }

    const payload = { goal };
    const appId = getSelectedAiDialogAppId();
    if (appId) {
        payload.app_id = appId;
    }

    const account = getSelectedAiAccount();
    if (account) {
        if (account.account) payload.account = account.account;
        if (account.password) payload.password = account.password;
        if (account.twofa) {
            payload.two_factor_code = account.twofa;
            payload.twofa_secret = account.twofa;
        }
    }

    const advancedPrompt = getSelectedAdvancedPrompt();
    if (advancedPrompt) {
        payload.advanced_prompt = advancedPrompt;
    }

    payload._workflow_source = 'ai_dialog';
    return payload;
}

function applyTakeoverContext(unit, taskId) {
    const traceContext = buildTraceContextForTask(unit, taskId);
    setUnitTakeoverTraceContext(traceContext);
    return traceContext;
}

function handleSuccessfulAiTaskSubmission(unit, taskData) {
    const taskId = String(taskData?.task_id || '').trim();
    if (!taskId) return;
    const traceContext = applyTakeoverContext(unit, taskId);
    rememberActiveAiTask(unit, taskData);
    unitLog('>>> AI 对话任务已下发');
    closeUnitAiDialog();
    openAiTaskOverlay({
        taskId,
        title: `AI 正在执行：${taskData.display_name || plannerResult?.display_name || '当前任务'}`,
        unit,
        traceContext,
    });
}

async function loadAiDialogHistory() {
    const response = await fetchJson('/api/ai_dialog/history?limit=6', { silentErrors: true });
    if (!response.ok) {
        clearHistoryList('快捷历史加载失败');
        return;
    }
    const host = $('unitAiHistoryList');
    if (!host) return;
    clearElement(host);
    const items = Array.isArray(response.data) ? response.data : [];
    if (!items.length) {
        clearHistoryList();
        return;
    }

    items.forEach((item) => {
        const card = document.createElement('div');
        card.className = 'task-summary-target';

        const header = document.createElement('div');
        header.className = 'task-summary-target-header';

        const title = document.createElement('div');
        title.className = 'task-summary-target-label';
        title.textContent = String(item.display_name || '未命名任务');
        header.appendChild(title);

        const badge = document.createElement('span');
        badge.className = `badge ${item.can_replay ? 'badge-ok' : ''}`;
        badge.textContent = String(item.status || 'unknown');
        header.appendChild(badge);

        const body = document.createElement('div');
        body.className = 'task-summary-target-message';
        body.textContent = [
            item.app_id ? `应用 ${item.app_id}` : '',
            item.account ? `账号 ${item.account}` : '',
            item.updated_at ? `上次 ${formatRelativeTime(item.updated_at)}` : '',
        ].filter(Boolean).join(' · ');

        const actions = document.createElement('div');
        actions.className = 'flex flex-wrap gap-2 mt-2';

        const runButton = document.createElement('button');
        runButton.type = 'button';
        runButton.className = 'btn btn-primary btn-sm';
        runButton.textContent = '立即执行';
        runButton.disabled = !item.can_replay;
        runButton.onclick = () => {
            void replayHistoryItem(item);
        };
        actions.appendChild(runButton);

        const editButton = document.createElement('button');
        editButton.type = 'button';
        editButton.className = 'btn btn-secondary btn-sm';
        editButton.textContent = '编辑后执行';
        editButton.disabled = !item.can_edit;
        editButton.onclick = () => {
            void loadHistoryItemIntoDialog(item);
        };
        actions.appendChild(editButton);

        card.append(header, body, actions);
        host.appendChild(card);
    });
}

async function replayHistoryItem(item) {
    if (!currentAiDialogUnit) return;
    const draftId = String(item?.draft_id || '').trim();
    if (!draftId) return;
    const response = await fetchJson(`/api/tasks/drafts/${encodeURIComponent(draftId)}/continue`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ count: 1 }),
        silentErrors: true,
    });
    if (!response.ok) {
        toast.error(String(response.data?.detail || '快捷重放失败'));
        return;
    }
    const [taskData] = Array.isArray(response.data) ? response.data : [];
    if (!taskData?.task_id) {
        toast.error('快捷重放未返回任务');
        return;
    }
    toast.success('已从快捷历史重放任务');
    handleSuccessfulAiTaskSubmission(currentAiDialogUnit, taskData);
}

async function loadHistoryItemIntoDialog(item) {
    const draftId = String(item?.draft_id || '').trim();
    if (!draftId) return;
    const response = await fetchJson(`/api/tasks/drafts/${encodeURIComponent(draftId)}/snapshot`, {
        silentErrors: true,
    });
    if (!response.ok) {
        toast.error(String(response.data?.detail || '读取快捷历史失败'));
        return;
    }
    const snapshot = response.data?.snapshot || {};
    const payload = snapshot.payload || {};
    const identity = snapshot.identity || {};
    const appId = String(payload.app_id || identity.app_id || 'default').trim() || 'default';
    const accountName = String(payload.account || identity.account || '').trim();

    activeDraftId = String(response.data?.draft_id || draftId);
    activeSuccessThreshold = Number(response.data?.success_threshold || 0) || null;

    const goalInput = $('unitAiGoal');
    if (goalInput) goalInput.value = String(payload.goal || '').trim();
    const advancedPrompt = $('unitAiAdvancedPrompt');
    if (advancedPrompt) advancedPrompt.value = String(payload.advanced_prompt || '').trim();

    await loadAiDialogApps();
    const appSelect = $('unitAiAppSelect');
    if (appSelect) appSelect.value = appId;
    await loadAiDialogAccounts(appId, accountName);
    resetPlannerState();
    await requestPlanner({ force: true, silent: true });
    toast.info('已载入历史任务，可修改后再次执行');
}

function bindPlannerInputs() {
    const goalInput = $('unitAiGoal');
    if (goalInput) goalInput.oninput = () => {
        resetPlannerState();
        schedulePlanner();
    };

    const advancedPrompt = $('unitAiAdvancedPrompt');
    if (advancedPrompt) advancedPrompt.oninput = () => {
        resetPlannerState();
        schedulePlanner();
    };

    const refreshBtn = $('unitAiAccountRefresh');
    if (refreshBtn) {
        refreshBtn.onclick = () => {
            void loadAiDialogAccounts(getSelectedAiDialogAppId()).then(() => requestPlanner({ force: true, silent: true }));
        };
    }

    const appSelect = $('unitAiAppSelect');
    if (appSelect) {
        appSelect.onchange = () => {
            resetPlannerState();
            activeDraftId = '';
            activeSuccessThreshold = null;
            void loadAiDialogAccounts(getSelectedAiDialogAppId()).then(() => requestPlanner({ force: true, silent: true }));
        };
    }

    const accountSelect = $('unitAiAccountSelect');
    if (accountSelect) {
        accountSelect.onchange = () => {
            resetPlannerState();
            schedulePlanner();
        };
    }
}

export async function openUnitAiDialog(unit) {
    if (!unit) return;
    const activeTask = await resolveActiveAiTaskForUnit(unit);
    if (activeTask) {
        setUnitTakeoverTraceContext(activeTask.traceContext);
        openAiTaskOverlay({
            taskId: activeTask.taskId,
            title: activeTask.title,
            unit,
            traceContext: activeTask.traceContext,
        });
        toast.info('当前云机已有进行中的 AI 任务，已恢复执行视图');
        return;
    }
    clearRememberedAiTask(unit);
    currentAiDialogUnit = unit;
    resetPlannerState();
    activeDraftId = '';
    activeSuccessThreshold = null;

    const modal = $('unitAiModal');
    if (modal) modal.style.display = 'flex';

    const title = $('unitAiModalTitle');
    if (title) title.textContent = `AI 对话 - 云机 #${unit.parent_id}-${unit.cloud_id}`;

    const goalInput = $('unitAiGoal');
    if (goalInput) goalInput.value = '';
    const advancedPrompt = $('unitAiAdvancedPrompt');
    if (advancedPrompt) advancedPrompt.value = '';

    const advanced = $('unitAiAdvanced');
    if (advanced) advanced.style.display = 'none';

    bindPlannerInputs();
    clearPlannerCard();
    await loadAiDialogApps();
    await loadAiDialogAccounts();
    await loadAiDialogHistory();
}

export function closeUnitAiDialog() {
    const modal = $('unitAiModal');
    if (modal) modal.style.display = 'none';
    const advanced = $('unitAiAdvanced');
    if (advanced) advanced.style.display = 'none';
    currentAiDialogUnit = null;
    if (plannerTimer) {
        clearTimeout(plannerTimer);
        plannerTimer = null;
    }
}

export async function submitUnitAiTask(unit, { onSuccess = null, onFailure = null } = {}) {
    if (!unit) return { ok: false, reason: 'missing_unit' };
    const rawPayload = buildAiTaskPayload();
    if (!rawPayload) return { ok: false, reason: 'invalid_payload' };

    const plan = await requestPlanner({ force: true });
    if (!plan) return { ok: false, reason: 'planner_failed' };

    const payload = await prepareTaskPayload('agent_executor', {
        rawPayload: {
            ...(plan.resolved_payload || {}),
            ...rawPayload,
        },
        stripRuntimeOnly: true,
    });

    const taskData = buildTaskRequest({
        task: 'agent_executor',
        payload,
        targets: [{ device_id: unit.parent_id, cloud_id: unit.cloud_id }],
    });
    taskData.display_name = String(plan.display_name || '').trim() || 'AI 对话任务';
    if (activeDraftId) {
        taskData.draft_id = activeDraftId;
    }
    if (activeSuccessThreshold) {
        taskData.success_threshold = activeSuccessThreshold;
    }

    const result = await apiSubmitTask(taskData, { openReport: false });
    if (result.ok) {
        handleSuccessfulAiTaskSubmission(unit, result.data || {});
        onSuccess?.(result);
    } else {
        onFailure?.(result);
    }
    return result;
}
