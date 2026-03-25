import { fetchJson } from '../utils/api.js';
import { refreshDevicesSnapshot } from '../state/devices.js';
import { toast } from '../ui/toast.js';
import { buildAiDialogPayload } from './credential_payload.js';
import {
    applyPlannerSubmitState,
    clearPlannerCard,
    renderPlannerResult,
    renderPlannerStateLoading,
} from './ai_planner_presenter.js';
import {
    formatExitAction,
    formatQualification,
    formatReuseAction,
    formatReusePriority,
    normalizeDraftExit,
    normalizeDraftSummary,
    normalizeLatestRunAsset,
    resolveDistillButtonState,
} from './ai_dialog_history_summary.js';
import { openAiDraftSaveModal } from './ai_task_annotations.js';
import { submitAiTaskForUnit } from './device_ai_dialog.js';
import { openAiWorkspaceDetail } from './devices.js';
import { loadDrafts } from './drafts.js';
import { loadMetrics } from './metrics.js';
import { loadTaskCatalog } from './task_service.js';

const $ = (id) => document.getElementById(id);
const CUSTOM_APP_OPTION = '__custom__';
const GUIDED_STEPS = [
    { step: 1, title: '目标与资源', hint: '先选择目标云机、应用和账号，为当前任务图绑定执行上下文。' },
    { step: 2, title: '任务描述与约束', hint: '补充目标、成功判定、失败出口和人工接管条件。' },
    { step: 3, title: '确认任务图', hint: '生成任务图草案后，确认控制流、声明脚本和执行门槛。' },
    { step: 4, title: '执行与回流', hint: '确认后下发执行，并在设备执行态或工作台中查看结果回流。' },
];
const ADVANCED_PROMPT_LABELS = {
    success: '成功判定',
    failure: '失败出口',
    takeover: '人工接管',
    notes: '补充说明',
};

const state = {
    uiMode: 'guided',
    guidedStep: 1,
    accounts: [],
    plannerSignature: '',
    plannerResult: null,
    plannerDirty: false,
    planConfirmed: false,
    activeDraftId: '',
    activeSuccessThreshold: null,
    historyCache: [],
    selectedHistoryId: '',
    taskCatalog: [],
};

function clearElement(element) {
    if (element) {
        element.replaceChildren();
    }
}

function stopEvent(event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
}

function switchToTab(tabId) {
    const button = document.querySelector(`.nav-item[data-tab="${tabId}"]`);
    if (button) {
        button.click();
    }
}

function resetWorkspaceDraftContext() {
    state.activeDraftId = '';
    state.activeSuccessThreshold = null;
}

function formatUpdatedAt(value) {
    const text = String(value || '').trim();
    if (!text) return '';
    const date = new Date(text);
    if (Number.isNaN(date.getTime())) return text;
    return date.toLocaleString();
}

function describeTargets(targets) {
    if (!Array.isArray(targets) || targets.length === 0) {
        return '未绑定目标节点';
    }
    return targets
        .map((target) => `#${Number(target?.device_id || 0)}-${Number(target?.cloud_id || 0)}`)
        .join('、');
}

function renderEmptyAccountSelect(label) {
    const select = $('aiWorkspaceAccountSelect');
    if (!select) return;
    select.replaceChildren();
    const option = document.createElement('option');
    option.value = '';
    option.textContent = label;
    select.appendChild(option);
}

function selectedHistoryItem() {
    return state.historyCache.find((item) => String(item?.draft_id || '').trim() === state.selectedHistoryId) || null;
}

function getSelectedWorkspaceAppId() {
    const appSelect = $('aiWorkspaceAppSelect');
    if (String(appSelect?.value || '').trim() === CUSTOM_APP_OPTION) {
        return String($('aiWorkspaceCustomAppId')?.value || '').trim();
    }
    return String(appSelect?.value || '').trim();
}

function getSelectedWorkspaceAppDisplayName() {
    const appSelect = $('aiWorkspaceAppSelect');
    if (String(appSelect?.value || '').trim() === CUSTOM_APP_OPTION) {
        return String($('aiWorkspaceCustomDisplayName')?.value || '').trim();
    }
    return '';
}

function getSelectedWorkspacePackageName() {
    const appSelect = $('aiWorkspaceAppSelect');
    if (String(appSelect?.value || '').trim() === CUSTOM_APP_OPTION) {
        return String($('aiWorkspaceCustomPackageName')?.value || '').trim();
    }
    return '';
}

function getSelectedWorkspaceAccount() {
    const select = $('aiWorkspaceAccountSelect');
    if (!select || select.value === '') return null;
    const index = Number.parseInt(select.value, 10);
    if (!Number.isFinite(index) || index < 0) return null;
    return state.accounts[index] || null;
}

function isWorkspaceAccountRequired() {
    return !$('aiWorkspaceNoAccountRequired')?.checked;
}

function getWorkspaceInputs() {
    return {
        goal: String($('aiWorkspaceGoal')?.value || '').trim(),
        appId: getSelectedWorkspaceAppId(),
        appDisplayName: getSelectedWorkspaceAppDisplayName(),
        packageName: getSelectedWorkspacePackageName(),
        accountRequired: isWorkspaceAccountRequired(),
        account: getSelectedWorkspaceAccount(),
        autoTotpEnabled: $('aiWorkspaceAutoTotpEnabled')?.checked !== false,
        successCriteria: String($('aiWorkspaceSuccessCriteria')?.value || '').trim(),
        failureGuard: String($('aiWorkspaceFailureGuard')?.value || '').trim(),
        takeoverRules: String($('aiWorkspaceTakeoverRules')?.value || '').trim(),
        advancedPrompt: String($('aiWorkspaceAdvancedPrompt')?.value || '').trim(),
    };
}

function buildCombinedAdvancedPrompt(inputs = getWorkspaceInputs()) {
    const sections = [
        [ADVANCED_PROMPT_LABELS.success, inputs.successCriteria],
        [ADVANCED_PROMPT_LABELS.failure, inputs.failureGuard],
        [ADVANCED_PROMPT_LABELS.takeover, inputs.takeoverRules],
        [ADVANCED_PROMPT_LABELS.notes, inputs.advancedPrompt],
    ].filter(([, value]) => String(value || '').trim());
    return sections.map(([label, value]) => `${label}：${String(value).trim()}`).join('\n');
}

function parseCombinedAdvancedPrompt(rawValue) {
    const result = {
        successCriteria: '',
        failureGuard: '',
        takeoverRules: '',
        advancedPrompt: '',
    };
    const extraLines = [];
    String(rawValue || '')
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
        .forEach((line) => {
            const match = line.match(/^([^：:]+)[：:]\s*(.+)$/);
            if (!match) {
                extraLines.push(line);
                return;
            }
            const [, label, value] = match;
            if (label === ADVANCED_PROMPT_LABELS.success) {
                result.successCriteria = value;
                return;
            }
            if (label === ADVANCED_PROMPT_LABELS.failure) {
                result.failureGuard = value;
                return;
            }
            if (label === ADVANCED_PROMPT_LABELS.takeover) {
                result.takeoverRules = value;
                return;
            }
            if (label === ADVANCED_PROMPT_LABELS.notes) {
                result.advancedPrompt = value;
                return;
            }
            extraLines.push(line);
        });
    if (!result.advancedPrompt && extraLines.length > 0) {
        result.advancedPrompt = extraLines.join('\n');
    }
    return result;
}

function currentPlannerSignature() {
    const inputs = getWorkspaceInputs();
    return JSON.stringify({
        goal: inputs.goal,
        app_id: inputs.appId,
        app_display_name: inputs.appDisplayName,
        package_name: inputs.packageName,
        account_required: inputs.accountRequired,
        selected_account: String(inputs.account?.account || '').trim(),
        auto_totp_enabled: inputs.autoTotpEnabled,
        success_criteria: inputs.successCriteria,
        failure_guard: inputs.failureGuard,
        takeover_rules: inputs.takeoverRules,
        advanced_prompt: inputs.advancedPrompt,
    });
}

