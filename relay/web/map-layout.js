/* A rigid map rotation: the same projection is used for track, cars and flags. */
(function(root){
  'use strict';
  function rotatedBounds(points,angle){
    const c=Math.cos(angle),s=Math.sin(angle);
    let minX=Infinity,maxX=-Infinity,minZ=Infinity,maxZ=-Infinity;
    for(const [x,z] of points){
      const a=x*c-z*s,b=x*s+z*c;
      minX=Math.min(minX,a);maxX=Math.max(maxX,a);minZ=Math.min(minZ,b);maxZ=Math.max(maxZ,b);
    }
    return {minX,maxX,minZ,maxZ};
  }
  function fit(points,width,height,padding=28,rotate=true){
    points=points.filter(p=>Array.isArray(p)&&Number.isFinite(p[0])&&Number.isFinite(p[1]));
    if(!points.length||width<=2*padding||height<=2*padding)return null;
    let best=null;const candidates=[];
    function consider(angle){
      const b=rotatedBounds(points,angle),dx=Math.max(1,b.maxX-b.minX),dz=Math.max(1,b.maxZ-b.minZ);
      const scale=Math.min((width-2*padding)/dx,(height-2*padding)/dz);
      candidates.push({x:(b.minX+b.maxX)/2,z:(b.minZ+b.maxZ)/2,angle,scale});
      if(!best||scale>best.scale+1e-9||Math.abs(scale-best.scale)<1e-9&&Math.abs(angle)<Math.abs(best.angle)){
        best={x:(b.minX+b.maxX)/2,z:(b.minZ+b.maxZ)/2,angle,scale};
      }
    }
    consider(0);
    if(rotate&&points.length>2){
      // Maximise uniform scale in this window, rather than stretching the track.
      for(let degree=-90;degree<=90;degree+=2)consider(degree*Math.PI/180);
      const coarse=best.angle;
      for(let step=-20;step<=20;step++)consider(coarse+step*.1*Math.PI/180);
      // Prefer the long axis along the window when fits differ by under 2%.
      // This avoids a needless diagonal tilt for a nearly horizontal circuit.
      const mx=points.reduce((sum,p)=>sum+p[0],0)/points.length,mz=points.reduce((sum,p)=>sum+p[1],0)/points.length;
      let xx=0,zz=0,xz=0;
      for(const [x,z] of points){xx+=(x-mx)**2;zz+=(z-mz)**2;xz+=(x-mx)*(z-mz);}
      const axis=.5*Math.atan2(2*xz,xx-zz),desired=width>=height?0:Math.PI/2;
      consider(desired-axis);
      const near=candidates.filter(candidate=>candidate.scale>=best.scale*.98);
      near.sort((a,b)=>Math.abs(Math.sin(a.angle+axis-desired))-Math.abs(Math.sin(b.angle+axis-desired))||b.scale-a.scale);
      best=near[0];
    }
    return best;
  }
  function project(point,camera,width,height){
    const c=Math.cos(camera.angle),s=Math.sin(camera.angle),[x,z]=point;
    return [(x*c-z*s-camera.x)*camera.scale+width/2,(x*s+z*c-camera.z)*camera.scale+height/2];
  }
  const api={fit,project};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.SpotterMap=api;
})(typeof globalThis!=='undefined'?globalThis:this);
