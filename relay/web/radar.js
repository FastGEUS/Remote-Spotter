"use strict";
/* TinyPedal radar coordinates: -X left, +X right, -Y ahead, +Y behind.
 * Canvas Y already increases downwards: do not invert it a second time.
 * Vehicle yaw uses the opposite screen rotation (upstream radar.py). */
(function(root){
  function project(car,cx,cy,scale){
    return {x:cx+car.relativeRotatedPositionX*scale,
      y:cy+car.relativeRotatedPositionY*scale,
      angle:-car.relativeOrientationRadians};
  }
  // Schematic footprint shared by every car; metres use the same scale as
  // positions. Fixed pixel icons would overlap cars driving side by side.
  function body(scale){return {width:2*scale,length:5*scale};}
  function drawCar(ctx,x,y,angle,scale,color){
    const {width,length}=body(scale);
    ctx.save();ctx.translate(x,y);ctx.rotate(Number.isFinite(angle)?angle:0);
    ctx.fillStyle=color;ctx.fillRect(-width/2,-length/2,width,length);ctx.restore();
  }
  const api={project,body,drawCar};
  if(typeof module!=="undefined"&&module.exports)module.exports=api;
  else root.SpotterRadar=api;
})(typeof window!=="undefined"?window:globalThis);