function currentWorkspaceTargetSummary() {
    const target = String($('aiWorkspaceTargetSelect')?.value || '').trim();
    if (!target) {
        return '尚未选择目标云机';
    }
    const [deviceIdText, cloudIdText] = target.split('-');
    return `目标云机 #${Number(deviceIdText || 0)}-${Number(cloudIdText || 0)}`;
}

function plannerElements() {
    return {
        card: $('aiWorkspacePlannerCard'),
        title: $('aiWorkspacePlannerTitle'),
        summary: $('aiWorkspacePlannerSummary'),
        badge: $('aiWorkspacePlannerBadge'),
        guidance: $('aiWorkspacePlannerGuidance'),
        controlFlow: $('aiWorkspacePlannerControlFlow'),
        scriptsHost: $('aiWorkspacePlannerScripts'),
        followUp: $('aiWorkspacePlannerFollowUp'),
    };
}

function buildMetaLines(values) {
    return values
        .map((item) => String(item || '').trim())
        .filter(Boolean)
        .slice(0, 4);
}

function normalizeCapabilities(capabilities) {
    if (!capabilities || typeof capabilities !== 'object') {
        return {};
    }
    return {
        account_binding: Boolean(capabilities.account_binding),
        totp_2fa: Boolean(capabilities.totp_2fa),
        email_code: Boolean(capabilities.email_code),
        sms_code: Boolean(capabilities.sms_code),
        graphic_captcha: Boolean(capabilities.graphic_captcha),
        slider_captcha: Boolean(capabilities.slider_captcha),
        human_takeover: Boolean(capabilities.human_takeover),
    };
}

function looksLikeLoginGoal(goal) {
    const text = String(goal || '').trim().toLowerCase();
    if (!text) return false;
    return ['登录', '登陆', 'login', 'log in', 'sign in', 'signin'].some((token) => text.includes(token));
}

function findWorkspaceCapabilityManifest(inputs = getWorkspaceInputs()) {
    if (!Array.isArray(state.taskCatalog) || state.taskCatalog.length === 0) {
        return null;
    }
    const appId = String(inputs.appId || '').trim().toLowerCase();
    const goal = String(inputs.goal || '').trim();
    if (appId === 'x' && looksLikeLoginGoal(goal)) {
        return state.taskCatalog.find((item) => String(item?.task || '').trim() === 'x_login') || null;
    }
    return null;
}

function workspaceCapabilityItems() {
    const inputs = getWorkspaceInputs();
    const manifest = findWorkspaceCapabilityManifest(inputs);
    const capabilities = normalizeCapabilities(manifest?.capabilities);
    const account = inputs.account;
    const hasTwofaSecret = Boolean(String(account?.twofa || account?.twofa_secret || '').trim());
    const accountRequired = inputs.accountRequired;
    const accountBound = Boolean(account?.account);
    const autoTotpAvailable = Boolean(capabilities.totp_2fa);
    const autoTotpReady = autoTotpAvailable && accountRequired && accountBound && hasTwofaSecret;
    const autoTotpEnabled = autoTotpReady && Boolean(inputs.autoTotpEnabled);

    return [
        {
            title: '自动 2FA 验证码',
            status: autoTotpAvailable ? (autoTotpEnabled ? '已启用' : autoTotpReady ? '已关闭' : '可用') : '未触发',
            tone: autoTotpAvailable ? (autoTotpEnabled ? 'available' : 'warning') : 'planned',
            text: autoTotpAvailable
                ? autoTotpEnabled
                    ? '当前已匹配支持 TOTP 的登录流程，且所选账号包含 2FA 密钥；执行时会自动计算 6 位验证码。'
                    : autoTotpReady
                        ? '当前账号和流程都满足自动 2FA 条件，但你已手动关闭；本次执行将不自动带入 2FA 密钥。'
                    : accountRequired && !accountBound
                        ? '当前流程支持自动 2FA，但还未绑定账号；绑定含 2FA 密钥的账号后会自动启用。'
                        : accountRequired && accountBound && !hasTwofaSecret
                            ? '当前流程支持自动 2FA，但所选账号未配置 2FA 密钥；遇到验证时可能需要人工处理。'
                            : '当前流程支持自动 2FA；当账号与任务条件满足时会自动启用。'
                : '当前任务尚未匹配到已声明 TOTP 能力的固定流程；后续可由 AI 继续识别或切换到支持的登录插件。',
        },
        {
            title: '人工接管',
            status: '可用',
            tone: 'available',
            text: '遇到图形验证码、滑块验证码、短信码、邮箱码或风险确认时，当前仍以暂停并等待人工处理为主。',
        },
        {
            title: '图形验证码 / 滑块验证码',
            status: 'AI 驱动',
            tone: 'planned',
            text: '规划为 AI 驱动挑战节点：由 AI 识别、求解或判断，再把结果回填到脚本流中；当前先展示能力方向，不伪装成已自动可用。',
        },
        {
            title: '短信码 / 邮箱码',
            status: '通道驱动',
            tone: 'planned',
            text: '规划为通道驱动挑战节点：先接入短信/邮箱资源读取，再做验证码提取与流程编排；AI 最多只参与内容理解，不应替代通道能力本身。',
        },
    ];
}

function renderWorkspaceCapabilities() {
    const host = $('aiWorkspaceCapabilitiesList');
    const toggle = $('aiWorkspaceAutoTotpEnabled');
    const hint = $('aiWorkspaceAutoTotpHint');
    if (!host) return;
    const inputs = getWorkspaceInputs();
    const manifest = findWorkspaceCapabilityManifest(inputs);
    const capabilities = normalizeCapabilities(manifest?.capabilities);
    const account = inputs.account;
    const hasTwofaSecret = Boolean(String(account?.twofa || account?.twofa_secret || '').trim());
    const autoTotpSupported = Boolean(capabilities.totp_2fa);
    if (toggle) {
        toggle.disabled = !autoTotpSupported || !inputs.accountRequired;
    }
    if (hint) {
        hint.textContent = !autoTotpSupported
            ? '当前任务还未匹配到支持自动 TOTP 的固定流程；如识别到 X 登录等流程，会在这里启用。'
            : !inputs.accountRequired
                ? '当前任务已声明无需账号数据，因此不会使用账号 2FA 密钥。'
                : !account?.account
                    ? '请先绑定账号；若账号含 2FA 密钥，系统可在支持的流程里自动生成 6 位验证码。'
                    : !hasTwofaSecret
                        ? '当前账号未配置 2FA 密钥；如需自动生成验证码，请先在账号资源中补充 2FA 字段。'
                        : inputs.autoTotpEnabled
                            ? '当前流程和账号都满足自动 2FA 条件；执行时会自动计算并填写 6 位验证码。'
                            : '你已手动关闭自动 2FA；本次执行会保留账号绑定，但不会自动带入 2FA 密钥。';
    }
    clearElement(host);
    workspaceCapabilityItems().forEach((item) => {
        const card = document.createElement('div');
        card.className = 'capability-item';
        const header = document.createElement('div');
        header.className = 'capability-item-header';
        const title = document.createElement('div');
        title.className = 'capability-item-title';
        title.textContent = item.title;
        const badge = document.createElement('span');
        badge.className = `capability-item-status ${item.tone}`;
        badge.textContent = item.status;
        header.append(title, badge);
        const text = document.createElement('div');
        text.className = 'capability-item-text';
        text.textContent = item.text;
        card.append(header, text);
        host.appendChild(card);
    });
}

function createMetaBlock(title, lines) {
    const resolvedLines = buildMetaLines(lines);
    if (resolvedLines.length === 0) {
        return null;
    }
    const block = document.createElement('div');
    block.className = 'task-summary-target';

    const heading = document.createElement('div');
    heading.className = 'task-guide-title';
    heading.textContent = title;
    block.appendChild(heading);

    resolvedLines.forEach((text) => {
        const row = document.createElement('div');
        row.className = 'task-summary-line';
        row.textContent = text;
        block.appendChild(row);
    });
    return block;
}

