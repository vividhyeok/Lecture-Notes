const assert = require('node:assert/strict');
require('../extension/context-router.js');
function mock(top, children = {}) {
  return {
    scripting: {executeScript: async ({target, files}) => {
      const id = target.frameIds[0]; assert.equal(id,0,'Only the top page may be read');
      const value = id === 0 ? top : children[id];
      if (value instanceof Error) throw value;
      return files ? [] : [{frameId:id, result:value}];
    }},
    webNavigation: {getAllFrames: async () => {throw Error('Frame enumeration must never happen');}}
  };
}
(async () => {
  const top = {title:'AI와 인간 관계의 윤리학_01_01', course:'AI와인간관계의윤리학', pageKey:'https://canvas.jejunu.ac.kr/courses/43319/modules/items/2864676', canBind:true, lecturePage:true, hasMedia:false};
  const c = await LectureContextRouter.collect(mock(top, {1:new Error('Cannot access frame')}), {id:7});
  assert.equal(c.title,top.title); assert.equal(c.canBind,true); assert.equal(c.pageKey,top.pageKey);
  const yt = {...top,course:'youtube',title:'YouTube lesson',pageKey:'https://www.youtube.com/watch?v=abcdefghijk',hasMedia:true};
  assert.equal((await LectureContextRouter.collect(mock(yt,{1:new Error('blocked ad')}),{id:8})).course,'youtube');
  const child = {hasMedia:true,title:'player',course:'',mediaKey:'https://player.test/media',area:900,paused:false};
  assert.equal((await LectureContextRouter.collect(mock(top,{1:child,2:new Error('ad')}),{id:9})).title,top.title);
  assert.equal(await LectureContextRouter.collect(mock({...top,canBind:false}),{id:10}),null);
  assert.ok((await LectureContextRouter.collect(mock(new Error('permission')),{id:11})).error.includes('주소'));
  const fallback=await LectureContextRouter.collect(mock(new Error('permission')),{id:12,url:'https://canvas.jejunu.ac.kr/courses/1/modules/items/2?token=secret',title:'강의 2'});
  assert.equal(fallback.canBind,true);assert.equal(fallback.pageKey,'https://canvas.jejunu.ac.kr/courses/1/modules/items/2');
  console.log('PASS: inaccessible iframe, YouTube ad frame, page fallback, permissions, non-video page');
})().catch(error=>{console.error(error);process.exitCode=1;});
