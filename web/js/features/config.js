import { fetchJson } from '/static/js/utils/api.js';
import { toast } from '/static/js/ui/toast.js';

const saveBtn = document.getElementById("saveConfig");

// 网络配置
const cfgHostIp = document.getElementById("cfgHostIp");
const cfgSdkPort = document.getElementById("cfgSdkPort");
const cfgCloudPerDevice = document.getElementById("cfgCloudPerDevice");
const discoveryEnabled = document.getElementById("discoveryEnabled");
const discoverySubnet = document.getElementById("discoverySubnet");

// 业务文本
const txtLocation = document.getElementById("txtLocation");
const txtWebsite = document.getElementById("txtWebsite");

// 拟人化引擎 (原有)
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
const hzWordPauseProbability = document.getElementById("hzWordPauseProbability");
const hzWordPauseMax = document.getElementById("hzWordPauseMax");
const hzClickHoldMin = document.getElementById("hzClickHoldMin");
const hzClickHoldMax = document.getElementById("hzClickHoldMax");
const hzRandomSeed = document.getElementById("hzRandomSeed");

const hzInputs = [
  hzEnabled, hzTypoProbability, hzTypingDelayMin, hzTypingDelayMax,
  hzTypoDelayMin, hzTypoDelayMax, hzBackspaceDelayMin, hzBackspaceDelayMax,
  hzClickOffsetXMin, hzClickOffsetXMax, hzClickOffsetYMin, hzClickOffsetYMax,
  hzWordPauseProbability, hzWordPauseMax, hzClickHoldMin, hzClickHoldMax,
  hzRandomSeed, discoveryEnabled, discoverySubnet,
];

const HZ_PRESETS = {
  low: {
    typo_probability: 0.01, typing_delay_min: 0.02, typing_delay_max: 0.08,
    typo_delay_min: 0.02, typo_delay_max: 0.06, backspace_delay_min: 0.01,
    backspace_delay_max: 0.03, click_offset_x_min: -2, click_offset_x_max: 2,
    click_offset_y_min: -2, click_offset_y_max: 2, word_pause_probability: 0.02,
    word_pause_max: 0.15, click_hold_min: 0.01, click_hold_max: 0.03
  },
  medium: {
    typo_probability: 0.03, typing_delay_min: 0.04, typing_delay_max: 0.18,
    typo_delay_min: 0.04, typo_delay_max: 0.12, backspace_delay_min: 0.02,
    backspace_delay_max: 0.08, click_offset_x_min: -4, click_offset_x_max: 4,
    click_offset_y_min: -4, click_offset_y_max: 4, word_pause_probability: 0.04,
    word_pause_max: 0.24, click_hold_min: 0.01, click_hold_max: 0.05
  },
  high: {
    typo_probability: 0.08, typing_delay_min: 0.06, typing_delay_max: 0.28,
    typo_delay_min: 0.06, typo_delay_max: 0.20, backspace_delay_min: 0.03,
    backspace_delay_max: 0.12, click_offset_x_min: -8, click_offset_x_max: 8,
    click_offset_y_min: -8, click_offset_y_max: 8, word_pause_probability: 0.10,
    word_pause_max: 0.50, click_hold_min: 0.02, click_hold_max: 0.10
  },
};

const HZ_PRESET_KEYS = Object.keys(HZ_PRESETS.medium);

export function initConfig() {
    if (saveBtn) saveBtn.onclick = saveConfig;

    if (applyHzPreset) {
        applyHzPreset.onclick = () => {
            if (hzPreset?.value === "custom") return;
            applyHumanizedPreset(hzPreset?.value);
        };
    }

    if (hzPreset) {
        hzPreset.onchange = () => {
            if (hzPreset.value !== "custom") {
                applyHumanizedPreset(hzPreset.value);
            }
        };
    }

    hzInputs.forEach(input => {
        if (input) {
            input.oninput = refreshHumanizedPreview;
            input.onchange = refreshHumanizedPreview;
        }
    });

    loadConfig();
    loadBusinessTexts();
}

