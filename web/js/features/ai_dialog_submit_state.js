export function resolveAiDialogSubmitState(plan) {
    const executionHint = String(
        plan?.account?.execution_hint
        || plan?.follow_up?.message
        || ''
    ).trim();

    if (plan?.account?.can_execute === false) {
        return {
            disabled: true,
            label: '缺少账号',
            title: executionHint || '当前规划未满足执行条件',
        };
    }

    return {
        disabled: false,
        label: '下发任务',
        title: executionHint,
    };
}
