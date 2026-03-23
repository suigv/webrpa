import test from 'node:test';
import assert from 'node:assert/strict';

class FakeElement {
    constructor(tagName = 'div') {
        this.tagName = tagName.toUpperCase();
        this.children = [];
        this.style = {};
        this.className = '';
        this.textContent = '';
        this.parentNode = null;
    }

    append(...nodes) {
        nodes.forEach((node) => this.appendChild(node));
    }

    appendChild(node) {
        this.children.push(node);
        node.parentNode = this;
        return node;
    }

    remove() {
        if (!this.parentNode) return;
        this.parentNode.children = this.parentNode.children.filter((child) => child !== this);
        this.parentNode = null;
    }
}

function installGlobals() {
    globalThis.document = {
        visibilityState: 'visible',
        body: new FakeElement('body'),
        createElement: (tagName) => new FakeElement(tagName),
        addEventListener: () => {},
        removeEventListener: () => {},
    };
    globalThis.window = globalThis;
    globalThis.localStorage = {
        getItem: () => null,
        setItem: () => {},
        removeItem: () => {},
    };
    globalThis.fetch = async () => {
        throw new Error('unexpected network fetch');
    };
}

test('refreshDevicesSnapshot dedupes concurrent requests and updates shared snapshot', async () => {
    installGlobals();
    const devicesModule = await import(`./devices.js?case=${Date.now()}-dedupe`);
    devicesModule.__resetDevicesStateForTests();

    let calls = 0;
    let resolver = null;
    devicesModule.__setDevicesFetchImplForTests(() => {
        calls += 1;
        return new Promise((resolve) => {
            resolver = resolve;
        });
    });

    const first = devicesModule.refreshDevicesSnapshot({ force: true });
    const second = devicesModule.refreshDevicesSnapshot({ force: true });
    assert.equal(calls, 1);

    resolver({
        ok: true,
        data: [{ device_id: 1, cloud_machines: [{ cloud_id: 2, availability_state: 'available' }] }],
    });

    const [firstResult, secondResult] = await Promise.all([first, second]);
    assert.equal(firstResult.ok, true);
    assert.equal(secondResult.ok, true);
    assert.equal(devicesModule.getDevicesSnapshot().length, 1);
});

test('refreshDevicesSnapshot reuses fresh cache when maxAgeMs allows it', async () => {
    installGlobals();
    const devicesModule = await import(`./devices.js?case=${Date.now()}-cache`);
    devicesModule.__resetDevicesStateForTests();

    let calls = 0;
    devicesModule.__setDevicesFetchImplForTests(async () => {
        calls += 1;
        return {
            ok: true,
            data: [{ device_id: calls, cloud_machines: [] }],
        };
    });

    const first = await devicesModule.refreshDevicesSnapshot({ force: true });
    const second = await devicesModule.refreshDevicesSnapshot({ maxAgeMs: 10_000 });

    assert.equal(first.ok, true);
    assert.equal(second.ok, true);
    assert.equal(second.cached, true);
    assert.equal(calls, 1);
    assert.deepEqual(devicesModule.getDevicesSnapshot(), [{ device_id: 1, cloud_machines: [] }]);
});
