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

export function collectTaskPayload(container) {
    const payload = {};
    if (!container) return payload;
    container.querySelectorAll('[data-payload-key]').forEach(input => {
        payload[input.dataset.payloadKey] = input.value;
    });
    return payload;
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
    const { notify = true, log = true } = options;
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
