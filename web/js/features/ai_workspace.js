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
let plannerTimer = null;
let plannerSignature = '';
let plannerResult = null;
let activeDraftId = '';
let activeSuccessThreshold = null;
let aiHistoryCache = [];
let selectedAiHistoryId = '';
let designerExpanded = false;

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

function renderAiHistoryDetail(item) {
    const host = $('aiWorkspaceHistoryDetail');
    if (!host) return;
    clearElement(host);

    if (!item) {
        const empty = document.createElement('div');
        empty.className = 'text-muted';
        empty.textContent = '选择一条 AI 会话后，可在这里查看复用状态、失败建议和声明脚本绑定。';
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
    if (item?.can_edit) {
        const chip = document.createElement('span');
        chip.className = 'task-guide-tag';
        chip.textContent = '可编辑';
        badges.appendChild(chip);
    }
    if (item?.can_save) {
        const chip = document.createElement('span');
        chip.className = 'task-guide-tag';
        chip.textContent = '可沉淀';
        badges.appendChild(chip);
    }
    host.appendChild(badges);

    const summaryBlock = createMetaBlock('当前结论', [
        draft?.message,
        item?.app_id ? `应用：${String(item.app_id)}` : '',
        item?.account ? `账号：${String(item.account)}` : '',
        Number(draft?.success_threshold || 0) > 0
            ? `样本进度：${Number(draft?.success_count || 0)}/${Number(draft?.success_threshold || 0)}`
            : '',
    ]);
    if (summaryBlock) host.appendChild(summaryBlock);

    const declarativeBlock = createMetaBlock('声明脚本绑定', [
        declarativeBinding?.summary,
        declarativeBinding?.script_title
            ? `主脚本：${String(declarativeBinding.script_title)}`
            : '',
        declarativeBinding?.current_stage?.stage_title
            ? `当前阶段：${String(declarativeBinding.current_stage.stage_title)}`
            : '',
        typeof declarativeBinding?.script_count === 'number'
            ? `脚本数量：${Number(declarativeBinding.script_count)}`
            : '',
    ]);
    if (declarativeBlock) host.appendChild(declarativeBlock);

    const runAssetBlock = createMetaBlock('最近运行资产', [
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
    ]);
    if (runAssetBlock) host.appendChild(runAssetBlock);

    const failureBlock = createMetaBlock('失败建议', [
        failureAdvice?.summary || '',
        Array.isArray(failureAdvice?.suggestions) && failureAdvice.suggestions.length > 0
            ? `建议：${failureAdvice.suggestions.join('；')}`
            : '',
        failureAdvice?.suggested_prompt ? `推荐提示词：${String(failureAdvice.suggested_prompt)}` : '',
    ]);
    if (failureBlock) host.appendChild(failureBlock);

    const actions = document.createElement('div');
    actions.className = 'ai-workspace-history-actions';

    const loadButton = document.createElement('button');
    loadButton.type = 'button';
    loadButton.className = 'btn btn-secondary btn-sm';
    loadButton.textContent = '载入到工作台';
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
    renderWorkspaceDesignerPanel();
}

function currentWorkspaceTargetSummary() {
    const target = String($('aiWorkspaceTargetSelect')?.value || '').trim();
    if (!target) {
        return '尚未选择目标云机';
    }
    const [deviceIdText, cloudIdText] = target.split('-');
    return `目标云机 #${Number(deviceIdText || 0)}-${Number(cloudIdText || 0)}`;
}

function renderWorkspaceDesignerPanel() {
    const panel = $('aiWorkspaceDesignerPanel');
    const hint = $('aiWorkspaceDesignerHint');
    const summaryHost = $('aiWorkspaceDesignerSummary');
    const executionHost = $('aiWorkspaceDesignerExecution');
    const openButton = $('aiWorkspaceOpenDesigner');
    const runButton = $('aiWorkspaceDesignerRun');
    const detailButton = $('aiWorkspaceDesignerOpenDetail');
    if (!panel || !summaryHost || !executionHost) return;

    panel.style.display = designerExpanded ? 'block' : 'none';
    if (openButton) {
        openButton.textContent = designerExpanded ? '收起完整设计器' : '展开完整设计器';
    }
    if (!designerExpanded) {
        return;
    }

    if (hint) {
        hint.textContent = plannerResult
            ? '当前设计上下文已固定在工作台内；如需单设备调试，再进入设备详情快捷入口。'
            : '先填写目标与任务描述，工作台会在这里展开完整设计上下文。';
    }

    clearElement(summaryHost);
    clearElement(executionHost);

    const summaryTitle = document.createElement('div');
    summaryTitle.className = 'task-summary-title';
    summaryTitle.textContent = plannerResult
        ? String(plannerResult.display_name || '当前 AI 任务设计')
        : '完整设计器等待规划结果';

    const summaryText = document.createElement('div');
    summaryText.className = 'task-summary-text';
    summaryText.textContent = plannerResult
        ? String(plannerResult.operator_summary || '').trim()
        : '填写任务描述后，工作台会在此展示执行模式、阻塞项、会话锚点和下一步建议。';

    const summaryMeta = document.createElement('div');
    summaryMeta.className = 'task-guide-tags';
    [
        currentWorkspaceTargetSummary(),
        getSelectedWorkspaceAppId() ? `应用 ${getSelectedWorkspaceAppId()}` : '',
        getSelectedWorkspaceAccount()?.account
            ? `账号 ${String(getSelectedWorkspaceAccount().account)}`
            : '未绑定账号',
        activeDraftId ? `继续草稿 ${activeDraftId}` : '',
    ].filter(Boolean).forEach((text) => {
        const chip = document.createElement('span');
        chip.className = 'task-guide-tag';
        chip.textContent = text;
        summaryMeta.appendChild(chip);
    });
    summaryHost.append(summaryTitle, summaryText, summaryMeta);

    const selectedHistory = selectedHistoryItem();
    const historyDraft = normalizeDraftSummary(selectedHistory);
    const execution = plannerResult?.execution || {};
    const followUp = plannerResult?.follow_up || {};
    const blockingReasons = Array.isArray(execution?.blocking_reasons) ? execution.blocking_reasons : [];
    const missing = Array.isArray(followUp?.missing) ? followUp.missing : [];

    [
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
        createMetaBlock('会话锚点', [
            selectedHistory ? `当前参考会话：${String(selectedHistory.display_name || '')}` : '当前没有选中的参考会话',
            historyDraft?.declarative_binding?.script_title
                ? `参考脚本：${String(historyDraft.declarative_binding.script_title)}`
                : '',
            historyDraft?.declarative_binding?.current_stage?.stage_title
                ? `参考阶段：${String(historyDraft.declarative_binding.current_stage.stage_title)}`
                : '',
            historyDraft?.message ? String(historyDraft.message) : '',
        ]),
    ].filter(Boolean).forEach((block) => executionHost.appendChild(block));

    applyPlannerSubmitState(runButton, plannerResult, '直接下发当前任务');
    if (detailButton) {
        const hasTarget = Boolean(String($('aiWorkspaceTargetSelect')?.value || '').trim());
        detailButton.disabled = !hasTarget;
        detailButton.title = hasTarget ? '' : '请先选择目标云机';
    }
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

        const status = document.createElement('span');
        status.className = 'badge';
        status.textContent = String(item?.status || 'unknown');
        badges.appendChild(status);

        if (item?.can_replay) {
            const badge = document.createElement('span');
            badge.className = 'badge badge-ok';
            badge.textContent = '可重放';
            badges.appendChild(badge);
        }
        if (item?.can_edit) {
            const badge = document.createElement('span');
            badge.className = 'badge';
            badge.textContent = '可编辑';
            badges.appendChild(badge);
        }
        if (item?.can_save) {
            const badge = document.createElement('span');
            badge.className = 'task-guide-tag';
            badge.textContent = '可沉淀';
            badges.appendChild(badge);
        }
        const draft = normalizeDraftSummary(item);
        const latestRunAsset = normalizeLatestRunAsset(item);
        const quickHint = [
            draft?.distill_assessment?.latest_qualification
                ? formatQualification(draft.distill_assessment.latest_qualification)
                : '',
            latestRunAsset?.memory_summary?.reuse_priority
                ? formatReusePriority(latestRunAsset.memory_summary.reuse_priority)
                : '',
        ].filter(Boolean);
        quickHint.slice(0, 2).forEach((text) => {
            const badge = document.createElement('span');
            badge.className = 'task-guide-tag';
            badge.textContent = text;
            badges.appendChild(badge);
        });

        content.append(title, meta, badges);

        const actions = document.createElement('div');
        actions.className = 'ai-workspace-history-row-actions';

        const loadButton = document.createElement('button');
        loadButton.type = 'button';
        loadButton.className = 'btn btn-secondary btn-sm';
        loadButton.textContent = '载入到工作台';
        loadButton.disabled = !item?.can_edit;
        loadButton.onclick = (event) => {
            stopEvent(event);
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
        distillButton.onclick = (event) => {
            stopEvent(event);
            void distillHistoryItem(item);
        };
        actions.appendChild(distillButton);

        const saveButton = document.createElement('button');
        saveButton.type = 'button';
        saveButton.className = 'btn btn-secondary btn-sm';
        saveButton.textContent = '保存可复用项';
        saveButton.disabled = !item?.can_save;
        saveButton.onclick = async (event) => {
            stopEvent(event);
            await openAiDraftSaveModal(String(item?.draft_id || '').trim());
        };
        actions.appendChild(saveButton);

        row.append(content, actions);
        host.appendChild(row);
    });

    renderAiHistoryDetail(selectedHistoryItem());
    renderWorkspaceDesignerPanel();
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
            ? `当前共有 ${onlineCount} 个在线云机可作为 AI 设计目标`
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

function resetPlannerState() {
    plannerSignature = '';
    plannerResult = null;
}

function updateOpenDesignerButton(plan) {
    applyPlannerSubmitState($('aiWorkspaceSubmitTask'), plan, '下发任务');
    const detailButton = $('aiWorkspaceOpenDetail');
    const button = $('aiWorkspaceOpenDesigner');
    const hasTarget = Boolean(String($('aiWorkspaceTargetSelect')?.value || '').trim());
    if (detailButton) {
        detailButton.disabled = !hasTarget;
        detailButton.title = hasTarget ? '' : '请先选择目标云机';
    }
    const submitButton = $('aiWorkspaceSubmitTask');
    if (submitButton && !hasTarget) {
        submitButton.disabled = true;
        submitButton.title = '请先选择目标云机';
    }
    if (!button) return;
    if (!hasTarget) {
        button.disabled = true;
        button.title = '请先选择目标云机';
    } else {
        button.disabled = false;
        button.title = '';
    }
    renderWorkspaceDesignerPanel();
}

async function requestWorkspacePlanner({ force = false, silent = false } = {}) {
    const goal = String($('aiWorkspaceGoal')?.value || '').trim();
    if (!goal) {
        resetPlannerState();
        clearPlannerCard(plannerElements(), {
            submitButton: $('aiWorkspaceSubmitTask'),
            submitLabel: '下发任务',
        });
        updateOpenDesignerButton(null);
        renderWorkspaceDesignerPanel();
        return null;
    }

    const signature = currentPlannerSignature();
    if (!force && plannerResult && signature === plannerSignature) {
        updateOpenDesignerButton(plannerResult);
        return plannerResult;
    }

    renderPlannerStateLoading(plannerElements(), {
        submitButton: $('aiWorkspaceSubmitTask'),
        submitLabel: '下发任务',
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
            toast.error(String(response.data?.detail || 'AI 规划失败'));
        }
        clearPlannerCard(plannerElements(), {
            submitButton: $('aiWorkspaceSubmitTask'),
            submitLabel: '下发任务',
        });
        updateOpenDesignerButton(null);
        renderWorkspaceDesignerPanel();
        return null;
    }

    plannerSignature = signature;
    plannerResult = response.data;
    renderPlannerResult(plannerElements(), plannerResult, {
        submitButton: $('aiWorkspaceSubmitTask'),
        submitLabel: '下发任务',
    });
    updateOpenDesignerButton(plannerResult);
    renderWorkspaceDesignerPanel();
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
    if (String(seed.goal || '').trim()) {
        await requestWorkspacePlanner({ force: true, silent: true });
    } else {
        clearPlannerCard(plannerElements(), {
            submitButton: $('aiWorkspaceSubmitTask'),
            submitLabel: '下发任务',
        });
        updateOpenDesignerButton(null);
        renderWorkspaceDesignerPanel();
    }
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
    toast.info('已载入到 AI 工作台，可直接继续执行');
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
            ? device.cloud_machines.find((item) => Number(item?.cloud_id || 0) === cloudId)
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

function schedulePlanner() {
    if (plannerTimer) {
        clearTimeout(plannerTimer);
    }
    plannerTimer = setTimeout(() => {
        void requestWorkspacePlanner({ silent: true });
    }, 300);
}

export async function loadAiWorkspace() {
    await Promise.all([
        loadWorkspaceApps(),
        refreshDevicesSnapshot({ force: true, silentErrors: true }),
    ]);

    const devicesResponse = await refreshDevicesSnapshot({ silentErrors: true, maxAgeMs: 5000 });
    renderTargetOptions(devicesResponse.ok ? devicesResponse.data : []);
    await loadWorkspaceAccounts();
    if (String($('aiWorkspaceGoal')?.value || '').trim()) {
        await requestWorkspacePlanner({ force: true, silent: true });
    } else {
        clearPlannerCard(plannerElements(), {
            submitButton: $('aiWorkspaceOpenDesigner'),
            submitLabel: '打开完整 AI 设计器',
        });
        updateOpenDesignerButton(null);
        renderWorkspaceDesignerPanel();
    }

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
            resetPlannerState();
            resetWorkspaceDraftContext();
            void loadWorkspaceAccounts().then(() => requestWorkspacePlanner({ force: true, silent: true }));
        };
    }

    const goalInput = $('aiWorkspaceGoal');
    if (goalInput) {
        goalInput.oninput = () => {
            resetPlannerState();
            schedulePlanner();
        };
    }

    const advancedPrompt = $('aiWorkspaceAdvancedPrompt');
    if (advancedPrompt) {
        advancedPrompt.oninput = () => {
            resetPlannerState();
            schedulePlanner();
        };
    }

    const targetSelect = $('aiWorkspaceTargetSelect');
    if (targetSelect) {
        targetSelect.onchange = () => {
            updateOpenDesignerButton(plannerResult);
        };
    }

    ['aiWorkspaceCustomAppId', 'aiWorkspaceCustomDisplayName', 'aiWorkspaceCustomPackageName'].forEach((id) => {
        const input = $(id);
        if (input) {
            input.oninput = () => {
                resetPlannerState();
                resetWorkspaceDraftContext();
                void loadWorkspaceAccounts().then(() => requestWorkspacePlanner({ force: true, silent: true }));
            };
        }
    });

    const accountRefresh = $('aiWorkspaceAccountRefresh');
    if (accountRefresh) {
        accountRefresh.onclick = () => {
            resetPlannerState();
            void loadWorkspaceAccounts().then(() => requestWorkspacePlanner({ force: true, silent: true }));
        };
    }

    const accountSelect = $('aiWorkspaceAccountSelect');
    if (accountSelect) {
        accountSelect.onchange = () => {
            resetPlannerState();
            schedulePlanner();
        };
    }

    const openDesignerBtn = $('aiWorkspaceOpenDesigner');
    if (openDesignerBtn) {
        openDesignerBtn.onclick = async () => {
            designerExpanded = !designerExpanded;
            if (designerExpanded && String($('aiWorkspaceGoal')?.value || '').trim()) {
                await requestWorkspacePlanner({ force: true, silent: true });
            } else {
                renderWorkspaceDesignerPanel();
            }
        };
    }

    const submitTaskBtn = $('aiWorkspaceSubmitTask');
    if (submitTaskBtn) {
        submitTaskBtn.onclick = async () => {
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
            const plan = await requestWorkspacePlanner({ force: true });
            if (!plan) return;
            await submitAiTaskForUnit(unit, {
                rawPayload,
                plan,
                draftId: activeDraftId,
                successThreshold: activeSuccessThreshold,
                closeDialog: false,
            });
            await loadAiWorkspace();
        };
    }

    const openDetailBtn = $('aiWorkspaceOpenDetail');
    if (openDetailBtn) {
        openDetailBtn.onclick = () => {
            const target = String($('aiWorkspaceTargetSelect')?.value || '').trim();
            if (!target) return;
            const [deviceIdText, cloudIdText] = target.split('-');
            void openAiWorkspaceDetail({
                deviceId: Number(deviceIdText || 0),
                cloudId: Number(cloudIdText || 0),
            });
        };
    }

    const designerRunBtn = $('aiWorkspaceDesignerRun');
    if (designerRunBtn) {
        designerRunBtn.onclick = () => {
            $('aiWorkspaceSubmitTask')?.click();
        };
    }

    const designerOpenDetailBtn = $('aiWorkspaceDesignerOpenDetail');
    if (designerOpenDetailBtn) {
        designerOpenDetailBtn.onclick = () => {
            $('aiWorkspaceOpenDetail')?.click();
        };
    }

    const designerCloseBtn = $('aiWorkspaceDesignerClose');
    if (designerCloseBtn) {
        designerCloseBtn.onclick = () => {
            designerExpanded = false;
            renderWorkspaceDesignerPanel();
        };
    }

    updateOpenDesignerButton(null);
    renderWorkspaceDesignerPanel();

    if (window.location.hash === '#ai') {
        void loadAiWorkspace();
    }
}
