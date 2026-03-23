import { fetchJson } from '../utils/api.js';
import { toast } from '../ui/toast.js';
import { FetchSseClient } from '../utils/sse.js';
import { mountUnitControlSurface } from './device_unit_detail.js';
import { findUnitInDevices, refreshDevicesSnapshot } from '../state/devices.js';

const $ = (id) => document.getElementById(id);

let overlayStream = null;
let overlayTaskId = '';
let overlayControlCleanup = null;
let overlayUnit = null;
let overlayTraceContext = null;
let overlayResolveToken = 0;

function setResumeVisibility(visible) {
    const resumeBtn = $('aiTaskOverlayResume');
    if (resumeBtn) {
        resumeBtn.style.display = visible ? '' : 'none';
    }
}

function clearElement(element) {
    if (element) {
        element.replaceChildren();
    }
}

function ensureOverlayConsoleDom() {
    const modal = $('aiTaskOverlay');
    if (!modal) return;

    let body = modal.querySelector('.modal-body');
    if (!body) return;

    let layout = body.querySelector('.ai-task-overlay-layout');
    let stream = $('aiTaskOverlayHint')?.closest('.ai-task-overlay-stream') || body.querySelector('.ai-task-overlay-stream');
    if (!layout) {
        layout = document.createElement('div');
        layout.className = 'ai-task-overlay-layout';
        layout.style.display = 'grid';
        layout.style.gridTemplateColumns = 'minmax(0, 420px) minmax(0, 1fr)';
        layout.style.gap = '16px';
        layout.style.alignItems = 'start';

        if (!stream) {
            stream = document.createElement('div');
            stream.className = 'ai-task-overlay-stream';
            const hint = $('aiTaskOverlayHint');
            const steps = $('aiTaskOverlaySteps');
            if (hint) stream.appendChild(hint);
            if (steps) stream.appendChild(steps);
        }
        if (stream) {
            stream.style.minWidth = '0';
            stream.style.display = 'flex';
            stream.style.flexDirection = 'column';
        }
        clearElement(body);
        body.appendChild(layout);
        if (stream) {
            layout.appendChild(stream);
        }
    }

    if (!$('aiTaskOverlayConsole')) {
        const consolePanel = document.createElement('div');
        consolePanel.id = 'aiTaskOverlayConsole';
        consolePanel.className = 'ai-task-overlay-console';
        consolePanel.style.display = 'none';
        consolePanel.style.flexDirection = 'column';
        consolePanel.style.gap = '12px';
        consolePanel.innerHTML = `
            <div class="ai-task-overlay-console-header" style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">
              <div>
                <div class="task-summary-title">当前云机画面</div>
                <div id="aiTaskOverlayTarget" class="task-summary-text">当前任务未绑定云机目标</div>
              </div>
              <button type="button" id="aiTaskOverlayRefreshScreenshot" class="btn btn-secondary btn-sm" data-unit-control>刷新截图</button>
            </div>
            <div class="ai-task-overlay-screen" style="position:relative;min-height:360px;border:1px solid var(--border);border-radius:var(--radius-sm);background:rgba(0,0,0,0.28);overflow:hidden;">
              <img id="aiTaskOverlayScreenshotImg" src="" alt="" class="ai-task-overlay-screen-image" style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:auto;height:auto;max-width:92%;max-height:340px;border-radius:var(--radius-sm);visibility:hidden;cursor:crosshair;">
              <div id="aiTaskOverlayScreenshotPlaceholder" class="text-muted ai-task-overlay-screen-placeholder" style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);white-space:nowrap;">正在加载截图...</div>
            </div>
            <div class="device-control-panel ai-task-overlay-control-panel" style="padding:12px;border:1px solid var(--border);border-radius:var(--radius-sm);background-color:rgba(255,255,255,0.02);">
              <div class="device-control-actions">
                <button type="button" id="aiTaskOverlayKeyBack" class="btn btn-secondary btn-sm" data-unit-control>返回</button>
                <button type="button" id="aiTaskOverlayKeyHome" class="btn btn-secondary btn-sm" data-unit-control>Home</button>
                <button type="button" id="aiTaskOverlayKeyEnter" class="btn btn-secondary btn-sm" data-unit-control>Enter</button>
                <button type="button" id="aiTaskOverlayKeyDelete" class="btn btn-secondary btn-sm" data-unit-control>退格键</button>
              </div>
              <div class="device-swipe-pad">
                <button type="button" id="aiTaskOverlaySwipeUp" class="btn btn-secondary btn-sm" data-unit-control>上滑</button>
                <button type="button" id="aiTaskOverlaySwipeLeft" class="btn btn-secondary btn-sm" data-unit-control>左滑</button>
                <button type="button" id="aiTaskOverlaySwipeDown" class="btn btn-secondary btn-sm" data-unit-control>下滑</button>
                <button type="button" id="aiTaskOverlaySwipeRight" class="btn btn-secondary btn-sm" data-unit-control>右滑</button>
              </div>
              <div class="device-text-input-row">
                <input id="aiTaskOverlayTextInput" type="text" placeholder="向当前焦点输入框发送单行文本" autocomplete="off" data-unit-control>
                <button type="button" id="aiTaskOverlaySendText" class="btn btn-secondary btn-sm" data-unit-control>发送文本</button>
              </div>
              <div class="text-muted text-xs">点击截图发送轻触；接管后所有操作会继续写入同一条蒸馏轨迹。</div>
            </div>
        `;
        layout.insertBefore(consolePanel, layout.firstChild);
    }

    stream = $('aiTaskOverlayHint')?.closest('.ai-task-overlay-stream') || body.querySelector('.ai-task-overlay-stream');
    if (stream) {
        stream.style.minWidth = '0';
        stream.style.display = 'flex';
        stream.style.flexDirection = 'column';
    }
    const steps = $('aiTaskOverlaySteps');
    if (steps) {
        steps.style.flex = '1';
        steps.style.maxHeight = '520px';
        steps.style.overflowY = 'auto';
    }
}

