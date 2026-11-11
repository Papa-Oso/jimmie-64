-- Isolated cosmetic crash controller. No hooks, globals, object or Mario writes.
-- Momentum split and explicit reset are general lessons from GodotSkate/SK8;
-- this implementation, tuning and animation are independently written.
local M = { HZ=30, BRACE_TICKS=90, MAX_TICKS=132, MAX_BOARD_RETURN=180, VERSION=2 }
local function finite(x) return type(x)=='number' and x==x and x~=math.huge and x~=-math.huge end
local function clamp(x,a,b) return math.max(a,math.min(b,x)) end
local function copy(p) return {x=p.x,y=p.y,z=p.z} end
local function vec(p) return type(p)=='table' and finite(p.x) and finite(p.y) and finite(p.z) end
local function length(x,z) return math.sqrt(x*x+z*z) end
local function unit(x,z) local n=length(x,z); if n<.001 then return 1,0 end; return x/n,z/n end
local function phase_frame(s)
 if s.landed then return math.min(44,12+s.groundTicks) end
 return math.min(11,s.ticks)
end
local function surface(world,x,y,z)
 local ok,f=pcall(world.floor,x,y,z)
 if not ok then return nil,'probe-error' end
 if f==nil then return nil end
 if type(f)~='table' or not finite(f.y) or not finite(f.ny) or f.ny<.999999 or f.safe~=true or f.dynamic==true then return nil,'unsafe-floor' end
 return f
end
local function board_extent(s,b)
 -- Exact AABB vertical support for the authored deck bounding box under ZXY.
 local a=s.board.pitch; local r=s.board.roll
 local sx,cx=math.sin(a),math.cos(a); local sz,cz=math.sin(r),math.cos(r)
 return math.abs(sz*cx)*b[1]+math.abs(cz*cx)*b[2]+math.abs(sx)*b[3]
