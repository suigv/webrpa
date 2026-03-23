import { toast } from '../ui/toast.js';
import { renderTaskFormPanel } from '../utils/task_form_ui.js';
import {
    apiSubmitTask,
    buildTaskRequest,
    collectTaskPayload,
    prepareTaskPayload,
} from './task_service.js';
import { sysLog } from './logs.js';

const pipelineStateByContainer = new WeakMap();

function findCatalogTask(catalog, taskName) {
    if (!Array.isArray(catalog) || !taskName) return null;
    return catalog.find((item) => item.task === taskName) || null;
}

function clearElement(element) {
    if (element) {
        element.replaceChildren();
    }
}

function childPipelineCatalog(catalog) {
    return Array.isArray(catalog)
        ? catalog.filter((item) => item?.task && item.task !== '_pipeline')
        : [];
}

function pipelineDisplayName(catalog, taskName) {
    return findCatalogTask(catalog, taskName)?.display_name || taskName;
}

function getPipelineState(container) {
    return pipelineStateByContainer.get(container) || [];
}

function setPipelineState(container, steps) {
    pipelineStateByContainer.set(
        container,
        Array.isArray(steps)
            ? steps.map((step) => ({
                plugin: String(step.plugin || step.task || '').trim(),
                label: String(step.label || step.display_name || step.plugin || step.task || '').trim(),
                payloadText: step.payload && typeof step.payload === 'object'
                    ? JSON.stringify(step.payload, null, 2)
                    : String(step.payloadText || ''),
            }))
            : []
    );
}

function setFieldValues(container, payload) {
    if (!container || !payload || typeof payload !== 'object') return;
    container.querySelectorAll('[data-payload-key]').forEach((input) => {
        const key = input?.dataset?.payloadKey;
        if (!key || !(key in payload)) return;
        const value = payload[key];
        const type = input.dataset?.payloadType || 'string';
        if (type === 'boolean' || input.type === 'checkbox') {
            input.checked = Boolean(value);
            return;
        }
        if (value === null || value === undefined || typeof value === 'object') {
            return;
        }
        input.value = String(value);
    });
}

function renderRuntimePayloadFields(container) {
    if (!container) return;

    const block = document.createElement('div');
    block.className = 'form-grid columns-3 mt-4';
    block.innerHTML = `
        <div class="form-group">
            <label>执行速度</label>
            <select data-payload-key="_speed" data-payload-type="string">
                <option value="normal" selected>标准</option>
                <option value="fast">快速</option>
                <option value="slow">慢速</option>
            </select>
        </div>
        <div class="form-group">
            <label>步间等待最小值 (ms)</label>
            <input type="number" value="0" min="0" step="50" data-payload-key="_wait_min_ms" data-payload-type="integer">
        </div>
        <div class="form-group">
            <label>步间等待最大值 (ms)</label>
            <input type="number" value="0" min="0" step="50" data-payload-key="_wait_max_ms" data-payload-type="integer">
        </div>
    `;
    container.appendChild(block);

    const hint = document.createElement('div');
    hint.className = 'text-muted';
    hint.style.fontSize = '12px';
    hint.textContent = '速度档位会统一缩放拟真点击/输入节奏；步间等待会在普通 action 之间追加随机等待，不改变 ui.wait_until 本身超时。';
    container.appendChild(hint);
}