function overlayStatusVariant(status) {
    const normalized = String(status || 'pending').toLowerCase();
    if (normalized === 'completed') return 'ok';
    if (normalized === 'failed' || normalized === 'cancelled') return 'error';
    return 'default';
}

function setOverlayStatus(status) {
    const badge = $('aiTaskOverlayStatus');
    if (!badge) return;
    const normalized = String(status || 'pending').toLowerCase();
    badge.className = `badge badge-${overlayStatusVariant(normalized)}`;
    badge.textContent = normalized.toUpperCase();
}

function setOverlayHint(text) {
    const hint = $('aiTaskOverlayHint');
    if (hint) hint.textContent = text;
}

function setOverlayProgress(text) {
    const progress = $('aiTaskOverlayProgress');
    if (progress) progress.textContent = text;
}

function setOverlayTarget(text) {
    const target = $('aiTaskOverlayTarget');
    if (target) target.textContent = text;
}

function describeOverlayUnit(unit) {
    if (!unit) return '当前任务未绑定云机目标';
    return `云机 #${unit.parent_id}-${unit.cloud_id}`;
}

function overlayConsoleButtons() {
    return Array.from(document.querySelectorAll('#aiTaskOverlayConsole [data-unit-control]'));
}

function setOverlayConsoleEnabled(enabled) {
    overlayConsoleButtons().forEach((button) => {
        button.disabled = !enabled;
    });
}

function setOverlayConsolePlaceholder(text) {
    const placeholder = $('aiTaskOverlayScreenshotPlaceholder');
    const img = $('aiTaskOverlayScreenshotImg');
    if (img) {
        img.style.visibility = 'hidden';
    }
    if (placeholder) {
        placeholder.textContent = text;
        placeholder.style.visibility = 'visible';
    }
}

function showOverlayConsole() {
    const consolePanel = $('aiTaskOverlayConsole');
    if (consolePanel) {
        consolePanel.style.display = 'flex';
    }
}

function teardownOverlayControls({ hidePanel = true } = {}) {
    overlayControlCleanup?.();
    overlayControlCleanup = null;
    overlayUnit = null;
    overlayTraceContext = null;
    const consolePanel = $('aiTaskOverlayConsole');
    if (consolePanel && hidePanel) {
        consolePanel.style.display = 'none';
    }
    setOverlayTarget('当前任务未绑定云机目标');
}

function setOverlayConsolePending(targetText, placeholderText) {
    teardownOverlayControls({ hidePanel: false });
    showOverlayConsole();
    setOverlayTarget(targetText);
    setOverlayConsoleEnabled(false);
    setOverlayConsolePlaceholder(placeholderText);
}

