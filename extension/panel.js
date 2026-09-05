"use strict";
const $ = (id) => document.getElementById(id);
const extension = Boolean(globalThis.chrome?.runtime?.id);
const config = globalThis.LN_CONFIG || {
  base: "http://127.0.0.1:18765",
  token: "",
};
let state = null,
  current = null,
  view = "library",
  readerMode = "notes",
  editing = false,
  editBase = "",
  activeTab = null,
  context = null,
  lastMarkdown = "",
  polling = false,
  timer;
const checked = new Set();
const closedCourses = new Set();
function videoUrl(lecture) {
  for (const binding of [...(lecture?.bindings || [])].reverse()) {
    try {
      const url = new URL(binding.pageKey);
      if (url.protocol === 'https:' && !url.username && !url.password) return url.href;
    } catch {}
  }
  return '';
}
async function openVideo(lecture) {
  const url = videoUrl(lecture);
  if (!url) throw Error('노트 관리에서 열린 강의를 먼저 연결하세요.');
  if (extension) await chrome.tabs.create({url});
  else window.open(url, '_blank', 'noopener,noreferrer');
}
let lastContextKey = '', contextPolling = false;
let autoCourse = '', autoTitle = '';
function renderLectureNavigation() {
  const navigation = document.querySelector('.lecture-navigation');
  navigation.hidden = !current;
  if (!current || !state) return;
  const list = LectureNavigation.ordered(state.lectures, current.course);
  const index = list.findIndex(l => l.id === current.id);
  $('lectureJump').replaceChildren(...list.map(l => {
    const option = document.createElement('option'); option.value = l.id; option.textContent = l.title;
    option.selected = l.id === current.id; return option;
  }));
  $('previousLecture').disabled = index <= 0;
  $('nextLecture').disabled = index < 0 || index >= list.length - 1;
  $('previousLecture').onclick = action(() => index > 0 && openLecture(list[index-1].id));
  $('nextLecture').onclick = action(() => index+1 < list.length && openLecture(list[index+1].id));
}
async function updateLectureContext() {
  if (!extension || contextPolling) return;
  contextPolling = true;
  try {
    const fresh = await chrome.runtime.sendMessage({type:'GET_LECTURE_CONTEXT'});
    if (fresh?.error) { context = null; $('playingContext').textContent = fresh.error; return; }
    context = fresh;
    if (!fresh) { lastContextKey = ''; $('playingContext').textContent = 'JNUclass 또는 YouTube 영상 탭에서 강의를 연결하세요.'; return; }
    activeTab = fresh.tabId;
    if ((!$('importCourse').value || $('importCourse').value === autoCourse) && fresh.course) { $('importCourse').value = fresh.course; autoCourse = fresh.course; }
    if ((!$('importTitle').value || $('importTitle').value === autoTitle) && fresh.title) { $('importTitle').value = fresh.title; autoTitle = fresh.title; }
    $('playingContext').textContent = '열린 강의: ' + [fresh.course, fresh.title].filter(Boolean).join(' · ');
    const key = LectureNavigation.identity(fresh);
    if (editing || !state || key === lastContextKey) return;
    const match = LectureNavigation.find(state.lectures, fresh);
    if (!match) { lastContextKey = ''; return; }
    lastContextKey = key;
    if (match && current?.id !== match.id) {
      await openLecture(match.id);
      toast('현재 영상에 맞는 노트를 열었습니다.');
    }
  } finally { contextPolling = false; }
}
function toast(text) {
  $("toast").textContent = text;
  $("toast").style.display = "block";
  clearTimeout(timer);
  timer = setTimeout(() => ($("toast").style.display = "none"), 4500);
}
async function api(path, data, raw = false) {
  const response = await fetch(config.base + "/api/" + path, {
    method: data === undefined ? "GET" : "POST",
    headers: {
      Authorization: "Bearer " + config.token,
      ...(data !== undefined && !raw
        ? { "Content-Type": "application/json" }
        : {}),
    },
    body: data === undefined ? undefined : raw ? data : JSON.stringify(data),
  });
  if (!response.ok) {
    let error;
    try {
      error = await response.json();
    } catch {}
    throw Error(error?.error || "서버 연결에 실패했습니다.");
  }
  return response.json();
}
function show(name) {
  view = name;
  for (const section of ["library", "reader", "exam", "settings"])
    $(section + "View").hidden = section !== name;
  document
    .querySelectorAll("[data-view]")
    .forEach((b) =>
      b.setAttribute("aria-selected", String(b.dataset.view === name)),
    );
  if (name === "settings" && state) fillSettings();
}
function action(fn) {
  return async (event) => {
    try {
      await fn(event);
    } catch (e) {
      toast(e.message);
    }
  };
}
async function refresh() {
  if (polling) return;
  polling = true;
  try {
    state = await api("state");
    $("offline").hidden = true;
    $("connection").classList.add("connected");
    $("connection").textContent = state.settings.has_key
      ? "자료함 연결됨 · 파일 자동 보관"
      : "자료함 연결됨 · 설정에서 OpenAI API 키를 입력하세요";
    renderLibrary();
    renderJobs();
    renderExams();
    if (current && !editing) {
      const latest = await api("lecture?id=" + encodeURIComponent(current.id));
      current = latest;
      if (view === "reader") renderReader();
    }
    await updateLectureContext().catch(() => { $('playingContext').textContent = '영상 정보를 읽지 못했습니다. LMS 페이지와 확장을 새로고침하세요.'; });
    if (!state.settings.has_key && !sessionStorage.getItem("setupShown")) {
      sessionStorage.setItem("setupShown", "1");
      show("settings");
    }
  } catch (e) {
    $("offline").hidden = false;
    $("connection").textContent = e.message;
    $("connection").classList.remove("connected");
  } finally {
    polling = false;
  }
}
function renderLibrary() {
  const query = $("search").value.toLowerCase(),
    root = $("lectureList");
  root.replaceChildren();
  const courses = [
    ...new Set(state.lectures.map((l) => l.course || "미분류")),
  ].sort((a, b) => a.localeCompare(b, "ko"));
  $("courseNames").replaceChildren(
    ...courses.map((c) => {
      const o = document.createElement("option");
      o.value = c;
      return o;
    }),
  );
  for (const course of courses) {
    const lectures = state.lectures.filter(
      (l) =>
        (l.course || "미분류") === course &&
        (l.title + " " + course).toLowerCase().includes(query),
    );
    if (!lectures.length) continue;
    const folder = document.createElement('details');
    folder.className = 'course-folder';
    folder.open = Boolean(query) || !closedCourses.has(course);
    folder.addEventListener('toggle', () => {
      if (!folder.isConnected || query) return;
      if (folder.open) closedCourses.delete(course); else closedCourses.add(course);
    });
    const heading = document.createElement('summary');
    heading.textContent = course + ' · ' + lectures.length;
    folder.append(heading);
    root.append(folder);
    for (const lecture of lectures.sort((a,b) => a.title.localeCompare(b.title, 'ko', {numeric:true}))) {
      const button = document.createElement("button");
      button.className = "lecture-item";
      const title = document.createElement("strong"),
        info = document.createElement("span");
      title.textContent = lecture.title;
      info.textContent = lecture.sync_status || (lecture.has_notes
        ? "노트 준비됨"
        : lecture.has_transcript
          ? "전사본 보관됨 · 노트 대기"
          : "오디오 보관됨 · 전사 대기");
      button.append(title, info);
      button.onclick = action(() => openLecture(lecture.id));
      const row = document.createElement('div');
      row.className = 'lecture-row';
      row.append(button);
      if (videoUrl(lecture)) {
        const play = document.createElement('button');
        play.className = 'quiet';
        play.textContent = '영상 열기';
        play.setAttribute('aria-label', lecture.title + ' 영상 열기');
        play.onclick = action(() => openVideo(lecture));
        row.append(play);
      }
      folder.append(row);
    }
  }
  if (!root.children.length) {
    const p = document.createElement("p");
    p.className = "empty";
    p.textContent = query
      ? "일치하는 강의가 없습니다."
      : "아직 강의가 없습니다. 입력 폴더에 파일을 저장하면 자동으로 추가됩니다. 직접 넣으려면 아래 수동 추가를 펼치세요.";
    root.append(p);
  }
}
function renderJobs() {
  const jobs = state.jobs;
  $("jobCount").textContent =
    jobs.filter((j) => ["queued", "running"].includes(j.status)).length +
    "개 진행/대기";
  const root = $("jobList");
  root.replaceChildren();
  for (const job of jobs.slice(0, 20)) {
    const div = document.createElement("div");
    div.className = "job " + job.status;
    const title = document.createElement("strong");
    title.textContent =
      (state.lectures.find((l) => l.id === job.target)?.title || "시험 자료") +
      " · " +
      job.progress;
    const desc = document.createElement("p");
    desc.textContent =
      job.error ||
      (job.status === "queued" && !state.settings.has_key
        ? "API 키 설정 후 진행됩니다."
        : "");
    div.append(title, desc);
    if (job.status === "error") {
      const b = document.createElement("button");
      b.className = "quiet";
      b.textContent = "저장된 구간부터 재시도";
      b.onclick = action(async () => {
        await api("retry", { id: job.id });
        await refresh();
      });
      div.append(b);
    }
    root.append(div);
  }
}
function renderExams() {
  const root = $("examSelect");
  root.replaceChildren();
  for (const l of state.lectures.filter(
    (l) => l.has_transcript || l.has_notes,
  )) {
    const label = document.createElement("label"),
      check = document.createElement("input");
    check.type = "checkbox";
    check.checked = checked.has(l.id);
    check.onchange = () =>
      check.checked ? checked.add(l.id) : checked.delete(l.id);
    label.append(
      check,
      document.createTextNode((l.course ? l.course + " · " : "") + l.title),
    );
    root.append(label);
  }
  const results = $("examResults");
  results.replaceChildren();
  for (const exam of state.exams) {
    const box = document.createElement("div");
    box.className = "exam-result";
    const p = document.createElement("p");
    p.textContent = exam.name;
    const b = document.createElement("button");
    b.textContent = "읽기";
    b.onclick = () => {
      if (editing) return toast("현재 편집 내용을 먼저 저장하거나 취소하세요.");
      current = null;
      renderLectureNavigation();
      $("readerEmpty").hidden = true;
      $("readerContent").hidden = false;
      $("readerTitle").textContent = exam.name;
      $("readerCourse").textContent = "시험 대비";
      $("notePath").textContent = exam.folder;
      lastMarkdown = exam.content;
      NoteMarkdown.render(exam.content, $("noteBody"));
      $("editNote").disabled = true;
      $("showNotes").disabled = true;
      $("showTranscript").disabled = true;
      document.querySelector('.reader-tools').hidden = true;
      $("playingContext").textContent = '';
      readerMode = 'notes';
      show("reader");
    };
    const save = document.createElement("button");
    save.className = "quiet";
    save.textContent = "MD 저장";
    save.onclick = () => download(exam.name + ".md", exam.content);
    box.append(p, b, save);
    results.append(box);
  }
}
async function openLecture(id) {
  if (editing) {
    toast("현재 편집 내용을 먼저 저장하거나 취소하세요.");
    return;
  }
  current = await api("lecture?id=" + encodeURIComponent(id));
  $('renameBox').hidden = true;
  $('noteSearch').value = '';
  $('searchCount').textContent = '';
  readerMode = "notes";
  lastMarkdown = "";
  $("editNote").disabled = false;
  renderReader();
  show("reader");
}
function renderReader() {
  if (!current) return;
  renderLectureNavigation();
  $("readerEmpty").hidden = true;
  $("readerContent").hidden = false;
  $("readerTitle").textContent = current.title;
  $("showNotes").disabled = false;
  $("showTranscript").disabled = false;
  document.querySelector('.reader-tools').hidden = false;
  $("readerCourse").textContent = current.course || "미분류";
  $('openVideo').hidden = !videoUrl(current);
  $('openVideo').onclick = action(() => openVideo(current));
  $("notePath").textContent = (current.sync_status ? current.sync_status + "\n" : "") + (current.note_path || current.folder);
  $("showNotes").setAttribute("aria-pressed", String(readerMode === "notes"));
  $("showTranscript").setAttribute(
    "aria-pressed",
    String(readerMode === "transcript"),
  );
  $("editNote").disabled = readerMode !== "notes";
  $("bindTab").hidden = !extension;
  let text =
    readerMode === "notes" ? current.notes : transcriptText(current.transcript);
  if (!text)
    text =
      current.sync_status ? '## 동기화를 기다리고 있습니다\n\n- ' + current.sync_status : readerMode === "notes"
        ? "## 노트를 준비하고 있습니다\n\n- 전사본 탭에서 먼저 내용을 확인할 수 있습니다.\n- 새 자료를 자동 처리하지 않도록 설정했다면 내 강의에서 파일을 보관한 뒤 아래 버튼으로 작성을 시작하세요."
        : "";
  if (text !== lastMarkdown && !editing) {
    lastMarkdown = text;
    NoteMarkdown.render(text, $("noteBody"));
    if (readerMode === "notes" && !current.notes && !current.sync_status) {
      const b = document.createElement("button");
      b.textContent = "전사·노트 작성 시작";
      b.onclick = action(async () => {
        await api("process", { id: current.id });
        toast("저장된 전사는 재사용하고 노트를 작성합니다.");
        refresh();
      });
      $("noteBody").append(b);
    }
  }
  if (context)
    $("playingContext").textContent =
      "열린 강의: " + [context.course, context.title].filter(Boolean).join(' · ') + (current.bindings?.some(b => LectureNavigation.matches(b, context)) ? ' · 연결됨' : ' · 연결하려면 강의 연결');
}
function transcriptText(t) {
  if (t?.segments?.length)
    return (
      "# 전사본\n\n" +
      t.segments
        .map((s) => "[" + formatTime(s.start) + "] " + s.text)
        .join("\n\n")
    );
  return t?.text || "";
}
function formatTime(n) {
  n = Math.max(0, Math.floor(n || 0));
  return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, "0")}`;
}
async function upload(files, exam = false) {
  const list = [...files];
  if (!list.length) return;
  for (let i = 0; i < list.length; i++) {
    const file = list[i],
      status = `${i + 1}/${list.length} ${file.name} 가져오는 중…`;
    $("uploadStatus").textContent = status;
    $("examStatus").textContent = exam ? status : "";
    const query = new URLSearchParams({
      name: file.name,
      course: exam ? "" : $("importCourse").value,
      title: !exam && list.length === 1 ? $("importTitle").value : "",
      exam: exam ? "1" : "0",
    });
    await api("upload?" + query, file, true);
  }
  $("uploadStatus").textContent =
    list.length + "개 파일을 보관했습니다. 같은 파일은 중복 전사하지 않습니다.";
  if (exam)
    $("examStatus").textContent =
      "시험 자료함에 저장했습니다. 자동 처리가 켜져 있으면 약 10초 후 작업을 시작합니다.";
  await refresh();
}
function drop(id, input, exam) {
  const zone = $(id);
  zone.addEventListener("dragover", (e) => {
    e.preventDefault();
    zone.classList.add("drag");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag"));
  zone.addEventListener(
    "drop",
    action(async (e) => {
      e.preventDefault();
      zone.classList.remove("drag");
      await upload(e.dataTransfer.files, exam);
    }),
  );
  zone.addEventListener("keydown", (e) => {
    if (e.target === zone && ["Enter", " "].includes(e.key)) {
      e.preventDefault();
      $(input).click();
    }
  });
  $(input).onchange = action(async () => {
    await upload($(input).files, exam);
    $(input).value = "";
  });
}
function fillSettings() {
  const s = state.settings;
  $("keyState").textContent = s.has_key
    ? "API 키 저장됨 · 다시 입력하지 않아도 됩니다."
    : "아직 API 키가 없습니다.";
  if (s.watch_error) $("keyState").textContent += '\n폴더 확인: ' + s.watch_error;
  $("vaultFolder").value = s.vault_folder;
  $('settingsStatus').textContent = '현재 노트 저장 위치: ' + s.vault_folder + ' / 강의노트 / 과목명';
  $("watchFolder").value = s.watch_folder;
  $("textModel").value = s.text_model;
  $("autoProcess").checked = s.auto_process;
  $("timedMode").checked = s.timed;
  $("downloadImportLabel").hidden = !extension;
  if (extension)
    chrome.storage.local.get(["downloadImport", "downloadStatus"]).then((s) => {
      $("downloadImport").checked = Boolean(s.downloadImport);
      $("downloadStatus").textContent = s.downloadStatus || "";
    });
}
function download(name, text) {
  const url = URL.createObjectURL(
      new Blob([text], { type: "text/markdown;charset=utf-8" }),
    ),
    a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 3000);
}
function findInNote() {
  NoteMarkdown.render(lastMarkdown, $("noteBody"));
  const query = $("noteSearch").value.trim();
  if (!query) {
    $("searchCount").textContent = "";
    return;
  }
  const walker = document.createTreeWalker($("noteBody"), NodeFilter.SHOW_TEXT),
    nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  let count = 0;
  for (const node of nodes) {
    const value = node.textContent,
      lower = value.toLocaleLowerCase(),
      needle = query.toLocaleLowerCase();
    let start = 0,
      at = lower.indexOf(needle),
      fragment = document.createDocumentFragment();
    if (at < 0) continue;
    while (at >= 0) {
      fragment.append(document.createTextNode(value.slice(start, at)));
      const m = document.createElement("mark");
      m.textContent = value.slice(at, at + query.length);
      fragment.append(m);
      count++;
      start = at + query.length;
      at = lower.indexOf(needle, start);
    }
    fragment.append(document.createTextNode(value.slice(start)));
    node.replaceWith(fragment);
  }
  $("searchCount").textContent = count + "개 일치";
  $("noteBody").querySelector("mark")?.scrollIntoView({ block: "center" });
}
document
  .querySelectorAll("[data-view]")
  .forEach((b) => (b.onclick = () => show(b.dataset.view)));
document
  .querySelectorAll("[data-folder]")
  .forEach(
    (b) =>
      (b.onclick = action(() =>
        api("open-folder", { name: b.dataset.folder }),
      )),
  );
$("settingsButton").onclick = () =>
  show(view === "settings" ? "library" : "settings");
$("reconnect").onclick = refresh;
$("chooseFiles").onclick = () => $("fileInput").click();
$("chooseExamFiles").onclick = () => $("examInput").click();
drop("dropZone", "fileInput", false);
drop("examDrop", "examInput", true);
$("search").oninput = () => state && renderLibrary();
$("noteSearch").oninput = findInNote;
$("showNotes").onclick = () => {
  readerMode = "notes";
  lastMarkdown = "";
  renderReader();
};
$("showTranscript").onclick = () => {
  if (editing) {
    toast("편집 내용을 먼저 저장하세요.");
    return;
  }
  readerMode = "transcript";
  lastMarkdown = "";
  renderReader();
};
$("editNote").onclick = () => {
  if (!current) return;
  editing = true;
  editBase = current.notes;
  $("editor").value = current.notes;
  $("editorBox").hidden = false;
  $("noteBody").hidden = true;
};
$("cancelEdit").onclick = () => {
  editing = false;
  $("editorBox").hidden = true;
  $("noteBody").hidden = false;
  refresh();
};
$("saveNote").onclick = action(async () => {
  await api("notes", {
    id: current.id,
    text: $("editor").value,
    base: editBase,
  });
  editing = false;
  $("editorBox").hidden = true;
  $("noteBody").hidden = false;
  lastMarkdown = "";
  await refresh();
  toast("Obsidian 노트에 저장했습니다.");
});
$("exportNote").onclick = () =>
  download(
    (current?.title || "시험대비") +
      (readerMode === "transcript" ? "-전사본" : "") +
      ".md",
    readerMode === "transcript" && current
      ? transcriptText(current.transcript)
      : current?.notes || lastMarkdown,
  );
$("printNote").onclick = action(() => {
  if (editing) throw Error('편집 내용을 저장하거나 취소한 뒤 인쇄하세요.');
  if (!lastMarkdown || (current && readerMode === 'notes' && !current.notes)) throw Error('인쇄할 노트가 아직 없습니다.');
  const id = crypto.randomUUID();
  localStorage.setItem('lecture-print-' + id, JSON.stringify({ title: $("readerTitle").textContent, course: $("readerCourse").textContent, markdown: lastMarkdown }));
  const opened = window.open('print.html?id=' + encodeURIComponent(id), '_blank');
  if (!opened) toast('팝업을 허용한 뒤 다시 인쇄해 주세요.');
});
$("openLectureFolder").onclick = action(
  () => current && api("open-folder", { id: current.id }),
);
$("renameLecture").onclick = () => {
  if (!current) return;
  $("renameBox").hidden = false;
  $("renameBox").open = true;
  $("renameTitle").value = current.title;
  $("renameCourse").value = current.course;
};
$("saveNames").onclick = action(async () => {
  await api("rename", {
    id: current.id,
    title: $("renameTitle").value,
    course: $("renameCourse").value,
  });
  $("renameBox").hidden = true;
  await refresh();
  toast("과목·강의명으로 저장 경로를 정리했습니다.");
});
$("makeExam").onclick = action(async () => {
  if (!checked.size) throw Error("시험 범위에 넣을 강의를 선택하세요.");
  await api("exam", { ids: [...checked], title: $("examTitle").value });
  $("examStatus").textContent =
    "기존 전사본과 노트로 시험 자료를 만들고 있습니다.";
  await refresh();
});
$("settingsForm").onsubmit = action(async (e) => {
  e.preventDefault();
  $('settingsStatus').textContent = '설정 저장 및 기존 노트 경로 적용 중…';
  try {
  await api("settings", {
    api_key: $("apiKey").value,
    vault_folder: $("vaultFolder").value,
    watch_folder: $("watchFolder").value,
    text_model: $("textModel").value,
    auto_process: $("autoProcess").checked,
    timed: $("timedMode").checked,
  });
  $("apiKey").value = "";
  if (extension)
    await chrome.storage.local.set({
      downloadImport: $("downloadImport").checked,
    });
  await refresh();
  fillSettings();
  toast("설정을 저장했습니다.");
  } catch (error) {
    $('settingsStatus').textContent = '설정을 적용하지 못했습니다: ' + error.message;
    throw error;
  }
});
$("stopServer").onclick = action(async () => {
  await api("shutdown", {});
  toast("처리 서버를 종료했습니다. 파일은 보관됩니다.");
});
$("bindTab").onclick = action(async () => {
  if (!extension || !current) return;
  if (editing) throw Error('편집 내용을 먼저 저장하거나 취소하세요.');
  const fresh = await chrome.runtime.sendMessage({type:'GET_LECTURE_CONTEXT'});
  if (fresh?.error) throw Error(fresh.error);
  if (!fresh?.hasMedia) throw Error('연결할 JNUclass 또는 YouTube 영상 탭을 열고 다시 누르세요.');
  await api('bind-lecture', {id:current.id, context:fresh});
  if (fresh.course && current.course !== fresh.course && (fresh.course === 'youtube' || !current.course || current.course === '미분류')) {
    await api('rename', {id:current.id, title:current.title, course:fresh.course});
  }
  context = fresh;
  lastContextKey = LectureNavigation.identity(fresh);
  await refresh();
  toast(fresh.title + ' → ' + current.title + ' 연결됨');
});
$('lectureJump').onchange = action(async e => {
  const id = e.target.value;
  await openLecture(id);
  renderLectureNavigation();
});
document.addEventListener("keydown", (e) => {
  if (
    (e.ctrlKey || e.metaKey) &&
    e.key.toLowerCase() === "f" &&
    view === "reader" &&
    !editing
  ) {
    e.preventDefault();
    $("noteSearch").focus();
    $("noteSearch").select();
  }
});
window.addEventListener("beforeunload", (e) => {
  if (editing && $("editor").value !== editBase) {
    e.preventDefault();
    e.returnValue = "";
  }
});
if (extension) {
  chrome.tabs.onActivated.addListener(() => { updateLectureContext().catch(()=>{}); });
}
refresh();
setInterval(() => {
  if (!document.hidden) refresh();
}, 3000);
$("attachExisting").onclick = () => current && $("attachInput").click();
$("reorganizeNote").onclick = action(async () => {
  if (!current) return;
  if (editing) throw Error('편집 내용을 먼저 저장하거나 취소하세요.');
  await api('reorganize', { id: current.id });
  toast('기존 전사본으로 다시 정리합니다. AI 비용이 발생하며 이전 노트는 백업됩니다.');
  await refresh();
});
$("attachInput").onchange = action(async () => {
  const file = $("attachInput").files[0];
  if (!file || !current) return;
  if (editing) throw Error("편집 중인 내용을 먼저 저장하세요.");
  await api(
    "upload?" + new URLSearchParams({ name: file.name, attach: current.id }),
    file,
    true,
  );
  $("attachInput").value = "";
  lastMarkdown = "";
  await refresh();
  toast("기존 자료를 이 강의에 연결했습니다. STT는 호출하지 않았습니다.");
});
