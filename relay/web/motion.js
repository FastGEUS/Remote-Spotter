/* Presentation only: do not extrapolate or modify telemetry. */
(function(root){
  "use strict";
  class MotionBuffer {
    constructor(delay=100){this.delay=delay;this.frames=[];this.key=null;this.seq=null;}
    push(state,now){
      const key=state.streamId+":"+state.sessionId;
      if(key!==this.key){this.frames=[];this.key=key;this.seq=null;}
      if(state.seq===this.seq)return false;
      this.seq=state.seq;
      const previous=this.frames.at(-1);
      if(previous&&(now-previous.time>500||state.gameTime<previous.gameTime))this.frames=[];
      this.frames.push({time:now,gameTime:state.gameTime,cars:state.cars.filter(c=>c.mapVisible!==false&&Number.isFinite(c.x)&&Number.isFinite(c.z)).map(c=>({...c}))});
      while(this.frames.length>60)this.frames.shift();
      return true;
    }
    sample(now,live=true){
      if(!this.frames.length)return [];
      const last=this.frames.at(-1);
      if(!live)return last.cars;
      const target=now-this.delay;
      while(this.frames.length>2&&this.frames[1].time<=target)this.frames.shift();
      const first=this.frames[0],next=this.frames[1];
      if(target<=first.time)return first.cars;
      if(!next||target>=last.time)return last.cars;
      const dt=(next.time-first.time)/1000;
      const t=Math.max(0,Math.min(1,(target-first.time)/(next.time-first.time)));
      const old=new Map(first.cars.map(c=>[c.id,c]));
      return next.cars.map(c=>{
        const p=old.get(c.id);
        if(!p||Math.hypot(c.x-p.x,c.z-p.z)>Math.max(80,(c.speedMps||0)*dt*4))return c;
        return {...c,x:p.x+(c.x-p.x)*t,z:p.z+(c.z-p.z)*t};
      });
    }
  }
  function bounds(points,cars,previous,complete){
    const list=(complete&&points.length?points:[...points,...cars.filter(c=>c.mapVisible!==false).map(c=>[c.x,c.z])]).filter(p=>p.every(Number.isFinite));
    if(!list.length)return previous;
    let minX=Infinity,maxX=-Infinity,minZ=Infinity,maxZ=-Infinity;
    for(const [x,z] of list){minX=Math.min(minX,x);maxX=Math.max(maxX,x);minZ=Math.min(minZ,z);maxZ=Math.max(maxZ,z);}
    if(previous&&!complete){minX=Math.min(minX,previous.minX);maxX=Math.max(maxX,previous.maxX);minZ=Math.min(minZ,previous.minZ);maxZ=Math.max(maxZ,previous.maxZ);}
    const cx=(minX+maxX)/2,cz=(minZ+maxZ)/2;
    const sx=Math.max(200,maxX-minX),sz=Math.max(200,maxZ-minZ);
    return {minX:cx-sx/2,maxX:cx+sx/2,minZ:cz-sz/2,maxZ:cz+sz/2};
  }
  const api={MotionBuffer,bounds};
  if(typeof module!=="undefined"&&module.exports)module.exports=api;
  else root.SpotterMotion=api;
})(typeof globalThis!=="undefined"?globalThis:this);
