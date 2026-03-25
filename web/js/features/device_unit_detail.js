import { authFetch, fetchJson } from '../utils/api.js';
import { promptAiTaskInputAnnotation } from './ai_task_annotations.js';
import { toast } from '../ui/toast.js';
import { store } from '../state/store.js';

const $ = (id) => document.getElementById(id);

let activeUnitTraceContext = null;
let detailUnitControlCleanup = null;

export function setUnitTakeoverTraceContext(context) {
    activeUnitTraceContext = context && typeof context === 'object'
        ? {
            ...context,
            takeoverRequested: Boolean(context.takeoverRequested),
            currentDeclarativeStage: context.currentDeclarativeStage && typeof context.currentDeclarativeStage === 'object'
                ? { ...context.currentDeclarativeStage }
                : null,
        }
        : null;
}

function traceContextForUnit(unit) {
    if (!unit || !activeUnitTraceContext) return null;
    const sameDevice = Number(activeUnitTraceContext.deviceId || 0) === Number(unit.parent_id || 0);
    const sameCloud = Number(activeUnitTraceContext.cloudId || 0) === Number(unit.cloud_id || 0);
    if (!sameDevice || !sameCloud) return null;
    return activeUnitTraceContext;
}

async function ensureHumanTakeover(traceContext) {
    if (!traceContext || traceContext.takeoverRequested) {
        return true;
    }
    const response = await fetchJson(`/api/tasks/${encodeURIComponent(traceContext.taskId)}/takeover`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            run_id: traceContext.runId,
            owner: 'web_console',
            reason: 'human_takeover_from_unit_controls',
            current_declarative_stage: traceContext.currentDeclarativeStage || undefined,
        }),
        silentErrors: true,
    });
    if (!response.ok) {
        return false;
    }
    traceContext.takeoverRequested = true;
    toast.info('已切换到人工接管，后续操作会写入蒸馏轨迹');
    return true;
}

function revokeSurfaceImage(img) {
    if (img?.src && img.src.startsWith('blob:')) {
        URL.revokeObjectURL(img.src);
    }
}

function buildSurfaceRefs(ids = {}) {
    const byId = (key) => {
        const value = String(ids[key] || '').trim();
        return value ? $(value) : null;
    };
    return {
        root: byId('root') || document,
        refreshBtn: byId('refreshBtn'),
        img: byId('img'),
        placeholder: byId('placeholder'),
        textInput: byId('textInput'),
        sendTextBtn: byId('sendTextBtn'),
        keyBack: byId('keyBack'),
        keyHome: byId('keyHome'),
        keyEnter: byId('keyEnter'),
        keyDelete: byId('keyDelete'),
        swipeUp: byId('swipeUp'),
        swipeLeft: byId('swipeLeft'),
        swipeDown: byId('swipeDown'),
        swipeRight: byId('swipeRight'),
    };
}

function surfaceControlButtons(refs) {
    return Array.from(refs.root?.querySelectorAll?.('[data-unit-control]') || []);
}

function setSurfaceControlBusy(refs, state, busy) {
    state.busy = busy;
    surfaceControlButtons(refs).forEach((button) => {
        button.disabled = busy;
    });
    if (refs.img) {
        refs.img.style.cursor = busy ? 'wait' : 'crosshair';
    }
}

async function loadUnitScreenshotIntoSurface(unit, refs) {
    return loadUnitScreenshotIntoSurfaceWithState(unit, refs, null, { force: true });
}

function shouldAutoRefreshSurface(refs) {
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
        return false;
    }
    const root = refs?.root;
    if (!root || root === document) {
        return true;
    }
    if (typeof root.isConnected === 'boolean' && !root.isConnected) {
        return false;
    }
    if (root.style && root.style.display === 'none') {
        return false;
    }
    return true;
}

