import { fetchJson } from '../utils/api.js';
import { toast } from '../ui/toast.js';

const taskPriority = document.getElementById('taskPriority');
const taskRunAt = document.getElementById('taskRunAt');
const targetDeviceId = document.getElementById('targetDeviceId');
const targetCloudId = document.getElementById('targetCloudId');
const taskMaxRetries = document.getElementById('taskMaxRetries');
const taskPluginHost = document.getElementById('taskPluginHost');
const taskPayloadFields = document.getElementById('taskPayloadFields');
const tasksList = document.getElementById('tasksList');
const submitTaskBtn = document.getElementById('submitTask');
const refreshTasksBtn = document.getElementById('refreshTasks');
const clearTasksBtn = document.getElementById('clearTasks');

let pluginCatalog = [];
let selectedTaskName = '';

const PLUGIN_NAME_MAP = {
    blogger_scrape: '博主资料采集',
    device_reboot: '硬件重启',
    device_soft_reset: '系统重置',
    dm_reply: '私信回复',
    follow_interaction: '关注互动',
    home_interaction: '首页推流互动',
    profile_clone: '资料克隆',
    quote_interaction: '引用互动',
    x_auto_login: 'X 自动登录 (Web)',
    x_mobile_login: 'X 自动登录 (APP)',
};

const PLUGIN_PRESETS = {
    x_mobile_login: [
        { label: '标准登录', payload: { package: 'com.twitter.android', status_hint: 'login' } },
        { label: '备用节点', payload: { package: 'com.twitter.android.lite', status_hint: 'fallback' } }
    ],
    blogger_scrape: [
        { label: '采集示例', payload: { scrape_source: 'scrape_profile', blogger_id: 'elonmusk' } }
    ]
};

const FIELD_LABEL_MAP = {
    source_key: '数据源', username: '用户', display_name: '昵称',
    device_ip: '设备IP', acc: '账号', pwd: '密码',
    fa2_secret: '2FA密钥', name: '任务名', package: '包名',
    status_hint: '备注', credentials_ref: '凭据', headless: '无界面',
    two_factor_code: '2FA码', timeout_seconds: '超时',
};

export function initTasks() {
    if (submitTaskBtn) submitTaskBtn.addEventListener('click', submitTask);
    if (refreshTasksBtn) refreshTasksBtn.addEventListener('click', loadTasks);
    if (clearTasksBtn) clearTasksBtn.addEventListener('click', clearAllTasks);
    
    // Bind toggle buttons
    const toggleTasksAdvancedBtn = document.getElementById('toggleTasksAdvancedBtn');
    if (toggleTasksAdvancedBtn) {
        toggleTasksAdvancedBtn.addEventListener('click', () => {
            const el = document.getElementById('tasksAdvanced');
            if (el) el.style.display = (el.style.display === 'block') ? 'none' : 'block';
        });
    }

    const clearGlobalLogBtn = document.getElementById('clearGlobalLogBtn');
    if (clearGlobalLogBtn) {
        clearGlobalLogBtn.addEventListener('click', () => {
            const el = document.getElementById('globalLogBox');
            if (el) el.innerHTML = '';
        });
    }

    // Bind modal close buttons
    document.querySelectorAll('.close-task-modal-btn').forEach(btn => {
        btn.addEventListener('click', closeTaskModal);
    });
    
    initPluginSelector();
    loadTasks();
}

const closeTaskModal = () => {
    const modal = document.getElementById('taskModal');
    if (modal) modal.style.display = 'none';
};

async function clearAllTasks() {
    if (!confirm('此操作将永久清空所有历史流水记录，是否继续？')) return;
    if (clearTasksBtn) clearTasksBtn.disabled = true;
    try {
        const r = await fetchJson('/api/tasks/', { method: 'DELETE' });
        if (r.ok) {
            toast.success('执行流水已安全归零');
            tasksList.innerHTML = ''; 
            await loadTasks(); 
        }
    } catch (e) { toast.error('清空指令被拒绝'); }
    finally { if (clearTasksBtn) clearTasksBtn.disabled = false; }
}