function buildOverlayTraceContext(taskId, unit, traceContext) {
    if (traceContext && typeof traceContext === 'object') {
        return { ...traceContext, takeoverRequested: Boolean(traceContext.takeoverRequested) };
    }
    if (!taskId || !unit) return null;
    return {
        taskId,
        runId: `${taskId}-run-1`,
        targetLabel: `Unit #${unit.parent_id}-${unit.cloud_id}`,
        attemptNumber: 1,
        deviceId: unit.parent_id,
        cloudId: unit.cloud_id,
        takeoverRequested: false,
    };
}

async function resolveOverlayUnit(taskId, initialUnit = null) {
    if (initialUnit?.parent_id && initialUnit?.cloud_id) {
        return initialUnit;
    }
    const taskResponse = await fetchJson(`/api/tasks/${encodeURIComponent(taskId)}`, {
        silentErrors: true,
    });
    if (!taskResponse.ok) return null;
    const firstTarget = Array.isArray(taskResponse.data?.targets) ? taskResponse.data.targets[0] : null;
    const deviceId = Number(firstTarget?.device_id || 0);
    const cloudId = Number(firstTarget?.cloud_id || 0);
    if (!deviceId || !cloudId) return null;

    const devicesResponse = await refreshDevicesSnapshot({ silentErrors: true, maxAgeMs: 5000 });
    if (!devicesResponse.ok) return null;
    return findUnitInDevices(deviceId, cloudId, devicesResponse.data);
}

async function hydrateOverlayControls(taskId, initialUnit, traceContext) {
    const resolveToken = overlayResolveToken;
    const targetLabel = initialUnit
        ? describeOverlayUnit(initialUnit)
        : '正在定位云机目标';
    setOverlayConsolePending(targetLabel, '正在连接云机画面...');
    const resolvedUnit = await resolveOverlayUnit(taskId, initialUnit);
    if (resolveToken !== overlayResolveToken) {
        return;
    }
    if (!resolvedUnit) {
        setOverlayConsolePending('未定位到云机目标', '当前任务未解析出可展示的云机画面');
        return;
    }
    mountOverlayControls(resolvedUnit, buildOverlayTraceContext(taskId, resolvedUnit, traceContext));
}

function mountOverlayControls(unit, traceContext) {
    const consolePanel = $('aiTaskOverlayConsole');
    if (!consolePanel || !unit) {
        setOverlayConsolePending('当前任务未绑定云机目标', '当前任务未解析出可展示的云机画面');
        return;
    }
    overlayControlCleanup?.();
    overlayUnit = unit;
    overlayTraceContext = traceContext && typeof traceContext === 'object'
        ? { ...traceContext, takeoverRequested: Boolean(traceContext.takeoverRequested) }
        : null;
    showOverlayConsole();
    setOverlayConsoleEnabled(true);
    setOverlayTarget(describeOverlayUnit(unit));
    overlayControlCleanup = mountUnitControlSurface({
        unit,
        getTraceContext: () => overlayTraceContext,
        ids: {
            root: 'aiTaskOverlayConsole',
            refreshBtn: 'aiTaskOverlayRefreshScreenshot',
            img: 'aiTaskOverlayScreenshotImg',
            placeholder: 'aiTaskOverlayScreenshotPlaceholder',
            textInput: 'aiTaskOverlayTextInput',
            sendTextBtn: 'aiTaskOverlaySendText',
            keyBack: 'aiTaskOverlayKeyBack',
            keyHome: 'aiTaskOverlayKeyHome',
            keyEnter: 'aiTaskOverlayKeyEnter',
            keyDelete: 'aiTaskOverlayKeyDelete',
            swipeUp: 'aiTaskOverlaySwipeUp',
            swipeLeft: 'aiTaskOverlaySwipeLeft',
            swipeDown: 'aiTaskOverlaySwipeDown',
            swipeRight: 'aiTaskOverlaySwipeRight',
        },
        refreshIntervalMs: 1200,
    });
}

function appendOverlayStep(title, message = '', badgeText = '', badgeVariant = 'default') {
    const host = $('aiTaskOverlaySteps');
    if (!host) return;

    const item = document.createElement('div');
    item.className = 'task-summary-target';

    const header = document.createElement('div');
    header.className = 'task-summary-target-header';

    const titleEl = document.createElement('div');
    titleEl.className = 'task-summary-target-label';
    titleEl.textContent = title;
    header.appendChild(titleEl);

    if (badgeText) {
        const badge = document.createElement('span');
        badge.className = `badge badge-${badgeVariant}`;
        badge.textContent = badgeText;
        header.appendChild(badge);
    }

    const body = document.createElement('div');
    body.className = 'task-summary-target-message';
    body.textContent = message || '等待更新';

    item.append(header, body);
    host.appendChild(item);
    host.scrollTop = host.scrollHeight;

    while (host.children.length > 16) {
        host.removeChild(host.firstChild);
    }
}

