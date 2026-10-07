const {test}=require('node:test');
const assert=require('node:assert/strict');
const {MotionBuffer,bounds}=require('../../relay/web/motion.js');
const frame=(seq,x,extra={})=>({streamId:'a',sessionId:'one',seq,gameTime:seq/20,cars:[{id:1,x,z:0,speedMps:50}],...extra});
test('positions interpolate, never predict beyond last packet',()=>{
  const m=new MotionBuffer(100);m.push(frame(0,0),0);m.push(frame(1,10),50);
  assert.equal(m.sample(125)[0].x,5);assert.equal(m.sample(300)[0].x,10);
  assert.equal(m.sample(125,false)[0].x,10);
});
test('repeated relay envelopes do not replace samples',()=>{
  const m=new MotionBuffer();m.push(frame(0,0),0);assert.equal(m.push(frame(0,10),30),false);
  assert.equal(m.frames.length,1);assert.equal(m.sample(200)[0].x,0);
});
test('session changes, long gaps and rewinds reset movement',()=>{
  const m=new MotionBuffer();m.push(frame(0,0),0);m.push(frame(1,10),50);
  m.push(frame(2,900,{sessionId:'two'}),100);assert.equal(m.frames.length,1);
  m.push(frame(3,1000,{sessionId:'two'}),700);assert.equal(m.frames.length,1);
  m.push(frame(4,300,{sessionId:'two',gameTime:0}),750);assert.equal(m.frames.length,1);
});
test('teleports do not sweep across the circuit; joins use car IDs',()=>{
  const m=new MotionBuffer();m.push(frame(0,0),0);m.push(frame(1,1000),50);
  assert.equal(m.sample(125)[0].x,1000);
  const n=new MotionBuffer();n.push(frame(0,0),0);n.push(frame(1,10,{cars:[{id:2,x:50,z:0},{id:1,x:10,z:0}]}),50);
  assert.deepEqual(n.sample(125).map(c=>[c.id,c.x]),[[2,50],[1,5]]);
});
test('recorded geometry keeps camera stable despite traffic; recording never shrinks',()=>{
  const points=[[0,0],[1000,500]];
  const fixed=bounds(points,[{x:5000,z:1000}],null,true);
  assert.deepEqual(fixed,bounds(points,[{x:-9000,z:-4000}],null,true));
  const growing=bounds([], [{x:0,z:0},{x:1000,z:500}],null,false);
  const next=bounds([], [{x:400,z:200}],growing,false);
  assert.deepEqual(growing,next);
});
test('unrecorded iRacing rivals never appear at the origin or poison map bounds',()=>{
  const m=new MotionBuffer();
  const cars=[{id:1,x:null,z:null,mapVisible:false},{id:2,x:0,z:0,mapVisible:false},{id:3,x:20,z:30,mapVisible:true}];
  m.push(frame(0,0,{mode:'iracing',cars}),0);
  assert.deepEqual(m.sample(200).map(c=>c.id),[3]);
  assert.equal(bounds([],cars.slice(0,2),null,false),null);
  assert.equal(bounds([[NaN,0]],cars.slice(0,2),null,true),null);
});
