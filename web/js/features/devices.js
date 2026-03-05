import { fetchJson } from '../utils/api.js';
import { store } from '../state/store.js';
import { toast } from '../ui/toast.js';

const devicesList = document.getElementById("devicesList");
const refreshBtn = document.getElementById("refreshDevices");
const discoverBtn = document.createElement("button"); // Dynamically add or find if exists

export function initDevices() {
    if (refreshBtn) {
        refreshBtn.addEventListener("click", loadDevices);
        
        // Add Discover Button next to Refresh if not exists
        discoverBtn.textContent = "扫描设备";
        discoverBtn.className = "btn";
        discoverBtn.style.marginLeft = "10px";
        discoverBtn.addEventListener("click", discoverDevices);
        
        if(refreshBtn.parentNode) {
            refreshBtn.parentNode.insertBefore(discoverBtn, refreshBtn.nextSibling);
        }
    }
    // Subscribe to store changes if needed, or just load directly
    loadDevices();
}

export async function loadDevices() {
    if(refreshBtn) refreshBtn.disabled = true;
    
    const r = await fetchJson("/api/devices/");
    if (r.ok) {
        store.setState({ devices: r.data });
        renderDevices(r.data);
    } else {
        toast.error("加载设备列表失败");
    }
    
    if(refreshBtn) refreshBtn.disabled = false;
}

async function discoverDevices() {
    discoverBtn.disabled = true;
    discoverBtn.innerHTML = '<span class="loading-spinner"></span> 扫描中...';
    
    const r = await fetchJson("/api/devices/discover", { method: "POST" });
    if(r.ok) {
        toast.success(`扫描完成: 发现 ${r.data.count} 台设备`);
        await loadDevices();
    } else {
        toast.error("扫描失败");
    }
    
    discoverBtn.disabled = false;
    discoverBtn.textContent = "扫描设备";
}

function renderDevices(items) {
    devicesList.innerHTML = "";
    if (!Array.isArray(items) || items.length === 0) {
        devicesList.innerHTML = '<div class="device-item"><strong>暂无设备</strong></div>';
        return;
    }

    items.forEach((d) => {
        const clouds = Array.isArray(d.cloud_machines) ? d.cloud_machines : [];
        const firstCloud = clouds[0] || null;
        
        const node = document.createElement("div");
        node.className = "device-item";
        
        // Enhance: Add status indicator color
        const displayStatus = '待命';
        const statusColor = 'var(--ok)';
        
        const sdkRole = mapPortRole(d.sdk_port_role || 'device_control_api');
        const apiRole = firstCloud ? mapPortRole(firstCloud.api_port_role || 'cloud_api') : '无';
        const rpaRole = firstCloud ? mapPortRole(firstCloud.rpa_port_role || 'mytrpc_control') : '无';
        const aiName = mapAiType(d.ai_type);

        node.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <strong style="color:${statusColor}">#${d.device_id} • ${displayStatus}</strong>
            </div>
            <div class="device-meta">IP: ${d.ip}</div>
            <div class="device-meta">设备控制端口: ${d.sdk_port}（${sdkRole}）</div>
            <div class="device-meta">云端: ${clouds.length}</div>
            <div class="device-meta">云机1接口端口: ${firstCloud ? `${firstCloud.api_port}（${apiRole}）` : "无"}</div>
            <div class="device-meta">云机1操作端口: ${firstCloud ? `${firstCloud.rpa_port}（${rpaRole}）` : "无"}</div>
            <div class="device-meta">模型类型: ${aiName}</div>
        `;
        devicesList.appendChild(node);
    });
    
    // No manual connect/disconnect actions: scanned devices stay ready.
}

function mapPortRole(role) {
    const key = String(role || '').toLowerCase();
    if (key === 'device_control_api') return '设备控制接口';
    if (key === 'cloud_api') return '云机接口';
    if (key === 'mytrpc_control') return '云机操作通道';
    return '未命名接口';
}

function mapAiType(aiType) {
    const key = String(aiType || '').toLowerCase();
    if (key === 'volc') return '火山';
    if (key === 'part_time') return '兼职';
    return '未知';
}
