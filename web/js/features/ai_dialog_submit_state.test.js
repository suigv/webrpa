import test from 'node:test';
import assert from 'node:assert/strict';

test('resolveAiDialogSubmitState disables submit when planner marks task as not executable', async () => {
    const { resolveAiDialogSubmitState } = await import(`./ai_dialog_submit_state.js?case=${Date.now()}-blocked`);
    const state = resolveAiDialogSubmitState({
        account: {
            can_execute: false,
            execution_hint: '执行方式：当前没有可用账号，登录类任务下发后大概率无法完成。',
        },
    });

    assert.deepEqual(state, {
        disabled: true,
        label: '缺少账号',
        title: '执行方式：当前没有可用账号，登录类任务下发后大概率无法完成。',
    });
});

test('resolveAiDialogSubmitState keeps submit enabled for executable plans', async () => {
    const { resolveAiDialogSubmitState } = await import(`./ai_dialog_submit_state.js?case=${Date.now()}-ok`);
    const state = resolveAiDialogSubmitState({
        account: {
            can_execute: true,
            execution_hint: '执行方式：使用已选账号 demo@example.com。',
        },
    });

    assert.deepEqual(state, {
        disabled: false,
        label: '下发任务',
        title: '执行方式：使用已选账号 demo@example.com。',
    });
});