end
function M.new(data,world)
 assert(type(data)=='table' and data.variants and data.board_half,'crash envelope data required')
 assert(type(world)=='table' and type(world.floor)=='function' and type(world.wall)=='function','floor and wall adapters required')
 local s={active=false,braceTicks=0,sequence=nil,scene=nil,reason='idle'}
 function s:reset(reason)
  self.active=false; self.reason=reason or 'reset'; self.body=nil; self.board=nil;self.recovering=false;self.ready=false
  self.ticks=0; self.groundTicks=0; self.landed=false; self.recover=nil
  self.braceTicks=0; self.sequence=nil; self.scene=nil; self.previousFrame=nil
 end
 function s:begin(e)
  if type(e)~='table' or e.kind~='companion_crash' or e.source=='mario' then return false,'real companion crash required' end
  if self.active then return false,'crash already active' end
  if not vec(e.pos) or not vec(e.velocity) or not finite(e.yaw) or not finite(e.frame) or e.frame%1~=0 or type(e.scene)~='string' or e.scene=='' or not finite(e.sequence) or e.sequence%1~=0 then return false,'invalid snapshot' end
  if e.heading~=nil and e.heading~=0 and e.heading~=1 then return false,'invalid riding heading' end
  self.heading=e.heading or 0
  if self.scene==e.scene and self.sequence~=nil and e.sequence<=self.sequence then return false,'duplicate or stale crash' end
  if length(e.velocity.x,e.velocity.z)>5000 or math.abs(e.velocity.y)>5000 then return false,'velocity outside contract' end
  local n=length(e.velocity.x,e.velocity.z);local dx,dz=unit(e.velocity.x,e.velocity.z)
  if n<1 then dx,dz=math.cos(e.yaw),-math.sin(e.yaw) end
  local speed=clamp(n,80,650);local variant=1+(e.sequence%3)
  self.body={x=e.pos.x,y=e.pos.y,z=e.pos.z,vx=dx*speed*.72,vy=clamp(e.velocity.y*.2+180,60,300),vz=dz*speed*.72,yaw=e.yaw}
  -- Board releases away from the authored anatomical fall direction.
  local lx,lz=0,1;if variant==2 then lx,lz=-1,0 elseif variant==3 then lx,lz=0,-1 end
  local ax,az=math.cos(e.yaw)*lx+math.sin(e.yaw)*lz,-math.sin(e.yaw)*lx+math.cos(e.yaw)*lz
  self.board={x=e.pos.x,y=e.pos.y+data.board_half[2]+1,z=e.pos.z,vx=dx*speed*.55+ax*180,vy=230,vz=dz*speed*.55+az*180,yaw=e.yaw+self.heading*math.pi,pitch=0,roll=0,spin=12+(variant-1)*2,bounces=0}
  self.recovering=false;self.ready=false;self.drawFrame=0;self.active=true;self.reason='crash';self.ticks=0;self.groundTicks=0;self.landed=false
  self.variant=variant;self.scene=e.scene;self.sequence=e.sequence;self.previousFrame=e.frame
  self.braceTicks=M.BRACE_TICKS;self.recover=nil;self.hitCount=0;self.origin=copy(e.pos)
  return true
 end
 function s:snapshot()
  return {active=self.active,reason=self.reason,phase=self.recovering and 'getup' or self.landed and 'flop' or 'release',ready=self.ready,frame=self.drawFrame or 0,
   variant=self.variant,heading=self.heading,body=self.body and {x=self.body.x,y=self.body.y,z=self.body.z,yaw=self.body.yaw},
   board=self.board and {x=self.board.x,y=self.board.y,z=self.board.z,yaw=self.board.yaw,pitch=self.board.pitch,roll=self.board.roll},
   braceTicks=self.braceTicks,ticks=self.ticks,hitCount=self.hitCount,recover=self.recover}
 end
 local function stop(reason)
  s.active=false;s.reason=reason;s.recover={kind='host_recovery_required',reason=reason,position=s.body and copy(s.body),scene=s.scene}
 end
 local function move(part,radius,envelope)
  local old=copy(part);local dt=1/M.HZ
  part.vy=math.max(-1000,part.vy-1100*dt)
  -- Six microsteps bound travel for the capped crash impulses.
  for sub=1,6 do
   local target={x=part.x+part.vx*dt/6,y=part.y+part.vy*dt/6,z=part.z+part.vz*dt/6}
   local ok,hit=pcall(world.wall,{x=part.x,y=part.y,z=part.z},target,radius,envelope)
   if not ok or type(hit)~='table' or not vec(hit.pos) then return false,'wall-probe-error' end
   if length(hit.pos.x-target.x,hit.pos.z-target.z)>radius*2+1 or math.abs(hit.pos.y-target.y)>1 then return false,'invalid-wall-correction' end
   part.x,part.y,part.z=hit.pos.x,hit.pos.y,hit.pos.z
   if hit.blocked then
    if finite(hit.nx) and finite(hit.nz) then
     local nx,nz=unit(hit.nx,hit.nz);local vn=part.vx*nx+part.vz*nz
     if vn<0 then part.vx=part.vx-1.18*vn*nx;part.vz=part.vz-1.18*vn*nz end
    else part.vx=0;part.vz=0 end
   end
  end
  if length(part.x-s.origin.x,part.z-s.origin.z)>1100 or math.abs(part.y-s.origin.y)>1600 then return false,'bounded-recovery' end
  return true,old
 end
 local function start_getup()
  if not data.recoveries or not data.recoveries[s.variant] then return false,'no-getup' end
  if length(s.board.x-s.body.x,s.board.z-s.body.z)>M.MAX_BOARD_RETURN then return false,'board-too-far' end
  local f,err=surface(world,s.body.x,s.body.y+120,s.body.z)
  local b,err2=surface(world,s.board.x,s.board.y+120,s.board.z)
  if err or err2 or not f or not b or math.abs(f.y-b.y)>.001 then return false,'getup-support-unavailable' end
  s.recovering=true;s.getupFrame=0;s.drawFrame=0;s.getupFloor=f.y;s.getupRootLift=s.body.y-f.y
  s.boardStart={x=s.board.x,y=s.board.y,z=s.board.z,yaw=s.board.yaw,pitch=s.board.pitch,roll=s.board.roll}
  s.body.vx,s.body.vy,s.body.vz=0,0,0;s.board.vx,s.board.vy,s.board.vz=0,0,0
  return true
 end
 local function getup_step()
  local frames=#data.recoveries[s.variant].bounds
  s.getupFrame=math.min(frames-1,s.getupFrame+1);s.drawFrame=s.getupFrame
  local t=s.getupFrame/(frames-1)
  -- Settle the deck before the supported push transfers weight onto it.
  -- Translation remains a deliberate cartoon scoot, proved by the same wall/floor guards.
  local q=clamp((s.getupFrame-8)/19,0,1);q=q*q*(3-2*q)
  local flat=clamp((s.getupFrame-4)/13,0,1);flat=flat*flat*(3-2*flat)
  local b=data.recoveries[s.variant].bounds[s.getupFrame+1]
  local old=copy(s.body);local target={x=s.body.x,y=s.getupFloor+s.getupRootLift*(1-t),z=s.body.z}
  local ok,hit=pcall(world.wall,old,target,b.radius,{minY=b.minY,maxY=b.maxY})
  if not ok or not hit or not vec(hit.pos) then stop('getup-body-proof');return end
  s.body.x,s.body.y,s.body.z=hit.pos.x,hit.pos.y,hit.pos.z
  local offset=data.board_idle;local c,z=math.cos(s.body.yaw),math.sin(s.body.yaw)
  local tx=s.body.x+c*offset[1]+z*offset[3];local tz=s.body.z-z*offset[1]+c*offset[3]
  local function shortest(a,targetAngle) return (targetAngle-a+math.pi)%(2*math.pi)-math.pi end
  s.board.pitch=s.boardStart.pitch+shortest(s.boardStart.pitch,0)*flat
  s.board.roll=s.boardStart.roll+shortest(s.boardStart.roll,0)*flat
  s.board.yaw=s.boardStart.yaw+shortest(s.boardStart.yaw,s.body.yaw+(s.heading or 0)*math.pi)*q
  local h=board_extent(s,data.board_half)
  local targetBoard={x=s.boardStart.x+(tx-s.boardStart.x)*q,y=s.getupFloor+h+2*(1-q),z=s.boardStart.z+(tz-s.boardStart.z)*q}
  ok,hit=pcall(world.wall,copy(s.board),targetBoard,math.sqrt(data.board_half[1]^2+data.board_half[2]^2+data.board_half[3]^2),{minY=-h,maxY=h})
  if not ok or not hit or not vec(hit.pos) then stop('getup-board-proof');return end
  s.board.x,s.board.y,s.board.z=hit.pos.x,hit.pos.y,hit.pos.z
  if s.getupFrame==frames-1 then s.ready=true end
 end
 function s:step(e)
  if type(e)~='table' or type(e.scene)~='string' or not finite(e.frame) or e.frame%1~=0 then return false,'invalid update' end
  if self.scene and e.scene~=self.scene then self:reset('scene-change');return self:snapshot() end
  if e.enabled==false or e.ownerAlive==false then self:reset('owner-removed');return self:snapshot() end
  if e.paused then self.previousFrame=e.frame; return self:snapshot() end
  if self.previousFrame and e.frame<=self.previousFrame then return self:snapshot() end
  -- One update per gameplay tick, not catch-up debt. Large clock gaps abort.
  if self.previousFrame and e.frame-self.previousFrame>4 then self:reset('stale-clock');return self:snapshot() end
  self.previousFrame=e.frame
  if self.braceTicks>0 then self.braceTicks=self.braceTicks-1 end
  if not self.active then return self:snapshot() end
  self.ticks=self.ticks+1
  if e.cancel then stop('cancelled');return self:snapshot() end
  if self.ticks>=M.MAX_TICKS then stop('time-budget');return self:snapshot() end
  if self.recovering then if not self.ready then getup_step() end;return self:snapshot() end
  local frame=phase_frame(self);self.drawFrame=frame;local bounds=data.variants[self.variant].bounds[frame+1]
  local ok,old=move(self.body,bounds.radius,{minY=bounds.minY,maxY=bounds.maxY})
  if not ok then stop(old);return self:snapshot() end
  local floor,err=surface(world,self.body.x,math.max(old.y,self.body.y)+120,self.body.z)
  if err then stop(err);return self:snapshot() end
  if floor then
   local bottom=self.body.y+bounds.minY
   if bottom<=floor.y+2 and self.body.vy<=0 and old.y+bounds.minY>=floor.y-80 then
    self.body.y=floor.y-bounds.minY+2
    if not self.landed then self.landed=true;self.groundTicks=0;self.hitCount=self.hitCount+1 end
    if self.body.vy< -100 and self.hitCount<3 then self.body.vy=-self.body.vy*.16;self.hitCount=self.hitCount+1 else self.body.vy=0 end
    self.body.vx=self.body.vx*.76;self.body.vz=self.body.vz*.76
   else self.body.vx=self.body.vx*.994;self.body.vz=self.body.vz*.994 end
  end
  if self.landed then self.groundTicks=self.groundTicks+1 end
  ok,old=move(self.board,math.sqrt(data.board_half[1]^2+data.board_half[3]^2),{minY=-80,maxY=80})
  if not ok then stop(old);return self:snapshot() end
  self.board.pitch=self.board.pitch+self.board.spin/M.HZ;self.board.roll=self.board.roll+self.board.spin*.37/M.HZ
  self.board.yaw=self.board.yaw+.8/M.HZ
  local extent=board_extent(self,data.board_half)
  floor,err=surface(world,self.board.x,math.max(old.y,self.board.y)+100,self.board.z)
  if err then stop(err);return self:snapshot() end
  if floor and self.board.y-extent<=floor.y+2 and self.board.vy<=0 then
   self.board.y=floor.y+extent+2
   if self.board.vy< -80 and self.board.bounces<3 then self.board.vy=-self.board.vy*.30;self.board.bounces=self.board.bounces+1 else self.board.vy=0 end
   self.board.vx=self.board.vx*.82;self.board.vz=self.board.vz*.82;self.board.spin=self.board.spin*.68
   if self.board.spin<4 then
    self.board.spin=0
    local function flatten(a) local target=math.floor(a/math.pi+.5)*math.pi;return target+(a-target)*.60 end
    self.board.pitch=flatten(self.board.pitch);self.board.roll=flatten(self.board.roll)
    self.board.y=floor.y+board_extent(self,data.board_half)+2
   end
  end
  if self.ticks>=45 and self.groundTicks>=30 and length(self.body.vx,self.body.vz)<40 then
   local ready,why=start_getup();if not ready then stop(why or 'settled') end
  end
  return self:snapshot()
 end
 return s
end
return M
