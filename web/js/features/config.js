import { fetchJson } from '../utils/api.js';
import { store } from '../state/store.js';
import { toast } from '../ui/toast.js';

// DOM Elements
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
const hzClickOffsetXMax = document.getElementById("hzClickOffsetXMax");
const hzClickOffsetYMax = document.getElementById("hzClickOffsetYMax");
const hzRandomSeed = document.getElementById("hzRandomSeed");

// Discovery Elements
const discoveryEnabled = document.getElementById("discoveryEnabled");
const discoverySubnet = document.getElementById("discoverySubnet");

const hzInputs = [
  hzEnabled, hzTypoProbability, hzTypingDelayMin, hzTypingDelayMax,
  hzTypoDelayMin, hzTypoDelayMax, hzBackspaceDelayMin, hzBackspaceDelayMax,
  hzClickOffsetXMax, hzClickOffsetYMax, hzRandomSeed,
  discoveryEnabled, discoverySubnet
];

const HZ_PRESETS = {
  low: {
    typo_probability: 0.01, typing_delay_min: 0.02, typing_delay_max: 0.08,
    typo_delay_min: 0.02, typo_delay_max: 0.06, backspace_delay_min: 0.01,
    backspace_delay_max: 0.03, click_offset_x_max: 2, click_offset_y_max: 2,
  },
  medium: {
    typo_probability: 0.03, typing_delay_min: 0.04, typing_delay_max: 0.18,
    typo_delay_min: 0.04, typo_delay_max: 0.12, backspace_delay_min: 0.02,
    backspace_delay_max: 0.08, click_offset_x_max: 4, click_offset_y_max: 4,
  },
  high: {
    typo_probability: 0.08, typing_delay_min: 0.06, typing_delay_max: 0.28,
    typo_delay_min: 0.06, typo_delay_max: 0.20, backspace_delay_min: 0.03,
    backspace_delay_max: 0.12, click_offset_x_max: 8, click_offset_y_max: 8,
  },
};

const HZ_PRESET_KEYS = ["typo_probability", "typing_delay_min", "typing_delay_max"];

export function initConfig() {
    if (saveBtn) saveBtn.addEventListener("click", saveConfig);
    
    if (applyHzPreset) {
        applyHzPreset.addEventListener("click", () => {
            if (hzPreset.value === "custom") return;
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
    setFormValues(data);
    store.setState({ config: data });
}

export async function saveConfig() {
    if(saveBtn) {
        saveBtn.disabled = true;
        saveBtn.textContent = "保存中...";
    }

    const currentConfig = store.getState().config || {};
    const parsedHumanized = buildHumanizedFromForm();
    const humanizedError = validateHumanizedForm(parsedHumanized);
    
    if (humanizedError) {
        toast.error(humanizedError);
        resetSaveBtn();
        return;
    }

    const body = {
        ...currentConfig,
        discovery_enabled: Boolean(discoveryEnabled ? discoveryEnabled.checked : false),
        discovery_subnet: (discoverySubnet ? discoverySubnet.value : "").trim() || currentConfig.discovery_subnet,
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
        loadConfig(); // Reload to sync
    } else {
        toast.error(`保存失败: ${r.status}`);
    }
    resetSaveBtn();
}

function resetSaveBtn() {
    if(saveBtn) {
        saveBtn.disabled = false;
        saveBtn.textContent = "保存全局配置";
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
    if(hzPreset) hzPreset.value = detectHumanizedPreset(cfg);
}

function applyHumanizedPreset(presetName) {
    const preset = HZ_PRESETS[presetName];
    if (!preset) return;
    
    if(hzTypoProbability) hzTypoProbability.value = preset.typo_probability;
    if(hzTypingDelayMin) hzTypingDelayMin.value = preset.typing_delay_min;
    if(hzTypingDelayMax) hzTypingDelayMax.value = preset.typing_delay_max;
    if(hzTypoDelayMin) hzTypoDelayMin.value = preset.typo_delay_min;
    if(hzTypoDelayMax) hzTypoDelayMax.value = preset.typo_delay_max;
    if(hzBackspaceDelayMin) hzBackspaceDelayMin.value = preset.backspace_delay_min;
    if(hzBackspaceDelayMax) hzBackspaceDelayMax.value = preset.backspace_delay_max;
    if(hzClickOffsetXMax) hzClickOffsetXMax.value = preset.click_offset_x_max;
    if(hzClickOffsetYMax) hzClickOffsetYMax.value = preset.click_offset_y_max;
    
    if(hzPreset) hzPreset.value = presetName;
}

function setFormValues(data) {
    const hz = data.humanized || {};
    if(hzEnabled) hzEnabled.checked = Boolean(hz.enabled);
    if(hzTypoProbability) hzTypoProbability.value = hz.typo_probability ?? 0.03;
    if(hzTypingDelayMin) hzTypingDelayMin.value = hz.typing_delay_min ?? 0.04;
    if(hzTypingDelayMax) hzTypingDelayMax.value = hz.typing_delay_max ?? 0.18;
    if(hzTypoDelayMin) hzTypoDelayMin.value = hz.typo_delay_min ?? 0.04;
    if(hzTypoDelayMax) hzTypoDelayMax.value = hz.typo_delay_max ?? 0.12;
    if(hzBackspaceDelayMin) hzBackspaceDelayMin.value = hz.backspace_delay_min ?? 0.02;
    if(hzBackspaceDelayMax) hzBackspaceDelayMax.value = hz.backspace_delay_max ?? 0.08;
    if(hzClickOffsetXMax) hzClickOffsetXMax.value = hz.click_offset_x_max ?? 4;
    if(hzClickOffsetYMax) hzClickOffsetYMax.value = hz.click_offset_y_max ?? 4;
    if(hzRandomSeed) hzRandomSeed.value = hz.random_seed ?? "";
    
    if(discoveryEnabled) discoveryEnabled.checked = Boolean(data.discovery_enabled);
    if(discoverySubnet) discoverySubnet.value = data.discovery_subnet || "";

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
        click_offset_x_max: Number(hzClickOffsetXMax.value || 0),
        click_offset_y_max: Number(hzClickOffsetYMax.value || 0),
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
    ];
    for (const [name, minV, maxV] of pairs) {
        if (minV > maxV) return `${name}: 最小值必须 <= 最大值`;
    }
    return "";
}
