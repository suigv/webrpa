import test from 'node:test';
import assert from 'node:assert/strict';

class FakeElement {
    constructor(tagName = 'div', ownerDocument = null) {
        this.tagName = tagName.toUpperCase();
        this.ownerDocument = ownerDocument;
        this.children = [];
        this.style = {};
        this.className = '';
        this.textContent = '';
        this.onclick = null;
        this.parentNode = null;
        this.listeners = new Map();
        this.dataset = {};
        this.value = '';
        this._id = '';
        this.classList = {
            contains: () => false,
            add: () => {},
        };
    }

    set id(value) {
        this._id = value;
        if (value && this.ownerDocument) {
            this.ownerDocument.elements.set(value, this);
        }
    }

    get id() {
        return this._id;
    }

    append(...nodes) {
        nodes.forEach((node) => {
            this.appendChild(node);
        });
    }

    appendChild(node) {
        this.children.push(node);
        node.parentNode = this;
        return node;
    }

    replaceChildren(...nodes) {
        this.children = [];
        nodes.forEach((node) => {
            this.appendChild(node);
        });
    }

    addEventListener(type, handler) {
        this.listeners.set(type, handler);
    }

    remove() {
        if (!this.parentNode) return;
        this.parentNode.children = this.parentNode.children.filter((child) => child !== this);
        this.parentNode = null;
    }

    get offsetWidth() {
        return 0;
    }
}

class FakeDocument {
    constructor() {
        this.elements = new Map();
        this.body = new FakeElement('body', this);
    }

    createElement(tagName) {
        return new FakeElement(tagName, this);
    }

    getElementById(id) {
        return this.elements.get(id) ?? null;
    }

    querySelectorAll(selector) {
        if (selector === '.close-device-modal-btn') {
            return [];
        }
        return [];
    }
}

function registerElement(document, id, tagName = 'div') {
    const element = document.createElement(tagName);
    element.id = id;
    return element;
}

test('stop-device confirmation is device-scoped and keeps device-scoped POST target', async () => {
    const document = new FakeDocument();
    registerElement(document, 'deviceDetailModal');
    registerElement(document, 'deviceDetailContent');
    registerElement(document, 'deviceDetailTitle');
    registerElement(document, 'stopDeviceTasksBtn', 'button');
    registerElement(document, 'enableDeviceBtn', 'button');
    registerElement(document, 'disableDeviceBtn', 'button');

    globalThis.document = document;
    globalThis.window = globalThis;
    globalThis.localStorage = {
        getItem: () => null,
        setItem: () => {},
        removeItem: () => {},
    };

    const confirmations = [];
    globalThis.confirm = (message) => {
        confirmations.push(message);
        return true;
    };

    const fetchCalls = [];
    globalThis.fetch = async (url, options = {}) => {
        fetchCalls.push({ url, options });
        return {
            ok: true,
            status: 200,
            text: async () => JSON.stringify({ cancelled_count: 2 }),
        };
    };

    const { bindDeviceModalActions } = await import('./device_detail_modal.js');

    let deviceChangedCalls = 0;
    bindDeviceModalActions({
        getCurrentUnit: () => ({ parent_id: 17, cloud_id: 3 }),
        onDeviceChanged: () => {
            deviceChangedCalls += 1;
        },
    });

    await document.getElementById('stopDeviceTasksBtn').onclick();

    assert.deepEqual(confirmations, ['确定要停止设备 #17 上正在运行的所有任务吗？']);
    assert.equal(confirmations[0].includes('云机 #17-3'), false);
    assert.equal(fetchCalls.length, 1);
    assert.equal(fetchCalls[0].url, '/api/tasks/device/17/stop');
    assert.equal(fetchCalls[0].options.method, 'POST');
    assert.equal(deviceChangedCalls, 1);
});