function resetPlannerState({ keepPlan = false } = {}) {
    if (!keepPlan) {
        state.plannerSignature = '';
        state.plannerResult = null;
    }
    state.planConfirmed = false;
}

function toggleCustomAppFields() {
    const wrapper = $('aiWorkspaceCustomAppFields');
    if (!wrapper) return;
    wrapper.style.display = String($('aiWorkspaceAppSelect')?.value || '').trim() === CUSTOM_APP_OPTION
        ? 'flex'
        : 'none';
}

function updateWorkspaceAccountHint(appId, readyCount) {
    const hint = $('aiWorkspaceAccountHint');
    if (!hint) return;
    if (!isWorkspaceAccountRequired()) {
        hint.textContent = '当前任务已声明无需账号数据，下发时不会要求账号池或已选账号。';
        return;
    }
    if (!appId || appId === 'default') {
        hint.textContent = `当前显示系统账号池，共 ${readyCount} 个就绪账号`;
        return;
    }
    hint.textContent = `当前显示 ${appId} 账号池，共 ${readyCount} 个就绪账号`;
}

function syncWorkspaceAccountRequirementUi() {
    const select = $('aiWorkspaceAccountSelect');
    const refresh = $('aiWorkspaceAccountRefresh');
    const disabled = !isWorkspaceAccountRequired();
    if (select) {
        if (disabled) {
            select.value = '';
        }
        select.disabled = disabled;
    }
    if (refresh) {
        refresh.disabled = disabled;
    }
    updateWorkspaceAccountHint(getSelectedWorkspaceAppId(), state.accounts.length);
}

function canAdvanceGuidedStep(step = state.guidedStep) {
    const hasTarget = Boolean(String($('aiWorkspaceTargetSelect')?.value || '').trim());
    const hasGoal = Boolean(String($('aiWorkspaceGoal')?.value || '').trim());
    const hasFreshPlan = Boolean(state.plannerResult) && !state.plannerDirty;
    if (step === 1) return hasTarget;
    if (step === 2) return hasGoal;
    if (step === 3) return hasFreshPlan && state.planConfirmed;
    return true;
}

function setGuidedStep(step) {
    state.guidedStep = Math.max(1, Math.min(4, Number(step || 1)));
    renderWorkspaceMode();
}

function markWorkspaceInputsChanged({ resetDraft = false } = {}) {
    state.plannerDirty = state.plannerResult
        ? true
        : Boolean(String($('aiWorkspaceGoal')?.value || '').trim());
    state.planConfirmed = false;
    if (resetDraft) {
        resetWorkspaceDraftContext();
    }
    renderWorkspace();
}

function setUiMode(mode) {
    state.uiMode = mode === 'advanced' ? 'advanced' : 'guided';
    renderWorkspaceMode();
}

function updateWorkspaceActionState() {
    const hasTarget = Boolean(String($('aiWorkspaceTargetSelect')?.value || '').trim());
    const hasGoal = Boolean(String($('aiWorkspaceGoal')?.value || '').trim());
    const planReady = Boolean(state.plannerResult) && !state.plannerDirty;
    const generateButton = $('aiWorkspaceGeneratePlan');
    const regenerateButton = $('aiWorkspaceRegeneratePlan');
    const confirmButton = $('aiWorkspaceConfirmPlan');
    const submitButton = $('aiWorkspaceSubmitTask');
    const detailButton = $('aiWorkspaceOpenDetail');
    const graphDetailButton = $('aiWorkspaceGraphOpenDetail');
    const continueEditButton = $('aiWorkspaceContinueEdit');

    if (generateButton) {
        generateButton.disabled = !hasTarget || !hasGoal;
        generateButton.title = !hasTarget
            ? '请先选择目标云机'
            : !hasGoal
                ? '请先填写任务描述'
                : '';
        generateButton.textContent = state.plannerResult ? '重新生成任务图' : '开始设计任务图';
    }

    if (regenerateButton) {
        regenerateButton.disabled = !hasTarget || !hasGoal;
        regenerateButton.title = !hasTarget
            ? '请先选择目标云机'
            : !hasGoal
                ? '请先填写任务描述'
                : '';
    }

    if (confirmButton) {
        confirmButton.disabled = !planReady || state.planConfirmed;
        confirmButton.title = !planReady
            ? '请先生成最新任务图草案'
            : state.planConfirmed
                ? '当前任务图已确认'
                : '';
        confirmButton.textContent = state.planConfirmed ? '任务图已确认' : '确认任务图';
    }

    if (submitButton) {
        submitButton.disabled = !state.planConfirmed || !planReady || !hasTarget;
        submitButton.title = !hasTarget
            ? '请先选择目标云机'
            : !planReady
                ? '请先生成最新任务图草案'
                : !state.planConfirmed
                    ? '请先确认任务图'
                    : '';
        applyPlannerSubmitState(
            submitButton,
            state.planConfirmed && planReady ? state.plannerResult : null,
            '下发执行',
        );
    }

    [detailButton, graphDetailButton].forEach((button) => {
        if (!button) return;
        button.disabled = !hasTarget;
        button.title = hasTarget ? '' : '请先选择目标云机';
    });

    if (continueEditButton) {
        continueEditButton.disabled = !state.plannerResult && !state.activeDraftId;
        continueEditButton.title = continueEditButton.disabled ? '当前没有可继续编辑的任务图草案' : '';
    }
}

function renderGuidedNavigation() {
    const prevButton = $('aiWorkspaceGuidedPrev');
    const nextButton = $('aiWorkspaceGuidedNext');
    if (!prevButton || !nextButton) return;

    prevButton.disabled = state.guidedStep <= 1;
    const nextLabels = {
        1: '继续补全约束',
        2: '生成任务图',
        3: state.planConfirmed ? '进入执行步骤' : '确认任务图',
        4: '保持当前步骤',
    };
    nextButton.textContent = nextLabels[state.guidedStep] || '下一步';
    nextButton.disabled = state.guidedStep === 4 ? !state.planConfirmed : false;
}