async function loadBusinessTexts() {
    // 加载 location
    const r1 = await fetchJson("/api/data/location", { silentErrors: true });
    if (r1.ok) txtLocation.value = r1.data.data || "";
    
    // 加载 website
    const r2 = await fetchJson("/api/data/website", { silentErrors: true });
    if (r2.ok) txtWebsite.value = r2.data.data || "";
}

export async function loadConfig() {
    const r = await fetchJson("/api/config/", { silentErrors: true });
    if (!r.ok) {
        toast.error("加载配置失败");
        return;
    }

    const data = r.data;
    setFormValues(data);
}

export async function saveConfig() {
    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.textContent = "保存中...";
    }

    try {
        const parsedHumanized = buildHumanizedFromForm();
        const humanizedError = validateHumanizedForm(parsedHumanized);

        if (humanizedError) {
            toast.error(humanizedError);
            resetSaveBtn();
            return;
        }

        // 1. 保存全局配置
        const configBody = {
            host_ip: cfgHostIp.value.trim(),
            sdk_port: Number(cfgSdkPort.value),
            cloud_machines_per_device: Number(cfgCloudPerDevice.value),
            discovery_enabled: Boolean(discoveryEnabled.checked),
            discovery_subnet: discoverySubnet.value.trim(),
            humanized: parsedHumanized,
        };

        const r = await fetchJson("/api/config/", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(configBody),
            silentErrors: true,
        });

        if (!r.ok) throw new Error(`保存配置失败: ${r.status}`);

        // 2. 保存业务文本
        await fetchJson("/api/data/location", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ content: txtLocation.value }),
        });
        
        await fetchJson("/api/data/website", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ content: txtWebsite.value }),
        });

        toast.success("系统配置与业务文本已全量同步");
        await loadConfig();
    } catch (e) {
        toast.error(e.message || "同步过程中发生错误");
    } finally {
        resetSaveBtn();
    }
}

function resetSaveBtn() {
    if (saveBtn) {
        saveBtn.disabled = false;
        saveBtn.textContent = "持久化当前配置";
    }
}

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
    if (hzPreset) hzPreset.value = detectHumanizedPreset(cfg);
}

function applyHumanizedPreset(presetName) {
    const preset = HZ_PRESETS[presetName];
    if (!preset) return;

    Object.keys(preset).forEach(key => {
        const id = "hz" + key.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join('');
        const input = document.getElementById(id);
        if (input) input.value = preset[key];
    });

    if (hzPreset) hzPreset.value = presetName;
}

