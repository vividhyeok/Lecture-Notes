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
  document.getElementById('printSize').onchange = (e) => document.documentElement.style.setProperty('--print-size', e.target.value + 'pt');
  document.getElementById('doPrint').onclick = () => window.print();
})();
