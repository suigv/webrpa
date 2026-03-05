import { fetchJson } from '../utils/api.js';
import { toast } from '../ui/toast.js';

const taskPriority = document.getElementById('taskPriority');
const taskRunAt = document.getElementById('taskRunAt');
const taskMaxRetries = document.getElementById('taskMaxRetries');
const taskBackoff = document.getElementById('taskBackoff');
const targetDeviceId = document.getElementById('targetDeviceId');
const targetCloudId = document.getElementById('targetCloudId');
const taskPluginHost = document.getElementById('taskPluginHost');
const taskPayloadFields = document.getElementById('taskPayloadFields');
const tasksList = document.getElementById('tasksList');
const taskDetail = document.getElementById('taskDetail');
const submitTaskBtn = document.getElementById('submitTask');
const refreshTasksBtn = document.getElementById('refreshTasks');

let taskEventSource = null;
let pluginCatalog = [];
let selectedTaskName = '';

const PLUGIN_NAME_MAP = {
    blogger_scrape: '博主资料抓取',
    device_reboot: '设备重启',
    device_soft_reset: '设备软重置',
    dm_reply: '私信回复互动',
    follow_interaction: '关注互动',
    home_interaction: '首页互动',
    profile_clone: '资料克隆',
    quote_interaction: '引用互动',
    x_auto_login: 'X 网页自动登录',
    x_mobile_login: 'X 移动端登录',
};

const FIELD_LABEL_MAP = {
    source_key: '数据源标识',
    username: '用户名',
    display_name: '显示名称',
    device_ip: '设备 IP',
    name: '设备名称',
    package: '应用包名',
    status_hint: '状态提示',
    credentials_ref: '凭据标识',
    headless: '无界面模式',
    two_factor_code: '二步验证码',
    timeout_seconds: '超时时间（秒）',
    login_url: '登录地址',
    account: '账号',
    password: '密码',
};

const FIELD_VALUE_MAP = {
    scrape_profile: '资料抓取源',
    demo_blogger: '示例博主',
    'Demo Blogger': '示例博主',
    success: '成功',
};

export function initTasks() {
    if (submitTaskBtn) submitTaskBtn.addEventListener('click', submitTask);
    if (refreshTasksBtn) refreshTasksBtn.addEventListener('click', loadTasks);
    initPluginSelector();
    loadTasks();
}

async function initPluginSelector() {
    if (!taskPluginHost) return;
    taskPluginHost.innerHTML = '<div class="msg">插件加载中...</div>';

    const catalog = await fetchJson('/api/tasks/catalog');
    if (!catalog.ok || !catalog.data || !Array.isArray(catalog.data.tasks)) {
        taskPluginHost.innerHTML = '<div class="msg">未能加载插件列表</div>';
        return;
    }

    pluginCatalog = catalog.data.tasks;
    if (pluginCatalog.length === 0) {
        taskPluginHost.innerHTML = '<div class="msg">暂无可用插件</div>';
        return;
    }

    const options = ['<div class="block-label"><strong>选择插件（勾选一个）</strong></div>'];
    options.push('<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px;">');
    for (let index = 0; index < pluginCatalog.length; index += 1) {
        const item = pluginCatalog[index];
        const name = String(item.task || '').trim();
        if (!name) continue;
        const label = resolvePluginLabel(name, item.display_name);
        const checked = index === 0 ? 'checked' : '';
        options.push(`
            <label class="device-item" style="padding:8px;cursor:pointer;">
                <input type="checkbox" data-plugin-pick="${name}" ${checked}>
                <span style="margin-left:8px;">${label}</span>
            </label>
        `);
        if (index === 0) selectedTaskName = name;
    }
    options.push('</div>');
    taskPluginHost.innerHTML = options.join('');

    taskPluginHost.querySelectorAll('[data-plugin-pick]').forEach((node) => {
        node.addEventListener('change', (event) => {
            const current = event.currentTarget;
            if (!current.checked) {
                current.checked = true;
                return;
            }
            taskPluginHost.querySelectorAll('[data-plugin-pick]').forEach((peer) => {
                if (peer !== current) peer.checked = false;
            });
            selectedTaskName = String(current.getAttribute('data-plugin-pick') || '').trim();
            renderPluginFields();
        });
    });

    renderPluginFields();
}

