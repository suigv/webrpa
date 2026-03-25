import { resolveAiDialogSubmitState } from './ai_dialog_submit_state.js';

function clearElement(element) {
    if (element) {
        element.replaceChildren();
    }
}

const REUSE_PRIORITY_LABELS = {
    distill_sample: '优先蒸馏样本',
    continue_trace: '优先继续复用',
    context_only: '优先复用上下文',
    none: '暂无可复用资产',
};

const REUSE_ACTION_LABELS = {
    distill_or_validate: '继续验证或进入蒸馏',
    continue_from_memory: '沿最近运行继续',
    reuse_context: '带上下文继续执行',
    fresh_exploration: '重新探索执行',
};

const QUALIFICATION_LABELS = {
    distillable: '可蒸馏',
    replayable: '可继续执行',
    useful_trace: '有价值轨迹',
    context_only: '仅上下文可复用',
    discard: '未形成复用价值',
};

function plannerBadgeState(plan) {
    const execution = plan?.execution || {};
    const followUp = plan?.follow_up || {};
    const missing = Array.isArray(followUp?.missing) ? followUp.missing.length : 0;
    if (execution?.distill_eligible) {
        return { className: 'badge badge-ok', text: '可蒸馏' };
    }
    if (missing > 0) {
        return { className: 'badge badge-error', text: '待补充' };
    }
    const reusePriority = String(execution?.reuse_priority || '').trim();
    if (reusePriority === 'continue_trace') {
        return { className: 'badge badge-ok', text: '可复用' };
    }
    if (reusePriority === 'context_only') {
        return { className: 'badge', text: '有上下文' };
    }
    return { className: 'badge badge-ok', text: '已就绪' };
}

function formatReusePriority(priority) {
    return REUSE_PRIORITY_LABELS[String(priority || '').trim()] || '待评估';
}

function formatReuseAction(action) {
    return REUSE_ACTION_LABELS[String(action || '').trim()] || '继续执行';
}

function formatQualification(value) {
    return QUALIFICATION_LABELS[String(value || '').trim()] || '待评估';
}

export function applyPlannerSubmitState(button, plan, defaultLabel = '下发任务') {
    if (!button) return;
    const state = resolveAiDialogSubmitState(plan);
    button.disabled = Boolean(state.disabled);
    button.textContent = state.label || defaultLabel;
    button.title = state.title || '';
}

export function renderPlannerStateLoading(elements, { submitButton = null, submitLabel = '下发任务' } = {}) {
    const {
        card,
        title,
        summary,
        badge,
        guidance,
        controlFlow,
        scriptsHost,
        followUp,
    } = elements;
    if (card) card.style.display = 'block';
    if (title) title.textContent = 'AI 任务规划';
    if (summary) summary.textContent = '正在分析当前 goal 与应用上下文…';
    if (badge) {
        badge.className = 'badge';
        badge.textContent = '分析中';
    }
    applyPlannerSubmitState(submitButton, null, submitLabel);
    clearElement(guidance);
    clearElement(controlFlow);
    clearElement(scriptsHost);
    clearElement(followUp);
}

export function clearPlannerCard(elements, { submitButton = null, submitLabel = '下发任务' } = {}) {
    const { card, guidance, controlFlow, scriptsHost, followUp } = elements;
    if (card) card.style.display = 'none';
    applyPlannerSubmitState(submitButton, null, submitLabel);
    clearElement(guidance);
    clearElement(controlFlow);
    clearElement(scriptsHost);
    clearElement(followUp);
}

