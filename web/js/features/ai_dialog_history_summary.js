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

export function normalizeDraftSummary(item) {
    if (item?.workflow_draft && typeof item.workflow_draft === 'object') {
        return item.workflow_draft;
    }
    return item && typeof item === 'object' ? item : {};
}

export function normalizeDraftExit(item) {
    const draft = normalizeDraftSummary(item);
    return draft?.exit && typeof draft.exit === 'object' ? draft.exit : {};
}

export function normalizeDistillAssessment(item) {
    const draft = normalizeDraftSummary(item);
    return draft?.distill_assessment && typeof draft.distill_assessment === 'object'
        ? draft.distill_assessment
        : {};
}

export function normalizeLatestRunAsset(item) {
    const draft = normalizeDraftSummary(item);
    return draft?.latest_run_asset && typeof draft.latest_run_asset === 'object'
        ? draft.latest_run_asset
        : {};
}

export function formatExitAction(action) {
    return EXIT_ACTION_LABELS[String(action || '').trim()] || '继续处理';
}

export function formatReusePriority(priority) {
    return REUSE_PRIORITY_LABELS[String(priority || '').trim()] || '待评估';
}

export function formatReuseAction(action) {
    return REUSE_ACTION_LABELS[String(action || '').trim()] || '继续执行';
}

export function formatQualification(value) {
    return QUALIFICATION_LABELS[String(value || '').trim()] || '待评估';
}

export function resolveDistillButtonState(item) {
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
