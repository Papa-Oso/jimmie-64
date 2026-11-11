-- Private native input routes for raised Castle banister and BoB fence.
-- One validated initial placement per case. All later movement is native analog/A.
-- No rail seeding, outcome override, held positions/velocities or render claims.
local qa={tick=0,index=1,sceneTick=0,results={},episodes={},done=false,cases={
 {name='castle_banister',level=6,area=1,start={-2400,512,-1160},player={-2000,512,-1160},
  stick=48,frames=600,waypoints={{-1800,-1160},{-2500,-1160}}},
 {name='bob_lower_fence',level=9,area=1,start={-72.057727,768,2861.002140},
  player={-527.66828524,768,2571.14179536},stick=48,frames=600,
  waypoints={{-915.780983,2324.223724},{181.0592498,3022.0356648}}}
}}
local function emit(kind,data)print('[raised-rails] '..kind..' '..Personality.json(data))end
local function pos(p)return p and {x=p.x,y=p.y,z=p.z} or nil end
local function numeric(v)return type(v)=='number' and v==v and math.abs(v)<1e8 end
local function vector(v)
 if not v then return nil end
 local x,y,z=v.x,v.y,v.z
 if numeric(x) and numeric(y) and numeric(z) then return {x=x,y=y,z=z} end
end
local function snapshot(o)
 if not o then return nil end
 local ok,s=pcall(function()
  local gfx=o.header.gfx
  return {object={x=o.oPosX,y=o.oPosY,z=o.oPosZ},gfx=vector(gfx.pos),
   yaw=o.oFaceAngleYaw,pitch=o.oFaceAnglePitch,roll=o.oFaceAngleRoll,
   animFrame=gfx.animInfo.animFrame}
 end)
 return ok and s or {unavailable=true}
end
-- Read-only numeric/string copies. No render/publish calls or retained userdata.
local function scalarSnapshot(value,depth)
 local kind=type(value)
 if kind=='number' then return numeric(value) and value or nil end
 if kind=='string' or kind=='boolean' then return value end
 if kind~='table' or depth<=0 then return nil end
 local copy={};local count=0
 for k,v in pairs(value) do
  if type(k)=='string' or type(k)=='number' then
   count=count+1;if count>100 then copy.truncated=true;break end
   copy[k]=scalarSnapshot(v,depth-1)
  end
 end
 return copy
end
local function bindingSnapshot()
 if not railPresentation or type(railPresentation.status)~='function' then return {available=false} end
 local ok,status=pcall(railPresentation.status,railPresentation)
 if not ok or type(status)~='table' then return {available=false,error='status-unavailable'} end
 local copy=scalarSnapshot(status,8);copy.available=true;return copy
end
-- Registered after the main binding. This only reads the exact objects the
-- binding actually shifted, then records their first non-grind render baseline.
-- It does not invoke the binding or write gfx/physics/animation state.
if HOOK_ON_OBJECT_RENDER~=nil then hook_event(HOOK_ON_OBJECT_RENDER,function(o)
 if qa.done or not qa.current or not qa.renderedOwners then return end
 local role=o==jimmie and 'body' or (o==originalBoard and 'board' or nil)
 if not role then return end
 local status=bindingSnapshot();local frame=get_global_timer()
 local records=status.lastRenderByPart;local rendered=records and records[role]
 if rendered and rendered.frame==frame and rendered.certificateFrame==frame
  and rendered.source=='HOOK_ON_OBJECT_RENDER' and rendered.ownerRole==role then
  qa.renderedOwners[role]={object=o,frame=frame,publicationId=rendered.publicationId,
   certificateFrame=rendered.certificateFrame,episode=opportunityMotion and opportunityMotion.episode}
  return
 end
 local prior=qa.renderedOwners[role]
 if not prior or prior.object~=o or qa.restorationObserved[role] or frame<=prior.frame then return end
 local motion=opportunityMotion
 if dying or (motion and (motion.grind or motion.raisedPresentation)) or status.active~=false
  or originalController.external or originalController.dying then return end
 local observed=snapshot(o)
 if not observed or observed.unavailable then return end
 qa.restorationObserved[role]=true
 emit('baseline-restoration',{case=qa.current.case,frame=frame,ownerRole=role,
  source='HOOK_ON_OBJECT_RENDER',postBinding=true,currentOwner=true,sameRenderedObject=true,
  afterPublicationId=prior.publicationId,afterCertificateFrame=prior.certificateFrame,
  afterRaisedFrame=prior.frame,episode=prior.episode,
  physical=observed.object,gfx=observed.gfx,graphYOffset=o.oGraphYOffset or 0,
  motionGrind=motion and motion.grind==true or false,certificatePresent=motion and motion.raisedPresentation~=nil or false,
  bindingActive=status.active,bindingReason=status.reason,crash=dying==true,
  externalOwner=originalController.external==true,clip=originalController.output and originalController.output.clip,
  meaning='Passive exact-owner readback after main binding; no gfx/state writes'})
end)end
local function railSnapshot(rail)
 if not rail then return nil end
 local v=rail.visual
 return {a=pos(rail.a),b=pos(rail.b),exit=pos(rail.exit),shapeSource=rail.shapeSource,
  indexKey=rail.indexKey,visual=v and {a=pos(v.a),b=pos(v.b),point=pos(v.point),
   source=v.source,level=v.level,area=v.area} or nil}
