(() => {
  const normalize = value => String(value || '').normalize('NFKC').toLocaleLowerCase().replace(/\.(mp3|mp4|m4a|wav|webm|md|txt)$/i, '').replace(/[\s_\-·]+/g, ' ').trim();
  function identity(c) { return JSON.stringify([c?.pageKey || '', c?.mediaKey || '', normalize(c?.course), normalize(c?.title)]); }
  function matches(binding, c) { return Boolean(binding.pageKey && binding.pageKey === c.pageKey); }
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

  const QUALITY = {
    fast: ['빠름', 'gpt-5.6-luna', '비용을 가장 아끼는 일상 강의 정리'],
    balanced: ['균형', 'gpt-5.6-terra', '기본 추천 · 품질과 비용의 균형'],
    precise: ['정밀', 'gpt-5.6-sol', '복잡한 강의·시험 범위에 더 높은 품질'],
    custom: ['직접 지정', '', '고급 사용자용 모델 ID 직접 입력'],
  };
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
  const setText = (node, value) => {
    if (node && node.textContent !== value) node.textContent = value;
  };

  function injectStyles() {
    const style = document.createElement('style');
    style.textContent = `
      .icon-button { width: 36px; min-width: 36px; height: 34px; padding: 0; display: inline-flex; align-items: center; justify-content: center; font-size: 17px; line-height: 1; border-radius: 9px; }
      .reader-tools { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
      #noteTools > summary { width: max-content; min-width: 36px; padding-inline: 10px; cursor: pointer; }
      .compact-preference { margin: 8px 0; }
      .compact-preference + .muted { margin-top: -2px; }
      .cleanup-row { display: flex; flex-wrap: wrap; gap: 6px; justify-content: flex-end; margin: 8px 0 2px; }
      .archive-row-button { width: 34px; min-width: 34px; padding-inline: 0; align-self: stretch; }
      .lecture-item.pipeline-running span { font-weight: 600; }
      .lecture-item.pipeline-error span { font-weight: 600; }
      .quality-row { display: grid; gap: 5px; margin: 10px 0; }
      .quality-row select { width: 100%; }
      .archive-mode-note { margin: 4px 0 10px; }
      .jobs[hidden] { display: none; }
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

  function improveStaticCopy() {
    const offline = document.getElementById('offline');
    if (offline) {
      const title = offline.querySelector('h2');
      const text = offline.querySelector('p');
      if (title) title.textContent = 'Lecture Notes가 꺼져 있습니다';
      if (text) text.textContent = '보통 Windows 로그인 시 자동으로 켜집니다. 계속 오프라인이면 시작 메뉴에서 “Lecture Notes”를 검색해 실행한 뒤 다시 확인하세요. 프로젝트 폴더를 찾을 필요는 없습니다.';
      const reconnect = document.getElementById('reconnect');
      if (reconnect) reconnect.textContent = '다시 확인';
    }
    const watch = document.getElementById('watchFolder');
    const watchHint = watch?.closest('label')?.nextElementSibling;
    if (watchHint?.classList.contains('muted')) {
      watchHint.textContent = 'DownloadHelper가 저장하는 폴더를 지정합니다. 기본 상태에서는 이 폴더를 통째로 감시하지 않고, 확장 프로그램이 실제 강의 페이지에서 시작된 다운로드라고 확인한 파일만 가져옵니다.';
    }
    const stop = document.getElementById('stopServer');
    const stopHint = stop?.previousElementSibling;
    if (stopHint?.classList.contains('muted')) {
      stopHint.textContent = '서버가 꺼져도 노트는 유지됩니다. 다음 Windows 로그인 때 자동 시작하며, 바로 다시 켜려면 시작 메뉴에서 “Lecture Notes”를 실행하세요.';
    }
    const importLabel = document.getElementById('downloadImportLabel');
    const importInput = document.getElementById('downloadImport');
    if (importLabel && importInput) {
      importLabel.replaceChildren(importInput, document.createTextNode('강의 페이지의 DownloadHelper 다운로드 자동 가져오기'));
    }
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
    hint.textContent = '권장: 끄기. 켜면 지정 폴더의 일반 MP3·영상도 강의 후보가 될 수 있습니다.';
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
    hint.textContent = '기본은 꺼짐입니다. 음악 다운로드가 강의로 섞이는 것을 막습니다. YouTube 강의를 저장할 때만 켜세요.';
    main.after(label, hint);
    chrome.storage.local.get('downloadImportYoutube').then(value => {
      check.checked = Boolean(value.downloadImportYoutube);
    });
    check.onchange = () => chrome.storage.local.set({downloadImportYoutube: check.checked});
  }

  function addQualityControls() {
    const model = document.getElementById('textModel');
    if (!model || document.getElementById('qualityPreset')) return;
    const modelLabel = model.closest('label');
    const row = document.createElement('label');
    row.className = 'quality-row';
    row.append(document.createTextNode('AI 정리 품질'));
    const select = document.createElement('select');
    select.id = 'qualityPreset';
    for (const [value, [label]] of Object.entries(QUALITY)) {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = label;
      select.append(option);
    }
    // The migrated/default backend preset is balanced. Set the same fallback
    // synchronously so the UI never flashes “fast” before the first state fetch.
    select.value = 'balanced';
    const hint = document.createElement('span');
    hint.className = 'muted';
    hint.textContent = QUALITY.balanced[2];
    row.append(select, hint);
    modelLabel?.before(row);

    const finalLabel = document.createElement('label');
    finalLabel.className = 'check compact-preference';
    const finalCheck = document.createElement('input');
    finalCheck.id = 'finalizeLongNotes';
    finalCheck.type = 'checkbox';
    finalCheck.checked = true;
    finalLabel.append(finalCheck, document.createTextNode('긴 강의노트 최종 일관성 정리'));
    const finalHint = document.createElement('p');
    finalHint.className = 'muted';
    finalHint.textContent = '긴 강의를 구간별로 정리한 뒤 제목·용어·계층을 한 번 더 맞춥니다. 추가 API 호출이 발생하지만 긴 노트의 연결감이 좋아집니다.';
    (modelLabel?.nextElementSibling || modelLabel)?.after(finalLabel, finalHint);

    const sync = () => {
      if (!state?.settings) return;
      const preset = state.settings.quality_preset || 'custom';
      if (select.value !== (QUALITY[preset] ? preset : 'custom')) select.value = QUALITY[preset] ? preset : 'custom';
      setText(hint, QUALITY[select.value]?.[2] || '');
      finalCheck.checked = Boolean(state.settings.finalize_long_notes);
      if (modelLabel) modelLabel.hidden = select.value !== 'custom';
    };
    select.onchange = async () => {
      try {
        const preset = select.value;
        setText(hint, QUALITY[preset][2]);
        if (modelLabel) modelLabel.hidden = preset !== 'custom';
        if (preset !== 'custom') {
          model.value = QUALITY[preset][1];
          await api('settings', {quality_preset: preset});
          await refresh();
          toast('AI 정리 품질을 ' + QUALITY[preset][0] + '으로 설정했습니다.');
        }
      } catch (error) { toast(error.message); }
    };
    finalCheck.onchange = async () => {
      try {
        await api('settings', {finalize_long_notes: finalCheck.checked});
        await refresh();
      } catch (error) {
        finalCheck.checked = !finalCheck.checked;
        toast(error.message);
      }
    };
    setInterval(sync, 1000);
    sync();
  }

  function addArchiveControls() {
    if (document.getElementById('archiveToggle')) return;
    const title = document.querySelector('#libraryView .section-title');
    if (!title) return;
    const toggle = document.createElement('button');
    toggle.id = 'archiveToggle';
    toggle.className = 'quiet';
    toggle.onclick = async () => {
      try {
        await api('settings', {archive_view: !Boolean(state?.settings?.archive_view)});
        current = null;
        await refresh();
      } catch (error) { toast(error.message); }
    };
    title.append(toggle);

    const list = document.getElementById('lectureList');
    const row = document.createElement('div');
    row.className = 'cleanup-row';
    const unclassified = document.createElement('button');
    unclassified.id = 'archiveUnclassified';
    unclassified.className = 'quiet';
    unclassified.textContent = '미분류 전체 보관';
    unclassified.title = '미분류 강의를 보관함으로 옮깁니다. 파일과 Obsidian 노트는 삭제하지 않습니다.';
    unclassified.onclick = async () => {
      if (!confirm('미분류 강의를 모두 보관함으로 옮길까요? 파일은 삭제되지 않습니다.')) return;
      try {
        await api('settings', {archive_unclassified: true});
        await refresh();
        toast('미분류 강의를 보관함으로 옮겼습니다.');
      } catch (error) { toast(error.message); }
    };
    const restoreAll = document.createElement('button');
    restoreAll.id = 'restoreAllArchived';
    restoreAll.className = 'quiet';
    restoreAll.textContent = '모두 복원';
    restoreAll.onclick = async () => {
      if (!confirm('보관된 강의를 모두 내 강의로 복원할까요?')) return;
      try {
        await api('settings', {restore_all_archived: true});
        await refresh();
      } catch (error) { toast(error.message); }
    };
    row.append(unclassified, restoreAll);
    list?.after(row);

    const archiveCurrent = document.createElement('button');
    archiveCurrent.id = 'archiveCurrent';
    archiveCurrent.className = 'quiet icon-button';
    document.querySelector('.reader-tools')?.append(archiveCurrent);
    archiveCurrent.onclick = async () => {
      if (!current) return;
      const restoring = Boolean(current.archived);
      try {
        await api('settings', restoring ? {restore_id: current.id} : {archive_id: current.id});
        current = null;
        show('library');
        await refresh();
        toast(restoring ? '강의를 복원했습니다.' : '강의를 보관했습니다. 파일은 그대로 유지됩니다.');
      } catch (error) { toast(error.message); }
    };

    setInterval(() => {
      if (!state?.settings) return;
      const archived = Boolean(state.settings.archive_view);
      setText(toggle, archived ? '← 내 강의' : `보관함 ${state.settings.archived_count || 0}`);
      toggle.title = archived ? '활성 강의 목록으로 돌아갑니다.' : '보관한 강의를 봅니다.';
      unclassified.hidden = archived || !state.lectures.some(l => !l.course || l.course === '미분류');
      restoreAll.hidden = !archived || !state.lectures.length;
      setText(archiveCurrent, current?.archived ? '↩' : '⌄');
      archiveCurrent.title = current?.archived ? '이 강의를 내 강의로 복원' : '이 강의를 보관함으로 이동';
      archiveCurrent.setAttribute('aria-label', archiveCurrent.title);
    }, 800);
  }

  function decorateLibrary() {
    if (!state?.lectures) return;
    const archiveView = Boolean(state.settings?.archive_view);
    document.querySelectorAll('#lectureList .course-folder').forEach(folder => {
      const summary = folder.querySelector(':scope > summary');
      const course = summary?.textContent?.replace(/ · \d+$/, '') || '';
      const lectures = state.lectures
        .filter(l => (l.course || '미분류') === course)
        .sort((a,b) => a.title.localeCompare(b.title, 'ko', {numeric:true}));
      const rows = [...folder.querySelectorAll(':scope > .lecture-row')];
      rows.forEach((row, index) => {
        const lecture = lectures[index];
        const item = row.querySelector('.lecture-item');
        if (!lecture || !item) return;
        const info = item.querySelector('span');
        const job = state.jobs?.find(j => j.target === lecture.id && ['running','queued','error'].includes(j.status));
        item.classList.toggle('pipeline-running', job?.status === 'running' || job?.status === 'queued');
        item.classList.toggle('pipeline-error', job?.status === 'error');
        let status;
        if (job?.status === 'error') status = '처리 실패 · 처리 상태에서 재시도';
        else if (job?.status === 'running') status = '처리 중 · ' + job.progress;
        else if (job?.status === 'queued') status = '처리 대기 · ' + job.progress;
        else if (lecture.sync_status) status = lecture.sync_status;
        else if (lecture.has_notes) status = '완료 · 노트 준비됨';
        else if (lecture.has_transcript) status = '전사 완료 · 노트 작성 대기';
        else status = '다운로드 완료 · 전사 대기';
        if ((lecture.bindings || []).length && !lecture.sync_status) status += ' · 영상 연결됨';
        setText(info, status);

        let archive = row.querySelector('.archive-row-button');
        if (!archive) {
          archive = document.createElement('button');
          archive.className = 'quiet archive-row-button';
          row.append(archive);
        }
        setText(archive, archiveView ? '↩' : '⌄');
        archive.title = archiveView ? '복원' : '보관';
        archive.setAttribute('aria-label', lecture.title + (archiveView ? ' 복원' : ' 보관'));
        archive.onclick = async () => {
          try {
            await api('settings', archiveView ? {restore_id: lecture.id} : {archive_id: lecture.id});
            await refresh();
          } catch (error) { toast(error.message); }
        };
      });
    });
    const empty = document.querySelector('#lectureList > .empty');
    if (empty && archiveView) setText(empty, '보관한 강의가 없습니다.');
  }

  function simplifyJobs() {
    if (!state?.jobs) return;
    const details = document.querySelector('details.jobs');
    const visible = state.jobs.filter(j => ['queued','running','error'].includes(j.status));
    document.querySelectorAll('#jobList .job.done').forEach(node => node.remove());
    if (details) {
      details.hidden = visible.length === 0;
      if (visible.some(j => j.status === 'error')) details.open = true;
      const count = document.getElementById('jobCount');
      const active = visible.filter(j => j.status !== 'error').length;
      const errors = visible.filter(j => j.status === 'error').length;
      setText(count, [active ? `${active}개 처리 중` : '', errors ? `${errors}개 확인 필요` : ''].filter(Boolean).join(' · '));
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    injectStyles();
    compactReaderTools();
    improveStaticCopy();
    addWatchPreference();
    addYoutubePreference();
    addQualityControls();
    addArchiveControls();

    const library = document.getElementById('lectureList');
    if (library) new MutationObserver(decorateLibrary).observe(library, {childList:true, subtree:true});
    const jobs = document.getElementById('jobList');
    if (jobs) new MutationObserver(simplifyJobs).observe(jobs, {childList:true, subtree:true});
    setInterval(() => { decorateLibrary(); simplifyJobs(); }, 1100);

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