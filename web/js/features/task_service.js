import { fetchJson } from '../utils/api.js';
import { toast } from '../ui/toast.js';
import { sysLog } from './logs.js';

let catalogCache = null;

/**
 * 获取插件目录（单例缓存）
 */
export async function getTaskCatalog() {
    if (catalogCache) return catalogCache;
    const r = await fetchJson("/api/tasks/catalog");
    if (r.ok) {
        catalogCache = r.data.tasks || [];
        return catalogCache;
    }
    return [];
}

/**
 * 统一的任务提交入口
 * @param {Object} payload 任务体 
 */
export async function apiSubmitTask(taskData) {
    const r = await fetchJson("/api/tasks/", { 
        method: "POST", 
        body: JSON.stringify(taskData) 
    });
    
    if (r.ok) {
        toast.success("指令已送达执行池");
        const targetDesc = taskData.targets?.length 
            ? taskData.targets.map(t => `#${t.device_id}-${t.cloud_id}`).join(', ')
            : "集群分发";
        sysLog(`[指令] ${taskData.task} -> ${targetDesc}`);
        return { ok: true, data: r.data };
    } else {
        toast.error("指令下发熔断");
        sysLog(`[错误] 任务下发失败: ${taskData.task}`, "error");
        return { ok: false };
    }
}
