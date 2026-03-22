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
        this.parentNode = null;
        this.listeners = new Map();
        this.dataset = {};
        this.classList = {
            contains: () => false,
            add: () => {},
        };
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
        this.body = new FakeElement('body', this);
    }

    createElement(tagName) {
        return new FakeElement(tagName, this);
    }

    getElementById() {
        return null;
    }

    querySelectorAll() {
        return [];
    }
}

function installGlobals(taskCatalog) {
    globalThis.document = new FakeDocument();
    globalThis.window = globalThis;
    globalThis.localStorage = {
        getItem: () => null,
        setItem: () => {},
        removeItem: () => {},
    };

    globalThis.fetch = async (url) => {
        if (url === '/api/tasks/catalog') {
            return {
                ok: true,
                status: 200,
                text: async () => JSON.stringify({ tasks: taskCatalog }),
            };
        }
        throw new Error(`Unexpected fetch URL: ${url}`);
    };
}

test('prepareTaskPayload strips runtime-only fields and keeps declared business/account fields', async () => {
    installGlobals([
        {
            task: 'one_click_new_device',
            inputs: [
                { name: 'account' },
                { name: 'password' },
                { name: 'twofa_secret' },
                { name: 'status_hint' },
            ],
        },
    ]);

    const { prepareTaskPayload } = await import(`./task_service.js?case=${Date.now()}-bulk`);
    const payload = await prepareTaskPayload('one_click_new_device', {
        rawPayload: {
            device_ip: '192.168.0.8',
            status_hint: 'runtime',
            ignored_field: 'drop-me',
        },
        account: {
            account: 'demo-account',
            password: 'demo-password',
            twofa: 'demo-twofa',
        },
        stripRuntimeOnly: true,
    });

    assert.deepEqual(payload, {
        account: 'demo-account',
        password: 'demo-password',
        twofa_secret: 'demo-twofa',
        status_hint: 'runtime',
    });
    assert.equal('device_ip' in payload, false);
    assert.equal('ignored_field' in payload, false);
});

test('prepareTaskPayload injects app_id only when the task declares it', async () => {
    installGlobals([
        {
            task: 'app_aware_task',
            inputs: [{ name: 'app_id' }, { name: 'account' }],
        },
        {
            task: 'plain_task',
            inputs: [{ name: 'account' }],
        },
    ]);

    const { prepareTaskPayload } = await import(`./task_service.js?case=${Date.now()}-app`);
    const declaredPayload = await prepareTaskPayload('app_aware_task', {
        rawPayload: {},
        appId: 'wechat',
    });
    const undeclaredPayload = await prepareTaskPayload('plain_task', {
        rawPayload: {},
        appId: 'wechat',
    });

    assert.deepEqual(declaredPayload, { app_id: 'wechat' });
    assert.deepEqual(undeclaredPayload, {});
});
