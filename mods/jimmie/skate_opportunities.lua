-- General arcade opportunities layered over the accepted ground-skating integrator.
-- No engine writes, hooks, assets, scene-pointer strings or arbitrary model choices.
local O={}; O.__index=O
local function finite(n) return type(n)=='number' and n==n and math.abs(n)<1e8 end
local function point(p) return p and finite(p.x) and finite(p.y) and finite(p.z) end
local function dist(a,b) return math.sqrt((a.x-b.x)^2+(a.z-b.z)^2) end
local function cp(p) return {x=p.x,y=p.y,z=p.z} end
local function clamp(n,a,b) return math.max(a,math.min(b,n)) end
-- Arcade rail dynamics use native 30 Hz ticks: distance/tick and distance/tick^2.
-- Contact momentum belongs to Jimmie, not Mario. Gravity acts along the signed
-- 3D tangent. Passive sliding still dissipates energy; moving alongside Mario
-- can add bounded arcade pace assistance, never a position correction.
local RAIL_GRAVITY,RAIL_FRICTION,RAIL_DRAG,RAIL_MAX_SPEED=2.5,.04,.001,48
-- motion:railhop. Frames a planned hop crouches on the ground before it leaves.
O.WINDUP=5
local function railShape(rail)
 local x,y,z=rail.b.x-rail.a.x,rail.b.y-rail.a.y,rail.b.z-rail.a.z
 local length=math.sqrt(x*x+y*y+z*z)
 if length<1 then return nil end
 return length,x/length,y/length,z/length
end
function O.railDynamics(speed,grade,pace)
 speed=clamp(speed,0,RAIL_MAX_SPEED);grade=clamp(grade,-1,1)
 local acceleration=-RAIL_GRAVITY*grade-RAIL_FRICTION*math.sqrt(1-grade*grade)-RAIL_DRAG*speed
 local nextSpeed=clamp(speed+acceleration,0,RAIL_MAX_SPEED)
 if finite(pace) and pace>nextSpeed then
  nextSpeed=math.min(RAIL_MAX_SPEED,pace,nextSpeed+2.4)
  acceleration=nextSpeed-speed
 end
 local distance=(speed+nextSpeed)*.5
 if nextSpeed==0 and acceleration<0 then distance=math.min(distance,speed*speed/(-2*acceleration)) end
 return nextSpeed,distance,acceleration
end
-- Only assist a nearby player moving along this rail, and taper the target
-- with the actual longitudinal gap. Passing Mario or turning away removes
-- assistance immediately; ordinary momentum remains, rather than snapping.
function O.railPace(rail,p,m)
 if not point(p) or not point(m) then return nil end
 local vx,vz=m.vx or 0,m.vz or 0
 if not finite(vx) or not finite(vz) then return nil end
 local length,tx,grade,tz=railShape(rail)
 if not length then return nil end
 local horizontal=math.sqrt(tx*tx+tz*tz)
 if horizontal<.5 then return nil end
 local dx,dz=tx/horizontal,tz/horizontal
 local speed=math.sqrt(vx*vx+vz*vz);local forward=vx*dx+vz*dz
 if speed<4 or speed>48 or forward<speed*.7 then return nil end
 local x,z=m.x-p.x,m.z-p.z
 local along=x*dx+z*dz;local lateral=math.abs(x*dz-z*dx)
 if along<0 or lateral>280 or dist(p,m)>800 or math.abs(m.y-p.y)>220 then return nil end
 return clamp((forward+clamp((along-80)/20,-8,8))/horizontal,0,RAIL_MAX_SPEED)
end
-- motion:railspeed. Speed along the rail at contact: most of the approach speed carries over,
-- as long as he was already heading the rail's way.
local function entrySpeed(vx,vy,vz,x,y,z)
 local along=(vx or 0)*x+(vy or 0)*y+(vz or 0)*z
 if along>0 then along=math.max(along,.85*math.sqrt((vx or 0)^2+(vz or 0)^2)) end
 return clamp(along,0,RAIL_MAX_SPEED)
end
local function startGrind(t,vx,vy,vz)
 local length,x,y,z=railShape(t.rail)
 if not length then return false end
 t.grindLength=length;t.grindGrade=y;t.grindDistance=0;t.grindTicks=0
 t.grindSpeed=entrySpeed(vx,vy,vz,x,y,z)
 t.phase='grind';t.step=0;t.contactPending=true
 return true
