import { fetchJson } from '../utils/api.js';
import { openAiDraftSaveModal } from './ai_task_annotations.js';
import { toast } from '../ui/toast.js';
import { openAiTaskOverlay } from './ai_task_overlay.js';
import { resolveAiDialogSubmitState } from './ai_dialog_submit_state.js';
import { buildAiDialogPayload } from './credential_payload.js';
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
const CUSTOM_APP_OPTION = '__custom__';
const EXIT_ACTION_LABELS = {
    apply_suggestion: '按建议重试',
    continue_validation: '继续验证',
    distill: '蒸馏草稿',
    review_distilled: '已蒸馏',
    retry: '重新执行',
};
const REUSE_PRIORITY_LABELS = {
    distill_sample: '优先蒸馏样本',
    continue_trace: '优先继续复用',
    context_only: '优先复用上下文',
    none: '暂无可复用资产',
};
const REUSE_ACTION_LABELS = {
    distill_or_validate: '继续验证或进入蒸馏',
    continue_from_memory: '沿最近运行继续',
    reuse_context: '带上下文继续执行',
    fresh_exploration: '重新探索执行',
};
const QUALIFICATION_LABELS = {
    distillable: '可蒸馏',
    replayable: '可继续执行',
    useful_trace: '有价值轨迹',
    context_only: '仅上下文可复用',
    discard: '未形成复用价值',
};

function clearElement(element) {
    if (element) {
        element.replaceChildren();
    }
}

function normalizeDraftSummary(item) {
    if (item?.workflow_draft && typeof item.workflow_draft === 'object') {
        return item.workflow_draft;
    }
    return item && typeof item === 'object' ? item : {};
}

function normalizeDraftExit(item) {
    const draft = normalizeDraftSummary(item);
    return draft?.exit && typeof draft.exit === 'object' ? draft.exit : {};
}

function normalizeDistillAssessment(item) {
    const draft = normalizeDraftSummary(item);
    return draft?.distill_assessment && typeof draft.distill_assessment === 'object'
        ? draft.distill_assessment
        : {};
}

function normalizeLatestRunAsset(item) {
    const draft = normalizeDraftSummary(item);
    return draft?.latest_run_asset && typeof draft.latest_run_asset === 'object'
        ? draft.latest_run_asset
        : {};
}

function formatExitAction(action) {
    return EXIT_ACTION_LABELS[String(action || '').trim()] || '继续处理';
}

function formatReusePriority(priority) {
    return REUSE_PRIORITY_LABELS[String(priority || '').trim()] || '待评估';
}

function formatReuseAction(action) {
    return REUSE_ACTION_LABELS[String(action || '').trim()] || '继续执行';
}

function formatQualification(value) {
    return QUALIFICATION_LABELS[String(value || '').trim()] || '待评估';
}

function historyPrimaryActionLabel(item) {
    const exitAction = String(normalizeDraftExit(item)?.action || '').trim();
    if (exitAction === 'apply_suggestion') return '按建议重试';
    if (exitAction === 'continue_validation') return '继续执行';
    if (exitAction === 'distill') return '继续验证';
    if (exitAction === 'review_distilled') return '再次执行';
    return '立即执行';
}

function distillButtonState(item) {
    const draft = normalizeDraftSummary(item);
    const assessment = normalizeDistillAssessment(item);
    const exitAction = String(normalizeDraftExit(item)?.action || '').trim();
    if (exitAction === 'review_distilled' || draft?.last_distilled_manifest_path) {
        return {
            label: '已蒸馏',
            disabled: true,
            title: '该草稿已经产出蒸馏结果',
        };
    }
    if (assessment?.can_distill_now || draft?.can_distill) {
        return {
            label: '蒸馏草稿',
            disabled: false,
            title: '当前样本已满足蒸馏门槛',
        };
    }
    const threshold = Number(assessment?.success_threshold || draft?.success_threshold || 0);
    const count = Number(assessment?.success_count || draft?.success_count || 0);
    const stage = String(assessment?.stage || '').trim();
    if (threshold > count && threshold > 0) {
        return {
            label: '蒸馏草稿',
            disabled: true,
            title: `当前成功样本 ${count}/${threshold}，还不能蒸馏`,
        };
    }
    if (stage === 'repair') {
        return {
            label: '蒸馏草稿',
            disabled: true,
            title: '当前应先修正任务，再考虑蒸馏',
        };
    }
    return {
        label: '蒸馏草稿',
        disabled: true,
        title: '当前还没有达到蒸馏条件',
    };
}