function renderPluginFields() {
    if (!taskPayloadFields) return;
    const task = selectedTaskName;
    const found = pluginCatalog.find((x) => String(x.task || '') === task);
    const payload = (found && found.example_payload && typeof found.example_payload === 'object') ? found.example_payload : {};

    const keys = Object.keys(payload);
    if (keys.length === 0) {
        taskPayloadFields.innerHTML = '<div class="msg">该插件没有必填参数。</div>';
        return;
    }

    const fields = [];
    for (const key of keys) {
        const value = localizeFieldValue(payload[key]);
        const label = FIELD_LABEL_MAP[key] || '参数';
        fields.push(`<label>${label}<input data-payload-key="${key}" type="text" value="${value}"></label>`);
    }
    taskPayloadFields.innerHTML = fields.join('');
}

function localizeFieldValue(raw) {
    if (raw == null) return '';
    const text = String(raw);
    if (FIELD_VALUE_MAP[text]) return FIELD_VALUE_MAP[text];
    if (/^<[^>]+>$/.test(text)) {
        const key = text.slice(1, -1).trim();
        return `请填写${FIELD_LABEL_MAP[key] || '参数'}`;
    }
    return text;
}

export async function loadTasks() {
    if (refreshTasksBtn) refreshTasksBtn.disabled = true;
    const r = await fetchJson('/api/tasks/?limit=50');
    if (r.ok) renderTasks(r.data);
    if (refreshTasksBtn) refreshTasksBtn.disabled = false;
}

function renderTasks(items) {
    if (!tasksList) return;
    tasksList.innerHTML = '';
    if (!Array.isArray(items) || items.length === 0) {
        tasksList.innerHTML = '<div class="device-item"><strong>暂无任务</strong></div>';
        return;
    }
    const visibleItems = (items || []).filter((t) => {
        const taskName = String(t.task_name || '').trim().toLowerCase();
        return taskName && taskName !== 'anonymous';
    });
    if (visibleItems.length === 0) {
        tasksList.innerHTML = '<div class="device-item"><strong>暂无插件任务</strong></div>';
        return;
    }

    for (const t of visibleItems) {
        const node = document.createElement('div');
        node.className = 'device-item';
        const statusText = ({ pending: '排队中', running: '执行中', completed: '已完成', failed: '失败', cancelled: '已取消' })[t.status] || t.status;
        const targets = Array.isArray(t.targets) ? t.targets : [];
        const targetText = targets.length ? targets.map((x) => `设备${x.device_id}/云机${x.cloud_id}`).join('，') : '未指定';
        const taskName = resolvePluginLabel(t.task_name);

        node.innerHTML = `
            <strong>${taskName} • ${statusText}</strong>
            <div class="device-meta">插件：${taskName}</div>
            <div class="device-meta">目标：${targetText}</div>
            <div class="device-meta">优先级：${t.priority} | 计划时间：${t.run_at || '立即'}</div>
            <div style="margin-top:6px;display:flex;gap:6px;">
                <button class="btn btn-ghost action-detail" data-id="${t.task_id}">详情</button>
                <button class="btn btn-ghost action-cancel" data-id="${t.task_id}">取消</button>
                <button class="btn btn-ghost action-watch" data-id="${t.task_id}">监听</button>
            </div>
        `;
        tasksList.appendChild(node);
    }

    tasksList.querySelectorAll('.action-detail').forEach((btn) => btn.addEventListener('click', () => loadTaskDetail(btn.dataset.id)));
    tasksList.querySelectorAll('.action-cancel').forEach((btn) => btn.addEventListener('click', () => cancelTask(btn.dataset.id)));
    tasksList.querySelectorAll('.action-watch').forEach((btn) => btn.addEventListener('click', () => openTaskEvents(btn.dataset.id)));
}

