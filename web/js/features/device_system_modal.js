import { fetchJson } from '../utils/api.js';
import { toast } from '../ui/toast.js';

const $ = (id) => document.getElementById(id);

function clearElement(element) {
    if (element) {
        element.replaceChildren();
    }
}

function createStatusRow(labelText, initialValueText = '-') {
    const row = document.createElement('div');
    const labelSpan = document.createElement('span');
    labelSpan.className = 'text-muted';
    labelSpan.textContent = `${labelText}: `;
    const valueSpan = document.createElement('span');
    valueSpan.textContent = initialValueText;
    row.append(labelSpan, valueSpan);
    return { row, valueSpan };
}

export function closeSystemModal() {
    const modal = $('systemStatusModal');
    if (modal) modal.style.display = 'none';
}

async function openSystemStatusModal() {
    const modal = $('systemStatusModal');
    if (modal) modal.style.display = 'flex';

    const coreStatus = $('coreServicesStatus');
    clearElement(coreStatus);
    clearElement($('browserDiagResult'));

    const baseUrl = location.origin || '(unknown)';
    const apiRow = createStatusRow('API 地址', baseUrl);
    const healthRow = createStatusRow('API 健康', '检测中...');
    const rpcRow = createStatusRow('RPC', '检测中...');
    const pluginRow = createStatusRow('已加载插件', '检测中...');
    coreStatus?.append(apiRow.row, healthRow.row, rpcRow.row, pluginRow.row);

    try {
        const response = await fetchJson('/health', { silentErrors: true });
        if (!response.ok || !response.data) {
            healthRow.valueSpan.textContent = '不可用';
            healthRow.valueSpan.style.color = 'var(--warn)';
            rpcRow.valueSpan.textContent = '未知';
            rpcRow.valueSpan.style.color = 'var(--warn)';
            pluginRow.valueSpan.textContent = '未知';
            pluginRow.valueSpan.style.color = 'var(--warn)';
            return;
        }

        healthRow.valueSpan.textContent = 'OK';
        healthRow.valueSpan.style.color = 'var(--success)';
        if (response.data.rpc_enabled) {
            rpcRow.valueSpan.textContent = '已启用';
            rpcRow.valueSpan.style.color = 'var(--success)';
        } else {
            rpcRow.valueSpan.textContent = '已禁用';
            rpcRow.valueSpan.style.color = 'var(--warn)';
        }

        const loadedPlugins = response.data?.plugins?.loaded;
        pluginRow.valueSpan.textContent = Array.isArray(loadedPlugins)
            ? `${loadedPlugins.length} 个`
            : '未知';
    } catch (_error) {
        healthRow.valueSpan.textContent = '检测失败';
        healthRow.valueSpan.style.color = 'var(--warn)';
        rpcRow.valueSpan.textContent = '未知';
        rpcRow.valueSpan.style.color = 'var(--warn)';
        pluginRow.valueSpan.textContent = '未知';
        pluginRow.valueSpan.style.color = 'var(--warn)';
    }
}

async function runGlobalBrowserDiag() {
    const resultBox = $('browserDiagResult');
    if (!resultBox) return;
    resultBox.replaceChildren();
    const loading = document.createElement('div');
    loading.className = 'text-xs text-muted';
    loading.textContent = '正在探测服务端浏览器环境...';
    resultBox.appendChild(loading);

    const response = await fetchJson('/api/diagnostics/browser');
    if (response.ok) {
        const diag = response.data;
        const wrap = document.createElement('div');
        wrap.className =
            'bg-black text-green-400 p-4 rounded font-mono text-xs overflow-auto max-h-64 mt-2';
        const pre = document.createElement('pre');
        pre.style.margin = '0';
        const lines = [];
        lines.push(`> Browser Ready: ${diag.ready ? 'YES' : 'NO'}`);
        if (diag.error) lines.push(`> Error: ${diag.error}`);
        lines.push(`> DrissionPage: ${diag.drissionpage_importable ? 'OK' : 'FAIL'}`);
        lines.push(`> Chromium Binary: ${diag.chromium_binary_found ? 'FOUND' : 'NOT FOUND'}`);
        if (diag.chromium_binary_path) lines.push(`> Path: ${diag.chromium_binary_path}`);
        pre.textContent = lines.join('\n');
        wrap.appendChild(pre);
        resultBox.replaceChildren(wrap);
        return;
    }

    toast.error('诊断请求失败');
    resultBox.replaceChildren();
    const err = document.createElement('div');
    err.className = 'text-error text-xs';
    err.textContent = '请求失败，请检查 API 连通性';
    resultBox.appendChild(err);
}

export function bindSystemStatusModal() {
    const showSysBtn = $('showSystemStatus') || $('apiStatus');
    if (showSysBtn) {
        showSysBtn.style.cursor = 'pointer';
        showSysBtn.onclick = () => {
            void openSystemStatusModal();
        };
    }

    const closeButtons = document.querySelectorAll('.close-system-modal-btn');
    closeButtons.forEach((button) => {
        button.onclick = closeSystemModal;
    });

    const globalBrowserDiagBtn = $('runGlobalBrowserDiag');
    if (globalBrowserDiagBtn) {
        globalBrowserDiagBtn.onclick = () => {
            void runGlobalBrowserDiag();
        };
    }
}