async function initPluginSelector() {
    const catalog = await fetchJson('/api/tasks/catalog');
    if (!catalog.ok) return;
    pluginCatalog = catalog.data.tasks;
    
    if (taskPluginHost) {
        taskPluginHost.innerHTML = '';
        pluginCatalog.forEach(p => {
            const label = PLUGIN_NAME_MAP[p.task] || p.display_name || p.task;
            const node = document.createElement('div');
            node.className = 'plugin-item';
            node.dataset.id = p.task;
            node.textContent = label;
            
            node.addEventListener('click', () => {
                taskPluginHost.querySelectorAll('.plugin-item').forEach(i => i.classList.remove('selected'));
                node.classList.add('selected');
                selectedTaskName = node.dataset.id;
                renderFields();
            });
            taskPluginHost.appendChild(node);
        });
    }

    const showMoreBtn = document.getElementById('showMoreFields');
    if (showMoreBtn) {
        showMoreBtn.addEventListener('click', () => {
            const fields = document.querySelectorAll('#taskPayloadFields .field-optional');
            const isHidden = fields[0]?.style.display === 'none';
            fields.forEach(el => el.style.display = isHidden ? 'flex' : 'none');
            showMoreBtn.textContent = isHidden ? '收起高级参数' : '显示高级参数';
        });
    }
}

const applyPluginPreset = (pluginName, index) => {
    const preset = PLUGIN_PRESETS[pluginName]?.[index];
    if (!preset) return;
    Object.keys(preset.payload).forEach(key => {
        const input = document.getElementById(`field-${key}`);
        if (input) input.value = preset.payload[key];
    });
    toast.info(`预设参数已注入: ${preset.label}`);
};

function renderFields() {
    if (!taskPayloadFields) return;
    const p = pluginCatalog.find(x => x.task === selectedTaskName);
    const payload = p ? p.example_payload : {};
    const required = p ? p.required : [];
    
    taskPayloadFields.innerHTML = '';
    
    const presets = PLUGIN_PRESETS[selectedTaskName];
    if (presets) {
        const presetContainer = document.createElement('div');
        presetContainer.className = 'col-span-2 flex gap-2 mb-2 items-center';
        presetContainer.innerHTML = '<span class="text-sm text-muted">快捷注入:</span>';
        presets.forEach((pr, idx) => {
            const btn = document.createElement('button');
            btn.className = 'btn btn-secondary btn-sm';
            btn.textContent = pr.label;
            btn.addEventListener('click', () => applyPluginPreset(selectedTaskName, idx));
            presetContainer.appendChild(btn);
        });
        taskPayloadFields.appendChild(presetContainer);
    }

    Object.keys(payload).forEach(k => {
        const isReq = required.includes(k);
        const label = FIELD_LABEL_MAP[k] || k;
        
        const group = document.createElement('div');
        group.className = `form-group ${isReq ? '' : 'field-optional'}`;
        group.style.display = isReq ? 'flex' : 'none';
        
        group.innerHTML = `
            <label>${label}${isReq ? ' <span class="text-error">*</span>' : ''}</label>
            <input data-payload-key="${k}" id="field-${k}" type="text" value="${payload[k] || ''}">
        `;
        taskPayloadFields.appendChild(group);
    });

    const showMoreBtn = document.getElementById('showMoreFields');
    if (showMoreBtn) {
        const hasOptional = Object.keys(payload).some(k => !required.includes(k));
        showMoreBtn.style.display = hasOptional ? 'block' : 'none';
        showMoreBtn.textContent = '显示高级参数';
    }
}

export async function loadTasks() {
    if (refreshTasksBtn) refreshTasksBtn.disabled = true;
    try {
        const r = await fetchJson('/api/tasks/?limit=50');
        if (r.ok) renderTasks(r.data);
    } finally {
        if (refreshTasksBtn) refreshTasksBtn.disabled = false;
    }
}

function resolvePluginLabel(taskName) {
    const name = String(taskName || '').trim();
    if (!name || name === 'null' || name.toLowerCase() === 'anonymous') return '隐式作业';
    if (PLUGIN_NAME_MAP[name]) return PLUGIN_NAME_MAP[name];
    const found = pluginCatalog.find((x) => String(x.task || '') === name);
    return (found && found.display_name) ? found.display_name : name;
}

