import { fetchJson } from '../utils/api.js';
import { toast } from '../ui/toast.js';
import { apiSubmitTask, buildTaskRequest } from './task_service.js';

const $ = (id) => document.getElementById(id);

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

    const payload = {
        device_ip: unit.parent_ip,
        goal,
        expected_state_ids: readSelectedValues('input[name="aiState"]:checked'),
        allowed_actions: readSelectedValues('input[name="aiAction"]:checked'),
        observation: {},
        max_steps: resolvedMaxSteps,
        stagnant_limit: resolvedStagnantLimit,
    };

    const aiAccountSelect = $('unitAiAccountSelect');
    if (aiAccountSelect && aiAccountSelect.value !== '') {
        const selectedOpt = aiAccountSelect.options[aiAccountSelect.selectedIndex];
        if (selectedOpt.dataset.acc) payload.acc = selectedOpt.dataset.acc;
        if (selectedOpt.dataset.pwd) payload.pwd = selectedOpt.dataset.pwd;
        if (selectedOpt.dataset.twofa) {
            payload.two_factor_code = selectedOpt.dataset.twofa;
            payload.fa2_secret = selectedOpt.dataset.twofa;
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
    document.querySelectorAll('input[name="aiAction"]').forEach((checkbox) => {
        checkbox.checked = true;
    });
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
