import { fetchJson } from '/static/js/utils/api.js';
import { toast } from '/static/js/ui/toast.js';
import { apiSubmitTask, buildTaskRequest } from '/static/js/features/task_service.js';

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

const accountModal = document.getElementById("accountModal");
const saveAccountBtn = document.getElementById("saveAccountBtn");
const editAcc = document.getElementById("editAcc");
const editPwd = document.getElementById("editPwd");
const edit2fa = document.getElementById("edit2fa");
const editToken = document.getElementById("editToken");
const editEmail = document.getElementById("editEmail");
const editEmailPwd = document.getElementById("editEmailPwd");
const editStatus = document.getElementById("editStatus");
const editErrorMsg = document.getElementById("editErrorMsg");

let currentEditingAccount = null;
let currentMapping = {};
let currentDelimiter = "----";

const STATUS_META = {
    ready: { text: '就绪', className: 'badge badge-ok', icon: '✅' },
    in_progress: { text: '执行中', className: 'badge', icon: '⏳' },
    bad_auth: { text: '密码错误', className: 'badge badge-warn', icon: '❌' },
    banned: { text: '封号', className: 'badge badge-warn', icon: '⛔' },
    '2fa_issue': { text: '2FA异常', className: 'badge badge-warn', icon: '❓' },
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
    const meta = STATUS_META[status] || { text: status, className: 'badge' };
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
    
    const resetBtn = document.getElementById("resetAccounts");
    if(resetBtn) resetBtn.onclick = resetAccountStatus;

    if(accountsInput) {
        accountsInput.oninput = handleInputDebounced;
    }

    document.querySelectorAll(".close-account-modal-btn").forEach(btn => {
        btn.onclick = () => accountModal.style.display = "none";
    });

    if (saveAccountBtn) {
        saveAccountBtn.onclick = saveAccount;
    }

    initImportAppSelector();
    loadAccounts();
}

async function updateAccountStatus(account, newStatus) {
    try {
        const r = await fetchJson("/api/data/accounts/status", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                account: account,
                status: newStatus
            }),
        });
        if (r.ok) {
            toast.success(`状态已更新为 ${STATUS_META[newStatus]?.text || newStatus}`);
            await loadAccounts();
        } else {
            toast.error("更新失败");
        }
    } catch (e) {
        toast.error("网络请求失败");
    }
}

async function saveAccount() {
    if (!currentEditingAccount) return;

    const newData = {
        account: editAcc.value,
        password: editPwd.value,
        twofa: edit2fa.value,
        token: editToken.value,
        email: editEmail.value,
        email_password: editEmailPwd.value,
        status: editStatus.value,
        error_msg: editErrorMsg.value
    };

    try {
        const r = await fetchJson("/api/data/accounts/update", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                old_account: currentEditingAccount.account,
                new_data: newData
            }),
        });

        if (r.ok) {
            toast.success("账号资料已保存");
            accountModal.style.display = "none";
            loadAccounts();
        } else {
            toast.error("更新失败: " + (r.data?.message || r.status));
        }
    } catch (e) {
        toast.error("网络请求失败");
    }
}

