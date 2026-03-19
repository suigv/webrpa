import { fetchJson } from '../utils/api.js';
import { toast } from '../ui/toast.js';
import { toggleAdvancedTaskFields } from '../utils/task_form_ui.js';
import { sysLog, unitLog } from './logs.js';
import {
    closeUnitAiDialog,
    openUnitAiDialog,
    submitUnitAiTask,
} from './device_ai_dialog.js';
import {
    bindDeviceModalActions,
    openDeviceDetail,
} from './device_detail_modal.js';
import {
    renderDeviceTaskForm,
    runBulkPluginTasks,
    submitUnitPluginTask,
} from './device_task_panel.js';
import { closeUnitDetail, openUnitDetail } from './device_unit_detail.js';
import {
    getTaskCatalog,
    buildTaskRequest,
    apiSubmitTask,
} from './task_service.js';

const $ = (id) => document.getElementById(id);

let selectedUnits = new Set();
let currentCatalog = [];
let currentUnitsById = new Map();
let currentUnitDetail = null;

const UNIT_ADVANCED_COLLAPSED_TEXT = '配置高级属性';
const UNIT_ADVANCED_EXPANDED_TEXT = '收起高级属性';
const BULK_ADVANCED_COLLAPSED_TEXT = '显示高级参数';
const BULK_ADVANCED_EXPANDED_TEXT = '收起高级参数';

function clearElement(element) {
    if (element) {
        element.replaceChildren();
    }
}

function buildUnitLogTarget(unit) {
    return `Unit #${unit.parent_id}-${unit.cloud_id}`;
}

function createTextBlock(label, value, valueStyle = '') {
    const row = document.createElement('div');
    const labelSpan = document.createElement('span');
    labelSpan.className = 'text-muted';
    labelSpan.textContent = `${label}: `;
    const valueSpan = document.createElement('span');
    valueSpan.textContent = value;
    if (valueStyle) {
        valueSpan.style.cssText = valueStyle;
    }
    row.append(labelSpan, valueSpan);
    return row;
}

function createDeviceStat(label, value, extraClass = '') {
    const block = document.createElement('div');
    block.className = 'device-stat';

    const labelEl = document.createElement('div');
    labelEl.className = 'device-stat-label';
    labelEl.textContent = label;

    const valueEl = document.createElement('div');
    valueEl.className = `device-stat-value ${extraClass}`.trim();
    valueEl.textContent = value;

    block.append(labelEl, valueEl);
    return block;
}

function summarizeTaskState(unit, isOnline) {
    if (unit.current_task) return '执行中';
    return isOnline ? '空闲待命' : '不可用';
}

function summarizeHealth(unit, isOnline) {
    if (isOnline) {
        if (typeof unit.latency_ms === 'number' && Number.isFinite(unit.latency_ms)) {
            return `${unit.latency_ms} ms`;
        }
        return '已上线';
    }
    const reason = String(unit.availability_reason || '').trim();
    if (!reason) return '等待回线';
    if (reason.toLowerCase().includes('timed out')) return '连接超时';
    if (reason.toLowerCase().includes('refused')) return '连接被拒绝';
    return reason;
}

let unitAccounts = [];

async function loadUnitAccounts() {
    const select = $("unitAccountSelect");
    const hint = $("unitAccountHint");
    if (!select) return;
    try {
        const r = await fetchJson("/api/data/accounts/parsed");
        if (!r.ok) {
            unitAccounts = [];
            renderEmptyAccountSelect(select, '-- 账号加载失败 --');
            if (hint) hint.textContent = '加载账号失败';
            return;
        }
        unitAccounts = (r.data?.accounts || []).filter(a => a.status === 'ready');
        select.replaceChildren();
        const emptyOpt = document.createElement('option');
        emptyOpt.value = '';
        emptyOpt.textContent = `-- 不绑定账号 (${unitAccounts.length} 个就绪) --`;
        select.appendChild(emptyOpt);
        unitAccounts.forEach((a, i) => {
            const opt = document.createElement('option');
            opt.value = String(i);
            opt.textContent = a.account;
            select.appendChild(opt);
        });
        if (hint) hint.textContent = `账号池共 ${unitAccounts.length} 个就绪账号`;
    } catch (e) {
        unitAccounts = [];
        renderEmptyAccountSelect(select, '-- 账号加载失败 --');
        if (hint) hint.textContent = '加载账号失败';
    }
}

