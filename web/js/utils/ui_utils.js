export const FIELD_LABEL_MAP = {
    source_key: '数据源',
    username: '用户',
    display_name: '昵称',
    device_ip: '设备IP',
    acc: '账号',
    pwd: '密码',
    fa2_secret: '2FA密钥',
    name: '任务名',
    package: '包名',
    status_hint: '备注',
    credentials_ref: '凭据',
    headless: '无界面',
    two_factor_code: '2FA码',
    timeout_seconds: '超时',
    login_url: '登录地址',
    account: '账号',
    password: '密码',
    target_url: '目标地址',
    keyword: '关键字',
    comment_text: '评论',
    scrape_source: '采集模式',
    blogger_id: '博主ID',
    country_profile: '地区模板',
    model_source: '机型来源',
    execution_mode: '执行模式',
    phone_model_name_contains: '机型关键词',
    seed: '随机种子',
    refresh_inventory: '刷新机型库存',
    write_contacts: '写入联系人',
    set_google_id: '写入 Google ID',
    enable_shake: '启用摇一摇',
    take_screenshot: '完成后截图',
    language_override: '语言覆盖',
    country_override: '国家覆盖',
    timezone_override: '时区覆盖',
};

const SYSTEM_AUTO_FIELDS = ['device_ip', 'sdk_port', 'api_port'];

function placeholderForValue(val) {
    if (val === null || val === undefined) return '';
    const s = String(val);
    if (s.startsWith('<') && s.endsWith('>')) {
        const key = s.slice(1, -1);
        return `请输入 ${FIELD_LABEL_MAP[key] || key}`;
    }
    return '';
}

function normalizeInputs(task) {
    if (Array.isArray(task?.inputs) && task.inputs.length > 0) {
        return task.inputs.map((input) => ({
            name: input.name,
            type: input.type || 'string',
            required: Boolean(input.required),
            default: input.default,
            label: input.label || FIELD_LABEL_MAP[input.name] || input.name,
            description: input.description || '',
            placeholder: input.placeholder || '',
            advanced: Boolean(input.advanced),
            system: Boolean(input.system),
            widget: input.widget || null,
            options: Array.isArray(input.options) ? input.options : [],
        }));
    }

    const payload = task?.example_payload || {};
    const requiredKeys = task?.required || [];
    return Object.keys(payload).map((key) => ({
        name: key,
        type: 'string',
        required: requiredKeys.includes(key),
        default: payload[key],
        label: FIELD_LABEL_MAP[key] || key,
        description: '',
        placeholder: placeholderForValue(payload[key]),
        advanced: !requiredKeys.includes(key),
        system: SYSTEM_AUTO_FIELDS.includes(key),
        widget: null,
        options: [],
    }));
}

function visibleGuideFields(task) {
    return normalizeInputs(task).filter((field) => {
        if (field.widget === 'hidden') return false;
        if (field.system) return false;
        if (SYSTEM_AUTO_FIELDS.includes(field.name)) return false;
        return true;
    });
}

function stringifyDefaultValue(value, options = []) {
    if (value === '' || value === null || value === undefined) return '';
    const matched = options.find((option) => String(option.value ?? '') === String(value));
    if (matched?.label) return matched.label;
    if (typeof value === 'boolean') return value ? '开启' : '关闭';
    return String(value);
}

