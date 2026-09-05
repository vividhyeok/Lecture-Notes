/* Linking reads the top-level page only. Player frames are irrelevant. */
(() => {
  async function collect(chrome, tab) {
    async function read(frameId) {
      const target = {tabId: tab.id, frameIds: [frameId]};
      await chrome.scripting.executeScript({target, files: ['context.js']});
      const rows = await chrome.scripting.executeScript({target, func: () => globalThis.LectureContext?.read()});
      return rows[0]?.result;
    }
    let top;
    try { top = await read(0); }
    catch { return {error: '이 사이트의 접근 권한을 확인하세요. 확장 관리 → 사이트 액세스에서 현재 사이트를 허용한 뒤 페이지를 새로고침하세요.'}; }
    if (!top?.canBind) return null;
    return {...top, tabId: tab.id};
  }
  globalThis.LectureContextRouter = {collect};
})();