function getSelectedAccount() {
    const select = $("unitAccountSelect");
    if (!select || select.value === '') return null;
    return unitAccounts[parseInt(select.value)] || null;
}

function renderEmptyAccountSelect(select, label) {
    if (!select) return;
    select.replaceChildren();
    const emptyOpt = document.createElement('option');
    emptyOpt.value = '';
    emptyOpt.textContent = label;
    select.appendChild(emptyOpt);
}

export function initDevices() {
    const clearBtn = $("clearSelection");
    const closeBtn = $("closeDetail");
    const bulkBtn = $("bulkRunBtn");
    const scanBtn = $("scanDevices");
    const initAllBtn = $("initializeAllDevices");
    const openAiBtn = $("openUnitAiDialog");
    const closeAiBtn = $("closeUnitAiModal");
    const cancelAiBtn = $("cancelUnitAiTask");
    const submitAiBtn = $("submitUnitAiTask");
    const toggleAiAdvancedBtn = $("toggleUnitAiAdvancedBtn");

    const accountRefreshBtn = $("unitAccountRefresh");
    if (accountRefreshBtn) accountRefreshBtn.onclick = loadUnitAccounts;

    bindDeviceModalActions({
        getCurrentUnit: () => currentUnitDetail,
        onDeviceChanged: () => {
            void loadDevices();
        },
    });
    
    // 系统状态模态框绑定 (全局)
    const showSysBtn = $("showSystemStatus") || $("apiStatus");
    if (showSysBtn) {
        showSysBtn.style.cursor = "pointer";
        showSysBtn.onclick = openSystemStatusModal;
    }
    
    const closeSystemModalBtns = document.querySelectorAll(".close-system-modal-btn");
    closeSystemModalBtns.forEach(btn => btn.onclick = closeSystemModal);
    
    const globalBrowserDiagBtn = $("runGlobalBrowserDiag");
    if (globalBrowserDiagBtn) globalBrowserDiagBtn.onclick = runGlobalBrowserDiag;

    if (clearBtn) clearBtn.onclick = clearSelection;
    if (closeBtn) closeBtn.onclick = closeDetail;
    if (bulkBtn) bulkBtn.onclick = runBulkTasks;
    if (scanBtn) scanBtn.onclick = scanDevices;
    if (initAllBtn) initAllBtn.onclick = initializeAllDevices;
    if (openAiBtn) openAiBtn.onclick = () => openUnitAiDialog(currentUnitDetail);
    if (closeAiBtn) closeAiBtn.onclick = closeUnitAiDialog;
    if (cancelAiBtn) cancelAiBtn.onclick = closeUnitAiDialog;
    if (submitAiBtn) submitAiBtn.onclick = submitCurrentUnitAiTask;

    if (toggleAiAdvancedBtn) {
        toggleAiAdvancedBtn.onclick = () => {
            const advanced = $("unitAiAdvanced");
            if (advanced) {
                advanced.style.display = advanced.style.display === "block" ? "none" : "block";
            }
        };
    }

    const unitPluginSelect = $("unitPluginSelect");
    if (unitPluginSelect) unitPluginSelect.onchange = renderUnitPluginFields;
    const bulkPluginSelect = $("bulkPluginSelect");
    if (bulkPluginSelect) bulkPluginSelect.onchange = renderBulkPluginFields;

    const showMoreBtn = $('showMoreUnitFields');
    if (showMoreBtn) {
        showMoreBtn.onclick = () => {
            const container = $("unitPluginFields");
            toggleAdvancedTaskFields(container, showMoreBtn);
        };
    }

    const showMoreBulkBtn = $('showMoreBulkFields');
    if (showMoreBulkBtn) {
        showMoreBulkBtn.onclick = () => {
            const container = $("bulkTaskFields");
            toggleAdvancedTaskFields(container, showMoreBulkBtn);
        };
    }

    const toggleAdvancedBtn = $('toggleUnitAdvancedBtn');
    if (toggleAdvancedBtn) {
        toggleAdvancedBtn.onclick = () => {
            const advanced = $('unitAdvanced');
            if (advanced) {
                advanced.style.display = advanced.style.display === 'block' ? 'none' : 'block';
            }
        };
    }

    loadDevices();
    loadPluginCatalog();
    setInterval(loadDevices, 5000);
}

