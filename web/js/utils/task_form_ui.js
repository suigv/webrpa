import { renderCommonFields, renderTaskGuide } from './ui_utils.js';

function clearElement(element) {
    if (element) {
        element.replaceChildren();
    }
}

function setAdvancedFieldVisibility(container, visible) {
    if (!container) return 0;
    const advancedFields = container.querySelectorAll('.field-advanced');
    advancedFields.forEach((element) => {
        element.style.display = visible ? 'flex' : 'none';
    });
    return advancedFields.length;
}

export function toggleAdvancedTaskFields(container, button) {
    if (!container || !button) return;
    const shouldExpand = button.dataset.expanded !== 'true';
    setAdvancedFieldVisibility(container, shouldExpand);
    button.dataset.expanded = shouldExpand ? 'true' : 'false';
    button.textContent = shouldExpand
        ? (button.dataset.expandedText || '收起高级参数')
        : (button.dataset.collapsedText || '显示高级参数');
}

export function renderTaskFormPanel({
    task,
    guideCard,
    fieldsContainer,
    toggleButton,
    collapsedText = '显示高级参数',
    expandedText = '收起高级参数',
}) {
    if (!fieldsContainer) return;

    renderTaskGuide(guideCard, task || null);

    if (!task) {
        clearElement(fieldsContainer);
        if (toggleButton) {
            toggleButton.style.display = 'none';
            toggleButton.dataset.expanded = 'false';
            toggleButton.textContent = collapsedText;
            toggleButton.dataset.collapsedText = collapsedText;
            toggleButton.dataset.expandedText = expandedText;
        }
        return;
    }

    renderCommonFields(fieldsContainer, task, false);
    if (!toggleButton) return;

    const advancedCount = setAdvancedFieldVisibility(fieldsContainer, false);
    toggleButton.dataset.expanded = 'false';
    toggleButton.dataset.collapsedText = collapsedText;
    toggleButton.dataset.expandedText = expandedText;
    toggleButton.textContent = collapsedText;
    toggleButton.style.display = advancedCount > 0 ? 'inline-flex' : 'none';
}
