import { fetchJson } from '../utils/api.js';
import { toast } from '../ui/toast.js';
import { sysLog } from './logs.js';

let catalogCache = null;
let catalogPromise = null;

/**
 * 获取插件目录（单例缓存）
 */
export async function getTaskCatalog() {
    if (catalogCache) return catalogCache;
    if (catalogPromise) return catalogPromise;

    catalogPromise = (async () => {
        try {
            const r = await fetchJson("/api/tasks/catalog");
            if (r.ok) {
                catalogCache = r.data.tasks || [];
                return catalogCache;
            }
            return [];
        } finally {
            catalogPromise = null;
        }
    })();

    return catalogPromise;
}

function getCatalogTask(taskName) {
    if (!taskName || !Array.isArray(catalogCache)) {
        return null;
    }
    return catalogCache.find(item => item.task === taskName) || null;
}

export function collectTaskPayload(container) {
    const payload = {};
    if (!container) return payload;
    container.querySelectorAll('[data-payload-key]').forEach(input => {
        const key = input.dataset.payloadKey;
        const type = input.dataset.payloadType || 'string';
        if (!key) return;

        if (type === 'boolean') {
            payload[key] = Boolean(input.checked);
            return;
        }

        const rawValue = typeof input.value === 'string' ? input.value.trim() : input.value;
        if (rawValue === '' || rawValue === null || rawValue === undefined) {
            return;
        }

        if (type === 'integer') {
            const parsed = Number.parseInt(rawValue, 10);
            if (!Number.isNaN(parsed)) {
                payload[key] = parsed;
            }
            return;
        }

        if (type === 'number') {
            const parsed = Number(rawValue);
            if (!Number.isNaN(parsed)) {
                payload[key] = parsed;
            }
            return;
        }

        payload[key] = rawValue;
    });
    return payload;
}

export async function sanitizePayloadForTask(taskName, payload = {}) {
    if (!taskName || !payload || typeof payload !== 'object') {
        return {};
    }

    if (!catalogCache) {
        await getTaskCatalog();
    }

    const task = getCatalogTask(taskName);
    if (!task || !Array.isArray(task.inputs) || task.inputs.length === 0) {
        return { ...payload };
    }

    const declaredKeys = new Set(task.inputs.map(item => item.name).filter(Boolean));
    return Object.fromEntries(
        Object.entries(payload).filter(([key]) => declaredKeys.has(key) || key.startsWith('_'))
    );
}

export function buildTaskRequest({
    task,
    payload = {},
    targets,
    priority = 50,
    maxRetries = 0,
    runAt = null,
}) {
    const request = {
        task,
        payload,
        priority: Number(priority || 50),
        max_retries: Number(maxRetries || 0),
        run_at: runAt || null,
    };
    if (Array.isArray(targets) && targets.length) {
        request.targets = targets;
    }
    return request;
}

function describeTargets(taskData) {
    return taskData.targets?.length
        ? taskData.targets.map(t => `#${t.device_id}-${t.cloud_id}`).join(', ')
        : '未指定目标';
}

/**
 * 统一的任务提交入口
 * @param {Object} payload 任务体
 */
export async function apiSubmitTask(taskData, options = {}) {
    const { notify = true, log = true, openReport = true } = options;
    const r = await fetchJson("/api/tasks/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(taskData),
        silentErrors: true,
    });

    if (r.ok) {
        if (notify) {
            toast.success("任务已提交，节点正在启动...");
        }
        if (log) {
            // 尝试从缓存中查找中文名
            const taskObj = (catalogCache || []).find(x => x.task === taskData.task);
            const taskDisplayName = taskObj ? taskObj.display_name : taskData.task;
            sysLog(`[任务] ${taskDisplayName} 已分配至云机 ${describeTargets(taskData)}`);
        }
        if (openReport && typeof window !== 'undefined' && r.data?.task_id) {
            window.dispatchEvent(new CustomEvent('webrpa:task-submitted', {
                detail: {
                    taskId: r.data.task_id,
                    taskName: taskData.task,
                    displayName: r.data.display_name || null,
                },
            }));
        }
        return { ok: true, data: r.data };
    }

    if (notify) {
        toast.error("任务下发失败，请检查设备连通性");
    }
    if (log) {
        sysLog(`[异常] 任务提交失败: ${taskData.task}`, "error");
    }
    return { ok: false, data: r.data };
}
