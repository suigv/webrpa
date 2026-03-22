import { fetchJson } from '../utils/api.js';
import { toast } from '../ui/toast.js';
import { prefillTaskFromDraft } from './tasks.js';

const $ = (id) => document.getElementById(id);

let draftListCache = [];
let selectedDraftId = '';

function clearElement(element) {
    if (element) {
        element.replaceChildren();
    }
}

function badgeVariant(status) {
    const normalized = String(status || '').toLowerCase();
    if (normalized === 'distilled' || normalized === 'ready') return 'ok';
    if (normalized === 'needs_attention') return 'warn';
    return 'default';
}

function formatUpdatedAt(value) {
    const text = String(value || '').trim();
    if (!text) return '';
    const date = new Date(text);
    if (Number.isNaN(date.getTime())) return text;
    return date.toLocaleString();
}

function renderDraftsList(drafts) {
    const host = $('draftsList');
    if (!host) return;
    clearElement(host);

    if (!Array.isArray(drafts) || drafts.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'text-muted';
        empty.style.padding = '12px 16px';
        empty.textContent = '暂无草稿记录';
        host.appendChild(empty);
        return;
    }

    drafts.forEach((draft) => {
        const item = document.createElement('div');
        item.className = 'list-item';
        if (String(draft?.draft_id || '') === selectedDraftId) {
            item.classList.add('active');
        }

        const titleRow = document.createElement('div');
        titleRow.className = 'flex justify-between items-center';

        const title = document.createElement('div');
        title.className = 'font-medium';
        title.textContent = String(draft?.display_name || draft?.draft_id || '草稿');

        const badge = document.createElement('span');
        badge.className = `badge badge-${badgeVariant(draft?.status)}`;
        badge.textContent = String(draft?.status || 'collecting');

        titleRow.append(title, badge);

        const meta = document.createElement('div');
        meta.className = 'text-xs text-muted mt-1';
        const progress = `${Number(draft?.success_count || 0)}/${Number(draft?.success_threshold || 0)}`;
        const updatedAt = formatUpdatedAt(draft?.updated_at);
        meta.textContent = [
            String(draft?.task_name || ''),
            `进度 ${progress}`,
            updatedAt ? `更新 ${updatedAt}` : '',
        ].filter(Boolean).join(' · ');

        item.append(titleRow, meta);

        item.onclick = () => {
            const draftId = String(draft?.draft_id || '').trim();
            if (!draftId) return;
            selectedDraftId = draftId;
            renderDraftsList(draftListCache);
            void loadDraftDetail(draftId);
        };

        host.appendChild(item);
    });
}