function renderWorkspaceMode() {
    const root = $('aiWorkspaceRoot');
    const guidedButton = $('aiWorkspaceModeGuided');
    const advancedButton = $('aiWorkspaceModeAdvanced');
    const modeHint = $('aiWorkspaceModeHint');
    const inputTitle = $('aiWorkspaceInputTitle');
    const graphTitle = $('aiWorkspaceGraphTitle');
    const stepNote = $('aiWorkspaceStepNote');
    const primaryActions = $('aiWorkspacePrimaryActions');
    const guidedActions = $('aiWorkspaceGuidedActions');
    const referencePanel = $('aiWorkspaceReferencePanel');
    const runsPanel = $('aiWorkspaceRunsPanel');

    if (root) {
        root.dataset.mode = state.uiMode;
        root.dataset.step = String(state.guidedStep);
    }

    if (guidedButton && advancedButton) {
        guidedButton.className = `btn ${state.uiMode === 'guided' ? 'btn-primary' : 'btn-secondary'} btn-sm`;
        advancedButton.className = `btn ${state.uiMode === 'advanced' ? 'btn-primary' : 'btn-secondary'} btn-sm`;
    }

    if (modeHint) {
        modeHint.textContent = state.uiMode === 'guided'
            ? '引导模式会按步骤完成任务图设计，非关键上下文延后暴露。'
            : '高级模式会展示完整上下文，但仍复用同一套任务图、历史参考和执行状态。';
    }

    const currentStepConfig = GUIDED_STEPS.find((item) => item.step === state.guidedStep) || GUIDED_STEPS[0];
    if (inputTitle) {
        inputTitle.textContent = state.uiMode === 'guided'
            ? `${currentStepConfig.step}. ${currentStepConfig.title}`
            : '设计输入';
    }
    if (graphTitle) {
        graphTitle.textContent = state.uiMode === 'guided' && state.guidedStep < 3
            ? '任务图预览'
            : '任务图主画布';
    }
    if (stepNote) {
        const textNode = stepNote.querySelector('.task-guide-text');
        const titleNode = stepNote.querySelector('.task-guide-title');
        if (textNode) {
            textNode.textContent = state.uiMode === 'guided'
                ? currentStepConfig.hint
                : '高级模式会保留完整输入、任务图和参考上下文，但设计与执行仍保持前后顺序。';
        }
        if (titleNode) {
            titleNode.textContent = state.uiMode === 'guided'
                ? `当前步骤：${currentStepConfig.title}`
                : '高级模式说明';
        }
    }

    if (primaryActions && guidedActions) {
        const isGuided = state.uiMode === 'guided';
        guidedActions.style.display = isGuided ? 'flex' : 'none';
        Array.from(primaryActions.children).forEach((button) => {
            button.hidden = false;
        });
        if (isGuided) {
            $('aiWorkspaceGeneratePlan').hidden = state.guidedStep !== 2 && state.guidedStep !== 3;
            $('aiWorkspaceConfirmPlan').hidden = state.guidedStep !== 3;
            $('aiWorkspaceSubmitTask').hidden = state.guidedStep !== 4;
            $('aiWorkspaceOpenDetail').hidden = state.guidedStep !== 4;
            document.querySelector('[data-nav-target="tab-tasks"]')?.toggleAttribute('hidden', state.guidedStep !== 4);
            document.querySelector('[data-nav-target="tab-accounts"]')?.toggleAttribute('hidden', state.guidedStep !== 4);
        } else {
            document.querySelector('[data-nav-target="tab-tasks"]')?.removeAttribute('hidden');
            document.querySelector('[data-nav-target="tab-accounts"]')?.removeAttribute('hidden');
        }
    }

    if (referencePanel) {
        referencePanel.style.opacity = state.uiMode === 'guided' && state.guidedStep < 3 ? '0.65' : '1';
    }
    if (runsPanel) {
        runsPanel.style.opacity = state.uiMode === 'guided' && state.guidedStep < 4 ? '0.65' : '1';
    }

    document.querySelectorAll('.ai-workspace-step').forEach((button) => {
        const step = Number(button.getAttribute('data-step') || 0);
        button.classList.toggle('active', step === state.guidedStep);
        button.classList.toggle('done', step < state.guidedStep || (step === 3 && state.planConfirmed));
    });

    renderGuidedNavigation();
}

function renderWorkspaceGraphSummary() {
    const host = $('aiWorkspaceGraphSummary');
    if (!host) return;
    clearElement(host);

    const title = document.createElement('div');
    title.className = 'task-summary-title';
    const text = document.createElement('div');
    text.className = 'task-summary-text';

    if (!state.plannerResult) {
        title.textContent = state.uiMode === 'guided' && state.guidedStep < 3
            ? '当前步骤还未进入任务图确认'
            : '任务图尚未生成';
        text.textContent = state.uiMode === 'guided' && state.guidedStep < 3
            ? '先完成前两步的目标与约束输入，再生成任务图草案。'
            : '填写输入后，点击“开始设计任务图”。当前版本只支持生成、确认、重新生成，不提供节点级手工编辑。';
        host.append(title, text);
        return;
    }

    title.textContent = String(state.plannerResult.display_name || '当前任务图草案');
    if (state.plannerDirty) {
        text.textContent = '输入已变更，当前画布展示的是旧版本草案。请重新生成任务图后再确认或执行。';
    } else if (state.planConfirmed) {
        text.textContent = '当前任务图已确认，可以直接下发执行，或进入设备详情进行单设备执行与接管。';
    } else {
        text.textContent = '任务图草案已生成，请检查控制流、成功判定、失败出口和人工接管点，再确认任务图。';
    }

    const tags = document.createElement('div');
    tags.className = 'task-guide-tags';
    [
        currentWorkspaceTargetSummary(),
        getSelectedWorkspaceAppId() ? `应用 ${getSelectedWorkspaceAppId()}` : '',
        getSelectedWorkspaceAccount()?.account ? `账号 ${String(getSelectedWorkspaceAccount().account)}` : '未绑定账号',
        state.activeDraftId ? `草稿 ${state.activeDraftId}` : '新任务图',
        state.planConfirmed ? '已确认' : state.plannerDirty ? '待重新生成' : '待确认',
    ].filter(Boolean).forEach((line) => {
        const chip = document.createElement('span');
        chip.className = 'task-guide-tag';
        chip.textContent = line;
        tags.appendChild(chip);
    });

    host.append(title, text, tags);
}

function renderWorkspaceGraphExecution() {
    const host = $('aiWorkspaceGraphExecution');
    const status = $('aiWorkspaceGraphStatus');
    if (!host) return;
    clearElement(host);

    const selectedHistory = selectedHistoryItem();
    const historyDraft = normalizeDraftSummary(selectedHistory);
    const execution = state.plannerResult?.execution || {};
    const followUp = state.plannerResult?.follow_up || {};
    const blockingReasons = Array.isArray(execution?.blocking_reasons) ? execution.blocking_reasons : [];
    const missing = Array.isArray(followUp?.missing) ? followUp.missing : [];

    if (!state.plannerResult) {
        if (status) {
            status.textContent = state.uiMode === 'guided' && state.guidedStep < 3
                ? '等待进入任务图确认步骤'
                : '等待生成任务图草案';
        }
        const block = createMetaBlock('当前状态', [
            state.uiMode === 'guided' && state.guidedStep < 3
                ? '先完成前两步输入，再生成任务图草案。'
                : '还没有任务图草案。',
            '如需继续已有草稿，请从右侧历史会话选择“继续编辑草稿”。',
        ]);
        if (block) host.appendChild(block);
        return;
    }

    if (status) {
        status.textContent = state.plannerDirty
            ? '当前草案已过期，等待重新生成'
            : state.planConfirmed
                ? '任务图已确认，可进入执行'
                : '任务图草案已生成，等待确认';
    }

    [
        createMetaBlock('任务图状态', [
            state.plannerResult?.operator_summary ? String(state.plannerResult.operator_summary) : '',
            state.plannerDirty ? '输入已变更：请重新生成任务图' : '',
            state.planConfirmed ? '确认状态：已确认，可下发执行' : '确认状态：待确认',
        ]),
        createMetaBlock('执行门槛', [
            execution?.runtime ? `运行时：${String(execution.runtime)}` : '',
            execution?.mode ? `模式：${String(execution.mode)}` : '',
            execution?.readiness ? `就绪度：${String(execution.readiness)}` : '',
            blockingReasons.length > 0 ? `阻塞原因：${blockingReasons.join('、')}` : '当前无明确阻塞',
        ]),
        createMetaBlock('补充信息', [
            followUp?.message ? String(followUp.message) : '',
            missing.length > 0 ? `仍缺少：${missing.join('、')}` : '',
            state.plannerResult?.account?.execution_hint ? String(state.plannerResult.account.execution_hint) : '',
        ]),
        createMetaBlock('挑战处理策略', workspaceCapabilityItems().map((item) => `${item.title}：${item.status}；${item.text}`)),
        createMetaBlock('参考上下文', [
            selectedHistory ? `当前参考会话：${String(selectedHistory.display_name || '')}` : '当前没有引用历史会话',
            historyDraft?.declarative_binding?.script_title
                ? `参考脚本：${String(historyDraft.declarative_binding.script_title)}`
                : '',
            historyDraft?.declarative_binding?.current_stage?.stage_title
                ? `参考阶段：${String(historyDraft.declarative_binding.current_stage.stage_title)}`
                : '',
            historyDraft?.message ? String(historyDraft.message) : '',
        ]),
    ].filter(Boolean).forEach((block) => host.appendChild(block));
}

