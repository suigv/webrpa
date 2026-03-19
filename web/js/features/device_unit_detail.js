import { authFetch, fetchJson } from '../utils/api.js';
import { toast } from '../ui/toast.js';
import { store } from '../state/store.js';

const $ = (id) => document.getElementById(id);

let currentUnitScreenshotTimer = null;
let unitControlInFlight = false;

async function loadUnitScreenshot(unit) {
    const img = $('unitScreenshotImg');
    const placeholder = $('unitScreenshotPlaceholder');
    if (!img || !placeholder) return;
    if (unit.availability_state !== 'available') {
        img.style.visibility = 'hidden';
        placeholder.textContent = '设备离线，无法获取截图';
        placeholder.style.visibility = 'visible';
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
    }
}

function unitControlButtons() {
    return Array.from(document.querySelectorAll('[data-unit-control]'));
}

function setUnitControlBusy(busy) {
    unitControlInFlight = busy;
    unitControlButtons().forEach((button) => {
        button.disabled = busy;
    });
    const img = $('unitScreenshotImg');
    if (img) {
        img.style.cursor = busy ? 'wait' : 'crosshair';
    }
}

function controlErrorDetail(response) {
    const detail = response?.data?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail.trim();
    return `HTTP ${response?.status || 0}`;
}

async function postUnitControl(unit, action, payload, successMessage = '') {
    if (!unit || unit.availability_state !== 'available') {
        toast.error('设备离线，无法控制');
        return false;
    }
    if (unitControlInFlight) return false;
    setUnitControlBusy(true);
    try {
        const response = await fetchJson(`/api/devices/${unit.parent_id}/${unit.cloud_id}/${action}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!response.ok) {
            toast.error(`控制失败: ${controlErrorDetail(response)}`);
            return false;
        }
        if (successMessage) {
            toast.success(successMessage);
        }
        await loadUnitScreenshot(unit);
        return true;
    } finally {
        setUnitControlBusy(false);
    }
}

async function handleScreenshotTap(event, unit) {
    const img = $('unitScreenshotImg');
    if (!img || !unit || !img.src || img.style.visibility === 'hidden') return;
    const rect = img.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;
    const rx = Math.min(Math.max(event.clientX - rect.left, 0), rect.width);
    const ry = Math.min(Math.max(event.clientY - rect.top, 0), rect.height);
    const nx = Math.round((rx / rect.width) * 1000);
    const ny = Math.round((ry / rect.height) * 1000);
    await postUnitControl(unit, 'tap', { nx, ny }, `已点击 (${nx}, ${ny})`);
}

async function handleUnitTextSend(unit) {
    const input = $('unitTextInput');
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
    const ok = await postUnitControl(unit, 'text', { text }, '已发送文本');
    if (ok) {
        input.value = '';
    }
}

function bindUnitControls(unit) {
    const refreshBtn = $('refreshScreenshot');
    if (refreshBtn) refreshBtn.onclick = () => {
        void loadUnitScreenshot(unit);
    };

    const img = $('unitScreenshotImg');
    if (img) {
        img.onclick = (event) => {
            void handleScreenshotTap(event, unit);
        };
    }

    const keyActions = {
        unitKeyBack: { action: 'key', payload: { key: 'back' }, message: '已发送返回' },
        unitKeyHome: { action: 'key', payload: { key: 'home' }, message: '已发送 Home' },
        unitKeyEnter: { action: 'key', payload: { key: 'enter' }, message: '已发送 Enter' },
        unitKeyDelete: { action: 'key', payload: { key: 'delete' }, message: '已发送退格键' },
        unitSwipeUp: {
            action: 'swipe',
            payload: { nx0: 500, ny0: 820, nx1: 500, ny1: 220, duration: 350 },
            message: '已上滑',
        },
        unitSwipeDown: {
            action: 'swipe',
            payload: { nx0: 500, ny0: 220, nx1: 500, ny1: 820, duration: 350 },
            message: '已下滑',
        },
        unitSwipeLeft: {
            action: 'swipe',
            payload: { nx0: 820, ny0: 500, nx1: 220, ny1: 500, duration: 350 },
            message: '已左滑',
        },
        unitSwipeRight: {
            action: 'swipe',
            payload: { nx0: 220, ny0: 500, nx1: 820, ny1: 500, duration: 350 },
            message: '已右滑',
        },
    };

    Object.entries(keyActions).forEach(([id, config]) => {
        const button = $(id);
        if (!button) return;
        button.onclick = () => {
            void postUnitControl(unit, config.action, config.payload, config.message);
        };
    });

    const textInput = $('unitTextInput');
    if (textInput) {
        textInput.onkeydown = (event) => {
            if (event.key !== 'Enter') return;
            event.preventDefault();
            void handleUnitTextSend(unit);
        };
    }

    const sendTextBtn = $('unitSendText');
    if (sendTextBtn) {
        sendTextBtn.onclick = () => {
            void handleUnitTextSend(unit);
        };
    }
}

function clearScreenshotTimer() {
    if (currentUnitScreenshotTimer) {
        clearInterval(currentUnitScreenshotTimer);
        currentUnitScreenshotTimer = null;
    }
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
    void loadUnitAccounts();
    const submitButton = $('submitSingleTask');
    if (submitButton) submitButton.onclick = () => {
        void submitUnitTask(unit);
    };
    bindUnitControls(unit);
    void loadUnitScreenshot(unit);
    clearScreenshotTimer();
    currentUnitScreenshotTimer = setInterval(() => {
        const sameDevice = document.body.dataset.currentDeviceId === String(unit.parent_id);
        const sameCloud = document.body.dataset.currentCloudId === String(unit.cloud_id);
        if (!sameDevice || !sameCloud) {
            clearScreenshotTimer();
            return;
        }
        void loadUnitScreenshot(unit);
    }, 1000);
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
    setCurrentUnit?.(null);
    clearScreenshotTimer();
    document.body.dataset.currentDeviceId = '';
    document.body.dataset.currentCloudId = '';
    setUnitControlBusy(false);
    const img = $('unitScreenshotImg');
    if (img && img.src && img.src.startsWith('blob:')) {
        URL.revokeObjectURL(img.src);
        img.src = '';
        img.style.visibility = 'hidden';
    }
    if (restoreMainTab) {
        const tabMain = $('tab-main');
        if (tabMain) tabMain.classList.add('active');
        void loadDevices?.();
    }
    store.setState({ currentUnitLogTarget: '' });
}