end
function O.new(world, rng)
 return setmetatable({world=world,rng=rng or math.random,nextProbe=0,nextFun=0,nextFollow=0,lastVariant=0,events={},episode=0,scanEpoch=0},O)
end
function O:event(kind,ctx,extra)
 local e={kind=kind,frame=ctx.frame,time=ctx.time,episode=self.episode}
 if extra then for k,v in pairs(extra) do e[k]=v end end
 self.events[#self.events+1]=e;self.lastEvent=e
end
function O:drain() local e=self.events;self.events={};return e end
function O:cancel(reason,ctx)
 -- A cooperative timeout cancels all movement authority, but numeric geometry
 -- may be retried with a full fresh proof. Do not lose a safe entry window just
 -- because one frame's native calls exhausted the unchanged shared budget.
 local retry
 if reason=='native-time-budget' or reason=='native-query-budget' then
  retry=self.pendingRail
  if not retry and self.task and self.task.rail then
   retry={rail=self.task.rail,time=self.task.started,scene=self.task.scene,area=self.task.area}
  end
 end
 if retry then
  retry.budgetFailures=(retry.budgetFailures or 0)+1
  if retry.budgetFailures>=3 then
   if self.world.deferRail then self.world:deferRail(retry.rail,ctx and ctx.frame or 0,300) end
   self:event('rail-candidate-deferred',ctx or {frame=0,time=0},{reason='repeated-native-budget',budgetReason=reason,budgetCalls=self.world.lastBudget and self.world.lastBudget.calls,budgetElapsed=self.world.lastBudget and self.world.lastBudget.elapsed,indexKey=retry.rail.indexKey})
   retry=nil
  end
 end
 if self.task then self:event('cancelled',ctx or {frame=0,time=0},{reason=reason}) end
 self.task=nil; self.cue=nil; self.previous=nil; self.pendingLanding=nil;self.pendingRail=nil;self.followSearch=nil
 self.scanEpoch=(self.scanEpoch or 0)+1;self.scanContext=nil;self.nextProbe=0;self.nextFun=0
 self.pendingRail=retry
 if reason~='native-time-budget' and reason~='native-query-budget' and self.world.resetRailHints then
  self.world:resetRailHints()
 elseif self.world.invalidateRails then self.world:invalidateRails() end
end
function O:chooseVariant(kind)
 local n=self.rng(); if not finite(n) then n=.5 end
 local weight=kind=='follow' and .28 or .48
 if self.lastVariant==1 then weight=weight*.45 end
 self.lastVariant=n<weight and 1 or 0
 return self.lastVariant
end
function O:chooseBalance(ctx,visual)
 local r=self.rng();if not finite(r) then r=.5 end
 if visual then
  -- On a visible rail only poses whose contact point lies on the rail line may be used: the 50-50 and the named grinds.
  local total,pool=0,{}
  for _,g in ipairs(JIMMIE_GRINDS or {}) do if g.clip~=self.lastBalance then total=total+g.weight;pool[#pool+1]=g end end
  local pick=r*total
  for _,g in ipairs(pool) do pick=pick-g.weight;if pick<=0 then self.lastBalance=g.clip;return g.clip end end
  self.lastBalance=pool[1] and pool[#pool].clip or 'balance042';return self.lastBalance
 end
 local speed=math.sqrt((ctx.player.vx or 0)^2+(ctx.player.vz or 0)^2)
 local key=r<(speed>=24 and .45 or .65) and 'balance038' or r<.85 and 'balance039' or 'balance042'
 if key==self.lastBalance then key=key=='balance038' and 'balance039' or 'balance038' end
 self.lastBalance=key;return key
end
function O:observe(ctx)
 local m,prev=ctx.player,self.previous
 local same=prev and prev.frame+1==ctx.frame and prev.scene==ctx.scene and prev.instance==ctx.playerInstance
 if same and prev.grounded and ctx.playerRising and m.y>prev.y+1 and m.y-prev.y<100
  and dist(prev,m)<150 then
  self.cue={takeoff=cp(prev),untilTime=ctx.time+3,scene=ctx.scene}
  self:event('player-jump-observed',ctx)
 end
 if self.cue then
  if self.cue.scene~=ctx.scene or ctx.time>self.cue.untilTime then self.cue=nil
  elseif ctx.playerGrounded then self.cue.landing=cp(m) end
 end
 self.previous={x=m.x,y=m.y,z=m.z,frame=ctx.frame,scene=ctx.scene,
  instance=ctx.playerInstance,grounded=ctx.playerGrounded}
end
function O:playersClear(a,b,ctx)
 for _,m in ipairs(ctx.players or {ctx.player}) do
  if not self.world:segment(a,b,m) then return false end
 end
 return true
end
function O:begin(plan,kind,p,ctx,rail)
 if not plan or not finite(plan.duration) or plan.duration<1 or plan.duration>60 then return nil end
 -- motion:keepup. While Mario is moving fast, a crossing hop travels at his pace instead of a fixed slow one and
 -- the crouch before it is 2 frames instead of 5. The path is the one already proved; only its timing changes.
 local quick=false
 if kind=='follow' and not plan.contactEntry and ctx.player then
  local sp=math.sqrt((ctx.player.vx or 0)^2+(ctx.player.vz or 0)^2)
  if sp>=16 then quick=true;plan.duration=math.max(9,math.min(plan.duration,math.ceil(dist(plan.a,plan.b)/math.max(22,sp)))) end
 end
 if self.world.invalidateRails then self.world:invalidateRails() end
 self.episode=self.episode+1
 self.task={plan=plan,kind=kind,balanceClip=rail and self:chooseBalance(ctx,rail.visual) or nil,phase='air',frame=ctx.frame,scene=ctx.scene,instance=ctx.instance,
  phys=ctx.phys,area=ctx.area,step=0,expected=cp(p),variant=self:chooseVariant(kind),rail=rail,
  terrain=ctx.terrain,started=ctx.time,approachOrigin=cp(p),windup=plan.contactEntry and 0 or (quick and 2 or O.WINDUP)}
 if plan.contactEntry then
  if not startGrind(self.task,p.vx,p.vy,p.vz) then self.task=nil;return nil end
 end
 self.nextFollow=ctx.time+1.25
 -- Navigation does not consume optional fun. Keep the RNG draw for parity.
 local nextFun=ctx.time+9+self.rng()*7
 if kind=='rail' then self.nextFun=nextFun end
 self.cue=nil;self.pendingRail=nil
 self:event('selected',ctx,{opportunity=kind,variant=self.task.variant,from=cp(p),to=cp(plan.landing or plan.b),finiteProbes=true})
 return self:advance(p,ctx)
end
-- One freshly checked dismount candidate per update after a stall. Nearby
-- side landings are tested in native geometry, never assumed from the rail tag.
function O:dismount(t,p,ctx)
 local floor=self.world:floor(p.x,p.y+16,p.z)
 if not floor or math.abs(floor.y-p.y)>12 or not self:playersClear(p,p,ctx) then
  self:cancel('rail-stall-support-lost',ctx);return nil
 end
 t.exitTry=(t.exitTry or 0)+1
 local target
 local first,second=t.rail.exit,t.approachOrigin
 if t.dismountReason=='companion-range' and second and dist(second,ctx.player)<dist(first,ctx.player) then first,second=second,first end
 if t.exitTry==1 then target=first
 elseif t.exitTry==2 then target=second
 else
  local offsets={{96,0},{-96,0},{144,48},{-144,48},{192,0},{-192,0}}
  local offset=offsets[t.exitTry-2]
  if offset then
   local dx,dz=t.rail.b.x-t.rail.a.x,t.rail.b.z-t.rail.a.z
   local length=math.max(1,math.sqrt(dx*dx+dz*dz));dx,dz=dx/length,dz/length
   target=self.world:floor(p.x-dz*offset[1]+dx*offset[2],p.y+180,p.z+dx*offset[1]+dz*offset[2])
  end
 end
 local plan=target and self.world:arc(p,target,80)
 if plan then
  t.plan=plan;t.phase='exit';t.step=0
  self:event('rail-exit',ctx,{reason=t.dismountReason or 'momentum-stall',speed=t.grindSpeed})
  return true
 end
 if t.exitTry>=8 then
  -- No certified landing: stop grinding on the observed support and hand back
  -- to normal follow/recovery. Never fabricate a hop through a blocked exit.
  self:event('rail-stall-handback',ctx,{reason='no-clear-dismount'})
  self.task=nil
  return {position=cp(p),velocity={x=0,y=0,z=0},onGround=true,kind='rail',grind=false,
   phase='released',episode=self.episode,variant=t.variant,duration=0,airTime=0}
 end
 local presentation
 if t.rail.visual then
  presentation=self.world.raisedPresentation and self.world:raisedPresentation(p,p,t.rail,ctx)
  if not presentation then self:cancel('raised-dismount-clearance-refused',ctx);return nil end
 end
 return {position=cp(p),velocity={x=0,y=0,z=0},onGround=false,kind='rail',grind=true,
  phase='dismount',episode=self.episode,variant=t.variant,balanceClip=t.balanceClip,raisedPresentation=presentation,
  incline=presentation and presentation.incline or math.asin(t.grindGrade),duration=0,airTime=0}
end
function O:advance(p,ctx)
 local t=self.task
 if not t then return nil end
 if ctx.scene~=t.scene or ctx.instance~=t.instance or ctx.phys~=t.phys or ctx.area~=t.area or ctx.terrain~=t.terrain
  or (ctx.frame~=t.frame and ctx.frame~=t.frame+1) or ctx.time-t.started>(t.rail and 5 or 4)
  or dist(p,t.expected)>4 or math.abs(p.y-t.expected.y)>4 then
  self:cancel('interrupted-or-displaced',ctx);return nil
 end
 -- Optional fun must yield if Mario outruns it. Cancel only this controller's
 -- ownership; normal follow/collision/recovery resumes from the observed state,
 -- never from an invented landing or teleport. Prefer a checked dismount first.
 if t.rail then
  local gap=dist(p,ctx.player)
  if gap>1000 then self:cancel('player-outpaced-rail',ctx);return nil end
  if gap>800 and t.phase=='grind' then
   t.phase='dismount';t.exitTry=0;t.dismountReason='companion-range'
   self:event('rail-dismount-requested',ctx,{reason='companion-range',gap=gap})
  end
 end
 if ctx.frame==t.frame and t.step>0 then return nil end
 t.frame=ctx.frame
 if t.phase=='landed' then
  if p.onGround and self.world:support(p,28) then
   self:event('landing-observed',ctx,{opportunity=t.kind})
  else self:event('landing-unconfirmed',ctx,{opportunity=t.kind}) end
  self.task=nil;return nil
 end
 if t.phase=='dismount' then
  local result=self:dismount(t,p,ctx)
  if result~=true then return result end
 end
 if t.phase=='grind' then
  local f=self.world:floor(p.x,p.y+16,p.z)
  if not f or math.abs(f.y-p.y)>12 then self:cancel('rail-support-lost',ctx);return nil end
  if t.contactPending then self:event('rail-contact-observed',ctx);t.contactPending=nil end
 end
 if t.phase=='air' and t.step==0 and (t.windup or 0)>0 then
  -- Crouch where he stands. The jump was already proved from this exact spot, so nothing moves.
  if not self:playersClear(p,p,ctx) then self:cancel('fresh-clearance-refused',ctx);return nil end
  if t.windup==O.WINDUP then self:event('windup',ctx,{opportunity=t.kind}) end
  t.windup=t.windup-1;t.popped=true
  local to=t.plan.landing or t.plan.b
  return {position=cp(p),velocity={x=0,y=0,z=0},onGround=true,variant=t.variant,kind=t.kind,grind=false,phase='windup',
   windup=(O.WINDUP-1-t.windup)/math.max(1,O.WINDUP-1)*.99,heading=to and dist(p,to)>1 and math.atan2(to.x-p.x,to.z-p.z) or nil,
   episode=self.episode,duration=t.plan.duration/30,airTime=0}
 end
 t.step=t.step+1
 local total=t.phase=='grind' and 60 or t.plan.duration
 local k=clamp(t.step/total,0,1)
 local q
 if t.phase=='grind' then
  local speed,travel=O.railDynamics(t.grindSpeed,t.grindGrade,O.railPace(t.rail,p,ctx.player))
  t.grindSpeed=speed;t.grindDistance=math.min(t.grindLength,t.grindDistance+travel);t.grindTicks=t.grindTicks+1
  k=t.grindDistance/t.grindLength
  if k<1 and (speed<=.01 or t.grindTicks>=60) then
   t.phase='dismount';t.exitTry=0;t.dismountReason='momentum-stall'
   self:event('rail-stalled',ctx,{speed=speed,progress=k,grade=t.grindGrade})
   local result=self:dismount(t,p,ctx)
   if result~=true then return result end
   t.step=1;total=t.plan.duration;k=1/total;q=self.world:at(t.plan,k)
  else
   q={x=t.rail.a.x+(t.rail.b.x-t.rail.a.x)*k,y=t.rail.a.y+(t.rail.b.y-t.rail.a.y)*k,z=t.rail.a.z+(t.rail.b.z-t.rail.a.z)*k}
  end
 else q=self.world:at(t.plan,k) end
 if not point(q) or not self:playersClear(p,q,ctx) then
  self:cancel('fresh-clearance-refused',ctx);return nil
 end
 local grounded=false;local grind=t.phase=='grind';local presentation
 if grind then
  local f=self.world:floor(q.x,q.y+16,q.z)
  if not f or math.abs(f.y-q.y)>12 then self:cancel('rail-support-lost',ctx);return nil end
  if t.rail.visual then
   presentation=self.world.raisedPresentation and self.world:raisedPresentation(p,q,t.rail,ctx)
   if not presentation then self:cancel('raised-presentation-clearance-refused',ctx);return nil end
  end
 end
 if k>=1 then
  if t.rail and t.phase=='air' then
   local h=self.world:floor(q.x,q.y+16,q.z)
   if not h or math.abs(h.y-q.y)>12 then self:cancel('rail-contact-missing',ctx);return nil end
   if not startGrind(t,q.x-p.x,q.y-p.y,q.z-p.z) then self:cancel('invalid-rail',ctx);return nil end
   self:event('rail-contact-proposed',ctx,{from=cp(t.rail.a),to=cp(t.rail.b)})
  elseif t.phase=='grind' then
   local plan=self.world:arc(q,t.rail.exit,80)
   if not plan then self:cancel('exit-changed',ctx);return nil end
   t.plan=plan;t.phase='exit';t.step=0;self:event('rail-exit',ctx)
  else
   local h=self.world:support(q,28)
   if not h then self:cancel('landing-support-missing',ctx);return nil end
   q.y=h.y or q.y;grounded=true;t.phase='landed';self:event('landing-proposed',ctx)
  end
 end
 local vx,vy,vz=q.x-p.x,q.y-p.y,q.z-p.z
 t.expected=cp(q)
 return {position=q,velocity={x=vx,y=grounded and 0 or vy,z=vz},onGround=grounded,
  variant=t.variant,balanceClip=t.balanceClip,kind=t.kind,grind=grind,phase=t.phase,episode=self.episode,
  raisedPresentation=presentation,popped=t.popped,
  heading=t.rail and (t.phase=='air' or t.phase=='grind') and math.atan2(t.rail.b.x-t.rail.a.x,t.rail.b.z-t.rail.a.z) or nil,
  incline=presentation and presentation.incline or (grind and math.atan((t.rail.b.y-t.rail.a.y)/math.max(1,dist(t.rail.a,t.rail.b))) or 0),
  duration=t.plan.duration/30,airTime=math.min(t.step,total)/30}
end
function O:follow(p,ctx)
 local m=ctx.player;local length=dist(p,m)
 if ctx.time<self.nextFollow or length<160 or length>1600 then self.followReason='follow-range-or-cooldown';return nil end
 local cue=self.cue
 local dx,dz=(m.x-p.x)/length,(m.z-p.z)/length
 local barrier=self.world.barrier and self.world:barrier(p,m)
 local near=not self.world.barrier and self.world:floor(p.x+dx*85,p.y+220,p.z+dz*85) or nil
 local obstacle=barrier~=nil or (not self.world.barrier and (not near or near.y>p.y+32 or near.y<p.y-55))
 local heightChange=math.abs(m.y-p.y)>45 and ctx.playerGrounded
 if not obstacle and not heightChange and not (cue and dist(p,cue.takeoff)<320) then
  self.followSearch=nil;self.followReason='no-follow-crossing';return nil
 end
 local search=self.followSearch
 if not search or dist(p,search.origin)>64 or dist(m,search.player)>160 or ctx.time-search.time>1.5 then
  search={origin=cp(p),player=cp(m),time=ctx.time,index=0};self.followSearch=search
 end
 local maxDistance=math.min(560,math.max(90,length-155))
 -- Nearby intermediate support is preferred over a single distant landing.
 -- At most one expensive arc proof per update; a refusal continues next frame.
 local distances={math.min(maxDistance,180),math.min(maxDistance,320),maxDistance}
 local sides={0,110,-110}
 for _=1,9 do
  search.index=search.index%9+1
  local radial=distances[math.floor((search.index-1)/3)+1];local side=sides[(search.index-1)%3+1]
  local x,z=p.x+dx*radial-dz*side,p.z+dz*radial+dx*side
  local target=self.world:floor(x,math.max(p.y,m.y)+220,z)
  if target and target.y-p.y<=180 and p.y-target.y<=640 and dist(p,target)>=90
   and self.world:away(target,m) and self.world:support(target,28) then
   local plan=self.world:arc(p,target,obstacle and 180 or 75,{landingRadius=28,launchEase=obstacle})
   self.nextProbe=ctx.time+1/30
   self.followReason=plan and 'crossing-clear' or (self.world.lastReject or 'crossing-refused')
   if plan and self:playersClear(p,self.world:at(plan,1/plan.duration),ctx) then
    self.followSearch=nil;return self:begin(plan,'follow',p,ctx)
   end
   return nil
  end
 end
 self.followReason=self.world.lastReject or 'no-supported-landing';return nil
end
-- Optional moving tricks must contribute forward progress and finish near Mario.
-- Linear prediction is an eligibility estimate only; each frame still rechecks space.
function O:railKeepsUp(p,rail,ctx,plan)
 local m=ctx.player;local vx,vz=m.vx or 0,m.vz or 0
 local speed=math.sqrt(vx*vx+vz*vz)
 if speed>48 or dist(p,m)>650 then return false,'player-range-or-speed' end
 local total,tx,grade,tz=railShape(rail)
 if not total then return false,'invalid-rail-shape' end
 local entryFrames=plan and not plan.contactEntry and plan.duration or 0
 -- Avoid starting optional fun after the approach has already lost the player.
 -- This is a follow window estimate, not a physical camera visibility promise.
 local entryPlayer={x=m.x+vx*entryFrames,y=m.y,z=m.z+vz*entryFrames}
 if speed>=8 and dist(rail.a,entryPlayer)>400 then return false,'entry-outside-follow-window' end
 local estimated
 if entryFrames>0 then
  local before=self.world:at(plan,1-1/entryFrames)
  estimated=entrySpeed(rail.a.x-before.x,rail.a.y-before.y,rail.a.z-before.z,tx,grade,tz)
 else
  estimated=entrySpeed(p.vx,p.vy,p.vz,tx,grade,tz)
 end
 local progress,grindFrames=0,0
 while progress<total and grindFrames<60 do
  local position={x=rail.a.x+tx*progress,y=rail.a.y+grade*progress,z=rail.a.z+tz*progress}
  local elapsed=entryFrames+grindFrames
  local player={x=m.x+vx*elapsed,y=m.y,z=m.z+vz*elapsed,vx=vx,vz=vz}
  local advance;estimated,advance=O.railDynamics(estimated,grade,O.railPace(rail,position,player))
  progress=progress+advance;grindFrames=grindFrames+1
  if estimated<=.01 then return false,'predicted-momentum-stall' end
 end
 if progress<total then return false,'predicted-grind-timeout' end
 local exitFrames=(rail.exitArc and rail.exitArc.duration) or 18
 local horizon=entryFrames+grindFrames+exitFrames+3
 if horizon>105 then return false,'optional-trip-too-long' end
 if speed<8 then return true end
 -- Mario may turn or stop. Extrapolating a full multi-hop trip wrongly vetoes
 -- ordinary running even beside a good rail. Predict only 0.4 seconds, then
 -- apply a bounded companion excursion. Actual clearance is checked each tick.
 local lookahead=math.min(horizon,12)
 local predicted={x=m.x+vx*lookahead,y=m.y,z=m.z+vz*lookahead}
 if dist(rail.exit,predicted)>650 then
  return false,'exit-outside-companion-range'
 end
 return true
end

-- Incremental discovery is optional and never owns movement. Its cached numeric
-- search progress is invalidated by every relevant live identity/lifecycle change.
function O:scanRails(p,ctx)
 local speed=math.sqrt((ctx.player.vx or 0)^2+(ctx.player.vz or 0)^2)
 if speed>48 or dist(p,ctx.player)>650 then
  if self.world.invalidateRails then self.world:invalidateRails() end
  return nil
 end
 local rail
 if self.world.railScan then
  local dx,dz=ctx.player.vx or 0,ctx.player.vz or 0
  if dx*dx+dz*dz<64 then dx,dz=ctx.player.x-p.x,ctx.player.z-p.z end
  rail=self.world:railScan(p,ctx.player,{frame=ctx.frame,epoch=self.scanEpoch or 0,forwardX=dx,forwardZ=dz,speed=speed})
 else rail=self.world:railNear(p,ctx.player) end
 if rail and dist(p,rail.a)<=500 then
  self.pendingRail={rail=rail,time=ctx.time,scene=ctx.scene,area=ctx.area}
  self:event('rail-opportunity-found',ctx,{from=cp(rail.a),to=cp(rail.b),remaining=rail.visual and rail.visual.remaining or nil})
 end
end
-- A moving follower can consume a discovered entry's longitudinal lead before
-- admission. Try a bounded downstream suffix if pace assistance cannot help.
-- This stores numbers only: next update repeats every live admission proof.
function O:retryRaisedEntry(pending,rail,ctx)
 if not pending or not rail or not rail.visual or rail.shapeSource~='static-surface-edge'
  or (pending.entryRetries or 0)>=2 or type(rail.points)~='table' then return false end
 local a=rail.points[2]
 if not point(a) or not point(rail.a) or not point(rail.b) or not point(rail.exit)
  or dist(rail.a,a)<1 or dist(rail.a,a)>24.001 or dist(a,rail.b)<95.999 then return false end
 local hint={kind='grind',a=cp(a),b=cp(rail.b),entry=cp(a),exit=cp(rail.exit),
  indexKey=rail.indexKey,shapeSource=rail.shapeSource,visual=rail.visual}
 pending.rail=hint;pending.entryRetries=(pending.entryRetries or 0)+1
 -- Keep original time, scene, area and budget-failure count. A suffix never
 -- renews a stale intent, retains a certificate or acquires movement ownership.
 self.pendingRail=pending;self.diagnostic.railReason='entry-suffix-retry'
 self:event('rail-entry-retry',ctx,{reason='predicted-momentum-stall',attempt=pending.entryRetries,
  from=cp(rail.a),to=cp(a),remaining=dist(a,rail.b),indexKey=rail.indexKey})
 return true
end
function O:deferCandidate(rail,ctx,reason)
 self.pendingRail=nil;self.diagnostic.railReason=reason
 if self.world.deferRail then self.world:deferRail(rail,ctx.frame) end
 self:event('rail-candidate-deferred',ctx,{reason=reason,indexKey=rail and rail.indexKey})
end
function O:step(p,ctx)
 local previousDiagnostic=self.diagnostic
 self.diagnostic={frame=ctx and ctx.frame,reason='evaluating'}
 if not point(p) or not ctx or not point(ctx.player) or not finite(ctx.frame) or not finite(ctx.time)
  or not ctx.scene or not ctx.instance or not ctx.phys or not ctx.area or ctx.enabled~=true
  or ctx.dead or ctx.paused or ctx.manual or ctx.water then
  self:cancel('not-gameplay',ctx);self.diagnostic.reason='not-gameplay';return nil
 end
 if ctx.time>=(self.nextStatus or 0) then
  self.nextStatus=ctx.time+5
  local scan=self.world._railScan;local budget=self.world.lastBudget
  self:event('rail-status',ctx,{scene=ctx.scene,skater=cp(p),player=cp(ctx.player),grounded=p.onGround==true,
   playerSpeed=math.sqrt((ctx.player.vx or 0)^2+(ctx.player.vz or 0)^2),gap=dist(p,ctx.player),
   phase=self.task and self.task.phase or 'idle',pending=self.pendingRail~=nil,
   scanPhase=scan and scan.phase,scanIndex=scan and scan.index,
   previousReason=previousDiagnostic and previousDiagnostic.reason,railReason=previousDiagnostic and previousDiagnostic.railReason,
   budgetReason=budget and budget.reason,budgetCalls=budget and budget.calls})
 end
 local c=self.scanContext
 if c and (c.scene~=ctx.scene or c.area~=ctx.area or c.terrain~=ctx.terrain or c.instance~=ctx.instance
  or c.phys~=ctx.phys or c.playerInstance~=ctx.playerInstance) then self:cancel('scan-context-changed',ctx) end
 self.scanContext={scene=ctx.scene,area=ctx.area,terrain=ctx.terrain,instance=ctx.instance,phys=ctx.phys,playerInstance=ctx.playerInstance}
 self:observe(ctx)
 if self.task then self.diagnostic.reason='active-'..self.task.phase;return self:advance(p,ctx) end
 if not p.onGround then self.diagnostic.reason='baseline-airborne';if self.world.invalidateRails then self.world:invalidateRails() end;return nil end
 -- Required navigation owns its scheduled probe before optional rail entry.
 -- Geometry discovery never pauses or changes the baseline follow integrator.
 local followDue=ctx.time>=self.nextProbe
 if followDue then
  self.nextProbe=ctx.time+.2
  local hop=self:follow(p,ctx);self.diagnostic.reason=self.followReason or 'follow-idle'
  if hop then return hop end
 end
 -- Discovery saves targets only, never a permission/certificate. Revalidate entry
 -- next frame with a fresh full budget rather than doing search + proof in one hitch.
 if self.pendingRail then
  -- Starting inside player exclusion cannot authorize any first segment.
  -- Wait before paying for a full rail/arc proof; normal following still runs.
  for _,player in ipairs(ctx.players or {ctx.player}) do
   if not self.world:away(p,player) then self.diagnostic.railReason='entry-player-clearance-wait';return nil end
  end
  local pending=self.pendingRail
  local rail=pending.rail
  local admission=false
  if pending.scene~=ctx.scene or pending.area~=ctx.area or ctx.time-pending.time>=2 or dist(p,rail.a)>500 then
   self.pendingRail=nil;rail=nil
  end
  if rail then
   admission=true
   if self.world.allowRailAdmission then self.world:allowRailAdmission() end
   -- Trimming already freshly proves the remaining rail and exit. Do not run
   -- two complete proofs when the actor has reached the original rail line.
   local trimmed=self.world.trimRail and self.world:trimRail(p,rail,ctx.player)
   if trimmed then rail=trimmed
   elseif self.world.validateRail then rail=self.world:validateRail(rail,ctx.player) end
   if not rail then self:deferCandidate(pending.rail,ctx,self.world.lastReject or 'fresh-rail-proof-refused') end
  end
  if rail then
  if pending.scene==ctx.scene and pending.area==ctx.area and ctx.time-pending.time<2
   and dist(p,ctx.player)<=650
   and self.world:support(rail.a,0) then
   local plan
   if dist(p,rail.a)<8 and math.abs(p.y-rail.a.y)<12 then
    plan={a=cp(p),b=cp(rail.a),landing=cp(rail.a),duration=18,contactEntry=true}
   else plan=self.world:arc(p,rail.a,90,{landingRadius=0}) end
   if plan then
    local eligible,reason=self:railKeepsUp(p,rail,ctx,plan)
    if eligible and rail.visual then
     -- Crowned-cap discovery may use a wider height filter, but admission must
     -- freshly prove exact connected support and the shifted contact envelope.
     eligible=self.world.raisedPresentation and self.world:raisedPresentation(rail.a,rail.a,rail,ctx)~=nil
     reason=eligible and nil or (self.world.lastReject or 'raised-entry-presentation-refused')
    end
    if eligible then
     -- Never commit cooldown/RNG/ownership before the very first live movement
     -- is clear. A nearby moving player may clear the entry on the next tick.
     local first=plan.contactEntry and p or self.world:at(plan,1/plan.duration)
     if self:playersClear(p,first,ctx) then return self:begin(plan,'rail',p,ctx,rail) end
     self.diagnostic.railReason='entry-clearance-wait'
    elseif reason~='predicted-momentum-stall' or not self:retryRaisedEntry(pending,rail,ctx) then
     self:deferCandidate(pending.rail,ctx,reason)
    end
   else self:deferCandidate(pending.rail,ctx,self.world.lastReject or 'entry-refused') end
  end
  end
  -- Do not let generic discovery inherit the admission-only time allowance.
  if admission then return nil end
 end
 local scanning=self.world.railScanActive and self.world:railScanActive()
 if not followDue then
  if scanning then self:scanRails(p,ctx) end
  return nil
 end
 local speed=math.sqrt((ctx.player.vx or 0)^2+(ctx.player.vz or 0)^2)
 if not self.pendingRail and (scanning or (ctx.time>=self.nextFun and speed<=48 and dist(p,ctx.player)<=650)) then
  if not scanning then self.nextFun=ctx.time+.5 end
  self:scanRails(p,ctx)
 end
 return nil
end
return O