export function renderTaskGuide(container, task) {
    if (!container) return;
    container.replaceChildren();

    if (!task) {
        container.style.display = 'none';
        return;
    }

    container.style.display = 'block';
    const fields = visibleGuideFields(task);

    const title = document.createElement('div');
    title.className = 'task-guide-title';
    title.textContent = `${task.display_name || task.task || '当前任务'} 说明`;

    const description = document.createElement('div');
    description.className = 'task-guide-text';
    description.textContent = task.description || '该任务支持参数化执行，可按下方说明调整关键参数。';

    container.append(title, description);

    const defaultSummary = fields
        .filter((field) => field.default !== '' && field.default !== null && field.default !== undefined)
        .slice(0, 6)
        .map((field) => `${field.label}: ${stringifyDefaultValue(field.default, field.options)}`);

    if (defaultSummary.length > 0) {
        const defaults = document.createElement('div');
        defaults.className = 'task-guide-text';
        defaults.style.marginTop = '8px';
        defaults.textContent = `默认行为：${defaultSummary.join('，')}`;
        container.appendChild(defaults);
    }

    if (fields.length > 0) {
        const tips = document.createElement('div');
        tips.className = 'task-guide-text';
        tips.style.marginTop = '8px';
        tips.textContent = '可调参数：';
        container.appendChild(tips);

        const tags = document.createElement('div');
        tags.className = 'task-guide-tags';
        fields.forEach((field) => {
            const tag = document.createElement('span');
            tag.className = 'task-guide-tag';
            tag.textContent = field.label;
            if (field.description) {
                tag.title = field.description;
            }
            tags.appendChild(tag);
        });
        container.appendChild(tags);
    }
}

function createTextLikeInput(field) {
    const input = document.createElement('input');
    input.dataset.payloadKey = field.name;
    input.dataset.payloadType = field.type || 'string';
    input.type = field.type === 'integer' || field.type === 'number' || field.widget === 'number'
        ? 'number'
        : 'text';
    if (field.default !== null && field.default !== undefined) {
        input.value = String(field.default);
    }
    if (field.placeholder) {
        input.placeholder = field.placeholder;
    }
    if (field.type === 'integer') {
        input.step = '1';
    }
    return input;
}

function createSelectInput(field) {
    const select = document.createElement('select');
    select.dataset.payloadKey = field.name;
    select.dataset.payloadType = field.type || 'string';
    if (!field.required && (field.default === null || field.default === undefined)) {
        const empty = document.createElement('option');
        empty.value = '';
        empty.textContent = '请选择';
        select.appendChild(empty);
    }
    field.options.forEach((option) => {
        const item = document.createElement('option');
        item.value = String(option.value ?? '');
        item.textContent = option.label || String(option.value ?? '');
        if (option.description) {
            item.title = option.description;
        }
        if (field.default !== null && field.default !== undefined && String(field.default) === item.value) {
            item.selected = true;
        }
        select.appendChild(item);
    });
    if (field.default === null || field.default === undefined) {
        const firstValue = field.required ? select.querySelector('option')?.value : '';
        if (firstValue !== undefined) {
            select.value = firstValue;
        }
    }
    return select;
}

function createCheckboxInput(field) {
    const input = document.createElement('input');
    input.dataset.payloadKey = field.name;
    input.dataset.payloadType = 'boolean';
    input.type = 'checkbox';
    input.checked = Boolean(field.default);
    return input;
}

function createFieldInput(field) {
    if (field.widget === 'hidden') return null;
    if (field.widget === 'select' || (Array.isArray(field.options) && field.options.length > 0)) {
        return createSelectInput(field);
    }
    if (field.widget === 'checkbox' || field.type === 'boolean') {
        return createCheckboxInput(field);
    }
    return createTextLikeInput(field);
}

export function renderCommonFields(container, task, showOptional = false) {
    if (!container || !task) return;
    container.replaceChildren();

    const fields = visibleGuideFields(task);

    fields.forEach((field) => {
        const div = document.createElement('div');
        div.className = [
            'form-group',
            field.required ? '' : 'field-optional',
            field.advanced ? 'field-advanced' : '',
        ].filter(Boolean).join(' ');
        div.style.display = (field.required || showOptional || !field.advanced) ? 'flex' : 'none';
        div.style.flexDirection = 'column';

        const label = document.createElement('label');
        label.textContent = field.label;

        if (field.required) {
            const requiredMark = document.createElement('span');
            requiredMark.className = 'text-error';
            requiredMark.textContent = ' *';
            label.appendChild(requiredMark);
        }

        const input = createFieldInput(field);
        if (!input) {
            return;
        }

        if (field.description) {
            const helper = document.createElement('div');
            helper.className = 'text-xs text-muted';
            helper.style.marginTop = '4px';
            helper.textContent = field.description;
            div.append(label, input, helper);
        } else {
            div.append(label, input);
        }
        container.appendChild(div);
    });
}