function renderReferenceContextVisibility() {
    const list = $('aiWorkspaceHistoryList');
    const detail = $('aiWorkspaceHistoryDetail');
    if (!list || !detail) return;

    if (state.uiMode === 'guided' && state.guidedStep < 3) {
        list.style.display = 'none';
        detail.innerHTML = '<div class="text-muted">引导模式会在第 3 步之后展开历史会话、失败建议和蒸馏线索，避免参考信息过早干扰主流程。</div>';
    } else {
        list.style.display = '';
        renderAiHistoryDetail(selectedHistoryItem());
    }
}

function renderWorkspace() {
    renderWorkspaceMode();
    updateWorkspaceActionState();
    renderWorkspaceCapabilities();
    renderWorkspaceGraphSummary();
    renderWorkspaceGraphExecution();
    renderReferenceContextVisibility();
}

function renderAiHistoryDetail(item) {
    const host = $('aiWorkspaceHistoryDetail');
    if (!host) return;
    clearElement(host);

    if (!item) {
        const empty = document.createElement('div');
        empty.className = 'text-muted';
        empty.textContent = '选择一条历史 AI 会话后，可在这里查看参考价值、失败建议、声明脚本绑定，以及“作为参考”或“继续编辑草稿”两种动作。';
        host.appendChild(empty);
        return;
    }

    const draft = normalizeDraftSummary(item);
    const exit = normalizeDraftExit(item);
    const latestRunAsset = normalizeLatestRunAsset(item);
    const declarativeBinding = draft?.declarative_binding && typeof draft.declarative_binding === 'object'
        ? draft.declarative_binding
        : {};
    const failureAdvice = draft?.latest_failure_advice && typeof draft.latest_failure_advice === 'object'
        ? draft.latest_failure_advice
        : {};

    const header = document.createElement('div');
    header.className = 'ai-workspace-history-header';

    const title = document.createElement('div');
    title.className = 'list-item-title';
    title.textContent = String(item?.display_name || draft?.display_name || 'AI 会话详情');
    header.appendChild(title);

    const meta = document.createElement('div');
    meta.className = 'list-item-meta';
    meta.textContent = [
        `草稿 ${String(item?.draft_id || '').trim() || '--'}`,
        item?.last_task_id ? `任务 ${String(item.last_task_id)}` : '',
        item?.updated_at ? `更新 ${formatUpdatedAt(item.updated_at)}` : '',
    ].filter(Boolean).join(' · ');
    header.appendChild(meta);
    host.appendChild(header);

    const badges = document.createElement('div');
    badges.className = 'task-guide-tags';
    [
        String(item?.status || '').trim() || 'unknown',
        exit?.action ? formatExitAction(exit.action) : '',
        draft?.distill_assessment?.latest_qualification
            ? formatQualification(draft.distill_assessment.latest_qualification)
            : '',
        latestRunAsset?.memory_summary?.reuse_priority
            ? formatReusePriority(latestRunAsset.memory_summary.reuse_priority)
            : '',
    ].filter(Boolean).forEach((text, index) => {
        const chip = document.createElement('span');
        chip.className = index === 0 ? 'badge' : 'task-guide-tag';
        chip.textContent = text;
        badges.appendChild(chip);
    });
    host.appendChild(badges);

    [
        createMetaBlock('参考结论', [
            draft?.message,
            item?.app_id ? `应用：${String(item.app_id)}` : '',
            item?.account ? `账号：${String(item.account)}` : '',
            Number(draft?.success_threshold || 0) > 0
                ? `样本进度：${Number(draft?.success_count || 0)}/${Number(draft?.success_threshold || 0)}`
                : '',
        ]),
        createMetaBlock('声明脚本绑定', [
            declarativeBinding?.summary,
            declarativeBinding?.script_title ? `主脚本：${String(declarativeBinding.script_title)}` : '',
            declarativeBinding?.current_stage?.stage_title
                ? `当前阶段：${String(declarativeBinding.current_stage.stage_title)}`
                : '',
            typeof declarativeBinding?.script_count === 'number'
                ? `脚本数量：${Number(declarativeBinding.script_count)}`
                : '',
        ]),
        createMetaBlock('最近运行资产', [
            latestRunAsset?.terminal_message || '',
            latestRunAsset?.memory_summary?.recommended_action
                ? `推荐动作：${formatReuseAction(latestRunAsset.memory_summary.recommended_action)}`
                : '',
            Array.isArray(latestRunAsset?.retained_value) && latestRunAsset.retained_value.length > 0
                ? `保留资产：${latestRunAsset.retained_value.join('、')}`
                : '',
            Array.isArray(latestRunAsset?.learned_assets?.observed_state_ids)
                && latestRunAsset.learned_assets.observed_state_ids.length > 0
                ? `观测状态：${latestRunAsset.learned_assets.observed_state_ids.slice(0, 4).join('、')}`
                : '',
        ]),
        createMetaBlock('失败建议', [
            failureAdvice?.summary || '',
            Array.isArray(failureAdvice?.suggestions) && failureAdvice.suggestions.length > 0
                ? `建议：${failureAdvice.suggestions.join('；')}`
                : '',
            failureAdvice?.suggested_prompt ? `推荐提示词：${String(failureAdvice.suggested_prompt)}` : '',
        ]),
    ].filter(Boolean).forEach((block) => host.appendChild(block));

    const actions = document.createElement('div');
    actions.className = 'ai-workspace-history-actions';

    const referenceButton = document.createElement('button');
    referenceButton.type = 'button';
    referenceButton.className = 'btn btn-secondary btn-sm';
    referenceButton.textContent = '作为当前设计参考';
    referenceButton.onclick = () => {
        state.selectedHistoryId = String(item?.draft_id || '').trim();
        renderAiHistory(state.historyCache);
        toast.info('已将该历史会话设为当前任务图的参考上下文');
    };
    actions.appendChild(referenceButton);

    const loadButton = document.createElement('button');
    loadButton.type = 'button';
    loadButton.className = 'btn btn-secondary btn-sm';
    loadButton.textContent = '继续编辑草稿';
    loadButton.disabled = !item?.can_edit;
    loadButton.onclick = () => {
        void loadHistoryItemIntoWorkspace(item);
    };
    actions.appendChild(loadButton);

    const distillButton = document.createElement('button');
    const distillState = resolveDistillButtonState(item);
    distillButton.type = 'button';
    distillButton.className = 'btn btn-secondary btn-sm';
    distillButton.textContent = distillState.label;
    distillButton.disabled = Boolean(distillState.disabled);
    distillButton.title = distillState.title || '';
    distillButton.onclick = () => {
        void distillHistoryItem(item);
    };
    actions.appendChild(distillButton);

    const saveButton = document.createElement('button');
    saveButton.type = 'button';
    saveButton.className = 'btn btn-secondary btn-sm';
    saveButton.textContent = '保存可复用项';
    saveButton.disabled = !item?.can_save;
    saveButton.onclick = async () => {
        await openAiDraftSaveModal(String(item?.draft_id || '').trim());
    };
    actions.appendChild(saveButton);

    host.appendChild(actions);
}

function setSelectedAiHistory(draftId) {
    state.selectedHistoryId = String(draftId || '').trim();
    renderAiHistory(state.historyCache);
}

