import { fetchJson } from '../utils/api.js';
import { toast } from '../ui/toast.js';
import { apiSubmitTask, buildTaskRequest } from './task_service.js';

const $ = (id) => document.getElementById(id);
const DEFAULT_AI_ACTIONS = [
    {
        name: 'ai.locate_point',
        label: '视觉定位',
        description: 'Locate a specific point/UI element using AI description',
    },
    { name: 'ui.click', label: '点击', description: '点击屏幕坐标 (x, y)' },
    { name: 'ui.input_text', label: '输入文字', description: '在当前焦点处输入文本' },
    { name: 'ui.key_press', label: '按键', description: '向设备发送按键事件' },
    { name: 'ui.swipe', label: '滑动', description: '执行屏幕滑动' },
];
const DEFAULT_AI_ACTION_SELECTION = new Set(DEFAULT_AI_ACTIONS.map((item) => item.name));

function parseCommaSeparated(value) {
    return String(value || '')
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean);
}

function uniqueStringList(values) {
    return [...new Set((Array.isArray(values) ? values : []).map((item) => String(item || '').trim()).filter(Boolean))];
}

function isInteractiveSkill(name) {
    return name === 'ai.locate_point' || name.startsWith('ui.') || name.startsWith('app.');
}

function prettifyActionLabel(name) {
    const matched = DEFAULT_AI_ACTIONS.find((item) => item.name === name);
    if (matched) return matched.label;
    return String(name || '').replaceAll('.', ' / ');
}

function renderActionOptions(actions) {
    const host = $('unitAiActionCheckboxes');
    if (!host) return;
    host.replaceChildren();

    actions.forEach((action) => {
        const label = document.createElement('label');
        label.className = 'custom-checkbox inline-flex items-center gap-1';
        if (action.description) {
            label.title = action.description;
        }

        const input = document.createElement('input');
        input.type = 'checkbox';
        input.name = 'aiAction';
        input.value = action.name;
        input.checked = DEFAULT_AI_ACTION_SELECTION.has(action.name);

        const checkmark = document.createElement('span');
        checkmark.className = 'checkmark';

        const text = document.createElement('span');
        text.textContent = action.label;

        label.append(input, checkmark, text);
        host.appendChild(label);
    });
}

async function loadAiActionOptions() {
    try {
        const response = await fetchJson('/api/engine/skills', { silentErrors: true });
        if (!response.ok || !response.data || typeof response.data !== 'object') {
            renderActionOptions(DEFAULT_AI_ACTIONS);
            return;
        }
        const actions = Object.entries(response.data)
            .filter(([name]) => isInteractiveSkill(String(name || '')))
            .map(([name, metadata]) => ({
                name: String(name || ''),
                label: prettifyActionLabel(name),
                description: String(metadata?.description || '').trim(),
            }))
            .sort((left, right) => {
                const leftDefault = DEFAULT_AI_ACTION_SELECTION.has(left.name) ? 0 : 1;
                const rightDefault = DEFAULT_AI_ACTION_SELECTION.has(right.name) ? 0 : 1;
                if (leftDefault !== rightDefault) return leftDefault - rightDefault;
                return left.name.localeCompare(right.name);
            });
        renderActionOptions(actions.length > 0 ? actions : DEFAULT_AI_ACTIONS);
    } catch (_error) {
        renderActionOptions(DEFAULT_AI_ACTIONS);
    }
}

function renderEmptyAccountSelect(select, label) {
    if (!select) return;
    select.replaceChildren();
    const emptyOpt = document.createElement('option');
    emptyOpt.value = '';
    emptyOpt.textContent = label;
    select.appendChild(emptyOpt);
}

async function loadAiDialogAccounts() {
    const select = $('unitAiAccountSelect');
    if (!select) return;
    try {
        const response = await fetchJson('/api/data/accounts/parsed');
        if (!response.ok) {
            renderEmptyAccountSelect(select, '-- 账号加载失败 --');
            return;
        }
        const accounts = (response.data?.accounts || []).filter((account) => account.status === 'ready');
        select.replaceChildren();
        const emptyOpt = document.createElement('option');
        emptyOpt.value = '';
        emptyOpt.textContent = `-- 不绑定账号 (${accounts.length} 个就绪) --`;
        select.appendChild(emptyOpt);
        accounts.forEach((account, index) => {
            const opt = document.createElement('option');
            opt.value = String(index);
            opt.textContent = account.account;
            opt.dataset.acc = account.account || '';
            opt.dataset.pwd = account.password || '';
            opt.dataset.twofa = account.twofa || '';
            select.appendChild(opt);
        });
    } catch (_error) {
        renderEmptyAccountSelect(select, '-- 账号加载失败 --');
    }
}

async function loadDefaultAiSystemPrompt() {
    const systemPrompt = $('unitAiSystemPrompt');
    if (!systemPrompt) return;
    try {
        const response = await fetchJson('/api/tasks/prompt_templates', { silentErrors: true });
        if (!response.ok) return;
        const [defaultTemplate] = Array.isArray(response.data?.templates) ? response.data.templates : [];
        if (defaultTemplate?.content) {
            systemPrompt.value = defaultTemplate.content;
        }
    } catch (_error) {
        // Keep dialog usable even when template bootstrap fails.
    }
}

