(() => {
  "use strict";
  if (globalThis.__lectureNotesAttached) return;
  globalThis.__lectureNotesAttached = true;
  let last = 0;
  const bound = new WeakSet();
  function report(media) {
    if (Date.now() - last < 1500) return;
    last = Date.now();
    try {
      chrome.runtime.sendMessage(
        {
          type: "LECTURE_TIME",
          course:
            [
              ...document.querySelectorAll(
                "[aria-label*=breadcrumb i] a,.breadcrumbs a,.breadcrumb a",
              ),
            ].map((n) => n.textContent.trim())[1] || "",
          title:
            document.querySelector("main h1,h1")?.textContent || document.title,
          currentTime: media.currentTime,
          duration: Number.isFinite(media.duration) ? media.duration : 0,
          paused: media.paused,
          ...globalThis.LectureContext?.read(media),
        },
        () => {
          void chrome.runtime.lastError;
        },
      );
    } catch {
      observer.disconnect();
    }
  }
  function scan() {
    for (const m of document.querySelectorAll("video,audio"))
      if (!bound.has(m)) {
        bound.add(m);
        for (const e of ["timeupdate", "playing", "pause", "loadedmetadata"])
          m.addEventListener(e, () => report(m));
      }
  }
  const observer = new MutationObserver(scan);
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
  });
  scan();
  if (window === window.top) {
    const host = document.createElement("div");
    host.id = "lecture-notes-edge";
    const shadow = host.attachShadow({ mode: "closed" });
    const style = document.createElement("style");
    style.textContent =
      "button{position:fixed;right:0;top:42%;z-index:2147483647;writing-mode:vertical-rl;border:1px solid #d7dce4;border-radius:9px 0 0 9px;padding:15px 9px;background:#233955;color:white;font:600 13px system-ui;cursor:pointer;box-shadow:0 2px 8px #0002}button:focus-visible{outline:3px solid #f5b948}";
    const button = document.createElement("button");
    button.textContent = "강의 노트";
    button.title = "강의 옆에 노트 열기";
    button.onclick = () => {
      try {
        chrome.runtime.sendMessage({ type: "OPEN_NOTES" }, () => {
          void chrome.runtime.lastError;
        });
      } catch {
        button.textContent = "확장 다시 로드";
      }
    };
    shadow.append(style, button);
    document.documentElement.append(host);
  }
})();
