import { fetchJson, fetchText } from '/static/js/utils/api.js';
import { toast } from '/static/js/ui/toast.js';

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
        container.innerHTML = '<div class="text-center text-muted py-8">暂无错误记录</div>';
        return;
    }

    const totalErrors = entries.reduce((sum, e) => sum + e[1], 0);

    entries.forEach(([code, count]) => {
        const percent = ((count / totalErrors) * 100).toFixed(1);
        
        const row = document.createElement("div");
        row.innerHTML = `
            <div class="flex justify-between text-xs mb-1">
                <span class="font-mono font-bold">${code}</span>
                <span class="text-muted">${count} 次 (${percent}%)</span>
            </div>
            <div class="w-full bg-bg-sidebar rounded-full h-1.5 overflow-hidden">
                <div class="bg-primary h-full" style="width: ${percent}%"></div>
            </div>
        `;
        container.appendChild(row);
    });
}

function renderPluginStats(plugins) {
    const container = $('metricPluginStats');
    if (!container) return;
    container.replaceChildren();

    if (plugins.length === 0) {
        container.innerHTML = '<div class="text-center text-muted py-8">暂无插件执行记录</div>';
        return;
    }

    plugins.forEach(p => {
        const successRate = ((p.success_rate || 0) * 100).toFixed(1);
        const remaining = p.distill_remaining || 0;
        const ready = p.distill_ready;
        const completed = p.completed || 0;
        const threshold = p.distill_threshold || 3;
        const progress = Math.min(100, (completed / threshold) * 100).toFixed(0);

        const row = document.createElement('div');
        row.style.cssText = 'margin-bottom: 16px;';
        row.innerHTML = `
            <div class="flex justify-between text-xs mb-1">
                <span class="font-mono font-bold">${p.task_name}</span>
                <div class="flex items-center gap-2">
                    <span class="${ready ? 'text-success' : 'text-muted'}">
                        ${ready ? '✅ 可蒸馏' : `还差 ${remaining} 次`}
                        &nbsp;·&nbsp; 成功率 ${successRate}%
                        &nbsp;·&nbsp; ${completed}/${threshold}
                    </span>
                    <button class="btn btn-secondary btn-sm distill-btn" data-plugin="${p.task_name}" ${ready ? '' : 'disabled'}>
                        蒸馏
                    </button>
                </div>
            </div>
            <div class="w-full bg-bg-sidebar rounded-full h-1.5 overflow-hidden">
                <div class="h-full ${ready ? 'bg-success' : 'bg-primary'}" style="width: ${progress}%"></div>
            </div>
        `;
        container.appendChild(row);
    });

    // 绑定蒸馏按钮
    container.querySelectorAll('.distill-btn').forEach(btn => {
        btn.onclick = async () => {
            const plugin = btn.dataset.plugin;
            btn.disabled = true;
            btn.textContent = '蒸馏中...';
            const r = await fetchJson(`/api/tasks/distill/${plugin}`, { method: 'POST' });
            if (r.ok && r.data?.ok) {
                toast.success(`${plugin} 蒸馏完成，草稿已生成至 plugins/${plugin}_distilled/`);
            } else {
                const msg = r.data?.message || r.data?.stderr || '蒸馏失败';
                toast.error(msg);
                btn.disabled = false;
                btn.textContent = '蒸馏';
            }
        };
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