function readSelectedValues(selector) {
    return Array.from(document.querySelectorAll(selector)).map((element) => element.value);
}

function buildAiTaskPayload(unit) {
    const goal = String($('unitAiGoal')?.value || '').trim();
    if (!goal) {
        toast.warn('请填写任务描述');
        return null;
    }

    const systemPrompt = String($('unitAiSystemPrompt')?.value || '').trim();
    const profileName = String($('unitAiProfile')?.value || '').trim();
    const useVlm = $('unitAiUseVlm')?.checked || false;
    const maxStepsValue = Number.parseInt(String($('unitAiMaxSteps')?.value || '').trim(), 10);
    const stagnantLimitValue = Number.parseInt(
        String($('unitAiStagnantLimit')?.value || '').trim(),
        10,
    );
    const resolvedMaxSteps = Number.isFinite(maxStepsValue) && maxStepsValue > 0 ? maxStepsValue : 15;
    const resolvedStagnantLimit =
        Number.isFinite(stagnantLimitValue) && stagnantLimitValue > 0 ? stagnantLimitValue : 4;
    const expectedStateIds = uniqueStringList([
        ...readSelectedValues('input[name="aiState"]:checked'),
        ...parseCommaSeparated($('unitAiExtraStates')?.value || ''),
    ]);
    const allowedActions = uniqueStringList(readSelectedValues('input[name="aiAction"]:checked'));

    if (expectedStateIds.length === 0) {
        toast.warn('请至少选择一个预期状态');
        return null;
    }
    if (allowedActions.length === 0) {
        toast.warn('请至少保留一个允许动作');
        return null;
    }

    const payload = {
        device_ip: unit.parent_ip,
        goal,
        expected_state_ids: expectedStateIds,
        allowed_actions: allowedActions,
        observation: {},
        max_steps: resolvedMaxSteps,
        stagnant_limit: resolvedStagnantLimit,
    };

    const aiAccountSelect = $('unitAiAccountSelect');
    if (aiAccountSelect && aiAccountSelect.value !== '') {
        const selectedOpt = aiAccountSelect.options[aiAccountSelect.selectedIndex];
        if (selectedOpt.dataset.acc) payload.account = selectedOpt.dataset.acc;
        if (selectedOpt.dataset.pwd) payload.password = selectedOpt.dataset.pwd;
        if (selectedOpt.dataset.twofa) {
            payload.two_factor_code = selectedOpt.dataset.twofa;
            payload.twofa_secret = selectedOpt.dataset.twofa;
        }
    }

    if (systemPrompt) payload.system_prompt = systemPrompt;
    if (profileName) payload._runtime_profile = profileName;
    if (useVlm) payload.fallback_modalities = ['vlm'];
    return payload;
}

export function openUnitAiDialog(unit) {
    if (!unit) return;
    const modal = $('unitAiModal');
    if (modal) modal.style.display = 'flex';
    void loadAiDialogAccounts();
    renderActionOptions(DEFAULT_AI_ACTIONS);
    void loadAiActionOptions();
    const refreshBtn = $('unitAiAccountRefresh');
    if (refreshBtn) refreshBtn.onclick = () => {
        void loadAiDialogAccounts();
    };

    const title = $('unitAiModalTitle');
    if (title) title.textContent = `AI 对话 - 云机 #${unit.parent_id}-${unit.cloud_id}`;

    const goalInput = $('unitAiGoal');
    if (goalInput) goalInput.value = '';
    const profileInput = $('unitAiProfile');
    if (profileInput) profileInput.value = '';
    const maxStepsInput = $('unitAiMaxSteps');
    if (maxStepsInput) maxStepsInput.value = '15';
    const stagnantLimitInput = $('unitAiStagnantLimit');
    if (stagnantLimitInput) stagnantLimitInput.value = '4';
    document.querySelectorAll('input[name="aiState"]').forEach((checkbox) => {
        checkbox.checked = ['home', 'account', 'password', 'two_factor'].includes(checkbox.value);
    });
    const extraStatesInput = $('unitAiExtraStates');
    if (extraStatesInput) extraStatesInput.value = '';
    const systemPromptInput = $('unitAiSystemPrompt');
    if (systemPromptInput) systemPromptInput.value = '';
    void loadDefaultAiSystemPrompt();
    const useVlm = $('unitAiUseVlm');
    if (useVlm) useVlm.checked = false;
}

export function closeUnitAiDialog() {
    const modal = $('unitAiModal');
    if (modal) modal.style.display = 'none';
    const advanced = $('unitAiAdvanced');
    if (advanced) advanced.style.display = 'none';
}

export async function submitUnitAiTask(unit, { onSuccess = null, onFailure = null } = {}) {
    if (!unit) return { ok: false, reason: 'missing_unit' };
    const payload = buildAiTaskPayload(unit);
    if (!payload) return { ok: false, reason: 'invalid_payload' };

    const taskData = buildTaskRequest({
        task: 'agent_executor',
        payload,
        targets: [{ device_id: unit.parent_id, cloud_id: unit.cloud_id }],
    });
    const result = await apiSubmitTask(taskData);
    if (result.ok) {
        onSuccess?.(result);
    } else {
        onFailure?.(result);
    }
    return result;
}
