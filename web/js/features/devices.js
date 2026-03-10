import { fetchJson } from '../utils/api.js';
import { toast } from '../ui/toast.js';
import { renderCommonFields } from '../utils/ui_utils.js';
import { sysLog, unitLog } from './logs.js';
import { getTaskCatalog, apiSubmitTask, buildTaskRequest, collectTaskPayload } from './task_service.js';
import { store } from '../state/store.js';

const $ = (id) => document.getElementById(id);

let selectedUnits = new Set();
let currentCatalog = [];
let currentUnitsById = new Map();
let currentUnitDetail = null;

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

    if (clearBtn) clearBtn.onclick = clearSelection;
    if (closeBtn) closeBtn.onclick = closeDetail;
    if (bulkBtn) bulkBtn.onclick = runBulkTasks;
    if (scanBtn) scanBtn.onclick = scanDevices;
    if (initAllBtn) initAllBtn.onclick = initializeAllDevices;
    if (openAiBtn) openAiBtn.onclick = () => openUnitAiDialog(currentUnitDetail);
    if (closeAiBtn) closeAiBtn.onclick = closeUnitAiDialog;
    if (cancelAiBtn) cancelAiBtn.onclick = closeUnitAiDialog;
    if (submitAiBtn) submitAiBtn.onclick = submitUnitAiTask;
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

    const showMoreBtn = $('showMoreUnitFields');
    if (showMoreBtn) {
        showMoreBtn.onclick = () => {
            const container = $("unitPluginFields");
            if(!container) return;
            const fields = container.querySelectorAll('.field-optional');
            const isHidden = fields[0]?.style.display === 'none';
            fields.forEach(el => el.style.display = isHidden ? 'flex' : 'none');
            showMoreBtn.textContent = isHidden ? '收起可选参数' : '配置高级属性';
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

async function loadPluginCatalog() {
    currentCatalog = await getTaskCatalog();
    const select = $("bulkPluginSelect");
    const unitSelect = $("unitPluginSelect");
    if (select) renderGroupedSelect(select, currentCatalog);
    if (unitSelect) renderGroupedSelect(unitSelect, currentCatalog);
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

    const modelName = u.machine_model_name || "标准型";
    const aiType = u.ai_type || "volc";

    const header = document.createElement('div');
    header.className = 'device-card-header';

    const title = document.createElement('span');
    title.className = 'device-id';
    title.textContent = `云机 #${unitId}`;

    const badge = document.createElement('span');
    badge.className = 'badge badge-sm';
    badge.textContent = aiType;

    const label = document.createElement('label');
    label.className = 'checkbox-container';
    label.style.cssText = 'padding-left:18px; margin:0;';
    label.onclick = (event) => event.stopPropagation();

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = selectedUnits.has(unitId);
    checkbox.disabled = !isOnline;
    checkbox.className = 'unit-checkbox';

    const checkmark = document.createElement('span');
    checkmark.className = 'checkmark';
    checkmark.style.top = '0';

    label.append(checkbox, checkmark);
    header.append(title, badge, label);

    const meta = document.createElement('div');
    meta.className = 'device-meta';
    meta.append(
        createTextBlock('型号', modelName, 'color:var(--text-main);'),
        createTextBlock('路由', `${u.parent_ip}:${u.rpa_port}`),
    );

    const status = document.createElement('div');
    status.style.cssText = `color:${isOnline ? 'var(--success)' : 'var(--error)'}; font-weight: 500;`;
    status.textContent = isOnline ? '就绪' : '连接中断';
    meta.appendChild(status);

    const actions = document.createElement('div');
    actions.className = 'mt-4 pt-4 border-t flex gap-2';
    
    const initBtn = document.createElement('button');
    initBtn.className = 'btn btn-secondary btn-sm flex-1';
    initBtn.textContent = '设备初始化';
    initBtn.disabled = !isOnline;
    initBtn.onclick = (e) => {
        e.stopPropagation();
        initializeDevice(u);
    };
    
    actions.appendChild(initBtn);
    card.append(header, meta, actions);
    checkbox.onchange = () => { toggleSelection(unitId, checkbox.checked); };
    card.onclick = () => { if (isOnline) openUnitDetail(u); else toast.warn("该节点当前无法连接"); };
    container.appendChild(card);
}

function toggleSelection(id, check) {
    if (check) selectedUnits.add(id); else selectedUnits.delete(id);
    updateBar();
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

function renderUnitPluginFields() {
    const select = $("unitPluginSelect");
    const container = $("unitPluginFields");
    if (!select || !container) return;
    const taskName = select.value;
    const task = currentCatalog.find(t => t.task === taskName);
    renderCommonFields(container, task, false);
}

function openUnitDetail(unit) {
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    const view = $("unitDetailView");
    if(view) view.style.display = "flex";
    const title = $("detailUnitTitle");
    if(title) title.textContent = `云机 #${unit.parent_id}-${unit.cloud_id}`;
    currentUnitDetail = unit;
    const logBox = $("unitLogBox");
    clearElement(logBox);
    store.setState({ currentUnitLogTarget: buildUnitLogTarget(unit) });
    renderUnitPluginFields();
    const btn = $("submitSingleTask");
    if(btn) btn.onclick = () => submitUnitTask(unit);
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

export function closeDetail(restoreMainTab = true) {
    const view = $("unitDetailView");
    if(view) view.style.display = "none";
    closeUnitAiDialog();
    currentUnitDetail = null;
    if (restoreMainTab) {
        const tabMain = $("tab-main");
        if(tabMain) tabMain.classList.add("active");
        loadDevices();
    }
    store.setState({ currentUnitLogTarget: '' });
}

async function submitUnitTask(unit) {
    const select = $("unitPluginSelect");
    const container = $("unitPluginFields");
    if(!select || !container) return;

    // 自动合并已知参数，如 device_ip
    const payload = collectTaskPayload(container);
    payload.device_ip = unit.parent_ip;

    const taskData = buildTaskRequest({
        task: select.value,
        payload: payload,
        targets: [{ device_id: unit.parent_id, cloud_id: unit.cloud_id }],
        priority: $("unitTaskPriority")?.value || 50,
        maxRetries: $("unitTaskMaxRetries")?.value || 0,
        runAt: $("unitTaskRunAt")?.value || null,
    });

    const res = await apiSubmitTask(taskData);
    if (res.ok) {
        const taskName = select.value;
        const taskObj = currentCatalog.find(t => t.task === taskName);
        const displayName = taskObj ? taskObj.display_name : taskName;
        
        unitLog(`>>> 业务已启动: ${displayName}`);
        unitLog(`>>> 正在建立连接并同步运行环境...`);
    } else {
        unitLog(`❌ 任务部署失败，请检查网络或设备状态`, "error");
    }
}

async function runBulkTasks() {
    const select = $("bulkPluginSelect");
    if(!select) return;
    const plugin = select.value;
    const count = selectedUnits.size;
    if(!confirm(`即将对选中的 ${count} 个节点执行该操作，是否继续？`)) return;

    sysLog(`开始集群派发任务: ${plugin}, 目标数量: ${count}`);
    for (const id of selectedUnits) {
        const [dId, cId] = id.split("-");
        const unit = currentUnitsById.get(id);
        
        const payload = {};
        // 自动注入环境参数
        if (unit) {
            payload.device_ip = unit.parent_ip;
            // 如果是常用的包名，则自动注入
            payload.package = "com.twitter.android";
        }

        const taskData = buildTaskRequest({
            task: plugin,
            payload: payload,
            targets: [{ device_id: parseInt(dId, 10), cloud_id: parseInt(cId, 10) }],
        });
        await apiSubmitTask(taskData, { notify: false, log: false });
    }
    toast.success("集群任务分发完成");
    clearSelection();
}

async function initializeDevice(unit) {
    const warning = `【高危操作警告】\n\n您确定要初始化云机 #${unit.parent_id}-${unit.cloud_id} 吗？\n\n后果如下：\n1. 强制终止该设备上所有正在运行的任务\n2. 清理 APP 数据与系统缓存\n3. 重置系统语言与地区设置\n\n确定要继续吗？`;
    if(!confirm(warning)) return;
    
    const taskData = buildTaskRequest({
        task: 'mytos_device_setup',
        payload: {
            device_ip: unit.parent_ip,
            package: "com.twitter.android", // 默认设置
            language: "en",
            country: "US"
        },
        targets: [{ device_id: unit.parent_id, cloud_id: unit.cloud_id }],
    });
    
    const res = await apiSubmitTask(taskData);
    if(res.ok) {
        toast.success(`云机 #${unit.parent_id}-${unit.cloud_id} 初始化任务已提交`);
    }
}

async function initializeAllDevices() {
    const onlineUnits = Array.from(currentUnitsById.values()).filter(u => u.availability_state === "available");
    if(onlineUnits.length === 0) return toast.warn("当前没有在线的云机");
    
    const bulkWarning = `【全局高危操作！！】\n\n即将对所有 ${onlineUnits.length} 个在线节点执行系统初始化！\n\n严重后果：\n1. 全局所有正在运行的任务将被强制中断\n2. 所有设备的 App 登录信息将被清除\n3. 系统环境将恢复至初始状态\n\n该操作不可撤销，确定要继续吗？`;
    if(!confirm(bulkWarning)) return;

    // 二次确认逻辑：手动输入“确认”验证
    const input = prompt(`【最终严正确认】\n\n即将对这 ${onlineUnits.length} 台设备执行“全量初始化”。\n该操作将导致所有已登录账号被迫退出！\n\n若确定执行，请在下方输入“确认”：`);
    
    if (input !== "确认") {
        toast.info("操作已取消");
        return;
    }
    
    sysLog(`开始全量设备初始化, 目标数量: ${onlineUnits.length}`);
    for (const u of onlineUnits) {
        const taskData = buildTaskRequest({
            task: 'mytos_device_setup',
            payload: {
                device_ip: u.parent_ip,
                package: "com.twitter.android",
                language: "en",
                country: "US"
            },
            targets: [{ device_id: u.parent_id, cloud_id: u.cloud_id }],
        });
        await apiSubmitTask(taskData, { notify: false, log: false });
    }
    toast.success("全量初始化指令已分发");
}

function parseCommaList(value) {
    return String(value || "")
        .split(",")
        .map(item => item.trim())
        .filter(Boolean);
}

function openUnitAiDialog(unit) {
    if (!unit) return;
    const modal = $("unitAiModal");
    if (modal) modal.style.display = "flex";

    const title = $("unitAiModalTitle");
    if (title) title.textContent = `AI 对话 - 云机 #${unit.parent_id}-${unit.cloud_id}`;

    const goalInput = $("unitAiGoal");
    if (goalInput) goalInput.value = "";

    const profileInput = $("unitAiProfile");
    if (profileInput) profileInput.value = "x_mobile_login_gpt";

    const stateInput = $("unitAiStateIds");
    if (stateInput) stateInput.value = "home,account,password,captcha,two_factor,unknown";

    const actionsInput = $("unitAiActions");
    if (actionsInput) actionsInput.value = "ai.locate_point,input.text,input.enter,swipe.up,swipe.down";

    const appInput = $("unitAiApp");
    if (appInput) appInput.value = "com.twitter.android";

    const bindingInput = $("unitAiBindingId");
    if (bindingInput) bindingInput.value = "tw";

    const systemPrompt = $("unitAiSystemPrompt");
    if (systemPrompt) {
        systemPrompt.value = "你是云机自动化助手，只能使用 allowed_actions。需要点击/输入时先调用 ai.locate_point 获取坐标。";
    }

    const useUitars = $("unitAiUseUitars");
    if (useUitars) useUitars.checked = false;
}

function closeUnitAiDialog() {
    const modal = $("unitAiModal");
    if (modal) modal.style.display = "none";
    const advanced = $("unitAiAdvanced");
    if (advanced) advanced.style.display = "none";
}

async function submitUnitAiTask() {
    if (!currentUnitDetail) return;

    const goal = String($("unitAiGoal")?.value || "").trim();
    if (!goal) {
        toast.warn("请填写任务描述");
        return;
    }

    const expectedStateIds = parseCommaList($("unitAiStateIds")?.value || "");
    if (expectedStateIds.length === 0) {
        toast.warn("预期状态 IDs 不能为空");
        return;
    }

    const allowedActions = parseCommaList($("unitAiActions")?.value || "");
    if (allowedActions.length === 0) {
        toast.warn("允许动作列表不能为空");
        return;
    }

    const appPackage = String($("unitAiApp")?.value || "").trim();
    const bindingId = String($("unitAiBindingId")?.value || "").trim();
    const systemPrompt = String($("unitAiSystemPrompt")?.value || "").trim();
    const profileName = String($("unitAiProfile")?.value || "").trim();
    const useUitars = $("unitAiUseUitars")?.checked || false;

    const payload = {
        device_ip: currentUnitDetail.parent_ip,
        goal,
        observation: {
            expected_state_ids: expectedStateIds,
            allowed_actions: allowedActions,
        }
    };

    if (appPackage) {
        payload.observation.app_package = appPackage;
    }
    if (bindingId) {
        payload.observation.binding_id = bindingId;
    }
    if (systemPrompt) {
        payload.system_prompt = systemPrompt;
    }
    if (profileName) {
        payload._runtime_profile = profileName;
    }
    if (useUitars) {
        payload.fallback_modalities = ["uitars"];
    }

    const taskData = buildTaskRequest({
        task: "gpt_executor",
        payload,
        targets: [{ device_id: currentUnitDetail.parent_id, cloud_id: currentUnitDetail.cloud_id }],
    });

    const res = await apiSubmitTask(taskData);
    if (res.ok) {
        unitLog(">>> AI 对话任务已下发");
        closeUnitAiDialog();
    } else {
        unitLog("❌ AI 对话任务提交失败", "error");
    }
}
