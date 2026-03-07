import { fetchJson } from '../utils/api.js';
import { toast } from '../ui/toast.js';

const accountsInput = document.getElementById("accountsInput");
const accountsPreview = document.getElementById("accountsPreview");
const accountsInventoryList = document.getElementById("accountsInventoryList");
const loadBtn = document.getElementById("loadAccounts");
const importOverwriteBtn = document.getElementById("importAccountsOverwrite");
const importAppendBtn = document.getElementById("importAccountsAppend");
const bulkDispatchBtn = document.getElementById("bulkDispatchBtn");

const statReady = document.getElementById("statReady");
const statProgress = document.getElementById("statProgress");
const statError = document.getElementById("statError");

let currentMapping = {}; 
let currentDelimiter = "----";

export function initAccounts() {
    if(loadBtn) loadBtn.onclick = loadAccounts;
    if(importOverwriteBtn) importOverwriteBtn.onclick = () => {
        if(confirm("确定要清空现有账号池并重新导入吗？")) importAccounts(true);
    };
    if(importAppendBtn) importAppendBtn.onclick = () => importAccounts(false);
    if(bulkDispatchBtn) bulkDispatchBtn.onclick = bulkDispatch;
    
    if(accountsInput) {
        accountsInput.oninput = handleInputDebounced;
    }
    
    loadAccounts();
}

let inputTimeout;
function handleInputDebounced() {
    clearTimeout(inputTimeout);
    inputTimeout = setTimeout(refreshImportPreview, 300);
}

// --- 核心逻辑：加载并渲染已有库存 ---
export async function loadAccounts() {
    try {
        const r = await fetchJson("/api/data/accounts/parsed");
        if (r.ok && r.data && r.data.accounts) {
            renderInventory(r.data.accounts);
        }
    } catch (e) {
        console.error("Failed to load inventory:", e);
    }
}

function renderInventory(accounts) {
    if (!accountsInventoryList) return;
    
    if (accounts.length === 0) {
        accountsInventoryList.innerHTML = '<div style="padding:40px; text-align:center; color:var(--text-muted);">池子是空的</div>';
        updateStats(0, 0, 0);
        return;
    }

    let readyCount = 0, progressCount = 0, errorCount = 0;
    let html = `<table style="width: 100%; border-collapse: collapse; font-size: 0.8rem; text-align: left;">`;
    html += `<thead style="position: sticky; top: 0; background: var(--bg-sidebar); z-index: 10;"><tr>`;
    html += `<th style="padding: 12px; border-bottom: 1px solid var(--border);">账号</th>`;
    html += `<th style="padding: 12px; border-bottom: 1px solid var(--border);">状态</th>`;
    html += `<th style="padding: 12px; border-bottom: 1px solid var(--border);">资产详情</th>`;
    html += `</tr></thead><tbody>`;

    accounts.forEach(a => {
        const status = a.status || "ready";
        if (status === "ready") readyCount++;
        else if (status === "in_progress") progressCount++;
        else errorCount++;

        const statusLabel = {
            ready: '<span class="badge badge-ok">就绪</span>',
            in_progress: '<span class="badge" style="background:var(--primary-soft); color:var(--primary)">执行中</span>',
            bad_auth: '<span class="badge badge-warn">密码错误</span>',
            banned: '<span class="badge badge-warn">封号</span>',
            "2fa_issue": '<span class="badge badge-warn">2FA异常</span>'
        }[status] || status;

        const assetTags = [];
        if (a.token) assetTags.push("Token");
        if (a.twofa) assetTags.push("2FA");
        if (a.email) assetTags.push("Email");

        html += `<tr style="border-bottom: 1px solid var(--border); background: ${status === 'ready' ? 'transparent' : 'rgba(255,255,255,0.02)'}">`;
        html += `<td style="padding: 12px; font-weight: 500;">${a.account}</td>`;
        html += `<td style="padding: 12px;">${statusLabel}</td>`;
        html += `<td style="padding: 12px; color: var(--text-muted); font-size: 0.7rem;">${assetTags.join(" · ") || "仅账密"}</td>`;
        html += `</tr>`;
    });

    html += `</tbody></table>`;
    accountsInventoryList.innerHTML = html;
    updateStats(readyCount, progressCount, errorCount);
}

function updateStats(ready, progress, error) {
    if(statReady) statReady.textContent = `就绪: ${ready}`;
    if(statProgress) statProgress.textContent = `执行中: ${progress}`;
    if(statError) statError.textContent = `异常: ${error}`;
}

// --- 导入预览逻辑 (左侧面板恢复表格视图) ---
function detectDelimiter(text) {
    const candidates = ["----", "|", "\t", ","];
    let best = "----";
    let maxCount = -1;
    const firstLine = text.split('\n')[0] || "";
    candidates.forEach(c => {
        let count = firstLine.split(c).length;
        if (count > 1 && count > maxCount) { maxCount = count; best = c; }
    });
    return best;
}

