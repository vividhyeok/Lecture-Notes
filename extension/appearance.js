/* Display preferences are local to this PC/browser, never part of the vault. */
(() => {
  // navigation.js used to run three cosmetic maintenance loops every 0.8–1.1s.
  // Convert just those known loops to state-update events before navigation.js
  // registers them. The normal 3s panel polling timer is left untouched.
  const nativeSetInterval = globalThis.setInterval.bind(globalThis);
  const eventDrivenDelays = new Set([800, 1000, 1100]);
  globalThis.__LN_NATIVE_SET_INTERVAL__ = nativeSetInterval;
  globalThis.setInterval = (callback, delay, ...args) => {
    if (!eventDrivenDelays.has(Number(delay)))
      return nativeSetInterval(callback, delay, ...args);
    const run = () => callback(...args);
    document.addEventListener("lecture-notes:state-updated", run);
    queueMicrotask(run);
    return 0;
  };

  const root = document.documentElement;
  const system = matchMedia('(prefers-color-scheme: dark)');
  let prefs = {};
  try { prefs = JSON.parse(localStorage.getItem('lecture-display') || '{}'); } catch {}
  let theme = ['auto', 'light', 'dark'].includes(prefs.theme) ? prefs.theme : 'auto';
  let scale = Number.isFinite(prefs.scale) ? Math.min(160, Math.max(80, prefs.scale)) : 100;
  function apply() {
    root.dataset.theme = theme === 'auto' ? (system.matches ? 'dark' : 'light') : theme;
    root.style.setProperty('--note-size', (14 * scale / 100) + 'px');
    document.getElementById('themeToggle').textContent = { auto: '자동 테마', light: '밝은 테마', dark: '다크 모드' }[theme];
    document.getElementById('themeToggle').title = '클릭하여 자동 → 밝게 → 어둡게 전환';
    document.getElementById('fontReset').textContent = scale + '%';
    document.getElementById('fontDecrease').disabled = scale <= 80;
    document.getElementById('fontIncrease').disabled = scale >= 160;
    try { localStorage.setItem('lecture-display', JSON.stringify({ theme, scale })); } catch {}
  }
  document.getElementById('themeToggle').onclick = () => { theme = { auto: 'light', light: 'dark', dark: 'auto' }[theme]; apply(); };
  document.getElementById('fontDecrease').onclick = () => { scale = Math.max(80, scale - 10); apply(); };
  document.getElementById('fontIncrease').onclick = () => { scale = Math.min(160, scale + 10); apply(); };
  document.getElementById('fontReset').onclick = () => { scale = 100; apply(); };
  system.addEventListener('change', apply);
  apply();

  // performance.js depends on panel.js globals. Load it only after all parser
  // scripts have completed, then it can wrap refresh/render safely.
  window.addEventListener('load', () => {
    const script = document.createElement('script');
    script.src = 'performance.js';
    document.body.append(script);
  }, { once: true });
})();
