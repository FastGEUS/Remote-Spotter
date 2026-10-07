"use strict";
(function(root){
  class Connection {
    constructor(options={}){
      this.options=options;this.generation=0;this.socket=null;this.retry=null;this.guard=null;
      this.failures=0;this.state='idle';this.lastPacket=0;
      this.fetch=options.fetch||root.fetch.bind(root);this.WebSocket=options.WebSocket||root.WebSocket;
      this.clock=options.clock||(()=>performance.now());this.setTimer=options.setTimer||((fn,delay)=>setTimeout(fn,delay));this.clearTimer=options.clearTimer||(id=>clearTimeout(id));
      this.origin=options.origin||location.origin;
    }
    status(state,text){this.state=state;this.options.onStatus?.(state,text);}
    stop(){++this.generation;this.clearTimer(this.retry);this.clearTimer(this.guard);this.retry=this.guard=null;const old=this.socket;this.socket=null;if(old)old.close();}
    async start(){
      this.stop();const generation=this.generation;
      this.status('connecting','Подключаю страницу споттера…');
      let auth;
      const abort=new AbortController();const timer=this.setTimer(()=>abort.abort(),5000);
      try{auth=await this.fetch(`${this.origin}/api/session`,{method:'GET',cache:'no-store',signal:abort.signal});}
      catch{if(generation===this.generation)this.schedule('Нет связи с сервером');return;}
      finally{this.clearTimer(timer);}
      if(generation!==this.generation)return;
      if(auth.status===401){this.status('auth','Сессия входа истекла · введите ключ споттера');this.options.onAuth?.();return;}
      if(!auth.ok){this.schedule('Сервер временно недоступен');return;}
      const ws=new this.WebSocket(`${this.origin.replace(/^http/,'ws')}/ws/view`);this.socket=ws;
      const alive=()=>generation===this.generation&&this.socket===ws;
      this.guard=this.setTimer(()=>{if(alive())this.schedule('Соединение не открылось');},8000);
      ws.onopen=()=>{if(!alive())return;this.clearTimer(this.guard);this.lastPacket=this.clock();this.status('open','Ожидание данных пилота');this.options.onOpen?.();this.watch(generation,ws);};
      ws.onmessage=e=>{if(!alive())return;let data;try{data=JSON.parse(e.data);}catch{this.schedule('Повреждённый пакет сервера');return;}
        this.lastPacket=this.clock();this.failures=0;this.options.onData?.(data);};
      ws.onclose=()=>{if(alive())this.schedule('Связь прервана');};
      ws.onerror=()=>{if(alive())this.schedule('Ошибка соединения');};
    }
    watch(generation,ws){
      this.guard=this.setTimer(()=>{if(generation!==this.generation||ws!==this.socket)return;
        if(this.clock()-this.lastPacket>=8000)this.schedule('Сервер перестал присылать пакеты');else this.watch(generation,ws);
      },1000);
    }
    schedule(reason){
      this.stop();const delay=Math.min(1000*2**this.failures,10000);this.failures=Math.min(this.failures+1,4);
      this.status('retry',`${reason} · повтор через ${delay/1000} с`);
      this.retry=this.setTimer(()=>this.start(),delay);
    }
  }
  if(typeof module!=='undefined'&&module.exports)module.exports={Connection};
  else root.SpotterConnection={Connection};
})(typeof window!=='undefined'?window:globalThis);
