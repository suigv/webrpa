import { fetchJson } from '../utils/api.js';
import { toast } from '../ui/toast.js';

const accountsInput = document.getElementById("accountsInput");
const accountsPreview = document.getElementById("accountsPreview");
const accountsMsg = document.getElementById("accountsMsg");
const loadBtn = document.getElementById("loadAccounts");
const importOverwriteBtn = document.getElementById("importAccountsOverwrite");
const importAppendBtn = document.getElementById("importAccountsAppend");

export function initAccounts() {
    if(loadBtn) loadBtn.addEventListener("click", loadAccounts);
    if(importOverwriteBtn) importOverwriteBtn.addEventListener("click", () => importAccounts(true));
    if(importAppendBtn) importAppendBtn.addEventListener("click", () => importAccounts(false));
    
    loadAccounts();
}

export async function loadAccounts() {
    if(loadBtn) loadBtn.disabled = true;

    // Parallel fetch
    const [raw, parsed] = await Promise.all([
        fetchJson("/api/data/accounts"),
        fetchJson("/api/data/accounts/parsed"),
    ]);

    if (raw.ok) {
        if(accountsInput) accountsInput.value = raw.data.data || "";
    } else {
        toast.warn("加载原始账号数据失败");
    }

    if (parsed.ok) {
        const list = Array.isArray(parsed.data.accounts) ? parsed.data.accounts : [];
        if(accountsPreview) {
            if (list.length === 0) {
                accountsPreview.textContent = "暂无账号";
            } else {
                accountsPreview.textContent = list
                    .map((item, idx) => `${idx + 1}. ${item.account || '-'} | 密码: ${item.password ? '已设置' : '未设置'} | 2FA: ${item.otp_secret ? '已设置' : '无'}`)
                    .join("\n");
            }
        }
        if(accountsMsg) accountsMsg.textContent = `已加载 ${list.length} 个账号`;
    } else {
        toast.error("加载解析后账号失败");
    }
    
    if(loadBtn) loadBtn.disabled = false;
}

async function importAccounts(overwrite) {
    const btn = overwrite ? importOverwriteBtn : importAppendBtn;
    if(btn) btn.disabled = true;
    
    const r = await fetchJson("/api/data/accounts/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: accountsInput.value || "", overwrite }),
    });

    if (r.ok) {
        const d = r.data;
        const msg = `成功导入 ${d.imported} (有效=${d.valid}, 无效=${d.invalid}), 已存储=${d.stored}`;
        toast.success(msg);
        if(accountsMsg) accountsMsg.textContent = msg;
        await loadAccounts();
    } else {
        toast.error("导入失败");
        if(accountsPreview) accountsPreview.textContent = `导入失败（状态码 ${r.status}）`;
    }
    
    if(btn) btn.disabled = false;
}
