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
})();
