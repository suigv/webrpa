import { fetchJson } from '../utils/api.js';
import { store } from '../state/store.js';
import { toast } from '../ui/toast.js';
import { loadDevices } from './devices.js';

// DOM Elements
const hostIp = document.getElementById("hostIp");
const totalDevices = document.getElementById("totalDevices");
const deviceIps = document.getElementById("deviceIps");
const configMsg = document.getElementById("configMsg");
const saveBtn = document.getElementById("saveConfig");

// Humanized Elements
const hzPreset = document.getElementById("hzPreset");
const applyHzPreset = document.getElementById("applyHzPreset");
const hzEnabled = document.getElementById("hzEnabled");
const hzTypoProbability = document.getElementById("hzTypoProbability");
const hzTypingDelayMin = document.getElementById("hzTypingDelayMin");
const hzTypingDelayMax = document.getElementById("hzTypingDelayMax");
const hzTypoDelayMin = document.getElementById("hzTypoDelayMin");
const hzTypoDelayMax = document.getElementById("hzTypoDelayMax");
const hzBackspaceDelayMin = document.getElementById("hzBackspaceDelayMin");
const hzBackspaceDelayMax = document.getElementById("hzBackspaceDelayMax");
const hzClickOffsetXMin = document.getElementById("hzClickOffsetXMin");
const hzClickOffsetXMax = document.getElementById("hzClickOffsetXMax");
const hzClickOffsetYMin = document.getElementById("hzClickOffsetYMin");
const hzClickOffsetYMax = document.getElementById("hzClickOffsetYMax");
const hzMoveDurationMin = document.getElementById("hzMoveDurationMin");
const hzMoveDurationMax = document.getElementById("hzMoveDurationMax");
const hzMoveStepsMin = document.getElementById("hzMoveStepsMin");
const hzMoveStepsMax = document.getElementById("hzMoveStepsMax");
const hzRandomSeed = document.getElementById("hzRandomSeed");

const hzInputs = [
  hzEnabled, hzTypoProbability, hzTypingDelayMin, hzTypingDelayMax,
  hzTypoDelayMin, hzTypoDelayMax, hzBackspaceDelayMin, hzBackspaceDelayMax,
  hzClickOffsetXMin, hzClickOffsetXMax, hzClickOffsetYMin, hzClickOffsetYMax,
  hzMoveDurationMin, hzMoveDurationMax, hzMoveStepsMin, hzMoveStepsMax, hzRandomSeed
];

const HZ_PRESETS = {
  low: {
    typo_probability: 0.01, typing_delay_min: 0.02, typing_delay_max: 0.08,
    typo_delay_min: 0.02, typo_delay_max: 0.06, backspace_delay_min: 0.01,
    backspace_delay_max: 0.03, click_offset_x_min: -2, click_offset_x_max: 2,
    click_offset_y_min: -2, click_offset_y_max: 2, move_duration_min: 0.10,
    move_duration_max: 0.30, move_steps_min: 4, move_steps_max: 12,
  },
  medium: {
    typo_probability: 0.03, typing_delay_min: 0.04, typing_delay_max: 0.18,
    typo_delay_min: 0.04, typo_delay_max: 0.12, backspace_delay_min: 0.02,
    backspace_delay_max: 0.08, click_offset_x_min: -4, click_offset_x_max: 4,
    click_offset_y_min: -4, click_offset_y_max: 4, move_duration_min: 0.20,
    move_duration_max: 0.70, move_steps_min: 8, move_steps_max: 24,
  },
  high: {
    typo_probability: 0.08, typing_delay_min: 0.06, typing_delay_max: 0.28,
    typo_delay_min: 0.06, typo_delay_max: 0.20, backspace_delay_min: 0.03,
    backspace_delay_max: 0.12, click_offset_x_min: -8, click_offset_x_max: 8,
    click_offset_y_min: -8, click_offset_y_max: 8, move_duration_min: 0.30,
    move_duration_max: 1.00, move_steps_min: 12, move_steps_max: 36,
  },
};

const HZ_PRESET_KEYS = Object.keys(HZ_PRESETS.medium);

export function initConfig() {
    if (saveBtn) saveBtn.addEventListener("click", saveConfig);
    
    if (applyHzPreset) {
        applyHzPreset.addEventListener("click", () => {
            if (hzPreset.value === "custom") {
                refreshHumanizedPreview();
                return;
            }
            applyHumanizedPreset(hzPreset.value);
        });
    }

    if (hzPreset) {
        hzPreset.addEventListener("change", () => {
            if (hzPreset.value !== "custom") {
                applyHumanizedPreset(hzPreset.value);
            }
        });
    }

    hzInputs.forEach(input => {
        if(input) {
            input.addEventListener("input", refreshHumanizedPreview);
            input.addEventListener("change", refreshHumanizedPreview);
        }
    });

    loadConfig();
}

