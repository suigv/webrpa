import { fetchJson } from '../utils/api.js';
import { toast } from '../ui/toast.js';

const devicesList = document.getElementById("devicesList");
const selectionBar = document.getElementById("selectionBar");
const selectedCountEl = document.getElementById("selectedCount");
const unitDetailView = document.getElementById("unitDetailView");
const tabMain = document.getElementById("tab-main");
const viewTitle = document.getElementById("viewTitle");

const FIELD_LABEL_MAP = {
    source_key: '数据源', username: '用户', display_name: '昵称',
    device_ip: '设备IP', acc: '账号', pwd: '密码',
    fa2_secret: '2FA密钥', name: '任务名', package: '包名',
    status_hint: '备注', credentials_ref: '凭据', headless: '无界面',
    two_factor_code: '2FA码', timeout_seconds: '超时', login_url: '登录地址',
    account: '账号', password: '密码', target_url: '目标地址',
    keyword: '关键字', comment_text: '评论', scrape_source: '采集模式',
    blogger_id: '博主ID',
};

const FIELD_VALUE_MAP = {
    scrape_profile: 'PROFILE', demo_blogger: 'DEMO',
    'Demo Blogger': 'DEMO', success: 'SUCCESS', true: 'YES', false: 'NO',
};

function localizeValue(val) {
    if (val === null || val === undefined) return "";
    const s = String(val);
    if (FIELD_VALUE_MAP[s]) return FIELD_VALUE_MAP[s];
    if (s.startsWith("<") && s.endsWith(">")) {
        const key = s.slice(1, -1);
        return `请输入 ${FIELD_LABEL_MAP[key] || key}`;
    }
    return s;
}

let selectedUnits = new Set(); 
let currentCatalog = [];
let currentUnitsById = new Map();

export function initDevices() {
    const clearBtn = document.getElementById("clearSelection");
    const closeBtn = document.getElementById("closeDetail");
    const bulkBtn = document.getElementById("bulkRunBtn");
    const scanBtn = document.getElementById("scanDevices");

    if (clearBtn) clearBtn.onclick = clearSelection;
    if (closeBtn) closeBtn.onclick = closeDetail;
    if (bulkBtn) bulkBtn.onclick = runBulkTasks;
    if (scanBtn) scanBtn.onclick = scanDevices;

    const unitPluginSelect = document.getElementById("unitPluginSelect");
    if (unitPluginSelect) unitPluginSelect.onchange = renderUnitPluginFields;

    const showMoreBtn = document.getElementById('showMoreUnitFields');
    if (showMoreBtn) {
        showMoreBtn.onclick = () => {
            const fields = document.querySelectorAll('#unitPluginFields .field-optional');
            const isHidden = fields[0]?.style.display === 'none';
            fields.forEach(el => el.style.display = isHidden ? 'flex' : 'none');
            showMoreBtn.textContent = isHidden ? '收起可选参数' : '显示可选参数';
        };
    }
    
    loadDevices();
    loadPluginCatalog(); 
    setInterval(loadDevices, 5000); 
}

async function loadPluginCatalog() {
    const r = await fetchJson("/api/tasks/catalog");
    if (!r.ok) return;
    currentCatalog = r.data.tasks || [];
    const select = document.getElementById("bulkPluginSelect");
    const unitSelect = document.getElementById("unitPluginSelect");
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
    const btn = document.getElementById("scanDevices");
    if (!btn) return;
    btn.disabled = true;
    btn.textContent = "正在扫描...";
    toast.info("已在后台启动局域网发现...");
    try {
        const r = await fetchJson("/api/devices/discover", { method: "POST" });
        if (r.ok) {
            toast.success("扫描指令已下发，设备将陆续上线");
            // 启动高频同步，以便设备上线时立即展示
            let ticks = 0;
            const fastSync = setInterval(async () => {
                await loadDevices();
                ticks++;
                if (ticks >= 4) clearInterval(fastSync); // 持续 8 秒高频同步
            }, 2000);
        } else {
            toast.error(`发现失败: ${r.status}`);
        }
    } catch (e) { 
        toast.error("扫描请求异常"); 
    } finally { 
        setTimeout(() => { 
            if(btn) {
                btn.disabled = false; 
                btn.textContent = "发现设备"; 
            }
        }, 3000); 
    }
}

function renderUnits(devices) {
    if (!devicesList || unitDetailView.style.display === "block") return;
    const onlineUnits = [];
    const offlineUnits = [];
    currentUnitsById = new Map();
    devices.forEach(d => {
        (d.cloud_machines || []).forEach(u => {
            const unit = { ...u, parent_ip: d.ip, parent_id: d.device_id };
            currentUnitsById.set(`${d.device_id}-${u.cloud_id}`, unit);
            if (u.availability_state === "available") onlineUnits.push(unit);
            else offlineUnits.push(unit);
        });
    });
    devicesList.innerHTML = "";
    if (onlineUnits.length > 0) {
        renderHeader(`可用节点 (${onlineUnits.length})`);
        onlineUnits.forEach(u => renderUnitCard(u));
    }
    if (offlineUnits.length > 0) {
        renderHeader(`离线节点 (${offlineUnits.length})`, true);
        offlineUnits.forEach(u => renderUnitCard(u));
    }
}

