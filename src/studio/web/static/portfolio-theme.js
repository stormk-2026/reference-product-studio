// Runs before styles load so a saved dark theme never flashes a light page.
'use strict';
(() => {
  const root = document.documentElement;
  const key = 'storm-portfolio-theme';
  const system = window.matchMedia('(prefers-color-scheme: dark)');
  const valid = value => value === 'light' || value === 'dark' ? value : null;
  let preference = null;
  try { preference = valid(localStorage.getItem(key)); } catch { /* storage is optional */ }
  function apply() {
    const theme = preference || (system.matches ? 'dark' : 'light');
    root.dataset.theme = theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#101916' : '#f4f7f4');
    const button = document.getElementById('theme-toggle');
    if (button) {
      const label = theme === 'dark' ? '切换为浅色主题' : '切换为深色主题';
      button.hidden = false;
      button.setAttribute('aria-label', label);
      button.title = label;
    }
  }
  apply();
  system.addEventListener('change', apply);
  window.addEventListener('storage', event => {
    if (event.key === key || event.key === null) {
      preference = valid(event.newValue);
      apply();
    }
  });
  document.addEventListener('DOMContentLoaded', () => {
    apply();
    document.getElementById('theme-toggle')?.addEventListener('click', () => {
      preference = root.dataset.theme === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem(key, preference); } catch { /* still switch for this page */ }
      apply();
    });
  }, {once: true});
})();
