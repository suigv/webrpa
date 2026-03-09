export const FIELD_LABEL_MAP = {
    source_key: '数据源', username: '用户', display_name: '昵称',
    device_ip: '设备IP', acc: '账号', pwd: '密码',
    fa2_secret: '2FA密钥', name: '任务名', package: '包名',
    status_hint: '备注', credentials_ref: '凭据', headless: '无界面',
    two_factor_code: '2FA码', timeout_seconds: '超时', login_url: '登录地址',
    account: '账号', password: '密码', target_url: '目标地址',
    keyword: '关键字', comment_text: '评论', scrape_source: '采集模式',
    blogger_id: '博主ID',
};

const FIELD_VALUE_MAP = {
    scrape_profile: 'PROFILE', demo_blogger: 'DEMO',
    'Demo Blogger': 'DEMO', success: 'SUCCESS', true: 'YES', false: 'NO',
};

export function localizeValue(val) {
    if (val === null || val === undefined) return "";
    const s = String(val);
    if (FIELD_VALUE_MAP[s]) return FIELD_VALUE_MAP[s];
    if (s.startsWith("<") && s.endsWith(">")) {
        const key = s.slice(1, -1);
        return `请输入 ${FIELD_LABEL_MAP[key] || key}`;
    }
    return s;
}

export function renderCommonFields(container, task, showOptional = false) {
    if (!container || !task) return;
    const payload = task.example_payload || {};
    const requiredKeys = task.required || [];
    container.innerHTML = "";

    Object.keys(payload).forEach(key => {
        const isReq = requiredKeys.includes(key);
        const val = localizeValue(payload[key]);
        const div = document.createElement("div");
        div.className = `form-group ${isReq ? '' : 'field-optional'}`;
        div.style.display = (isReq || showOptional) ? "flex" : "none";
        div.innerHTML = `
            <label>${FIELD_LABEL_MAP[key] || key}${isReq ? ' <span class="text-error">*</span>' : ''}</label>
            <input data-payload-key="${key}" type="text" value="${val}">
        `;
        container.appendChild(div);
    });
}
