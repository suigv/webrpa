import { getTaskCatalog } from './task_service.js';

function clearElement(element) {
    if (element) {
        element.replaceChildren();
    }
}

export function renderGroupedTaskSelect(select, tasks) {
    const grouped = {};
    tasks.forEach((task) => {
        const category = task.category || '其它';
        if (!grouped[category]) grouped[category] = [];
        grouped[category].push(task);
    });
    clearElement(select);
    Object.keys(grouped).forEach((category) => {
        const groupEl = document.createElement('optgroup');
        groupEl.label = category;
        grouped[category].forEach((task) => {
            const opt = document.createElement('option');
            opt.value = task.task;
            opt.textContent = task.display_name || task.task;
            groupEl.appendChild(opt);
        });
        select.appendChild(groupEl);
    });
}

export async function loadDevicePluginCatalog({
    bulkSelect,
    unitSelect,
    onLoaded,
}) {
    const catalog = await getTaskCatalog();
    if (bulkSelect) renderGroupedTaskSelect(bulkSelect, catalog);
    if (unitSelect) renderGroupedTaskSelect(unitSelect, catalog);
    onLoaded?.(catalog);
    return catalog;
}
