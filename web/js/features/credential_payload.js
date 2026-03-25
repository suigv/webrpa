export function buildCredentialsRef(account) {
    return buildCredentialsRefWithOptions(account, {});
}

export function buildCredentialsRefWithOptions(account, {
    includeTwofaSecret = true,
} = {}) {
    if (!account || typeof account !== 'object') {
        return '';
    }
    const accountName = String(account.account || '').trim();
    const password = String(account.password || '').trim();
    if (!accountName || !password) {
        return '';
    }
    const payload = {
        account: accountName,
        password,
    };
    const twofa = String(account.twofa || account.twofa_secret || '').trim();
    if (includeTwofaSecret && twofa) payload.twofa_secret = twofa;
    const optionalKeys = ['email', 'email_password', 'token', 'email_token'];
    optionalKeys.forEach((key) => {
        const value = account[key];
        if (value !== null && value !== undefined && String(value).trim()) {
            payload[key] = String(value).trim();
        }
    });
    return JSON.stringify(payload);
}

export function buildAiDialogPayload({
    goal = '',
    appId = '',
    appDisplayName = '',
    packageName = '',
    accountRequired = true,
    account = null,
    includeTwofaSecret = true,
    advancedPrompt = '',
} = {}) {
    const normalizedGoal = String(goal || '').trim();
    if (!normalizedGoal) {
        return null;
    }

    const payload = { goal: normalizedGoal };
    const normalizedAppId = String(appId || '').trim();
    if (normalizedAppId) {
        payload.app_id = normalizedAppId;
    }
    const normalizedAppDisplayName = String(appDisplayName || '').trim();
    if (normalizedAppDisplayName) {
        payload.app_display_name = normalizedAppDisplayName;
    }
    const normalizedPackageName = String(packageName || '').trim();
    if (normalizedPackageName) {
        payload.package = normalizedPackageName;
        payload.package_name = normalizedPackageName;
    }
    if (!accountRequired) {
        payload.account_required = false;
    }

    const credentialsRef = buildCredentialsRefWithOptions(account, { includeTwofaSecret });
    if (credentialsRef) {
        payload.credentials_ref = credentialsRef;
    }
    payload.use_account_twofa = Boolean(includeTwofaSecret);

    const normalizedAdvancedPrompt = String(advancedPrompt || '').trim();
    if (normalizedAdvancedPrompt) {
        payload.advanced_prompt = normalizedAdvancedPrompt;
    }

    payload._workflow_source = 'ai_dialog';
    return payload;
}
