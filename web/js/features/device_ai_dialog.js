import { fetchJson } from '../utils/api.js';
import { toast } from '../ui/toast.js';
import { openAiTaskOverlay } from './ai_task_overlay.js';
import {
    applyPlannerSubmitState as applySharedPlannerSubmitState,
    clearPlannerCard as clearSharedPlannerCard,
    renderPlannerResult as renderSharedPlannerResult,
    renderPlannerStateLoading as renderSharedPlannerStateLoading,
} from './ai_planner_presenter.js';
import { buildAiDialogPayload } from './credential_payload.js';
import { unitLog } from './logs.js';
import { setUnitTakeoverTraceContext } from './device_unit_detail.js';
import { apiSubmitTask, buildTaskRequest, prepareTaskPayload } from './task_service.js';

const $ = (id) => document.getElementById(id);

let aiDialogAccounts = [];
let currentAiDialogUnit = null;
let plannerSignature = '';
let plannerResult = null;
let activeDraftId = '';
let activeSuccessThreshold = null;
const activeAiTaskByUnit = new Map();
const CUSTOM_APP_OPTION = '__custom__';

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
        currentDeclarativeStage: null,
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
    const select = $('unitAiAppSelect');
    if (String(select?.value || '').trim() === CUSTOM_APP_OPTION) {
        return String($('unitAiCustomAppId')?.value || '').trim();
    }
    return String(select?.value || '').trim();
}

function getSelectedAiDialogAppDisplayName() {
    const select = $('unitAiAppSelect');
    if (String(select?.value || '').trim() === CUSTOM_APP_OPTION) {
        return String($('unitAiCustomDisplayName')?.value || '').trim();
    }
    return '';
}

function getSelectedAiDialogPackageName() {
    const select = $('unitAiAppSelect');
    if (String(select?.value || '').trim() === CUSTOM_APP_OPTION) {
        return String($('unitAiCustomPackageName')?.value || '').trim();
    }
    return '';
}

function toggleAiCustomAppFields() {
    const wrapper = $('unitAiCustomAppFields');
    if (!wrapper) return;
    wrapper.style.display = String($('unitAiAppSelect')?.value || '').trim() === CUSTOM_APP_OPTION
        ? 'flex'
        : 'none';
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

function isAiDialogAccountRequired() {
    return !$('unitAiNoAccountRequired')?.checked;
}

function updateAiAccountHint(appId, readyCount) {
    const hint = $('unitAiAccountHint');
    if (!hint) return;
    if (!isAiDialogAccountRequired()) {
        hint.textContent = '当前任务已声明无需账号数据，执行时不会要求账号池或已选账号。';
        return;
    }
    if (appId === 'default') {
        hint.textContent = `当前显示系统账号池，共 ${readyCount} 个就绪账号`;
        return;
    }
    hint.textContent = `当前显示 ${appId} 账号池，共 ${readyCount} 个就绪账号`;
}

function syncAiDialogAccountRequirementUi() {
    const select = $('unitAiAccountSelect');
    const refresh = $('unitAiAccountRefresh');
    const disabled = !isAiDialogAccountRequired();
    if (select) {
        if (disabled) {
            select.value = '';
        }
        select.disabled = disabled;
    }
    if (refresh) {
        refresh.disabled = disabled;
    }
    updateAiAccountHint(getSelectedAiDialogAppId() || 'default', aiDialogAccounts.length);
}

function currentPlannerSignature() {
    return JSON.stringify({
        goal: getSelectedAiDialogGoal(),
        app_id: getSelectedAiDialogAppId(),
        app_display_name: getSelectedAiDialogAppDisplayName(),
        package_name: getSelectedAiDialogPackageName(),
        account_required: isAiDialogAccountRequired(),
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
    renderSharedPlannerStateLoading({
        card: $('unitAiPlannerCard'),
        title: $('unitAiPlannerTitle'),
        summary: $('unitAiPlannerSummary'),
        badge: $('unitAiPlannerBadge'),
        guidance: $('unitAiPlannerGuidance'),
        controlFlow: $('unitAiPlannerControlFlow'),
        scriptsHost: $('unitAiPlannerScripts'),
        followUp: $('unitAiPlannerFollowUp'),
    }, {
        submitButton: $('submitUnitAiTask'),
        submitLabel: '分析并执行',
    });
}

function applyAiSubmitState(plan) {
    applySharedPlannerSubmitState($('submitUnitAiTask'), plan, '分析并执行');
}

function renderPlannerResult(plan) {
    renderSharedPlannerResult({
        card: $('unitAiPlannerCard'),
        title: $('unitAiPlannerTitle'),
        summary: $('unitAiPlannerSummary'),
        badge: $('unitAiPlannerBadge'),
        guidance: $('unitAiPlannerGuidance'),
        controlFlow: $('unitAiPlannerControlFlow'),
        scriptsHost: $('unitAiPlannerScripts'),
        followUp: $('unitAiPlannerFollowUp'),
    }, plan, {
        submitButton: $('submitUnitAiTask'),
        submitLabel: '分析并执行',
    });
}

function clearPlannerCard() {
    clearSharedPlannerCard({
        card: $('unitAiPlannerCard'),
        guidance: $('unitAiPlannerGuidance'),
        controlFlow: $('unitAiPlannerControlFlow'),
        scriptsHost: $('unitAiPlannerScripts'),
        followUp: $('unitAiPlannerFollowUp'),
    }, {
        submitButton: $('submitUnitAiTask'),
        submitLabel: '分析并执行',
    });
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
            option.textContent = String(app.display_name || app.name || app.id || '').trim();
            select.appendChild(option);
        });
        const customOption = document.createElement('option');
        customOption.value = CUSTOM_APP_OPTION;
        customOption.textContent = '新建应用…';
        select.appendChild(customOption);
        const hasPrevious = Array.from(select.options).some((option) => option.value === previous);
        select.value = hasPrevious ? previous : 'default';
        toggleAiCustomAppFields();
    } catch (_error) {
        select.replaceChildren();
        const option = document.createElement('option');
        option.value = 'default';
        option.textContent = '系统资产 / default';
        select.appendChild(option);
        select.value = 'default';
        toggleAiCustomAppFields();
    }
}

