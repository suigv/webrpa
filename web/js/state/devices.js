import { fetchJson } from '../utils/api.js';
import { store } from './store.js';

const DEFAULT_POLL_INTERVAL_MS = 5000;

let devicesRequest = null;
let pollTimer = null;
let pollIntervalMs = DEFAULT_POLL_INTERVAL_MS;
const pollConsumers = new Set();
let fetchDevicesImpl = (options = {}) => fetchJson('/api/devices/', options);

function normalizeDevices(data) {
    return Array.isArray(data) ? data : [];
}

function currentState() {
    return store.getState();
}

function currentFetchedAt() {
    return Number(currentState().devicesFetchedAt || 0);
}

export function getDevicesSnapshot() {
    return normalizeDevices(currentState().devicesSnapshot);
}

function setDevicesSnapshot(devices) {
    store.setState({
        devicesSnapshot: normalizeDevices(devices),
        devicesFetchedAt: Date.now(),
    });
}

function clearPollTimer() {
    if (pollTimer) {
        clearTimeout(pollTimer);
        pollTimer = null;
    }
}

function pollShouldPause() {
    return typeof document !== 'undefined' && document.visibilityState === 'hidden';
}

async function pollOnce() {
    if (pollConsumers.size === 0) {
        clearPollTimer();
        return;
    }
    pollTimer = setTimeout(pollOnce, pollIntervalMs);
    if (pollShouldPause()) {
        return;
    }
    await refreshDevicesSnapshot({
        silentErrors: true,
        maxAgeMs: Math.max(250, pollIntervalMs - 250),
    });
}

function ensurePollingLoop() {
    if (pollTimer || pollConsumers.size === 0) {
        return;
    }
    pollTimer = setTimeout(pollOnce, pollIntervalMs);
}

export async function refreshDevicesSnapshot({
    force = false,
    silentErrors = false,
    maxAgeMs = 0,
} = {}) {
    const fetchedAt = currentFetchedAt();
    if (!force && fetchedAt > 0 && maxAgeMs > 0 && Date.now() - fetchedAt <= maxAgeMs) {
        return {
            ok: true,
            data: getDevicesSnapshot(),
            cached: true,
        };
    }

    if (devicesRequest) {
        return devicesRequest;
    }

    devicesRequest = (async () => {
        try {
            const response = await fetchDevicesImpl({ silentErrors });
            if (response?.ok) {
                const devices = normalizeDevices(response.data);
                setDevicesSnapshot(devices);
                return {
                    ok: true,
                    data: devices,
                    cached: false,
                };
            }
            return {
                ok: false,
                status: Number(response?.status || 0),
                data: response?.data ?? null,
                cached: false,
            };
        } finally {
            devicesRequest = null;
        }
    })();

    return devicesRequest;
}

export function subscribeDevices(listener, { emitCurrent = true } = {}) {
    if (typeof listener !== 'function') {
        return () => {};
    }
    let lastFetchedAt = currentFetchedAt();
    let lastDevices = currentState().devicesSnapshot;
    if (emitCurrent) {
        listener(getDevicesSnapshot(), { fetchedAt: lastFetchedAt });
    }
    return store.subscribe((state) => {
        if (state.devicesFetchedAt === lastFetchedAt && state.devicesSnapshot === lastDevices) {
            return;
        }
        lastFetchedAt = Number(state.devicesFetchedAt || 0);
        lastDevices = state.devicesSnapshot;
        listener(getDevicesSnapshot(), { fetchedAt: lastFetchedAt });
    });
}

export function startDevicesPolling(consumerId = 'default', { immediate = true } = {}) {
    const key = String(consumerId || 'default').trim() || 'default';
    pollConsumers.add(key);
    ensurePollingLoop();
    if (immediate) {
        void refreshDevicesSnapshot({ force: true, silentErrors: true });
    }
}

export function stopDevicesPolling(consumerId = 'default') {
    const key = String(consumerId || 'default').trim() || 'default';
    pollConsumers.delete(key);
    if (pollConsumers.size === 0) {
        clearPollTimer();
    }
}

export function findUnitInDevices(deviceId, cloudId, devices = getDevicesSnapshot()) {
    const wantedDeviceId = Number(deviceId || 0);
    const wantedCloudId = Number(cloudId || 0);
    if (!wantedDeviceId || !wantedCloudId) {
        return null;
    }
    for (const device of normalizeDevices(devices)) {
        if (Number(device?.device_id || 0) !== wantedDeviceId) {
            continue;
        }
        const unit = Array.isArray(device?.cloud_machines)
            ? device.cloud_machines.find((item) => Number(item?.cloud_id || 0) === wantedCloudId)
            : null;
        if (unit) {
            return {
                ...unit,
                parent_ip: device.ip,
                parent_id: device.device_id,
            };
        }
    }
    return null;
}

export function __setDevicesFetchImplForTests(fn) {
    fetchDevicesImpl = typeof fn === 'function' ? fn : ((options = {}) => fetchJson('/api/devices/', options));
}

export function __resetDevicesStateForTests() {
    clearPollTimer();
    pollConsumers.clear();
    pollIntervalMs = DEFAULT_POLL_INTERVAL_MS;
    devicesRequest = null;
    fetchDevicesImpl = (options = {}) => fetchJson('/api/devices/', options);
    store.setState({
        devicesSnapshot: [],
        devicesFetchedAt: 0,
    });
}