function stopOverlayStream() {
    if (overlayStream) {
        overlayStream.close();
        overlayStream = null;
    }
}

function buildFailureHint(data) {
    const text = String(data?.error || data?.message || '').trim();
    if (!text) {
        return overlayUnit
            ? '任务执行失败。你可以直接在左侧云机画面中人工处理当前页面。'
            : '任务执行失败，可查看步骤记录或切换人工接管继续处理。';
    }
    if (text.toLowerCase().includes('stagnant')) {
        return overlayUnit
            ? 'AI 检测到停滞，建议直接在左侧云机画面中接管处理当前页面。'
            : 'AI 检测到停滞，建议切换人工接管处理当前页面。';
    }
    return text;
}

function startOverlayStream(taskId) {
    stopOverlayStream();
    overlayTaskId = taskId;

    overlayStream = new FetchSseClient(`/api/tasks/${encodeURIComponent(taskId)}/events`, {
        onOpen: () => {
            setOverlayHint(
                overlayUnit
                    ? '已连接任务事件流。执行过程中可随时查看当前云机画面并进行轻控制。'
                    : '已连接任务事件流，正在等待 AI 输出步骤。'
            );
        },
        onEvent: (type, raw) => {
            if (!type || type === 'message') return;
            let data = {};
            try {
                data = raw ? JSON.parse(raw) : {};
            } catch {
                data = {};
            }

            if (type === 'task.started') {
                setOverlayStatus('running');
                setOverlayHint(
                    overlayUnit
                        ? 'AI 已开始执行当前任务。若需要人工介入，可直接在左侧云机画面操作。'
                        : 'AI 已开始执行当前任务。'
                );
                setResumeVisibility(false);
                return;
            }

            if (type === 'task.action_result') {
                const step = Number(data?.step || 0);
                const label = String(data?.label || '未命名步骤');
                const ok = Boolean(data?.ok);
                setOverlayStatus('running');
                setOverlayProgress(step > 0 ? `已执行 ${step} 步` : 'AI 正在执行');
                setResumeVisibility(false);
                appendOverlayStep(
                    `步骤 ${step > 0 ? step : '?'}`,
                    String(data?.message || `${label} ${ok ? '已完成' : '未完成'}`).trim(),
                    label,
                    ok ? 'ok' : 'error',
                );
                return;
            }

            if (type === 'task.paused') {
                const interventionRequired = Boolean(data?.intervention_required);
                setOverlayStatus('paused');
                setResumeVisibility(true);
                setOverlayHint(
                    interventionRequired
                        ? (
                            overlayUnit
                                ? 'AI 检测到停滞，已暂停等待人工干预。可直接在左侧云机画面接管，处理后点击继续等待。'
                                : 'AI 检测到停滞，已暂停等待人工干预。你可以继续等待、手动接管，或直接停止任务。'
                        )
                        : String(data?.message || '任务已暂停')
                );
                appendOverlayStep(
                    '任务已暂停',
                    String(data?.message || '任务已暂停，等待人工处理'),
                    interventionRequired ? '待干预' : '暂停',
                    interventionRequired ? 'error' : 'default',
                );
                return;
            }

            if (type === 'task.completed') {
                setOverlayStatus('completed');
                setResumeVisibility(false);
                setOverlayHint('任务已完成，并已写入 AI 对话快捷历史。');
                appendOverlayStep('任务完成', 'AI 已完成本轮操作。', '完成', 'ok');
                stopOverlayStream();
                return;
            }

            if (type === 'task.failed') {
                setOverlayStatus('failed');
                setResumeVisibility(false);
                setOverlayHint(buildFailureHint(data));
                appendOverlayStep('任务失败', buildFailureHint(data), '失败', 'error');
                stopOverlayStream();
                return;
            }

            if (type === 'task.cancelled') {
                setOverlayStatus('cancelled');
                setResumeVisibility(false);
                setOverlayHint(String(data?.message || '任务已取消'));
                appendOverlayStep('任务已取消', String(data?.message || '已停止当前任务'), '取消', 'error');
                stopOverlayStream();
                return;
            }

            if (type === 'task.takeover_requested') {
                if (overlayTraceContext) {
                    overlayTraceContext.takeoverRequested = true;
                }
                setOverlayHint(
                    overlayUnit
                        ? '已切换到人工接管，可直接在左侧云机画面继续操作。'
                        : '已切换到人工接管，可直接在云机详情页继续操作。'
                );
            }
        },
        onError: () => {
            setOverlayHint('任务事件流已断开，可稍后在任务详情页查看完整结果。');
        },
    });
}

