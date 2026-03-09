import { fetchJson } from '../utils/api.js';
import { toast } from '../ui/toast.js';
import { renderCommonFields } from '../utils/ui_utils.js';
import { sysLog } from './logs.js';
import { getTaskCatalog, apiSubmitTask } from './task_service.js';

const $ = (id) => document.getElementById(id);

let selectedUnits = new Set(); 
let currentCatalog = [];
let currentUnitsById = new Map();

export function initDevices() {
    const clearBtn = $("clearSelection");
    const closeBtn = $("closeDetail");
    const bulkBtn = $("bulkRunBtn");
    const scanBtn = $("scanDevices");

    if (clearBtn) clearBtn.onclick = clearSelection;
    if (closeBtn) closeBtn.onclick = closeDetail;
    if (bulkBtn) bulkBtn.onclick = runBulkTasks;
    if (scanBtn) scanBtn.onclick = scanDevices;

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
    select.innerHTML = "";
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
    
    list.innerHTML = "";
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

    card.innerHTML = `
        <div class="device-card-header">
            <span class="device-id">云机 #${unitId}</span>
            <span class="badge badge-sm">${aiType}</span>
            <label class="checkbox-container" style="padding-left:18px; margin:0;" onclick="event.stopPropagation()">
                <input type="checkbox" ${selectedUnits.has(unitId) ? 'checked' : ''} ${!isOnline ? 'disabled' : ''} class="unit-checkbox">
                <span class="checkmark" style="top:0;"></span>
            </label>
        </div>
        <div class="device-meta">
            <div><span class="text-muted">型号:</span> <span style="color:var(--text-main)">${modelName}</span></div>
            <div><span class="text-muted">路由:</span> ${u.parent_ip}:${u.rpa_port}</div>
            <div style="color:${isOnline ? 'var(--success)' : 'var(--error)'}; font-weight: 500;">
                ${isOnline ? '就绪' : '连接中断'}
            </div>
        </div>
    `;
    const cb = card.querySelector(".unit-checkbox");
    if(cb) cb.onchange = (e) => { toggleSelection(unitId, cb.checked); };
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
    renderUnitPluginFields();
    const btn = $("submitSingleTask");
    if(btn) btn.onclick = () => submitUnitTask(unit);
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function closeDetail() {
    const view = $("unitDetailView");
    if(view) view.style.display = "none";
    const tabMain = $("tab-main");
    if(tabMain) tabMain.classList.add("active");
    loadDevices();
}

async function submitUnitTask(unit) {
    const select = $("unitPluginSelect");
    const container = $("unitPluginFields");
    if(!select || !container) return;

    const fields = container.querySelectorAll("[data-payload-key]");
    const p = {}; fields.forEach(i => { p[i.dataset.payloadKey] = i.value; });

    const taskData = { 
        task: select.value, 
        payload: p, 
        targets: [{ device_id: unit.parent_id, cloud_id: unit.cloud_id }],
        priority: Number($("unitTaskPriority")?.value || 50),
        max_retries: Number($("unitTaskMaxRetries")?.value || 0),
        run_at: $("unitTaskRunAt")?.value || null
    };
    
    await apiSubmitTask(taskData);
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
        const taskData = { 
            task: plugin, 
            payload: {}, 
            targets: [{ device_id: parseInt(dId), cloud_id: parseInt(cId) }] 
        };
        await apiSubmitTask(taskData);
    }
    toast.success("集群任务分发完成");
    clearSelection();
}
