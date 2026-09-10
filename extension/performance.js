"use strict";
(() => {
  const labels = {
    copyCorrection: "GPT 보정용 복사",
    pasteCorrection: "보정본 붙여넣기",
    editNote: "편집",
    exportNote: "MD 저장",
    reorganizeNote: "AI 다시 정리",
    bindTab: "강의 연결",
    openLectureFolder: "원본 폴더",
    renameLecture: "이름 정리",
    attachExisting: "기존 노트·전사 연결",
    printNote: "A4 인쇄 / PDF",
    openVideo: "강의 영상 열기",
  };

  function restoreTextControls() {
    for (const [id, label] of Object.entries(labels)) {
      const button = document.getElementById(id);
      if (!button) continue;
      if (button.textContent !== label) button.textContent = label;
      button.classList.remove("icon-button");
    }
    const summary = document.querySelector("#noteTools > summary");
    if (summary && summary.textContent !== "도구 · 보기") {
      summary.textContent = "도구 · 보기";
      summary.removeAttribute("aria-label");
      summary.title = "노트 도구 및 보기 설정";
    }
  }

  const style = document.createElement("style");
  style.textContent = `
    #noteTools .reader-tools { gap: 7px; }
    #noteTools .reader-tools button { width: auto; min-width: 0; height: auto; padding: 6px 10px; font-size: 11px; border-radius: 8px; }
    #noteTools > summary { width: auto; min-width: 0; padding-inline: 0; }
    #archiveCurrent, .archive-row-button { width: auto !important; min-width: 0 !important; font-size: 0 !important; padding-inline: 9px !important; }
    .archive-row-button::after { content: attr(title); font-size: 11px; }
    #archiveCurrent::after { content: "보관"; font-size: 11px; }
    #archiveCurrent[title*="복원"]::after { content: "복원"; }
    #readingOptions .reading-controls { gap: 8px; }
    #printNote { white-space: nowrap; }
  `;
  document.head.append(style);

  const baseApi = api;
  let forceNextRefresh = false;
  api = async function(path, data, raw = false) {
    if (data !== undefined) forceNextRefresh = true;
    if (path === "state") path = "state?compact=1";
    return baseApi(path, data, raw);
  };

  function lectureFingerprint() {
    const rows = (state?.lectures || []).map((lecture) => [
      lecture.id,
      lecture.title,
      lecture.course,
      Boolean(lecture.has_notes),
      Boolean(lecture.has_transcript),
      lecture.sync_status || "",
      Boolean(lecture.archived),
      (lecture.bindings || []).map((b) => b.pageKey || "").join("|"),
    ]);
    return JSON.stringify([
      document.getElementById("search")?.value || "",
      Boolean(state?.settings?.archive_view),
      rows,
    ]);
  }

  function jobFingerprint() {
    return JSON.stringify([
      Boolean(state?.settings?.has_key),
      (state?.jobs || []).map((job) => [job.id, job.target, job.status, job.progress, job.error]),
    ]);
  }

  function examFingerprint() {
    const exams = (state?.exams || []).map((exam) => [
      exam.source || "",
      exam.key || exam.name,
      exam.name,
      exam.folder,
      exam.modified || 0,
      typeof exam.content === "string" ? exam.content.length : -1,
    ]);
    const lectures = (state?.lectures || [])
      .filter((lecture) => lecture.has_transcript || lecture.has_notes)
      .map((lecture) => [lecture.id, lecture.course, lecture.title, Boolean(lecture.has_transcript), Boolean(lecture.has_notes)]);
    return JSON.stringify([exams, lectures]);
  }

  const baseRenderLibrary = renderLibrary;
  const baseRenderJobs = renderJobs;
  let lastLectureRender = "";
  let lastJobRender = "";
  let lastExamRender = "";

  renderLibrary = function() {
    const signature = lectureFingerprint();
    if (signature === lastLectureRender) return;
    lastLectureRender = signature;
    return baseRenderLibrary();
  };

  renderJobs = function() {
    const signature = jobFingerprint();
    if (signature === lastJobRender) return;
    lastJobRender = signature;
    return baseRenderJobs();
  };

  async function loadExamContent(exam) {
    if (typeof exam.content === "string") return exam;
    const params = new URLSearchParams({
      source: exam.source || "local",
      name: exam.key || exam.name || "",
    });
    return api("exam-content?" + params.toString());
  }

  renderExams = function() {
    const signature = examFingerprint();
    if (signature === lastExamRender) return;
    lastExamRender = signature;

    const root = document.getElementById("examSelect");
    root.replaceChildren();
    for (const lecture of (state?.lectures || []).filter((item) => item.has_transcript || item.has_notes)) {
      const label = document.createElement("label");
      const check = document.createElement("input");
      check.type = "checkbox";
      check.checked = checked.has(lecture.id);
      check.onchange = () => check.checked ? checked.add(lecture.id) : checked.delete(lecture.id);
      label.append(check, document.createTextNode((lecture.course ? lecture.course + " · " : "") + lecture.title));
      root.append(label);
    }

    const results = document.getElementById("examResults");
    results.replaceChildren();
    for (const exam of state?.exams || []) {
      const box = document.createElement("div");
      box.className = "exam-result";
      const name = document.createElement("p");
      name.textContent = exam.name;
      const read = document.createElement("button");
      read.textContent = "읽기";
      read.onclick = action(async () => {
        if (editing) return toast("현재 편집 내용을 먼저 저장하거나 취소하세요.");
        read.disabled = true;
        try {
          const full = await loadExamContent(exam);
          current = null;
          renderLectureNavigation();
          document.getElementById("readerEmpty").hidden = true;
          document.getElementById("readerContent").hidden = false;
          document.getElementById("readerTitle").textContent = full.name || exam.name;
          document.getElementById("readerCourse").textContent = "시험 대비";
          document.getElementById("notePath").textContent = full.folder || exam.folder;
          lastMarkdown = full.content || "";
          NoteMarkdown.render(lastMarkdown, document.getElementById("noteBody"));
          document.getElementById("editNote").disabled = true;
          document.getElementById("showNotes").disabled = true;
          document.getElementById("showTranscript").disabled = true;
          document.querySelector(".reader-tools").hidden = true;
          document.getElementById("playingContext").textContent = "";
          readerMode = "notes";
          show("reader");
        } finally {
          read.disabled = false;
        }
      });
      const save = document.createElement("button");
      save.className = "quiet";
      save.textContent = "MD 저장";
      save.onclick = action(async () => {
        save.disabled = true;
        try {
          const full = await loadExamContent(exam);
          download((full.name || exam.name) + ".md", full.content || "");
        } finally {
          save.disabled = false;
        }
      });
      box.append(name, read, save);
      results.append(box);
    }
  };

  const baseRefresh = refresh;
  let lastNetworkRefresh = 0;
  refresh = async function(force = false) {
    if (polling) {
      if (force) forceNextRefresh = true;
      return;
    }
    const now = Date.now();
    const active = Boolean(state?.jobs?.some((job) => ["queued", "running"].includes(job.status)));
    const minimum = active ? 2500 : 6000;
    if (!force && !forceNextRefresh && now - lastNetworkRefresh < minimum) return;
    lastNetworkRefresh = now;
    try {
      return await baseRefresh();
    } finally {
      forceNextRefresh = false;
      document.dispatchEvent(new CustomEvent("lecture-notes:state-updated"));
      restoreTextControls();
    }
  };

  function initialize() {
    if (globalThis.__LN_NATIVE_SET_INTERVAL__) {
      globalThis.setInterval = globalThis.__LN_NATIVE_SET_INTERVAL__;
      delete globalThis.__LN_NATIVE_SET_INTERVAL__;
    }
    document.head.append(style);
    document.addEventListener("lecture-notes:state-updated", restoreTextControls);
    restoreTextControls();
    document.getElementById("reconnect")?.addEventListener("click", () => { forceNextRefresh = true; }, true);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) refresh(true).catch(() => {});
    });
    window.addEventListener("focus", () => refresh(true).catch(() => {}));
    const kick = () => polling
      ? setTimeout(kick, 100)
      : refresh(true).catch(() => {});
    setTimeout(kick, 120);
  }

  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", initialize, { once: true });
  else
    initialize();
})();
