import { fetchJson } from '../utils/api.js';

const $ = (id) => document.getElementById(id);

let unitAccounts = [];
let activeUnitAccountScope = '';

function renderEmptyAccountSelect(select, label) {
    if (!select) return;
    select.replaceChildren();
    const emptyOpt = document.createElement('option');
    emptyOpt.value = '';
    emptyOpt.textContent = label;
    select.appendChild(emptyOpt);
}

export async function loadUnitAccounts(appId = activeUnitAccountScope) {
    const select = $('unitAccountSelect');
    const hint = $('unitAccountHint');
    if (!select) return;
    activeUnitAccountScope = String(appId || '').trim();
    const params = new URLSearchParams();
    if (activeUnitAccountScope) {
        params.set('app_id', activeUnitAccountScope);
    }
    const query = params.toString();
    try {
        const response = await fetchJson(`/api/data/accounts/parsed${query ? `?${query}` : ''}`);
        if (!response.ok) {
            unitAccounts = [];
            renderEmptyAccountSelect(select, '-- 账号加载失败 --');
            if (hint) hint.textContent = '加载账号失败';
            return;
        }
        unitAccounts = (response.data?.accounts || []).filter((account) => account.status === 'ready');
        select.replaceChildren();
        const emptyOpt = document.createElement('option');
        emptyOpt.value = '';
        emptyOpt.textContent = `-- 不绑定账号 (${unitAccounts.length} 个就绪) --`;
        select.appendChild(emptyOpt);
        unitAccounts.forEach((account, index) => {
            const opt = document.createElement('option');
            opt.value = String(index);
            opt.textContent = account.account;
            select.appendChild(opt);
        });
        if (hint) {
            hint.textContent = activeUnitAccountScope
                ? `${activeUnitAccountScope} 账号池共 ${unitAccounts.length} 个就绪账号`
                : `全部账号池共 ${unitAccounts.length} 个就绪账号`;
        }
    } catch (_error) {
        unitAccounts = [];
        renderEmptyAccountSelect(select, '-- 账号加载失败 --');
        if (hint) hint.textContent = '加载账号失败';
    }
}

export function getSelectedUnitAccount() {
    const select = $('unitAccountSelect');
    if (!select || select.value === '') return null;
    return unitAccounts[Number.parseInt(select.value, 10)] || null;
}