function closeSystemModal() {
    const modal = $("systemStatusModal");
    if (modal) modal.style.display = "none";
}

function createStatusRow(labelText, initialValueText = '-') {
    const row = document.createElement('div');
    const labelSpan = document.createElement('span');
    labelSpan.className = 'text-muted';
    labelSpan.textContent = `${labelText}: `;
    const valueSpan = document.createElement('span');
    valueSpan.textContent = initialValueText;
    row.append(labelSpan, valueSpan);
    return { row, valueSpan };
}

async function openSystemStatusModal() {
    const modal = $("systemStatusModal");
    if (modal) modal.style.display = "flex";
    
    const coreStatus = $("coreServicesStatus");
    clearElement(coreStatus);
    clearElement($("browserDiagResult"));
    
    const baseUrl = location.origin || '(unknown)';
    const apiRow = createStatusRow("API 地址", baseUrl);
    const healthRow = createStatusRow("API 健康", "检测中...");
    const rpcRow = createStatusRow("RPC", "检测中...");
    const pluginRow = createStatusRow("已加载插件", "检测中...");
    coreStatus.append(apiRow.row, healthRow.row, rpcRow.row, pluginRow.row);

    try {
        const r = await fetchJson("/health", { silentErrors: true });
        if (!r.ok || !r.data) {
            healthRow.valueSpan.textContent = "不可用";
            healthRow.valueSpan.style.color = "var(--warn)";
            rpcRow.valueSpan.textContent = "未知";
            rpcRow.valueSpan.style.color = "var(--warn)";
            pluginRow.valueSpan.textContent = "未知";
            pluginRow.valueSpan.style.color = "var(--warn)";
            return;
        }

        healthRow.valueSpan.textContent = "OK";
        healthRow.valueSpan.style.color = "var(--success)";

        if (r.data.rpc_enabled) {
            rpcRow.valueSpan.textContent = "已启用";
            rpcRow.valueSpan.style.color = "var(--success)";
        } else {
            rpcRow.valueSpan.textContent = "已禁用";
            rpcRow.valueSpan.style.color = "var(--warn)";
        }

        const loadedPlugins = r.data?.plugins?.loaded;
        if (Array.isArray(loadedPlugins)) {
            pluginRow.valueSpan.textContent = `${loadedPlugins.length} 个`;
        } else {
            pluginRow.valueSpan.textContent = "未知";
        }
    } catch (e) {
        healthRow.valueSpan.textContent = "检测失败";
        healthRow.valueSpan.style.color = "var(--warn)";
        rpcRow.valueSpan.textContent = "未知";
        rpcRow.valueSpan.style.color = "var(--warn)";
        pluginRow.valueSpan.textContent = "未知";
        pluginRow.valueSpan.style.color = "var(--warn)";
    }
}

async function runGlobalBrowserDiag() {
    const resultBox = $("browserDiagResult");
    resultBox.replaceChildren();
    const loading = document.createElement('div');
    loading.className = 'text-xs text-muted';
    loading.textContent = '正在探测服务端浏览器环境...';
    resultBox.appendChild(loading);
    
    const r = await fetchJson("/api/diagnostics/browser");
    if (r.ok) {
        const d = r.data;
        const wrap = document.createElement('div');
        wrap.className = 'bg-black text-green-400 p-4 rounded font-mono text-xs overflow-auto max-h-64 mt-2';
        const pre = document.createElement('pre');
        pre.style.margin = '0';
        const lines = [];
        lines.push(`> Browser Ready: ${d.ready ? 'YES' : 'NO'}`);
        if (d.error) lines.push(`> Error: ${d.error}`);
        lines.push(`> DrissionPage: ${d.drissionpage_importable ? 'OK' : 'FAIL'}`);
        lines.push(`> Chromium Binary: ${d.chromium_binary_found ? 'FOUND' : 'NOT FOUND'}`);
        if (d.chromium_binary_path) lines.push(`> Path: ${d.chromium_binary_path}`);
        pre.textContent = lines.join('\n');
        wrap.appendChild(pre);
        resultBox.replaceChildren(wrap);
    } else {
        toast.error("诊断请求失败");
        resultBox.replaceChildren();
        const err = document.createElement('div');
        err.className = 'text-error text-xs';
        err.textContent = '请求失败，请检查 API 连通性';
        resultBox.appendChild(err);
    }
}

