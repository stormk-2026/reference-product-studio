'use strict';
const filters = document.querySelectorAll('[data-filter]');
filters.forEach(button => button.addEventListener('click', () => {
  filters.forEach(item => item.setAttribute('aria-pressed', String(item === button)));
  let count = 0;
  document.querySelectorAll('[data-category]').forEach(card => {
    card.hidden = button.dataset.filter !== 'all' && card.dataset.category !== button.dataset.filter;
    if (!card.hidden) count++;
  });
  document.getElementById('filter-status').textContent = `显示 ${count} 个作品`;
}));
const viewer = document.getElementById('image-viewer');
document.querySelectorAll('[data-image]').forEach(button => button.addEventListener('click', () => {
  const img = document.getElementById('viewer-image');
  img.src = button.dataset.image; img.alt = button.dataset.caption;
  document.getElementById('viewer-caption').textContent = button.dataset.caption;
  viewer.showModal();
}));
viewer?.querySelector('button').addEventListener('click', () => viewer.close());
viewer?.addEventListener('click', event => { if (event.target === viewer) viewer.close(); });
document.getElementById('print-resume')?.addEventListener('click', () => window.print());

// Contact details stay usable even if clipboard access is unavailable.
const contactDialog = document.getElementById('contact-dialog');
document.querySelectorAll('[data-contact]').forEach(button => button.addEventListener('click', () => {
  contactDialog.querySelectorAll('[data-contact-pane]').forEach(pane => {
    pane.hidden = pane.dataset.contactPane !== button.dataset.contact;
  });
  document.getElementById('copy-status').textContent = '';
  contactDialog.showModal();
}));
contactDialog?.querySelector('[data-close-contact]').addEventListener('click', () => contactDialog.close());
contactDialog?.addEventListener('click', event => { if (event.target === contactDialog) contactDialog.close(); });
document.querySelectorAll('[data-copy]').forEach(button => button.addEventListener('click', async () => {
  const field = document.getElementById(button.dataset.copy);
  const status = document.getElementById('copy-status');
  try {
    await navigator.clipboard.writeText(field.value);
    status.textContent = button.dataset.copy === 'wechat-id' ? '微信号已复制，去微信搜索添加吧。' : '邮箱已复制。';
  } catch {
    field.focus(); field.select(); field.setSelectionRange(0, field.value.length);
    status.textContent = '已选中文字，请长按或按 Ctrl / ⌘ + C 复制。';
  }
}));

// Motion is optional, pauses in background tabs and never gates navigation.
const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
const motionButton = document.getElementById('motion-toggle');
const motionKey = 'storm-portfolio-motion';
let userPaused = false;
try { userPaused = localStorage.getItem(motionKey) === 'off'; } catch { /* private browsing */ }
let revealObserver;
function syncMotion() {
  const enabled = !motionPreference.matches && !userPaused;
  document.body.dataset.motion = enabled ? 'on' : 'off';
  motionButton.hidden = false;
  motionButton.disabled = motionPreference.matches;
  const label = motionPreference.matches ? '系统已减少动态效果' : enabled ? '暂停动效' : '开启动效';
  motionButton.setAttribute('aria-label', label);
  motionButton.setAttribute('aria-pressed', String(enabled));
  motionButton.dataset.label = label;
  if (!enabled) {
    revealObserver?.disconnect();
    document.querySelectorAll('.reveal-ready').forEach(el => el.classList.add('is-revealed'));
  }
}
syncMotion();
motionButton.addEventListener('click', () => {
  userPaused = !userPaused;
  try { localStorage.setItem(motionKey, userPaused ? 'off' : 'on'); } catch { /* optional setting */ }
  syncMotion();
});
motionPreference.addEventListener('change', syncMotion);
document.addEventListener('visibilitychange', () => document.body.classList.toggle('motion-suspended', document.hidden));
if ('IntersectionObserver' in window && document.body.dataset.motion === 'on') {
  revealObserver = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      entry.target.classList.add('is-revealed');
      revealObserver.unobserve(entry.target);
    }
  }, {threshold:0.06, rootMargin:'0px 0px -24px 0px'});
  document.querySelectorAll('.section-heading,.project-card,.tool-feature,.commercial-card,.story-section,.demo-section,.tool-row,.timeline article,.engineering,.experience-card,.workspace-entry,.contact-strip').forEach(el => {
    if (el.getBoundingClientRect().top < innerHeight - 24) return;
    el.classList.add('reveal-ready'); revealObserver.observe(el);
  });
}
// Filtered-in cards must be visible even when they were hidden at initialization.
filters.forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('[data-category]:not([hidden])').forEach(card => card.classList.add('is-revealed'));
}));
const showcase = document.querySelector('.hero-showcase');
if (showcase && window.matchMedia('(hover: hover) and (pointer: fine)').matches) {
  let frame;
  showcase.addEventListener('pointermove', event => {
    if (document.body.dataset.motion !== 'on') return;
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      const box = showcase.getBoundingClientRect();
      showcase.style.setProperty('--look-x', `${((event.clientX - box.left) / box.width - .5) * 5}deg`);
      showcase.style.setProperty('--look-y', `${-((event.clientY - box.top) / box.height - .5) * 4}deg`);
    });
  });
  showcase.addEventListener('pointerleave', () => {
    cancelAnimationFrame(frame);
    showcase.style.setProperty('--look-x', '0deg'); showcase.style.setProperty('--look-y', '0deg');
  });
}
