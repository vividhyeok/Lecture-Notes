(() => {
  const normalize = value => String(value || '').normalize('NFKC').toLocaleLowerCase().replace(/\.(mp3|mp4|m4a|wav|webm|md|txt)$/i, '').replace(/[\s_\-·]+/g, ' ').trim();
  function identity(c) { return JSON.stringify([c?.pageKey || '', c?.mediaKey || '', normalize(c?.course), normalize(c?.title)]); }
  function matches(binding, c) {
    return Boolean(binding.pageKey && binding.pageKey === c.pageKey);
  }
  function find(lectures, c) {
    if (!c?.canBind || !c.title) return null;
    const linked = lectures.filter(l => (l.bindings || []).some(b => matches(b, c)));
    if (linked.length) return linked.length === 1 ? linked[0] : null;
    if (!c.course) return null;
    const exact = lectures.filter(l => normalize(l.course) === normalize(c.course) && normalize(l.title) === normalize(c.title));
    return exact.length === 1 ? exact[0] : null;
  }
  function ordered(lectures, course) {
    return lectures.filter(l => normalize(l.course) === normalize(course)).slice().sort((a,b) => a.title.localeCompare(b.title, 'ko', {numeric:true, sensitivity:'base'}) || a.created-b.created);
  }
  globalThis.LectureNavigation = { normalize, identity, matches, find, ordered };

  if (typeof document === 'undefined') return;

  const HIDE_UNCLASSIFIED = 'lecture-notes-hide-unclassified';
  const iconButtons = {
    copyCorrection: ['⎘', 'GPT 보정용 프롬프트 복사'],
    pasteCorrection: ['⇩', '보정본 붙여넣기'],
    editNote: ['✎', '노트 편집'],
    exportNote: ['↓', 'Markdown 파일로 저장'],
    reorganizeNote: ['✦', 'AI로 강의노트 다시 정리'],
    bindTab: ['⌁', '현재 강의 페이지와 연결'],
    openLectureFolder: ['▣', '원본 폴더 열기'],
    renameLecture: ['≡', '과목·강의명 정리'],
    attachExisting: ['＋', '기존 노트·전사본 연결'],
    printNote: ['⎙', 'A4 인쇄 / PDF'],
    openVideo: ['▶', '연결된 강의 영상 열기'],
  };

  function injectStyles() {
    const style = document.createElement('style');
    style.textContent = `
      .icon-button { width: 36px; min-width: 36px; height: 34px; padding: 0; display: inline-flex; align-items: center; justify-content: center; font-size: 17px; line-height: 1; border-radius: 9px; }
      .reader-tools { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
      #noteTools > summary { width: max-content; min-width: 36px; padding-inline: 10px; cursor: pointer; }
      .compact-preference { margin: 8px 0; }
      .compact-preference + .muted { margin-top: -2px; }
      #toggleUnclassified { white-space: nowrap; }
      .cleanup-row { display: flex; justify-content: flex-end; margin-top: 6px; }
    `;
    document.head.append(style);
  }

  function compactReaderTools() {
    for (const [id, [glyph, label]] of Object.entries(iconButtons)) {
      const button = document.getElementById(id);
      if (!button) continue;
      const existing = button.title;
      button.textContent = glyph;
      button.classList.add('icon-button');
      button.setAttribute('aria-label', label);
      button.title = existing ? label + '\n' + existing : label;
    }
    const summary = document.querySelector('#noteTools > summary');
    if (summary) {
      summary.textContent = '⋯';
      summary.title = '노트 도구 및 보기 설정';
      summary.setAttribute('aria-label', '노트 도구 및 보기 설정');
    }
  }

  function improveOfflineMessage() {
    const offline = document.getElementById('offline');
    if (!offline) return;
    const title = offline.querySelector('h2');
    const text = offline.querySelector('p');
    if (title) title.textContent = 'Lecture Notes가 꺼져 있습니다';
    if (text) text.textContent = '보통 Windows 로그인 시 자동으로 켜집니다. 계속 오프라인이면 시작 메뉴에서 “Lecture Notes”를 검색해 실행한 뒤 다시 확인하세요. 프로젝트 폴더를 찾을 필요는 없습니다.';
    const reconnect = document.getElementById('reconnect');
    if (reconnect) reconnect.textContent = '다시 확인';
  }

  function addWatchPreference() {
    const input = document.getElementById('watchFolder');
    if (!input || document.getElementById('watchAllFiles')) return;
    const label = document.createElement('label');
    label.className = 'check compact-preference';
    const check = document.createElement('input');
    check.type = 'checkbox';
    check.id = 'watchAllFiles';
    label.append(check, document.createTextNode('다운로드 폴더의 모든 지원 파일 자동 가져오기'));
    const hint = document.createElement('p');
    hint.className = 'muted';
    hint.textContent = '기본값은 꺼짐입니다. 꺼두면 일반 MP3·영상은 무시하고, 확장 프로그램이 강의로 확인한 다운로드만 가져옵니다.';
    const anchor = input.closest('label')?.nextElementSibling || input.closest('label');
    anchor?.after(label, hint);
    check.onchange = async () => {
      try {
        await api('settings', { watch_all_files: check.checked });
        await refresh();
        toast(check.checked ? '다운로드 폴더 전체 감시를 켰습니다.' : '강의로 확인된 다운로드만 가져옵니다.');
      } catch (error) {
        check.checked = !check.checked;
        toast(error.message);
      }
    };
    setInterval(() => {
      try {
        if (state?.settings) check.checked = Boolean(state.settings.watch_all_files);
      } catch {}
    }, 1200);
  }

  function addYoutubePreference() {
    if (!globalThis.chrome?.runtime?.id || document.getElementById('downloadImportYoutube')) return;
    const main = document.getElementById('downloadImportLabel');
    if (!main) return;
    const label = document.createElement('label');
    label.className = 'check compact-preference';
    const check = document.createElement('input');
    check.type = 'checkbox';
    check.id = 'downloadImportYoutube';
    label.append(check, document.createTextNode('YouTube 다운로드도 자동 가져오기'));
    const hint = document.createElement('p');
    hint.className = 'muted';
    hint.textContent = '기본은 꺼짐입니다. 음악 다운로드가 강의로 섞이는 것을 막습니다. YouTube 강의를 자주 저장할 때만 켜세요.';
    main.after(label, hint);
    chrome.storage.local.get('downloadImportYoutube').then(value => {
      check.checked = Boolean(value.downloadImportYoutube);
    });
    check.onchange = () => chrome.storage.local.set({downloadImportYoutube: check.checked});
  }

  function applyUnclassifiedVisibility() {
    const hidden = localStorage.getItem(HIDE_UNCLASSIFIED) === '1';
    document.querySelectorAll('#lectureList .course-folder').forEach(folder => {
      const summary = folder.querySelector(':scope > summary');
      if (summary?.textContent?.trim().startsWith('미분류 ·')) folder.hidden = hidden;
    });
    const button = document.getElementById('toggleUnclassified');
    if (button) {
      button.textContent = hidden ? '미분류 표시' : '미분류 숨기기';
      button.title = hidden ? '숨긴 미분류 강의를 다시 표시합니다.' : '미분류 묶음을 목록에서만 숨깁니다. 파일은 삭제하지 않습니다.';
    }
  }

  function addUnclassifiedToggle() {
    if (document.getElementById('toggleUnclassified')) return;
    const list = document.getElementById('lectureList');
    if (!list) return;
    const row = document.createElement('div');
    row.className = 'cleanup-row';
    const button = document.createElement('button');
    button.id = 'toggleUnclassified';
    button.className = 'quiet';
    button.onclick = () => {
      const next = localStorage.getItem(HIDE_UNCLASSIFIED) === '1' ? '0' : '1';
      localStorage.setItem(HIDE_UNCLASSIFIED, next);
      applyUnclassifiedVisibility();
    };
    row.append(button);
    list.after(row);
    new MutationObserver(applyUnclassifiedVisibility).observe(list, {childList: true, subtree: true});
    applyUnclassifiedVisibility();
  }

  document.addEventListener('DOMContentLoaded', () => {
    injectStyles();
    compactReaderTools();
    improveOfflineMessage();
    addWatchPreference();
    addYoutubePreference();
    addUnclassifiedToggle();

    document.addEventListener('keydown', event => {
      const tag = document.activeElement?.tagName;
      if (event.key === '/' && !event.ctrlKey && !event.metaKey && !['INPUT', 'TEXTAREA'].includes(tag)) {
        const search = document.getElementById('search');
        if (search && !document.getElementById('libraryView')?.hidden) {
          event.preventDefault();
          search.focus();
        }
      }
    });
  });
})();
