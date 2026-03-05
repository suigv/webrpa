export class Toast {
    constructor() {
        this.container = document.createElement('div');
        this.container.className = 'toast-container';
        document.body.appendChild(this.container);
    }

    show(message, type = 'info', duration = 3000) {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;

        // Auto remove
        setTimeout(() => {
            toast.classList.add('hide');
            toast.addEventListener('transitionend', () => toast.remove());
        }, duration);

        this.container.appendChild(toast);
        // Trigger reflow for animation
        void toast.offsetWidth;
        toast.classList.add('show');
    }

    success(msg) { this.show(msg, 'success'); }
    error(msg) { this.show(msg, 'error', 5000); }
    info(msg) { this.show(msg, 'info'); }
    warn(msg) { this.show(msg, 'warn'); }
}

export const toast = new Toast();
