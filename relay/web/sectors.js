"use strict";
window.SpotterSectors=(()=>{
  const T=SpotterTheme;
  const get=id=>document.getElementById(id),colors=[T.sector1,T.sector2,T.sector3];
  const labels={green:"Зелёный флаг",yellow:"Локальный жёлтый",caution:"FCY / Safety Car",finished:"Сессия завершена",stopped:"Сессия остановлена",starting:"Стартовая процедура",waiting:"Ожидание старта",blue:"Синий флаг пилоту",unknown:"Сектор не сопоставлен",clear:"Нет локального жёлтого",stale:"Данные устарели"};
  let envelope=null,historyKey=null,history=[],order="";
  try{order=localStorage.getItem('spotter-flag-order')||"";}catch{}
  if(!/^(012|021|102|120|201|210)$/.test(order))order="";
  get('flag-order').value=order;
  get('flag-order').addEventListener('change',e=>{order=e.target.value;try{localStorage.setItem('spotter-flag-order',order);}catch{}historyKey=null;});
  function flags(state,live){
    if(!live)return ['stale','stale','stale'];
    const f=state?.overlays?.flags;
    if(f?.sectorFlags)return f.sectorFlags;
    if(state?.mode==='iracing'||!f||!order)return ['unknown','unknown','unknown'];
    return [0,1,2].map(s=>{const v=f.rawChannels[order.indexOf(String(s))];return v===1?'yellow':v===0?'clear':'unknown';});
  }
  function time(n){if(typeof n!=='number'||!Number.isFinite(n)||n<0||n>=99999)return '—';const ms=Math.round(n*1000);return `${Math.floor(ms/60000)}:${String(Math.floor(ms/1000)%60).padStart(2,'0')}.${String(ms%1000).padStart(3,'0')}`;}
  const cards=[0,1,2].map(i=>{const card=document.createElement('div');card.className='sector-card';card.style.setProperty('--sector-color',colors[i]);
    const title=document.createElement('h3');title.textContent=`СЕКТОР ${i+1} · S${i+1}`;
    const flag=document.createElement('div');flag.className='sector-indicator';const lamp=document.createElement('span'),name=document.createElement('strong'),label=document.createElement('span');lamp.className='flag-light';name.textContent=`S${i+1}`;flag.append(lamp,name,label);get('sector-flags').append(flag);
    const values=['Текущий','Последний','Лучший'].map(text=>{const row=document.createElement('div');row.className='sector-time';const label=document.createElement('span'),value=document.createElement('strong');label.textContent=text;row.append(label,value);card.append(row);return value;});
    const note=document.createElement('small');card.prepend(title);card.append(note);get('sector-cards').append(card);return {card,flag,label,values,note};});
  function render(e,live){
    envelope=e;const s=e.state,f=s?.overlays?.flags,t=s?.overlays?.sectorTiming;
    const codes=flags(s,live);
    SpotterFlags.render(s,live,codes);
    get('flag-channels').textContent=f?`Каналы LMU: ${f.rawChannels.map((c,i)=>`${i}: ${c===1?'жёлтый':c===0?'нет жёлтого':`неизвестно (${c})`}`).join(' · ')}. ${s.mode==='demo'?'В демо порядок задан синтетически.':order?'Используется подтверждённое вами соответствие.':'Без подтверждения участок карты не подсвечивается.'}`:'Нет данных: нужен сборщик с полным снимком LMU.';
    if(s?.mode==='iracing')get('flag-channels').textContent='iRacing: общий флаг и флаги пилота из SDK; флаги по отдельным секторам не передаются.';
    cards.forEach((node,i)=>{node.card.classList.toggle('active',live&&t?.currentSector===i+1);const flagCode=live&&f?.session==='caution'?'caution':codes[i];node.flag.className=`sector-indicator flag-${flagCode}`;node.label.textContent=labels[flagCode]||flagCode;node.flag.title=labels[flagCode]||flagCode;
      node.values[0].textContent=live&&t?.currentSector===i+1?`${time(t.elapsed)} ≈`:time(t?.current?.[i]);node.values[1].textContent=time(t?.last?.[i]);node.values[2].textContent=time(t?.best?.[i]);
      const rawDelta=t?.delta?.[i],d=typeof rawDelta==='number'&&Number.isFinite(rawDelta)?Math.round(rawDelta*1000)/1000:null,ref=t?.reference?.[i];
      node.note.textContent=typeof d==='number'&&Number.isFinite(d)?`${d<0?'−':d>0?'+':'±'}${Math.abs(d).toFixed(3)} с · эталон ${time(ref)}`:live&&t?.valid===false?'Невалидный круг':live&&t?.currentSector===i+1?'≈ текущий счётчик':'Ожидание сравнения';
      node.note.title=typeof d==='number'?`Круг ${t?.comparisonLap?.[i]??t?.lap} · сравнение с лучшим сектором до начала этого круга`:'';
      node.note.className=typeof d==='number'?(d<=0?'split-good':'split-slow'):'';});
    history=t?.history||[];get('sector-export').disabled=!history.length;
    get('sector-history-note').textContent=t?.storageError?'Ошибка сохранения журнала на VPS. CSV содержит полученные данные.':!t?'Ожидание полного снимка LMU':`${history.length} записей · последние 200 кругов. Первый неполный круг пропускается; невалидные круги отмечаются. Журнал сохраняется на VPS.`;
    if(s?.mode==='iracing')get('sector-history-note').textContent=t?`${history.length} кругов · приблизительные времена пересечения отсечек SDK при 20 Гц. Официальная валидность круга не передаётся.`:`Ожидание отсечек iRacing; число секторов ${s.session?.sectorCount??0}. Эта панель рассчитана на три сектора.`;
    const key=[s?.streamId,s?.sessionId,history.length,history.at(-1)?.lapStart].join(':');
    if(key!==historyKey){historyKey=key;const body=get('sector-history');body.replaceChildren();for(const row of [...history].reverse()){const tr=document.createElement('tr');const status=row.status==='estimated'?'Оценка 20 Гц':row.status==='complete'?'Валидный':row.status==='invalid'?'Невалидный':'Нет времени игры';[row.lap,...row.sectors.map(time),time(row.total),status+(row.inPit?' · пит':'')].forEach(value=>{const td=document.createElement('td');td.textContent=value;tr.append(td);});body.append(tr);}}
  }
  get('sector-export').addEventListener('click',()=>{if(!history.length)return;const csv=['lap,S1_seconds,S2_seconds,S3_seconds,lap_seconds,valid,in_pit,status',...history.map(r=>[r.lap,...r.sectors.map(v=>v??''),r.total??'',r.valid,r.inPit,r.status].join(','))].join('\r\n');const url=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'}));const link=document.createElement('a');link.href=url;link.download='sector-laps.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),2000);});
  get('map-expand').addEventListener('click',async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await get('map-panel').requestFullscreen();}catch{get('map-note').textContent='Браузер не разрешил полноэкранный режим.';}});
  document.addEventListener('fullscreenchange',()=>{
    const fullscreen=document.fullscreenElement===get('map-panel'),screen=get('flag-screen');
    get('map-expand').textContent=fullscreen?'Свернуть':'На весь экран';
    screen.classList.toggle('flag-floating',fullscreen);
    (fullscreen?document.querySelector('.map-wrap'):document.querySelector('.flag-panel')).append(screen);
  });
  function draw(ctx,project,state,live){
    const points=state.trackmap.points,g=state.trackmap.sectorGeometry;
    if(!g)return;
    const [a,b]=g.indices,ends=[0,a,b,points.length-1],codes=flags(state,live),caution=live&&state.overlays?.flags?.session==='caution';
    ctx.lineWidth=9;
    for(let s=0;s<3;s++){ctx.beginPath();for(let i=ends[s];i<=ends[s+1];i++){const [x,y]=project(points[i]);i===ends[s]?ctx.moveTo(x,y):ctx.lineTo(x,y);}if(s===2){const [x,y]=project(points[0]);ctx.lineTo(x,y);}ctx.strokeStyle=caution||codes[s]==='yellow'?T.warning:live?colors[s]:T.textMuted;ctx.stroke();}
    ctx.font='700 12px system-ui';ctx.textAlign='center';ctx.textBaseline='middle';
    [0,a,b].forEach(idx=>{const p=project(points[idx]),before=project(points[Math.max(0,idx-1)]),after=project(points[Math.min(points.length-1,idx+1)]);let dx=after[0]-before[0],dy=after[1]-before[1],n=Math.hypot(dx,dy)||1;ctx.strokeStyle=T.text;ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(p[0]-dy/n*12,p[1]+dx/n*12);ctx.lineTo(p[0]+dy/n*12,p[1]-dx/n*12);ctx.stroke();});
    for(let s=0;s<3;s++){const idx=Math.round((ends[s]+ends[s+1])/2),[x,y]=project(points[idx]);ctx.fillStyle=T.plot;ctx.fillRect(x-15,y+13,30,22);ctx.fillStyle=caution||codes[s]==='yellow'?T.warning:T.textSecondary;ctx.fillText(`S${s+1}`,x,y+24);}
  }
  return {render,draw,flags,time};
})();