async function loadPluginCatalog() {
    currentCatalog = await getTaskCatalog();
    const select = $("bulkPluginSelect");
    const unitSelect = $("unitPluginSelect");
    if (select) renderGroupedSelect(select, currentCatalog);
    if (unitSelect) renderGroupedSelect(unitSelect, currentCatalog);
    renderBulkPluginFields();
    renderUnitPluginFields();
}

function renderGroupedSelect(select, tasks) {
    const grouped = {};
    tasks.forEach(t => {
        const cat = t.category || "其它";
        if (!grouped[cat]) grouped[cat] = [];
        grouped[cat].push(t);
    });
    clearElement(select);
    Object.keys(grouped).forEach(cat => {
        const groupEl = document.createElement("optgroup");
        groupEl.label = cat;
        grouped[cat].forEach(t => {
            const opt = document.createElement("option");
            opt.value = t.task;
            opt.textContent = t.display_name || t.task;
            groupEl.appendChild(opt);
        });
        select.appendChild(groupEl);
    });
}

export async function loadDevices() {
    const r = await fetchJson("/api/devices/");
    if (r.ok) renderUnits(r.data);
}

export async function scanDevices() {
    const btn = $("scanDevices");
    if (!btn) return;
    btn.disabled = true;
    const oldText = btn.textContent;
    btn.textContent = "正在扫描...";

    sysLog("已在后台启动局域网发现...");
    toast.info("已在后台启动局域网发现...");

    try {
        const r = await fetchJson("/api/devices/discover", { method: "POST" });
        if (r.ok) {
            sysLog("扫描指令已下发，设备将陆续上线");
            toast.success("扫描指令已下发");
            let ticks = 0;
            const fastSync = setInterval(async () => {
                await loadDevices();
                ticks++;
                if (ticks >= 4) clearInterval(fastSync);
            }, 2000);
        } else {
            sysLog(`发现失败: ${r.status}`, "error");
        }
    } catch (e) {
        sysLog("扫描请求异常", "error");
    } finally {
        setTimeout(() => {
            if(btn) {
                btn.disabled = false;
                btn.textContent = oldText;
            }
        }, 3000);
    }
}

function renderUnits(devices) {
    const list = $("devicesList");
    const detailView = $("unitDetailView");
    if (!list || (detailView && detailView.style.display === "flex")) return;

    const onlineUnits = [];
    const offlineUnits = [];
    currentUnitsById = new Map();

    devices.forEach(d => {
        (d.cloud_machines || []).forEach(u => {
            const unit = { ...u, parent_ip: d.ip, parent_id: d.device_id, ai_type: d.ai_type };
            currentUnitsById.set(`${d.device_id}-${u.cloud_id}`, unit);
            if (u.availability_state === "available") onlineUnits.push(unit);
            else offlineUnits.push(unit);
        });
    });

    clearElement(list);
    if (onlineUnits.length > 0) {
        renderHeader(list, `可用节点 (${onlineUnits.length})`);
        onlineUnits.forEach(u => renderUnitCard(list, u));
    }
    if (offlineUnits.length > 0) {
        renderHeader(list, `离线节点 (${offlineUnits.length})`, true);
        offlineUnits.forEach(u => renderUnitCard(list, u));
    }
}

