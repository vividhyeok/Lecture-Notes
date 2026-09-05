const { chromium } = require("playwright-core");
const { spawn } = require("node:child_process");
const fs = require("node:fs"),
  path = require("node:path"),
  os = require("node:os"),
  assert = require("node:assert/strict");
(async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lecture-notes-test-"));
  fs.cpSync("extension", path.join(root, "extension"), { recursive: true });
  const process = spawn(
    "python",
    [path.resolve("backend/server.py"), "--root", root, "--port", "18766"],
    { windowsHide: true, stdio: "ignore" },
  );
  let browser, token;
  const base = "http://127.0.0.1:18766";
  try {
    let ready = false;
    for (let i = 0; i < 60; i++) {
      try {
        const r = await fetch(base + "/health");
        if (r.ok) {
          ready = true;
          break;
        }
      } catch {}
      await new Promise((r) => setTimeout(r, 100));
    }
    assert.ok(ready, "test server must start");
    token = JSON.parse(
      fs.readFileSync(path.join(root, ".local/settings.json"), "utf8"),
    ).token;
    browser = await chromium.launch({ channel: "chrome", headless: true });
    const page = await browser.newPage({
      viewport: { width: 430, height: 900 },
    });
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(base);
    await page.locator("#settingsView").waitFor({ state: "visible" });
    await page.click("[data-view=library]");
    assert.equal(await page.locator('#manualImport').getAttribute('open'), null);
    await page.setInputFiles("#fileInput", {
      name: "[운영체제] 프로세스-노트.md",
      mimeType: "text/markdown",
      buffer: Buffer.from(
        "# 프로세스\n\n## 정의\n\n- 실행 중인 프로그램\n  - 주소 공간\n  - 예시\n\n<script>window.pwned=true</script>",
      ),
    });
    await page.locator(".lecture-item").waitFor();
    await page.locator(".lecture-item").click();
    await page.waitForFunction(() =>
      document.querySelector("#noteBody")?.textContent.includes("주소 공간"),
    );
    assert.equal(await page.locator("#noteBody ul ul").count(), 1);
    assert.equal(await page.evaluate(() => Boolean(window.pwned)), false);
    await page.click('#themeToggle');
    await page.click('#themeToggle');
    assert.equal(await page.getAttribute('html', 'data-theme'), 'dark');
    await page.click('#readingOptions > summary');
    await page.click('#fontIncrease');
    assert.equal(await page.locator('#fontReset').textContent(), '110%');
    await page.reload();
    await page.locator('.lecture-item').waitFor();
    await page.locator('.lecture-item').click();
    assert.equal(await page.getAttribute('html', 'data-theme'), 'dark');
    assert.equal(await page.locator('#fontReset').textContent(), '110%');
    await page.setViewportSize({ width: 320, height: 850 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    const popupPromise = page.waitForEvent('popup');
    await page.click('#readingOptions > summary');
    await page.click('#printNote');
    const print = await popupPromise;
    await print.locator('#printBody ul ul').waitFor();
    assert.equal(await print.locator('#printBody script').count(), 0);
    await print.selectOption('#printSize', '12');
    await print.emulateMedia({ media: 'print' });
    assert.equal(await print.locator('.print-actions').isVisible(), false);
    const pdf = await print.pdf({ preferCSSPageSize: true });
    assert.ok(pdf.length > 1000, 'A4 PDF should contain rendered lecture');
    await print.close();
    await page.setViewportSize({ width: 430, height: 900 });
    await page.fill("#noteSearch", "주소 공간");
    await page.waitForFunction(
      () => document.querySelector("#searchCount").textContent === "1개 일치",
    );
    await page.click('#noteTools > summary');
    await page.click("#editNote");
    await page.fill("#editor", "# 수정한 노트\n\n- 사용자 추가 내용");
    await page.click("#saveNote");
    await page.waitForFunction(() =>
      document
        .querySelector("#noteBody")
        .textContent.includes("사용자 추가 내용"),
    );
    const state = await (
      await fetch(base + "/api/state", {
        headers: { Authorization: "Bearer " + token },
      })
    ).json();
    const lecture = await (
      await fetch(base + "/api/lecture?id=" + state.lectures[0].id, {
        headers: { Authorization: "Bearer " + token },
      })
    ).json();
    assert.ok(
      fs.readFileSync(lecture.note_path, "utf8").includes("사용자 추가 내용"),
    );
    await page.click("#editNote");
    await page.fill("#editor", "# 충돌 테스트");
    fs.appendFileSync(lecture.note_path, "\n- Obsidian에서 편집");
    await page.click("#saveNote");
    await page.waitForFunction(() =>
      document.querySelector("#toast").textContent.includes("다른 화면"),
    );
    assert.ok(
      fs.readFileSync(lecture.note_path, "utf8").includes("Obsidian에서 편집"),
    );
    await page.click("#cancelEdit");
    await page.waitForFunction(() =>
      document
        .querySelector("#noteBody")
        .textContent.includes("Obsidian에서 편집"),
    );
    await page.click("[data-view=library]");
    await page.setInputFiles("#fileInput", {
      name: "[운영체제] 프로세스-노트.md",
      mimeType: "text/markdown",
      buffer: Buffer.from(
        "# 프로세스\n\n## 정의\n\n- 실행 중인 프로그램\n  - 주소 공간\n  - 예시\n\n<script>window.pwned=true</script>",
      ),
    });
    await page.waitForTimeout(500);
    assert.equal(await page.locator(".lecture-item").count(), 1);
    assert.deepEqual(errors, []);
    await page.setInputFiles('#fileInput', {name:'[운영체제] 10 다음 강의-노트.md',mimeType:'text/markdown',buffer:Buffer.from('# 다음 강의\n- 다음 내용')});
    await page.waitForFunction(()=>document.querySelectorAll('.lecture-item').length===2);
    const linked = await browser.newPage({viewport:{width:350,height:850}});
    linked.on('pageerror', e=>errors.push(e.message));
    await linked.addInitScript(() => {
      sessionStorage.setItem('setupShown','1');
      window.testLecture = {canBind:true,course:'운영체제',title:'LMS 영상 01',pageKey:'https://jnuclass.jejunu.ac.kr/courses/1/lecture/1',mediaKey:'https://common.jejunu.ac.kr/01.mp4',tabId:123};
      window.chrome ||= {};
      chrome.runtime = {id:'test-extension',sendMessage:async()=>window.testLecture};
      chrome.tabs = {create:async args=>{window.openedVideo=args.url;},onActivated:{addListener:()=>{}}};
      chrome.storage = {local:{get:async()=>({}),set:async()=>{}}};
    });
    await linked.goto(base);
    await linked.locator('.lecture-item').first().waitFor();
    await linked.locator('.lecture-item').filter({hasText:'프로세스'}).click();
    await linked.click('#noteTools > summary');
    await linked.click('#bindTab');
    await linked.waitForFunction(()=>document.querySelector('#toast').textContent.includes('연결됨'));
    await linked.click('#openVideo');
    assert.equal(await linked.evaluate(()=>window.openedVideo), 'https://jnuclass.jejunu.ac.kr/courses/1/lecture/1');
    await linked.reload();
    await linked.waitForFunction(()=>!document.querySelector('#readerView').hidden && document.querySelector('#readerTitle').textContent.includes('프로세스'));
    const index = await linked.locator('#lectureJump').evaluate(s=>s.selectedIndex);
    await linked.click(index===0 ? '#nextLecture' : '#previousLecture');
    await linked.waitForFunction(()=>document.querySelector('#readerTitle').textContent.includes('다음 강의'));
    await linked.waitForTimeout(3300);
    assert.ok((await linked.locator('#readerTitle').textContent()).includes('다음 강의'),'manual navigation must not snap back');
    assert.equal(await linked.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await linked.evaluate(()=>{window.testLecture={canBind:true,course:'youtube',title:'YouTube lesson',pageKey:'https://www.youtube.com/watch?v=abcdefghijk',mediaKey:'',tabId:124};});
    await linked.click('#noteTools > summary');
    await linked.click('#bindTab');
    await linked.waitForFunction(()=>document.querySelector('#readerCourse').textContent==='youtube');
    await linked.click('#openVideo');
    assert.equal(await linked.evaluate(()=>window.openedVideo), 'https://www.youtube.com/watch?v=abcdefghijk');
    await linked.reload();
    await linked.evaluate(()=>{window.testLecture={canBind:true,course:'youtube',title:'Renamed YouTube lesson',pageKey:'https://www.youtube.com/watch?v=abcdefghijk',mediaKey:'',tabId:124};});
    await linked.waitForFunction(()=>!document.querySelector('#readerView').hidden && document.querySelector('#readerCourse').textContent==='youtube');
    await linked.close();
    assert.deepEqual(errors, []);
    console.log(
      "PASS: Chrome import, Markdown, XSS, search, edit/conflict, dedupe, dark theme/size persistence, 320px layout and A4 PDF",
    );
  } finally {
    await browser?.close();
    if (token)
      try {
        await fetch(base + "/api/shutdown", {
          method: "POST",
          headers: {
            Authorization: "Bearer " + token,
            "Content-Type": "application/json",
          },
          body: "{}",
        });
      } catch {}
    await new Promise((resolve) => {
      if (process.exitCode !== null) return resolve();
      process.once("exit", resolve);
      setTimeout(() => {
        process.kill();
        resolve();
      }, 5000).unref();
    });
    // Only delete the uniquely created test directory, never the user's library.
    if (
      path.dirname(root) === os.tmpdir() &&
      path.basename(root).startsWith("lecture-notes-test-")
    )
      fs.rmSync(root, { recursive: true, force: true });
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
