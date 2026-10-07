/* A separate cockpit-style display; its colour always follows fresh flags. */
(function(root){
  'use strict';
  const titles={green:'ЗЕЛЁНЫЙ',yellow:'ЖЁЛТЫЙ',caution:'FCY / SC',blue:'СИНИЙ',stopped:'СТОП',finished:'ФИНИШ',starting:'СТАРТ',waiting:'ОЖИДАНИЕ',unknown:'НЕТ ФЛАГОВ',stale:'НЕТ ДАННЫХ',black:'ЧЁРНЫЙ',repair:'РЕМОНТ',white:'БЕЛЫЙ'};
  function model(flags,live,codes=['unknown','unknown','unknown']){
    if(!live)return {code:'stale',title:titles.stale,detail:'Флаги недоступны или устарели',blue:false,sectors:['stale','stale','stale']};
    if(!flags)return {code:'unknown',title:titles.unknown,detail:'Ожидание данных о флагах',blue:false,sectors:['unknown','unknown','unknown']};
    let code=Object.hasOwn(titles,flags.session)?flags.session:'unknown';
    if(code==='green'&&(codes.includes('yellow')||flags.rawChannels?.includes(1)))code='yellow';
    const blue=flags.pilotBlue===true;
    if(blue&&['green','waiting'].includes(code))code='blue';
    const sectors=['caution','stopped','finished'].includes(code)?[code,code,code]:codes;
    const yellow=codes.map((c,i)=>c==='yellow'?`S${i+1}`:null).filter(Boolean);
    const detail={black:'Чёрный флаг / дисквалификация пилота',repair:'Механическая неисправность · ремонт',white:'Белый флаг',green:'Трасса под зелёным флагом',blue:'Синий флаг показан пилоту',
      yellow:yellow.length?`Локальный жёлтый · ${yellow.join(' / ')}`:'Локальный жёлтый · сектор не сопоставлен',
      caution:'Нейтрализация всей трассы',stopped:'Сессия остановлена',finished:'Сессия завершена',
      starting:'Стартовая процедура',waiting:'Ожидание начала сессии',unknown:'Статус флагов недоступен'}[code]||'Статус флагов недоступен';
    return {code,title:titles[code],detail,blue,sectors};
  }
  function render(state,live,codes){
    const value=model(state?.overlays?.flags,live,codes),get=id=>document.getElementById(id);
    const text=(node,value)=>{if(node.textContent!==value)node.textContent=value;};
    get('flag-screen').dataset.flag=value.code;
    text(get('flag-title'),value.title);
    text(get('flag-detail'),value.detail);
    text(get('flag-live'),live&&state?.overlays?.flags?'LIVE':'ОЖИДАНИЕ');
    get('flag-pilot-blue').hidden=!value.blue||value.code==='blue';
    text(get('flag-pilot-blue'),'СИНИЙ ФЛАГ ПИЛОТУ');
    value.sectors.forEach((code,i)=>{
      const node=get(`flag-sector-${i+1}`);node.dataset.flag=code;
      text(node.querySelector('strong'),`S${i+1}`);
      text(node.querySelector('span'),code==='unknown'?'?':code==='stale'?'—':code==='yellow'||code==='caution'?'!':code==='stopped'?'СТОП':code==='finished'?'■':'•');
      node.title=code==='unknown'?'Сектор не сопоставлен':code==='stale'?'Данные устарели':code==='clear'?'Нет локального жёлтого':titles[code]||code;
    });
  }
  const api={model,render};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.SpotterFlags=api;
})(typeof globalThis!=='undefined'?globalThis:this);
