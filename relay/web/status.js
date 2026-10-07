"use strict";
(function(root){
  function describe(e,open,elapsed=0){
    if(!open)return {text:'Восстановление связи с сервером',good:false};
    if(!e?.sourceConnected)return {text:e?.state?'Пилот отключён · показан последний снимок':'Ожидание подключения пилота',good:false};
    if(!e.state)return {text:'Пилот подключён · ожидание первого расчёта',good:false};
    const sourceAge=e.sourceAgeMs+Math.max(0,elapsed),ingestAge=e.ingestAgeMs+Math.max(0,elapsed);
    if(e.sourceAgeMs<0||sourceAge>=1000){
      return {text:e.ingestAgeMs>=0&&ingestAge<1000?'Расчёт на VPS задерживается · данные устарели':'Нет свежих данных от пилота',good:false};
    }
    const text={waitingForGame:`Сервер подключён · ожидание ${e.state.mode==='iracing'?'iRacing':'LMU'}`,garage:'Подключено · пилот в гараже',paused:'Подключено · пауза / повтор / нет обновлений игры',live:'В эфире'}[e.state.status];
    return {text:text||'Ожидание телеметрии',good:e.state.status==='live'||e.state.status==='garage'};
  }
  if(typeof module!=='undefined'&&module.exports)module.exports={describe};else root.SpotterStatus={describe};
})(typeof window!=='undefined'?window:globalThis);
