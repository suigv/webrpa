import { fetchJson } from '../utils/api.js';
import { toast } from '../ui/toast.js';

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

function multilineText(values) {
    return Array.isArray(values) ? values.map((item) => String(item || '').trim()).filter(Boolean).join('\n') : '';
}

function parseMultilineText(value) {
    return String(value || '')
        .split('\n')
        .map((item) => item.trim())
        .filter(Boolean);
}

function deriveSnapshotAppId(snapshot) {
    const payload = snapshot?.snapshot?.payload || {};
    const identity = snapshot?.snapshot?.identity || {};
    return String(payload.app_id || identity.app_id || payload.app || '').trim();
}

function buildDetailMeta(draft, snapshot) {
    const identity = snapshot?.snapshot?.identity || {};
    const appId = deriveSnapshotAppId(snapshot);
    return [
        appId ? `应用 ${appId}` : '',
        identity.account ? `账号 ${String(identity.account)}` : '',
        identity.branch_id ? `分支 ${String(identity.branch_id)}` : '',
    ].filter(Boolean).join(' · ');
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

function renderDraftDetail(draft, detailState = {}) {
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
        buildDetailMeta(draft, detailState.snapshot),
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

    const btnOpenWorkspace = document.createElement('button');
    btnOpenWorkspace.className = 'btn btn-secondary btn-sm';
    btnOpenWorkspace.textContent = '转到 AI 工作台';
    btnOpenWorkspace.onclick = () => {
        switchToAiTab();
        toast.info('失败建议、会话复用与保存可复用项已收口到 AI 工作台');
    };

    actions.append(btnContinue, btnDistill, btnOpenWorkspace);
    host.appendChild(actions);

    const workspaceNote = document.createElement('div');
    workspaceNote.className = 'task-guide-card mt-4';
    const workspaceTitle = document.createElement('div');
    workspaceTitle.className = 'task-guide-title';
    workspaceTitle.textContent = '职责边界';
    const workspaceText = document.createElement('div');
    workspaceText.className = 'task-guide-text';
    workspaceText.textContent = '草稿详情仅保留验证、蒸馏和配置收敛信息；失败建议、会话复用和声明脚本阶段锚点统一在 AI 工作台查看。';
    workspaceNote.append(workspaceTitle, workspaceText);
    host.appendChild(workspaceNote);

    renderConfigCandidatesPanel(host, draft, detailState);
    renderBranchProfilesPanel(host, draft, detailState);
}

function renderConfigCandidatesPanel(host, draft, detailState) {
    const appId = deriveSnapshotAppId(detailState.snapshot);
    if (!appId) return;

    const bundle = detailState.candidateBundle;
    const card = document.createElement('div');
    card.className = 'panel mt-4';
    card.style.padding = '12px';

    const title = document.createElement('div');
    title.className = 'text-sm font-medium mb-2';
    title.textContent = '共享配置候选项';
    card.appendChild(title);

    const helper = document.createElement('div');
    helper.className = 'text-xs text-muted mb-3';
    helper.textContent = '蒸馏学到的选择器、状态、阶段识别和提示词会先进入候选池，只有审核后才写入共享 app 配置。';
    card.appendChild(helper);

    const list = document.createElement('div');
    list.className = 'flex-col gap-2';
    list.style.display = 'flex';
    card.appendChild(list);

    const candidates = Array.isArray(bundle?.candidates) ? bundle.candidates : [];
    if (!candidates.length) {
        const empty = document.createElement('div');
        empty.className = 'text-muted';
        empty.textContent = '当前草稿还没有待审核的共享配置候选项';
        list.appendChild(empty);
        host.appendChild(card);
        return;
    }

    const selected = new Set();
    candidates.forEach((candidate) => {
        const row = document.createElement('label');
        row.className = 'task-summary-target';
        row.style.display = 'block';
        row.style.cursor = 'pointer';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.style.marginRight = '10px';
        checkbox.onchange = () => {
            const candidateId = String(candidate.candidate_id || '');
            if (!candidateId) return;
            if (checkbox.checked) selected.add(candidateId);
            else selected.delete(candidateId);
        };

        const titleEl = document.createElement('div');
        titleEl.className = 'task-summary-target-label';
        titleEl.textContent = String(candidate.title || candidate.kind || '候选项');

        const header = document.createElement('div');
        header.className = 'task-summary-target-header';
        const titleWrap = document.createElement('div');
        titleWrap.style.display = 'flex';
        titleWrap.style.alignItems = 'center';
        titleWrap.append(checkbox, titleEl);

        const badge = document.createElement('span');
        badge.className = 'badge';
        badge.textContent = `证据 ${Number(candidate.evidence_count || 0)}`;
        header.append(titleWrap, badge);

        const message = document.createElement('div');
        message.className = 'task-summary-target-message';
        message.textContent = [
            String(candidate.preview || '').trim(),
            Number(candidate.occurrences || 0) > 1 ? `累计 ${Number(candidate.occurrences)} 次` : '',
        ].filter(Boolean).join(' · ');

        row.append(header, message);
        list.appendChild(row);
    });

    const actions = document.createElement('div');
    actions.className = 'flex gap-2 mt-3';

    const review = async (action) => {
        if (!selected.size) {
            toast.warn('请先勾选候选项');
            return;
        }
        const response = await fetchJson(
            `/api/ai_dialog/apps/${encodeURIComponent(appId)}/config_candidates/review`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    candidate_ids: Array.from(selected),
                    action,
                }),
                silentErrors: true,
            }
        );
        if (!response.ok) {
            toast.error(String(response.data?.detail || '审核共享配置候选项失败'));
            return;
        }
        toast.success(action === 'promote' ? '已写入共享配置' : '已忽略所选候选项');
        await loadDraftDetail(String(draft?.draft_id || '').trim());
    };

    const promoteButton = document.createElement('button');
    promoteButton.className = 'btn btn-primary btn-sm';
    promoteButton.textContent = '提升到共享配置';
    promoteButton.onclick = () => void review('promote');

    const rejectButton = document.createElement('button');
    rejectButton.className = 'btn btn-secondary btn-sm';
    rejectButton.textContent = '忽略所选';
    rejectButton.onclick = () => void review('reject');

    actions.append(promoteButton, rejectButton);
    card.appendChild(actions);
    host.appendChild(card);
}

