(() => {
  const key = 'lecture-print-' + new URLSearchParams(location.search).get('id');
  let data;
  try { data = JSON.parse(localStorage.getItem(key)); localStorage.removeItem(key); } catch {}
  if (!data || typeof data.markdown !== 'string') {
    document.getElementById('printBody').textContent = '노트 화면에서 A4 인쇄 버튼을 다시 눌러 주세요.';
    document.getElementById('doPrint').disabled = true;
    return;
  }
  document.title = data.title || '강의노트';
  document.getElementById('printCourse').textContent = data.course || '';
  NoteMarkdown.render(data.markdown, document.getElementById('printBody'));
  if (!document.querySelector('#printBody h1')) {
    const heading = document.createElement('h1'); heading.textContent = document.title;
    document.getElementById('printBody').prepend(heading);
  }
  const size = document.getElementById('printSize');
  const width = document.getElementById('printWidth');
  const setSize = value => document.documentElement.style.setProperty('--print-size', value + 'pt');
  const setWidth = value => document.documentElement.style.setProperty('--content-width', value);
  setSize(size.value);
  setWidth(width.value);
  size.onchange = event => setSize(event.target.value);
  width.onchange = event => setWidth(event.target.value);
  document.getElementById('doPrint').onclick = () => window.print();
})();