function openAccountModal(account) {
    currentEditingAccount = account;
    editAcc.value = account.account || "";
    editPwd.value = account.password || "";
    edit2fa.value = account.twofa || "";
    editToken.value = account.token || "";
    editEmail.value = account.email || "";
    editEmailPwd.value = account.email_password || "";
    editStatus.value = account.status || "ready";
    editErrorMsg.value = account.error_msg || "";
    
    accountModal.style.display = "flex";
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

async function initImportAppSelector() {
    const r = await fetchJson('/api/tasks/catalog/apps');
    if (!r.ok) return;
    const select = document.getElementById('accountImportAppId');
    if (select) {
        clearElement(select);
        (r.data.apps || []).forEach(app => {
            const opt = document.createElement('option');
            opt.value = app.id;
            opt.textContent = app.name;
            select.appendChild(opt);
        });
    }
}

async function resetAccountStatus() {
    if (!confirm("确定要将所有‘执行中’或‘异常’账号重置为‘就绪’状态吗？")) return;
    
    try {
        const r = await fetchJson("/api/data/accounts/reset", { method: "POST" });
        if (r.ok) {
            toast.success(r.data.message || "账号状态已恢复");
            await loadAccounts();
        } else {
            toast.error("恢复操作失败");
        }
    } catch (e) {
        toast.error("网络请求失败");
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
    table.style.cssText = 'width: 100%; border-collapse: collapse; font-size: 0.75rem; text-align: left;';

    const thead = document.createElement('thead');
    thead.style.cssText = 'position: sticky; top: 0; background: var(--bg-sidebar); z-index: 10;';
    const headerRow = document.createElement('tr');
    headerRow.append(
        makeTableCell('th', '账号', 'padding: 10px; border-bottom: 1px solid var(--border); width: 120px;'),
        makeTableCell('th', '当前状态', 'padding: 10px; border-bottom: 1px solid var(--border); width: 80px;'),
        makeTableCell('th', '快捷标记', 'padding: 10px; border-bottom: 1px solid var(--border); width: 140px;'),
        makeTableCell('th', '异常追踪', 'padding: 10px; border-bottom: 1px solid var(--border);'),
    );
    thead.appendChild(headerRow);

    const tbody = document.createElement('tbody');

    accounts.forEach(a => {
        const status = a.status || 'ready';
        if (status === 'ready') readyCount++;
        else if (status === 'in_progress') progressCount++;
        else errorCount++;

        const row = document.createElement('tr');
        row.style.cssText = `border-bottom: 1px solid var(--border); background: ${status === 'ready' ? 'transparent' : 'rgba(255,255,255,0.01)'}`;

        // 1. 账号列 (可点击编辑)
        const accountCell = document.createElement('td');
        accountCell.style.cssText = 'padding: 10px; font-weight: 600; color: var(--primary); cursor: pointer; text-decoration: underline;';
        accountCell.textContent = a.account || '';
        accountCell.onclick = () => openAccountModal(a);

        // 2. 状态列
        const statusCell = document.createElement('td');
        statusCell.style.cssText = 'padding: 10px;';
        statusCell.appendChild(buildStatusBadge(status));

        // 3. 快捷标记列
        const quickCell = document.createElement('td');
        quickCell.style.cssText = 'padding: 10px; display: flex; gap: 4px;';
        
        const createQuickBtn = (targetStatus, title) => {
            const btn = document.createElement('button');
            btn.className = 'btn btn-text p-1 text-xs';
            btn.innerHTML = STATUS_META[targetStatus].icon;
            btn.title = `标记为${STATUS_META[targetStatus].text}`;
            btn.onclick = (e) => {
                e.stopPropagation();
                updateAccountStatus(a.account, targetStatus);
            };
            if (status === targetStatus) {
                btn.style.opacity = '1';
                btn.style.background = 'var(--bg-sidebar)';
                btn.style.borderRadius = '4px';
            } else {
                btn.style.opacity = '0.3';
            }
            return btn;
        };

        quickCell.append(
            createQuickBtn('ready', '就绪'),
            createQuickBtn('bad_auth', '密错'),
            createQuickBtn('banned', '封号'),
            createQuickBtn('2fa_issue', '2FA异常')
        );

        // 4. 异常详情列
        const errorCell = makeTableCell('td', a.error_msg || '-', 'padding: 10px; color: var(--error); font-size: 0.7rem; max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;');
        errorCell.title = a.error_msg || '';

        row.append(accountCell, statusCell, quickCell, errorCell);
        tbody.appendChild(row);
    });

    table.append(thead, tbody);
    wrapper.appendChild(table);
    accountsInventoryList.appendChild(wrapper);
    updateStats(readyCount, progressCount, errorCount);
}

function updateStats(ready, progress, error) {
    if(statReady) statReady.textContent = ready;
    if(statProgress) statProgress.textContent = progress;
    if(statError) statError.textContent = error;
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

    const appId = document.getElementById("accountImportAppId")?.value || "default";

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
                mapping: currentMapping,
                app_id: appId
            }),
        });

        if (r.ok) {
            toast.success(`成功导入 ${r.data.valid} 条账号，数据已同步`);
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

    const plugin = prompt("请输入要派发的插件名称（如 device_reboot）", (localStorage.getItem("bulkDispatchPlugin") || ""));
    if (!plugin || !plugin.trim()) return;
    localStorage.setItem("bulkDispatchPlugin", plugin.trim());

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
            task: plugin.trim(),
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

    toast.success(`派发完成：${dispatched} 台机器已开工！`);
    bulkDispatchBtn.disabled = false;
    bulkDispatchBtn.textContent = '启动全局指派策略';
    setTimeout(loadAccounts, 2000);
}
