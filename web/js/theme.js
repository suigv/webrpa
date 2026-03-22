const ThemeManager = {
  STORAGE_KEY: 'webrpa-theme',
  THEMES: {
    GLASS: 'glass',
    MINIMAL: 'minimal'
  },
  currentTheme: 'glass',
  
  init() {
    const saved = localStorage.getItem(this.STORAGE_KEY);
    if (saved && Object.values(this.THEMES).includes(saved)) {
      this.currentTheme = saved;
    }
    this.applyTheme(this.currentTheme);
    this.updateLabel();
    
    const btn = document.getElementById('themeToggle');
    if (btn) btn.addEventListener('click', () => this.toggle());
  },
  
  toggle() {
    const newTheme = this.currentTheme === this.THEMES.GLASS 
      ? this.THEMES.MINIMAL 
      : this.THEMES.GLASS;
    this.setTheme(newTheme);
  },
  
  setTheme(theme) {
    if (!Object.values(this.THEMES).includes(theme)) return;
    this.currentTheme = theme;
    localStorage.setItem(this.STORAGE_KEY, theme);
    this.applyTheme(theme);
    this.updateLabel();
  },
  
  applyTheme(theme) {
    const html = document.documentElement;
    if (theme === 'minimal') {
      html.setAttribute('data-theme', 'minimal');
    } else {
      html.removeAttribute('data-theme');
    }
  },
  
  updateLabel() {
    const label = document.getElementById('themeLabel');
    if (label) {
      label.textContent = this.currentTheme === 'glass' ? '玻璃' : '简约';
    }
  }
};

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => ThemeManager.init());
} else {
  ThemeManager.init();
}

window.ThemeManager = ThemeManager;
