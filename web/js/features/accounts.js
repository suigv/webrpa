import { fetchJson } from '../utils/api.js';
import { toast } from '../ui/toast.js';
import { apiSubmitTask, buildTaskRequest } from './task_service.js';

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

const STATUS_META = {
    ready: { text: '就绪', className: 'badge badge-ok' },
    in_progress: { text: '执行中', className: 'badge' },
    bad_auth: { text: '密码错误', className: 'badge badge-warn' },
    banned: { text: '封号', className: 'badge badge-warn' },
    '2fa_issue': { text: '2FA异常', className: 'badge badge-warn' },
};

function clearElement(element) {
    if (element) {
        element.replaceChildren();
    }
}

function makeTableCell(tagName, text, styleText = '') {
    const cell = document.createElement(tagName);
    cell.textContent = text;
    if (styleText) {
        cell.style.cssText = styleText;
    }
    return cell;
}

function buildStatusBadge(status) {
    const meta = STATUS_META[status] || null;
    if (!meta) {
        return document.createTextNode(status);
    }
    const badge = document.createElement('span');
    badge.className = meta.className;
    badge.textContent = meta.text;
    if (status === 'in_progress') {
        badge.style.background = 'var(--primary-soft)';
        badge.style.color = 'var(--primary)';
    }
    return badge;
}

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
    clearElement(accountsInventoryList);

    if (accounts.length === 0) {
        const empty = document.createElement('div');
        empty.textContent = '池子是空的';
        empty.style.cssText = 'padding:40px; text-align:center; color:var(--text-muted);';
        accountsInventoryList.appendChild(empty);
        updateStats(0, 0, 0);
        return;
    }

    let readyCount = 0;
    let progressCount = 0;
    let errorCount = 0;

    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'overflow-x:auto;';

    const table = document.createElement('table');
    table.style.cssText = 'width: 100%; border-collapse: collapse; font-size: 0.8rem; text-align: left;';

    const thead = document.createElement('thead');
    thead.style.cssText = 'position: sticky; top: 0; background: var(--bg-sidebar); z-index: 10;';
    const headerRow = document.createElement('tr');
    headerRow.append(
        makeTableCell('th', '账号', 'padding: 12px; border-bottom: 1px solid var(--border);'),
        makeTableCell('th', '状态', 'padding: 12px; border-bottom: 1px solid var(--border);'),
        makeTableCell('th', '资产详情', 'padding: 12px; border-bottom: 1px solid var(--border);'),
    );
    thead.appendChild(headerRow);

    const tbody = document.createElement('tbody');

    accounts.forEach(a => {
        const status = a.status || 'ready';
        if (status === 'ready') readyCount++;
        else if (status === 'in_progress') progressCount++;
        else errorCount++;

        const assetTags = [];
        if (a.token) assetTags.push('Token');
        if (a.twofa) assetTags.push('2FA');
        if (a.email) assetTags.push('Email');

        const row = document.createElement('tr');
        row.style.cssText = `border-bottom: 1px solid var(--border); background: ${status === 'ready' ? 'transparent' : 'rgba(255,255,255,0.02)'}`;

        const accountCell = makeTableCell('td', a.account || '', 'padding: 12px; font-weight: 500;');

        const statusCell = document.createElement('td');
        statusCell.style.cssText = 'padding: 12px;';
        statusCell.appendChild(buildStatusBadge(status));

        const assetsCell = makeTableCell('td', assetTags.join(' · ') || '仅账密', 'padding: 12px; color: var(--text-muted); font-size: 0.7rem;');

        row.append(accountCell, statusCell, assetsCell);
        tbody.appendChild(row);
    });

    table.append(thead, tbody);
    wrapper.appendChild(table);
    accountsInventoryList.appendChild(wrapper);
    updateStats(readyCount, progressCount, errorCount);
}

function updateStats(ready, progress, error) {
    if(statReady) statReady.textContent = `就绪: ${ready}`;
    if(statProgress) statProgress.textContent = `执行中: ${progress}`;
    if(statError) statError.textContent = `异常: ${error}`;
}

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
        clearElement(accountsPreview);
        return;
    }
    currentDelimiter = detectDelimiter(text);
    const lines = text.split('\n').filter(l => l.trim()).slice(0, 5);
    const firstRowParts = lines[0].split(currentDelimiter);

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

    clearElement(accountsPreview);

    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'overflow-x:auto; border:1px solid var(--border); border-radius:4px; margin-top:10px;';

    const table = document.createElement('table');
    table.style.cssText = 'width:100%; border-collapse:collapse; font-size:0.7rem;';

    const thead = document.createElement('thead');
    const headRow = document.createElement('tr');
    headRow.style.background = 'var(--bg-sidebar)';

    const options = [["account","账号"],["password","密码"],["twofa","2FA"],["token","Token"],["email","邮箱"],["email_password","邮箱密"],["ignore","忽略"]];

    firstRowParts.forEach((_, i) => {
        const th = document.createElement('th');
        th.style.cssText = 'padding:4px; border:1px solid var(--border)';

        const select = document.createElement('select');
        select.dataset.col = String(i);
        select.className = 'm-sel';
        select.style.cssText = 'background:transparent; color:var(--primary); border:none; font-size:0.65rem; width:100%';

        options.forEach(([value, label]) => {
            const option = document.createElement('option');
            option.value = value;
            option.textContent = label;
            option.selected = currentMapping[i] === value;
            select.appendChild(option);
        });

        th.appendChild(select);
        headRow.appendChild(th);
    });
    thead.appendChild(headRow);

    const tbody = document.createElement('tbody');
    lines.forEach(line => {
        const row = document.createElement('tr');
        line.split(currentDelimiter).forEach(part => {
            const cell = document.createElement('td');
            cell.textContent = part;
            cell.style.cssText = 'padding:4px; border:1px solid var(--border); color:var(--text-muted); max-width:80px; overflow:hidden;';
            row.appendChild(cell);
        });
        tbody.appendChild(row);
    });

    table.append(thead, tbody);
    wrapper.appendChild(table);
    accountsPreview.appendChild(wrapper);

    accountsPreview.querySelectorAll('.m-sel').forEach(select => {
        select.onchange = (e) => currentMapping[e.target.dataset.col] = e.target.value;
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
            headers: { "Content-Type": "application/json" },
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
            clearElement(accountsPreview);
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
    bulkDispatchBtn.textContent = '批量派发中...';

    let dispatched = 0;
    for (const u of onlineUnits) {
        const accountRes = await fetchJson("/api/data/accounts/pop", { method: "POST" });
        if (!accountRes.ok || !accountRes.data || accountRes.data.status !== "ok" || !accountRes.data.account) {
            toast.warn("账号池耗尽，停止后续派发");
            break;
        }
        const account = accountRes.data.account;
        const twofa = account.twofa || "";
        const taskData = buildTaskRequest({
            task: 'x_mobile_login',
            payload: {
                device_ip: u.deviceIp,
                acc: account.account || '',
                pwd: account.password || '',
                two_factor_code: twofa,
                fa2_secret: twofa,
                status_hint: 'runtime',
            },
            targets: [{ device_id: u.dId, cloud_id: u.cId }],
        });
        const res = await apiSubmitTask(taskData, { notify: false, log: false });
        if (res.ok) dispatched++;
    }

    toast.success(`任务派发成功: ${dispatched} 台机器已开工`);
    bulkDispatchBtn.disabled = false;
    bulkDispatchBtn.textContent = '启动全局指派策略';
    setTimeout(loadAccounts, 2000);
}
