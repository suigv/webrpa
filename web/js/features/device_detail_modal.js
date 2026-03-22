import { fetchJson } from '../utils/api.js';
import { toast } from '../ui/toast.js';

const $ = (id) => document.getElementById(id);

function createTextBlock(label, value, valueStyle = '') {
    const row = document.createElement('div');
    const labelSpan = document.createElement('span');
    labelSpan.className = 'text-muted';
    labelSpan.textContent = `${label}: `;
    const valueSpan = document.createElement('span');
    valueSpan.textContent = value;
    if (valueStyle) {
        valueSpan.style.cssText = valueStyle;
    }
    row.append(labelSpan, valueSpan);
    return row;
}

export function showDeviceModal() {
    const modal = $('deviceDetailModal');
    if (modal) modal.style.display = 'flex';
}

export function closeDeviceModal() {
    const modal = $('deviceDetailModal');
    if (modal) modal.style.display = 'none';
}

export function openDeviceDetail(unit) {
    if (!unit) return;
    const content = $('deviceDetailContent');
    if (content) {
        content.replaceChildren();
    }

    const unitId = `${unit.parent_id}-${unit.cloud_id}`;
    const title = $('deviceDetailTitle');
    if (title) title.textContent = `设备详情 - 云机 #${unitId}`;

    const grid = document.createElement('div');
    grid.className = 'form-grid columns-2 text-sm';
    grid.append(createTextBlock('设备 IP', unit.parent_ip));
    grid.append(createTextBlock('ADB 端口', unit.rpa_port));
    grid.append(createTextBlock('API 端口', unit.api_port));
    grid.append(createTextBlock('云机型号', unit.machine_model_name || '标准型'));
    grid.append(createTextBlock('AI 引擎', unit.ai_type));
    grid.append(
        createTextBlock(
            '状态',
            unit.availability_state,
            `color:${unit.availability_state === 'available' ? 'var(--success)' : 'var(--error)'}`,
        ),
    );

    if (unit.current_task) {
        const taskRow = createTextBlock(
            '当前任务',
            unit.current_task,
            'color:var(--text-primary); font-weight:600;',
        );
        taskRow.style.gridColumn = '1 / -1';
        grid.append(taskRow);
    }

    content?.appendChild(grid);
    showDeviceModal();
}

export function bindDeviceModalActions({ getCurrentUnit, onDeviceChanged }) {
    const closeButtons = document.querySelectorAll('.close-device-modal-btn');
    closeButtons.forEach((button) => {
        button.onclick = closeDeviceModal;
    });

    const stopDeviceBtn = $('stopDeviceTasksBtn');
    if (stopDeviceBtn) {
        stopDeviceBtn.onclick = async () => {
            const unit = getCurrentUnit?.();
            if (!unit) return;
            if (!window.confirm(`确定要停止设备 #${unit.parent_id} 上正在运行的所有任务吗？`)) {
                return;
            }
            const response = await fetchJson(`/api/tasks/device/${unit.parent_id}/stop`, { method: 'POST' });
            if (response.ok) {
                toast.success(`已下发停止指令，取消了 ${response.data.cancelled_count} 个任务`);
                closeDeviceModal();
                onDeviceChanged?.();
                return;
            }
            toast.error('停止任务失败');
        };
    }

    const bindOnlineStatusButton = (id, online) => {
        const button = $(id);
        if (!button) return;
        button.onclick = async () => {
            const unit = getCurrentUnit?.();
            if (!unit) return;
            const action = online ? '上线' : '下线';
            if (!window.confirm(`确定要将设备 #${unit.parent_id} ${action}吗？`)) {
                return;
            }
            const endpoint = online ? 'start' : 'stop';
            const response = await fetchJson(`/api/devices/${unit.parent_id}/${endpoint}`, {
                method: 'POST',
            });
            if (response.ok) {
                toast.success(`设备 #${unit.parent_id} 已${action}`);
                closeDeviceModal();
                onDeviceChanged?.();
                return;
            }
            toast.error(`设备${action}失败`);
        };
    };

    bindOnlineStatusButton('enableDeviceBtn', true);
    bindOnlineStatusButton('disableDeviceBtn', false);
}
