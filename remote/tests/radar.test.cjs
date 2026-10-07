const {test}=require('node:test');
const assert=require('node:assert/strict');
const {project}=require('../../relay/web/radar.js');
// Actual upstream convention, from tinypedal/widget/radar.py draw_vehicle:
// -X left / +X right / -Y ahead / +Y behind, screen rotation = -yaw.
test('radar keeps ahead above and behind below the pilot',()=>{
  const ahead=project({relativeRotatedPositionX:0,relativeRotatedPositionY:-20,relativeOrientationRadians:0},100,100,2);
  const behind=project({relativeRotatedPositionX:0,relativeRotatedPositionY:20,relativeOrientationRadians:0},100,100,2);
  assert.equal(ahead.x,100);assert.equal(ahead.y,60);
  assert.equal(behind.x,100);assert.equal(behind.y,140);
});
test('radar preserves left/right and upstream screen yaw',()=>{
  const left=project({relativeRotatedPositionX:-10,relativeRotatedPositionY:0,relativeOrientationRadians:Math.PI/2},100,100,2);
  const right=project({relativeRotatedPositionX:10,relativeRotatedPositionY:0,relativeOrientationRadians:-Math.PI/2},100,100,2);
  assert.equal(left.x,80);assert.equal(right.x,120);
  assert.equal(left.angle,-Math.PI/2);assert.equal(right.angle,Math.PI/2);
});