async function loadAiDialogAccounts(appId = getSelectedAiDialogAppId(), preferredAccount = '') {
    const select = $('unitAiAccountSelect');
    if (!select) return;
    if (String($('unitAiAppSelect')?.value || '').trim() === CUSTOM_APP_OPTION && !String(appId || '').trim()) {
        aiDialogAccounts = [];
        renderEmptyAccountSelect(select, '-- 先填写应用 ID --');
        syncAiDialogAccountRequirementUi();
        return;
    }
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
            syncAiDialogAccountRequirementUi();
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
        syncAiDialogAccountRequirementUi();
    } catch (_error) {
        aiDialogAccounts = [];
        renderEmptyAccountSelect(select, '-- 账号加载失败 --');
        syncAiDialogAccountRequirementUi();
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
            app_display_name: getSelectedAiDialogAppDisplayName() || null,
            package_name: getSelectedAiDialogPackageName() || null,
            account_required: isAiDialogAccountRequired(),
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

function buildAiTaskPayload() {
    const payload = buildAiDialogPayload({
        goal: getSelectedAiDialogGoal(),
        appId: getSelectedAiDialogAppId(),
        appDisplayName: getSelectedAiDialogAppDisplayName(),
        packageName: getSelectedAiDialogPackageName(),
        accountRequired: isAiDialogAccountRequired(),
        account: getSelectedAiAccount(),
        advancedPrompt: getSelectedAdvancedPrompt(),
    });
    if (!payload) {
        toast.warn('请填写任务描述');
        return null;
    }
    return payload;
}

function mergePlannedAiTaskPayload(plan, rawPayload) {
    const plannerPayload = plan?.resolved_payload && typeof plan.resolved_payload === 'object'
        ? { ...plan.resolved_payload }
        : {};
    const nextPayload = {
        ...plannerPayload,
        ...rawPayload,
    };

    const plannedAppId = String(plan?.resolved_app?.app_id || plannerPayload.app_id || '').trim();
    const plannedAppDisplayName = String(
        plan?.resolved_app?.display_name
        || plan?.resolved_app?.name
        || plannerPayload.app_display_name
        || ''
    ).trim();
    const plannedPackageName = String(
        plan?.resolved_app?.package
        || plan?.resolved_app?.package_name
        || plannerPayload.package_name
        || plannerPayload.package
        || ''
    ).trim();

    if (plannedAppId) {
        nextPayload.app_id = plannedAppId;
    }
    if (plannedAppDisplayName) {
        nextPayload.app_display_name = plannedAppDisplayName;
    }
    if (plannedPackageName) {
        nextPayload.package = plannedPackageName;
        nextPayload.package_name = plannedPackageName;
    }
    return nextPayload;
}

function applyTakeoverContext(unit, taskId) {
    const traceContext = buildTraceContextForTask(unit, taskId);
    setUnitTakeoverTraceContext(traceContext);
    return traceContext;
}

function handleSuccessfulAiTaskSubmission(unit, taskData, { closeDialog = true, titleFallback = '' } = {}) {
    const taskId = String(taskData?.task_id || '').trim();
    if (!taskId) return;
    const traceContext = applyTakeoverContext(unit, taskId);
    rememberActiveAiTask(unit, taskData);
    unitLog('>>> AI 对话任务已下发');
    if (closeDialog) {
        closeUnitAiDialog();
    }
    openAiTaskOverlay({
        taskId,
        title: `AI 正在执行：${taskData.display_name || titleFallback || plannerResult?.display_name || '当前任务'}`,
        unit,
        traceContext,
    });
}

export async function submitAiTaskForUnit(unit, {
    rawPayload = null,
    plan = null,
    draftId = '',
    successThreshold = null,
    closeDialog = false,
    onSuccess = null,
    onFailure = null,
} = {}) {
    if (!unit) return { ok: false, reason: 'missing_unit' };
    if (!rawPayload || typeof rawPayload !== 'object') {
        return { ok: false, reason: 'invalid_payload' };
    }
    if (!plan || typeof plan !== 'object') {
        return { ok: false, reason: 'planner_failed' };
    }
    if (plan?.account?.can_execute === false) {
        toast.warn(String(plan.account.execution_hint || plan.follow_up?.message || '当前规划未满足执行条件'));
        const blocked = { ok: false, reason: 'planner_blocked' };
        onFailure?.(blocked);
        return blocked;
    }

    const payload = await prepareTaskPayload('agent_executor', {
        rawPayload: mergePlannedAiTaskPayload(plan, rawPayload),
        stripRuntimeOnly: true,
    });

    const taskData = buildTaskRequest({
        task: 'agent_executor',
        payload,
        targets: [{ device_id: unit.parent_id, cloud_id: unit.cloud_id }],
    });
    taskData.display_name = String(plan.display_name || '').trim() || 'AI 对话任务';
    if (String(draftId || '').trim()) {
        taskData.draft_id = String(draftId).trim();
    }
    if (successThreshold) {
        taskData.success_threshold = successThreshold;
    }

    const result = await apiSubmitTask(taskData, { openReport: false });
    if (result.ok) {
        handleSuccessfulAiTaskSubmission(unit, result.data || {}, {
            closeDialog,
            titleFallback: String(plan.display_name || '').trim(),
        });
        onSuccess?.(result);
    } else {
        onFailure?.(result);
    }
    return result;
}

async function applyAiDialogSeed(seed = {}) {
    const appId = String(seed.appId || seed.app_id || 'default').trim() || 'default';
    const appDisplayName = String(seed.appDisplayName || seed.app_display_name || '').trim();
    const packageName = String(seed.packageName || seed.package_name || seed.package || '').trim();
    const accountName = String(seed.accountName || seed.account || '').trim();
    const accountRequired = seed.accountRequired !== false;

    activeDraftId = String(seed.draftId || seed.draft_id || '').trim();
    activeSuccessThreshold = Number(seed.successThreshold || seed.success_threshold || 0) || null;

    const goalInput = $('unitAiGoal');
    if (goalInput) {
        goalInput.value = String(seed.goal || '').trim();
    }
    const advancedPrompt = $('unitAiAdvancedPrompt');
    if (advancedPrompt) {
        advancedPrompt.value = String(seed.advancedPrompt || seed.advanced_prompt || '').trim();
    }
    const noAccountRequired = $('unitAiNoAccountRequired');
    if (noAccountRequired) {
        noAccountRequired.checked = !accountRequired;
    }

    await loadAiDialogApps();
    const appSelect = $('unitAiAppSelect');
    if (appSelect) {
        const hasExistingOption = Array.from(appSelect.options).some((option) => option.value === appId);
        appSelect.value = hasExistingOption ? appId : CUSTOM_APP_OPTION;
    }
    const customAppId = $('unitAiCustomAppId');
    if (customAppId) {
        customAppId.value = appSelect?.value === CUSTOM_APP_OPTION ? appId : '';
    }
    const customDisplayName = $('unitAiCustomDisplayName');
    if (customDisplayName) {
        customDisplayName.value = appSelect?.value === CUSTOM_APP_OPTION ? appDisplayName : '';
    }
    const customPackageName = $('unitAiCustomPackageName');
    if (customPackageName) {
        customPackageName.value = appSelect?.value === CUSTOM_APP_OPTION ? packageName : '';
    }
    toggleAiCustomAppFields();
    await loadAiDialogAccounts(appId, accountName);
    syncAiDialogAccountRequirementUi();
    resetPlannerState();
    clearPlannerCard();
}

function bindPlannerInputs() {
    const clearSummary = () => {
        resetPlannerState();
        clearPlannerCard();
    };

    const goalInput = $('unitAiGoal');
    if (goalInput) goalInput.oninput = clearSummary;

    const advancedPrompt = $('unitAiAdvancedPrompt');
    if (advancedPrompt) advancedPrompt.oninput = clearSummary;

    const refreshBtn = $('unitAiAccountRefresh');
    if (refreshBtn) {
        refreshBtn.onclick = () => {
            resetPlannerState();
            clearPlannerCard();
            void loadAiDialogAccounts(getSelectedAiDialogAppId());
        };
    }

    const appSelect = $('unitAiAppSelect');
    if (appSelect) {
        appSelect.onchange = () => {
            toggleAiCustomAppFields();
            resetPlannerState();
            activeDraftId = '';
            activeSuccessThreshold = null;
            clearPlannerCard();
            void loadAiDialogAccounts(getSelectedAiDialogAppId());
        };
    }

    ['unitAiCustomAppId', 'unitAiCustomDisplayName', 'unitAiCustomPackageName'].forEach((id) => {
        const element = $(id);
        if (element) {
            element.oninput = clearSummary;
        }
    });

    const accountSelect = $('unitAiAccountSelect');
    if (accountSelect) {
        accountSelect.onchange = clearSummary;
    }
    const accountRequiredToggle = $('unitAiNoAccountRequired');
    if (accountRequiredToggle) {
        accountRequiredToggle.onchange = () => {
            syncAiDialogAccountRequirementUi();
            clearSummary();
        };
    }
}

export async function openUnitAiDialog(unit, seed = null) {
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
    if (title) title.textContent = `AI 执行 - 云机 #${unit.parent_id}-${unit.cloud_id}`;
    const workspaceSummary = $('unitAiWorkspaceSummary');
    if (workspaceSummary) {
        workspaceSummary.textContent = `当前弹窗只负责云机 #${unit.parent_id}-${unit.cloud_id} 的单任务执行、执行观察和人工接管。任务图设计、历史复用和蒸馏沉淀请转到 AI 工作台查看。`;
    }

    const goalInput = $('unitAiGoal');
    if (goalInput) goalInput.value = '';
    const advancedPrompt = $('unitAiAdvancedPrompt');
    if (advancedPrompt) advancedPrompt.value = '';
    const customAppId = $('unitAiCustomAppId');
    if (customAppId) customAppId.value = '';
    const customDisplayName = $('unitAiCustomDisplayName');
    if (customDisplayName) customDisplayName.value = '';
    const customPackageName = $('unitAiCustomPackageName');
    if (customPackageName) customPackageName.value = '';
    const noAccountRequired = $('unitAiNoAccountRequired');
    if (noAccountRequired) noAccountRequired.checked = false;

    const advanced = $('unitAiAdvanced');
    if (advanced) advanced.style.display = 'none';

    const openWorkspaceButton = $('unitAiOpenWorkspace');
    if (openWorkspaceButton) {
        openWorkspaceButton.onclick = () => {
            closeUnitAiDialog();
            document.querySelector('.nav-item[data-tab="tab-ai"]')?.click();
        };
    }

    bindPlannerInputs();
    clearPlannerCard();
    await loadAiDialogApps();
    await loadAiDialogAccounts();
    syncAiDialogAccountRequirementUi();
    if (seed && typeof seed === 'object') {
        await applyAiDialogSeed(seed);
    }
}

export function closeUnitAiDialog() {
    const modal = $('unitAiModal');
    if (modal) modal.style.display = 'none';
    const advanced = $('unitAiAdvanced');
    if (advanced) advanced.style.display = 'none';
    applyAiSubmitState(null);
    currentAiDialogUnit = null;
}

export async function submitUnitAiTask(unit, { onSuccess = null, onFailure = null } = {}) {
    if (!unit) return { ok: false, reason: 'missing_unit' };
    const rawPayload = buildAiTaskPayload();
    if (!rawPayload) return { ok: false, reason: 'invalid_payload' };

    const plan = await requestPlanner({ force: true });
    if (!plan) return { ok: false, reason: 'planner_failed' };
    return submitAiTaskForUnit(unit, {
        rawPayload,
        plan,
        draftId: activeDraftId,
        successThreshold: activeSuccessThreshold,
        closeDialog: true,
        onSuccess,
        onFailure,
    });
}