async function loadTaskDetail(taskId) {
    const r = await fetchJson(`/api/tasks/${taskId}`);
    if (!taskDetail) return;
    if (!r.ok) {
        taskDetail.textContent = '加载任务详情失败';
        return;
    }
    const d = r.data;
    const taskName = resolvePluginLabel(d.task_name);
    if (!taskName) {
        taskDetail.textContent = '该任务未绑定插件，不在任务列表展示。';
        return;
    }
    const targetText = Array.isArray(d.targets) && d.targets.length
        ? d.targets.map((x) => `设备${x.device_id}/云机${x.cloud_id}`).join('，')
        : '未指定';
    const statusText = ({ pending: '排队中', running: '执行中', completed: '已完成', failed: '失败', cancelled: '已取消' })[d.status] || d.status;
    taskDetail.textContent = `任务状态：${statusText}；插件：${taskName}；目标：${targetText}`;
}

function resolvePluginLabel(taskName) {
    const name = String(taskName || '').trim();
    if (!name || name.toLowerCase() === 'anonymous') return '';
    if (PLUGIN_NAME_MAP[name]) return PLUGIN_NAME_MAP[name];
    const found = pluginCatalog.find((x) => String(x.task || '') === name);
    if (found && String(found.display_name || '').trim()) {
        return String(found.display_name).trim();
    }
    return '插件任务';
}

async function submitTask() {
    if (!selectedTaskName) {
        toast.warn('请先选择插件');
        return;
    }
    if (submitTaskBtn) submitTaskBtn.disabled = true;

    const payload = {};
    if (taskPayloadFields) {
        taskPayloadFields.querySelectorAll('[data-payload-key]').forEach((input) => {
            const key = input.getAttribute('data-payload-key');
            if (!key) return;
            payload[key] = String(input.value || '').trim();
        });
    }

    const body = {
        task: selectedTaskName,
        payload,
        targets: [
            {
                device_id: Number(targetDeviceId?.value || 1),
                cloud_id: Number(targetCloudId?.value || 1),
            },
        ],
        ai_type: 'volc',
        max_retries: Number(taskMaxRetries?.value || 0),
        retry_backoff_seconds: Number(taskBackoff?.value || 2),
        priority: Number(taskPriority?.value || 50),
        run_at: String(taskRunAt?.value || '').trim() || null,
    };

    const r = await fetchJson('/api/tasks/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });

    if (r.ok) {
        toast.success('任务已提交');
        await loadTasks();
        await loadTaskDetail(r.data.task_id);
        openTaskEvents(r.data.task_id);
    } else {
        toast.error(`提交失败：${r.status}`);
    }
    if (submitTaskBtn) submitTaskBtn.disabled = false;
}

async function cancelTask(taskId) {
    const r = await fetchJson(`/api/tasks/${taskId}/cancel`, { method: 'POST' });
    if (r.ok) {
        toast.info('已请求取消任务');
        await loadTasks();
        await loadTaskDetail(taskId);
    } else {
        toast.error('取消失败');
    }
}

function openTaskEvents(taskId) {
    if (taskEventSource) {
        taskEventSource.close();
        taskEventSource = null;
    }
    taskEventSource = new EventSource(`/api/tasks/${taskId}/events`);
    taskEventSource.onerror = () => {
        taskEventSource.close();
    };
    ['task.created', 'task.started', 'task.retry_scheduled', 'task.completed', 'task.failed', 'task.cancelled', 'task.cancel_requested'].forEach((evt) => {
        taskEventSource.addEventListener(evt, async () => {
            await loadTaskDetail(taskId);
            await loadTasks();
        });
    });
}
