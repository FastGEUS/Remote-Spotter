"use strict";
const el=id=>document.getElementById(id);
const theme=SpotterTheme;
const fmt=(n,d=1)=>typeof n==="number"&&Number.isFinite(n)?n.toFixed(d):"—";
const motion=new SpotterMotion.MotionBuffer(100);
let latest=null,lastMessage=0,lastRender=-Infinity;
let mapBounds=null,camera=null,mapKey=null,lastDraw=0,mapShape=null,mapFit=null;
function status(text,good){el("connection").textContent=text;el("connection").className=good?"good":"bad";}
function isLive(e){return viewConnection.state==="open"&&e?.sourceConnected&&e.sourceAgeMs<1000&&e.state?.status==="live"&&performance.now()-lastMessage<1000;}
const viewConnection=new SpotterConnection.Connection({
  onStatus:(_state,text)=>status(text,false),
  onAuth:()=>{el("login").hidden=false;},
  onOpen:()=>{el("login").hidden=true;el("dashboard").hidden=false;},
  onData:data=>{
    latest=data;lastMessage=performance.now();
    const s=latest.state;
    if(s&&motion.push(s,lastMessage)){
      const key=s.streamId+":"+s.sessionId;
      if(key!==mapKey){mapKey=key;mapBounds=null;camera=null;mapShape=null;mapFit=null;}
      const shape=JSON.stringify([s.trackmap.status,s.trackmap.points,s.trackmap.pitLanePoints||[]]);
      if(shape!==mapShape){mapShape=shape;mapFit=null;}
      mapBounds=SpotterMotion.bounds(s.trackmap.points.concat(s.trackmap.pitLanePoints||[]),s.cars,mapBounds,["demo","recorded"].includes(s.trackmap.status));
    }
  }
});
function connect(){viewConnection.start();}
el("login-form").addEventListener("submit",async e=>{
  e.preventDefault();el("login-error").textContent="";
  try{const r=await fetch("/api/session",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({token:el("token").value})});
    el("token").value="";if(!r.ok)throw Error("Неверный ключ или отказ сервера");connect();
  }catch(err){el("login-error").textContent=err.message;}
});
const wheelNodes=["FL","FR","RL","RR"].map(label=>{
  const box=document.createElement("div");box.className="wheel";
  const title=document.createElement("strong");title.textContent=label;
  const value=document.createElement("b"),pressure=document.createElement("span"),condition=document.createElement("span"),detail=document.createElement("small"),triple=document.createElement("div"),geometry=document.createElement("small");
  triple.className="temp-triple";triple.title="Температура протектора: внутренняя / центр / внешняя";
  for(let i=0;i<3;i++)triple.append(document.createElement("em"));geometry.className="geometry";
  condition.className="condition";box.append(title,value,triple,pressure,condition,detail,geometry);el("wheels").append(box);
  return {value,pressure,condition,detail,triple,geometry};
});
const rows=new Map();
function render(envelope){
  const s=envelope.state;
  if(!s){if(viewConnection.state==="open"){const label=SpotterStatus.describe(envelope,true,performance.now()-lastMessage);status(label.text,label.good);}return;}
  SpotterPanels.render({...envelope,sourceConnected:envelope.sourceConnected&&viewConnection.state==="open",
    sourceAgeMs:envelope.sourceAgeMs+Math.max(0,performance.now()-lastMessage)});
  SpotterSectors.render(envelope,isLive(envelope));
  SpotterCockpit.render(s,isLive(envelope));
  if(viewConnection.state==="open"){const label=SpotterStatus.describe(envelope,true,performance.now()-lastMessage);status(label.text,label.good);}
  el("track").textContent=s.session.track||"Ожидание игры";
  el("mode").textContent=s.mode==="demo"?"ДЕМО • синтетические данные":s.mode==='iracing'?"iRacing • SDK":"LMU • телеметрия";
  document.querySelector('.flag-settings').hidden=s.mode==='iracing';
  document.querySelector('.tire-note').textContent=s.mode==='iracing'?'FL / FR — передние · RL / RR — задние. 100% — новая шина. Каркас: левая / центр / правая. Шины: снимок SDK из питов, не непрерывные измерения.':'FL / FR — передние · RL / RR — задние. 100% — новая шина. Температура протектора: внутренняя / центр / внешняя.';
  if(s.mode==='iracing')document.querySelector('.legend').textContent='Пилот · соперники · позиции на карте приблизительные';
  else document.querySelector('.legend').textContent='Пилот · Hypercar · LMGT3';
  el("quality").textContent=`Возраст на VPS ${Math.max(0,Math.round(envelope.sourceAgeMs))} мс`;
  el("compute").textContent=`Расчёт на VPS ${fmt(envelope.computeMs,2)} мс`;
  el("speed").textContent=fmt(s.pilot?.speedKph,0);
  const gear=s.pilot?.gear;el("gear").textContent=gear===0?"N":gear===-1?"R":gear??"—";
  el("rpm").textContent=fmt(s.pilot?.rpm,0)+" об/мин";el("fuel").textContent=fmt(s.pilot?.fuelL);
  const strategy=s.strategy, fuel=strategy?.fuel, energy=strategy?.energy;
  const original=strategy?.status==="active";
  el("laps").textContent=fmt(original?fuel?.lapsRemaining:s.fuel.lapsRemaining);
  const consumption=original?fuel?.estimatedConsumption:s.fuel.consumptionLPerLap;
  el("consumption").textContent=consumption?`${fmt(consumption,2)} л/круг`:"Сбор данных";
  el("fuel-note").textContent=consumption?(original?"Расчёт топлива TinyPedal":"Базовая оценка по полным кругам"):"Расход появится после полного круга без питов и разрывов.";
  el("energy").textContent=fmt(energy?.amount,1);
  el("energy-laps").textContent=fmt(energy?.lapsRemaining,1);
  el("energy-consumption").textContent=energy?.estimatedConsumption?`${fmt(energy.estimatedConsumption,2)} %/круг`:"Сбор данных";
  const minutes=[fuel?.minutesRemaining,energy?.minutesRemaining].filter(v=>typeof v==="number"&&v>=0);
  el("stint-minutes").textContent=minutes.length?fmt(Math.min(...minutes),1):"—";
  el("strategy-note").textContent=strategy?.status==="collector-update-required"?"Обновите сборщик пилота для расчёта энергии.":
    !original?"Ожидание телеметрии":energy?.status==="unavailable"?"Виртуальная энергия пока недоступна. Расчёт времени — по последнему валидному кругу.":
    s.overlays?"Лимит стинта — по топливу и энергии. Темп рассчитывает DeltaModule TinyPedal.":"Лимит стинта — по топливу и энергии. Темп — последний валидный круг.";
  if(s.mode==='iracing'){
    el('strategy-note').textContent='iRacing: базовая оценка топлива по полным кругам. Виртуальная энергия LMU не применяется.';
    el('energy-consumption').textContent='Не применяется';
  }
  el("map-status").textContent=({demo:"ДЕМО-КАРТА",recording:"ЗАПИСЬ ТРАССЫ",recorded:"КРУГ ЗАПИСАН"})[s.trackmap.status]||"ОЖИДАНИЕ";
  el("map-note").textContent=s.mode==="demo"?"Синтетическая трасса · демонстрация передачи данных":s.trackmap.sectorGeometry?"S/F — старт/финиш; S1/S2 и S2/S3 — записанные границы секторов. Жёлтая подсветка — подтверждённый локальный флаг.":"Границы секторов появятся после записи полного круга TinyPedal или импорта карты с отсечками.";
  if(s.mode==='iracing')el('map-note').textContent='iRacing: приблизительная карта записывается на VPS по полному кругу без питов и разрывов. Машины проецируются по доле круга; локальный жёлтый не привязан к сектору.';
  el("map-empty").hidden=s.cars.some(c=>Number.isFinite(c.x)&&Number.isFinite(c.z))||s.trackmap.points.length>1;
  wheelNodes.forEach((node,i)=>{
    const w=s.pilot?.wheels?.[i];node.value.textContent=`${fmt(w?.temperatureC)}°`;
    node.pressure.textContent=`${fmt(w?.pressureKpa,0)} кПа`;
    node.condition.textContent=`Состояние ${fmt(typeof w?.wear==="number"?w.wear*100:null,0)}%`;
    node.detail.textContent=`Тормоз ${fmt(w?.brakeC,0)} °C`;
    const temperatures=s.overlays?.values?.[s.mode==='iracing'?'api.tyre.carcass_temperature_ico':'api.tyre.surface_temperature_ico']?.value;
    for(let j=0;j<3;j++)node.triple.children[j].textContent=`${fmt(temperatures?.[i*3+j],0)}°`;
    const m=s.overlays?.modules?.wheels;
    node.geometry.textContent=`Развал ${fmt(m?.camberAngle?.[i],1)}° · Toe ${fmt(m?.toeAngle?.[i],2)}°`;
  });
  const table=el("standings"),present=new Set();el("car-count").textContent=`${s.cars.length} машин`;
  s.cars.forEach((c,index)=>{
    present.add(c.id);let row=rows.get(c.id);
    if(!row){row=document.createElement("tr");for(let i=0;i<5;i++)row.append(document.createElement("td"));rows.set(c.id,row);}
    row.className=c.id===s.pilot?.id?"own":"";
    [c.place,"",c.driver,c.laps,c.inPit?"PIT":c.place===1?"ЛИДЕР":typeof c.gapBehindLeader==='number'&&Number.isFinite(c.gapBehindLeader)&&c.gapBehindLeader>=0&&c.gapBehindLeader<99999?`+${fmt(c.gapBehindLeader,1)}`:"—"].forEach((v,i)=>{if(i!==1)row.children[i].textContent=v;});
    let tag=row.children[1].firstChild;if(!tag){tag=document.createElement("span");row.children[1].append(tag);}
    tag.className='class-tag'+(c.class==='Hypercar'?'':' gt');tag.textContent=`${c.class==='Hypercar'?'HYP':c.class==='LMGT3'?'GT3':c.class} ${c.classPlace}`;
    row.children[2].title=c.driver;
    if(table.children[index]!==row)table.insertBefore(row,table.children[index]||null);
  });
  for(const [id,row] of rows)if(!present.has(id)){row.remove();rows.delete(id);}
}
const canvas=el("map"),ctx=canvas.getContext("2d");
function draw(now){
  const dt=Math.min(100,Math.max(0,now-lastDraw));lastDraw=now;
  if(latest&&now-lastRender>=100){render(latest);lastRender=now;}
  const dpr=Math.min(devicePixelRatio||1,2),w=canvas.clientWidth,h=canvas.clientHeight;
  if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);camera=null;mapFit=null;}
  ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
  const s=latest?.state;
  if(s&&mapBounds&&w&&h){
    const complete=["demo","recorded"].includes(s.trackmap.status);
    if(complete&&!mapFit)mapFit=SpotterMap.fit(s.trackmap.points.concat(s.trackmap.pitLanePoints||[]),w,h);
    const target=complete&&mapFit?mapFit:SpotterMap.fit([[mapBounds.minX,mapBounds.minZ],[mapBounds.maxX,mapBounds.maxZ]],w,h,28,false);
    if(!target){requestAnimationFrame(draw);return;}
    if(camera&&camera.angle!==target.angle)camera=null;
    if(!camera)camera=target;
    else{const blend=1-Math.exp(-dt/300);for(const k of ["x","z","scale"])camera[k]+=(target[k]-camera[k])*blend;}
    const project=p=>SpotterMap.project(p,camera,w,h);
    const points=s.trackmap.points;
    const path=()=>{ctx.beginPath();points.forEach((p,i)=>{const [x,y]=project(p);if(!i)ctx.moveTo(x,y);else ctx.lineTo(x,y);});
      if(points.length>2&&["demo","recorded"].includes(s.trackmap.status))ctx.closePath();};
    ctx.lineJoin="round";ctx.lineCap="round";
    path();ctx.strokeStyle=theme.plot;ctx.lineWidth=14;ctx.stroke();
    path();ctx.strokeStyle=theme.border;ctx.lineWidth=9;ctx.stroke();
    SpotterSectors.draw(ctx,project,s,isLive(latest));
    if(s.trackmap.pitLanePoints?.length){ctx.beginPath();s.trackmap.pitLanePoints.forEach((p,i)=>{const [x,y]=project(p);i?ctx.lineTo(x,y):ctx.moveTo(x,y);});ctx.strokeStyle=theme.warning;ctx.lineWidth=4;ctx.stroke();}
    path();ctx.strokeStyle=theme.textMuted;ctx.lineWidth=1;ctx.stroke();
    const cars=motion.sample(now,isLive(latest));
    const ordered=[...cars.filter(c=>c.id!==s.pilot?.id),...cars.filter(c=>c.id===s.pilot?.id)];
    ctx.save();ctx.font="800 12px ui-monospace, monospace";ctx.textAlign="center";ctx.textBaseline="middle";
    for(const c of ordered){const [x,y]=project([c.x,c.z]),own=c.id===s.pilot?.id;
      const label=s.mode==='iracing'&&c.number?c.number:Number.isFinite(c.place)&&c.place>0?String(c.place):"—";
      const radius=Math.max(own?9.5:8,label.length>=3?10:0);
      if(own){ctx.fillStyle=theme.plot;ctx.beginPath();ctx.arc(x,y,radius+2,0,Math.PI*2);ctx.fill();}
      ctx.fillStyle=own?theme.text:c.class==="Hypercar"?theme.hypercar:theme.gt;
      ctx.beginPath();ctx.arc(x,y,radius,0,Math.PI*2);ctx.fill();ctx.strokeStyle=own?theme.accent:theme.background;ctx.lineWidth=own?1.5:1;ctx.stroke();
      ctx.fillStyle=theme.background;ctx.fillText(label,x,y,radius*2-4);
    }
    ctx.restore();
  }
  requestAnimationFrame(draw);
}
requestAnimationFrame(draw);connect();
