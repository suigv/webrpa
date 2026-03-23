import { fetchJson } from '../utils/api.js';
import { toast } from '../ui/toast.js';
import { sysLog } from './logs.js';

let catalogCache = null;
let catalogPromise = null;
const CANONICAL_ACCOUNT_KEYS = ['account', 'password', 'twofa_secret'];
const LEGACY_ACCOUNT_KEYS = ['acc', 'pwd', 'fa2_secret'];
const ACCOUNT_INPUT_KEYS = new Set([
    ...CANONICAL_ACCOUNT_KEYS,
    ...LEGACY_ACCOUNT_KEYS,
    'two_factor_code',
]);
const RUNTIME_ONLY_PAYLOAD_KEYS = new Set([
    'device_ip',
    'device_id',
    'cloud_id',
    'target_device_id',
    'target_cloud_id',
    'target_label',
]);

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

export function getTaskCatalogEntry(taskName) {
    return getCatalogTask(taskName);
}

export async function getTaskInputDefinition(taskName, inputName) {
    if (!taskName || !inputName) {
        return null;
    }
    if (!catalogCache) {
        await getTaskCatalog();
    }
    const task = getCatalogTask(taskName);
    if (!task || !Array.isArray(task.inputs)) {
        return null;
    }
    return task.inputs.find((item) => item?.name === inputName) || null;
}

export async function taskDeclaresInput(taskName, inputName) {
    return Boolean(await getTaskInputDefinition(taskName, inputName));
}

export async function taskAcceptsAccount(taskName) {
    if (!taskName) {
        return false;
    }
    if (!catalogCache) {
        await getTaskCatalog();
    }
    const task = getCatalogTask(taskName);
    if (!task || !Array.isArray(task.inputs)) {
        return false;
    }
    return task.inputs.some((item) => ACCOUNT_INPUT_KEYS.has(String(item?.name || '').trim()));
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
        Object.entries(payload).filter(
            ([key]) =>
                declaredKeys.has(key) ||
                key.startsWith('_')
        )
    );
}

export function stripRuntimeOnlyPayloadFields(payload = {}) {
    if (!payload || typeof payload !== 'object') {
        return {};
    }
    return Object.fromEntries(
        Object.entries(payload).filter(([key]) => !RUNTIME_ONLY_PAYLOAD_KEYS.has(key))
    );
}

export async function resolveTaskAppContext(taskName, {
    rawPayload = {},
    fallbackAppId = '',
} = {}) {
    const payload = rawPayload && typeof rawPayload === 'object' ? rawPayload : {};
    const explicitAppId = String(payload.app_id || payload.app || '').trim();
    if (explicitAppId) {
        return explicitAppId;
    }
    const normalizedFallback = String(fallbackAppId || '').trim();
    if (normalizedFallback) {
        return normalizedFallback;
    }
    const declared = await getTaskInputDefinition(taskName, 'app_id');
    if (!declared) {
        return '';
    }
    const declaredDefault = String(declared.default || '').trim();
    return declaredDefault;
}

function _setAccountFields(payload, account, declaredKeys, mode) {
    if (!account || typeof account !== 'object') {
        return payload;
    }

    const nextPayload = { ...payload };
    const accountName = String(account.account || '').trim();
    const password = String(account.password || '').trim();
    const twofa = String(account.twofa || '').trim();
    const canWrite = (key) => !declaredKeys || declaredKeys.has(key);

    if (mode === 'canonical') {
        if (accountName && canWrite('account')) nextPayload.account = accountName;
        if (password && canWrite('password')) nextPayload.password = password;
        if (twofa && canWrite('twofa_secret')) nextPayload.twofa_secret = twofa;
    } else {
        if (accountName && canWrite('acc')) nextPayload.acc = accountName;
        if (password && canWrite('pwd')) nextPayload.pwd = password;
        if (twofa && canWrite('fa2_secret')) nextPayload.fa2_secret = twofa;
    }

    if (twofa && canWrite('two_factor_code')) {
        nextPayload.two_factor_code = twofa;
    }
    return nextPayload;
}

export async function injectAccountPayload(taskName, payload = {}, account = null) {
    if (!taskName || !payload || typeof payload !== 'object' || !account || typeof account !== 'object') {
        return { ...payload };
    }

    if (!catalogCache) {
        await getTaskCatalog();
    }

    const task = getCatalogTask(taskName);
    const declaredKeys = task && Array.isArray(task.inputs)
        ? new Set(task.inputs.map((item) => item.name).filter(Boolean))
        : null;

    const prefersCanonical = declaredKeys
        ? CANONICAL_ACCOUNT_KEYS.some((key) => declaredKeys.has(key))
        : false;
    const prefersLegacy = declaredKeys
        ? LEGACY_ACCOUNT_KEYS.some((key) => declaredKeys.has(key))
        : false;

    if (prefersCanonical) {
        return _setAccountFields(payload, account, declaredKeys, 'canonical');
    }
    if (prefersLegacy || !declaredKeys) {
        return _setAccountFields(payload, account, declaredKeys, 'legacy');
    }
    return _setAccountFields(payload, account, declaredKeys, 'canonical');
}

export async function prepareTaskPayload(taskName, {
    rawPayload = {},
    account = null,
    appId = null,
    stripRuntimeOnly = false,
} = {}) {
    let nextPayload = rawPayload && typeof rawPayload === 'object'
        ? { ...rawPayload }
        : {};

    if (stripRuntimeOnly) {
        nextPayload = stripRuntimeOnlyPayloadFields(nextPayload);
    }

    nextPayload = await injectAccountPayload(taskName, nextPayload, account);

    const normalizedAppId = String(appId || '').trim();
    if (normalizedAppId && await taskDeclaresInput(taskName, 'app_id')) {
        nextPayload.app_id = normalizedAppId;
    }

    return sanitizePayloadForTask(taskName, nextPayload);
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

export function resolveTaskDisplayName(taskData, catalog = catalogCache) {
    if (!taskData || typeof taskData !== 'object') {
        return null;
    }

    const explicitDisplayName = String(taskData.display_name || '').trim();
    if (explicitDisplayName) {
        return explicitDisplayName;
    }

    const taskName = String(taskData.task_name || taskData.task || '').trim();
    if (taskName && Array.isArray(catalog) && catalog.length > 0) {
        const matched = catalog.find((item) => item?.task === taskName);
        const catalogDisplayName = String(matched?.display_name || '').trim();
        if (catalogDisplayName) {
            return catalogDisplayName;
        }
    }

    return taskName || null;
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
            const taskDisplayName = resolveTaskDisplayName(taskData);
            sysLog(`[任务] ${taskDisplayName} 已分配至云机 ${describeTargets(taskData)}`);
        }
        if (openReport && typeof window !== 'undefined' && r.data?.task_id) {
            window.dispatchEvent(new CustomEvent('webrpa:task-submitted', {
                detail: {
                    taskId: r.data.task_id,
                    taskName: taskData.task,
                    displayName: resolveTaskDisplayName(r.data),
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
