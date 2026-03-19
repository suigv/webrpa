import { fetchJson, fetchText } from '../utils/api.js';
import { toast } from '../ui/toast.js';

const $ = (id) => document.getElementById(id);

export function initMetrics() {
    const viewPromBtn = $("viewPrometheusRaw");
    if (viewPromBtn) viewPromBtn.onclick = togglePrometheusPreview;

    const navItem = $("nav-metrics");
    if (navItem) {
        navItem.addEventListener("click", loadMetrics);
    }

    // 如果当前就是这个 tab，自动加载
    if (window.location.hash === '#metrics') {
        loadMetrics();
    }
}

export async function loadMetrics() {
    const r = await fetchJson("/api/tasks/metrics?window_seconds=3600");
    if (!r.ok) return;
    const d = r.data;
    renderKPIs(d);
    renderErrorDistribution(d.failure_distribution || {});

    const r2 = await fetchJson("/api/tasks/metrics/plugins");
    if (r2.ok) renderPluginStats(r2.data || []);
}

function renderKPIs(d) {
    const rates = d.rates || {};
    const failureRate = rates.failure_rate ?? 0;
    const successRateEl = $("metricSuccessRate");
    const healthEl = $("metricHealthStatus");

    successRateEl.textContent = `${((1 - failureRate) * 100).toFixed(1)}%`;

    // 健康分判定
    if (failureRate < 0.1) {
        healthEl.textContent = "状态良好";
        healthEl.className = "mt-2 text-xs px-2 py-1 rounded bg-success-soft text-success";
        successRateEl.style.color = "var(--success)";
    } else if (failureRate < 0.3) {
        healthEl.textContent = "监控警告";
        healthEl.className = "mt-2 text-xs px-2 py-1 rounded bg-warn-soft text-warn";
        successRateEl.style.color = "var(--warn)";
    } else {
        healthEl.textContent = "高危风险";
        healthEl.className = "mt-2 text-xs px-2 py-1 rounded bg-error-soft text-error";
        successRateEl.style.color = "var(--error)";
    }

    const terminal = d.terminal_outcomes || {};
    const terminalCount = (terminal.completed || 0) + (terminal.failed || 0) + (terminal.cancelled || 0);
    const statusCounts = d.status_counts || {};
    const activeCount = (statusCounts.pending || 0) + (statusCounts.running || 0);
    $("metricTotalTerminal").textContent = terminalCount;
    $("metricTotalActive").textContent = activeCount;
    $("metricAvgDuration").textContent = `${Math.round(d.avg_duration_seconds || 0)}s`;
}

function renderErrorDistribution(dist) {
    const container = $("metricErrorDistribution");
    container.replaceChildren();

    const entries = Object.entries(dist).sort((a, b) => b[1] - a[1]);
    
    if (entries.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'text-center text-muted py-8';
        empty.textContent = '暂无错误记录';
        container.appendChild(empty);
        return;
    }

    const totalErrors = entries.reduce((sum, e) => sum + e[1], 0);

    entries.forEach(([code, count]) => {
        const percent = ((count / totalErrors) * 100).toFixed(1);
        
        const row = document.createElement("div");
        const header = document.createElement('div');
        header.className = 'flex justify-between text-xs mb-1';
        const codeSpan = document.createElement('span');
        codeSpan.className = 'font-mono font-bold';
        codeSpan.textContent = String(code);
        const metaSpan = document.createElement('span');
        metaSpan.className = 'text-muted';
        metaSpan.textContent = `${count} 次 (${percent}%)`;
        header.append(codeSpan, metaSpan);

        const barWrap = document.createElement('div');
        barWrap.className = 'w-full bg-bg-sidebar rounded-full h-1.5 overflow-hidden';
        const bar = document.createElement('div');
        bar.className = 'bg-primary h-full';
        bar.style.width = `${percent}%`;
        barWrap.appendChild(bar);

        row.append(header, barWrap);
        container.appendChild(row);
    });
}

function renderPluginStats(plugins) {
    const container = $('metricPluginStats');
    if (!container) return;
    container.replaceChildren();

    if (plugins.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'text-center text-muted py-8';
        empty.textContent = '暂无插件执行记录';
        container.appendChild(empty);
        return;
    }

    plugins.forEach(p => {
        const distillable = p.distillable !== false;
        const successRate = ((p.success_rate || 0) * 100).toFixed(1);
        const remaining = p.distill_remaining || 0;
        const ready = distillable && p.distill_ready;
        const completed = p.completed || 0;
        const threshold = p.distill_threshold || 3;
        const progress = Math.min(100, (completed / threshold) * 100).toFixed(0);

        const row = document.createElement('div');
        row.style.cssText = 'margin-bottom: 16px;';
        const header = document.createElement('div');
        header.className = 'flex justify-between text-xs mb-1';

        const name = document.createElement('span');
        name.className = 'font-mono font-bold';
        name.textContent = String(p.task_name || '');

        const right = document.createElement('div');
        right.className = 'flex items-center gap-2';

        const meta = document.createElement('span');
        meta.className = ready ? 'text-success' : 'text-muted';
        if (!distillable) {
            meta.textContent = `不支持蒸馏 · 成功率 ${successRate}%`;
        } else {
            meta.textContent = `${ready ? '✅ 可蒸馏' : `还差 ${remaining} 次`} · 成功率 ${successRate}% · ${completed}/${threshold}`;
        }

        const button = document.createElement('button');
        button.className = 'btn btn-secondary btn-sm';
        button.textContent = '蒸馏';
        button.disabled = !ready;
        button.onclick = async () => {
            const plugin = String(p.task_name || '');
            button.disabled = true;
            button.textContent = '蒸馏中...';
            const r = await fetchJson(`/api/tasks/distill/${plugin}`, { method: 'POST' });
            if (r.ok && r.data?.ok) {
                toast.success(`${plugin} 蒸馏完成，草稿已生成至 plugins/${plugin}_distilled/`);
                button.textContent = '蒸馏';
            } else {
                const msg = r.data?.message || r.data?.stderr || '蒸馏失败';
                toast.error(msg);
                button.disabled = !ready;
                button.textContent = '蒸馏';
            }
        };

        right.append(meta, button);
        header.append(name, right);

        const barWrap = document.createElement('div');
        barWrap.className = 'w-full bg-bg-sidebar rounded-full h-1.5 overflow-hidden';
        const bar = document.createElement('div');
        bar.className = `h-full ${!distillable ? 'bg-bg-panel' : (ready ? 'bg-success' : 'bg-primary')}`;
        bar.style.width = `${progress}%`;
        barWrap.appendChild(bar);

        row.append(header, barWrap);
        container.appendChild(row);
    });
}

async function togglePrometheusPreview() {
    const area = $("prometheusPreviewArea");
    const text = $("prometheusRawText");
    const btn = $("viewPrometheusRaw");

    if (area.style.display === "block") {
        area.style.display = "none";
        btn.textContent = "查看 Prometheus 原始文本";
        return;
    }

    area.style.display = "block";
    btn.textContent = "收起预览";
    text.value = "正在加载数据...";

    const res = await fetchText("/api/tasks/metrics/prometheus");
    if (res.ok) {
        text.value = res.data;
    } else {
        text.value = "获取数据失败: " + res.status;
    }
}
