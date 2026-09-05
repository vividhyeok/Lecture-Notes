/* Linking reads the top-level page only. Player frames are irrelevant. */
(() => {
  async function current(chrome) {
    const [tab] = await chrome.tabs.query({active:true,currentWindow:true});
    if (!tab?.url) return {error:'현재 탭 주소를 읽지 못했습니다. 확장 관리에서 Lecture Notes를 새로고침하세요.'};
    const url = new URL(tab.url);
    const hosts = ['jnuclass.jejunu.ac.kr','canvas.jejunu.ac.kr','canvas.jnu.ac.kr','common.jejunu.ac.kr','youtube.com','www.youtube.com','m.youtube.com','youtu.be'];
    if (url.protocol !== 'https:' || !hosts.includes(url.hostname)) return {error:'현재 탭: '+(tab.title || url.hostname)+' · 연결할 강의 탭을 선택하세요.'};
    return collect(chrome,tab);
  }
  async function collect(chrome, tab) {
    let fallback;
    try {
      const url = new URL(tab.url);
      const youtube = ['youtube.com','www.youtube.com','m.youtube.com','youtu.be'].includes(url.hostname);
      const id = youtube && (url.hostname === 'youtu.be' ? url.pathname.slice(1) : url.searchParams.get('v') || url.pathname.match(/^\/(?:shorts|live|embed)\/([^/]+)/)?.[1]);
      const query = new URLSearchParams();
      for (const key of ['id','course_id','lecture_id','video_id','content_id','module_item_id']) if (url.searchParams.has(key)) query.set(key,url.searchParams.get(key));
      query.sort();
      const pageKey = youtube ? (/^[A-Za-z0-9_-]{11}$/.test(id || '') ? 'https://www.youtube.com/watch?v='+id : '') : url.origin+url.pathname+(query.size?'?'+query:'');
      if (pageKey) fallback = {pageKey,title:tab.title || url.pathname.split('/').filter(Boolean).at(-1),course:youtube?'youtube':'',module:'',mediaKey:'',canBind:true,tabId:tab.id};
    } catch {}
    async function read(frameId) {
      const target = {tabId: tab.id, frameIds: [frameId]};
      await chrome.scripting.executeScript({target, files: ['context.js']});
      const rows = await chrome.scripting.executeScript({target, func: () => globalThis.LectureContext?.read()});
      return rows[0]?.result;
    }
    let top;
    try { top = await read(0); }
    catch { return fallback || {error: '현재 페이지 주소를 읽지 못했습니다. 확장 관리에서 Lecture Notes를 새로고침하세요.'}; }
    if (!top?.canBind) return fallback || null;
    return {...top, tabId: tab.id};
  }
  globalThis.LectureContextRouter = {collect,current};
})();
