import { fetchJson } from '/static/js/utils/api.js';
import { toast } from '/static/js/ui/toast.js';
import { renderCommonFields } from '/static/js/utils/ui_utils.js';
import { sysLog, unitLog } from '/static/js/features/logs.js';
import { getTaskCatalog, apiSubmitTask, buildTaskRequest, collectTaskPayload } from '/static/js/features/task_service.js';
import { store } from '/static/js/state/store.js';

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

    // 设备详情模态框绑定
    const closeDeviceModalBtns = document.querySelectorAll(".close-device-modal-btn");
    closeDeviceModalBtns.forEach(btn => btn.onclick = closeDeviceModal);
    
    const stopDeviceBtn = $("stopDeviceTasksBtn");
    if (stopDeviceBtn) stopDeviceBtn.onclick = () => stopDeviceTasks(currentUnitDetail);

    const enableDeviceBtn = $("enableDeviceBtn");
    if (enableDeviceBtn) enableDeviceBtn.onclick = () => setDeviceOnlineStatus(currentUnitDetail, true);

    const disableDeviceBtn = $("disableDeviceBtn");
    if (disableDeviceBtn) disableDeviceBtn.onclick = () => setDeviceOnlineStatus(currentUnitDetail, false);
    
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

function showDeviceModal() {
    const modal = $("deviceDetailModal");
    if (modal) modal.style.display = "flex";
}

function closeDeviceModal() {
    const modal = $("deviceDetailModal");
    if (modal) modal.style.display = "none";
}

async function stopDeviceTasks(unit) {
    if (!unit) return;
    if (!confirm(`确定要停止云机 #${unit.parent_id}-${unit.cloud_id} 上正在运行的所有任务吗？`)) return;

    const r = await fetchJson(`/api/tasks/device/${unit.parent_id}/stop`, { method: "POST" });
    if (r.ok) {
        toast.success(`已下发停止指令，取消了 ${r.data.cancelled_count} 个任务`);
        closeDeviceModal();
        loadDevices();
    } else {
        toast.error("停止任务失败");
    }
}

async function setDeviceOnlineStatus(unit, online) {
    if (!unit) return;
    const action = online ? "上线" : "下线";
    if (!confirm(`确定要将设备 #${unit.parent_id} ${action}吗？`)) return;
    const endpoint = online ? "start" : "stop";
    const r = await fetchJson(`/api/devices/${unit.parent_id}/${endpoint}`, { method: "POST" });
    if (r.ok) {
        toast.success(`设备 #${unit.parent_id} 已${action}`);
        closeDeviceModal();
        loadDevices();
    } else {
        toast.error(`设备${action}失败`);
    }
}

function closeSystemModal() {
    const modal = $("systemStatusModal");
    if (modal) modal.style.display = "none";
}

async function openSystemStatusModal() {
    const modal = $("systemStatusModal");
    if (modal) modal.style.display = "flex";
    
    const coreStatus = $("coreServicesStatus");
    clearElement(coreStatus);
    clearElement($("browserDiagResult"));
    
    // 注入基础状态
    coreStatus.append(createTextBlock("API 端口", "8001 (WebRPA Console)"));
    coreStatus.append(createTextBlock("Redis 队列", "已连接 (Local)", "color:var(--success)"));
    coreStatus.append(createTextBlock("拟真引擎", "已就绪", "color:var(--success)"));
}

async function runGlobalBrowserDiag() {
    const resultBox = $("browserDiagResult");
    resultBox.innerHTML = '<div class="text-xs text-muted">正在探测服务端浏览器环境...</div>';
    
    const r = await fetchJson("/api/diagnostics/browser");
    if (r.ok) {
        const d = r.data;
        let html = `<div class="bg-black text-green-400 p-4 rounded font-mono text-xs overflow-auto max-h-64 mt-2">`;
        html += `> Browser Ready: ${d.ready ? 'YES' : 'NO'}\n`;
        if (d.error) html += `> Error: ${d.error}\n`;
        html += `> DrissionPage: ${d.drissionpage_importable ? 'OK' : 'FAIL'}\n`;
        html += `> Chromium Binary: ${d.chromium_binary_found ? 'FOUND' : 'NOT FOUND'}\n`;
        if (d.chromium_binary_path) html += `> Path: ${d.chromium_binary_path}\n`;
        html += `</div>`;
        resultBox.innerHTML = html;
    } else {
        toast.error("诊断请求失败");
        resultBox.innerHTML = '<div class="text-error text-xs">请求失败，请检查 API 连通性</div>';
    }
}

