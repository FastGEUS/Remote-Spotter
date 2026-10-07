const {test}=require('node:test');
const assert=require('node:assert/strict');
const {model}=require('../../relay/web/flag-display.js');
test('neutralization or stop remains primary while pilot blue is also visible',()=>{
  for(const code of ['caution','stopped','finished']){
    const m=model({session:code,pilotBlue:true},true,['clear','clear','clear']);
    assert.equal(m.code,code);assert.equal(m.blue,true);
    assert.deepEqual(m.sectors,[code,code,code]);
  }
});
test('pilot blue receives the whole display when the track is green',()=>{
  const m=model({session:'green',pilotBlue:true},true,['clear','clear','clear']);
  assert.equal(m.code,'blue');assert.equal(m.title,'СИНИЙ');
});
test('stale telemetry removes coloured warnings and pilot blue',()=>{
  const m=model({session:'caution',pilotBlue:true},false,['yellow','yellow','yellow']);
  assert.equal(m.code,'stale');assert.equal(m.blue,false);
  assert.deepEqual(m.sectors,['stale','stale','stale']);
});
test('unmapped yellow is prominent without pretending a known track sector',()=>{
  const m=model({session:'yellow',rawChannels:[0,1,0]},true,['unknown','unknown','unknown']);
  assert.equal(m.code,'yellow');assert.match(m.detail,/не сопоставлен/);
  assert.deepEqual(m.sectors,['unknown','unknown','unknown']);
  const verified=model({session:'yellow'},true,['clear','clear','yellow']);
  assert.match(verified.detail,/S3/);
});
test('missing flags never invent a green flag',()=>{
  const m=model(null,true);assert.equal(m.code,'unknown');
  assert.deepEqual(m.sectors,['unknown','unknown','unknown']);
});
