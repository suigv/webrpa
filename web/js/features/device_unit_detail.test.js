import test from 'node:test';
import assert from 'node:assert/strict';

class FakeClassList {
    constructor() {
        this._classes = new Set();
    }

    add(name) {
        this._classes.add(name);
    }

    remove(name) {
        this._classes.delete(name);
    }

    contains(name) {
        return this._classes.has(name);
    }
}

class FakeElement {
    constructor(tagName = 'div', ownerDocument = null) {
        this.tagName = tagName.toUpperCase();
        this.ownerDocument = ownerDocument;
        this.children = [];
        this.style = {};
        this.dataset = {};
        this.textContent = '';
        this.onclick = null;
        this.onkeydown = null;
        this.parentNode = null;
        this.value = '';
        this.src = '';
        this.classList = new FakeClassList();
        this._id = '';
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
        nodes.forEach((node) => this.appendChild(node));
    }

    appendChild(node) {
        this.children.push(node);
        node.parentNode = this;
        return node;
    }

    replaceChildren(...nodes) {
        this.children = [];
        nodes.forEach((node) => this.appendChild(node));
    }

    querySelectorAll() {
        return [];
    }
}

class FakeDocument {
    constructor() {
        this.elements = new Map();
        this.visibilityState = 'visible';
        this.body = new FakeElement('body', this);
        this.body.dataset = {};
        this._tabPanes = [];
    }

    createElement(tagName) {
        return new FakeElement(tagName, this);
    }

    getElementById(id) {
        return this.elements.get(id) ?? null;
    }

    querySelectorAll(selector) {
        if (selector === '.tab-pane') {
            return this._tabPanes;
        }
        return [];
    }

    addEventListener() {}

    removeEventListener() {}
}

function registerElement(document, id, tagName = 'div') {
    const element = document.createElement(tagName);
    element.id = id;
    return element;
}

function installGlobals() {
    const document = new FakeDocument();
    const tabMain = registerElement(document, 'tab-main');
    tabMain.classList.add('tab-pane');
    tabMain.classList.add('active');
    document._tabPanes.push(tabMain);

    registerElement(document, 'unitDetailView');
    registerElement(document, 'detailUnitTitle');
    registerElement(document, 'unitLogBox');
    registerElement(document, 'submitSingleTask', 'button');
    registerElement(document, 'refreshScreenshot', 'button');
    registerElement(document, 'unitScreenshotImg', 'img');
    registerElement(document, 'unitScreenshotPlaceholder');
    registerElement(document, 'unitTextInput', 'input');
    registerElement(document, 'unitSendText', 'button');
    registerElement(document, 'unitKeyBack', 'button');
    registerElement(document, 'unitKeyHome', 'button');
    registerElement(document, 'unitKeyEnter', 'button');
    registerElement(document, 'unitKeyDelete', 'button');
    registerElement(document, 'unitSwipeUp', 'button');
    registerElement(document, 'unitSwipeLeft', 'button');
    registerElement(document, 'unitSwipeDown', 'button');
    registerElement(document, 'unitSwipeRight', 'button');

    globalThis.document = document;
    globalThis.window = globalThis;
    globalThis.scrollTo = () => {};
    globalThis.localStorage = {
        getItem: () => null,
        setItem: () => {},
        removeItem: () => {},
    };
    globalThis.fetch = async () => ({
        ok: false,
        status: 503,
        json: async () => ({ detail: 'device offline' }),
    });

    return document;
}

test('openUnitDetail relies on scoped account loading from renderUnitPluginFields only once', async () => {
    installGlobals();
    const { closeUnitDetail, openUnitDetail } = await import(`./device_unit_detail.js?case=${Date.now()}-accounts`);

    let renderCalls = 0;
    const loadAccountCalls = [];
    let currentUnit = null;

    openUnitDetail({
        unit: {
            parent_id: 12,
            cloud_id: 4,
            availability_state: 'available',
        },
        clearElement: () => {},
        buildUnitLogTarget: () => 'Unit #12-4',
        renderUnitPluginFields: () => {
            renderCalls += 1;
            loadAccountCalls.push('x');
        },
        loadUnitAccounts: async (appId) => {
            loadAccountCalls.push(appId);
        },
        submitUnitTask: () => {},
        setCurrentUnit: (unit) => {
            currentUnit = unit;
        },
    });

    assert.equal(renderCalls, 1);
    assert.deepEqual(loadAccountCalls, ['x']);
    assert.equal(currentUnit?.parent_id, 12);
    assert.equal(document.body.dataset.currentDeviceId, '12');
    assert.equal(document.body.dataset.currentCloudId, '4');

    closeUnitDetail({
        restoreMainTab: false,
        closeUnitAiDialog: () => {},
        loadDevices: () => {},
        setCurrentUnit: () => {},
    });
});
