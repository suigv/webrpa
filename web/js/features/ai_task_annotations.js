import { fetchJson } from '../utils/api.js';
import { toast } from '../ui/toast.js';

const $ = (id) => document.getElementById(id);

const INPUT_OPTIONS = [
    { value: 'account_credential', label: '账号密码', hint: '此类内容不会保存为默认值' },
    { value: 'verification_code', label: '验证码', hint: '此类内容不会保存为默认值' },
    { value: 'search_keyword', label: '搜索关键词', hint: '可保存为后续草稿默认值' },
    { value: 'target_blogger_id', label: '博主ID', hint: '可保存为后续草稿默认值' },
    { value: 'dm_reply_text', label: '私信/回复内容', hint: '可保存为后续草稿默认值' },
    { value: 'profile_field_text', label: '资料字段内容', hint: '可保存为后续草稿默认值' },
    { value: 'temporary_text', label: '其他临时文本', hint: '默认仅保留在本次任务内' },
];

let annotationResolver = null;
let draftSaveState = { draftId: '', selected: new Set() };

function closeAnnotationModal() {
    const modal = $('aiInputAnnotationModal');
    if (modal) modal.style.display = 'none';
    if (annotationResolver) {
        annotationResolver(false);
        annotationResolver = null;
    }
}

function bindAnnotationModal() {
    if ($('aiInputAnnotationModal')?.dataset.bound === '1') {
        return;
    }
    const modal = $('aiInputAnnotationModal');
    if (modal) modal.dataset.bound = '1';
    ['aiInputAnnotationSkip', 'aiInputAnnotationSkipTop'].forEach((id) => {
        const button = $(id);
        if (button) {
            button.onclick = () => closeAnnotationModal();
        }
    });
}

export async function promptAiTaskInputAnnotation({ taskId, rawValue, stepId = null } = {}) {
    if (!taskId || !rawValue) {
        return false;
    }
    bindAnnotationModal();
    const modal = $('aiInputAnnotationModal');
    const optionsHost = $('aiInputAnnotationOptions');
    const hint = $('aiInputAnnotationHint');
    if (!modal || !optionsHost) {
        return false;
    }

    optionsHost.replaceChildren();
    if (hint) {
        hint.textContent = String(rawValue).trim().length > 24
            ? `本次输入：${String(rawValue).trim().slice(0, 24)}…`
            : `本次输入：${String(rawValue).trim()}`;
    }

    return await new Promise((resolve) => {
        annotationResolver = resolve;
        INPUT_OPTIONS.forEach((option) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'btn btn-secondary';
            button.style.justifyContent = 'flex-start';
            button.style.height = 'auto';
            button.style.padding = '12px';
            button.style.flexDirection = 'column';
            button.style.alignItems = 'flex-start';
            button.innerHTML = `
                <div style="font-weight:600;">${option.label}</div>
                <div class="text-xs text-muted mt-2">${option.hint}</div>
            `;
            button.onclick = async () => {
                const response = await fetchJson('/api/ai_dialog/annotations', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        task_id: taskId,
                        input_type: option.value,
                        raw_value: rawValue,
                        step_id: stepId,
                    }),
                    silentErrors: true,
                });
                if (!response.ok) {
                    toast.error(String(response.data?.detail || '输入标记失败'));
                    return;
                }
                toast.success(`已标记为${option.label}`);
                modal.style.display = 'none';
                const resolver = annotationResolver;
                annotationResolver = null;
                resolver?.(true);
            };
            optionsHost.appendChild(button);
        });
        modal.style.display = 'flex';
    });
}

function closeDraftSaveModal() {
    const modal = $('aiDraftSaveModal');
    if (modal) modal.style.display = 'none';
    draftSaveState = { draftId: '', selected: new Set() };
}

function bindDraftSaveModal() {
    if ($('aiDraftSaveModal')?.dataset.bound === '1') {
        return;
    }
    const modal = $('aiDraftSaveModal');
    if (modal) modal.dataset.bound = '1';
    ['aiDraftSaveClose', 'aiDraftSaveCloseTop'].forEach((id) => {
        const button = $(id);
        if (button) {
            button.onclick = () => closeDraftSaveModal();
        }
    });
    const submit = $('aiDraftSaveSubmit');
    if (submit) {
        submit.onclick = async () => {
            if (!draftSaveState.draftId) return;
            const response = await fetchJson(
                `/api/ai_dialog/drafts/${encodeURIComponent(draftSaveState.draftId)}/save_choices`,
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ candidate_ids: Array.from(draftSaveState.selected) }),
                    silentErrors: true,
                }
            );
            if (!response.ok) {
                toast.error(String(response.data?.detail || '保存默认值失败'));
                return;
            }
            toast.success('已保存选中的可复用项');
            closeDraftSaveModal();
        };
    }
}

export async function openAiDraftSaveModal(draftId) {
    if (!draftId) return;
    bindDraftSaveModal();
    const response = await fetchJson(
        `/api/ai_dialog/drafts/${encodeURIComponent(draftId)}/save_candidates`,
        { silentErrors: true }
    );
    if (!response.ok) {
        toast.error(String(response.data?.detail || '读取可复用项失败'));
        return;
    }
    const modal = $('aiDraftSaveModal');
    const list = $('aiDraftSaveList');
    const hint = $('aiDraftSaveHint');
    if (!modal || !list) return;

    draftSaveState = { draftId, selected: new Set() };
    list.replaceChildren();
    const candidates = Array.isArray(response.data?.candidates) ? response.data.candidates : [];
    if (hint) {
        const snapshot = response.data?.snapshot || {};
        hint.textContent = [
            snapshot.app_id ? `应用 ${snapshot.app_id}` : '',
            snapshot.account ? `账号 ${snapshot.account}` : '',
            snapshot.branch_id ? `当前分支 ${snapshot.branch_id}` : '',
        ].filter(Boolean).join(' · ') || '选择本次要沉淀的默认值';
    }

    if (!candidates.length) {
        const empty = document.createElement('div');
        empty.className = 'text-muted';
        empty.style.padding = '12px 4px';
        empty.textContent = '当前没有可保存的非敏感项';
        list.appendChild(empty);
        modal.style.display = 'flex';
        return;
    }

    candidates.forEach((item) => {
        const row = document.createElement('label');
        row.className = 'task-summary-target';
        row.style.display = 'block';
        row.style.cursor = 'pointer';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.style.marginRight = '10px';
        checkbox.onchange = () => {
            const candidateId = String(item.candidate_id || '');
            if (!candidateId) return;
            if (checkbox.checked) draftSaveState.selected.add(candidateId);
            else draftSaveState.selected.delete(candidateId);
        };

        const title = document.createElement('div');
        title.className = 'task-summary-target-label';
        title.textContent = String(item.label || item.kind || '未命名项');

        const message = document.createElement('div');
        message.className = 'task-summary-target-message';
        message.textContent = [
            String(item.description || '').trim(),
            item.value_preview ? `值：${String(item.value_preview)}` : '',
        ].filter(Boolean).join(' · ');

        const header = document.createElement('div');
        header.className = 'task-summary-target-header';
        const titleWrap = document.createElement('div');
        titleWrap.style.display = 'flex';
        titleWrap.style.alignItems = 'center';
        titleWrap.append(checkbox, title);
        header.appendChild(titleWrap);

        row.append(header, message);
        list.appendChild(row);
    });

    modal.style.display = 'flex';
}
