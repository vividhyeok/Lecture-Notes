/* Same title discovery order as the user's Lecture Notifier, plus stable identities. */
(() => {
  const text = value => String(value || '').replace(/https?:\/\/\S+/gi, '').replace(/\s+/g, ' ').trim().slice(0, 160);
  function stable(value) {
    try {
      const url = new URL(value, location.href);
      if (!['https:', 'http:'].includes(url.protocol)) return '';
      if (['www.youtube.com', 'm.youtube.com', 'youtube.com', 'youtu.be'].includes(url.hostname)) {
        const id = url.hostname === 'youtu.be' ? url.pathname.split('/')[1] : url.searchParams.get('v') || url.pathname.match(/^\/(?:shorts|embed|live)\/([^/]+)/)?.[1];
        return /^[A-Za-z0-9_-]{11}$/.test(id || '') ? 'https://www.youtube.com/watch?v=' + id : '';
      }
      // Never persist signed URLs, session tokens or access credentials.
      const allowed = ['id', 'course_id', 'lecture_id', 'video_id', 'content_id', 'module_item_id'];
      const query = new URLSearchParams();
      for (const key of allowed) if (url.searchParams.has(key)) query.set(key, url.searchParams.get(key));
      query.sort();
      return url.origin + url.pathname + (query.size ? '?' + query : '');
    } catch { return ''; }
  }
  function read(media) {
    const crumbNodes = [...document.querySelectorAll('#breadcrumbs a,[aria-label*="breadcrumb" i] a,.breadcrumbs a,.breadcrumb a')];
    const crumbs = crumbNodes.map(n => text(n.textContent)).filter(Boolean);
    const coursePath = location.pathname.match(/^\/courses\/\d+/)?.[0];
    const courseNode = coursePath && crumbNodes.find(n => {
      try { return new URL(n.href, location.href).pathname.replace(/\/$/, '') === coursePath; } catch { return false; }
    });
    const youtube = ['www.youtube.com', 'm.youtube.com', 'youtube.com', 'youtu.be'].includes(location.hostname);
    const youtubeTitle = youtube ? text(document.querySelector('ytd-watch-metadata h1, h1.ytd-watch-metadata')?.textContent) || text(document.title).replace(/ - YouTube$/, '') : '';
    const pageTitle = text(document.querySelector('main h1,[role="main"] h1,h1,main h2')?.textContent);
    const lmsLecture = Boolean(coursePath && /^\/courses\/\d+\/(?:modules\/items|external_tools)\/\d+/.test(location.pathname));
    const youtubeLecture = youtube && /^https:\/\/www\.youtube\.com\/watch\?v=/.test(stable(location.href)) && Boolean(youtubeTitle);
    return {
      course: youtube ? 'youtube' : text(courseNode?.textContent) || (crumbs.length > 1 ? crumbs[1] : ''),
      module: crumbs.length > 2 ? crumbs.at(-2) : '',
      title: youtubeTitle || pageTitle || crumbs.at(-1) || text(document.title),
      pageKey: stable(location.href), mediaKey: '',
      hasMedia: Boolean(media), area: media ? media.clientWidth * media.clientHeight : 0,
      canBind: Boolean(stable(location.href) && (youtubeTitle || pageTitle || document.title)), lecturePage: lmsLecture || youtubeLecture,
      currentTime: Number(media?.currentTime) || 0,
      duration: Number.isFinite(media?.duration) ? media.duration : 0,
      paused: media ? media.paused : true,
    };
  }
  globalThis.LectureContext = { read };
})();