function setFormValues(data) {
    // 网络字段
    if (cfgHostIp) cfgHostIp.value = data.host_ip || "";
    if (cfgSdkPort) cfgSdkPort.value = data.sdk_port || 8000;
    if (cfgCloudPerDevice) cfgCloudPerDevice.value = data.cloud_machines_per_device || 12;

    // 已发现设备数（从设备列表实时读取在线云机数）
    const discoveredCount = document.getElementById("cfgDiscoveredCount");
    if (discoveredCount) {
        fetchJson('/api/devices/').then(r => {
            if (!r.ok) return;
            let available = 0;
            (r.data || []).forEach(d => {
                (d.cloud_machines || []).forEach(c => {
                    if (c.availability_state === 'available') available++;
                });
            });
            discoveredCount.textContent = available > 0 ? `${available} 台在线` : '暂无在线云机';
        });
    }

    if (discoveryEnabled) discoveryEnabled.checked = Boolean(data.discovery_enabled);
    if (discoverySubnet) discoverySubnet.value = data.discovery_subnet || "";

    // 拟人化字段
    const hz = data.humanized || {};
    if (hzEnabled) hzEnabled.checked = Boolean(hz.enabled);
    if (hzTypoProbability) hzTypoProbability.value = hz.typo_probability ?? 0.03;
    if (hzTypingDelayMin) hzTypingDelayMin.value = hz.typing_delay_min ?? 0.04;
    if (hzTypingDelayMax) hzTypingDelayMax.value = hz.typing_delay_max ?? 0.18;
    if (hzTypoDelayMin) hzTypoDelayMin.value = hz.typo_delay_min ?? 0.04;
    if (hzTypoDelayMax) hzTypoDelayMax.value = hz.typo_delay_max ?? 0.12;
    if (hzBackspaceDelayMin) hzBackspaceDelayMin.value = hz.backspace_delay_min ?? 0.02;
    if (hzBackspaceDelayMax) hzBackspaceDelayMax.value = hz.backspace_delay_max ?? 0.08;
    
    if (hzClickOffsetXMin) hzClickOffsetXMin.value = hz.click_offset_x_min ?? -4;
    if (hzClickOffsetXMax) hzClickOffsetXMax.value = hz.click_offset_x_max ?? 4;
    if (hzClickOffsetYMin) hzClickOffsetYMin.value = hz.click_offset_y_min ?? -4;
    if (hzClickOffsetYMax) hzClickOffsetYMax.value = hz.click_offset_y_max ?? 4;
    
    if (hzWordPauseProbability) hzWordPauseProbability.value = hz.word_pause_probability ?? 0.04;
    if (hzWordPauseMax) hzWordPauseMax.value = hz.word_pause_max ?? 0.24;
    if (hzClickHoldMin) hzClickHoldMin.value = hz.click_hold_min ?? 0.01;
    if (hzClickHoldMax) hzClickHoldMax.value = hz.click_hold_max ?? 0.05;
    
    if (hzRandomSeed) hzRandomSeed.value = hz.random_seed ?? "";

    refreshHumanizedPreview();
}

function numberValue(input, fallback = 0) {
    if (!input) return fallback;
    const raw = String(input.value ?? '').trim();
    return raw === '' ? fallback : Number(raw);
}

function buildHumanizedFromForm() {
    const seedText = (hzRandomSeed ? hzRandomSeed.value : "").trim();

    return {
        enabled: Boolean(hzEnabled ? hzEnabled.checked : false),
        typing_delay_min: numberValue(hzTypingDelayMin, 0.04),
        typing_delay_max: numberValue(hzTypingDelayMax, 0.18),
        typo_probability: numberValue(hzTypoProbability, 0.03),
        typo_delay_min: numberValue(hzTypoDelayMin, 0.04),
        typo_delay_max: numberValue(hzTypoDelayMax, 0.12),
        backspace_delay_min: numberValue(hzBackspaceDelayMin, 0.02),
        backspace_delay_max: numberValue(hzBackspaceDelayMax, 0.08),
        click_offset_x_min: numberValue(hzClickOffsetXMin, -4),
        click_offset_x_max: numberValue(hzClickOffsetXMax, 4),
        click_offset_y_min: numberValue(hzClickOffsetYMin, -4),
        click_offset_y_max: numberValue(hzClickOffsetYMax, 4),
        word_pause_probability: numberValue(hzWordPauseProbability, 0.04),
        word_pause_max: numberValue(hzWordPauseMax, 0.24),
        click_hold_min: numberValue(hzClickHoldMin, 0.01),
        click_hold_max: numberValue(hzClickHoldMax, 0.05),
        target_strategy: "center_bias",
        move_duration_min: 0.2,
        move_duration_max: 0.7,
        move_steps_min: 8,
        move_steps_max: 24,
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
        ["点击偏移 X", cfg.click_offset_x_min, cfg.click_offset_x_max],
        ["点击偏移 Y", cfg.click_offset_y_min, cfg.click_offset_y_max],
        ["物理按压", cfg.click_hold_min, cfg.click_hold_max],
    ];
    for (const [name, minV, maxV] of pairs) {
        if (minV > maxV) return `${name}: 最小值必须 <= 最大值`;
    }
    return "";
}
