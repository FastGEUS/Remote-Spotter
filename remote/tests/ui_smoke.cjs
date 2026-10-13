// Development-only smoke check; requires Playwright + installed Chromium.
const {chromium}=require('playwright');
const {spawn}=require('child_process');
const crypto=require('crypto');
const path=require('path');
const fs=require('fs');
const os=require('os');
const root=path.resolve(__dirname,'../..');
const token=crypto.randomBytes(32).toString('hex');
const viewToken=crypto.randomBytes(32).toString('hex');
const port=18081;
const env={...process.env,SPOTTER_ROOT:root,SPOTTER_PYTHON:process.env.SPOTTER_PYTHON||'python3',SPOTTER_ADDR:`127.0.0.1:${port}`,SPOTTER_PILOT_TOKEN:token,SPOTTER_VIEW_TOKEN:viewToken};
async function main(){
  const server=spawn(process.argv[2],[],{env,stdio:'ignore'});
  let collector,browser,page,qtBrowser,qtDownloads;
  try{
    for(let i=0;i<100;i++){try{if((await fetch(`http://127.0.0.1:${port}/healthz`)).ok)break;}catch{}await new Promise(r=>setTimeout(r,50));}
    // Fixed synthetic game steps keep UI history checks independent of host load.
    // The real collector transport (ACK, ping and retries) still runs unchanged.
    const replay=`import asyncio,itertools
from types import SimpleNamespace
from remote import collector
original=collector.demo_frame
steps=itertools.count()
collector.demo_frame=lambda wall:original(next(steps)*.25)
collector.configure_logging()
asyncio.run(collector.run(SimpleNamespace(url='ws://127.0.0.1:${port}/ws/pilot',demo=True,allow_insecure_local=True,hz=20)))`;
    collector=spawn(env.SPOTTER_PYTHON,['-c',replay],{cwd:root,env,stdio:'ignore'});
    if(process.env.SPOTTER_QT_BROWSER){
      qtDownloads=fs.mkdtempSync(path.join(os.tmpdir(),'spotter-qt-downloads-'));
      qtBrowser=spawn(env.SPOTTER_PYTHON,[path.join(root,'remote/tests/qt_browser_fixture.py'),'18082'],{cwd:root,env:{...env,SPOTTER_QT_DOWNLOAD_DIR:qtDownloads},stdio:'ignore'});
      for(let i=0;i<100;i++){try{if((await fetch('http://127.0.0.1:18082/json/version')).ok)break;}catch{}await new Promise(r=>setTimeout(r,50));}
      browser=await chromium.connectOverCDP('http://127.0.0.1:18082',{noDefaults:true});
      page=browser.contexts()[0].pages()[0];await page.setViewportSize({width:1920,height:1080});
    }else{
      browser=await chromium.launch({headless:true,executablePath:process.env.SPOTTER_CHROMIUM||undefined});
      page=await browser.newPage({viewport:{width:1920,height:1080}});
    }
    const errors=[];page.on('pageerror',e=>{errors.push(e.message);console.error('Browser error:',e.message);});
    await page.goto(`http://127.0.0.1:${port}`);
    await page.locator('#token').fill(viewToken);await page.locator('#login-form button').click();
    await page.waitForFunction(()=>document.querySelector('#mode').textContent.includes('ДЕМО'));
    await page.waitForFunction(()=>document.querySelector('#standings').children.length===6);
    await page.evaluate(()=>{
      const cars=Array.from({length:64},(_,i)=>({id:i,place:i+1}));
      const positions=id=>carsAroundPilot(cars,id).map(c=>c.place);
      for(const [id,expected] of [[0,[1,2,3,4,5,6]],[31,[27,28,29,30,31,32,33,34,35,36,37]],[63,[59,60,61,62,63,64]]]){
        if(JSON.stringify(positions(id))!==JSON.stringify(expected))throw Error('Centred standings boundaries are wrong');
      }
      cars.reverse();if(positions(31)[5]!==32)throw Error('Standings depend on capture array order');
      if(carsAroundPilot(cars,999).length)throw Error('Missing pilot shows unrelated rows');
    });
    await page.waitForFunction(()=>document.querySelector('#speed').textContent==='225');
    await page.waitForFunction(()=>document.querySelector('.condition').textContent==='Остаток 96%');
    await page.waitForFunction(()=>Number.parseFloat(document.querySelector('#energy').textContent)>90);
    await page.waitForFunction(()=>Number.parseFloat(document.querySelector('#stint-minutes').textContent)>0,null,{timeout:45000});
    await page.waitForFunction(()=>document.querySelector('#consumption').title.includes('TinyPedal'));
    await page.waitForFunction(()=>document.querySelectorAll('[data-overlay]').length===76);
    await page.waitForFunction(()=>document.querySelector('#overlay-health').textContent.includes('12/12'));
    await page.waitForFunction(()=>document.querySelector('#sector-history').children.length>=1);
    if(await page.locator('.sector-card').count()!==3)throw Error('Missing sector cards');
    const mapSize=await page.locator('#map').boundingBox();
    if(mapSize.width<650||mapSize.height<300)throw Error('Main map is too small');
    const radarSize=await page.locator('#radar').boundingBox();
    if(radarSize.width<290||radarSize.height<164)throw Error('Radar must occupy the full instrument width');
    await page.evaluate(()=>{
      const sample=structuredClone(latest.state);
      sample.overlays.race=[
        {isPlayer:true},
        {isPlayer:false,relativeRotatedPositionX:2.4,relativeRotatedPositionY:0,relativeOrientationRadians:0,positionOverall:2},
        {isPlayer:false,relativeRotatedPositionX:0,relativeRotatedPositionY:-5.5,relativeOrientationRadians:0,positionOverall:3}
      ];
      const original=CanvasRenderingContext2D.prototype.fillRect;
      let bodies=[];
      CanvasRenderingContext2D.prototype.fillRect=function(x,y,w,h){
        if(this.canvas.id==='radar'){const matrix=this.getTransform();bodies.push({x:matrix.e/matrix.a,y:matrix.f/matrix.d,w,h});}
        return original.call(this,x,y,w,h);
      };
      try{
        for(const range of ['20','40','80']){
          document.querySelector('#radar-range').value=range;bodies=[];SpotterCockpit.render(sample,true);
          if(bodies.length!==3||!bodies.every(b=>b.w===bodies[0].w&&b.h===bodies[0].h))throw Error('Pilot and opponents must have equal footprints');
          const [side,ahead,own]=bodies;
          if(side.x-own.x<=own.w||own.y-ahead.y<=own.h)throw Error('Close cars show a false collision');
        }
      }finally{
        CanvasRenderingContext2D.prototype.fillRect=original;
        document.querySelector('#radar-range').value='40';SpotterCockpit.render(latest.state,isLive(latest));
      }
    });
    if(await page.locator('.sector-indicator').count()!==3)throw Error('Missing separate sector flag board');
    if(!await page.locator('#advanced-panels').evaluate(n=>!n.open))throw Error('Advanced panels should start collapsed');
    if(!await page.locator('#flag-title').innerText())throw Error('Flag display missing');
    const flagBox=await page.locator('.flag-panel').boundingBox();
    if(flagBox.width<300||flagBox.height<120||flagBox.x>=mapSize.x||flagBox.y>mapSize.y)throw Error('Flag screen must occupy the top-left block beside the map');
    await page.evaluate(()=>{
      const panels=[...document.querySelectorAll('.pitwall section')];
      if(panels.some(n=>n.getBoundingClientRect().bottom>innerHeight||n.scrollHeight>n.clientHeight+2))throw Error('Important panels do not fit the desktop screen');
      const table=document.querySelector('.positions .table-wrap');
      if(table.scrollHeight>table.clientHeight+2)throw Error('Centred standings require scrolling');
    });
    // Verify the separate board uses the same calibration as the map, and
    // never displays unverified local channels as a clear/green sector.
    await page.evaluate(()=>{
      const sample=structuredClone(latest);sample.state.mode='lmu';
      sample.state.overlays.flags={session:'green',rawChannels:[1,0,0],pilotBlue:true,sectorFlags:null};
      const select=document.querySelector('#flag-order');select.value='';select.dispatchEvent(new Event('change'));
      SpotterSectors.render(sample,true);
      if(![...document.querySelectorAll('.sector-indicator')].every(n=>n.classList.contains('flag-unknown')))throw Error('Unverified flags shown as clear');
      select.value='201';select.dispatchEvent(new Event('change'));SpotterSectors.render(sample,true);
      const board=[...document.querySelectorAll('.sector-indicator')];
      if(!board[2].classList.contains('flag-yellow')||!board[0].classList.contains('flag-clear'))throw Error('Sector channel permutation is wrong');
      sample.state.overlays.flags.session='caution';SpotterSectors.render(sample,true);
      if(!board.every(n=>n.classList.contains('flag-caution')))throw Error('FCY must warn every sector');
      if(document.querySelector('#flag-screen').dataset.flag!=='caution'||document.querySelector('#flag-pilot-blue').hidden)throw Error('FCY must stay primary while pilot blue remains visible');
      sample.state.overlays.flags.session='stopped';SpotterSectors.render(sample,true);
      if(document.querySelector('#flag-title').textContent!=='СТОП')throw Error('Red flag screen missing');
      SpotterSectors.render(sample,false);
      if(!board.every(n=>n.classList.contains('flag-stale')))throw Error('Stale sector board remains green');
      if(document.querySelector('#flag-screen').dataset.flag!=='stale'||!document.querySelector('#flag-pilot-blue').hidden)throw Error('Stale display retains live flags');
      sample.state.overlays.sectorTiming={...sample.state.overlays.sectorTiming,delta:[-.1,.2,-.3],reference:[30,35,40],comparisonLap:[2,2,1]};
      SpotterSectors.render(sample,true);
      const comparisons=[...document.querySelectorAll('.sector-card small')];
      if(!comparisons[0].textContent.includes('−0.100')||!comparisons[0].textContent.includes('0:30.000')||!comparisons[1].textContent.includes('+0.200')||!comparisons[2].title.includes('Круг 1'))throw Error('Sector comparison sign/reference/S3 context regressed');
      const written=[];
      const fake={beginPath(){},moveTo(){},lineTo(){},stroke(){},fillRect(){},fillText(text){written.push(text);}};
      SpotterSectors.draw(fake,p=>p,latest.state,true);
      if(written.join(',')!=='S1,S2,S3')throw Error('Labels at sector junctions must be removed');
      select.value='';select.dispatchEvent(new Event('change'));SpotterSectors.render(latest,isLive(latest));
      // Full instruments remain usable with an old collector/no overlay data.
      const legacy=structuredClone(latest.state);delete legacy.overlays;SpotterCockpit.render(legacy,true);
      if(document.querySelector('#lap-best').textContent==='1666:39.000')throw Error('Invalid time sentinel displayed');
      SpotterCockpit.render(latest.state,isLive(latest));
    });
    if(qtBrowser){
      await page.locator('#sector-export').click();
      const csv=path.join(qtDownloads,'sector-laps.csv');
      for(let i=0;i<100&&!fs.existsSync(csv);i++)await new Promise(r=>setTimeout(r,50));
      if(!fs.existsSync(csv)||fs.readFileSync(csv,'utf8').split('\n').length<2)throw Error('Missing native Qt CSV export');
    }else{
      const downloadPromise=page.waitForEvent('download');await page.locator('#sector-export').click();
      const download=await downloadPromise;if(download.suggestedFilename()!=='sector-laps.csv')throw Error('Missing CSV export');
    }
    await page.locator('#map-expand').click();
    await page.waitForFunction(()=>document.fullscreenElement?.id==='map-panel'&&document.querySelector('#flag-screen').parentElement.classList.contains('map-wrap'));
    const fullMap=await page.locator('#map').boundingBox();if(fullMap.width<1800||fullMap.height<700)throw Error('Map fullscreen did not grow');
    if(!await page.locator('#flag-screen').evaluate(n=>n.parentElement.classList.contains('map-wrap')))throw Error('Flag screen disappears in fullscreen map');
    await page.screenshot({path:path.join(root,'docs/remote/preview-fullscreen.png'),fullPage:false});
    await page.locator('#map-expand').click();await page.waitForFunction(()=>!document.fullscreenElement&&document.querySelector('#flag-screen').parentElement.classList.contains('flag-panel'));
    if(!await page.locator('#flag-screen').evaluate(n=>n.parentElement.classList.contains('flag-panel')))throw Error('Flag screen did not return to its panel');
    await page.locator('#advanced-panels > summary').click();
    await page.waitForFunction(()=>document.querySelector('[data-overlay="tyre_wear"] .panel-values').textContent.includes('96%'));
    const wear=await page.locator('[data-overlay="tyre_wear"] .panel-values').innerText();
    if(!wear.includes('96%'))throw Error('Tyre condition must be percent');
    const brake=await page.locator('[data-overlay="brake_temperature"] .panel-values').innerText();
    if(!brake.includes('410'))throw Error('Brake Celsius conversion regressed');
    const selector=page.locator('#overlay-group');await selector.selectOption('Шины');
    if(await page.locator('[data-overlay]:visible').count()!==11)throw Error('Tyre group filter failed');
    await selector.selectOption('Гонка и трафик');
    await page.waitForTimeout(1000);
    const dir=path.join(root,'docs/remote');
    await page.locator('#advanced-panels > summary').click();
    await page.evaluate(()=>scrollTo(0,0));
    await page.waitForFunction(()=>document.querySelector('#flag-screen').dataset.flag==='yellow'&&!document.querySelector('#flag-pilot-blue').hidden,null,{timeout:6000});
    await page.screenshot({path:path.join(dir,'preview.png'),fullPage:false});
    await page.setViewportSize({width:1440,height:1080});await page.waitForTimeout(200);
    await page.screenshot({path:path.join(dir,'preview-1440.png'),fullPage:false});
    const tyreOverflow=await page.locator('.tyres-panel').evaluate(n=>n.scrollHeight>n.clientHeight+1);
    if(tyreOverflow)throw Error('Main tyre card overflows its allocated height');
    const radar1440=await page.locator('#radar').boundingBox();
    if(radar1440.width<270||radar1440.height<164)throw Error('Radar shrinks on a 1440px desktop');
    await page.locator('#advanced-panels > summary').click();
    await page.locator('.overlay-controls').scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(dir,'preview-overlays.png'),fullPage:false});
    await page.setViewportSize({width:390,height:844});await page.evaluate(()=>scrollTo(0,0));await page.waitForTimeout(300);
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
    if(overflow)throw Error('mobile horizontal overflow');
    await page.screenshot({path:path.join(dir,'preview-mobile.png'),fullPage:false});
    const before=await page.evaluate(()=>({generation:viewConnection.generation,seq:latest.state.seq}));
    // No close event: the socket stays open but the application sees no packets.
    await page.evaluate(()=>{viewConnection.socket.onmessage=()=>{};});
    await page.waitForFunction(()=>document.querySelector('[data-overlay="relative"]').classList.contains('panel-stale')&&document.querySelector('#finish-status').textContent.includes('устарели'),null,{timeout:3500});
    await page.waitForFunction(g=>viewConnection.generation>g,before.generation,{timeout:12000});
    await page.waitForFunction(seq=>viewConnection.state==='open'&&latest.state.seq>seq,before.seq,{timeout:10000});
    if(!await page.locator('#login').isHidden())throw Error('Recovery unnecessarily asks for a key');
    // A normal explicit disconnect recovers as well.
    const next=await page.evaluate(()=>viewConnection.generation);
    await page.evaluate(()=>viewConnection.socket.close());
    await page.waitForFunction(g=>viewConnection.generation>g&&viewConnection.state==='open',next,{timeout:10000});
    collector.kill();
    await page.waitForFunction(()=>latest?.sourceConnected===false&&document.querySelector('#connection').classList.contains('bad'));
    await page.waitForFunction(()=>document.querySelector('#flag-screen').dataset.flag==='stale');
    await page.waitForFunction(()=>[...document.querySelectorAll('.sector-indicator')].every(n=>n.classList.contains('flag-stale')));
    if(!await page.locator('#dashboard').evaluate(n=>n.classList.contains('dashboard-stale')))throw Error('Main instruments missing stale marker'); 
    if(errors.length)throw Error(errors.join('\n'));
    console.log('UI PASS: login, demo labels, centred standings, all main panels on desktop, fullscreen, CSV, overlays, desktop/mobile, reconnect, no page errors');
  }catch(error){
    if(page)console.error(await page.evaluate(()=>({connection:document.querySelector("#connection")?.textContent,mode:document.querySelector("#mode")?.textContent,loginError:document.querySelector("#login-error")?.textContent,overlayHealth:document.querySelector('#overlay-health')?.textContent,overlayNotice:document.querySelector('#overlay-notice')?.textContent,moduleErrors:typeof latest!=="undefined"?latest?.state?.overlays?.moduleErrors:null,sourceAge:typeof latest!=="undefined"?latest?.sourceAgeMs:null,transport:typeof viewConnection!=="undefined"?viewConnection.state:"not-loaded",seq:typeof latest!=="undefined"?latest?.state?.seq:null,gameTime:typeof latest!=="undefined"?latest?.state?.gameTime:null})).catch(()=>({diagnostic:"page-unavailable"})));
    throw error;
  }finally{
    if(browser)await browser.close();if(qtBrowser)qtBrowser.kill();if(qtDownloads)fs.rmSync(qtDownloads,{recursive:true,force:true});if(collector)collector.kill();server.kill();
  }
}
main().catch(e=>{console.error(e.stack);process.exitCode=1;});