function plannerBadgeState(plan) {
    const execution = plan?.execution || {};
    const followUp = plan?.follow_up || {};
    const missing = Array.isArray(followUp?.missing) ? followUp.missing.length : 0;
    if (execution?.distill_eligible) {
        return { className: 'badge badge-ok', text: '可蒸馏' };
    }
    if (missing > 0) {
        return { className: 'badge badge-error', text: '待补充' };
    }
    const reusePriority = String(execution?.reuse_priority || '').trim();
    if (reusePriority === 'continue_trace') {
        return { className: 'badge badge-ok', text: '可复用' };
    }
    if (reusePriority === 'context_only') {
        return { className: 'badge', text: '有上下文' };
    }
    return { className: 'badge badge-ok', text: '已就绪' };
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
        app_display_name: getSelectedAiDialogAppDisplayName(),
        package_name: getSelectedAiDialogPackageName(),
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
    const guidance = $('unitAiPlannerGuidance');
    const controlFlow = $('unitAiPlannerControlFlow');
    const followUp = $('unitAiPlannerFollowUp');
    if (card) card.style.display = 'block';
    if (title) title.textContent = 'AI 任务规划';
    if (summary) summary.textContent = '正在分析当前 goal 与应用上下文…';
    if (badge) {
        badge.className = 'badge';
        badge.textContent = '分析中';
    }
    applyAiSubmitState(null);
    clearElement(guidance);
    clearElement(controlFlow);
    clearElement(followUp);
}

function applyAiSubmitState(plan) {
    const button = $('submitUnitAiTask');
    if (!button) return;
    const state = resolveAiDialogSubmitState(plan);
    button.disabled = Boolean(state.disabled);
    button.textContent = state.label || '下发任务';
    button.title = state.title || '';
}