function createBranchField(labelText, input) {
    const wrapper = document.createElement('div');
    wrapper.className = 'form-group';
    const label = document.createElement('label');
    label.textContent = labelText;
    wrapper.append(label, input);
    return wrapper;
}

function renderBranchProfilesPanel(host, draft, detailState) {
    const appId = deriveSnapshotAppId(detailState.snapshot);
    const bundle = detailState.branchBundle;
    if (!appId || !bundle) return;

    const card = document.createElement('div');
    card.className = 'panel mt-4';
    card.style.padding = '12px';

    const title = document.createElement('div');
    title.className = 'text-sm font-medium mb-2';
    title.textContent = '业务分支配置';
    card.appendChild(title);

    const helper = document.createElement('div');
    helper.className = 'text-xs text-muted mb-3';
    helper.textContent = '这里维护当前 app 的通用业务分支。单次任务仍可临时覆盖，但流水线和后续 AI 任务会优先复用这里的默认策略。';
    card.appendChild(helper);

    const defaultBranchInput = document.createElement('input');
    defaultBranchInput.type = 'text';
    defaultBranchInput.value = String(bundle.default_branch || 'default');
    defaultBranchInput.placeholder = '默认分支 ID，例如 default / volc / part_time';
    card.appendChild(createBranchField('默认分支 ID', defaultBranchInput));

    const rowsHost = document.createElement('div');
    rowsHost.className = 'flex-col gap-3 mt-3';
    rowsHost.style.display = 'flex';
    card.appendChild(rowsHost);

    const addBranchRow = (branch = {}) => {
        const row = document.createElement('div');
        row.className = 'task-summary-target';

        const header = document.createElement('div');
        header.className = 'flex justify-between items-center mb-2';

        const headerTitle = document.createElement('div');
        headerTitle.className = 'task-summary-target-label';
        headerTitle.textContent = `分支 ${String(branch.branch_id || '').trim() || '新分支'}`;

        const removeButton = document.createElement('button');
        removeButton.type = 'button';
        removeButton.className = 'btn btn-text btn-sm text-error';
        removeButton.textContent = '删除';
        removeButton.onclick = () => row.remove();
        header.append(headerTitle, removeButton);

        const grid = document.createElement('div');
        grid.className = 'form-grid columns-2';

        const branchIdInput = document.createElement('input');
        branchIdInput.type = 'text';
        branchIdInput.value = String(branch.branch_id || '').trim();
        branchIdInput.placeholder = 'branch_id';
        branchIdInput.dataset.field = 'branch_id';
        branchIdInput.oninput = () => {
            headerTitle.textContent = `分支 ${branchIdInput.value.trim() || '新分支'}`;
        };

        const labelInput = document.createElement('input');
        labelInput.type = 'text';
        labelInput.value = String(branch.label || '').trim();
        labelInput.placeholder = '显示名称';
        labelInput.dataset.field = 'label';

        const resourceInput = document.createElement('input');
        resourceInput.type = 'text';
        resourceInput.value = String(branch.resource_namespace || '').trim();
        resourceInput.placeholder = '资源命名空间（可选）';
        resourceInput.dataset.field = 'resource_namespace';

        const replyAiTypeInput = document.createElement('input');
        replyAiTypeInput.type = 'text';
        replyAiTypeInput.value = String(branch.reply_ai_type || '').trim();
        replyAiTypeInput.placeholder = '回复 AI 类型（可选）';
        replyAiTypeInput.dataset.field = 'reply_ai_type';

        const searchKeywordsInput = document.createElement('textarea');
        searchKeywordsInput.className = 'textarea-large';
        searchKeywordsInput.style.minHeight = '96px';
        searchKeywordsInput.value = multilineText(branch.search_keywords);
        searchKeywordsInput.placeholder = '搜索关键词，每行一个';
        searchKeywordsInput.dataset.field = 'search_keywords';

        const blacklistKeywordsInput = document.createElement('textarea');
        blacklistKeywordsInput.className = 'textarea-large';
        blacklistKeywordsInput.style.minHeight = '96px';
        blacklistKeywordsInput.value = multilineText(branch.blacklist_keywords);
        blacklistKeywordsInput.placeholder = '黑名单关键词，每行一个';
        blacklistKeywordsInput.dataset.field = 'blacklist_keywords';

        const replyTextsInput = document.createElement('textarea');
        replyTextsInput.className = 'textarea-large';
        replyTextsInput.style.minHeight = '96px';
        replyTextsInput.value = multilineText(branch.reply_texts);
        replyTextsInput.placeholder = '回复/互动文案，每行一个';
        replyTextsInput.dataset.field = 'reply_texts';

        const payloadDefaultsInput = document.createElement('textarea');
        payloadDefaultsInput.className = 'textarea-large';
        payloadDefaultsInput.style.minHeight = '96px';
        payloadDefaultsInput.value = Object.keys(branch.payload_defaults || {}).length
            ? JSON.stringify(branch.payload_defaults, null, 2)
            : '';
        payloadDefaultsInput.placeholder = '草稿默认值 JSON，例如 {\"keyword\":\"xxx\"}';
        payloadDefaultsInput.dataset.field = 'payload_defaults';

        const notesInput = document.createElement('textarea');
        notesInput.className = 'textarea-large';
        notesInput.style.minHeight = '72px';
        notesInput.value = String(branch.notes || '').trim();
        notesInput.placeholder = '备注（可选）';
        notesInput.dataset.field = 'notes';

        grid.append(
            createBranchField('分支 ID', branchIdInput),
            createBranchField('显示名称', labelInput),
            createBranchField('资源命名空间', resourceInput),
            createBranchField('回复 AI 类型', replyAiTypeInput),
        );
        row.append(
            header,
            grid,
            createBranchField('搜索关键词', searchKeywordsInput),
            createBranchField('黑名单关键词', blacklistKeywordsInput),
            createBranchField('回复文案', replyTextsInput),
            createBranchField('草稿默认值 JSON', payloadDefaultsInput),
            createBranchField('备注', notesInput),
        );
        rowsHost.appendChild(row);
    };

    const branches = Array.isArray(bundle.branches) ? bundle.branches : [];
    if (branches.length) {
        branches.forEach((branch) => addBranchRow(branch));
    } else {
        addBranchRow({ branch_id: String(bundle.default_branch || 'default') });
    }

    const actions = document.createElement('div');
    actions.className = 'flex gap-2 mt-3';

    const addButton = document.createElement('button');
    addButton.className = 'btn btn-secondary btn-sm';
    addButton.textContent = '新增分支';
    addButton.onclick = () => addBranchRow({});

    const saveButton = document.createElement('button');
    saveButton.className = 'btn btn-primary btn-sm';
    saveButton.textContent = '保存分支配置';
    saveButton.onclick = async () => {
        const rows = Array.from(rowsHost.children);
        const payload = {
            default_branch: defaultBranchInput.value.trim() || 'default',
            branches: [],
        };
        for (const row of rows) {
            const getField = (name) => row.querySelector(`[data-field="${name}"]`);
            const branchId = String(getField('branch_id')?.value || '').trim();
            if (!branchId) continue;
            const payloadDefaultsRaw = String(getField('payload_defaults')?.value || '').trim();
            let payloadDefaults = {};
            if (payloadDefaultsRaw) {
                try {
                    payloadDefaults = JSON.parse(payloadDefaultsRaw);
                } catch (_error) {
                    toast.error(`分支 ${branchId} 的草稿默认值 JSON 无法解析`);
                    return;
                }
            }
            payload.branches.push({
                branch_id: branchId,
                label: String(getField('label')?.value || '').trim() || null,
                search_keywords: parseMultilineText(getField('search_keywords')?.value),
                blacklist_keywords: parseMultilineText(getField('blacklist_keywords')?.value),
                reply_texts: parseMultilineText(getField('reply_texts')?.value),
                resource_namespace: String(getField('resource_namespace')?.value || '').trim() || null,
                reply_ai_type: String(getField('reply_ai_type')?.value || '').trim() || null,
                payload_defaults: payloadDefaults,
                notes: String(getField('notes')?.value || '').trim() || null,
            });
        }
        const response = await fetchJson(
            `/api/ai_dialog/apps/${encodeURIComponent(appId)}/branch_profiles`,
            {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
                silentErrors: true,
            }
        );
        if (!response.ok) {
            toast.error(String(response.data?.detail || '保存分支配置失败'));
            return;
        }
        toast.success('分支配置已保存');
        await loadDraftDetail(String(draft?.draft_id || '').trim());
    };

    actions.append(addButton, saveButton);
    card.appendChild(actions);
    host.appendChild(card);
}