end
-- Opt-in only: leave query interception off for acceptance timing.
local NATIVE_QUERY_DIAGNOSTICS=false
-- Bounded diagnostic observer of queries the runtime already performs. It never
-- calls geometry itself, invokes a scan, changes a return value, or seeds a plan.
-- Surface userdata are copied immediately into numeric records, never retained.
local function scanSnapshot(world)
 if not world then return nil end
 local capture=world.surfaceRails;local scan=world._railScan
 local out={surface=capture and {generation=capture.generation,error=capture.error,
  segmentCount=#(capture.segments or {}),stats=scalarSnapshot(capture.stats,3)} or nil,
  lastReject=world.lastReject,lastBudget=scalarSnapshot(world.lastBudget,3)}
 if scan then
  local hintIndex=scan.index-(scan.nearCount or 0)
  local hint=scan.hints and scan.hints[hintIndex]
  local selected=hint and {x=hint.x,y=hint.y,z=hint.z,dx=hint.dx,dz=hint.dz,key=hint.key,
   source=hint.source,score=hint.score,points=hint.points,visual=scalarSnapshot(hint.visual,4)} or nil
  out.scan={phase=scan.phase,index=scan.index,indexKey=scan.indexKey,source=scan.source,
   started=scan.started,frame=scan.frame,nearCount=scan.nearCount,nearGeneric=scan.nearGeneric,
   hintCount=#(scan.hints or {}),hintIndex=hintIndex,hint=selected,
   hintMatchesIndexKey=hint~=nil and hint.key==scan.indexKey,
   origin=pos(scan.origin),previous=pos(scan.previous),player=pos(scan.player),
   firstPoint=scan.points and pos(scan.points[1]),
   lastPoint=scan.points and pos(scan.points[#scan.points]),pointCount=#(scan.points or {}),
   dx=scan.dx,dz=scan.dz,fx=scan.fx,fz=scan.fz,width=scan.width,
   maxPoints=scan.maxPoints,exitIndex=scan.exitIndex,exit=pos(scan.exit)}
 end
 return out
end
local function surfaceSnapshot(surface)
 if not surface then return nil end
 return {type=surface.type,flags=surface.flags,poolType=surface.poolType,hasObject=surface.object~=nil,
  normal=vector(surface.normal),vertex1=vector(surface.vertex1),vertex2=vector(surface.vertex2),
  vertex3=vector(surface.vertex3)}
end
local function observingEarlyCastle()
 return qa.current and qa.current.case=='castle_banister' and qa.age<=180
  and (qa.refusalWitnessCount or 0)<24
end
local function observationContext(world)
 if not observingEarlyCastle() then return nil end
 local scan=world._railScan
 if not scan then return nil end
 local raised=scan.source=='static-surface-edge' and scan.indexKey~=nil
 if raised then qa.sawShapeHint=true
 elseif qa.sawShapeHint or qa.age>32 or (qa.genericWitnessCount or 0)>=4 then return nil end
 local identity=tostring(scan.started)..':'..tostring(raised and scan.indexKey or ('generic-'..scan.index))
 if not qa.nativeObservation or qa.nativeObservation.identity~=identity then
  qa.nativeObservation={identity=identity,recent={},calls=0,raised=raised}
 end
 return qa.nativeObservation
end
local function installGeometryTelemetry()
 local world=skateOpportunity and skateOpportunity.world
 if not world or type(world._native)~='function' or type(world.deny)~='function' then return end
 local native,deny=world._native,world.deny
 world._native=function(self,name,...)
  local context=observationContext(self)
  if not context then return native(self,name,...) end
  local args=table.pack(...)
  local before
  if context and name=='resolve_and_return_wall_collisions' then before=pos(args[1]) end
  -- Do not catch native errors: the existing transaction must see them unchanged.
  local a,b=native(self,name,table.unpack(args,1,args.n))
  if context then
   local ok=pcall(function()
    context.calls=context.calls+1
    local record={name=name,frame=self._railScan and self._railScan.frame}
    if name=='find_floor' then
     record.query={x=args[1],y=args[2],z=args[3]};record.height=a;record.hit=b~=nil
     local scan=self._railScan;local hint=scan.hints and scan.hints[scan.index-(scan.nearCount or 0)]
     local target=(scan.points and scan.points[1]) or hint
     if not context.candidateFloor and ((target and math.abs(args[1]-target.x)<.001 and math.abs(args[3]-target.z)<.001)
      or (not target and scan.phase==1)) then
      record.surface=surfaceSnapshot(b);context.candidateFloor=record
     end
    elseif name=='find_ceil' then
     record.query={x=args[1],y=args[2],z=args[3]};record.height=a;record.hit=b~=nil
    elseif name=='resolve_and_return_wall_collisions' then
     record.query=before;record.after=pos(args[1]);record.offsetY=args[2];record.radius=args[3]
     record.hit=a~=nil
     if a~=nil then record.surface=surfaceSnapshot(a) end
    else return end
    context.recent[#context.recent+1]=record
    if #context.recent>8 then table.remove(context.recent,1) end
   end)
   if not ok then qa.telemetryError='native-observation-copy-failed' end
  end
  return a,b
 end
 world.deny=function(self,reason)
  local result=deny(self,reason)
  local context=observationContext(self)
  if context then
   local expectedReject,expectedBudget,expectedScan=self.lastReject,self._budget,self._railScan
   local ok=pcall(function()
    local recent=context.recent[#context.recent]
    local q=recent and recent.query
    local signature=context.identity..':'..tostring(reason)..':'..(q and string.format('%.3f,%.3f,%.3f',q.x,q.y,q.z) or '')
    qa.observedRefusals=qa.observedRefusals or {}
    if qa.observedRefusals[signature] then return end
    qa.observedRefusals[signature]=true;qa.refusalWitnessCount=(qa.refusalWitnessCount or 0)+1
    if not context.raised then qa.genericWitnessCount=(qa.genericWitnessCount or 0)+1 end
    local m=gMarioStates and gMarioStates[0]
    local witness={case=qa.current.case,frame=expectedScan.frame,age=qa.age+1,reason=reason,
     actor=pos(PHYS),player=m and pos(m.pos),geometry=scanSnapshot(self),
     raisedHint=context.raised,actualNativeCallsObserved=context.calls,candidateFloor=scalarSnapshot(context.candidateFloor,6),
     recent=scalarSnapshot(context.recent,6),extraGeometryQueries=0,
     budgetAtRefusal=expectedBudget and {calls=expectedBudget.calls,queries=expectedBudget.queries,
      elapsed=expectedBudget.elapsed,reason=expectedBudget.reason},
     meaning='Observed existing native queries; no replay/probe or movement authority'}
    witness.diagnosticsUnchanged=self.lastReject==expectedReject and self._budget==expectedBudget and self._railScan==expectedScan
    qa.pendingGeometryWitnesses=qa.pendingGeometryWitnesses or {}
    qa.pendingGeometryWitnesses[#qa.pendingGeometryWitnesses+1]=witness
   end)
   if not ok then qa.telemetryError='refusal-observation-copy-failed' end
  end
  return result
 end
end
if NATIVE_QUERY_DIAGNOSTICS then installGeometryTelemetry() end
local oldStep=step_skate_opportunity
step_skate_opportunity=function()
 local t=clock_elapsed_f64();local r=oldStep();qa.opSeconds=clock_elapsed_f64()-t;return r
end
if skateOpportunity then
 local originalEvent=skateOpportunity.event
 skateOpportunity.event=function(self,kind,ctx,extra)
  originalEvent(self,kind,ctx,extra)
  if not qa.current then return end
  local task=self.task;local episode=self.episode
  local rail=railSnapshot(task and task.rail)
  if kind=='selected' and extra and extra.opportunity=='rail' then
   qa.episodes[episode]={selected=ctx.frame,rail=rail};qa.current.railSelected=qa.current.railSelected+1
  end
  local e=qa.episodes[episode]
  if e then
   if kind=='rail-contact-observed' then e.contact=ctx.frame;qa.current.contacts=qa.current.contacts+1 end
   if kind=='rail-exit' then e.exit=ctx.frame end
   if kind=='landing-observed' and extra and extra.opportunity=='rail' and e.contact and e.exit then
    e.landed=ctx.frame;qa.current.completedJourneys=qa.current.completedJourneys+1
   end
   if kind=='cancelled' or kind=='rail-stall-handback' then qa.current.handbacks=qa.current.handbacks+1 end
  end
  emit('event',{case=qa.current.case,kind=kind,episode=episode,frame=ctx.frame,age=qa.age,
   extra=extra,position=pos(PHYS),grounded=PHYS and PHYS.onGround,
   rail=rail or (e and e.rail),taskPhase=task and task.phase})
 end
end
local function validateRoute(c)
 local rows={};local valid=true
 local function sample(x,z,y,label)
  local h,s=find_floor(x,y+24,z)
  local okay=s~=nil and numeric(h) and math.abs(h-y)<=24
  rows[#rows+1]={x=x,z=z,height=h,expected=y,valid=okay,label=label};valid=valid and okay
 end
 sample(c.start[1],c.start[3],c.start[2],'actor')
 sample(c.player[1],c.player[3],c.player[2],'player')
 local previous={c.player[1],c.player[3]}
 for i=1,#c.waypoints+1 do
  local target=c.waypoints[(i-1)%#c.waypoints+1]
  local dx,dz=target[1]-previous[1],target[2]-previous[2]
  local count=math.max(1,math.ceil(math.sqrt(dx*dx+dz*dz)/48))
  for k=1,count do sample(previous[1]+dx*k/count,previous[2]+dz*k/count,c.player[2],'route-'..i)end
  previous=target
 end
 return valid,rows
end
-- BEGIN_INITIAL_PLACEMENT: the only actor/Mario state writes in this harness.
local function place(m,c)
 local valid,floors=validateRoute(c)
 emit('placement',{case=c.name,level=c.level,area=c.area,valid=valid,oneInitialPlacement=true,
  start=pos({x=c.start[1],y=c.start[2],z=c.start[3]}),
  player=pos({x=c.player[1],y=c.player[2],z=c.player[3]}),floorSamples=floors})
 if not valid then return false end
 m.pos.x,m.pos.y,m.pos.z=c.player[1],floors[2].height,c.player[3]
 m.vel.x,m.vel.y,m.vel.z=0,0,0;m.forwardVel=0;set_mario_action(m,ACT_IDLE,0)
 if skateOpportunity then skateOpportunity:cancel('private-raised-route-placement',{frame=get_global_timer(),time=now()})end
 if skateDirector then skateDirector:reset('private-raised-route-placement')end
 if rejoinHost then rejoinHost:invalidate();rejoinHost.policy.nextTry=0;rejoinHost.policy.latched=false end
 PHYS={x=c.start[1],y=floors[1].height,z=c.start[3],vx=0,vy=0,vz=0,onGround=true,airT=0,pushT=0,
  yaw=math.atan2(c.player[1]-c.start[1],c.player[3]-c.start[3])};PHYS.prevYaw=PHYS.yaw
 PHYS_AIR=false;PHYS_PUSHING=false;opportunityMotion=nil;rejoinTraceResult=nil
 currentSkateIntent=nil;currentSkateSensors=nil;blockedT=0;avoidT=0;detourT=0
 originalController:reset();update_pose_animation(0)
 for _,o in ipairs({jimmie,originalBoard})do
  o.oPosX,o.oPosY,o.oPosZ=PHYS.x,PHYS.y,PHYS.z
  obj_set_gfx_pos(o,PHYS.x,PHYS.y,PHYS.z);obj_skip_interpolation(o)
 end
 qa.age=0;qa.settling=false;qa.stableGround=0;qa.waypoint=1;qa.stuckInput=0;qa.nextJump=0
 qa.episodes={};qa.lastPhase=nil;qa.lastMario=pos(m.pos)
 qa.renderedOwners={};qa.restorationObserved={}
 qa.current={case=c.name,level=c.level,area=c.area,railSelected=0,contacts=0,completedJourneys=0,
  handbacks=0,grindTicks=0,movingGrindTicks=0,movingFrames=0,marioDistance=0,
  maxMarioSpeed=0,maxGap=0,maxOpSeconds=0,waypointsReached=0,crashFrames=0,jumpInputs=0,
  outcomeRollsBefore=originalOutcomes and originalOutcomes.rolls,
  outcomeFailuresBefore=originalOutcomes and originalOutcomes.failures}
 return true
end
-- END_INITIAL_PLACEMENT
local function neutral(m)
 m.controller.stickX=0;m.controller.stickY=0;m.controller.stickMag=0
 m.controller.buttonDown=0;m.controller.buttonPressed=0
end
hook_event(HOOK_BEFORE_MARIO_UPDATE,function(m)
 if qa.done or not qa.current or m.playerIndex~=0 or not m.controller or not m.area or not m.area.camera then return end
 if qa.settling then neutral(m);return end
 local c=qa.cases[qa.index];local target=c.waypoints[qa.waypoint]
 local dx,dz=target[1]-m.pos.x,target[2]-m.pos.z
 if dx*dx+dz*dz<55*55 then
  qa.current.waypointsReached=qa.current.waypointsReached+1
  qa.waypoint=qa.waypoint%#c.waypoints+1;target=c.waypoints[qa.waypoint]
  dx,dz=target[1]-m.pos.x,target[2]-m.pos.z
 end
 local yaw=math.atan2(dx,dz)-m.area.camera.yaw*math.pi/32768
 m.controller.stickX=math.sin(yaw)*c.stick;m.controller.stickY=-math.cos(yaw)*c.stick;m.controller.stickMag=c.stick
 m.controller.buttonDown=0;m.controller.buttonPressed=0
 local speed=math.sqrt(m.vel.x*m.vel.x+m.vel.z*m.vel.z)
 qa.stuckInput=speed<8 and qa.stuckInput+1 or 0
 if qa.stuckInput>=15 and qa.age>=qa.nextJump then
  m.controller.buttonDown=A_BUTTON;m.controller.buttonPressed=A_BUTTON
  qa.nextJump=qa.age+45;qa.stuckInput=0;qa.current.jumpInputs=qa.current.jumpInputs+1
 end
end)
emit('policy',{fixtureVariant='strict',failCount=TrickOutcomes and TrickOutcomes.FAIL_COUNT,
 failOutOf=TrickOutcomes and TrickOutcomes.FAIL_OUT_OF,normalRandomUnmodified=true,
 oneInitialPlacement=true,heldStates=false,seededRail=false,routeFrames=600,
 neutralSettleFrames=15,maxSettleFrames=180,renderedAcceptance=false})
hook_event(HOOK_UPDATE,function()
 if qa.done then return end;qa.tick=qa.tick+1
 if qa.tick>2400 then qa.done=true;emit('failure',{reason='bounded-harness-timeout'});return end
 local m,np=gMarioStates[0],gNetworkPlayers[0]
 if not m or not np or not m.area or m.action==0 then return end
 local c=qa.cases[qa.index]
 if not c then
  qa.done=true;emit('COMPLETE',{results=qa.results,
   meaning='Native synthetic input after one placement; normal crashes; no rendered or human-play acceptance'})
  return
 end
 if np.currLevelNum~=c.level or np.currAreaIndex~=c.area then
  if not qa.warpRequested and qa.tick>=120 then
   qa.warpRequested=true;qa.sceneTick=0
   emit('warp',{case=c.name,level=c.level,area=c.area,frame=get_global_timer()})
   warp_to_level(c.level,c.area,0)
  end
  return
 end
 qa.warpRequested=false;qa.sceneTick=qa.sceneTick+1;if qa.sceneTick<40 then return end
 if not qa.current then
  if not jimmie or not originalBoard or not PHYS then emit('failure',{case=c.name,reason='pair-not-ready'});qa.done=true;return end
  if not place(m,c)then
   qa.results[#qa.results+1]={case=c.name,setup=false};emit('case-end',qa.results[#qa.results])
   qa.index=qa.index+1;qa.sceneTick=0;return
  end
 end
 local q=qa.current;qa.age=qa.age+1
 -- Emit only after the runtime transaction and measured step have finished.
 for _,witness in ipairs(qa.pendingGeometryWitnesses or {})do emit('native-refusal-witness',witness)end
 qa.pendingGeometryWitnesses=nil
 if qa.telemetryError then emit('telemetry-error',{case=c.name,reason=qa.telemetryError});qa.telemetryError=nil end
 local p,motion,output=PHYS,opportunityMotion,originalController.output
 local speed=math.sqrt(m.vel.x*m.vel.x+m.vel.z*m.vel.z)
 q.maxMarioSpeed=math.max(q.maxMarioSpeed,speed);if speed>=8 then q.movingFrames=q.movingFrames+1 end
 local old=qa.lastMario;q.marioDistance=q.marioDistance+math.sqrt((m.pos.x-old.x)^2+(m.pos.z-old.z)^2)
 qa.lastMario=pos(m.pos);q.maxOpSeconds=math.max(q.maxOpSeconds,qa.opSeconds or 0)
 if p then
  q.final={x=p.x,y=p.y,z=p.z,grounded=p.onGround,gap=math.sqrt((p.x-m.pos.x)^2+(p.z-m.pos.z)^2)}
  q.maxGap=math.max(q.maxGap,q.final.gap)
 end
 if motion and motion.grind then q.grindTicks=q.grindTicks+1;if speed>=8 then q.movingGrindTicks=q.movingGrindTicks+1 end end
 if dying then q.crashFrames=q.crashFrames+1 end
 local task=skateOpportunity and skateOpportunity.task
 local episode=motion and motion.episode or (task and skateOpportunity.episode)
 local remembered=episode and qa.episodes[episode]
 if qa.age%4==0 or (c.name=='castle_banister' and qa.age<=32) or (motion and motion.grind) or (motion and motion.phase~=qa.lastPhase) or qa.settling then
  emit('trace',{case=c.name,level=np.currLevelNum,area=np.currAreaIndex,age=qa.age,frame=get_global_timer(),
   mario=pos(m.pos),marioSpeed=speed,marioGrounded=math.abs(m.pos.y-m.floorHeight)<=4 and math.abs(m.vel.y)<1,
   waypoint=qa.waypoint,position=q.final,episode=episode,taskActive=task~=nil,
   phase=motion and motion.phase,kind=motion and motion.kind,grind=motion and motion.grind,
   rail=railSnapshot(task and task.rail) or (remembered and remembered.rail),clip=output and output.clip,
   body=snapshot(jimmie),board=snapshot(originalBoard),
   certificate=motion and scalarSnapshot(motion.raisedPresentation,6),binding=bindingSnapshot(),
   diagnostic=skateOpportunity and skateOpportunity.diagnostic,
   follow=skateOpportunity and skateOpportunity.followReason,
   budget=skateOpportunity and skateOpportunity.world.lastBudget,
   reject=skateOpportunity and skateOpportunity.world.lastReject,
   geometry=c.name=='castle_banister' and qa.age<=180 and scanSnapshot(skateOpportunity and skateOpportunity.world) or nil,
   opSeconds=qa.opSeconds,crash=dying,settling=qa.settling})
 end
 qa.lastPhase=motion and motion.phase
 if qa.age>=c.frames and not qa.settling then
  qa.settling=true;q.routeCutoffFrame=get_global_timer();q.routeMovingGrindTicks=q.movingGrindTicks
  emit('input-released',{case=c.name,frame=get_global_timer(),meaning='native neutral input, no forced state'})
 end
 if qa.settling then
  q.releasedInputTicks=qa.age-c.frames
  local grounded=p and p.onGround and not dying and not task
   and math.abs(m.pos.y-m.floorHeight)<=4 and math.abs(m.vel.y)<1
  qa.stableGround=grounded and speed<1 and q.releasedInputTicks>0 and qa.stableGround+1 or 0
  if qa.stableGround>=15 or q.releasedInputTicks>=180 then
   q.settled=qa.stableGround>=15;q.stableGroundTicks=qa.stableGround
   q.nativeMovement=q.marioDistance>500 and q.movingFrames>120 and q.maxMarioSpeed>16
   q.hadMovingGrind=(q.routeMovingGrindTicks or 0)>0
   q.bindingFinal=bindingSnapshot()
   q.outcomeRollsAfter=originalOutcomes and originalOutcomes.rolls
   q.outcomeFailuresAfter=originalOutcomes and originalOutcomes.failures
   qa.results[#qa.results+1]=q;emit('case-end',q);qa.current=nil;qa.index=qa.index+1;qa.sceneTick=0
  end
 end
end)