function renderPlannerResult(plan) {
    const card = $('unitAiPlannerCard');
    const title = $('unitAiPlannerTitle');
    const summary = $('unitAiPlannerSummary');
    const badge = $('unitAiPlannerBadge');
    const guidance = $('unitAiPlannerGuidance');
    const controlFlow = $('unitAiPlannerControlFlow');
    const followUp = $('unitAiPlannerFollowUp');
    if (card) card.style.display = plan ? 'block' : 'none';
    if (!plan) return;

    if (title) title.textContent = String(plan.display_name || 'AI 任务规划');
    if (summary) summary.textContent = String(plan.operator_summary || '').trim();
    if (badge) {
        const badgeState = plannerBadgeState(plan);
        badge.className = badgeState.className;
        badge.textContent = badgeState.text;
    }
    applyAiSubmitState(plan);

    clearElement(guidance);
    const guidanceSummary = String(plan.guidance?.summary || '').trim();
    if (guidanceSummary) {
        const wrapper = document.createElement('div');
        wrapper.className = 'task-guide-card';

        const heading = document.createElement('div');
        heading.className = 'task-guide-title';
        heading.textContent = String(plan.guidance?.title || '蒸馏写法建议').trim();
        wrapper.appendChild(heading);

        const text = document.createElement('div');
        text.className = 'task-guide-text';
        text.textContent = guidanceSummary;
        wrapper.appendChild(text);

        const tags = document.createElement('div');
        tags.className = 'task-guide-tags';
        const guidanceSuggestions = Array.isArray(plan.guidance?.suggestions)
            ? plan.guidance.suggestions
            : [];
        guidanceSuggestions.slice(0, 3).forEach((item) => {
            const tip = String(item || '').trim();
            if (!tip) return;
            const chip = document.createElement('span');
            chip.className = 'task-guide-tag';
            chip.textContent = tip;
            tags.appendChild(chip);
        });
        const example = String(plan.guidance?.example || '').trim();
        if (example) {
            const chip = document.createElement('span');
            chip.className = 'task-guide-tag';
            chip.textContent = example;
            tags.appendChild(chip);
        }
        if (tags.childElementCount > 0) {
            wrapper.appendChild(tags);
        }
        guidance?.appendChild(wrapper);
    }

    clearElement(controlFlow);
    const controlFlowItems = Array.isArray(plan.control_flow?.items) ? plan.control_flow.items : [];
    if (controlFlowItems.length > 0) {
        const wrapper = document.createElement('div');
        wrapper.className = 'task-summary-target';

        const heading = document.createElement('div');
        heading.className = 'task-guide-title';
        heading.textContent = '已识别的控制流提示';
        wrapper.appendChild(heading);

        const tags = document.createElement('div');
        tags.className = 'task-guide-tags';
        controlFlowItems.slice(0, 4).forEach((item) => {
            const text = String(item?.text || '').trim();
            if (!text) return;
            const chip = document.createElement('span');
            chip.className = 'task-guide-tag';
            const label = String(item?.label || item?.type || '').trim();
            chip.textContent = label ? `${label}：${text}` : text;
            tags.appendChild(chip);
        });
        if (tags.childElementCount > 0) {
            wrapper.appendChild(tags);
            controlFlow?.appendChild(wrapper);
        }
    }

    clearElement(followUp);
    const lines = [];
    if (plan.resolved_app?.app_id) {
        lines.push(`应用上下文：${plan.resolved_app.app_id}`);
    }
    if (plan.intent?.label) {
        lines.push(`任务意图：${String(plan.intent.label).trim()}`);
    }
    if (plan.branch?.label) {
        lines.push(`业务分支：${String(plan.branch.label).trim()}`);
    }
    if (plan.account?.execution_hint) {
        lines.push(String(plan.account.execution_hint).trim());
    }
    if (plan.execution?.reuse_priority) {
        lines.push(`复用优先级：${formatReusePriority(plan.execution.reuse_priority)}`);
    }
    if (plan.execution?.reuse_action) {
        lines.push(`当前出口：${formatReuseAction(plan.execution.reuse_action)}`);
    }
    if (plan.memory?.qualification) {
        lines.push(`最近运行价值：${formatQualification(plan.memory.qualification)}`);
    }
    if (plan.execution?.distill_eligible) {
        lines.push('蒸馏资格：当前已有可蒸馏样本，可进入蒸馏评估');
    }
    const recommendedWorkflow = Array.isArray(plan.recommended_workflows)
        ? plan.recommended_workflows.find((item) => String(item?.task || '').trim() !== 'agent_executor')
        : null;
    if (recommendedWorkflow?.display_name) {
        lines.push(`推荐流程：${String(recommendedWorkflow.display_name).trim()}`);
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
    lines.slice(0, 6).forEach((text) => {
        const row = document.createElement('div');
        row.className = 'task-summary-line';
        row.textContent = text;
        followUp?.appendChild(row);
    });
}

function clearPlannerCard() {
    const card = $('unitAiPlannerCard');
    if (card) card.style.display = 'none';
    applyAiSubmitState(null);
    clearElement($('unitAiPlannerGuidance'));
    clearElement($('unitAiPlannerControlFlow'));
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
        updateAiAccountHint('default', 0);
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
            app_display_name: getSelectedAiDialogAppDisplayName() || null,
            package_name: getSelectedAiDialogPackageName() || null,
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
    const payload = buildAiDialogPayload({
        goal: getSelectedAiDialogGoal(),
        appId: getSelectedAiDialogAppId(),
        appDisplayName: getSelectedAiDialogAppDisplayName(),
        packageName: getSelectedAiDialogPackageName(),
        account: getSelectedAiAccount(),
        advancedPrompt: getSelectedAdvancedPrompt(),
    });
    if (!payload) {
        toast.warn('请填写任务描述');
        return null;
    }
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
        const draft = normalizeDraftSummary(item);
        const exit = normalizeDraftExit(item);
        const assessment = normalizeDistillAssessment(item);
        const latestRunAsset = normalizeLatestRunAsset(item);
        const card = document.createElement('div');
        card.className = 'task-summary-target';

        const header = document.createElement('div');
        header.className = 'task-summary-target-header';

        const title = document.createElement('div');
        title.className = 'task-summary-target-label';
        title.textContent = String(item.display_name || '未命名任务');
        header.appendChild(title);

        const badge = document.createElement('span');
        badge.className = `badge ${assessment?.can_distill_now ? 'badge-ok' : (String(item.status || '') === 'needs_attention' ? 'badge-error' : '')}`;
        badge.textContent = assessment?.can_distill_now ? '可蒸馏' : String(item.status || 'unknown');
        header.appendChild(badge);

        const body = document.createElement('div');
        body.className = 'task-summary-target-message';
        body.textContent = [
            item.app_id ? `应用 ${item.app_id}` : '',
            item.account ? `账号 ${item.account}` : '',
            item.updated_at ? `上次 ${formatRelativeTime(item.updated_at)}` : '',
        ].filter(Boolean).join(' · ');

        const details = document.createElement('div');
        details.className = 'task-summary-list mt-2';
        [
            exit?.action ? `当前出口：${formatExitAction(exit.action)}` : '',
            exit?.reuse_priority ? `复用优先级：${formatReusePriority(exit.reuse_priority)}` : '',
            assessment?.latest_qualification ? `最近运行价值：${formatQualification(assessment.latest_qualification)}` : '',
            latestRunAsset?.distill_reason ? `未蒸馏原因：${String(latestRunAsset.distill_reason).trim()}` : '',
        ].filter(Boolean).slice(0, 3).forEach((text) => {
            const row = document.createElement('div');
            row.className = 'task-summary-line';
            row.textContent = text;
            details.appendChild(row);
        });

        const actions = document.createElement('div');
        actions.className = 'flex flex-wrap gap-2 mt-2';

        const runButton = document.createElement('button');
        runButton.type = 'button';
        runButton.className = 'btn btn-primary btn-sm';
        runButton.textContent = historyPrimaryActionLabel(item);
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

        const saveButton = document.createElement('button');
        saveButton.type = 'button';
        saveButton.className = 'btn btn-secondary btn-sm';
        saveButton.textContent = '保存可复用项';
        saveButton.disabled = !item.can_save;
        saveButton.onclick = () => {
            void openAiDraftSaveModal(String(item.draft_id || ''));
        };
        actions.appendChild(saveButton);

        const distillButton = document.createElement('button');
        const distillState = distillButtonState(item);
        distillButton.type = 'button';
        distillButton.className = 'btn btn-secondary btn-sm';
        distillButton.textContent = distillState.label;
        distillButton.disabled = Boolean(distillState.disabled);
        distillButton.title = distillState.title || '';
        distillButton.onclick = () => {
            void distillHistoryItem(item);
        };
        actions.appendChild(distillButton);

        card.append(header, body, details, actions);
        host.appendChild(card);
    });
}

