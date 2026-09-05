/* One blocked player/ad frame must not discard the accessible lecture page. */
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
    const frames = await chrome.webNavigation.getAllFrames({tabId: tab.id}).catch(() => []);
    const results = await Promise.allSettled((frames || []).filter(f => f.frameId !== 0).map(f => read(f.frameId)));
    const media = [top, ...results.filter(r => r.status === 'fulfilled').map(r => r.value)]
      .filter(c => c?.hasMedia).sort((a,b) => Number(a.paused)-Number(b.paused) || b.area-a.area)[0];
    if (!media && !top?.canBind) return null;
    return {...(media || top), course: top?.course || media?.course || '',
      title: top?.lecturePage ? top.title : media?.title || top?.title,
      module: top?.module || media?.module || '', pageKey: top?.pageKey || media?.pageKey,
      hasMedia: true, tabId: tab.id};
  }
  globalThis.LectureContextRouter = {collect};
})();
