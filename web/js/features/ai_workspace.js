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

const $ = (id) => document.getElementById(id);
const CUSTOM_APP_OPTION = '__custom__';

let aiWorkspaceAccounts = [];
let plannerSignature = '';
let plannerResult = null;
let plannerDirty = false;
let planConfirmed = false;
let activeDraftId = '';
let activeSuccessThreshold = null;
let aiHistoryCache = [];
let selectedAiHistoryId = '';

function clearElement(element) {
    if (element) {
        element.replaceChildren();
    }
}

function resetWorkspaceDraftContext() {
    activeDraftId = '';
    activeSuccessThreshold = null;
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
    return aiWorkspaceAccounts[index] || null;
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
    if (!appId || appId === 'default') {
        hint.textContent = `当前显示系统账号池，共 ${readyCount} 个就绪账号`;
        return;
    }
    hint.textContent = `当前显示 ${appId} 账号池，共 ${readyCount} 个就绪账号`;
}

function buildMetaLines(values) {
    return values
        .map((item) => String(item || '').trim())
        .filter(Boolean)
        .slice(0, 4);
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

function selectedHistoryItem() {
    return aiHistoryCache.find((item) => String(item?.draft_id || '').trim() === selectedAiHistoryId) || null;
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

function currentPlannerSignature() {
    return JSON.stringify({
        goal: String($('aiWorkspaceGoal')?.value || '').trim(),
        app_id: getSelectedWorkspaceAppId(),
        app_display_name: getSelectedWorkspaceAppDisplayName(),
        package_name: getSelectedWorkspacePackageName(),
        selected_account: String(getSelectedWorkspaceAccount()?.account || '').trim(),
        advanced_prompt: String($('aiWorkspaceAdvancedPrompt')?.value || '').trim(),
    });
}

function resetPlannerState({ keepPlan = false } = {}) {
    if (!keepPlan) {
        plannerSignature = '';
        plannerResult = null;
    }
    planConfirmed = false;
}

function markWorkspaceInputsChanged({ resetDraft = false } = {}) {
    if (plannerResult) {
        plannerDirty = true;
    } else {
        plannerDirty = Boolean(String($('aiWorkspaceGoal')?.value || '').trim());
    }
    planConfirmed = false;
    if (resetDraft) {
        resetWorkspaceDraftContext();
    }
    renderWorkspaceGraph();
    updateWorkspaceActionState();
}

function updateWorkspaceActionState() {
    const hasTarget = Boolean(String($('aiWorkspaceTargetSelect')?.value || '').trim());
    const hasGoal = Boolean(String($('aiWorkspaceGoal')?.value || '').trim());
    const planReady = Boolean(plannerResult) && !plannerDirty;
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
        generateButton.textContent = plannerResult ? '重新生成任务图' : '开始设计任务图';
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
        confirmButton.disabled = !planReady || planConfirmed;
        confirmButton.title = !planReady
            ? '请先生成最新任务图草案'
            : planConfirmed
                ? '当前任务图已确认'
                : '';
        confirmButton.textContent = planConfirmed ? '任务图已确认' : '确认任务图';
    }

    if (submitButton) {
        submitButton.disabled = !planConfirmed || !planReady || !hasTarget;
        submitButton.title = !hasTarget
            ? '请先选择目标云机'
            : !planReady
                ? '请先生成最新任务图草案'
                : !planConfirmed
                    ? '请先确认任务图'
                    : '';
        applyPlannerSubmitState(submitButton, planConfirmed && planReady ? plannerResult : null, '下发执行');
    }

    if (detailButton) {
        detailButton.disabled = !hasTarget;
        detailButton.title = hasTarget ? '' : '请先选择目标云机';
    }
    if (graphDetailButton) {
        graphDetailButton.disabled = !hasTarget;
        graphDetailButton.title = hasTarget ? '' : '请先选择目标云机';
    }
    if (continueEditButton) {
        continueEditButton.disabled = !plannerResult && !activeDraftId;
        continueEditButton.title = continueEditButton.disabled ? '当前没有可继续编辑的任务图草案' : '';
    }
}

function renderWorkspaceGraphSummary() {
    const host = $('aiWorkspaceGraphSummary');
    if (!host) return;
    clearElement(host);

    const title = document.createElement('div');
    title.className = 'task-summary-title';

    const text = document.createElement('div');
    text.className = 'task-summary-text';

    if (!plannerResult) {
        title.textContent = '任务图尚未生成';
        text.textContent = '填写左侧输入后，点击“开始设计任务图”。当前版本只支持生成、确认、重新生成，不提供节点级手工编辑。';
        host.append(title, text);
        return;
    }

    title.textContent = String(plannerResult.display_name || '当前任务图草案');
    if (plannerDirty) {
        text.textContent = '输入已变更，当前画布展示的是旧版本草案。请重新生成任务图后再确认或执行。';
    } else if (planConfirmed) {
        text.textContent = '当前任务图已确认，可以直接下发执行，或进入设备详情进行单设备执行与接管。';
    } else {
        text.textContent = '任务图草案已生成，请结合右侧参考上下文检查控制流、成功判定、失败出口和人工接管点，再确认任务图。';
    }

    const tags = document.createElement('div');
    tags.className = 'task-guide-tags';
    [
        currentWorkspaceTargetSummary(),
        getSelectedWorkspaceAppId() ? `应用 ${getSelectedWorkspaceAppId()}` : '',
        getSelectedWorkspaceAccount()?.account ? `账号 ${String(getSelectedWorkspaceAccount().account)}` : '未绑定账号',
        activeDraftId ? `草稿 ${activeDraftId}` : '新任务图',
        planConfirmed ? '已确认' : plannerDirty ? '待重新生成' : '待确认',
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
    const execution = plannerResult?.execution || {};
    const followUp = plannerResult?.follow_up || {};
    const blockingReasons = Array.isArray(execution?.blocking_reasons) ? execution.blocking_reasons : [];
    const missing = Array.isArray(followUp?.missing) ? followUp.missing : [];

    if (!plannerResult) {
        if (status) {
            status.textContent = '等待生成任务图草案';
        }
        const block = createMetaBlock('当前状态', [
            '还没有任务图草案。',
            '左侧输入完成后点击“开始设计任务图”。',
            '如果要继续已有草稿，请从右侧历史会话选择“继续编辑草稿”。',
        ]);
        if (block) host.appendChild(block);
        return;
    }

    if (status) {
        status.textContent = plannerDirty
            ? '当前草案已过期，等待重新生成'
            : planConfirmed
                ? '任务图已确认，可进入执行'
                : '任务图草案已生成，等待确认';
    }

    [
        createMetaBlock('任务图状态', [
            plannerResult?.operator_summary ? String(plannerResult.operator_summary) : '',
            plannerDirty ? '输入已变更：请重新生成任务图' : '',
            planConfirmed ? '确认状态：已确认，可下发执行' : '确认状态：待确认',
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
            plannerResult?.account?.execution_hint ? String(plannerResult.account.execution_hint) : '',
        ]),
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

function renderWorkspaceGraph() {
    renderWorkspaceGraphSummary();
    renderWorkspaceGraphExecution();
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
        selectedAiHistoryId = String(item?.draft_id || '').trim();
        renderAiHistory(aiHistoryCache);
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
    selectedAiHistoryId = String(draftId || '').trim();
    renderAiHistory(aiHistoryCache);
}

function renderAiHistory(items) {
    const host = $('aiWorkspaceHistoryList');
    if (!host) return;
    clearElement(host);
    aiHistoryCache = Array.isArray(items) ? items : [];

    if (aiHistoryCache.length === 0) {
        selectedAiHistoryId = '';
        const empty = document.createElement('div');
        empty.className = 'text-muted';
        empty.style.padding = '16px';
        empty.textContent = '暂无 AI 会话记录';
        host.appendChild(empty);
        renderAiHistoryDetail(null);
        renderWorkspaceGraph();
        return;
    }

    const hasSelected = aiHistoryCache.some(
        (item) => String(item?.draft_id || '').trim() === selectedAiHistoryId,
    );
    if (!hasSelected) {
        selectedAiHistoryId = String(aiHistoryCache[0]?.draft_id || '').trim();
    }

    aiHistoryCache.forEach((item) => {
        const draftId = String(item?.draft_id || '').trim();
        const row = document.createElement('div');
        row.className = 'list-item';
        if (draftId === selectedAiHistoryId) {
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

        [
            String(item?.status || 'unknown'),
            item?.can_edit ? '可继续编辑' : '',
            item?.can_save ? '可沉淀' : '',
            normalizeLatestRunAsset(item)?.memory_summary?.reuse_priority
                ? formatReusePriority(normalizeLatestRunAsset(item).memory_summary.reuse_priority)
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
            selectedAiHistoryId = draftId;
            renderAiHistory(aiHistoryCache);
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

    renderAiHistoryDetail(selectedHistoryItem());
    renderWorkspaceGraph();
}

function renderActiveRuns(tasks) {
    const host = $('aiWorkspaceActiveRuns');
    if (!host) return;
    clearElement(host);

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
        aiWorkspaceAccounts = [];
        renderEmptyAccountSelect('-- 先填写应用 ID --');
        updateWorkspaceAccountHint('default', 0);
        return;
    }

    const params = new URLSearchParams();
    if (appId) {
        params.set('app_id', appId);
    }
    const query = params.toString();
    const response = await fetchJson(`/api/data/accounts/parsed${query ? `?${query}` : ''}`, {
        silentErrors: true,
    });
    if (!response.ok) {
        aiWorkspaceAccounts = [];
        renderEmptyAccountSelect('-- 账号加载失败 --');
        return;
    }

    aiWorkspaceAccounts = (response.data?.accounts || []).filter((account) => account.status === 'ready');
    const select = $('aiWorkspaceAccountSelect');
    if (!select) return;
    select.replaceChildren();
    const emptyOption = document.createElement('option');
    emptyOption.value = '';
    emptyOption.textContent = `-- 不绑定账号 (${aiWorkspaceAccounts.length} 个就绪) --`;
    select.appendChild(emptyOption);
    aiWorkspaceAccounts.forEach((account, index) => {
        const option = document.createElement('option');
        option.value = String(index);
        option.textContent = String(account.account || '').trim();
        select.appendChild(option);
    });
    updateWorkspaceAccountHint(appId || 'default', aiWorkspaceAccounts.length);
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
    const goal = String($('aiWorkspaceGoal')?.value || '').trim();
    if (!goal) {
        resetPlannerState();
        plannerDirty = false;
        clearPlannerCard(plannerElements(), {
            submitButton: $('aiWorkspaceSubmitTask'),
            submitLabel: '下发执行',
        });
        renderWorkspaceGraph();
        updateWorkspaceActionState();
        return null;
    }

    const signature = currentPlannerSignature();
    if (!force && plannerResult && signature === plannerSignature && !plannerDirty) {
        renderWorkspaceGraph();
        updateWorkspaceActionState();
        return plannerResult;
    }

    renderPlannerStateLoading(plannerElements(), {
        submitButton: $('aiWorkspaceSubmitTask'),
        submitLabel: '下发执行',
    });
    const response = await fetchJson('/api/ai_dialog/planner', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            goal,
            app_id: getSelectedWorkspaceAppId(),
            app_display_name: getSelectedWorkspaceAppDisplayName() || null,
            package_name: getSelectedWorkspacePackageName() || null,
            selected_account: String(getSelectedWorkspaceAccount()?.account || '').trim() || null,
            advanced_prompt: String($('aiWorkspaceAdvancedPrompt')?.value || '').trim() || null,
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
        renderWorkspaceGraph();
        updateWorkspaceActionState();
        return null;
    }

    plannerSignature = signature;
    plannerResult = response.data;
    plannerDirty = false;
    planConfirmed = false;
    renderPlannerResult(plannerElements(), plannerResult, {
        submitButton: $('aiWorkspaceSubmitTask'),
        submitLabel: '下发执行',
    });
    renderWorkspaceGraph();
    updateWorkspaceActionState();
    return plannerResult;
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

async function applyWorkspaceSeed(seed = {}) {
    const appId = String(seed.appId || seed.app_id || 'default').trim() || 'default';
    const appDisplayName = String(seed.appDisplayName || seed.app_display_name || '').trim();
    const packageName = String(seed.packageName || seed.package_name || seed.package || '').trim();
    const accountName = String(seed.accountName || seed.account || '').trim();

    activeDraftId = String(seed.draftId || seed.draft_id || '').trim();
    activeSuccessThreshold = Number(seed.successThreshold || seed.success_threshold || 0) || null;

    const goalInput = $('aiWorkspaceGoal');
    if (goalInput) goalInput.value = String(seed.goal || '').trim();
    const advancedPrompt = $('aiWorkspaceAdvancedPrompt');
    if (advancedPrompt) advancedPrompt.value = String(seed.advancedPrompt || seed.advanced_prompt || '').trim();

    await loadWorkspaceApps();
    const appSelect = $('aiWorkspaceAppSelect');
    if (appSelect) {
        const hasExistingOption = Array.from(appSelect.options).some((option) => option.value === appId);
        appSelect.value = hasExistingOption ? appId : CUSTOM_APP_OPTION;
    }
    const customAppId = $('aiWorkspaceCustomAppId');
    if (customAppId) customAppId.value = appSelect?.value === CUSTOM_APP_OPTION ? appId : '';
    const customDisplayName = $('aiWorkspaceCustomDisplayName');
    if (customDisplayName) customDisplayName.value = appSelect?.value === CUSTOM_APP_OPTION ? appDisplayName : '';
    const customPackageName = $('aiWorkspaceCustomPackageName');
    if (customPackageName) customPackageName.value = appSelect?.value === CUSTOM_APP_OPTION ? packageName : '';
    toggleCustomAppFields();
    await loadWorkspaceAccounts(appId);
    const accountSelect = $('aiWorkspaceAccountSelect');
    if (accountSelect) {
        const preferredIndex = aiWorkspaceAccounts.findIndex((account) => String(account?.account || '').trim() === accountName);
        accountSelect.value = preferredIndex >= 0 ? String(preferredIndex) : '';
    }
    resetPlannerState();
    plannerDirty = Boolean(String(seed.goal || '').trim());
    clearPlannerCard(plannerElements(), {
        submitButton: $('aiWorkspaceSubmitTask'),
        submitLabel: '下发执行',
    });
    renderWorkspaceGraph();
    updateWorkspaceActionState();
}

async function loadHistoryItemIntoWorkspace(item) {
    const draftId = String(item?.draft_id || '').trim();
    if (!draftId) return;
    selectedAiHistoryId = draftId;
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

    await applyWorkspaceSeed({
        goal: String(payload.goal || '').trim(),
        appId: String(payload.app_id || identity.app_id || 'default').trim() || 'default',
        appDisplayName: String(payload.app_display_name || '').trim(),
        packageName: String(payload.package_name || payload.package || '').trim(),
        accountName: String(payload.account || identity.account || '').trim(),
        advancedPrompt: String(payload.advanced_prompt || '').trim(),
        draftId: String(response.data?.draft_id || draftId),
        successThreshold: Number(response.data?.success_threshold || 0) || null,
    });
    await requestWorkspacePlanner({ force: true, silent: true });
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

export async function loadAiWorkspace() {
    await Promise.all([
        loadWorkspaceApps(),
        refreshDevicesSnapshot({ force: true, silentErrors: true }),
    ]);

    const devicesResponse = await refreshDevicesSnapshot({ silentErrors: true, maxAgeMs: 5000 });
    renderTargetOptions(devicesResponse.ok ? devicesResponse.data : []);
    await loadWorkspaceAccounts();

    if (!plannerResult) {
        clearPlannerCard(plannerElements(), {
            submitButton: $('aiWorkspaceSubmitTask'),
            submitLabel: '下发执行',
        });
    }

    renderWorkspaceGraph();
    updateWorkspaceActionState();

    await Promise.all([
        loadDrafts(),
        loadMetrics(),
        loadAiHistory(),
        loadActiveRuns(),
    ]);
}

export function initAiWorkspace() {
    const navItem = document.querySelector('.nav-item[data-tab="tab-ai"]');
    if (navItem) {
        navItem.addEventListener('click', () => {
            void loadAiWorkspace();
        });
    }

    const refreshBtn = $('aiWorkspaceRefresh');
    if (refreshBtn) {
        refreshBtn.onclick = () => {
            void loadAiWorkspace();
        };
    }

    document.querySelectorAll('[data-nav-target]').forEach((button) => {
        button.addEventListener('click', () => {
            const target = String(button.getAttribute('data-nav-target') || '').trim();
            if (target) switchToTab(target);
        });
    });

    const appSelect = $('aiWorkspaceAppSelect');
    if (appSelect) {
        appSelect.onchange = () => {
            toggleCustomAppFields();
            markWorkspaceInputsChanged({ resetDraft: true });
            void loadWorkspaceAccounts();
        };
    }

    const goalInput = $('aiWorkspaceGoal');
    if (goalInput) {
        goalInput.oninput = () => {
            markWorkspaceInputsChanged();
        };
    }

    const advancedPrompt = $('aiWorkspaceAdvancedPrompt');
    if (advancedPrompt) {
        advancedPrompt.oninput = () => {
            markWorkspaceInputsChanged();
        };
    }

    const targetSelect = $('aiWorkspaceTargetSelect');
    if (targetSelect) {
        targetSelect.onchange = () => {
            updateWorkspaceActionState();
            renderWorkspaceGraph();
        };
    }

    ['aiWorkspaceCustomAppId', 'aiWorkspaceCustomDisplayName', 'aiWorkspaceCustomPackageName'].forEach((id) => {
        const input = $(id);
        if (input) {
            input.oninput = () => {
                markWorkspaceInputsChanged({ resetDraft: true });
            };
        }
    });

    const accountRefresh = $('aiWorkspaceAccountRefresh');
    if (accountRefresh) {
        accountRefresh.onclick = () => {
            void loadWorkspaceAccounts();
        };
    }

    const accountSelect = $('aiWorkspaceAccountSelect');
    if (accountSelect) {
        accountSelect.onchange = () => {
            markWorkspaceInputsChanged();
        };
    }

    const generatePlanButton = $('aiWorkspaceGeneratePlan');
    if (generatePlanButton) {
        generatePlanButton.onclick = async () => {
            const plan = await requestWorkspacePlanner({ force: true });
            if (plan) {
                toast.success('任务图草案已生成，请先确认后再执行');
            }
        };
    }

    const regeneratePlanButton = $('aiWorkspaceRegeneratePlan');
    if (regeneratePlanButton) {
        regeneratePlanButton.onclick = async () => {
            const plan = await requestWorkspacePlanner({ force: true });
            if (plan) {
                toast.info('已按当前输入重新生成任务图');
            }
        };
    }

    const continueEditButton = $('aiWorkspaceContinueEdit');
    if (continueEditButton) {
        continueEditButton.onclick = () => {
            if (!plannerResult && !activeDraftId) return;
            plannerDirty = true;
            planConfirmed = false;
            renderWorkspaceGraph();
            updateWorkspaceActionState();
            $('aiWorkspaceGoal')?.focus();
            toast.info('已切回编辑态，请修改输入后重新生成任务图');
        };
    }

    const confirmButton = $('aiWorkspaceConfirmPlan');
    if (confirmButton) {
        confirmButton.onclick = () => {
            if (!plannerResult || plannerDirty) {
                toast.warn('请先生成最新任务图草案');
                return;
            }
            planConfirmed = true;
            renderWorkspaceGraph();
            updateWorkspaceActionState();
            toast.success('任务图已确认，可以下发执行');
        };
    }

    const submitTaskBtn = $('aiWorkspaceSubmitTask');
    if (submitTaskBtn) {
        submitTaskBtn.onclick = async () => {
            if (!planConfirmed || !plannerResult || plannerDirty) {
                toast.warn('请先确认最新任务图');
                return;
            }
            const unit = await resolveSelectedWorkspaceUnit();
            if (!unit) return;
            const rawPayload = buildAiDialogPayload({
                goal: String($('aiWorkspaceGoal')?.value || '').trim(),
                appId: getSelectedWorkspaceAppId(),
                appDisplayName: getSelectedWorkspaceAppDisplayName(),
                packageName: getSelectedWorkspacePackageName(),
                account: getSelectedWorkspaceAccount(),
                advancedPrompt: String($('aiWorkspaceAdvancedPrompt')?.value || '').trim(),
            });
            if (!rawPayload) {
                toast.warn('请填写任务描述');
                return;
            }
            const result = await submitAiTaskForUnit(unit, {
                rawPayload,
                plan: plannerResult,
                draftId: activeDraftId,
                successThreshold: activeSuccessThreshold,
                closeDialog: false,
            });
            if (result.ok) {
                await loadAiWorkspace();
            }
        };
    }

    const openDetail = () => {
        const target = String($('aiWorkspaceTargetSelect')?.value || '').trim();
        if (!target) return;
        const [deviceIdText, cloudIdText] = target.split('-');
        void openAiWorkspaceDetail({
            deviceId: Number(deviceIdText || 0),
            cloudId: Number(cloudIdText || 0),
        });
    };

    const openDetailBtn = $('aiWorkspaceOpenDetail');
    if (openDetailBtn) {
        openDetailBtn.onclick = openDetail;
    }

    const graphOpenDetailBtn = $('aiWorkspaceGraphOpenDetail');
    if (graphOpenDetailBtn) {
        graphOpenDetailBtn.onclick = openDetail;
    }

    renderWorkspaceGraph();
    updateWorkspaceActionState();

    if (window.location.hash === '#ai') {
        void loadAiWorkspace();
    }
}