async function loadUnitScreenshotIntoSurfaceWithState(unit, refs, state, { force = false } = {}) {
    const { img, placeholder } = refs;
    if (!img || !placeholder) return;
    if (!force && !shouldAutoRefreshSurface(refs)) {
        return;
    }
    if (state?.screenshotInFlight) {
        return;
    }
    if (state) {
        state.screenshotInFlight = true;
    }
    if (unit.availability_state !== 'available') {
        img.style.visibility = 'hidden';
        placeholder.textContent = '设备离线，无法获取截图';
        placeholder.style.visibility = 'visible';
        if (state) {
            state.screenshotInFlight = false;
        }
        return;
    }
    try {
        const url = `/api/devices/${unit.parent_id}/${unit.cloud_id}/screenshot?t=${Date.now()}`;
        const response = await authFetch(url);
        if (!response.ok) {
            let reason = `HTTP ${response.status}`;
            const body = await response.json().catch(() => null);
            if (body?.detail) reason = body.detail;
            if (response.status === 502) reason = `设备不可达 (${reason})`;
            throw new Error(reason);
        }
        const blob = await response.blob();
        const nextUrl = URL.createObjectURL(blob);
        await new Promise((resolve, reject) => {
            const tmp = new Image();
            tmp.onload = () => {
                const oldUrl = img.src;
                img.src = nextUrl;
                img.style.visibility = 'visible';
                placeholder.style.visibility = 'hidden';
                if (oldUrl && oldUrl.startsWith('blob:')) URL.revokeObjectURL(oldUrl);
                resolve();
            };
            tmp.onerror = () => {
                URL.revokeObjectURL(nextUrl);
                reject(new Error('image decode failed'));
            };
            tmp.src = nextUrl;
        });
    } catch (error) {
        if (!img.src || !img.src.startsWith('blob:')) {
            img.style.visibility = 'hidden';
            placeholder.textContent = `截图获取失败: ${error.message}`;
            placeholder.style.visibility = 'visible';
        }
    } finally {
        if (state) {
            state.screenshotInFlight = false;
        }
    }
}

function controlErrorDetail(response) {
    const detail = response?.data?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail.trim();
    return `HTTP ${response?.status || 0}`;
}

function isSwipeTransportUncertain(response, action) {
    if (action !== 'swipe') return false;
    if (Number(response?.status || 0) !== 502) return false;
    const detail = String(response?.data?.detail || '').trim().toLowerCase();
    return detail.includes('swipe failed')
        || detail.includes('did not acknowledge')
        || detail.includes('transport');
}