function renderDraftDetail(draft) {
    const empty = $('draftDetailEmpty');
    const host = $('draftDetail');
    if (!host) return;
    if (empty) empty.style.display = 'none';
    host.style.display = 'block';
    clearElement(host);

    const header = document.createElement('div');
    header.className = 'mb-4';

    const title = document.createElement('div');
    title.className = 'text-lg font-bold';
    title.textContent = String(draft?.display_name || draft?.draft_id || '草稿详情');

    const sub = document.createElement('div');
    sub.className = 'text-xs text-muted mt-1';
    sub.textContent = [
        `ID ${String(draft?.draft_id || '')}`,
        `任务 ${String(draft?.task_name || '')}`,
        `候选插件 ${String(draft?.plugin_name_candidate || '')}`,
    ].filter(Boolean).join(' · ');

    header.append(title, sub);
    host.appendChild(header);

    const summary = document.createElement('div');
    summary.className = 'panel';
    summary.style.padding = '12px';

    const statusLabel = document.createElement('div');
    statusLabel.className = 'text-xs text-muted mb-1';
    statusLabel.textContent = '状态';
    const statusValue = document.createElement('div');
    statusValue.className = 'text-sm font-medium';
    statusValue.textContent = String(draft?.status || 'unknown');

    const divider1 = document.createElement('div');
    divider1.className = 'divider my-3';

    const progressLabel = document.createElement('div');
    progressLabel.className = 'text-xs text-muted mb-1';
    progressLabel.textContent = '进度';
    const progressValue = document.createElement('div');
    progressValue.className = 'text-sm font-medium';
    progressValue.textContent = `${Number(draft?.success_count || 0)}/${Number(draft?.success_threshold || 0)}`;

    summary.append(statusLabel, statusValue, divider1, progressLabel, progressValue);

    const msg = String(draft?.message || '').trim();
    if (msg) {
        const divider2 = document.createElement('div');
        divider2.className = 'divider my-3';
        const msgLabel = document.createElement('div');
        msgLabel.className = 'text-xs text-muted mb-1';
        msgLabel.textContent = '说明';
        const msgValue = document.createElement('div');
        msgValue.className = 'text-sm';
        msgValue.textContent = msg;
        summary.append(divider2, msgLabel, msgValue);
    }
    host.appendChild(summary);

    const actions = document.createElement('div');
    actions.className = 'flex flex-wrap gap-2 mt-4';

    const btnContinue = document.createElement('button');
    btnContinue.className = 'btn btn-secondary btn-sm';
    btnContinue.textContent = '继续验证';
    btnContinue.disabled = !draft?.can_continue;
    btnContinue.onclick = () => void continueDraft(draft);

    const btnDistill = document.createElement('button');
    btnDistill.className = 'btn btn-primary btn-sm';
    btnDistill.textContent = '生成草稿';
    btnDistill.disabled = !draft?.can_distill;
    btnDistill.onclick = () => void distillDraft(draft);

    const btnReplay = document.createElement('button');
    btnReplay.className = 'btn btn-secondary btn-sm';
    btnReplay.textContent = '编辑并重放';
    btnReplay.disabled = !draft?.can_continue;
    btnReplay.onclick = () => void openReplayInTasksTab(draft);

    actions.append(btnContinue, btnReplay, btnDistill);
    host.appendChild(actions);

    const advice = draft?.latest_failure_advice;
    if (advice?.summary || advice?.suggested_prompt) {
        const card = document.createElement('div');
        card.className = 'panel mt-4';
        card.style.padding = '12px';
        const titleEl = document.createElement('div');
        titleEl.className = 'text-sm font-medium mb-2';
        titleEl.textContent = '失败建议';
        card.appendChild(titleEl);

        const lines = document.createElement('div');
        lines.className = 'text-sm';
        const parts = [];
        if (advice.summary) parts.push(String(advice.summary));
        if (Array.isArray(advice.suggestions) && advice.suggestions.length) {
            parts.push(`建议：${advice.suggestions.join('；')}`);
        }
        if (advice.suggested_prompt) {
            parts.push(`推荐提示词：${advice.suggested_prompt}`);
        }
        lines.textContent = parts.join(' ');
        card.appendChild(lines);

        const applyBtn = document.createElement('button');
        applyBtn.className = 'btn btn-secondary btn-sm mt-3';
        applyBtn.textContent = '应用建议到任务表单';
        applyBtn.onclick = () => void applySuggestion(draft);
        card.appendChild(applyBtn);
        host.appendChild(card);
    }
}


async function loadDrafts() {
    const btn = $('refreshDrafts');
    if (btn) btn.disabled = true;
    try {
        const r = await fetchJson('/api/tasks/drafts', { silentErrors: true });
        if (!r.ok) {
            toast.error(r.data?.detail || '加载草稿失败');
            return;
        }
        draftListCache = Array.isArray(r.data) ? r.data : [];
        renderDraftsList(draftListCache);
        if (!selectedDraftId && draftListCache.length > 0) {
            const firstId = String(draftListCache[0]?.draft_id || '').trim();
            if (firstId) {
                selectedDraftId = firstId;
                renderDraftsList(draftListCache);
                await loadDraftDetail(firstId);
            }
        }
        if (selectedDraftId) {
            const exists = draftListCache.some((d) => String(d?.draft_id || '') === selectedDraftId);
            if (!exists) {
                selectedDraftId = '';
                renderDraftDetailEmpty();
            }
        }
    } finally {
        if (btn) btn.disabled = false;
    }
}

function renderDraftDetailEmpty() {
    const empty = $('draftDetailEmpty');
    const host = $('draftDetail');
    if (empty) empty.style.display = 'block';
    if (host) {
        host.style.display = 'none';
        clearElement(host);
    }
}

async function loadDraftDetail(draftId) {
    const hint = $('draftDetailHint');
    if (hint) hint.textContent = `草稿 ${draftId}`;
    const r = await fetchJson(`/api/tasks/drafts/${encodeURIComponent(draftId)}`, { silentErrors: true });
    if (!r.ok) {
        toast.error(r.data?.detail || '加载草稿详情失败');
        renderDraftDetailEmpty();
        return;
    }
    renderDraftDetail(r.data);
}