function renderPipelineComposer({ catalog, container, rerender }) {
    const composer = document.createElement('div');
    composer.className = 'pipeline-composer';

    const title = document.createElement('div');
    title.className = 'text-sm font-medium';
    title.textContent = '勾选要纳入编排的任务';
    composer.appendChild(title);

    const selectorGrid = document.createElement('div');
    selectorGrid.className = 'form-grid columns-2';
    const state = getPipelineState(container);
    childPipelineCatalog(catalog).forEach((task) => {
        const label = document.createElement('label');
        label.className = 'custom-checkbox inline-flex items-center gap-1';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = state.some((item) => item.plugin === task.task);
        checkbox.onchange = () => {
            const next = [...getPipelineState(container)];
            const taskName = String(task.task || '').trim();
            if (checkbox.checked) {
                if (!next.some((item) => item.plugin === taskName)) {
                    next.push({
                        plugin: taskName,
                        label: pipelineDisplayName(catalog, taskName),
                        payloadText: '',
                    });
                }
            } else {
                setPipelineState(
                    container,
                    next.filter((item) => item.plugin !== taskName)
                );
                rerender();
                return;
            }
            setPipelineState(container, next);
            rerender();
        };

        const checkmark = document.createElement('span');
        checkmark.className = 'checkmark';

        const text = document.createElement('span');
        text.textContent = String(task.display_name || task.task || '');

        label.append(checkbox, checkmark, text);
        selectorGrid.appendChild(label);
    });
    composer.appendChild(selectorGrid);

    const list = document.createElement('div');
    list.className = 'pipeline-step-list';
    const steps = getPipelineState(container);
    if (steps.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'text-muted';
        empty.style.fontSize = '12px';
        empty.textContent = '当前没有步骤，先勾选上方任务。';
        list.appendChild(empty);
    }

    steps.forEach((step, index) => {
        const card = document.createElement('div');
        card.className = 'pipeline-step-card';

        const header = document.createElement('div');
        header.className = 'pipeline-step-header';

        const stepTitle = document.createElement('div');
        stepTitle.className = 'task-summary-target-label';
        stepTitle.textContent = `步骤 ${index + 1}`;
        header.appendChild(stepTitle);

        const actions = document.createElement('div');
        actions.className = 'flex gap-2';

        const upBtn = document.createElement('button');
        upBtn.type = 'button';
        upBtn.className = 'btn btn-text btn-sm';
        upBtn.textContent = '上移';
        upBtn.disabled = index === 0;
        upBtn.onclick = () => {
            const next = [...getPipelineState(container)];
            [next[index - 1], next[index]] = [next[index], next[index - 1]];
            setPipelineState(container, next);
            rerender();
        };
        actions.appendChild(upBtn);

        const downBtn = document.createElement('button');
        downBtn.type = 'button';
        downBtn.className = 'btn btn-text btn-sm';
        downBtn.textContent = '下移';
        downBtn.disabled = index === steps.length - 1;
        downBtn.onclick = () => {
            const next = [...getPipelineState(container)];
            [next[index], next[index + 1]] = [next[index + 1], next[index]];
            setPipelineState(container, next);
            rerender();
        };
        actions.appendChild(downBtn);

        header.appendChild(actions);
        card.appendChild(header);

        const nameLabel = document.createElement('label');
        nameLabel.textContent = '显示名称';
        card.appendChild(nameLabel);

        const nameInput = document.createElement('input');
        nameInput.type = 'text';
        nameInput.value = step.label || pipelineDisplayName(catalog, step.plugin);
        nameInput.oninput = () => {
            step.label = nameInput.value;
            setPipelineState(container, steps);
        };
        card.appendChild(nameInput);

        const payloadLabel = document.createElement('label');
        payloadLabel.textContent = '步骤 payload JSON';
        card.appendChild(payloadLabel);

        const payloadInput = document.createElement('textarea');
        payloadInput.className = 'textarea-large';
        payloadInput.style.minHeight = '88px';
        payloadInput.placeholder = '{\n  "screen_name": "jack"\n}';
        payloadInput.value = step.payloadText || '';
        payloadInput.oninput = () => {
            step.payloadText = payloadInput.value;
            setPipelineState(container, steps);
        };
        card.appendChild(payloadInput);

        list.appendChild(card);
    });

    composer.appendChild(list);
    container.prepend(composer);
}

async function buildPipelinePayload(container) {
    const steps = getPipelineState(container);
    if (!steps.length) {
        return { ok: false, error: '请至少勾选一个 Pipeline 步骤' };
    }
    const normalized = [];
    for (const [index, step] of steps.entries()) {
        const plugin = String(step.plugin || '').trim();
        if (!plugin) {
            return { ok: false, error: `第 ${index + 1} 个步骤缺少插件` };
        }
        const rawPayload = String(step.payloadText || '').trim();
        let payload = {};
        if (rawPayload) {
            try {
                payload = JSON.parse(rawPayload);
            } catch {
                return { ok: false, error: `第 ${index + 1} 个步骤 payload JSON 无法解析` };
            }
            if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
                return { ok: false, error: `第 ${index + 1} 个步骤 payload 必须是 JSON 对象` };
            }
        }
        const sanitizedPayload = await prepareTaskPayload(plugin, {
            rawPayload: payload,
            stripRuntimeOnly: true,
        });
        normalized.push({
            plugin,
            label: String(step.label || pipelineDisplayName([], plugin) || plugin).trim() || plugin,
            payload: sanitizedPayload,
        });
    }
    return { ok: true, steps: normalized };
}