function renderTasks(items) {
    if (!tasksList) return;
    tasksList.innerHTML = '';
    const visibleItems = items.filter(t => t.task_name !== 'anonymous');
    if (visibleItems.length === 0) {
        tasksList.innerHTML = '<div class="p-4 text-center text-muted text-sm">队列空闲中</div>';
        return;
    }

    visibleItems.forEach(t => {
        const node = document.createElement('div');
        node.className = 'list-item';
        
        const statusMap = {
            pending: { label: '排队', class: 'bg-warning' },
            running: { label: '运行', class: 'bg-primary' },
            completed: { label: '完成', class: 'bg-success' },
            failed: { label: '异常', class: 'bg-error' },
            cancelled: { label: '已弃', class: 'bg-muted' }
        };
        const status = statusMap[t.status] || { label: t.status, class: 'bg-muted' };
        
        const targetText = t.targets && t.targets.length ? t.targets.map(x => `#${x.device_id}`).join(',') : '无映射';
        const label = resolvePluginLabel(t.task_name || t.ai_type);

        node.innerHTML = `
            <div class="list-item-content">
                <div class="list-item-title flex items-center gap-2">
                    <span class="dot ${status.class}"></span>
                    ${label}
                </div>
                <div class="list-item-meta">目标: ${targetText} | ${new Date(t.created_at).toLocaleTimeString()}</div>
            </div>
            <div class="flex gap-2">
                <button class="btn btn-secondary btn-sm action-detail" data-id="${t.task_id}">分析</button>
                ${t.status === 'failed' ? `<button class="btn btn-secondary btn-sm text-error action-retry" data-id="${t.task_id}">重试</button>` : ''}
            </div>
        `;
        tasksList.appendChild(node);
    });

    tasksList.querySelectorAll('.action-detail').forEach(b => {
        b.addEventListener('click', () => loadTaskDetail(b.dataset.id));
    });
    tasksList.querySelectorAll('.action-retry').forEach(b => {
        b.addEventListener('click', () => retryTask(b.dataset.id));
    });
}

async function retryTask(taskId) {
    toast.info("正在提取快照并构建重试任务...");
    const r = await fetchJson(`/api/tasks/${taskId}/retry_failed`, { method: 'POST' });
    if (r.ok) {
        toast.success("容错重试已提交");
        await loadTasks();
    } else {
        toast.error("重试构建失败");
    }
}

async function loadTaskDetail(taskId) {
    const modal = document.getElementById('taskModal');
    const body = document.getElementById('taskDetailBody');
    if (!modal || !body) return;

    modal.style.display = 'flex';
    body.innerHTML = '<div class="text-center py-8 text-muted">解包报告中...</div>';

    const r = await fetchJson(`/api/tasks/${taskId}`);
    if (!r.ok) {
        body.innerHTML = `<div class="text-error p-4">数据调取被拒绝: ${r.status}</div>`;
        return;
    }

    const d = r.data;
    const label = resolvePluginLabel(d.task_name || d.ai_type);
    
    let html = `
        <div class="info-grid">
            <div class="info-row"><span class="info-label">追踪溯源</span><span class="info-value text-muted" style="font-family:var(--font-mono);">${d.task_id}</span></div>
            <div class="info-row"><span class="info-label">驱动载体</span><span class="info-value">${label}</span></div>
            <div class="info-row"><span class="info-label">运行时相</span><span class="info-value">${d.status.toUpperCase()}</span></div>
        </div>
    `;

    if (d.result) {
        html += `<h4 class="mt-4 text-primary">✅ 正常输出</h4>`;
        html += `<div class="code-block">${JSON.stringify(d.result, null, 2)}</div>`;
    }

    if (d.error) {
        html += `<h4 class="mt-4 text-error">❌ 致命中断</h4>`;
        html += `<div class="code-block text-error" style="border-color:var(--error);">${d.error}</div>`;
    }

    body.innerHTML = html;
}

async function submitTask() {
    if (!selectedTaskName) return toast.warn('请选定作业驱动');
    if (submitTaskBtn) submitTaskBtn.disabled = true;
    const p = {};
    taskPayloadFields.querySelectorAll('input').forEach(i => { p[i.dataset.payloadKey] = i.value; });
    const body = {
        task: selectedTaskName,
        payload: p,
        targets: [{ device_id: Number(targetDeviceId.value), cloud_id: Number(targetCloudId?.value || 1) }],
        priority: Number(taskPriority.value),
        max_retries: Number(taskMaxRetries?.value || 0),
        run_at: taskRunAt?.value || null
    };
    const r = await fetchJson('/api/tasks/', { method: 'POST', body: JSON.stringify(body) });
    if (r.ok) { toast.success('指令已送达执行池'); loadTasks(); }
    else { toast.error('指令下发熔断'); }
    if (submitTaskBtn) submitTaskBtn.disabled = false;
}