function renderHeader(container, title, isMuted = false) {
    const h = document.createElement("div");
    h.style.cssText = `grid-column: 1 / -1; margin: 8px 0; color: ${isMuted ? 'var(--text-muted)' : 'var(--text-main)'}; font-size: 13px; font-weight: 600; border-bottom: 1px solid var(--border); padding-bottom: 8px;`;
    h.textContent = title;
    container.appendChild(h);
}

function renderUnitCard(container, u) {
    const unitId = `${u.parent_id}-${u.cloud_id}`;
    const isOnline = u.availability_state === "available";
    const card = document.createElement("div");
    card.className = `device-card ${selectedUnits.has(unitId) ? 'selected' : ''}`;
    card.style.opacity = isOnline ? "1" : "0.5";

    const header = document.createElement('div');
    header.className = 'device-card-header';

    const title = document.createElement('span');
    title.className = 'device-id';
    title.textContent = `云机 #${unitId}`;

    const badge = document.createElement('span');
    badge.className = 'badge badge-sm';
    badge.textContent = u.ai_type || "volc";

    const infoBtn = document.createElement('button');
    infoBtn.className = 'btn btn-text text-primary p-0 ml-auto';
    infoBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>';
    infoBtn.onclick = (e) => {
        e.stopPropagation();
        currentUnitDetail = u;
        openDeviceDetail(u);
    };

    header.append(title, badge, infoBtn);

    const meta = document.createElement('div');
    meta.className = 'device-meta';
    meta.append(createTextBlock('节点', `${u.parent_id}-${u.cloud_id}`));

    const stats = document.createElement('div');
    stats.className = 'device-meta-grid';
    stats.append(
        createDeviceStat('机型', u.machine_model_name || '未识别'),
        createDeviceStat(
            '状态',
            isOnline ? '在线' : '离线',
            isOnline ? 'status-online' : 'status-offline'
        ),
        createDeviceStat('任务', summarizeTaskState(u, isOnline)),
        createDeviceStat(isOnline ? '质量' : '异常', summarizeHealth(u, isOnline))
    );
    meta.appendChild(stats);

    if (u.current_task) {
        const taskTag = document.createElement('div');
        taskTag.className = 'text-xs mt-2 bg-blue-50 text-blue-600 px-2 py-1 rounded border border-blue-100 truncate';
        taskTag.textContent = `任务: ${u.current_task}`;
        meta.appendChild(taskTag);
    }

    const actions = document.createElement('div');
    actions.className = 'mt-4 pt-4 border-t flex gap-2';
    
    const controlBtn = document.createElement('button');
    controlBtn.className = 'btn btn-primary btn-sm flex-1';
    controlBtn.textContent = '进入接管';
    controlBtn.disabled = !isOnline;
    controlBtn.onclick = (e) => {
        e.stopPropagation();
        openUnitDetail({
            unit: u,
            clearElement,
            buildUnitLogTarget,
            renderUnitPluginFields,
            loadUnitAccounts,
            submitUnitTask,
            setCurrentUnit: (unit) => {
                currentUnitDetail = unit;
            },
        });
    };
    
    actions.appendChild(controlBtn);
    card.append(header, meta, actions);
    card.onclick = () => { toggleSelection(unitId, !selectedUnits.has(unitId)); };
    container.appendChild(card);
}

function toggleSelection(id, check) {
    if (check) selectedUnits.add(id); else selectedUnits.delete(id);
    updateBar();
    loadDevices(); // 刷新选中样式
}

function updateBar() {
    const el = $("selectedCount");
    const bar = $("selectionBar");
    if(el) el.textContent = selectedUnits.size;
    if(bar) bar.style.display = selectedUnits.size > 0 ? "flex" : "none";
}

function clearSelection() {
    selectedUnits.clear(); updateBar(); loadDevices();
}

function renderBulkPluginFields() {
    const select = $("bulkPluginSelect");
    const config = $("bulkTaskConfig");
    const container = $("bulkTaskFields");
    const guideCard = $("bulkTaskGuideCard");
    const showMoreBtn = $('showMoreBulkFields');
    if (!select || !config || !container || !guideCard) return;

    const taskName = select.value;
    renderDeviceTaskForm({
        catalog: currentCatalog,
        taskName,
        configContainer: config,
        guideCard,
        fieldsContainer: container,
        toggleButton: showMoreBtn,
        collapsedText: BULK_ADVANCED_COLLAPSED_TEXT,
        expandedText: BULK_ADVANCED_EXPANDED_TEXT,
    });
}