async function postUnitControl(unit, action, payload, successMessage, getTraceContext, refs, state) {
    if (!unit || unit.availability_state !== 'available') {
        toast.error('设备离线，无法控制');
        return false;
    }
    if (state.busy) return false;
    setSurfaceControlBusy(refs, state, true);
    try {
        const traceContext = typeof getTraceContext === 'function' ? getTraceContext() : null;
        if (traceContext) {
            const takeoverOk = await ensureHumanTakeover(traceContext);
            if (!takeoverOk) {
                toast.error('人工接管初始化失败');
                return false;
            }
        }
        const requestPayload = traceContext
            ? {
                ...payload,
                trace_context: {
                    task_id: traceContext.taskId,
                    run_id: traceContext.runId,
                    target_label: traceContext.targetLabel,
                    attempt_number: Number(traceContext.attemptNumber || 1),
                    current_declarative_stage: traceContext.currentDeclarativeStage || undefined,
                },
            }
            : payload;
        const response = await fetchJson(`/api/devices/${unit.parent_id}/${unit.cloud_id}/${action}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestPayload),
        });
        if (!response.ok) {
            if (isSwipeTransportUncertain(response, action)) {
                toast.info('滑动已下发，后端未确认回执，已按效果不确定处理');
                await loadUnitScreenshotIntoSurfaceWithState(unit, refs, state, { force: true });
                return true;
            }
            toast.error(`控制失败: ${controlErrorDetail(response)}`);
            return false;
        }
        if (successMessage) {
            toast.success(successMessage);
        }
        await loadUnitScreenshotIntoSurfaceWithState(unit, refs, state, { force: true });
        return true;
    } finally {
        setSurfaceControlBusy(refs, state, false);
    }
}

async function handleScreenshotTap(event, unit, getTraceContext, refs, state) {
    const { img } = refs;
    if (!img || !unit || !img.src || img.style.visibility === 'hidden') return;
    const rect = img.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;
    const rx = Math.min(Math.max(event.clientX - rect.left, 0), rect.width);
    const ry = Math.min(Math.max(event.clientY - rect.top, 0), rect.height);
    const nx = Math.round((rx / rect.width) * 1000);
    const ny = Math.round((ry / rect.height) * 1000);
    await postUnitControl(unit, 'tap', { nx, ny }, `已点击 (${nx}, ${ny})`, getTraceContext, refs, state);
}

async function handleUnitTextSend(unit, getTraceContext, refs, state) {
    const input = refs.textInput;
    if (!input) return;
    const text = typeof input.value === 'string' ? input.value : '';
    if (!text.trim()) {
        toast.error('请输入要发送的文本');
        input.focus();
        return;
    }
    if (/[\r\n]/.test(text)) {
        toast.error('轻控制仅支持单行文本');
        input.focus();
        return;
    }
    const traceContext = typeof getTraceContext === 'function' ? getTraceContext() : null;
    const ok = await postUnitControl(unit, 'text', { text }, '已发送文本', getTraceContext, refs, state);
    if (ok) {
        input.value = '';
        if (traceContext?.taskId) {
            void promptAiTaskInputAnnotation({
                taskId: traceContext.taskId,
                rawValue: text.trim(),
            });
        }
    }
}

function bindUnitControls(unit, getTraceContext, refs, state) {
    const keyActions = {
        keyBack: { action: 'key', payload: { key: 'back' }, message: '已发送返回' },
        keyHome: { action: 'key', payload: { key: 'home' }, message: '已发送 Home' },
        keyEnter: { action: 'key', payload: { key: 'enter' }, message: '已发送 Enter' },
        keyDelete: { action: 'key', payload: { key: 'delete' }, message: '已发送退格键' },
        swipeUp: {
            action: 'swipe',
            payload: { nx0: 500, ny0: 820, nx1: 500, ny1: 220, duration: 350 },
            message: '已上滑',
        },
        swipeDown: {
            action: 'swipe',
            payload: { nx0: 500, ny0: 220, nx1: 500, ny1: 820, duration: 350 },
            message: '已下滑',
        },
        swipeLeft: {
            action: 'swipe',
            payload: { nx0: 820, ny0: 500, nx1: 220, ny1: 500, duration: 350 },
            message: '已左滑',
        },
        swipeRight: {
            action: 'swipe',
            payload: { nx0: 220, ny0: 500, nx1: 820, ny1: 500, duration: 350 },
            message: '已右滑',
        },
    };

    if (refs.refreshBtn) {
        refs.refreshBtn.onclick = () => {
            void loadUnitScreenshotIntoSurfaceWithState(unit, refs, state, { force: true });
        };
    }
    if (refs.img) {
        refs.img.onclick = (event) => {
            void handleScreenshotTap(event, unit, getTraceContext, refs, state);
        };
    }

    Object.entries(keyActions).forEach(([key, config]) => {
        const button = refs[key];
        if (!button) return;
        button.onclick = () => {
            void postUnitControl(unit, config.action, config.payload, config.message, getTraceContext, refs, state);
        };
    });

    const textInput = refs.textInput;
    if (textInput) {
        textInput.onkeydown = (event) => {
            if (event.key !== 'Enter') return;
            event.preventDefault();
            void handleUnitTextSend(unit, getTraceContext, refs, state);
        };
    }

    const sendTextBtn = refs.sendTextBtn;
    if (sendTextBtn) {
        sendTextBtn.onclick = () => {
            void handleUnitTextSend(unit, getTraceContext, refs, state);
        };
    }
}

function clearSurfaceTimer(state) {
    if (state.timer) {
        clearInterval(state.timer);
        state.timer = null;
    }
}

export function mountUnitControlSurface({ unit, getTraceContext = null, ids = {}, refreshIntervalMs = 0 }) {
    const refs = buildSurfaceRefs(ids);
    const state = { busy: false, timer: null, screenshotInFlight: false, visibilityHandler: null };
    bindUnitControls(unit, getTraceContext, refs, state);
    void loadUnitScreenshotIntoSurfaceWithState(unit, refs, state, { force: true });
    if (typeof document !== 'undefined' && typeof document.addEventListener === 'function') {
        state.visibilityHandler = () => {
            if (document.visibilityState === 'visible') {
                void loadUnitScreenshotIntoSurfaceWithState(unit, refs, state, { force: true });
            }
        };
        document.addEventListener('visibilitychange', state.visibilityHandler);
    }
    if (refreshIntervalMs > 0) {
        state.timer = setInterval(() => {
            void loadUnitScreenshotIntoSurfaceWithState(unit, refs, state);
        }, refreshIntervalMs);
    }
    return () => {
        clearSurfaceTimer(state);
        if (
            state.visibilityHandler
            && typeof document !== 'undefined'
            && typeof document.removeEventListener === 'function'
        ) {
            document.removeEventListener('visibilitychange', state.visibilityHandler);
        }
        state.visibilityHandler = null;
        setSurfaceControlBusy(refs, state, false);
        if (refs.refreshBtn) refs.refreshBtn.onclick = null;
        if (refs.img) refs.img.onclick = null;
        if (refs.textInput) refs.textInput.onkeydown = null;
        if (refs.sendTextBtn) refs.sendTextBtn.onclick = null;
        [refs.keyBack, refs.keyHome, refs.keyEnter, refs.keyDelete, refs.swipeUp, refs.swipeLeft, refs.swipeDown, refs.swipeRight]
            .forEach((button) => {
                if (button) button.onclick = null;
            });
        revokeSurfaceImage(refs.img);
        if (refs.img) {
            refs.img.src = '';
            refs.img.style.visibility = 'hidden';
        }
        if (refs.placeholder) {
            refs.placeholder.textContent = '正在加载截图...';
            refs.placeholder.style.visibility = 'visible';
        }
    };
}

export function openUnitDetail({
    unit,
    clearElement,
    buildUnitLogTarget,
    renderUnitPluginFields,
    loadUnitAccounts,
    submitUnitTask,
    setCurrentUnit,
}) {
    document.querySelectorAll('.tab-pane').forEach((panel) => panel.classList.remove('active'));
    const view = $('unitDetailView');
    if (view) view.style.display = 'flex';
    const title = $('detailUnitTitle');
    if (title) title.textContent = `云机 #${unit.parent_id}-${unit.cloud_id}`;
    setCurrentUnit?.(unit);
    document.body.dataset.currentDeviceId = String(unit.parent_id);
    document.body.dataset.currentCloudId = String(unit.cloud_id);
    const logBox = $('unitLogBox');
    clearElement(logBox);
    store.setState({ currentUnitLogTarget: buildUnitLogTarget(unit) });
    renderUnitPluginFields();
    const submitButton = $('submitSingleTask');
    if (submitButton) submitButton.onclick = () => {
        void submitUnitTask(unit);
    };
    detailUnitControlCleanup?.();
    detailUnitControlCleanup = mountUnitControlSurface({
        unit,
        getTraceContext: () => traceContextForUnit(unit),
        ids: {
            root: 'unitDetailView',
            refreshBtn: 'refreshScreenshot',
            img: 'unitScreenshotImg',
            placeholder: 'unitScreenshotPlaceholder',
            textInput: 'unitTextInput',
            sendTextBtn: 'unitSendText',
            keyBack: 'unitKeyBack',
            keyHome: 'unitKeyHome',
            keyEnter: 'unitKeyEnter',
            keyDelete: 'unitKeyDelete',
            swipeUp: 'unitSwipeUp',
            swipeLeft: 'unitSwipeLeft',
            swipeDown: 'unitSwipeDown',
            swipeRight: 'unitSwipeRight',
        },
        refreshIntervalMs: 1000,
    });
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

export function closeUnitDetail({
    restoreMainTab = true,
    closeUnitAiDialog,
    loadDevices,
    setCurrentUnit,
}) {
    const view = $('unitDetailView');
    if (view) view.style.display = 'none';
    closeUnitAiDialog?.();
    setUnitTakeoverTraceContext(null);
    setCurrentUnit?.(null);
    detailUnitControlCleanup?.();
    detailUnitControlCleanup = null;
    document.body.dataset.currentDeviceId = '';
    document.body.dataset.currentCloudId = '';
    if (restoreMainTab) {
        const tabMain = $('tab-main');
        if (tabMain) tabMain.classList.add('active');
        void loadDevices?.();
    }
    store.setState({ currentUnitLogTarget: '' });
}
