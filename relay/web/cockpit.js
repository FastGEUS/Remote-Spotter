"use strict";
/* Main instruments display server results. No pace/strategy calculations here. */
window.SpotterCockpit=(()=>{
  const T=SpotterTheme;
  const $=id=>document.getElementById(id),finite=n=>typeof n==="number"&&Number.isFinite(n);
  const fmt=(n,d=0)=>finite(n)?n.toFixed(d):"—";
  const api=(s,key)=>s.overlays?.values?.['api.'+key]?.value;
  const set=(id,text)=>$(id).textContent=text;
  const clamp=(n,a,b)=>Math.max(a,Math.min(b,n));
  function clock(n){if(!finite(n)||n<0)return "—";n=Math.floor(n);return [Math.floor(n/3600),Math.floor(n/60)%60,n%60].map(x=>String(x).padStart(2,'0')).join(':');}
  function lapTime(n){return finite(n)&&n>0&&n<99999?SpotterSectors.time(n):"—";}
  const pedals=[['throttle','ГАЗ',T.throttle],['brake','ТОРМ',T.brake],['clutch','СЦЕП',T.clutch]].map(([key,label,color])=>{
    const box=document.createElement('div'),value=document.createElement('span'),track=document.createElement('div'),fill=document.createElement('div'),name=document.createElement('small');
    box.className='pedal';box.style.setProperty('--pedal-color',color);box.dataset.input=key;track.className='pedal-track';fill.className='pedal-fill';name.textContent=label;track.append(fill);box.append(value,track,name);$('pedals').append(box);return {key,box,value,fill};
  });
  const switches=[['tc_level','TC'],['abs_level','ABS'],['speed_limiter','ЛИМИТ'],['headlights','СВЕТ'],['ignition_starter','ЗАЖИГ.'],['drs_status','DRS']].map(([key,label])=>{
    const cell=document.createElement('div'),value=document.createElement('strong');cell.className='switch-cell';cell.append(document.createTextNode(label),value);$('switches').append(cell);return {key,cell,value};
  });
  const leds=Array.from({length:16},()=>{const led=document.createElement('i');$('rpm-led').append(led);return led;});
  function surface(id){
    const canvas=$(id),w=canvas.clientWidth,h=canvas.clientHeight,dpr=Math.min(devicePixelRatio||1,2);
    if(!w||!h)return null;
    if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);}
    const ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);ctx.textAlign='left';ctx.textBaseline='alphabetic';return {ctx,w,h};
  }
  function drawRadar(s){
    const draw=surface('radar');if(!draw)return;
    const range=Number($('radar-range').value),{ctx,w,h}=draw,cx=w/2,cy=h/2,r=Math.min(w,h)/2-24,scale=r/range;
    if(s.mode==='iracing'){
      SpotterRadar.drawCar(ctx,cx,cy,0,6,T.text);
      const n=s.overlays?.proximity?.leftRight,left=[2,4,5].includes(n),right=[3,4,6].includes(n);
      ctx.textAlign='center';ctx.font='12px system-ui';
      for(const [x,active,label] of [[cx-65,left,'СЛЕВА'],[cx+65,right,'СПРАВА']]){
        ctx.fillStyle=active?T.warning:T.border;ctx.fillRect(x-20,cy-23,40,46);
        ctx.fillStyle=active?T.warning:T.textSecondary;ctx.fillText(label,x,cy-34);
      }
      ctx.fillStyle=T.textSecondary;ctx.font='11px system-ui';
      ctx.fillText(({1:'Слева / справа свободно',2:'Машина слева',3:'Машина справа',4:'Машины с обеих сторон',5:'Две машины слева',6:'Две машины справа'})[n]||'Нет данных о соседстве',cx,cy+55);
      ctx.font='9px system-ui';ctx.fillText('Индикатор SDK · расстояния не передаются',cx,h-12);return;
    }
    ctx.strokeStyle=T.border;ctx.lineWidth=1;
    for(const fraction of [.25,.5,1]){ctx.beginPath();ctx.arc(cx,cy,r*fraction,0,2*Math.PI);ctx.stroke();}
    ctx.beginPath();ctx.moveTo(cx-r,cy);ctx.lineTo(cx+r,cy);ctx.moveTo(cx,cy-r);ctx.lineTo(cx,cy+r);ctx.stroke();
    ctx.fillStyle=T.textMuted;ctx.font='9px system-ui';ctx.textAlign='center';ctx.fillText('ВПЕРЕДИ',cx,12);ctx.fillText('СЗАДИ',cx,h-6);ctx.textAlign='right';ctx.fillText(`${range} м`,w-6,cy+3);ctx.textAlign='left';
    const race=s.overlays?.race||[];
    for(const c of race){
      if(c.isPlayer||!finite(c.relativeRotatedPositionX)||!finite(c.relativeRotatedPositionY)||Math.hypot(c.relativeRotatedPositionX,c.relativeRotatedPositionY)>range)continue;
      const {x,y,angle}=SpotterRadar.project(c,cx,cy,scale);
      SpotterRadar.drawCar(ctx,x,y,angle,scale,c.isYellow?T.warning:c.vehicleClass==='Hypercar'?T.hypercar:T.gt);
      ctx.fillStyle=T.textSecondary;ctx.font='10px system-ui';ctx.fillText(String(c.positionOverall??''),x+SpotterRadar.body(scale).width/2+3,y+3);
    }
    SpotterRadar.drawCar(ctx,cx,cy,0,scale,T.text);
    if(!race.length){ctx.fillStyle=T.textSecondary;ctx.textAlign='center';ctx.fillText('Нет координат',cx,cy+r+10);}
  }
  function drawForce(s){
    const draw=surface('gforce');if(!draw)return;const {ctx,w,h}=draw,cx=w/2,cy=h/2,r=Math.min(w,h)/2-12;
    ctx.strokeStyle=T.border;ctx.lineWidth=1;
    for(const fraction of [1/3,2/3,1]){ctx.beginPath();ctx.arc(cx,cy,r*fraction,0,2*Math.PI);ctx.stroke();}
    ctx.beginPath();ctx.moveTo(cx-r,cy);ctx.lineTo(cx+r,cy);ctx.moveTo(cx,cy-r);ctx.lineTo(cx,cy+r);ctx.stroke();
    ctx.fillStyle=T.textMuted;ctx.font='8px system-ui';ctx.fillText('3G',cx+3,cy-r-2);
    const f=s.overlays?.modules?.force,x=f?.latGForceRaw,y=f?.lgtGForceRaw;
    if(finite(x)&&finite(y)){const magnitude=Math.hypot(x,y),scale=r/Math.max(3,magnitude);ctx.fillStyle=T.hypercar;ctx.beginPath();ctx.arc(cx+x*scale,cy+y*scale,4,0,2*Math.PI);ctx.fill();}
    set('force-values',`X ${fmt(x,2)} · Y ${fmt(y,2)} G`);
  }
  function drawTraces(s){
    const draw=surface('traces');if(!draw)return;const {ctx,w,h}=draw,left=26,right=w-8,top=10,bottom=h-18;
    ctx.strokeStyle=T.border;ctx.lineWidth=1;ctx.fillStyle=T.textMuted;ctx.font='8px system-ui';
    for(const [v,label] of [[0,'0'],[.5,'50'],[1,'100']]){const y=bottom-v*(bottom-top);ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(right,y);ctx.stroke();ctx.fillText(label,3,y+3);}
    const points=s.overlays?.widgetMath?.trailing?.samples||[];
    if(points.length<2){set('trace-range','Ожидание данных');ctx.fillText('Ожидание телеметрии',left+8,top+18);return;}
    const start=points[0][0],end=points.at(-1)[0],duration=end-start;
    if(!finite(duration)||duration<=0)return;
    set('trace-range',`${duration.toFixed(1)} с · руль ±100%`);
    for(const [column,color] of [[1,T.throttle],[2,T.brake],[3,T.clutch],[4,T.steering]]){
      ctx.beginPath();ctx.strokeStyle=color;ctx.setLineDash(column===3?[6,3]:column===4?[2,3]:[]);ctx.lineWidth=column===1?1.8:1.5;let started=false;
      for(const p of points){if(!finite(p[column])){started=false;continue;}const x=left+(p[0]-start)/duration*(right-left),value=column===4?(p[column]+1)/2:p[column],y=bottom-clamp(value,0,1)*(bottom-top);started?ctx.lineTo(x,y):ctx.moveTo(x,y);started=true;}ctx.stroke();
    }
    ctx.setLineDash([]);ctx.fillStyle=T.textMuted;ctx.fillText(`−${duration.toFixed(1)} с`,left,h-4);ctx.textAlign='right';ctx.fillText('сейчас',right,h-4);
  }
  function render(s,live){
    document.querySelector('.radar-range').hidden=s.mode==='iracing';
    document.querySelector('.radar-panel h2').textContent=s.mode==='iracing'?'Темп и соседство':'Темп и радар';
    $('radar').setAttribute('aria-label',s.mode==='iracing'?'Индикатор соседства слева и справа из SDK':'Радар ближайших машин');
    $('dashboard').classList.toggle('dashboard-stale',!live);
    set('track-clock',clock(api(s,'session.track_time')));
    const remaining=api(s,'session.remaining'),maximum=s.session?.maxLaps;
    const timed=finite(remaining)&&remaining>0;
    set('session-left-label',timed?'ДО КОНЦА СЕССИИ':'ФОРМАТ СЕССИИ');
    set('session-left',timed?clock(remaining):finite(maximum)&&maximum>0&&maximum<999999?`${maximum} кругов`:"—");
    const own=s.cars.find(c=>c.id===s.pilot?.id);set('pilot-lap',s.pilot?.lap??'—');set('pilot-position',own?`P${own.place} / P${own.classPlace}`:'—');
    const air=api(s,'session.ambient_temperature'),track=api(s,'session.track_temperature'),rain=api(s,'session.raininess');
    set('weather',`Воздух ${fmt(air)}° · Трасса ${fmt(track)}° · Дождь ${finite(rain)?fmt(rain*100):'—'}%`);
    pedals.forEach(n=>{const v=api(s,'inputs.'+n.key)??s.pilot?.[n.key];n.value.textContent=finite(v)?fmt(v*100):'—';n.fill.style.height=`${finite(v)?clamp(v,0,1)*100:0}%`;n.box.classList.toggle('unknown',!finite(v));});
    switches.forEach(n=>{const v=api(s,'switch.'+n.key);n.value.textContent=v==null||v===-1?'—':n.key==='headlights'||n.key==='speed_limiter'?(v?'ON':'OFF'):String(v);n.cell.classList.toggle('active',live&&(n.key==='headlights'||n.key==='speed_limiter')&&!!v);});
    const rpm=s.pilot?.rpm,max=api(s,'engine.rpm_max');leds.forEach((led,i)=>led.style.background=finite(rpm)&&finite(max)&&max>0&&rpm/max>(i+1)/16?(i>12?T.error:i>10?T.warning:T.textSecondary):T.border);
    set('steering-value',`Руль: ${fmt(s.overlays?.widgetMath?.steering_angle?.degrees,1)}°`);
    const delta=s.overlays?.modules?.delta;
    set('lap-current',lapTime(api(s,'timing.current_laptime')??delta?.lapTimeCurrent));set('lap-last',lapTime(own?.lastLapTime??delta?.lapTimeLast));set('lap-best',lapTime(lapTime(delta?.lapTimeSession)!=='—'?delta.lapTimeSession:own?.bestLapTime));set('lap-estimated',lapTime(delta?.lapTimeEstimated));
    const d=delta?.deltaSession,best=delta?.lapTimeSession;
    set('lap-delta',finite(d)&&finite(best)&&best>0&&best<99999?`Δ сессии ${d>0?'+':''}${d.toFixed(3)}`:'Дельта: —');
    $('lap-delta').className='badge '+(finite(best)&&best>0&&finite(d)?d<=0?'split-good':'split-slow':'');
    set('lap-valid',!live?'Данные устарели':s.pilot?.lapValid==null?'Валидность: —':s.pilot.lapValid?'Валидный круг':'Невалидный круг');
    const nearby=$('nearby');nearby.replaceChildren();
    const cars=s.cars.filter(c=>c.id!==s.pilot?.id&&finite(c.relativeGap)).sort((a,b)=>Math.abs(a.relativeGap)-Math.abs(b.relativeGap)).slice(0,3).sort((a,b)=>b.relativeGap-a.relativeGap);
    for(const c of cars){const row=document.createElement('div'),pos=document.createElement('small'),name=document.createElement('span'),gap=document.createElement('strong');row.className='nearby-row';pos.textContent=`P${c.place}`;name.textContent=c.driver;gap.textContent=c.inPit?'PIT':`${c.relativeGap>0?'↑':'↓'} ${Math.abs(c.relativeGap).toFixed(2)} с`;row.append(pos,name,gap);nearby.append(row);}
    if(!cars.length){const empty=document.createElement('span');empty.className='muted';empty.textContent='Ожидание интервалов';nearby.append(empty);}
    drawRadar(s);drawForce(s);drawTraces(s);
  }
  return {render};
})();
