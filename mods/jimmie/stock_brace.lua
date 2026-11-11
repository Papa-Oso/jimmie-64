-- Original approved collar on the same 15-node stock skeleton as the body.
-- Host owns spawning/visibility/deletion. Call after body's final pose each tick.
local M={MODEL='jimmie_original_brace_geo',SCALE=.62}
function M.apply(g,brace,body,ticks,owns)
 if type(ticks)~='number' or ticks<=0 then return false,'expired' end
 if not brace or not body or brace==body or type(owns)~='function' or owns(brace,body)~=true then return false,'ownership-required' end
 if type(g.gMarioStates)~='table' then return false,'Mario-state-unavailable' end
 for _,m in pairs(g.gMarioStates) do
  if m and (m.marioObj==brace or m.marioObj==body or m.heldObj==brace or m.heldObj==body or m.riddenObj==brace or m.riddenObj==body) then return false,'protected-object' end
 end
 if brace.activeFlags==0 or body.activeFlags==0 then return false,'deleted-object' end
 local a,b=brace.header.gfx.animInfo,body.header.gfx.animInfo
 if not b.curAnim then return false,'body-animation-unavailable' end
 a.curAnim=b.curAnim;a.animFrame=b.animFrame;a.animFrameAccelAssist=b.animFrameAccelAssist;a.animAccel=b.animAccel
 a.animYTrans=b.animYTrans;a.animTimer=b.animTimer
 a.animID=b.animID;a.prevAnimID=b.prevAnimID;a.prevAnimPtr=b.prevAnimPtr
 a.prevAnimFrame=b.prevAnimFrame;a.prevAnimFrameTimestamp=b.prevAnimFrameTimestamp
 brace.oPosX,brace.oPosY,brace.oPosZ=body.oPosX,body.oPosY,body.oPosZ
 brace.oFaceAnglePitch,brace.oFaceAngleYaw,brace.oFaceAngleRoll=body.oFaceAnglePitch,body.oFaceAngleYaw,body.oFaceAngleRoll
 brace.oGraphYOffset=body.oGraphYOffset;brace.oInteractType=0;brace.oCollisionDistance=0
 local p,r=body.header.gfx.pos,body.header.gfx.angle
 g.obj_set_gfx_pos(brace,p.x,p.y,p.z);g.obj_set_gfx_angle(brace,r.x,r.y,r.z)
 g.obj_scale(brace,M.SCALE)
 return true
end
return M