export async function loadDrafts() {
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
    const detailState = {};
    const snapshotResponse = await fetchJson(`/api/tasks/drafts/${encodeURIComponent(draftId)}/snapshot`, {
        silentErrors: true,
    });
    if (snapshotResponse.ok) {
        detailState.snapshot = snapshotResponse.data;
        const appId = deriveSnapshotAppId(snapshotResponse.data);
        if (appId) {
            const [branchResponse, candidateResponse] = await Promise.all([
                fetchJson(`/api/ai_dialog/apps/${encodeURIComponent(appId)}/branch_profiles`, {
                    silentErrors: true,
                }),
                fetchJson(
                    `/api/ai_dialog/apps/${encodeURIComponent(appId)}/config_candidates?draft_id=${encodeURIComponent(draftId)}`,
                    { silentErrors: true }
                ),
            ]);
            if (branchResponse.ok) {
                detailState.branchBundle = branchResponse.data;
            }
            if (candidateResponse.ok) {
                detailState.candidateBundle = candidateResponse.data;
            }
        }
    }
    renderDraftDetail(r.data, detailState);
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

function switchToAiTab() {
    const btn = document.querySelector('.nav-item[data-tab="tab-ai"]');
    if (btn) {
        btn.click();
    }
}

export function initDrafts() {
    const btn = $('refreshDrafts');
    if (btn) btn.onclick = loadDrafts;
    renderDraftDetailEmpty();
    loadDrafts();
}