async function distillHistoryItem(item) {
    const draftId = String(item?.draft_id || '').trim();
    if (!draftId) return;
    const response = await fetchJson(`/api/tasks/drafts/${encodeURIComponent(draftId)}/distill`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
        silentErrors: true,
    });
    if (!response.ok) {
        toast.error(String(response.data?.detail || '蒸馏失败'));
        return;
    }
    if (response.data?.ok === false) {
        toast.info(String(response.data?.message || '当前还不能蒸馏'));
        await loadAiDialogHistory();
        return;
    }
    toast.success('已生成蒸馏草稿');
    await loadAiDialogHistory();
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
    const appDisplayName = String(payload.app_display_name || '').trim();
    const packageName = String(payload.package_name || payload.package || '').trim();
    const accountName = String(payload.account || identity.account || '').trim();

    activeDraftId = String(response.data?.draft_id || draftId);
    activeSuccessThreshold = Number(response.data?.success_threshold || 0) || null;

    const goalInput = $('unitAiGoal');
    if (goalInput) goalInput.value = String(payload.goal || '').trim();
    const advancedPrompt = $('unitAiAdvancedPrompt');
    if (advancedPrompt) advancedPrompt.value = String(payload.advanced_prompt || '').trim();

    await loadAiDialogApps();
    const appSelect = $('unitAiAppSelect');
    if (appSelect) {
        const hasExistingOption = Array.from(appSelect.options).some((option) => option.value === appId);
        appSelect.value = hasExistingOption ? appId : CUSTOM_APP_OPTION;
    }
    const customAppId = $('unitAiCustomAppId');
    if (customAppId) customAppId.value = appSelect?.value === CUSTOM_APP_OPTION ? appId : '';
    const customDisplayName = $('unitAiCustomDisplayName');
    if (customDisplayName) customDisplayName.value = appSelect?.value === CUSTOM_APP_OPTION ? appDisplayName : '';
    const customPackageName = $('unitAiCustomPackageName');
    if (customPackageName) customPackageName.value = appSelect?.value === CUSTOM_APP_OPTION ? packageName : '';
    toggleAiCustomAppFields();
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
            toggleAiCustomAppFields();
            resetPlannerState();
            activeDraftId = '';
            activeSuccessThreshold = null;
            void loadAiDialogAccounts(getSelectedAiDialogAppId()).then(() => requestPlanner({ force: true, silent: true }));
        };
    }

    ['unitAiCustomAppId', 'unitAiCustomDisplayName', 'unitAiCustomPackageName'].forEach((id) => {
        const element = $(id);
        if (element) {
            element.oninput = () => {
                resetPlannerState();
                schedulePlanner();
            };
        }
    });

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
    const customAppId = $('unitAiCustomAppId');
    if (customAppId) customAppId.value = '';
    const customDisplayName = $('unitAiCustomDisplayName');
    if (customDisplayName) customDisplayName.value = '';
    const customPackageName = $('unitAiCustomPackageName');
    if (customPackageName) customPackageName.value = '';

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
    applyAiSubmitState(null);
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
    if (plan?.account?.can_execute === false) {
        toast.warn(String(plan.account.execution_hint || plan.follow_up?.message || '当前规划未满足执行条件'));
        const blocked = { ok: false, reason: 'planner_blocked' };
        onFailure?.(blocked);
        return blocked;
    }

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