export async function loadConfig() {
    const r = await fetchJson("/api/config/");
    if (!r.ok) {
        toast.error("加载配置失败");
        return;
    }
    
    const data = r.data;
    if (hostIp) hostIp.value = data.host_ip || "";
    if (totalDevices) totalDevices.value = data.total_devices || 1;
    if (deviceIps) {
        const lines = Object.entries(data.device_ips || {}).map(([deviceId, ip]) => `${deviceId} ${ip}`);
        deviceIps.value = lines.join("\n");
    }
    
    setHumanizedForm(data.humanized || {});
    store.setState({ config: data });
}

export async function saveConfig() {
    if(saveBtn) {
        saveBtn.disabled = true;
        saveBtn.textContent = "保存中...";
    }

    let parsedDeviceIps = {};
    let parsedHumanized = {};
    const currentConfig = store.getState().config || {};
    
    try {
        parsedDeviceIps = parseDeviceIpsText(deviceIps.value || "");
    } catch (error) {
        const msg = String(error?.message || "设备 IP 格式无效");
        toast.error(msg);
        if (configMsg) configMsg.textContent = msg;
        resetSaveBtn();
        return;
    }

    parsedHumanized = buildHumanizedFromForm();
    const humanizedError = validateHumanizedForm(parsedHumanized);
    if (humanizedError) {
        toast.error(humanizedError);
        if (configMsg) configMsg.textContent = humanizedError;
        resetSaveBtn();
        return;
    }

    const normalizedHostIp = (hostIp?.value || "").trim() || String(currentConfig.host_ip || "").trim();
    if (!normalizedHostIp) {
        const msg = "主机 IP 不能为空";
        toast.error(msg);
        if (configMsg) configMsg.textContent = msg;
        resetSaveBtn();
        return;
    }

    const body = {
        host_ip: normalizedHostIp,
        total_devices: Number(totalDevices.value || 1),
        device_ips: parsedDeviceIps,
        humanized: parsedHumanized,
    };

    const r = await fetchJson("/api/config/", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });

    if (r.ok) {
        toast.success("配置已保存");
        if (configMsg) configMsg.textContent = "配置已保存";
        await loadDevices(); // Refresh devices as config might affect them
    } else {
        const detail = (r.data && (r.data.detail || r.data.message)) ? ` - ${r.data.detail || r.data.message}` : "";
        const msg = `保存失败: ${r.status}${detail}`;
        toast.error(msg);
        if (configMsg) configMsg.textContent = msg;
    }
    resetSaveBtn();
}

function resetSaveBtn() {
    if(saveBtn) {
        saveBtn.disabled = false;
        saveBtn.textContent = "保存";
    }
}

// --- Humanized Logic ---

function numbersClose(a, b) {
    return Math.abs(Number(a) - Number(b)) < 1e-6;
}

function detectHumanizedPreset(cfg) {
    for (const presetName of ["low", "medium", "high"]) {
        const preset = HZ_PRESETS[presetName];
        const matches = HZ_PRESET_KEYS.every((key) => numbersClose(cfg[key], preset[key]));
        if (matches) return presetName;
    }
    return "custom";
}

function refreshHumanizedPreview() {
    const cfg = buildHumanizedFromForm();
    if(hzPreset) hzPreset.value = detectHumanizedPreset(cfg);
}

function parseDeviceIpsText(text) {
    const result = {};
    const lines = String(text || "").split(/\r?\n/);
    for (const lineRaw of lines) {
        const line = lineRaw.trim();
        if (!line) continue;
        const parts = line.split(/\s+/);
        if (parts.length < 2) {
            throw new Error(`设备 IP 格式错误: ${line}`);
        }
        const deviceId = String(parts[0]).trim();
        const ip = String(parts[1]).trim();
        result[deviceId] = ip;
    }
    return result;
}

function applyHumanizedPreset(presetName) {
    const preset = HZ_PRESETS[presetName];
    if (!preset) return;
    
    setHumanizedForm(preset); // Only sets values, doesn't set seed or enabled usually?
    // Preset doesn't contain 'enabled' or 'random_seed', so we keep them as is or pass defaults?
    // setHumanizedForm handles merging if we pass full object, but here we pass partial.
    // Actually setHumanizedForm implementation below expects full object or defaults.
    // Let's manually set fields from preset.
    
    if(hzTypoProbability) hzTypoProbability.value = preset.typo_probability;
    if(hzTypingDelayMin) hzTypingDelayMin.value = preset.typing_delay_min;
    if(hzTypingDelayMax) hzTypingDelayMax.value = preset.typing_delay_max;
    if(hzTypoDelayMin) hzTypoDelayMin.value = preset.typo_delay_min;
    if(hzTypoDelayMax) hzTypoDelayMax.value = preset.typo_delay_max;
    if(hzBackspaceDelayMin) hzBackspaceDelayMin.value = preset.backspace_delay_min;
    if(hzBackspaceDelayMax) hzBackspaceDelayMax.value = preset.backspace_delay_max;
    if(hzClickOffsetXMin) hzClickOffsetXMin.value = preset.click_offset_x_min;
    if(hzClickOffsetXMax) hzClickOffsetXMax.value = preset.click_offset_x_max;
    if(hzClickOffsetYMin) hzClickOffsetYMin.value = preset.click_offset_y_min;
    if(hzClickOffsetYMax) hzClickOffsetYMax.value = preset.click_offset_y_max;
    if(hzMoveDurationMin) hzMoveDurationMin.value = preset.move_duration_min;
    if(hzMoveDurationMax) hzMoveDurationMax.value = preset.move_duration_max;
    if(hzMoveStepsMin) hzMoveStepsMin.value = preset.move_steps_min;
    if(hzMoveStepsMax) hzMoveStepsMax.value = preset.move_steps_max;
    
    if(hzPreset) hzPreset.value = presetName;
    refreshHumanizedPreview();
}

