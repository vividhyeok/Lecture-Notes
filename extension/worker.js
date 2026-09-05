"use strict";
importScripts("config.local.js", "context-router.js");
const HOSTS = [
  "www.youtube.com", "m.youtube.com", "youtube.com", "youtu.be",
  "jnuclass.jejunu.ac.kr",
  "canvas.jejunu.ac.kr",
  "canvas.jnu.ac.kr",
  "common.jejunu.ac.kr",
];
const supported = (value) => {
  try {
    const u = new URL(value);
    return u.protocol === "https:" && HOSTS.includes(u.hostname);
  } catch {
    return false;
  }
};
const ports = new Set();
const safe = (p) => p.catch(() => null);
chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch(() => {});
chrome.runtime.onMessage.addListener((m, s, reply) => {
  if (m.type === "OPEN_NOTES" && s.tab && supported(s.tab.url)) {
    chrome.sidePanel.open({ tabId: s.tab.id }).then(
      () => reply({ ok: true }),
      () => reply({ ok: false }),
    );
    return true;
  }
  if (m.type === 'GET_LECTURE_CONTEXT' && s.id === chrome.runtime.id) {
    (async () => {
      const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
      if (!tab) return reply({error:'활성 탭을 찾지 못했습니다. 연결할 페이지를 클릭한 뒤 다시 누르세요.'});
      if (!tab.url) return reply({error:'탭 주소 권한이 적용되지 않았습니다. Chrome 확장 관리에서 Lecture Notes를 새로고침하세요.'});
      if (!supported(tab.url)) return reply({error:'현재 선택된 탭이 JNUclass 또는 YouTube가 아닙니다. 연결할 강의 탭을 선택하세요.'});
      reply(await LectureContextRouter.collect(chrome, tab));
    })().catch(()=>reply({error:'현재 탭 정보를 읽지 못했습니다. 영상 페이지와 확장을 새로고침한 뒤 다시 연결하세요.'}));
    return true;
  }
  if (m.type === "LECTURE_TIME" && s.tab && supported(s.tab.url)) {
    const state = {
      tabId: s.tab.id,
      frameId: s.frameId || 0,
      title: String(m.title || "").slice(0, 160),
      course: String(m.course || "").slice(0, 160),
      currentTime: Number(m.currentTime) || 0,
      duration: Number(m.duration) || 0,
      paused: Boolean(m.paused),
    };
    chrome.storage.session.set({ ["tab-" + s.tab.id]: state }).catch(() => {});
    for (const port of ports) {
      try {
        port.postMessage(state);
      } catch {
        ports.delete(port);
      }
    }
  }
});
chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== "lecture-notes") return;
  ports.add(port);
  port.onDisconnect.addListener(() => ports.delete(port));
});
chrome.downloads.onChanged.addListener((delta) => {
  if (delta.state?.current !== "complete") return;
  (async () => {
    const settings = await chrome.storage.local.get("downloadImport");
    if (!settings.downloadImport) return;
    const [item] = await chrome.downloads.search({ id: delta.id });
    if (
      !item ||
      !item.filename ||
      !/\.(mp3|m4a|mp4|wav|webm)$/i.test(item.filename)
    )
      return;
    if (
      item.byExtensionId !== "lmjnegcaeklhafolokijcfjliaokphfk" &&
      !supported(item.referrer)
    )
      return;
    const saved = await chrome.storage.session.get(
      "download-context-" + delta.id,
    );
    const source = saved["download-context-" + delta.id] || {};
    const response = await fetch(LN_CONFIG.base + "/api/download-complete", {
      method: "POST",
      headers: {
        Authorization: "Bearer " + LN_CONFIG.token,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        filename: item.filename,
        course: source.course || "",
      }),
    });
    if (!response.ok)
      throw Error("감시 폴더 설정과 서버 실행 상태를 확인하세요.");
    await chrome.storage.local.set({
      downloadStatus: "다운로드 파일을 노트 처리 대기열에 추가했습니다.",
    });
  })().catch(() =>
    chrome.storage.local.set({
      downloadStatus:
        "다운로드 감지 후 가져오지 못했습니다. START.cmd와 감시 폴더를 확인하세요.",
    }),
  );
});
async function restore(tabId) {
  const tab = await safe(chrome.tabs.get(tabId));
  if (!supported(tab?.url)) return;
  await safe(
    chrome.scripting.executeScript({
      target: { tabId, allFrames: true },
      files: ["context.js", "content.js"],
    }),
  );
}
chrome.runtime.onInstalled.addListener(() => {
  chrome.tabs
    .query({ url: HOSTS.map((h) => "https://" + h + "/*") })
    .then((tabs) => Promise.allSettled(tabs.map((t) => restore(t.id))));
});
chrome.webNavigation.onCompleted.addListener((d) => restore(d.tabId));
chrome.tabs.onRemoved.addListener((id) =>
  safe(chrome.storage.session.remove("tab-" + id)),
);
chrome.tabs
  .query({ url: HOSTS.map((h) => "https://" + h + "/*") })
  .then((tabs) => Promise.allSettled(tabs.map((t) => restore(t.id))))
  .catch(() => {});
chrome.downloads.onCreated.addListener((item) => {
  (async () => {
    const [tab] = await chrome.tabs.query({
      active: true,
      lastFocusedWindow: true,
    });
    if (!tab || !supported(tab.url)) return;
    const value = await chrome.storage.session.get("tab-" + tab.id);
    if (value["tab-" + tab.id])
      await chrome.storage.session.set({
        ["download-context-" + item.id]: value["tab-" + tab.id],
      });
  })().catch(() => {});
});