function openDeviceDetail(u) {
    currentUnitDetail = u;
    const content = $("deviceDetailContent");
    clearElement(content);
    
    const unitId = `${u.parent_id}-${u.cloud_id}`;
    $("deviceDetailTitle").textContent = `设备详情 - 云机 #${unitId}`;
    
    const grid = document.createElement("div");
    grid.className = "form-grid columns-2 text-sm";
    
    grid.append(createTextBlock("设备 IP", u.parent_ip));
    grid.append(createTextBlock("ADB 端口", u.rpa_port));
    grid.append(createTextBlock("API 端口", u.api_port));
    grid.append(createTextBlock("云机型号", u.machine_model_name || "标准型"));
    grid.append(createTextBlock("AI 引擎", u.ai_type));
    grid.append(createTextBlock("状态", u.availability_state, `color:${u.availability_state === 'available' ? 'var(--success)' : 'var(--error)'}`));
    
    if (u.current_task) {
        const taskRow = createTextBlock("当前任务", u.current_task, "color:var(--text-primary); font-weight:600;");
        taskRow.style.gridColumn = "1 / -1";
        grid.append(taskRow);
    }
    
    content.appendChild(grid);
    showDeviceModal();
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
    infoBtn.onclick = (e) => { e.stopPropagation(); openDeviceDetail(u); };

    header.append(title, badge, infoBtn);

    const meta = document.createElement('div');
    meta.className = 'device-meta';
    meta.append(
        createTextBlock('路由', `${u.parent_ip}:${u.rpa_port}`),
    );

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
        openUnitDetail(u);
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

function renderUnitPluginFields() {
    const select = $("unitPluginSelect");
    const container = $("unitPluginFields");
    if (!select || !container) return;
    const taskName = select.value;
    const task = currentCatalog.find(t => t.task === taskName);
    renderCommonFields(container, task, false);
}

async function loadUnitScreenshot(unit) {
    const img = $("unitScreenshotImg");
    const placeholder = $("unitScreenshotPlaceholder");
    if (!img || !placeholder) return;
    if (unit.availability_state !== "available") {
        img.style.visibility = "hidden";
        placeholder.textContent = "设备离线，无法获取截图";
        placeholder.style.visibility = "visible";
        return;
    }
    // 不隐藏当前图片，后台预加载新图，加载完成后无缝替换
    try {
        // API 端会从 config/devices.json 推导 device_ip，并按 cloud_id 推导 rpa_port。
        const url = `/api/devices/${unit.parent_id}/${unit.cloud_id}/screenshot?t=${Date.now()}`;
        const resp = await fetch(url);
        if (!resp.ok) {
            let reason = `HTTP ${resp.status}`;
            const body = await resp.json().catch(() => null);
            if (body?.detail) reason = body.detail;
            if (resp.status === 502) reason = `设备不可达 (${reason})`;
            throw new Error(reason);
        }
        const blob = await resp.blob();
        const newUrl = URL.createObjectURL(blob);
        await new Promise((resolve, reject) => {
            const tmp = new Image();
            tmp.onload = () => {
                const oldUrl = img.src;
                img.src = newUrl;
                img.style.visibility = "visible";
                placeholder.style.visibility = "hidden";
                if (oldUrl && oldUrl.startsWith('blob:')) URL.revokeObjectURL(oldUrl);
                resolve();
            };
            tmp.onerror = () => {
                URL.revokeObjectURL(newUrl);
                reject(new Error('image decode failed'));
            };
            tmp.src = newUrl;
        });
    } catch (e) {
        if (!img.src || !img.src.startsWith('blob:')) {
            img.style.visibility = "hidden";
            placeholder.textContent = `截图获取失败: ${e.message}`;
            placeholder.style.visibility = "visible";
        }
        // 若已有图片则静默失败，保留上一张
    }
}

function openUnitDetail(unit) {
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    const view = $("unitDetailView");
    if(view) view.style.display = "flex";
    const title = $("detailUnitTitle");
    if(title) title.textContent = `云机 #${unit.parent_id}-${unit.cloud_id}`;
    currentUnitDetail = unit;
    document.body.dataset.currentDeviceId = unit.parent_id;
    document.body.dataset.currentCloudId = unit.cloud_id;
    const logBox = $("unitLogBox");
    clearElement(logBox);
    store.setState({ currentUnitLogTarget: buildUnitLogTarget(unit) });
    renderUnitPluginFields();
    loadUnitAccounts();
    const btn = $("submitSingleTask");
    if(btn) btn.onclick = () => submitUnitTask(unit);
    const refreshBtn = $("refreshScreenshot");
    if(refreshBtn) refreshBtn.onclick = () => loadUnitScreenshot(unit);
    loadUnitScreenshot(unit);
    const _screenshotTimer = setInterval(() => {
        if (currentUnitDetail !== unit) {
            clearInterval(_screenshotTimer);
            return;
        }
        loadUnitScreenshot(unit);
    }, 1000);
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

export function closeDetail(restoreMainTab = true) {
    const view = $("unitDetailView");
    if(view) view.style.display = "none";
    closeUnitAiDialog();
    currentUnitDetail = null;
    const img = $("unitScreenshotImg");
    if (img && img.src && img.src.startsWith('blob:')) {
        URL.revokeObjectURL(img.src);
        img.src = '';
        img.style.visibility = 'hidden';
    }
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

    const payload = collectTaskPayload(container);
    payload.device_ip = unit.parent_ip;

    // 注入选中账号字段（只注入插件支持的字段）
    const account = getSelectedAccount();
    if (account) {
        if (account.account) payload.acc = account.account;
        if (account.password) payload.pwd = account.password;
        if (account.twofa) {
            payload.two_factor_code = account.twofa;
            payload.fa2_secret = account.twofa;
        }
    }

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
    const defaultPackage = (localStorage.getItem("defaultPackage") || "").trim();
    for (const id of selectedUnits) {
        const [dId, cId] = id.split("-");
        const unit = currentUnitsById.get(id);
        
        const payload = {};
        if (unit) {
            payload.device_ip = unit.parent_ip;
            if (defaultPackage) payload.package = defaultPackage;
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

async function initializeAllDevices() {
    const onlineUnits = Array.from(currentUnitsById.values()).filter(u => u.availability_state === "available");
    if(onlineUnits.length === 0) return toast.warn("当前没有在线的云机");
    
    const bulkWarning = `【全局高危操作！！】\n\n即将对所有 ${onlineUnits.length} 个在线节点执行系统初始化！\n\n该操作将导致所有已登录账号被迫退出！\n\n若确定执行，请在下方输入“确认”：`;
    const input = prompt(bulkWarning);
    
    if (input !== "确认") {
        toast.info("操作已取消");
        return;
    }

    const pkg = prompt("请输入要初始化的包名（例如 com.example.app）", (localStorage.getItem("defaultPackage") || ""));
    if (!pkg || !pkg.trim()) return;
    localStorage.setItem("defaultPackage", pkg.trim());
    
    sysLog(`开始全量设备初始化, 目标数量: ${onlineUnits.length}`);
    for (const u of onlineUnits) {
        const taskData = buildTaskRequest({
            task: 'mytos_device_setup',
            payload: {
                device_ip: u.parent_ip,
                package: pkg.trim(),
                language: "en",
                country: "US"
            },
            targets: [{ device_id: u.parent_id, cloud_id: u.cloud_id }],
        });
        await apiSubmitTask(taskData, { notify: false, log: false });
    }
    toast.success("全量初始化指令已分发");
}

async function loadAiDialogAccounts() {
    const select = $("unitAiAccountSelect");
    if (!select) return;
    try {
        const r = await fetchJson("/api/data/accounts/parsed");
        if (!r.ok) {
            renderEmptyAccountSelect(select, '-- 账号加载失败 --');
            return;
        }
        const accounts = (r.data?.accounts || []).filter(a => a.status === 'ready');
        select.replaceChildren();
        const emptyOpt = document.createElement('option');
        emptyOpt.value = '';
        emptyOpt.textContent = `-- 不绑定账号 (${accounts.length} 个就绪) --`;
        select.appendChild(emptyOpt);
        accounts.forEach((a, i) => {
            const opt = document.createElement('option');
            opt.value = String(i);
            opt.textContent = a.account;
            opt.dataset.acc = a.account || '';
            opt.dataset.pwd = a.password || '';
            opt.dataset.twofa = a.twofa || '';
            select.appendChild(opt);
        });
    } catch (e) {
        console.error("加载 AI 对话账号失败:", e);
        renderEmptyAccountSelect(select, '-- 账号加载失败 --');
    }
}

async function loadDefaultAiSystemPrompt() {
    const systemPrompt = $("unitAiSystemPrompt");
    if (!systemPrompt) return;
    try {
        const res = await fetch("/api/tasks/prompt_templates");
        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
        const data = await res.json();
        const [defaultTemplate] = Array.isArray(data.templates) ? data.templates : [];
        if (defaultTemplate?.content) {
            systemPrompt.value = defaultTemplate.content;
        }
    } catch (e) {
        console.error("加载默认提示词失败:", e);
    }
}

function openUnitAiDialog(unit) {
    if (!unit) return;
    const modal = $("unitAiModal");
    if (modal) modal.style.display = "flex";
    loadAiDialogAccounts();
    const refreshBtn = $("unitAiAccountRefresh");
    if (refreshBtn) refreshBtn.onclick = loadAiDialogAccounts;

    const title = $("unitAiModalTitle");
    if (title) title.textContent = `AI 对话 - 云机 #${unit.parent_id}-${unit.cloud_id}`;

    const goalInput = $("unitAiGoal");
    if (goalInput) goalInput.value = "";

    const profileInput = $("unitAiProfile");
    if (profileInput) profileInput.value = "";

    // 重置勾选框为默认值
    document.querySelectorAll('input[name="aiState"]').forEach(cb => {
        cb.checked = ['home','account','password','two_factor'].includes(cb.value);
    });
    document.querySelectorAll('input[name="aiAction"]').forEach(cb => {
        cb.checked = true;
    });

    const bindingInput = $("unitAiBindingId");
    if (bindingInput) bindingInput.value = "";

    const systemPromptInput = $("unitAiSystemPrompt");
    if (systemPromptInput) systemPromptInput.value = "";
    loadDefaultAiSystemPrompt();

    const useVlm = $("unitAiUseVlm");
    if (useVlm) useVlm.checked = false;
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

    const expectedStateIds = Array.from(document.querySelectorAll('input[name="aiState"]:checked')).map(cb => cb.value);
    const allowedActions = Array.from(document.querySelectorAll('input[name="aiAction"]:checked')).map(cb => cb.value);
    const bindingId = String($("unitAiBindingId")?.value || "").trim();
    const systemPrompt = String($("unitAiSystemPrompt")?.value || "").trim();
    const profileName = String($("unitAiProfile")?.value || "").trim();
    const useVlm = $("unitAiUseVlm")?.checked || false;
    const maxStepsValue = Number.parseInt(String($("unitAiMaxSteps")?.value || "").trim(), 10);
    const stagnantLimitValue = Number.parseInt(String($("unitAiStagnantLimit")?.value || "").trim(), 10);

    const payload = {
        device_ip: currentUnitDetail.parent_ip,
        goal,
        expected_state_ids: expectedStateIds,
        allowed_actions: allowedActions,
        observation: {}
    };

    // 注入选中账号
    const aiAccountSelect = $("unitAiAccountSelect");
    if (aiAccountSelect && aiAccountSelect.value !== '') {
        const selectedOpt = aiAccountSelect.options[aiAccountSelect.selectedIndex];
        if (selectedOpt.dataset.acc) payload.acc = selectedOpt.dataset.acc;
        if (selectedOpt.dataset.pwd) payload.pwd = selectedOpt.dataset.pwd;
        if (selectedOpt.dataset.twofa) {
            payload.two_factor_code = selectedOpt.dataset.twofa;
            payload.fa2_secret = selectedOpt.dataset.twofa;
        }
    }

    if (bindingId) payload.observation.binding_id = bindingId;
    if (systemPrompt) payload.system_prompt = systemPrompt;
    if (profileName) payload._runtime_profile = profileName;
    if (useVlm) payload.fallback_modalities = ["vlm"];
    if (Number.isFinite(maxStepsValue) && maxStepsValue > 0) payload.max_steps = maxStepsValue;
    if (Number.isFinite(stagnantLimitValue) && stagnantLimitValue > 0) payload.stagnant_limit = stagnantLimitValue;
    const taskData = buildTaskRequest({
        task: "agent_executor",
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
