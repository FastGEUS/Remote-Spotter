const test=require('node:test');const assert=require('node:assert/strict');
const {describe}=require('../../relay/web/status.js');
const fresh={sourceConnected:true,sourceAgeMs:50,ingestAgeMs:20,state:{status:'live'}};
test('normal garage and waiting are not network failures',()=>{
 for(const status of ['garage','waitingForGame','paused']){
  const label=describe({...fresh,state:{status}},true);
  assert.doesNotMatch(label.text,/устарели|прервана/);
 }
 assert.equal(describe({...fresh,state:{status:'garage'}},true).good,true);
});
test('aged packets and delayed computation cannot remain live',()=>{
 assert.equal(describe(fresh,true,1200).good,false);
 assert.match(describe({...fresh,sourceAgeMs:2000},true).text,/Расчёт на VPS/);
 assert.equal(describe(fresh,false).good,false);
 assert.match(describe({...fresh,sourceConnected:false},true).text,/Пилот отключён/);
});
test('first calculation and empty channel have distinct states',()=>{
 assert.match(describe({...fresh,state:null},true).text,/первого расчёта/);
 assert.match(describe({sourceConnected:false,state:null},true).text,/Ожидание подключения/);
});