function refreshImportPreview() {
    const text = accountsInput.value.trim();
    if (!text) {
        accountsPreview.innerHTML = "";
        return;
    }
    currentDelimiter = detectDelimiter(text);
    const lines = text.split('\n').filter(l => l.trim()).slice(0, 5);
    const firstRowParts = lines[0].split(currentDelimiter);
    
    // 初始化智能映射逻辑
    currentMapping = {};
    firstRowParts.forEach((p, i) => {
        const val = p.trim();
        if (i === 0) currentMapping[i] = "account";
        else if (i === 1) currentMapping[i] = "password";
        else if (val.includes("@")) currentMapping[i] = "email";
        else if (val.length > 40) currentMapping[i] = "token";
        else if (/^[A-Z2-7]{16,32}$/.test(val)) currentMapping[i] = "twofa";
        else if (i === 3) currentMapping[i] = "email_password";
        else currentMapping[i] = "ignore";
    });

    let html = `<div style="overflow-x:auto; border:1px solid var(--border); border-radius:4px; margin-top:10px;">`;
    html += `<table style="width:100%; border-collapse:collapse; font-size:0.7rem;"><thead><tr style="background:var(--bg-sidebar)">`;
    
    const options = [["account","账号"],["password","密码"],["twofa","2FA"],["token","Token"],["email","邮箱"],["email_password","邮箱密"],["ignore","忽略"]];
    
    firstRowParts.forEach((_, i) => {
        let sel = `<select data-col="${i}" class="m-sel" style="background:transparent; color:var(--primary); border:none; font-size:0.65rem; width:100%">`;
        options.forEach(([v, l]) => { sel += `<option value="${v}" ${currentMapping[i]===v?'selected':''}>${l}</option>`; });
        sel += `</select>`;
        html += `<th style="padding:4px; border:1px solid var(--border)">${sel}</th>`;
    });
    html += `</tr></thead><tbody>`;
    
    lines.forEach(line => {
        html += `<tr>`;
        line.split(currentDelimiter).forEach(p => {
            html += `<td style="padding:4px; border:1px solid var(--border); color:var(--text-muted); max-width:80px; overflow:hidden;">${p}</td>`;
        });
        html += `</tr>`;
    });
    html += `</tbody></table></div>`;
    
    accountsPreview.innerHTML = html;
    
    accountsPreview.querySelectorAll(".m-sel").forEach(s => {
        s.onchange = (e) => currentMapping[e.target.dataset.col] = e.target.value;
    });
}

async function importAccounts(overwrite) {
    const text = accountsInput.value.trim();
    if(!text) return toast.warn("请先输入数据");
    
    importOverwriteBtn.disabled = true;
    const originalText = importOverwriteBtn.textContent;
    importOverwriteBtn.textContent = "正在处理...";
    
    try {
        const r = await fetchJson("/api/data/accounts/import", {
            method: "POST",
            headers: { "Content-Type": "application/json" }, // 补全缺失的 Header
            body: JSON.stringify({ 
                content: text, 
                overwrite, 
                delimiter: currentDelimiter, 
                mapping: currentMapping 
            }),
        });

        if (r.ok) {
            toast.success(`成功导入 ${r.data.valid} 条账号资产`);
            accountsInput.value = "";
            accountsPreview.innerHTML = "";
            await loadAccounts();
        } else {
            toast.error(`导入失败: ${r.data.detail || r.status}`);
        }
    } catch (e) {
        toast.error("网络请求异常");
    } finally {
        importOverwriteBtn.disabled = false;
        importOverwriteBtn.textContent = originalText;
    }
}

async function bulkDispatch() {
    const r = await fetchJson("/api/devices/");
    if (!r.ok) return;
    
    const onlineUnits = [];
    r.data.forEach(d => {
        (d.cloud_machines || []).forEach(u => {
            if (u.availability_state === "available") onlineUnits.push({ dId: d.device_id, cId: u.cloud_id, deviceIp: d.ip });
        });
    });

    if (onlineUnits.length === 0) return toast.warn("当前无在线云机");
    
    bulkDispatchBtn.disabled = true;
    bulkDispatchBtn.innerHTML = '<span class="loading-spinner"></span> 批量派发中...';

    let dispatched = 0;
    for (const u of onlineUnits) {
        const accountRes = await fetchJson("/api/data/accounts/pop", { method: "POST" });
        if (!accountRes.ok || !accountRes.data || accountRes.data.status !== "ok" || !accountRes.data.account) {
            toast.warn("账号池耗尽，停止后续派发");
            break;
        }
        const account = accountRes.data.account;
        const twofa = account.twofa || "";
        const res = await fetchJson("/api/tasks/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                task: "x_mobile_login",
                payload: {
                    device_ip: u.deviceIp,
                    acc: account.account || "",
                    pwd: account.password || "",
                    two_factor_code: twofa,
                    fa2_secret: twofa,
                    status_hint: "runtime",
                },
                targets: [{ device_id: u.dId, cloud_id: u.cId }]
            }),
        });
        if (res.ok) dispatched++;
    }
    
    toast.success(`任务派发成功: ${dispatched} 台机器已开工`);
    bulkDispatchBtn.disabled = false;
    bulkDispatchBtn.textContent = "🚀 启动集群指派 (使用就绪账号)";
    setTimeout(loadAccounts, 2000);
}
