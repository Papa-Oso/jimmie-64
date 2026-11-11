-- Original motion state machine. Owns animation only, never PHYS or Mario.
local M={}
local families={'trick','kickflip','heelflip','bs_pop_shuvit','fs_pop_shuvit'}
local function valid(x) return type(x)=='number' and x==x and math.abs(x)<1e8 end
function M.new(bank)
 local s={bank=bank,serial=0}
 function s:reset()
  self.body=nil;self.board=nil;self.clip=nil;self.time=0;self.heading=0;self.air=nil;self.landing=nil;self.push=nil;self.balance=nil;self.exit=nil;self.previousPush=0
  self.dying=nil;self.external=nil;self.previousAir=nil;self.output=nil;self.journey=nil
  self.bank:reset()
 end
 s:reset()
 function s:step(c)
  local dt=valid(c.dt) and math.max(0,math.min(c.dt,1/15)) or 1/30
  if not c.body or not c.board or c.body==c.board then self:reset();return false,'missing pair' end
  if self.body~=c.body or self.board~=c.board or self.scene~=c.scene then self:reset();self.body=c.body;self.board=c.board;self.scene=c.scene end
  if c.externalOwner then self.journey=nil;self.bank:reset();self.external=true;return false,'external owner' end
  if self.external then self:reset();self.body=c.body;self.board=c.board;self.scene=c.scene;self.external=nil end
  if c.paused then return true,'paused' end
  local clip,phase,heading='idle',nil,self.heading
  local completed
  if c.dying then
   if not self.dying then self:reset();self.body=c.body;self.board=c.board;self.scene=c.scene;self.heading=heading;self.dying=true end
   clip='bail';phase=math.min(1,(self.time or 0)/math.max(dt,c.bailDuration or .9))
   if c.getup then phase=math.max(0,1-c.getup) end
  elseif c.debugClip and self.bank.clips[c.debugClip] then
   self.journey=nil
   clip=c.debugClip;phase=(self.time or 0)/self.bank.clips[clip].duration
  elseif c.railContact and c.balanceClip and self.bank.clips[c.balanceClip] then
   -- One actual contacted grind journey, not one lottery per balance frame.
   if not self.journey then self.serial=self.serial+1;self.journey={id=self.serial,kind='grind',clip=c.balanceClip} end
   self.journey.kind='grind';self.journey.grind=c.balanceClip
   -- Actual rail contact must be visible even when the grind is only 4 ticks.
   -- Do not consume those ticks with the normal six-frame landing blend.
   if self.air then
    self.heading=(self.air.heading+(self.bank.clips[self.air.clip].turn or 0))%2
   end
   self.air=nil;self.landing=nil;self.push=nil;self.exit=nil;self.dying=nil
   if self.balance~=c.balanceClip then self.balance=c.balanceClip;self.balanceTime=0 end
   clip=self.balance;heading=self.heading;phase=self.balanceTime/self.bank.clips[clip].duration
   self.balanceTime=self.balanceTime+dt
  elseif c.windup and not c.inAir and self.bank.clips.windup then
   -- Ground crouch before a trick jump. A landing cut short still reports its trick.
   if self.landing then completed=self.journey;self.journey=nil end
   self.push=nil;self.landing=nil;self.balance=nil;self.exit=nil;self.dying=nil;self.air=nil
   if not self.winding or c.windup<(self.lastWind or 0) then
    -- Decide now whether this jump is a nollie, a boneless or a no-comply: each has its own crouch.
    self.winding=true
    local want=c.requestedTrick and self.bank.clips[c.requestedTrick]
    local r=math.random()
    if want then self.style=want.style
    elseif self.bank.styles and not c.noSpin then self.style=r<.08 and 'nollie' or r<.13 and 'boneless' or r<.18 and 'nocomply' or nil
    else self.style=nil end
   end
   self.lastWind=c.windup
   clip=self.style and self.bank.clips['windup_'..self.style] and ('windup_'..self.style) or 'windup';phase=c.windup
  elseif c.inAir then
   self.dying=nil;self.push=nil;self.landing=nil;self.balance=nil;self.exit=nil
   if not self.air or (c.airTime or 0)<(self.previousAir or 0) then
    self.serial=self.serial+1
    local duration=math.max(dt,c.flightDuration or .7)
    local chosen=c.requestedTrick
    if not chosen and self.bank.tricks then
     -- Weighted pick from the bank's named tricks: never the same one twice running, and long tricks need the air time.
     local total,pool=0,{}
     for _,n in ipairs(self.bank.tricks) do
      local q=self.bank.clips[n]
      if q and n~=self.lastTrick and duration>=(q.minAir or .4) and not (q.spin and c.noSpin) and q.style==self.style then total=total+(q.weight or 1);pool[#pool+1]=n end
     end
     local roll=math.random()*total
     for _,n in ipairs(pool) do roll=roll-(self.bank.clips[n].weight or 1);if roll<=0 then chosen=n;break end end
     chosen=chosen or pool[#pool]
    end
    chosen=chosen or families[(self.serial-1)%#families+1]
    if not self.bank.clips[chosen] or duration<.4 then chosen='trick' end
    self.lastTrick=chosen;self.winding=nil;self.style=nil
    -- After a ground wind-up, start the clip at its pop instead of crouching again in the air.
    self.air={clip=chosen,t=0,duration=duration,heading=self.heading,from=c.popped and (self.bank.clips[chosen].pop or 0) or 0}
    if not self.journey or self.journey.kind~='grind' then
     self.journey=c.trickTakeoff==true and {id=self.serial,kind='trick',clip=chosen} or nil
    else self.journey.out=chosen end
   end
   local a=self.air;clip=a.clip;heading=a.heading
   -- Protect a visible catch section; physics and landing detection stay external.
   local caught=self.bank.clips[clip].catch or .84
   local before=math.max(dt,a.duration-4/30)
   phase=a.t<before and a.from+(caught-a.from)*a.t/before or caught+(1-caught)*(a.t-before)/math.max(dt,a.duration-before)
   phase=math.min(1,phase)
   if c.doomed then phase=a.from+(phase-a.from)*.7 end
   a.phase=phase;a.t=a.t+dt
  else
   self.dying=nil
   if self.air then
    local a=self.air;local q=self.bank.clips[a.clip]
    self.heading=(a.heading+(q.turn or 0))%2
    self.landing={clip=q.landing or 'land',t=0,heading=a.heading,early=(a.phase or 0)<(q.catch or .84)}
    self.air=nil
    if self.journey then completed=self.journey;completed.early=self.landing.early;self.journey=nil end
   end
   heading=self.heading
   if c.manualClip and self.bank.clips[c.manualClip] then
    -- Manual: tip onto two wheels straight from the landing and hold it; the trick has already been judged at touchdown.
    if self.manual~=c.manualClip then self.manual=c.manualClip;self.manualTime=0 end
    self.landing=nil;self.push=nil
    clip=self.manual;phase=math.min(1,self.manualTime/self.bank.clips[clip].duration);self.manualTime=self.manualTime+dt
   elseif self.manual then
    -- Set the other wheels back down: the entry run backwards, twice as fast.
    clip=self.manual;self.manualTime=math.min(self.manualTime,self.bank.clips[clip].duration)-dt*2
    phase=math.max(0,self.manualTime/self.bank.clips[clip].duration)
    if self.manualTime<=0 then self.manual=nil end
   elseif self.landing then
    local l=self.landing;clip=l.clip;heading=l.heading;phase=l.t/self.bank.clips[clip].duration;l.t=l.t+dt
    if phase>=1 then completed=self.journey;self.journey=nil;self.landing=nil end
   elseif c.balanceClip and self.bank.clips[c.balanceClip] then
    if self.balance~=c.balanceClip then self.balance=c.balanceClip;self.balanceTime=0 end
    clip=self.balance;phase=self.balanceTime/self.bank.clips[clip].duration;self.balanceTime=self.balanceTime+dt;self.push=nil;self.exit=nil
   elseif self.balance or self.exit then
    if self.balance then self.exit={clip=self.balance,t=0,from=math.min(1,self.balanceTime/self.bank.clips[self.balance].duration)};self.balance=nil end
    clip=self.exit.clip;phase=self.exit.from*(1-self.exit.t/.16);self.exit.t=self.exit.t+dt
    if phase<=0 then phase=0;self.exit=nil;if self.journey and self.journey.kind=='grind' then completed=self.journey;self.journey=nil end end
   else
    if self.push and self.push>=.4 then self.push=nil end
    if c.pushing and (not self.push or (c.pushTime or 0)<self.previousPush) then self.push=0 end
    if self.push then clip='push';phase=self.push/.4;self.push=self.push+dt
    elseif (tonumber(c.speed) or 0)>4 and self.bank.clips.pose then clip='pose' end
   end
  end
  if self.clip~=clip then self.clip=clip;self.time=0 end
  if phase==nil then phase=self.time/self.bank.clips[clip].duration end
  local q=self.bank.clips[clip]
  if q.loop then phase=phase%1 else phase=math.max(0,math.min(1,phase)) end
  local ok,frame=self.bank:apply(c.body,c.board,clip,phase,heading)
  self.time=self.time+dt;self.previousPush=c.pushTime or 0;self.previousAir=c.airTime or 0
  if completed and ok then completed.source='motion_controller';completed.scene=tostring(c.scene);completed.eligible=true end
  self.output={clip=clip,phase=phase,heading=heading,frame=frame,earlyLanding=self.landing and self.landing.early or false,journey=self.journey and self.journey.kind or nil,completedTrick=ok and completed or nil}
  return ok,self.output
 end
 return s
end
return M