async function continueDraft(draft) {
    const draftId = String(draft?.draft_id || '').trim();
    if (!draftId) return;
    const r = await fetchJson(`/api/tasks/drafts/${encodeURIComponent(draftId)}/continue`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ count: 1 }),
        silentErrors: true,
    });
    if (!r.ok) {
        toast.error(r.data?.detail || '继续验证失败');
        return;
    }
    toast.success('已创建新的验证任务');
    await loadDrafts();
    await loadDraftDetail(draftId);
}

async function distillDraft(draft) {
    const draftId = String(draft?.draft_id || '').trim();
    if (!draftId) return;
    const r = await fetchJson(`/api/tasks/drafts/${encodeURIComponent(draftId)}/distill`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force: false }),
        silentErrors: true,
    });
    if (!r.ok) {
        toast.error(r.data?.detail || '蒸馏失败');
        return;
    }
    if (r.data?.ok === false) {
        toast.error(String(r.data?.message || '蒸馏失败'));
        return;
    }
    toast.success('草稿已生成');
    await loadDrafts();
    await loadDraftDetail(draftId);
}

function switchToTasksTab() {
    const btn = document.querySelector('.nav-item[data-tab="tab-tasks"]');
    if (btn) {
        btn.click();
    }
}

async function openReplayInTasksTab(draft) {
    const draftId = String(draft?.draft_id || '').trim();
    if (!draftId) return;

    const r = await fetchJson(`/api/tasks/drafts/${encodeURIComponent(draftId)}/snapshot`, {
        silentErrors: true,
    });
    if (!r.ok) {
        toast.error(r.data?.detail || '获取回放快照失败');
        return;
    }
    const snapshot = r.data?.snapshot || {};
    const payload = snapshot.payload && typeof snapshot.payload === 'object' ? snapshot.payload : {};
    const targets = Array.isArray(snapshot.targets) ? snapshot.targets : [];
    const taskName = String(draft?.task_name || payload.task || 'agent_executor').trim();
    const appId = String(snapshot.identity?.app_id || payload.app_id || payload.app || '').trim();

    switchToTasksTab();
    await prefillTaskFromDraft({
        taskName,
        payload,
        targets,
        priority: snapshot.priority,
        maxRetries: snapshot.max_retries,
        appId,
        displayName: String(draft?.display_name || '').trim(),
        draftId,
        successThreshold: Number(draft?.success_threshold || 3),
        aiType: String(snapshot.ai_type || 'default'),
    });
    toast.info('已载入草稿快照，可修改后提交');
}

function applySuggestedPrompt(payload, suggested) {
    const next = payload && typeof payload === 'object' ? { ...payload } : {};
    const textKeys = ['goal', 'prompt', 'query', 'instruction', 'text', 'description'];
    const existing = textKeys.find((k) => typeof next[k] === 'string' && String(next[k] || '').trim());
    next[existing || 'goal'] = suggested;
    return next;
}

async function applySuggestion(draft) {
    const draftId = String(draft?.draft_id || '').trim();
    if (!draftId) return;
    const suggested = String(draft?.latest_failure_advice?.suggested_prompt || '').trim();
    if (!suggested) {
        toast.warn('暂无可应用的提示词');
        return;
    }

    const r = await fetchJson(`/api/tasks/drafts/${encodeURIComponent(draftId)}/snapshot`, {
        silentErrors: true,
    });
    if (!r.ok) {
        toast.error(r.data?.detail || '获取回放快照失败');
        return;
    }

    const snapshot = r.data?.snapshot || {};
    const payload = snapshot.payload && typeof snapshot.payload === 'object' ? snapshot.payload : {};
    const targets = Array.isArray(snapshot.targets) ? snapshot.targets : [];
    const taskName = String(draft?.task_name || payload.task || 'agent_executor').trim();
    const appId = String(snapshot.identity?.app_id || payload.app_id || payload.app || '').trim();

    switchToTasksTab();
    await prefillTaskFromDraft({
        taskName,
        payload: applySuggestedPrompt(payload, suggested),
        targets,
        priority: snapshot.priority,
        maxRetries: snapshot.max_retries,
        appId,
        displayName: String(draft?.display_name || '').trim(),
        draftId,
        successThreshold: Number(draft?.success_threshold || 3),
        aiType: String(snapshot.ai_type || 'default'),
    });
    toast.info('已应用建议到任务表单');
}

export function initDrafts() {
    const btn = $('refreshDrafts');
    if (btn) btn.onclick = loadDrafts;
    renderDraftDetailEmpty();
    loadDrafts();
}