async function cancelOverlayTask() {
    if (!overlayTaskId) return;
    const response = await fetchJson(`/api/tasks/${encodeURIComponent(overlayTaskId)}/cancel`, {
        method: 'POST',
        silentErrors: true,
    });
    if (!response.ok) {
        toast.error('停止任务失败');
        return;
    }
    toast.info('已提交停止请求');
}

async function resumeOverlayTask() {
    if (!overlayTaskId) return;
    const response = await fetchJson(`/api/tasks/${encodeURIComponent(overlayTaskId)}/resume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            reason: 'resume_after_ai_intervention_prompt',
        }),
        silentErrors: true,
    });
    if (!response.ok) {
        toast.error('恢复任务失败');
        return;
    }
    toast.info('已请求继续等待，AI 将从当前状态继续执行');
    setOverlayStatus('running');
    setOverlayProgress('恢复中…');
    setOverlayHint('已请求继续执行，等待 AI 从当前页面恢复。');
    setResumeVisibility(false);
}

async function requestOverlayTakeover() {
    if (!overlayTaskId) return;
    if (overlayTraceContext?.takeoverRequested) {
        setOverlayHint('当前已处于人工接管，可直接在左侧云机画面继续操作。');
        return;
    }
    const response = await fetchJson(`/api/tasks/${encodeURIComponent(overlayTaskId)}/takeover`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            run_id: overlayTraceContext?.runId,
            owner: 'web_console_overlay',
            reason: 'operator_takeover_from_ai_overlay',
        }),
        silentErrors: true,
    });
    if (!response.ok) {
        toast.error('切换人工接管失败');
        return;
    }
    if (overlayTraceContext) {
        overlayTraceContext.takeoverRequested = true;
    }
    toast.info('已切换人工接管');
    setOverlayHint(
        overlayUnit
            ? '已切换到人工接管，可直接在左侧云机画面执行轻控制，处理后点击继续等待。'
            : '已切换到人工接管，可直接在云机详情页继续操作。'
    );
}

export function closeAiTaskOverlay() {
    stopOverlayStream();
    overlayTaskId = '';
    overlayResolveToken += 1;
    teardownOverlayControls();
    const modal = $('aiTaskOverlay');
    if (modal) modal.style.display = 'none';
}

export function openAiTaskOverlay({ taskId, title, unit = null, traceContext = null }) {
    const normalizedTaskId = String(taskId || '').trim();
    if (!normalizedTaskId) return;
    overlayResolveToken += 1;
    ensureOverlayConsoleDom();

    const modal = $('aiTaskOverlay');
    if (modal) modal.style.display = 'flex';
    const titleEl = $('aiTaskOverlayTitle');
    if (titleEl) titleEl.textContent = title || 'AI 正在执行';

    clearElement($('aiTaskOverlaySteps'));
    void hydrateOverlayControls(normalizedTaskId, unit, traceContext);
    setOverlayStatus('pending');
    setOverlayProgress('等待任务启动…');
    setOverlayHint(
        unit
            ? '系统会持续更新 AI 的执行步骤与终态。你也可以直接在左侧云机画面中观察和轻控制。'
            : '系统会持续更新 AI 的执行步骤与终态。'
    );
    setResumeVisibility(false);

    const closeBtn = $('aiTaskOverlayClose');
    if (closeBtn) closeBtn.onclick = closeAiTaskOverlay;
    const resumeBtn = $('aiTaskOverlayResume');
    if (resumeBtn) resumeBtn.onclick = () => {
        void resumeOverlayTask();
    };
    const cancelBtn = $('aiTaskOverlayCancel');
    if (cancelBtn) cancelBtn.onclick = () => {
        void cancelOverlayTask();
    };
    const takeoverBtn = $('aiTaskOverlayTakeover');
    if (takeoverBtn) takeoverBtn.onclick = () => {
        void requestOverlayTakeover();
    };

    startOverlayStream(normalizedTaskId);
}