export function renderPlannerResult(elements, plan, { submitButton = null, submitLabel = '下发任务' } = {}) {
    const {
        card,
        title,
        summary,
        badge,
        guidance,
        controlFlow,
        scriptsHost,
        followUp,
    } = elements;
    if (card) card.style.display = plan ? 'block' : 'none';
    if (!plan) return;

    if (title) title.textContent = String(plan.display_name || 'AI 任务规划');
    if (summary) summary.textContent = String(plan.operator_summary || '').trim();
    if (badge) {
        const badgeState = plannerBadgeState(plan);
        badge.className = badgeState.className;
        badge.textContent = badgeState.text;
    }
    applyPlannerSubmitState(submitButton, plan, submitLabel);

    clearElement(guidance);
    const guidanceSummary = String(plan.guidance?.summary || '').trim();
    if (guidanceSummary) {
        const wrapper = document.createElement('div');
        wrapper.className = 'task-guide-card';

        const heading = document.createElement('div');
        heading.className = 'task-guide-title';
        heading.textContent = String(plan.guidance?.title || '蒸馏写法建议').trim();
        wrapper.appendChild(heading);

        const text = document.createElement('div');
        text.className = 'task-guide-text';
        text.textContent = guidanceSummary;
        wrapper.appendChild(text);

        const tags = document.createElement('div');
        tags.className = 'task-guide-tags';
        const guidanceSuggestions = Array.isArray(plan.guidance?.suggestions)
            ? plan.guidance.suggestions
            : [];
        guidanceSuggestions.slice(0, 3).forEach((item) => {
            const tip = String(item || '').trim();
            if (!tip) return;
            const chip = document.createElement('span');
            chip.className = 'task-guide-tag';
            chip.textContent = tip;
            tags.appendChild(chip);
        });
        const example = String(plan.guidance?.example || '').trim();
        if (example) {
            const chip = document.createElement('span');
            chip.className = 'task-guide-tag';
            chip.textContent = example;
            tags.appendChild(chip);
        }
        if (tags.childElementCount > 0) {
            wrapper.appendChild(tags);
        }
        guidance?.appendChild(wrapper);
    }

    clearElement(controlFlow);
    const controlFlowItems = Array.isArray(plan.control_flow?.items) ? plan.control_flow.items : [];
    if (controlFlowItems.length > 0) {
        const wrapper = document.createElement('div');
        wrapper.className = 'task-summary-target';

        const heading = document.createElement('div');
        heading.className = 'task-guide-title';
        heading.textContent = '已识别的控制流提示';
        wrapper.appendChild(heading);

        const tags = document.createElement('div');
        tags.className = 'task-guide-tags';
        controlFlowItems.slice(0, 4).forEach((item) => {
            const text = String(item?.text || '').trim();
            if (!text) return;
            const chip = document.createElement('span');
            chip.className = 'task-guide-tag';
            const label = String(item?.label || item?.type || '').trim();
            chip.textContent = label ? `${label}：${text}` : text;
            tags.appendChild(chip);
        });
        if (tags.childElementCount > 0) {
            wrapper.appendChild(tags);
            controlFlow?.appendChild(wrapper);
        }
    }

    clearElement(scriptsHost);
    const declarativeScripts = Array.isArray(plan.declarative_scripts) ? plan.declarative_scripts : [];
    if (declarativeScripts.length > 0) {
        const wrapper = document.createElement('div');
        wrapper.className = 'task-summary-target';

        const heading = document.createElement('div');
        heading.className = 'task-guide-title';
        heading.textContent = '声明脚本草案';
        wrapper.appendChild(heading);

        declarativeScripts.slice(0, 4).forEach((script) => {
            const item = document.createElement('div');
            item.className = 'declarative-script-card';

            const itemHeader = document.createElement('div');
            itemHeader.className = 'task-summary-target-header';

            const itemTitle = document.createElement('div');
            itemTitle.className = 'task-summary-target-label';
            itemTitle.textContent = String(script?.title || script?.name || '未命名脚本').trim();
            itemHeader.appendChild(itemTitle);

            const roleBadge = document.createElement('span');
            roleBadge.className = 'badge';
            roleBadge.textContent = String(script?.role || 'utility').trim();
            itemHeader.appendChild(roleBadge);
            item.appendChild(itemHeader);

            const desc = document.createElement('div');
            desc.className = 'task-summary-target-message';
            desc.textContent = String(script?.description || script?.goal || '').trim();
            item.appendChild(desc);

            const meta = [];
            if (script?.app_id) meta.push(`App：${script.app_id}`);
            if (script?.app_scope) meta.push(`范围：${script.app_scope}`);
            if (Array.isArray(script?.stages) && script.stages.length) {
                meta.push(`阶段：${script.stages.map((stage) => String(stage?.title || stage?.name || '').trim()).filter(Boolean).join(' / ')}`);
            }
            if (Array.isArray(script?.consumes) && script.consumes.length) {
                meta.push(`依赖：${script.consumes.slice(0, 3).map((entry) => String(entry?.name || '').trim()).filter(Boolean).join('、')}`);
            }
            if (Array.isArray(script?.produces) && script.produces.length) {
                meta.push(`产出：${script.produces.slice(0, 3).map((entry) => String(entry?.name || '').trim()).filter(Boolean).join('、')}`);
            }

            meta.slice(0, 4).forEach((text) => {
                const row = document.createElement('div');
                row.className = 'task-summary-line';
                row.textContent = text;
                item.appendChild(row);
            });

            wrapper.appendChild(item);
        });

        scriptsHost?.appendChild(wrapper);
    }

    clearElement(followUp);
    const lines = [];
    if (plan.resolved_app?.app_id) {
        lines.push(`应用上下文：${plan.resolved_app.app_id}`);
    }
    if (plan.intent?.label) {
        lines.push(`任务意图：${String(plan.intent.label).trim()}`);
    }
    if (plan.branch?.label) {
        lines.push(`业务分支：${String(plan.branch.label).trim()}`);
    }
    if (plan.account?.execution_hint) {
        lines.push(String(plan.account.execution_hint).trim());
    }
    if (plan.execution?.reuse_priority) {
        lines.push(`复用优先级：${formatReusePriority(plan.execution.reuse_priority)}`);
    }
    if (plan.execution?.reuse_action) {
        lines.push(`当前出口：${formatReuseAction(plan.execution.reuse_action)}`);
    }
    if (plan.memory?.qualification) {
        lines.push(`最近运行价值：${formatQualification(plan.memory.qualification)}`);
    }
    if (plan.execution?.distill_eligible) {
        lines.push('蒸馏资格：当前已有可蒸馏样本，可进入蒸馏评估');
    }
    const recommendedWorkflow = Array.isArray(plan.recommended_workflows)
        ? plan.recommended_workflows.find((item) => String(item?.task || '').trim() !== 'agent_executor')
        : null;
    if (recommendedWorkflow?.display_name) {
        lines.push(`推荐流程：${String(recommendedWorkflow.display_name).trim()}`);
    }
    if (plan.account?.strategy === 'selected' && plan.account?.selected_account) {
        lines.push(`执行账号：${plan.account.selected_account}`);
    } else if (plan.account?.ready_count > 0) {
        lines.push(`账号池：当前有 ${plan.account.ready_count} 个可用账号`);
    }
    if (Array.isArray(plan.follow_up?.suggestions)) {
        plan.follow_up.suggestions.forEach((item) => {
            const text = String(item || '').trim();
            if (text) lines.push(text);
        });
    }
    lines.slice(0, 6).forEach((text) => {
        const row = document.createElement('div');
        row.className = 'task-summary-line';
        row.textContent = text;
        followUp?.appendChild(row);
    });
}
