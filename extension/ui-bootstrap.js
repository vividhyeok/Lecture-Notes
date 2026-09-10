"use strict";
(() => {
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
})();
