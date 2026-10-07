const test=require('node:test');const assert=require('node:assert/strict');
const {Connection}=require('../../relay/web/connection.js');
function harness(fetch=async()=>({ok:true,status:204})){
  let now=0,next=0;const timers=new Map(),sockets=[],statuses=[],auth=[];
  class Socket{constructor(){sockets.push(this);}close(){this.closed=true;this.onclose?.();}}
  const c=new Connection({origin:'http://localhost',WebSocket:Socket,fetch,clock:()=>now,
    setTimer:(fn,delay)=>{const id=++next;timers.set(id,{fn,time:now+delay});return id;},clearTimer:id=>timers.delete(id),
    onStatus:(s,t)=>statuses.push([s,t]),onAuth:()=>auth.push(true)});
  async function advance(ms){const end=now+ms;while(true){const due=[...timers].filter(([,t])=>t.time<=end).sort((a,b)=>a[1].time-b[1].time)[0];if(!due)break;timers.delete(due[0]);now=due[1].time;due[1].fn();await new Promise(setImmediate);}now=end;await new Promise(setImmediate);}
  return {c,sockets,statuses,auth,timers,advance};
}
test('open socket without packets is replaced; late close cannot kill replacement',async()=>{
  const h=harness();await h.c.start();const old=h.sockets[0];old.onopen();
  await h.advance(8000);assert.equal(h.c.state,'retry');assert.ok(old.closed);
  await h.advance(1000);assert.equal(h.sockets.length,2);const next=h.sockets[1];next.onopen();
  old.onclose();assert.equal(h.c.socket,next);assert.equal(h.c.state,'open');h.c.stop();
});
test('regular envelopes keep the viewer connection, even when pilot is disconnected',async()=>{
  const h=harness();await h.c.start();const ws=h.sockets[0];ws.onopen();
  for(let i=0;i<20;i++){await h.advance(1000);ws.onmessage({data:'{"sourceConnected":false,"state":null}'});}
  assert.equal(h.sockets.length,1);assert.equal(h.c.state,'open');h.c.stop();
});
test('expired cookie shows login and stops retries; renewed login can start again',async()=>{
  let allowed=false;const h=harness(async()=>({ok:allowed,status:allowed?204:401}));
  await h.c.start();assert.equal(h.c.state,'auth');assert.equal(h.auth.length,1);
  await h.advance(60000);assert.equal(h.sockets.length,0);assert.equal(h.timers.size,0);
  allowed=true;await h.c.start();assert.equal(h.sockets.length,1);h.c.stop();
});
test('stalled handshake and failed HTTP request retry with bounded backoff',async()=>{
  const h=harness();await h.c.start();await h.advance(8000);assert.equal(h.c.state,'retry');
  await h.advance(1000);assert.equal(h.sockets.length,2);
  h.sockets[1].onerror();await h.advance(2000);assert.equal(h.sockets.length,3);h.c.stop();
  const failure=harness(async()=>{throw Error('offline');});await failure.c.start();assert.equal(failure.c.state,'retry');
  await failure.advance(1000);assert.equal(failure.c.state,'retry');assert.equal(failure.sockets.length,0);failure.c.stop();
});