function renderAiHistory(items) {
    const host = $('aiWorkspaceHistoryList');
    if (!host) return;
    clearElement(host);
    host.style.display = state.uiMode === 'guided' && state.guidedStep < 3 ? 'none' : '';
    state.historyCache = Array.isArray(items) ? items : [];

    if (state.historyCache.length === 0) {
        state.selectedHistoryId = '';
        const empty = document.createElement('div');
        empty.className = 'text-muted';
        empty.style.padding = '16px';
        empty.textContent = '暂无 AI 会话记录';
        host.appendChild(empty);
        renderAiHistoryDetail(null);
        return;
    }

    const hasSelected = state.historyCache.some(
        (item) => String(item?.draft_id || '').trim() === state.selectedHistoryId,
    );
    if (!hasSelected) {
        state.selectedHistoryId = String(state.historyCache[0]?.draft_id || '').trim();
    }

    state.historyCache.forEach((item) => {
        const draftId = String(item?.draft_id || '').trim();
        const row = document.createElement('div');
        row.className = 'list-item';
        if (draftId === state.selectedHistoryId) {
            row.classList.add('active');
        }
        row.onclick = () => {
            setSelectedAiHistory(draftId);
        };

        const content = document.createElement('div');
        content.className = 'list-item-content';

        const title = document.createElement('div');
        title.className = 'list-item-title';
        title.textContent = String(item?.display_name || '未命名 AI 会话');

        const meta = document.createElement('div');
        meta.className = 'list-item-meta';
        meta.textContent = [
            item?.app_id ? `应用 ${String(item.app_id)}` : '',
            item?.account ? `账号 ${String(item.account)}` : '',
            item?.updated_at ? `更新 ${formatUpdatedAt(item.updated_at)}` : '',
        ].filter(Boolean).join(' · ');

        const badges = document.createElement('div');
        badges.className = 'task-guide-tags';
        const latestRunAsset = normalizeLatestRunAsset(item);
        [
            String(item?.status || 'unknown'),
            item?.can_edit ? '可继续编辑' : '',
            item?.can_save ? '可沉淀' : '',
            latestRunAsset?.memory_summary?.reuse_priority
                ? formatReusePriority(latestRunAsset.memory_summary.reuse_priority)
                : '',
        ].filter(Boolean).forEach((text, index) => {
            const badge = document.createElement('span');
            badge.className = index === 0 ? 'badge' : 'task-guide-tag';
            badge.textContent = text;
            badges.appendChild(badge);
        });

        content.append(title, meta, badges);

        const actions = document.createElement('div');
        actions.className = 'ai-workspace-history-row-actions';

        const referenceButton = document.createElement('button');
        referenceButton.type = 'button';
        referenceButton.className = 'btn btn-secondary btn-sm';
        referenceButton.textContent = '作为参考';
        referenceButton.onclick = (event) => {
            stopEvent(event);
            state.selectedHistoryId = draftId;
            renderAiHistory(state.historyCache);
            toast.info('已将该历史会话设为当前设计参考');
        };
        actions.appendChild(referenceButton);

        const continueButton = document.createElement('button');
        continueButton.type = 'button';
        continueButton.className = 'btn btn-secondary btn-sm';
        continueButton.textContent = '继续编辑';
        continueButton.disabled = !item?.can_edit;
        continueButton.onclick = (event) => {
            stopEvent(event);
            void loadHistoryItemIntoWorkspace(item);
        };
        actions.appendChild(continueButton);

        row.append(content, actions);
        host.appendChild(row);
    });

    if (!(state.uiMode === 'guided' && state.guidedStep < 3)) {
        renderAiHistoryDetail(selectedHistoryItem());
    }
}

function renderActiveRuns(tasks) {
    const host = $('aiWorkspaceActiveRuns');
    if (!host) return;
    clearElement(host);

    if (state.uiMode === 'guided' && state.guidedStep < 4) {
        const empty = document.createElement('div');
        empty.className = 'text-muted';
        empty.style.padding = '16px';
        empty.textContent = '进入第 4 步后，这里会展示运行中的 AI 任务与执行协作入口。';
        host.appendChild(empty);
        return;
    }

    if (!Array.isArray(tasks) || tasks.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'text-muted';
        empty.style.padding = '16px';
        empty.textContent = '当前没有运行中的 AI 任务';
        host.appendChild(empty);
        return;
    }

    tasks.forEach((task) => {
        const row = document.createElement('div');
        row.className = 'list-item';

        const title = document.createElement('div');
        title.className = 'list-item-title';
        title.textContent = String(task?.display_name || task?.task_name || 'AI 任务');

        const meta = document.createElement('div');
        meta.className = 'list-item-meta';
        meta.textContent = [
            `状态 ${String(task?.status || 'unknown')}`,
            describeTargets(task?.targets),
        ].join(' · ');

        row.append(title, meta);
        host.appendChild(row);
    });
}

function renderTargetOptions(devices) {
    const select = $('aiWorkspaceTargetSelect');
    const hint = $('aiWorkspaceTargetHint');
    if (!select) return;

    const previous = String(select.value || '').trim();
    select.replaceChildren();
    const defaultOption = document.createElement('option');
    defaultOption.value = '';
    defaultOption.textContent = '请选择一个在线云机';
    select.appendChild(defaultOption);

    let onlineCount = 0;
    (Array.isArray(devices) ? devices : []).forEach((device) => {
        (Array.isArray(device?.cloud_machines) ? device.cloud_machines : []).forEach((unit) => {
            if (String(unit?.availability_state || '').trim() !== 'available') return;
            onlineCount += 1;
            const option = document.createElement('option');
            option.value = `${Number(device?.device_id || 0)}-${Number(unit?.cloud_id || 0)}`;
            option.textContent = `云机 #${Number(device?.device_id || 0)}-${Number(unit?.cloud_id || 0)} · ${String(unit?.machine_model_name || '未识别机型')}`;
            select.appendChild(option);
        });
    });

    const hasPrevious = Array.from(select.options).some((option) => option.value === previous);
    select.value = hasPrevious ? previous : '';
    if (hint) {
        hint.textContent = onlineCount > 0
            ? `当前共有 ${onlineCount} 个在线云机可作为任务图的执行目标`
            : '当前没有在线云机，请先在设备集群中恢复可用节点';
    }
}

async function loadWorkspaceApps() {
    const select = $('aiWorkspaceAppSelect');
    if (!select) return;
    const previous = getSelectedWorkspaceAppId() || 'default';
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
    toggleCustomAppFields();
}

async function loadWorkspaceAccounts(appId = getSelectedWorkspaceAppId()) {
    if (String($('aiWorkspaceAppSelect')?.value || '').trim() === CUSTOM_APP_OPTION && !String(appId || '').trim()) {
        state.accounts = [];
        renderEmptyAccountSelect('-- 先填写应用 ID --');
        syncWorkspaceAccountRequirementUi();
        return;
    }

    const params = new URLSearchParams();
    if (appId) {
        params.set('app_id', appId);
    }
    const response = await fetchJson(`/api/data/accounts/parsed${params.toString() ? `?${params.toString()}` : ''}`, {
        silentErrors: true,
    });
    if (!response.ok) {
        state.accounts = [];
        renderEmptyAccountSelect('-- 账号加载失败 --');
        syncWorkspaceAccountRequirementUi();
        return;
    }

    state.accounts = (response.data?.accounts || []).filter((account) => account.status === 'ready');
    const select = $('aiWorkspaceAccountSelect');
    if (!select) return;
    select.replaceChildren();
    const emptyOption = document.createElement('option');
    emptyOption.value = '';
    emptyOption.textContent = `-- 不绑定账号 (${state.accounts.length} 个就绪) --`;
    select.appendChild(emptyOption);
    state.accounts.forEach((account, index) => {
        const option = document.createElement('option');
        option.value = String(index);
        option.textContent = String(account.account || '').trim();
        select.appendChild(option);
    });
    syncWorkspaceAccountRequirementUi();
}

async function loadAiHistory() {
    const response = await fetchJson('/api/ai_dialog/history?limit=8', { silentErrors: true });
    renderAiHistory(response.ok ? response.data : []);
}

async function loadActiveRuns() {
    const response = await fetchJson('/api/tasks/', { silentErrors: true });
    if (!response.ok) {
        renderActiveRuns([]);
        return;
    }
    const tasks = Array.isArray(response.data) ? response.data : [];
    const active = tasks.filter((task) => {
        const taskName = String(task?.task_name || task?.task || '').trim();
        const status = String(task?.status || '').trim().toLowerCase();
        return taskName === 'agent_executor'
            && ['pending', 'running', 'paused', 'pause_requested'].includes(status);
    });
    renderActiveRuns(active);
}

