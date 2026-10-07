const {test}=require('node:test');
const assert=require('node:assert/strict');
const {fit,project}=require('../../relay/web/map-layout.js');
const rotate=(p,a)=>[p[0]*Math.cos(a)-p[1]*Math.sin(a),p[0]*Math.sin(a)+p[1]*Math.cos(a)];
test('a tall angled circuit fits a wide window horizontally without clipping or distortion',()=>{
  const points=[[-100,-1000],[100,-1000],[100,1000],[-100,1000]].map(p=>rotate(p,.3));
  const camera=fit(points,800,300);
  const upright=fit(points,800,300,28,false);
  assert.ok(camera.scale>upright.scale*2);
  const pixels=points.map(p=>project(p,camera,800,300));
  for(const [x,y] of pixels){assert.ok(x>=28-1e-6&&x<=772+1e-6);assert.ok(y>=28-1e-6&&y<=272+1e-6);}
  const widths=pixels.map(p=>p[0]),heights=pixels.map(p=>p[1]);
  assert.ok(Math.max(...widths)-Math.min(...widths)>Math.max(...heights)-Math.min(...heights));
  const d=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
  assert.ok(Math.abs(d(pixels[0],pixels[1])/d(points[0],points[1])-camera.scale)<1e-9);
  assert.ok(Math.abs(d(pixels[1],pixels[2])/d(points[1],points[2])-camera.scale)<1e-9);
});
test('fit scales again for full screen and ignores absent geometry safely',()=>{
  const points=[[-1000,-100],[-1000,100],[1000,100],[1000,-100]];
  assert.ok(fit(points,1920,900).scale>fit(points,800,300).scale);
  assert.equal(fit([],800,300),null);
  assert.equal(fit(points,20,20),null);
});

test('a horizontal circuit stays horizontal when tilting would only gain one percent',()=>{
  const points=Array.from({length:161},(_,i)=>{const a=i/160*Math.PI*2;return [650*Math.cos(a)+110*Math.cos(3*a),420*Math.sin(a)];});
  const camera=fit(points,818,314);
  assert.ok(Math.abs(camera.angle)<.01);
  assert.ok(camera.scale>=fit(points,818,314,28,false).scale*.999);
});