function renderUnitPluginFields() {
    const select = $("unitPluginSelect");
    const container = $("unitPluginFields");
    if (!select || !container) return;
    renderDeviceTaskForm({
        catalog: currentCatalog,
        taskName: select.value,
        guideCard: $("unitTaskGuideCard"),
        fieldsContainer: container,
        toggleButton: $('showMoreUnitFields'),
        collapsedText: UNIT_ADVANCED_COLLAPSED_TEXT,
        expandedText: UNIT_ADVANCED_EXPANDED_TEXT,
    });
}

export function closeDetail(restoreMainTab = true) {
    closeUnitDetail({
        restoreMainTab,
        closeUnitAiDialog,
        loadDevices,
        setCurrentUnit: (unit) => {
            currentUnitDetail = unit;
        },
    });
}

async function submitUnitTask(unit) {
    const select = $("unitPluginSelect");
    const container = $("unitPluginFields");
    if(!select || !container) return;
    await submitUnitPluginTask({
        catalog: currentCatalog,
        unit,
        taskName: select.value,
        fieldsContainer: container,
        account: getSelectedAccount(),
        priority: $("unitTaskPriority")?.value || 50,
        maxRetries: $("unitTaskMaxRetries")?.value || 0,
        runAt: $("unitTaskRunAt")?.value || null,
        onStarted: ({ displayName }) => {
            unitLog(`>>> 业务已启动: ${displayName}`);
            unitLog(`>>> 正在建立连接并同步运行环境...`);
        },
        onFailed: () => {
            unitLog(`❌ 任务部署失败，请检查网络或设备状态`, "error");
        },
    });
}

async function runBulkTasks() {
    const select = $("bulkPluginSelect");
    const fieldContainer = $("bulkTaskFields");
    if(!select || !fieldContainer) return;
    const defaultPackage = (localStorage.getItem("defaultPackage") || "").trim();
    const result = await runBulkPluginTasks({
        catalog: currentCatalog,
        taskName: select.value,
        fieldsContainer: fieldContainer,
        selectedUnitIds: Array.from(selectedUnits),
        defaultPackage,
    });
    if (result.ok) {
        clearSelection();
    }
}

async function initializeAllDevices() {
    const onlineUnits = Array.from(currentUnitsById.values()).filter(u => u.availability_state === "available");
    if(onlineUnits.length === 0) return toast.warn("当前没有在线的云机");
    
    const bulkWarning = `【全局高危操作！！】\n\n即将对所有 ${onlineUnits.length} 个在线节点执行一键新机！\n\n该操作会切换机型并重写设备环境画像，可能导致已登录账号失效。\n\n若确定执行，请在下方输入“确认”：`;
    const input = prompt(bulkWarning);
    
    if (input !== "确认") {
        toast.info("操作已取消");
        return;
    }

    const seed = prompt("可选：请输入统一随机种子（留空则每台设备自动随机）", "");

    sysLog(`开始全量一键新机, 目标数量: ${onlineUnits.length}`);
    for (const u of onlineUnits) {
        const taskData = buildTaskRequest({
            task: 'one_click_new_device',
            payload: {
                country_profile: "jp_mobile",
                model_source: "online",
                refresh_inventory: true,
                take_screenshot: true,
                seed: seed || "",
            },
            targets: [{ device_id: u.parent_id, cloud_id: u.cloud_id }],
        });
        await apiSubmitTask(taskData, { notify: false, log: false, openReport: false });
    }
    toast.success("全量一键新机指令已分发");
}

async function submitCurrentUnitAiTask() {
    if (!currentUnitDetail) return;
    await submitUnitAiTask(currentUnitDetail, {
        onSuccess: () => {
            unitLog(">>> AI 对话任务已下发");
            closeUnitAiDialog();
        },
        onFailure: () => {
            unitLog("❌ AI 对话任务提交失败", "error");
        },
    });
}
