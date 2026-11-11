-- Explicit renderer adapter. Loading does not install hooks or spawn anything.
-- Call bind only for two owned cosmetic objects while the normal renderer yields.
local M={}
local fields={'oPosX','oPosY','oPosZ','oFaceAnglePitch','oFaceAngleYaw','oFaceAngleRoll','oVelX','oVelY','oVelZ','oForwardVel','oInteractType','oCollisionDistance','oGraphYOffset'}
local function finite(x) return type(x)=='number' and x==x and math.abs(x)<math.huge end
local function angle(rad) return (math.floor(rad*32768/math.pi+0.5)+32768)%65536-32768 end
local function protected(o)
 if type(gMarioStates)~='table' then return true end
 for _,m in pairs(gMarioStates) do if m and (m.marioObj==o or m.heldObj==o or m.riddenObj==o) then return true end end
 return false
end
function M.new(data)
 local r={body=nil,board=nil,saved=nil}
 function r:bind(body,board)
  if self.saved then return false,'already bound' end
  if not body or not board or body==board or protected(body) or protected(board) then return false,'owned non-Mario body and board required' end
  for _,o in ipairs({body,board}) do if not o.header or not o.header.gfx or not o.header.gfx.animInfo then return false,'animation info missing' end end
  self.body,self.board=body,board;self.saved={}
  for _,o in ipairs({body,board}) do
   local v={};for _,f in ipairs(fields) do v[f]=o[f] end
   local a=o.header.gfx.animInfo;v.curAnim=a.curAnim;v.animFrame=a.animFrame;v.animFrameAccelAssist=a.animFrameAccelAssist;v.animAccel=a.animAccel
   self.saved[o]=v
  end
  return true
 end
 function r:apply(s)
  if not self.saved or protected(self.body) or protected(self.board) then return false,'renderer ownership unavailable' end
  local clips=type(s)=='table' and s.phase=='getup' and data.recoveries or data.variants
  if type(s)~='table' or not s.active or not clips[s.variant] or not finite(s.frame) or s.frame%1~=0 or s.frame<0 or s.frame>=#clips[s.variant].bounds then return false,'invalid crash pose' end
  for _,p in ipairs({s.body,s.board}) do
   if type(p)~='table' or not finite(p.x) or not finite(p.y) or not finite(p.z) or not finite(p.yaw) then return false,'invalid transform' end
  end
  if not finite(s.board.pitch) or not finite(s.board.roll) then return false,'invalid board angle' end
  local function draw(o,p,clip,frame,board)
   smlua_anim_util_set_animation(o,clip)
   local a=o.header.gfx.animInfo;a.animFrame=frame;a.animFrameAccelAssist=frame*65536;a.animAccel=65536
   local yaw=angle(p.yaw);local pitch=board and angle(p.pitch) or 0;local roll=board and angle(p.roll) or 0
   o.oPosX,o.oPosY,o.oPosZ=p.x,p.y,p.z;o.oFaceAnglePitch,o.oFaceAngleYaw,o.oFaceAngleRoll=pitch,yaw,roll
   o.oVelX,o.oVelY,o.oVelZ,o.oForwardVel=0,0,0,0;o.oInteractType,o.oCollisionDistance,o.oGraphYOffset=0,0,0
   obj_set_gfx_pos(o,p.x,p.y,p.z);obj_set_gfx_angle(o,pitch,yaw,roll)
  end
  draw(self.body,s.body,clips[s.variant].name,s.frame,false)
  draw(self.board,s.board,data.board_name,0,true)
  return true
 end
 function r:forget() self.body,self.board,self.saved=nil,nil,nil end
 function r:release()
  if not self.saved then return true end
  -- Restore every temporary override. Host must then reset its animation owner
  -- and choose the already approved companion recovery; no Mario/PHYS is touched.
  for _,o in ipairs({self.body,self.board}) do
   if protected(o) then return false,'object became protected; no writes' end
  end
  for _,o in ipairs({self.body,self.board}) do
   local v=self.saved[o];for _,f in ipairs(fields) do o[f]=v[f] end
   local a=o.header.gfx.animInfo;a.curAnim=v.curAnim;a.animFrame=v.animFrame;a.animFrameAccelAssist=v.animFrameAccelAssist;a.animAccel=v.animAccel
   obj_set_gfx_pos(o,v.oPosX,v.oPosY,v.oPosZ);obj_set_gfx_angle(o,v.oFaceAnglePitch,v.oFaceAngleYaw,v.oFaceAngleRoll)
   obj_skip_interpolation(o)
  end
  self.body,self.board,self.saved=nil,nil,nil
  return true
 end
 return r
end
return M
