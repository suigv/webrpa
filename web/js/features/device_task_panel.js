import { toast } from '../ui/toast.js';
import { renderTaskFormPanel } from '../utils/task_form_ui.js';
import {
    apiSubmitTask,
    buildTaskRequest,
    collectTaskPayload,
    sanitizePayloadForTask,
} from './task_service.js';
import { sysLog } from './logs.js';

function findCatalogTask(catalog, taskName) {
    if (!Array.isArray(catalog) || !taskName) return null;
    return catalog.find((item) => item.task === taskName) || null;
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

    const payload = collectTaskPayload(fieldsContainer);
    if (account) {
        if (account.account) payload.acc = account.account;
        if (account.password) payload.pwd = account.password;
        if (account.twofa) {
            payload.two_factor_code = account.twofa;
            payload.fa2_secret = account.twofa;
        }
    }

    const sanitizedPayload = await sanitizePayloadForTask(taskName, payload);
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
    if (defaultPackage && !Object.prototype.hasOwnProperty.call(rawPayload, 'package')) {
        rawPayload.package = defaultPackage;
    }
    const payload = await sanitizePayloadForTask(taskName, rawPayload);
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