async function requestWorkspacePlanner({ force = false, silent = false } = {}) {
    const inputs = getWorkspaceInputs();
    if (!inputs.goal) {
        resetPlannerState();
        state.plannerDirty = false;
        clearPlannerCard(plannerElements(), {
            submitButton: $('aiWorkspaceSubmitTask'),
            submitLabel: '下发执行',
        });
        renderWorkspace();
        return null;
    }

    const signature = currentPlannerSignature();
    if (!force && state.plannerResult && signature === state.plannerSignature && !state.plannerDirty) {
        renderWorkspace();
        return state.plannerResult;
    }

    renderPlannerStateLoading(plannerElements(), {
        submitButton: $('aiWorkspaceSubmitTask'),
        submitLabel: '下发执行',
    });
    const response = await fetchJson('/api/ai_dialog/planner', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            goal: inputs.goal,
            app_id: inputs.appId,
            app_display_name: inputs.appDisplayName || null,
            package_name: inputs.packageName || null,
            account_required: inputs.accountRequired,
            selected_account: String(inputs.account?.account || '').trim() || null,
            use_account_twofa: inputs.autoTotpEnabled,
            advanced_prompt: buildCombinedAdvancedPrompt(inputs) || null,
        }),
        silentErrors: true,
    });

    if (!response.ok) {
        if (!silent) {
            toast.error(String(response.data?.detail || '任务图生成失败'));
        }
        clearPlannerCard(plannerElements(), {
            submitButton: $('aiWorkspaceSubmitTask'),
            submitLabel: '下发执行',
        });
        renderWorkspace();
        return null;
    }

    state.plannerSignature = signature;
    state.plannerResult = response.data;
    state.plannerDirty = false;
    state.planConfirmed = false;
    renderPlannerResult(plannerElements(), state.plannerResult, {
        submitButton: $('aiWorkspaceSubmitTask'),
        submitLabel: '下发执行',
    });
    renderWorkspace();
    return state.plannerResult;
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
        await loadAiHistory();
        return;
    }
    toast.success('已生成蒸馏草稿');
    await loadAiWorkspace();
}

function setWorkspaceFields(seed = {}) {
    $('aiWorkspaceGoal').value = String(seed.goal || '').trim();
    $('aiWorkspaceSuccessCriteria').value = String(seed.successCriteria || '').trim();
    $('aiWorkspaceFailureGuard').value = String(seed.failureGuard || '').trim();
    $('aiWorkspaceTakeoverRules').value = String(seed.takeoverRules || '').trim();
    $('aiWorkspaceAdvancedPrompt').value = String(seed.advancedPrompt || '').trim();
    $('aiWorkspaceNoAccountRequired').checked = seed.accountRequired === false;
    $('aiWorkspaceAutoTotpEnabled').checked = seed.autoTotpEnabled !== false;
    syncWorkspaceAccountRequirementUi();
}

async function applyWorkspaceSeed(seed = {}) {
    const appId = String(seed.appId || seed.app_id || 'default').trim() || 'default';
    const appDisplayName = String(seed.appDisplayName || seed.app_display_name || '').trim();
    const packageName = String(seed.packageName || seed.package_name || seed.package || '').trim();
    const accountName = String(seed.accountName || seed.account || '').trim();
    const accountRequired = seed.accountRequired !== false;

    state.activeDraftId = String(seed.draftId || seed.draft_id || '').trim();
    state.activeSuccessThreshold = Number(seed.successThreshold || seed.success_threshold || 0) || null;

    setWorkspaceFields(seed);
    await loadWorkspaceApps();
    const appSelect = $('aiWorkspaceAppSelect');
    if (appSelect) {
        const hasExistingOption = Array.from(appSelect.options).some((option) => option.value === appId);
        appSelect.value = hasExistingOption ? appId : CUSTOM_APP_OPTION;
    }
    $('aiWorkspaceCustomAppId').value = appSelect?.value === CUSTOM_APP_OPTION ? appId : '';
    $('aiWorkspaceCustomDisplayName').value = appSelect?.value === CUSTOM_APP_OPTION ? appDisplayName : '';
    $('aiWorkspaceCustomPackageName').value = appSelect?.value === CUSTOM_APP_OPTION ? packageName : '';
    toggleCustomAppFields();

    await loadWorkspaceAccounts(appId);
    $('aiWorkspaceNoAccountRequired').checked = !accountRequired;
    syncWorkspaceAccountRequirementUi();
    const accountSelect = $('aiWorkspaceAccountSelect');
    if (accountSelect && accountRequired) {
        const preferredIndex = state.accounts.findIndex((account) => String(account?.account || '').trim() === accountName);
        accountSelect.value = preferredIndex >= 0 ? String(preferredIndex) : '';
    }

    resetPlannerState();
    state.plannerDirty = Boolean(String(seed.goal || '').trim());
    clearPlannerCard(plannerElements(), {
        submitButton: $('aiWorkspaceSubmitTask'),
        submitLabel: '下发执行',
    });
    renderWorkspace();
}

async function loadHistoryItemIntoWorkspace(item) {
    const draftId = String(item?.draft_id || '').trim();
    if (!draftId) return;
    state.selectedHistoryId = draftId;
    const response = await fetchJson(`/api/tasks/drafts/${encodeURIComponent(draftId)}/snapshot`, {
        silentErrors: true,
    });
    if (!response.ok) {
        toast.error(String(response.data?.detail || '读取 AI 会话失败'));
        return;
    }

    const snapshot = response.data?.snapshot || {};
    const payload = snapshot.payload || {};
    const identity = snapshot.identity || {};
    const parsedConstraints = parseCombinedAdvancedPrompt(String(payload.advanced_prompt || '').trim());

    await applyWorkspaceSeed({
        goal: String(payload.goal || '').trim(),
        appId: String(payload.app_id || identity.app_id || 'default').trim() || 'default',
        appDisplayName: String(payload.app_display_name || '').trim(),
        packageName: String(payload.package_name || payload.package || '').trim(),
        accountRequired: payload.account_required !== false,
        accountName: String(payload.account || identity.account || '').trim(),
        successCriteria: parsedConstraints.successCriteria,
        failureGuard: parsedConstraints.failureGuard,
        takeoverRules: parsedConstraints.takeoverRules,
        advancedPrompt: parsedConstraints.advancedPrompt,
        autoTotpEnabled: payload.use_account_twofa !== false,
        draftId: String(response.data?.draft_id || draftId),
        successThreshold: Number(response.data?.success_threshold || 0) || null,
    });

    await requestWorkspacePlanner({ force: true, silent: true });
    state.guidedStep = 3;
    renderWorkspace();
    toast.info('已载入该草稿，当前处于继续编辑状态');
}

async function resolveSelectedWorkspaceUnit() {
    const target = String($('aiWorkspaceTargetSelect')?.value || '').trim();
    if (!target) {
        toast.warn('请先选择目标云机');
        return null;
    }
    const [deviceIdText, cloudIdText] = target.split('-');
    const deviceId = Number(deviceIdText || 0);
    const cloudId = Number(cloudIdText || 0);
    if (!deviceId || !cloudId) {
        toast.warn('目标云机格式无效');
        return null;
    }

    const response = await refreshDevicesSnapshot({ force: true, silentErrors: true });
    if (!response.ok) {
        toast.error('刷新设备列表失败');
        return null;
    }

    for (const device of response.data || []) {
        if (Number(device?.device_id || 0) !== deviceId) continue;
        const unit = Array.isArray(device?.cloud_machines)
            ? device.cloud_machines.find((entry) => Number(entry?.cloud_id || 0) === cloudId)
            : null;
        if (!unit) break;
        return {
            ...unit,
            parent_ip: device.ip,
            parent_id: device.device_id,
        };
    }
    toast.error('未找到目标云机，请先刷新设备列表');
    return null;
}

async function generatePlanAndAdvance() {
    const plan = await requestWorkspacePlanner({ force: true });
    if (!plan) return false;
    if (state.uiMode === 'guided') {
        state.guidedStep = 3;
    }
    renderWorkspace();
    return true;
}

