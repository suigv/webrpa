export class Store {
    constructor() {
        this.state = {
            currentTab: 'tab-main',
            currentUnitLogTarget: '',
        };
        this.listeners = new Set();
    }

    getState() {
        return this.state;
    }

    setState(partialState) {
        this.state = { ...this.state, ...partialState };
        this.notify();
    }

    subscribe(listener) {
        this.listeners.add(listener);
        // Returns unsubscribe function
        return () => this.listeners.delete(listener);
    }

    notify() {
        for (const listener of this.listeners) {
            listener(this.state);
        }
    }
}

export const store = new Store();