function renderHeader(title, isMuted = false) {
    const h = document.createElement("div");
    h.style.cssText = `grid-column: 1 / -1; margin: 8px 0; color: ${isMuted ? 'var(--text-muted)' : 'var(--text-main)'}; font-size: 13px; font-weight: 600; border-bottom: 1px solid var(--border); padding-bottom: 8px;`;
    h.textContent = title;
    devicesList.appendChild(h);
}

function renderUnitCard(u) {
    const unitId = `${u.parent_id}-${u.cloud_id}`;
    const isOnline = u.availability_state === "available";
    const card = document.createElement("div");
    card.className = `device-card ${selectedUnits.has(unitId) ? 'selected' : ''}`;
    card.style.opacity = isOnline ? "1" : "0.5";
    card.innerHTML = `
        <div class="device-card-header">
            <span class="device-id">云机 #${unitId}</span>
            <label class="checkbox-container" style="padding-left:18px; margin:0;" onclick="event.stopPropagation()">
                <input type="checkbox" ${selectedUnits.has(unitId) ? 'checked' : ''} ${!isOnline ? 'disabled' : ''} class="unit-checkbox">
                <span class="checkmark" style="top:0;"></span>
            </label>
        </div>
        <div class="device-meta">
            <div><span class="text-muted">路由:</span> ${u.parent_ip}:${u.rpa_port}</div>
            <div style="color:${isOnline ? 'var(--success)' : 'var(--error)'}; font-weight: 500;">
                ${isOnline ? '就绪' : '连接中断'}
            </div>
        </div>
    `;
    const cb = card.querySelector(".unit-checkbox");
    cb.onchange = (e) => { toggleSelection(unitId, cb.checked); };
    card.onclick = () => { if (isOnline) openUnitDetail(u); else toast.warn("该节点当前无法连接"); };
    devicesList.appendChild(card);
}

function toggleSelection(id, check) {
    if (check) selectedUnits.add(id); else selectedUnits.delete(id);
    updateBar();
}

function updateBar() {
    selectedCountEl.textContent = selectedUnits.size;
    selectionBar.style.display = selectedUnits.size > 0 ? "flex" : "none";
}

function clearSelection() {
    selectedUnits.clear(); updateBar(); loadDevices();
}

function renderUnitPluginFields() {
    const select = document.getElementById("unitPluginSelect");
    const container = document.getElementById("unitPluginFields");
    if (!select || !container) return;
    const taskName = select.value;
    const task = currentCatalog.find(t => t.task === taskName);
    const payload = (task && task.example_payload) ? task.example_payload : {};
    const requiredKeys = (task && task.required) ? task.required : [];
    container.innerHTML = "";
    Object.keys(payload).forEach(key => {
        const isReq = requiredKeys.includes(key);
        const val = localizeValue(payload[key]);
        const div = document.createElement("div");
        div.className = `form-group ${isReq ? '' : 'field-optional'}`;
        div.style.display = isReq ? "flex" : "none";
        div.innerHTML = `<label>${FIELD_LABEL_MAP[key] || key}${isReq ? ' <span class="text-error">*</span>' : ''}</label><input data-payload-key="${key}" type="text" value="${val}">`;
        container.appendChild(div);
    });
}

function openUnitDetail(unit) {
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    unitDetailView.style.display = "flex";
    document.getElementById("detailUnitTitle").textContent = `云机 #${unit.parent_id}-${unit.cloud_id}`;
    renderUnitPluginFields();
    document.getElementById("submitSingleTask").onclick = () => submitUnitTask(unit);
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function closeDetail() {
    unitDetailView.style.display = "none";
    const tabMain = document.getElementById("tab-main");
    if(tabMain) tabMain.classList.add("active");
    loadDevices();
}

async function submitUnitTask(unit) {
    const select = document.getElementById("unitPluginSelect");
    const fields = document.querySelectorAll("#unitPluginFields [data-payload-key]");
    const p = {}; fields.forEach(i => { p[i.dataset.payloadKey] = i.value; });
    const body = { task: select.value, payload: p, targets: [{ device_id: unit.parent_id, cloud_id: unit.cloud_id }] };
    const r = await fetchJson("/api/tasks/", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (r.ok) toast.success("指令已送达执行队列"); else toast.error("指令下发失败");
}

async function runBulkTasks() {
    const plugin = document.getElementById("bulkPluginSelect").value;
    const count = selectedUnits.size;
    if(!confirm(`即将对选中的 ${count} 个节点执行该操作，是否继续？`)) return;
    for (const id of selectedUnits) {
        const [dId, cId] = id.split("-");
        const body = { task: plugin, payload: {}, targets: [{ device_id: parseInt(dId), cloud_id: parseInt(cId) }] };
        await fetchJson("/api/tasks/", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    }
    toast.success("集群任务分发完成");
    clearSelection();
}
