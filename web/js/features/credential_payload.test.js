import test from 'node:test';
import assert from 'node:assert/strict';

test('buildCredentialsRef serializes structured credentials without losing optional fields', async () => {
    const { buildCredentialsRef } = await import(`./credential_payload.js?case=${Date.now()}-creds`);
    const serialized = buildCredentialsRef({
        account: 'demo-account',
        password: 'demo-password',
        twofa: 'demo-twofa',
        email: 'demo@example.com',
        email_password: 'mail-secret',
    });

    assert.deepEqual(JSON.parse(serialized), {
        account: 'demo-account',
        password: 'demo-password',
        twofa_secret: 'demo-twofa',
        email: 'demo@example.com',
        email_password: 'mail-secret',
    });
});

test('buildAiDialogPayload uses credentials_ref and omits raw account fields', async () => {
    const { buildAiDialogPayload } = await import(`./credential_payload.js?case=${Date.now()}-ai-dialog`);
    const payload = buildAiDialogPayload({
        goal: '帮我登录 X',
        appId: 'x',
        account: {
            account: 'demo-account',
            password: 'demo-password',
            twofa: 'demo-twofa',
        },
        advancedPrompt: '先处理升级弹窗',
    });

    assert.equal(payload.goal, '帮我登录 X');
    assert.equal(payload.app_id, 'x');
    assert.equal(payload.advanced_prompt, '先处理升级弹窗');
    assert.equal(payload._workflow_source, 'ai_dialog');
    assert.equal('account' in payload, false);
    assert.equal('password' in payload, false);
    assert.equal('twofa_secret' in payload, false);
    assert.equal('two_factor_code' in payload, false);
    assert.deepEqual(JSON.parse(payload.credentials_ref), {
        account: 'demo-account',
        password: 'demo-password',
        twofa_secret: 'demo-twofa',
    });
});
