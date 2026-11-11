-- STAGED ONLY: asks for a same-frame native placement check, never moves anything.
-- Horizontal distance alone is intentionally NOT a recovery condition.
local P={};P.__index=P
local function finite(v) return type(v)=='number' and v==v and math.abs(v)<32000 end
local function pos(v) return type(v)=='table' and finite(v.x) and finite(v.y) and finite(v.z) end
local function distance(a,b) return math.sqrt((a.x-b.x)^2+(a.z-b.z)^2) end
function P.new() return setmetatable({time=0,nextTry=0,serial=0},P) end
function P:clearEvidence()
 self.stableAge,self.airAge,self.heightAge,self.stallAge,self.clearAge=0,0,0,0,0
 self.anchor,self.heightY,self.heightSign=nil,nil,nil
 self.blockedAge,self.blockedClearAge,self.blockedBest=0,0,nil
 self.blockedOrigin,self.blockedPlayer=nil,nil
end
function P:resolve(id,placed)
 if not self.pending or id~=self.pending or type(placed)~='boolean' then return false end
 self.pending=nil
 -- A failed geometric check can retry, an unknown outcome stays latched.
 self.nextTry=self.time+(placed and 8 or 2)
 self.latched=placed==true
 self:clearEvidence()
 return true
end
function P:step(dt,s)
 if type(s)~='table' or s.scene==nil then self:clearEvidence();return nil,'invalid-scene' end
 if s.scene~=self.scene then
  self.scene=s.scene;self.frame=nil;self.pending=nil;self.latched=false;self:clearEvidence()
 end
 if not finite(dt) or dt<=0 or dt>.25 or type(s.frame)~='number' or s.frame~=s.frame or s.frame<0 or s.frame>4294967295 or s.frame%1~=0 then
  self:clearEvidence();return nil,'observation-gap-or-duplicate'
 end
 local delta=self.frame and (s.frame-self.frame)%4294967296 or 1
 if delta==0 then return nil,'duplicate-observation' end
 self.frame=s.frame
 if delta>8 then self:clearEvidence();return nil,'observation-discontinuity' end
 -- Only observed time counts. Pause or a missing observation cannot expire cooldowns.
 if s.enabled~=true or s.paused or s.dead or s.manual or not pos(s.skater) or not pos(s.mario) or type(s.grounded)~='boolean' or not finite(s.vy) then
  self:clearEvidence();return nil,'inactive'
 end
 self.time=self.time+dt
 local p,m=s.skater,s.mario
 local dy=m.y-p.y;local gap=distance(p,m)
 if s.marioStable==true then self.stableAge=self.stableAge+dt else self.stableAge=0 end
 if s.grounded==true then self.airAge=0 else self.airAge=self.airAge+dt end
 -- After placement, observe actual ordinary support near Mario's height before rearming.
 if s.grounded==true and math.abs(dy)<120 then self.clearAge=self.clearAge+dt else self.clearAge=0 end
 if self.latched and self.clearAge>=1 then self.latched=false end
 -- Net progress over a bounded window, independent of sampling rate and tiny Y jitter.
 local sign=dy>=0 and 1 or -1
 if math.abs(dy)<260 then
  self.heightAge,self.heightY,self.heightSign=0,nil,nil
 else
  if self.heightY==nil or self.heightSign~=sign then
   self.heightAge,self.heightY,self.heightSign=0,p.y,sign
  end
  self.heightAge=self.heightAge+dt
  if self.heightAge>=1.5 and (p.y-self.heightY)*sign>=48 then
   self.heightAge,self.heightY=0,p.y
  end
 end
 if not self.anchor or distance(p,self.anchor)>=80 then
  self.anchor={x=p.x,y=p.y,z=p.z};self.stallAge=0
 elseif s.wantsMove==true and gap>=420 then self.stallAge=self.stallAge+dt
 else self.stallAge=0 end
 -- Close obstacle jams may have zero steering intent because the ordinary
 -- controller correctly brakes. Side-to-side displacement is not goal progress.
 if s.blocked==true and s.wantsMove==true and gap>=220 then
  self.blockedClearAge=0
  -- Travelling beside a moving player is useful progress even at a constant
  -- separation. A stationary player's side-to-side companion shuffle is not.
  local following=false
  if self.blockedOrigin and self.blockedPlayer then
   local px,pz=p.x-self.blockedOrigin.x,p.z-self.blockedOrigin.z
   local mx,mz=m.x-self.blockedPlayer.x,m.z-self.blockedPlayer.z
   local pp,mm=px*px+pz*pz,mx*mx+mz*mz
   following=pp>=80*80 and mm>=80*80 and px*mx+pz*mz>=.8*math.sqrt(pp*mm)
    and (px-mx)^2+(pz-mz)^2<=64*64
  end
  if not self.blockedBest or gap<=self.blockedBest-64 or following then
   self.blockedBest=gap;self.blockedAge=0
   self.blockedOrigin={x=p.x,z=p.z};self.blockedPlayer={x=m.x,z=m.z}
  else self.blockedAge=(self.blockedAge or 0)+dt end
 else
  self.blockedClearAge=(self.blockedClearAge or 0)+dt
  if self.blockedClearAge>.4 or gap<220 then self.blockedAge,self.blockedBest=0,nil;self.blockedOrigin,self.blockedPlayer=nil,nil end
 end
 if self.pending or self.latched or self.time<self.nextTry then return nil,'one-shot-or-cooldown' end
 if self.stableAge<.35 then return nil,'waiting-for-player-support' end
 -- A normal hop gets time to finish. Never replace a currently rising jump.
 if s.grounded~=true and (self.airAge<1.5 or (finite(s.vy) and s.vy>4)) then return nil,'ordinary-flight-grace' end
 local reason
 if self.heightAge>=1.5 then reason='sustained-height-separation'
 elseif (self.blockedAge or 0)>=2.0 then reason='sustained-close-obstacle-stall'
 elseif self.stallAge>=2.0 then reason='sustained-motion-stall' end
 if not reason then return nil,'ordinary-skating' end
 self.serial=self.serial+1;self.pending=self.serial
 return {id=self.serial,reason=reason,scene=self.scene,frame=self.frame,height=dy,horizontal=gap},reason
end
return P