function confirmCurrentPlan({ advance = false } = {}) {
    if (!state.plannerResult || state.plannerDirty) {
        toast.warn('请先生成最新任务图草案');
        return false;
    }
    state.planConfirmed = true;
    if (advance && state.uiMode === 'guided') {
        state.guidedStep = 4;
    }
    renderWorkspace();
    toast.success('任务图已确认，可以下发执行');
    return true;
}

async function submitCurrentPlan() {
    if (!state.planConfirmed || !state.plannerResult || state.plannerDirty) {
        toast.warn('请先确认最新任务图');
        return false;
    }

    const unit = await resolveSelectedWorkspaceUnit();
    if (!unit) return false;

    const inputs = getWorkspaceInputs();
    const rawPayload = buildAiDialogPayload({
        goal: inputs.goal,
        appId: inputs.appId,
        appDisplayName: inputs.appDisplayName,
        packageName: inputs.packageName,
        accountRequired: inputs.accountRequired,
        account: inputs.account,
        includeTwofaSecret: inputs.autoTotpEnabled,
        advancedPrompt: buildCombinedAdvancedPrompt(inputs),
    });
    if (!rawPayload) {
        toast.warn('请填写任务描述');
        return false;
    }

    const result = await submitAiTaskForUnit(unit, {
        rawPayload,
        plan: state.plannerResult,
        draftId: state.activeDraftId,
        successThreshold: state.activeSuccessThreshold,
        closeDialog: false,
    });
    if (result.ok) {
        await loadAiWorkspace();
        return true;
    }
    return false;
}

async function advanceGuidedStep() {
    if (state.guidedStep === 1) {
        if (!canAdvanceGuidedStep(1)) {
            toast.warn('请先选择目标云机');
            return;
        }
        setGuidedStep(2);
        return;
    }
    if (state.guidedStep === 2) {
        if (!canAdvanceGuidedStep(2)) {
            toast.warn('请先填写任务描述');
            return;
        }
        await generatePlanAndAdvance();
        return;
    }
    if (state.guidedStep === 3) {
        if (!state.planConfirmed) {
            confirmCurrentPlan({ advance: true });
            return;
        }
        setGuidedStep(4);
    }
}

async function handleGuidedStepClick(step) {
    if (step < state.guidedStep) {
        setGuidedStep(step);
        return;
    }
    if (step === state.guidedStep) return;
    while (state.guidedStep < step) {
        if (state.guidedStep === 4) return;
        const before = state.guidedStep;
        await advanceGuidedStep();
        if (state.guidedStep === before) {
            return;
        }
    }
}

export async function loadAiWorkspace() {
    state.taskCatalog = await loadTaskCatalog().catch(() => []);
    await Promise.all([
        loadWorkspaceApps(),
        refreshDevicesSnapshot({ force: true, silentErrors: true }),
    ]);

    const devicesResponse = await refreshDevicesSnapshot({ silentErrors: true, maxAgeMs: 5000 });
    renderTargetOptions(devicesResponse.ok ? devicesResponse.data : []);
    await loadWorkspaceAccounts();

    if (!state.plannerResult) {
        clearPlannerCard(plannerElements(), {
            submitButton: $('aiWorkspaceSubmitTask'),
            submitLabel: '下发执行',
        });
    }

    renderWorkspace();
    syncWorkspaceAccountRequirementUi();

    await Promise.all([
        loadDrafts(),
        loadMetrics(),
        loadAiHistory(),
        loadActiveRuns(),
    ]);
}

function bindWorkspaceInputs() {
    const markGoalChange = () => {
        markWorkspaceInputsChanged();
    };
    const markConfigChange = () => {
        markWorkspaceInputsChanged({ resetDraft: true });
    };

    $('aiWorkspaceAppSelect').onchange = () => {
        toggleCustomAppFields();
        markConfigChange();
        void loadWorkspaceAccounts();
    };
    $('aiWorkspaceGoal').oninput = markGoalChange;
    $('aiWorkspaceSuccessCriteria').oninput = markGoalChange;
    $('aiWorkspaceFailureGuard').oninput = markGoalChange;
    $('aiWorkspaceTakeoverRules').oninput = markGoalChange;
    $('aiWorkspaceAdvancedPrompt').oninput = markGoalChange;

    $('aiWorkspaceTargetSelect').onchange = () => {
        renderWorkspace();
    };

    ['aiWorkspaceCustomAppId', 'aiWorkspaceCustomDisplayName', 'aiWorkspaceCustomPackageName'].forEach((id) => {
        const input = $(id);
        if (input) {
            input.oninput = markConfigChange;
        }
    });

    $('aiWorkspaceAccountRefresh').onclick = () => {
        void loadWorkspaceAccounts();
    };
    $('aiWorkspaceAccountSelect').onchange = markGoalChange;
    $('aiWorkspaceNoAccountRequired').onchange = () => {
        syncWorkspaceAccountRequirementUi();
        markGoalChange();
    };
    $('aiWorkspaceAutoTotpEnabled').onchange = markGoalChange;
}

export function initAiWorkspace() {
    const navItem = document.querySelector('.nav-item[data-tab="tab-ai"]');
    if (navItem) {
        navItem.addEventListener('click', () => {
            void loadAiWorkspace();
        });
    }

    $('aiWorkspaceRefresh').onclick = () => {
        void loadAiWorkspace();
    };

    document.querySelectorAll('[data-nav-target]').forEach((button) => {
        button.addEventListener('click', () => {
            const target = String(button.getAttribute('data-nav-target') || '').trim();
            if (target) switchToTab(target);
        });
    });

    bindWorkspaceInputs();

    $('aiWorkspaceModeGuided').onclick = () => {
        setUiMode('guided');
    };
    $('aiWorkspaceModeAdvanced').onclick = () => {
        setUiMode('advanced');
    };

    document.querySelectorAll('.ai-workspace-step').forEach((button) => {
        button.addEventListener('click', () => {
            const step = Number(button.getAttribute('data-step') || 0);
            void handleGuidedStepClick(step);
        });
    });

    $('aiWorkspaceGuidedPrev').onclick = () => {
        if (state.guidedStep > 1) {
            setGuidedStep(state.guidedStep - 1);
        }
    };
    $('aiWorkspaceGuidedNext').onclick = () => {
        void advanceGuidedStep();
    };

    $('aiWorkspaceGeneratePlan').onclick = async () => {
        const created = await generatePlanAndAdvance();
        if (created) {
            toast.success('任务图草案已生成，请继续确认');
        }
    };

    $('aiWorkspaceRegeneratePlan').onclick = async () => {
        const created = await requestWorkspacePlanner({ force: true });
        if (created) {
            toast.info('已按当前输入重新生成任务图');
        }
    };

    $('aiWorkspaceContinueEdit').onclick = () => {
        if (!state.plannerResult && !state.activeDraftId) return;
        state.plannerDirty = true;
        state.planConfirmed = false;
        state.guidedStep = Math.min(state.guidedStep, 2);
        renderWorkspace();
        $('aiWorkspaceGoal')?.focus();
        toast.info('已切回编辑态，请修改输入后重新生成任务图');
    };

    $('aiWorkspaceConfirmPlan').onclick = () => {
        confirmCurrentPlan({ advance: state.uiMode === 'guided' });
    };

    $('aiWorkspaceSubmitTask').onclick = () => {
        void submitCurrentPlan();
    };

    const openDetail = () => {
        const target = String($('aiWorkspaceTargetSelect')?.value || '').trim();
        if (!target) return;
        const [deviceIdText, cloudIdText] = target.split('-');
        void openAiWorkspaceDetail({
            deviceId: Number(deviceIdText || 0),
            cloudId: Number(cloudIdText || 0),
        });
    };

    $('aiWorkspaceOpenDetail').onclick = openDetail;
    $('aiWorkspaceGraphOpenDetail').onclick = openDetail;

    renderWorkspace();

    if (window.location.hash === '#ai') {
        void loadAiWorkspace();
    }
}
