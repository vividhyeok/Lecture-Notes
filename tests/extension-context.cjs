const {chromium}=require('playwright-core');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const temp=fs.mkdtempSync(path.join(os.tmpdir(),'lecture-context-'));
 const extension=path.join(temp,'extension');fs.cpSync('extension',extension,{recursive:true});
 fs.writeFileSync(path.join(extension,'config.local.js'),"globalThis.LN_CONFIG={base:'http://127.0.0.1:18766',token:''};");
 const executablePath=process.env.LN_TEST_CHROME || path.join(process.env.LOCALAPPDATA,'ms-playwright/chromium-1208/chrome-win64/chrome.exe');
 const browser=await chromium.launchPersistentContext(path.join(temp,'profile'),{executablePath,headless:true,args:[`--disable-extensions-except=${extension}`,`--load-extension=${extension}`]});
 try{
  const worker=browser.serviceWorkers()[0] || await browser.waitForEvent('serviceworker');
  const id=new URL(worker.url()).hostname;
  const panel=await browser.newPage();await panel.goto(`chrome-extension://${id}/panel.html`);
  const lecture=await browser.newPage();
  await lecture.route('**/*',route=>route.fulfill({contentType:'text/html; charset=utf-8',body:'<title>AI 강의</title><nav id="breadcrumbs"><a href="/courses/43319">AI 윤리학</a><a href="/courses/43319/modules">모듈</a></nav><h1>AI와 인간 관계의 윤리학_01_01</h1>'}));
  await lecture.goto('https://canvas.jejunu.ac.kr/courses/43319/modules/items/2864676');await lecture.bringToFront();
  const value=await panel.evaluate(()=>LectureContextRouter.current(chrome));
  console.log('Real extension context:',JSON.stringify(value));
  assert.equal(value?.canBind,true);assert.equal(value.course,'AI 윤리학');assert.equal(value.pageKey,'https://canvas.jejunu.ac.kr/courses/43319/modules/items/2864676');
  await lecture.goto('https://www.youtube.com/watch?v=abcdefghijk');await lecture.bringToFront();
  const youtube=await panel.evaluate(()=>LectureContextRouter.current(chrome));
  assert.equal(youtube?.course,'youtube');assert.equal(youtube?.canBind,true);
  console.log('PASS: actual extension service worker and tabs API, Canvas/YouTube without video');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
