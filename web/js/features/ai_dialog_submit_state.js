export function resolveAiDialogSubmitState(plan) {
    const executionHint = String(
        plan?.execution?.next_step
        || plan?.account?.execution_hint
        || plan?.follow_up?.message
        || ''
    ).trim();
    const reuseAction = String(plan?.execution?.reuse_action || '').trim();

    if (plan?.account?.can_execute === false) {
        return {
            disabled: true,
            label: '缺少账号',
            title: executionHint || '当前规划未满足执行条件',
        };
    }

    if (reuseAction === 'continue_from_memory') {
        return {
            disabled: false,
            label: '继续执行',
            title: executionHint || '将优先复用最近一次可继续的运行资产',
        };
    }

    if (reuseAction === 'distill_or_validate') {
        return {
            disabled: false,
            label: '继续验证',
            title: executionHint || '当前已具备蒸馏样本，可继续验证或进入蒸馏评估',
        };
    }

    if (reuseAction === 'reuse_context') {
        return {
            disabled: false,
            label: '带上下文执行',
            title: executionHint || '将优先复用已沉淀的上下文和人工输入',
        };
    }

    return {
        disabled: false,
        label: '下发任务',
        title: executionHint,
    };
}
