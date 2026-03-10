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
        return "";
    }
    return s;
}

function placeholderForValue(val) {
    if (val === null || val === undefined) return "";
    const s = String(val);
    if (s.startsWith("<") && s.endsWith(">")) {
        const key = s.slice(1, -1);
        return `请输入 ${FIELD_LABEL_MAP[key] || key}`;
    }
    return "";
}

// 定义需要从 UI 中隐藏的环境类参数，这些参数将由系统自动注入
const SYSTEM_AUTO_FIELDS = ['device_ip', 'package', 'sdk_port'];

export function renderCommonFields(container, task, showOptional = false) {
    if (!container || !task) return;
    const payload = task.example_payload || {};
    const requiredKeys = task.required || [];
    container.replaceChildren();

    Object.keys(payload).forEach(key => {
        // 如果是系统自动处理的字段，则不在 UI 中显示
        if (SYSTEM_AUTO_FIELDS.includes(key)) {
            return;
        }

        const isReq = requiredKeys.includes(key);
        const value = localizeValue(payload[key]);
        const placeholder = placeholderForValue(payload[key]);
        const div = document.createElement("div");
        div.className = `form-group ${isReq ? '' : 'field-optional'}`;
        div.style.display = (isReq || showOptional) ? "flex" : "none";

        const label = document.createElement("label");
        label.textContent = FIELD_LABEL_MAP[key] || key;
        if (isReq) {
            const requiredMark = document.createElement("span");
            requiredMark.className = 'text-error';
            requiredMark.textContent = ' *';
            label.appendChild(requiredMark);
        }

        const input = document.createElement("input");
        input.dataset.payloadKey = key;
        input.type = "text";
        input.value = value;
        if (placeholder) {
            input.placeholder = placeholder;
        }

        div.append(label, input);
        container.appendChild(div);
    });
}