export function renderDeviceTaskForm({
    catalog,
    taskName,
    configContainer = null,
    guideCard,
    fieldsContainer,
    toggleButton,
    collapsedText,
    expandedText,
}) {
    if (!fieldsContainer) return;

    const task = findCatalogTask(catalog, taskName);
    const preservedPayload = collectTaskPayload(fieldsContainer);
    if (configContainer) {
        configContainer.style.display = task ? 'block' : 'none';
    }

    renderTaskFormPanel({
        task,
        guideCard,
        fieldsContainer,
        toggleButton,
        collapsedText,
        expandedText,
    });
    if (task) {
        renderRuntimePayloadFields(fieldsContainer);
    }
    if (taskName === '_pipeline') {
        renderPipelineComposer({
            catalog,
            container: fieldsContainer,
            rerender: () =>
                renderDeviceTaskForm({
                    catalog,
                    taskName,
                    configContainer,
                    guideCard,
                    fieldsContainer,
                    toggleButton,
                    collapsedText,
                    expandedText,
                }),
        });
    } else {
        pipelineStateByContainer.delete(fieldsContainer);
    }
    setFieldValues(fieldsContainer, preservedPayload);
}

export async function submitUnitPluginTask({
    catalog,
    unit,
    taskName,
    fieldsContainer,
    account = null,
    priority = 50,
    maxRetries = 0,
    runAt = null,
    onStarted = null,
    onFailed = null,
}) {
    if (!taskName || !fieldsContainer || !unit) return { ok: false, reason: 'invalid_params' };

    const rawPayload = collectTaskPayload(fieldsContainer);
    if (taskName === '_pipeline') {
        const pipelinePayload = await buildPipelinePayload(fieldsContainer);
        if (!pipelinePayload.ok) {
            toast.warn(pipelinePayload.error);
            return { ok: false, reason: 'invalid_pipeline' };
        }
        rawPayload.steps = pipelinePayload.steps;
    }
    const sanitizedPayload = await prepareTaskPayload(taskName, {
        rawPayload,
        account,
        stripRuntimeOnly: true,
    });
    const taskData = buildTaskRequest({
        task: taskName,
        payload: sanitizedPayload,
        targets: [{ device_id: unit.parent_id, cloud_id: unit.cloud_id }],
        priority,
        maxRetries,
        runAt,
    });

    const result = await apiSubmitTask(taskData);
    const task = findCatalogTask(catalog, taskName);
    const displayName = task ? task.display_name : taskName;

    if (result.ok) {
        onStarted?.({ taskName, displayName, result });
    } else {
        onFailed?.({ taskName, displayName, result });
    }
    return result;
}

export async function runBulkPluginTasks({
    catalog,
    taskName,
    fieldsContainer,
    selectedUnitIds,
    defaultPackage = '',
    confirmRun = (message) => window.confirm(message),
}) {
    const selectedIds = Array.isArray(selectedUnitIds) ? selectedUnitIds : [];
    const count = selectedIds.length;
    if (!taskName) {
        toast.warn('请先选择任务');
        return { ok: false, reason: 'missing_task' };
    }
    if (count === 0) {
        toast.warn('请先选择节点');
        return { ok: false, reason: 'missing_targets' };
    }
    if (!fieldsContainer) {
        return { ok: false, reason: 'missing_fields' };
    }
    if (!confirmRun(`即将对选中的 ${count} 个节点执行该操作，是否继续？`)) {
        return { ok: false, reason: 'cancelled' };
    }

    const rawPayload = collectTaskPayload(fieldsContainer);
    if (taskName === '_pipeline') {
        const pipelinePayload = await buildPipelinePayload(fieldsContainer);
        if (!pipelinePayload.ok) {
            toast.warn(pipelinePayload.error);
            return { ok: false, reason: 'invalid_pipeline' };
        }
        rawPayload.steps = pipelinePayload.steps;
    }
    if (defaultPackage && !Object.prototype.hasOwnProperty.call(rawPayload, 'package')) {
        rawPayload.package = defaultPackage;
    }
    const payload = await prepareTaskPayload(taskName, {
        rawPayload,
        stripRuntimeOnly: true,
    });
    sysLog(`开始集群派发任务: ${taskName}, 目标数量: ${count}`);

    for (const id of selectedIds) {
        const [deviceId, cloudId] = String(id).split('-');
        const taskData = buildTaskRequest({
            task: taskName,
            payload,
            targets: [{ device_id: Number.parseInt(deviceId, 10), cloud_id: Number.parseInt(cloudId, 10) }],
        });
        await apiSubmitTask(taskData, { notify: false, log: false, openReport: false });
    }

    toast.success('集群任务分发完成');
    return {
        ok: true,
        taskName,
        displayName: findCatalogTask(catalog, taskName)?.display_name || taskName,
        count,
    };
}