function setHumanizedForm(data) {
    if(hzEnabled) hzEnabled.checked = Boolean(data.enabled);
    if(hzTypoProbability) hzTypoProbability.value = Number(data.typo_probability ?? 0.03);
    if(hzTypingDelayMin) hzTypingDelayMin.value = Number(data.typing_delay_min ?? 0.04);
    if(hzTypingDelayMax) hzTypingDelayMax.value = Number(data.typing_delay_max ?? 0.18);
    if(hzTypoDelayMin) hzTypoDelayMin.value = Number(data.typo_delay_min ?? 0.04);
    if(hzTypoDelayMax) hzTypoDelayMax.value = Number(data.typo_delay_max ?? 0.12);
    if(hzBackspaceDelayMin) hzBackspaceDelayMin.value = Number(data.backspace_delay_min ?? 0.02);
    if(hzBackspaceDelayMax) hzBackspaceDelayMax.value = Number(data.backspace_delay_max ?? 0.08);
    if(hzClickOffsetXMin) hzClickOffsetXMin.value = Number(data.click_offset_x_min ?? -4);
    if(hzClickOffsetXMax) hzClickOffsetXMax.value = Number(data.click_offset_x_max ?? 4);
    if(hzClickOffsetYMin) hzClickOffsetYMin.value = Number(data.click_offset_y_min ?? -4);
    if(hzClickOffsetYMax) hzClickOffsetYMax.value = Number(data.click_offset_y_max ?? 4);
    if(hzMoveDurationMin) hzMoveDurationMin.value = Number(data.move_duration_min ?? 0.2);
    if(hzMoveDurationMax) hzMoveDurationMax.value = Number(data.move_duration_max ?? 0.7);
    if(hzMoveStepsMin) hzMoveStepsMin.value = Number(data.move_steps_min ?? 8);
    if(hzMoveStepsMax) hzMoveStepsMax.value = Number(data.move_steps_max ?? 24);
    if(hzRandomSeed) hzRandomSeed.value = data.random_seed === null || data.random_seed === undefined ? "" : String(data.random_seed);
    
    refreshHumanizedPreview();
}

function buildHumanizedFromForm() {
    const seedText = (hzRandomSeed ? hzRandomSeed.value : "").trim();
    return {
        enabled: Boolean(hzEnabled ? hzEnabled.checked : false),
        typo_probability: Number(hzTypoProbability.value || 0),
        typing_delay_min: Number(hzTypingDelayMin.value || 0),
        typing_delay_max: Number(hzTypingDelayMax.value || 0),
        typo_delay_min: Number(hzTypoDelayMin.value || 0),
        typo_delay_max: Number(hzTypoDelayMax.value || 0),
        backspace_delay_min: Number(hzBackspaceDelayMin.value || 0),
        backspace_delay_max: Number(hzBackspaceDelayMax.value || 0),
        click_offset_x_min: Number(hzClickOffsetXMin.value || 0),
        click_offset_x_max: Number(hzClickOffsetXMax.value || 0),
        click_offset_y_min: Number(hzClickOffsetYMin.value || 0),
        click_offset_y_max: Number(hzClickOffsetYMax.value || 0),
        move_duration_min: Number(hzMoveDurationMin.value || 0),
        move_duration_max: Number(hzMoveDurationMax.value || 0),
        move_steps_min: Number(hzMoveStepsMin.value || 1),
        move_steps_max: Number(hzMoveStepsMax.value || 1),
        random_seed: seedText === "" ? null : Number(seedText),
    };
}

function validateHumanizedForm(cfg) {
    if (!(cfg.typo_probability >= 0 && cfg.typo_probability <= 1)) {
        return "拼写错误概率必须在 0 到 1 之间";
    }
    const pairs = [
        ["输入延迟", cfg.typing_delay_min, cfg.typing_delay_max],
        ["错误输入延迟", cfg.typo_delay_min, cfg.typo_delay_max],
        ["退格延迟", cfg.backspace_delay_min, cfg.backspace_delay_max],
        ["点击X偏移", cfg.click_offset_x_min, cfg.click_offset_x_max],
        ["点击Y偏移", cfg.click_offset_y_min, cfg.click_offset_y_max],
        ["移动时长", cfg.move_duration_min, cfg.move_duration_max],
        ["移动步数", cfg.move_steps_min, cfg.move_steps_max],
    ];
    for (const [name, minV, maxV] of pairs) {
        if (minV > maxV) {
            return `${name}: 最小值必须 <= 最大值`;
        }
    }
    return "";
}
