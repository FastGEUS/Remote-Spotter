"use strict";
/* Web presentation adapter. Calculations and histories arrive from the VPS. */
window.SpotterPanels=(()=>{
  const T=SpotterTheme;
  const $=id=>document.getElementById(id), nodes=new Map(), groups=new Map();
  const names={acceleration:"Разгон",battery:"Батарея",brake_bias:"Баланс тормозов",brake_performance:"Эффективность торможения",brake_pressure:"Давление тормозов",brake_temperature:"Температура тормозов",brake_wear:"Износ тормозов",cruise:"Крейсерские показатели",damage:"Повреждения",damage_stats:"Инциденты",deltabest:"Дельта",deltabest_extended:"Дельта: расширенная",differential:"Дифференциал",drs:"DRS",electric_motor:"Электромотор",elevation:"Высота трассы",engine:"Двигатель",engine_temperature:"Температура двигателя",flag:"Флаги",force:"Перегрузки",friction_circle:"Круг сцепления",fuel:"Топливо",fuel_energy_saver:"Экономия топлива и энергии",gear:"Передача",heading:"Курс",instrument:"Приборы",lap_time_history:"История кругов",laps_and_position:"Круги и позиция",lift_and_coast_led:"Lift & Coast",navigation:"Навигация",onboard_setting:"Настройки машины",pace_notes:"Заметки темпа",pedal:"Педали",pit_stop_estimate:"Оценка пит-стопа",push_to_pass:"Push to Pass",radar:"Радар",rake_angle:"Наклон шасси",relative:"Ближайшие машины",relative_finish_order:"Относительный финиш",ride_height:"Дорожный просвет",rivals:"Соперники",roll_angle:"Крен",rpm_led:"Индикатор оборотов",sectors:"Сектора",session:"Сессия",slip_angle:"Угол скольжения",slip_ratio:"Пробуксовка",speedometer:"Скорость",standings:"Классификация",steering_angle:"Угол руля",steering_meter:"Рулевое управление",steering_wheel:"Руль",stint_history:"История стинтов",suspension_force:"Нагрузка подвески",suspension_position:"Положение подвески",suspension_travel:"Ход подвески",system_performance:"Производительность",timing:"Хронометраж",track_clock:"Часы трассы",track_map:"Карта",track_notes:"Заметки трассы",traffic:"Трафик",trailing:"След телеметрии",tyre_carcass:"Каркас шин",tyre_deflection:"Деформация шин",tyre_inner_layer:"Внутренний слой шин",tyre_load:"Нагрузка шин",tyre_pressure:"Давление шин",tyre_temperature:"Температура шин",tyre_wear:"Состояние шин",virtual_energy:"Виртуальная энергия",weather:"Погода",weather_forecast:"Прогноз погоды",weight_distribution:"Распределение веса",wheel_camber:"Развал",wheel_toe:"Схождение"};
  let initialized=false,catalog=[],settings={hidden:[],group:"all",search:"",temp:"C",pressure:"kPa",speed:"kph"};
  try{Object.assign(settings,JSON.parse(localStorage.getItem("spotter.panels.v1")||"{}"));}catch{}
  const save=()=>{try{localStorage.setItem("spotter.panels.v1",JSON.stringify(settings));}catch{}};
  const pretty=s=>s.replace(/([a-z])([A-Z])/g,"$1 $2").replaceAll("_"," ");
  const finite=n=>typeof n==="number"&&Number.isFinite(n);
  function valueText(value,label=""){
    if(value==null)return "—";
    if(typeof value==="boolean")return value?"Да":"Нет";
    if(Array.isArray(value))return value.map((v,i)=>Array.isArray(v)?valueText(v,label):valueText(v,label)).join(" / ");
    if(typeof value==="object")return Object.entries(value).slice(0,6).map(([k,v])=>`${pretty(k)}: ${valueText(v,k)}`).join(" · ");
    if(!finite(value))return String(value);
    let n=value,unit="";
    if(label.includes("Celsius")){if(settings.temp==="F")n=n*1.8+32;unit=` °${settings.temp}`;}
    else if(label.includes("kPa")){if(settings.pressure==="psi")n*=.1450377377;if(settings.pressure==="bar")n/=100;unit=` ${settings.pressure}`;}
    else if(label.includes("Speed")&&label.includes("meters/sec")){n*=settings.speed==="kph"?3.6:settings.speed==="mph"?2.23693629:1;unit=` ${settings.speed==="kph"?"км/ч":settings.speed==="mph"?"mph":"м/с"}`;}
    else if(label.includes("fraction")&&!label.includes("progress")){n*=100;unit="%";}
    else if(label.includes("percent")){unit="%";}
    else if(label.includes("millimeters")){unit=" мм";}
    else if(label.includes("Newtons")){unit=" Н";}
    else if(label.includes("degrees")||label.includes("Degrees")){unit="°";}
    else if(label.includes("seconds")||label.includes("Seconds")){unit=" с";}
    return `${n.toFixed(Math.abs(n)>=100?0:2).replace(/\.00$/," ").trim()}${unit}`;
  }
  function applyFilter(){
    const hidden=new Set(settings.hidden),search=settings.search.toLocaleLowerCase();
    for(const item of catalog){nodes.get(item.id).card.hidden=hidden.has(item.id)||(settings.group!=="all"&&settings.group!==item.group)||!`${item.id} ${names[item.id]} ${item.group}`.toLocaleLowerCase().includes(search);}
    for(const [name,node] of groups)node.section.hidden=![...node.grid.children].some(c=>!c.hidden);
    save();
  }
  function init(list){
    initialized=true;catalog=list;
    for(const item of list){
      if(!groups.has(item.group)){
        const section=document.createElement("section"),h=document.createElement("h2"),grid=document.createElement("div");section.className="overlay-section";grid.className="overlay-grid";h.textContent=item.group;section.append(h,grid);$("overlay-groups").append(section);groups.set(item.group,{section,grid});
        const option=document.createElement("option");option.value=item.group;option.textContent=item.group;$("overlay-group").append(option);
      }
      const card=document.createElement("article");card.className="overlay-card";card.dataset.overlay=item.id;
      const title=document.createElement("h3"),sub=document.createElement("small"),body=document.createElement("div"),state=document.createElement("span"),details=document.createElement("details"),summary=document.createElement("summary"),fields=document.createElement("dl");
      title.textContent=names[item.id]||item.name;sub.textContent=item.id;state.className="panel-status";state.textContent="Ожидание";summary.textContent="Все показатели и источник";
      details.append(summary,fields);const source=document.createElement("small");source.textContent=`TinyPedal v2.50.0 · ${item.source}`;details.append(source);
      body.className="panel-body";card.append(title,sub,state,body,details);groups.get(item.group).grid.append(card);
      const canvas=document.createElement("canvas");canvas.width=400;canvas.height=180;canvas.className="panel-canvas";
      if(["radar","track_map","navigation","friction_circle","steering_wheel","trailing","elevation","rpm_led"].includes(item.id))body.append(canvas);
      const metricBox=document.createElement("div");metricBox.className="panel-values";body.append(metricBox);
      nodes.set(item.id,{card,state,fields,metricBox,canvas,signature:"",rows:new Map()});
      const label=document.createElement("label"),input=document.createElement("input");input.type="checkbox";input.checked=!settings.hidden.includes(item.id);label.append(input,document.createTextNode(names[item.id]||item.name));$("overlay-settings").append(label);
      input.addEventListener("change",()=>{settings.hidden=settings.hidden.filter(k=>k!==item.id);if(!input.checked)settings.hidden.push(item.id);applyFilter();});
    }
    for(const [id,key] of [["overlay-group","group"],["overlay-search","search"],["unit-temp","temp"],["unit-pressure","pressure"],["unit-speed","speed"]]){
      $(id).value=settings[key];$(id).addEventListener(id==="overlay-search"?"input":"change",()=>{settings[key]=$(id).value;for(const node of nodes.values())node.signature="";applyFilter();});
    }
    $("overlay-reset").addEventListener("click",()=>{settings.hidden=[];settings.group="all";settings.search="";$("overlay-group").value="all";$("overlay-search").value="";for(const input of $("overlay-settings").querySelectorAll("input"))input.checked=true;applyFilter();});applyFilter();
  }
  function addLine(parent,label,text){const row=document.createElement("div"),caption=document.createElement("small"),value=document.createElement("strong");caption.textContent=label;value.textContent=text;row.append(caption,value);parent.append(row);}
  function raceTable(parent,cars){
    if(!cars.length){parent.textContent="Ожидание машин";return;}
    const table=document.createElement("table"),head=document.createElement("thead"),tr=document.createElement("tr");
    for(const caption of ["Поз.","Пилот","Интервал","Круг"]){const th=document.createElement("th");th.textContent=caption;tr.append(th);}head.append(tr);table.append(head);
    const body=document.createElement("tbody");for(const c of cars.slice(0,12)){const row=document.createElement("tr");row.className=c.isPlayer?"own":"";for(const val of [c.positionOverall,c.driverName,c.inPit?"PIT":finite(c.relativeGap)?`${c.relativeGap>0?"+":""}${c.relativeGap.toFixed(2)}`:"—",finite(c.lastLapTime)&&c.lastLapTime>0?c.lastLapTime.toFixed(2):"—"]){const td=document.createElement("td");td.textContent=val;row.append(td);}body.append(row);}table.append(body);parent.append(table);
  }
  function graph(canvas,id,s,envelope){
    const ctx=canvas.getContext("2d"),w=canvas.width,h=canvas.height,o=s.overlays,m=o.modules;
    ctx.clearRect(0,0,w,h);ctx.setLineDash([]);ctx.textAlign="left";ctx.textBaseline="alphabetic";ctx.strokeStyle=T.border;ctx.lineWidth=1;ctx.fillStyle=T.textSecondary;ctx.font="12px system-ui";
    if(id==="radar"||id==="navigation"){
      if(id==="navigation"){
        const nav=o.widgetMath.navigation,scale=65/(nav.rangeMeters||80);
        ctx.strokeStyle=T.textMuted;ctx.lineWidth=8;
        for(const points of nav.roadSegments){ctx.beginPath();points.forEach((p,i)=>{const x=w/2+p[0]*scale,y=h/2+p[1]*scale;i?ctx.lineTo(x,y):ctx.moveTo(x,y);});ctx.stroke();}
      }
      ctx.beginPath();ctx.arc(w/2,h/2,65,0,Math.PI*2);ctx.stroke();ctx.fillStyle=T.text;ctx.fillRect(w/2-4,h/2-8,8,16);
      for(const c of o.race.filter(c=>!c.isPlayer&&c.relativeStraightDistance<80)){const {x,y,angle}=SpotterRadar.project(c,w/2,h/2,65/80);ctx.save();ctx.translate(x,y);ctx.rotate(angle);ctx.fillStyle=T.textSecondary;ctx.fillRect(-4,-8,8,16);ctx.restore();ctx.fillText(String(c.positionOverall),x+6,y);}
    }else if(id==="friction_circle"){
      ctx.beginPath();ctx.arc(w/2,h/2,65,0,Math.PI*2);ctx.moveTo(w/2-70,h/2);ctx.lineTo(w/2+70,h/2);ctx.moveTo(w/2,h/2-70);ctx.lineTo(w/2,h/2+70);ctx.stroke();ctx.fillStyle=T.textSecondary;ctx.beginPath();ctx.arc(w/2+m.force.latGForceRaw*22,h/2+m.force.lgtGForceRaw*22,6,0,Math.PI*2);ctx.fill();
    }else if(id==="steering_wheel"){
      const steer=o.values['api.inputs.steering']?.value||0,range=o.values['api.inputs.steering_range_physical']?.value||540;ctx.save();ctx.translate(w/2,h/2);ctx.rotate(steer*range/2*Math.PI/180);ctx.lineWidth=9;ctx.strokeStyle=T.textSecondary;ctx.beginPath();ctx.arc(0,0,55,0,Math.PI*2);ctx.moveTo(-52,0);ctx.lineTo(52,0);ctx.moveTo(0,0);ctx.lineTo(0,52);ctx.stroke();ctx.restore();
    }else if(id==="rpm_led"){
      const ratio=(o.values['api.engine.rpm']?.value||0)/(o.values['api.engine.rpm_max']?.value||1);for(let i=0;i<16;i++){ctx.fillStyle=ratio>i/16?(i>12?T.error:i>10?T.warning:T.textSecondary):T.border;ctx.fillRect(15+i*23,60,17,40);}
    }else if(id==="trailing"){
      const points=o.widgetMath.trailing.samples;if(points.length<2)return;const start=points[0][0],duration=points.at(-1)[0]-start||1;
      for(const [column,color] of [[1,T.throttle],[2,T.brake],[3,T.clutch],[4,T.steering],[5,T.warning],[6,T.warning]]){ctx.strokeStyle=color;ctx.setLineDash(column===3?[6,3]:column===4?[2,3]:column===5?[8,3]:column===6?[2,4]:[]);ctx.lineWidth=2;ctx.beginPath();points.forEach((p,i)=>{const x=15+(p[0]-start)/duration*(w-30),y=h-15-(column===4?(p[column]+1)/2:p[column])*(h-40);i?ctx.lineTo(x,y):ctx.moveTo(x,y);});ctx.stroke();}
      ctx.setLineDash([]);ctx.fillStyle=T.textSecondary;ctx.fillText("Газ · тормоз · сцепление · руль · блокировка · пробуксовка",10,14);
    }else{
      const points=id==="elevation"?(o.trackmap.elevations||[]):s.trackmap.points;
      if(points.length<2){ctx.fillText("Ожидание записи трассы",20,90);return;}
      const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]),minX=Math.min(...xs),minY=Math.min(...ys),spanX=Math.max(...xs)-minX||1,spanY=Math.max(...ys)-minY||1;
      ctx.strokeStyle=T.textSecondary;ctx.lineWidth=3;ctx.beginPath();points.forEach((p,i)=>{const x=20+(p[0]-minX)/spanX*(w-40),y=20+(p[1]-minY)/spanY*(h-40);i?ctx.lineTo(x,y):ctx.moveTo(x,y);});ctx.stroke();
    }
  }
  function render(envelope){
    const s=envelope.state,o=s?.overlays;
    if(!o){$("overlay-notice").textContent=s?.overlayError||"Обновите сборщик пилота для остальных показателей. Панели появятся при получении полного снимка LMU.";return;}
    if(!initialized)init(o.catalog);
    const failures=Object.keys(o.moduleErrors);$("overlay-health").textContent=failures.length?`Ошибка модулей: ${failures.join(", ")}`:`76 панелей · ${12-failures.length}/12 модулей`;
    if(s.mode==='iracing')$('overlay-health').textContent='iRacing SDK · доступность показателей указана на панелях';
    $("overlay-notice").textContent="Расчёт — на VPS. REST-показатели, история и калибровки появляются по мере доступности. Настройки вида сохраняются в этом браузере.";
    if(s.mode==='iracing')$('overlay-notice').textContent='iRacing: отдельный адаптер SDK на VPS. Часть панелей LMU не поддерживается. Шины — снимок из питов; радар заменён индикатором соседства.';
    for(const item of catalog){
      const node=nodes.get(item.id);if(node.card.hidden)continue;
      const capability=o.capabilities[item.id],live=s.status==="live"&&envelope.sourceConnected&&envelope.sourceAgeMs<1000;
      node.state.textContent=!live?"Устарело":capability.status==="live"?"В эфире":"Ожидание данных";node.card.classList.toggle("panel-stale",!live);
      if(s.mode==='iracing')node.state.textContent=!live?'Устарело':({unsupported:'Не поддерживается',partial:'Частично', 'pit-only':'Снимок из питов',live:'В эфире'})[capability.status]||'Ожидание';
      // The main dashboard needs no hidden Canvas plots or source tables.
      // Opening the drawer renders the newest state on the next 100ms tick.
      if(!$("advanced-panels").open)continue;
      if(capability.status==='unsupported'){
        node.metricBox.textContent='Для iRacing этот показатель пока не доступен.';node.fields.replaceChildren();
        if(node.canvas.isConnected)node.canvas.getContext('2d').clearRect(0,0,node.canvas.width,node.canvas.height);continue;
      }
      const inputs=[...item.api.map(k=>o.values['api.'+k]),...item.modules.map(k=>o.values['module.'+k])].filter(Boolean);
      const signature=JSON.stringify(inputs)+(tableViewsFor(item.id)?s.seq:"");
      if(signature===node.signature)continue;node.signature=signature;
      node.metricBox.replaceChildren();node.fields.replaceChildren();
      const tableViews=["relative","standings","rivals","traffic","relative_finish_order"];
      if(tableViews.includes(item.id)){
        let race=[...o.race];
        if(item.id==="rivals"){const ids=[o.widgetMath.rivals.aheadIndex,o.widgetMath.rivals.behindIndex];race=race.filter(c=>ids.includes(c.index)||c.isPlayer);}
        if(item.id==="relative"||item.id==="traffic")race=race.filter(c=>c.isPlayer||finite(c.relativeGap)).sort((a,b)=>Math.abs(a.relativeGap??0)-Math.abs(b.relativeGap??0)).slice(0,9);
        race.sort(item.id==="relative"||item.id==="traffic"?(a,b)=>(b.relativeGap??0)-(a.relativeGap??0):(a,b)=>a.positionOverall-b.positionOverall);
        if(item.id!=="relative_finish_order")raceTable(node.metricBox,race);
        if(item.id==="traffic"){
          for(const [key,label] of [["ahead","Догоним впереди"],["behind","Догонят сзади"],["leader","Лидер догонит"]]){const v=o.widgetMath.traffic,car=o.race.find(c=>c.index===v[`${key}_overtake_index`]),laps=v[`${key}_overtake_laps`];addLine(node.metricBox,label,laps>0?`${car?.driverName||"—"} · ${laps.toFixed(2)} круга`:"Нет устойчивой оценки сближения");}
        }
        if(item.id==="relative_finish_order"){
          addLine(node.metricBox,"Ресурс",o.widgetMath.relative_finish_order.resource==="energy-percent"?"Энергия, %":"Топливо, л");
          for(const scenario of o.widgetMath.relative_finish_order.scenarios)addLine(node.metricBox,`Питы: ${scenario.playerPitSeconds.toFixed(0)} с`,`Финиш: ${valueText(scenario.playerFinishLapFraction)} · Долить: ${valueText(scenario.refillNeeded)}`);
          if(!o.widgetMath.relative_finish_order.scenarios.length)addLine(node.metricBox,"Сценарии","Ожидание темпа и расхода");
        }
      }else if(item.id==="system_performance"){
        addLine(node.metricBox,"Расчёт на VPS",`${envelope.computeMs.toFixed(2)} мс`);addLine(node.metricBox,"Возраст данных на VPS",`${Math.round(envelope.sourceAgeMs)} мс`);
      }else if(item.id==="lap_time_history"){
        const history=o.race.find(c=>c.isPlayer)?.lapTimeHistory||[];addLine(node.metricBox,"Последние круги",history.filter(t=>finite(t)&&t>0&&t<86400).slice(-8).map(t=>t.toFixed(2)).join(" / ")||"Нет полных кругов");
      }else if(item.id==="stint_history"){
        const history=mHistory(o);addLine(node.metricBox,"Завершённых стинтов",String(history.length));for(const stint of history.slice(-3))addLine(node.metricBox,"Стинт",valueText(stint));
      }else{
        if(o.widgetMath[item.id]&&!["traffic","relative_finish_order","rivals","lap_time_history","trailing","navigation"].includes(item.id)){
          const extra=o.widgetMath[item.id];for(const [key,value] of Object.entries(extra))addLine(node.metricBox,pretty(key),valueText(value,key));
        }
        const ordinary=inputs.filter(v=>v.value!==null&&!Array.isArray(v.value?.[0])&&!(Array.isArray(v.value)&&typeof v.value[0]==="object"));
        for(const field of ordinary.slice(0,8))addLine(node.metricBox,field.label,valueText(field.value,field.label));
        if(!ordinary.length)addLine(node.metricBox,"Данные",inputs.some(v=>v.status==="rest-unavailable")?"REST игры недоступен":"Ожидание истории или файла");
      }
      for(const field of inputs){const dt=document.createElement("dt"),dd=document.createElement("dd");dt.textContent=field.label;dd.textContent=field.status==="rest-unavailable"?"Недоступен REST игры":field.status==="not-provided-by-lmu"?"LMU не предоставляет этот показатель":valueText(field.value,field.label);node.fields.append(dt,dd);}
      if(node.canvas.isConnected)graph(node.canvas,item.id,s,envelope);
    }
    renderFinish(o);
    if(s.status!=="live"||!envelope.sourceConnected||envelope.sourceAgeMs>=1000){$("finish-status").textContent="Данные устарели";$("finish-note").textContent="Показана последняя полученная оценка. Ожидание восстановления телеметрии.";}
  }
  function tableViewsFor(id){return ["relative","standings","rivals","traffic","relative_finish_order","lap_time_history","system_performance","acceleration"].includes(id);}
  function mHistory(o){return o.modules.history.stintDataSet||[];}
  function renderFinish(o){
    if(o.source==='iracing'){$('finish-metrics').replaceChildren();$('finish-status').textContent='Не поддерживается';$('finish-note').textContent='Прогноз финиша и пит-стратегия LMU не применяются. Для iRacing доступна базовая оценка топлива.';return;}
    $("finish-metrics").replaceChildren();$("finish-status").textContent=o.finish.status==="estimated"?"Оценка TinyPedal":"Сбор данных";
    for(const [name,value,unit] of [["Топливо до финиша",o.finish.fuel?.neededAbsolute,"л"],["Долить до финиша",o.finish.fuel?.neededRelative,"л"],["Энергия до финиша",o.finish.energy?.neededAbsolute,"%"],["Остановок по топливу",o.finish.pitStopsFuel,""],["Проезд пит-лейна",o.pit.passSeconds,"с"],["Остановка",o.pit.stopSeconds,"с"],["Итого в питах",o.pit.totalSeconds,"с"]])addLine($("finish-metrics"),name,finite(value)?`${value.toFixed(unit?2:0)} ${unit}`:"—");
    $("finish-note").textContent=o.pit.exitTraffic.length?`Трафик после питов: ${o.pit.exitTraffic.map(c=>`${c.driver} (${c.gapAfterStop.toFixed(1)} с)`).join(", ")}. Оценка предполагает сохранение темпа.`:"Для оценки выхода из питов нужны калибровка пит-лейна и время остановки из REST игры.";
  }
  return {render};
})();
