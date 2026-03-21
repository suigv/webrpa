import test from 'node:test';
import assert from 'node:assert/strict';

function createFakeElement(id = '') {
    return {
        id,
        style: {},
        children: [],
        onclick: null,
        className: '',
        textContent: '',
        appendChild(child) {
            this.children.push(child);
            return child;
        },
        append(...children) {
            this.children.push(...children);
        },
        replaceChildren(...children) {
            this.children = [...children];
        },
        addEventListener() {},
        remove() {},
        classList: {
            add() {},
            contains() { return false; },
        },
        get offsetWidth() {
            return 0;
        },
    };
}

function installDom() {
    const elements = new Map();
    const getOrCreate = (id) => {
        if (!elements.has(id)) {
            elements.set(id, createFakeElement(id));
        }
        return elements.get(id);
    };

    const body = createFakeElement('body');
    const document = {
        body,
        createElement: () => createFakeElement(),
        getElementById: (id) => getOrCreate(id),
        querySelectorAll: (selector) => (selector === '.close-device-modal-btn' ? [] : []),
    };

    globalThis.document = document;
    globalThis.window = globalThis;
    globalThis.localStorage = {
        getItem() { return null; },
        setItem() {},
        removeItem() {},
    };

    return { getOrCreate };
}

test('device stop confirmation stays device-scoped and posts to device route', async () => {
    const { getOrCreate } = installDom();
    const confirmMessages = [];
    const fetchCalls = [];
    const unit = { parent_id: 7, cloud_id: 3 };

    globalThis.confirm = (message) => {
        confirmMessages.push(message);
        return true;
    };
    globalThis.fetch = async (url, options = {}) => {
        fetchCalls.push({ url, options });
        return {
            ok: true,
            status: 200,
            async text() {
                return JSON.stringify({ cancelled_count: 2 });
            },
        };
    };

    const modalModule = await import('./device_detail_modal.js');
    modalModule.bindDeviceModalActions({
        getCurrentUnit: () => unit,
        onDeviceChanged: () => {},
    });

    await getOrCreate('stopDeviceTasksBtn').onclick();

    assert.deepEqual(confirmMessages, ['确定要停止设备 #7 上正在运行的所有任务吗？']);
    assert.equal(fetchCalls.length, 1);
    assert.equal(fetchCalls[0].url, '/api/tasks/device/7/stop');
    assert.equal(fetchCalls[0].options.method, 'POST');
});
