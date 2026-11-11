-- Isolated native controller routes. One initial placement per route only.
-- Thereafter Mario moves through the actual engine from synthetic analog input.
-- No seeded rail, repeated position/velocity hold, trick request or crash override.
local qa={tick=0,sceneTick=0,index=0,results={},episodes={},done=false,cases={
 {name='east_parallel',start={-890,512,-620},player={-700,512,-800},stick=64,frames=600,waypoints={{-700,300},{-1024,300},{-1024,-800},{-700,-800}}},
 {name='west_parallel',start={-1160,512,-620},player={-1350,512,-800},stick=64,frames=600,waypoints={{-1350,300},{-1024,300},{-1024,-800},{-1350,-800}}},
 {name='center_stairs',start={-700,0,300},player={-1024,0,300},stick=48,frames=600,waypoints={{-1024,-800},{-1024,300}}}
}}
local function emit(kind,data)print('[moving-rails] '..kind..' '..Personality.json(data))end
local function pos(p)return {x=p.x,y=p.y,z=p.z}end
local oldStep=step_skate_opportunity
step_skate_opportunity=function()local t=clock_elapsed_f64();local r=oldStep();qa.opSeconds=clock_elapsed_f64()-t;return r end
if skateOpportunity then
 local originalEvent=skateOpportunity.event
 skateOpportunity.event=function(self,kind,ctx,extra)
  originalEvent(self,kind,ctx,extra)
  if not qa.current then return end
  if kind=='rail-candidate-deferred' and extra and extra.reason=='repeated-native-budget' then qa.current.budgetDeferrals=qa.current.budgetDeferrals+1 end
  local episode=self.episode
  if kind=='selected' and extra and extra.opportunity=='rail' then qa.episodes[episode]={selected=ctx.frame};qa.current.railSelected=qa.current.railSelected+1 end
  local e=qa.episodes[episode]
  if e then
   if kind=='rail-contact-observed' then e.contact=ctx.frame;qa.current.contacts=qa.current.contacts+1 end
   if kind=='rail-exit' then e.exit=ctx.frame end
   if kind=='landing-observed' and extra and extra.opportunity=='rail' and e.contact and e.exit then
    e.landed=ctx.frame;qa.current.completedJourneys=qa.current.completedJourneys+1
   end
  end
 end
end
local function place(m,c)
 local sh,ss=find_floor(c.start[1],c.start[2]+24,c.start[3]);local mh,ms=find_floor(c.player[1],c.player[2]+24,c.player[3])
 local valid=ss~=nil and ms~=nil and math.abs(sh-c.start[2])<100 and math.abs(mh-c.player[2])<100
 emit('placement',{case=c.name,valid=valid,startHeight=sh,playerHeight=mh,oneInitialPlacement=true})
 if not valid then return false end
 m.pos.x,m.pos.y,m.pos.z=c.player[1],mh,c.player[3];m.vel.x,m.vel.y,m.vel.z=0,0,0;m.forwardVel=0;set_mario_action(m,ACT_IDLE,0)
 if skateOpportunity then skateOpportunity:cancel('private-moving-route-placement',{frame=get_global_timer(),time=now()})end
 if skateDirector then skateDirector:reset('private-moving-route-placement')end
 if rejoinHost then rejoinHost:invalidate();rejoinHost.policy.nextTry=0;rejoinHost.policy.latched=false end
 PHYS={x=c.start[1],y=sh,z=c.start[3],vx=0,vy=0,vz=0,onGround=true,airT=0,pushT=0,yaw=math.atan2(c.player[1]-c.start[1],c.player[3]-c.start[3])};PHYS.prevYaw=PHYS.yaw
 PHYS_AIR=false;PHYS_PUSHING=false;opportunityMotion=nil;rejoinTraceResult=nil
 currentSkateIntent=nil;currentSkateSensors=nil;blockedT=0;avoidT=0;detourT=0
 originalController:reset();update_pose_animation(0)
 for _,o in ipairs({jimmie,originalBoard})do o.oPosX,o.oPosY,o.oPosZ=PHYS.x,PHYS.y,PHYS.z;obj_set_gfx_pos(o,PHYS.x,PHYS.y,PHYS.z);obj_skip_interpolation(o)end
 qa.age=0;qa.settling=false;qa.stableGround=0;qa.waypoint=1;qa.stuckInput=0;qa.nextJump=0;qa.episodes={};qa.lastPhase=nil;qa.lastMario=pos(m.pos)
 qa.current={case=c.name,railSelected=0,contacts=0,completedJourneys=0,budgetDeferrals=0,budgetRefusalFrames=0,grindTicks=0,movingGrindTicks=0,movingFrames=0,marioDistance=0,maxMarioSpeed=0,maxGap=0,maxOpSeconds=0,waypointsReached=0,crashFrames=0}
 return true
end
hook_event(HOOK_BEFORE_MARIO_UPDATE,function(m)
 if qa.done or not qa.current or m.playerIndex~=0 or not m.controller or not m.area or not m.area.camera then return end
 if qa.settling then
  m.controller.stickX=0;m.controller.stickY=0;m.controller.stickMag=0;m.controller.buttonDown=0;m.controller.buttonPressed=0
  return
 end
 local c=qa.cases[qa.index];local target=c.waypoints[qa.waypoint]
 local dx,dz=target[1]-m.pos.x,target[2]-m.pos.z
 if dx*dx+dz*dz<60*60 then
  qa.current.waypointsReached=qa.current.waypointsReached+1;qa.waypoint=qa.waypoint%#c.waypoints+1
  target=c.waypoints[qa.waypoint];dx,dz=target[1]-m.pos.x,target[2]-m.pos.z
 end
 -- Stock camera mode in the isolated runner. Native input and collision code
 -- compute Mario action, speed, gravity and position; those are not overwritten.
 local yaw=math.atan2(dx,dz)-m.area.camera.yaw*math.pi/32768
 m.controller.stickX=math.sin(yaw)*c.stick;m.controller.stickY=-math.cos(yaw)*c.stick;m.controller.stickMag=c.stick
 m.controller.buttonDown=0;m.controller.buttonPressed=0
 local speed=math.sqrt(m.vel.x*m.vel.x+m.vel.z*m.vel.z)
 qa.stuckInput=speed<8 and qa.stuckInput+1 or 0
 if qa.stuckInput>=15 and qa.age>=qa.nextJump then
  m.controller.buttonDown=A_BUTTON;m.controller.buttonPressed=A_BUTTON
  qa.nextJump=qa.age+45;qa.stuckInput=0;qa.current.jumpInputs=(qa.current.jumpInputs or 0)+1
 end
end)
hook_event(HOOK_UPDATE,function()
 if qa.done then return end;qa.tick=qa.tick+1
 local m,np=gMarioStates[0],gNetworkPlayers[0]
 if not m or not np or not m.area or m.action==0 then return end
 if not qa.warped and np.currLevelNum==16 and qa.tick>=120 then qa.warped=true;emit('warp',{frame=get_global_timer()});warp_to_level(6,1,0);return end
 if np.currLevelNum~=6 or np.currAreaIndex~=1 then return end
 qa.sceneTick=qa.sceneTick+1;if qa.sceneTick<40 then return end
 if not qa.current then
  qa.index=qa.index+1;local c=qa.cases[qa.index]
  if not c then qa.done=true;emit('COMPLETE',{results=qa.results,meaning='Native synthetic-input routes, not human/visual acceptance; normal crash lottery unchanged'});return end
  if not jimmie or not originalBoard or not PHYS then emit('failure',{case=c.name,reason='pair-not-ready'});qa.done=true;return end
  if not place(m,c)then qa.results[#qa.results+1]={case=c.name,setup=false};return end
 end
 local c,q=qa.cases[qa.index],qa.current;qa.age=qa.age+1
 local p=PHYS;local motion=opportunityMotion;local output=originalController.output
 local speed=math.sqrt(m.vel.x*m.vel.x+m.vel.z*m.vel.z)
 q.maxMarioSpeed=math.max(q.maxMarioSpeed,speed);if speed>=8 then q.movingFrames=q.movingFrames+1 end
 local old=qa.lastMario;q.marioDistance=q.marioDistance+math.sqrt((m.pos.x-old.x)^2+(m.pos.z-old.z)^2);qa.lastMario=pos(m.pos)
 q.maxOpSeconds=math.max(q.maxOpSeconds,qa.opSeconds or 0)
 if skateOpportunity and skateOpportunity.diagnostic and skateOpportunity.diagnostic.frame==get_global_timer() then
  local budget=skateOpportunity.world.lastBudget
  if budget and (budget.reason=='native-time-budget' or budget.reason=='native-query-budget') then q.budgetRefusalFrames=q.budgetRefusalFrames+1 end
 end
 if p then q.final={x=p.x,y=p.y,z=p.z,grounded=p.onGround,gap=math.sqrt((p.x-m.pos.x)^2+(p.z-m.pos.z)^2)};q.maxGap=math.max(q.maxGap,q.final.gap)end
 if motion and motion.grind then q.grindTicks=q.grindTicks+1;if speed>=8 then q.movingGrindTicks=q.movingGrindTicks+1 end end
 if dying then q.crashFrames=q.crashFrames+1 end
 if qa.age%8==0 or (motion and motion.phase~=qa.lastPhase)then
  emit('trace',{case=c.name,age=qa.age,frame=get_global_timer(),mario=pos(m.pos),marioSpeed=speed,waypoint=qa.waypoint,position=q.final,
   phase=motion and motion.phase,kind=motion and motion.kind,grind=motion and motion.grind,clip=output and output.clip,
   bodyAnim=jimmie and jimmie.header.gfx.animInfo.animFrame,boardAnim=originalBoard and originalBoard.header.gfx.animInfo.animFrame,
   diagnostic=skateOpportunity and skateOpportunity.diagnostic,follow=skateOpportunity and skateOpportunity.followReason,
   budget=skateOpportunity and skateOpportunity.world.lastBudget,reject=skateOpportunity and skateOpportunity.world.lastReject,
   opSeconds=qa.opSeconds,crash=dying})
 end
 qa.lastPhase=motion and motion.phase
 if qa.age>=c.frames and not qa.settling then
  qa.settling=true;q.routeCutoffFrame=get_global_timer();q.routeMovingGrindTicks=q.movingGrindTicks
  emit('input-released',{case=c.name,frame=get_global_timer(),meaning='native neutral input, no forced state'})
 end
 if qa.settling then
  q.releasedInputTicks=qa.age-c.frames
  local grounded=p and p.onGround and not dying and not (skateOpportunity and skateOpportunity.task)
  qa.stableGround=grounded and speed<1 and qa.stableGround+1 or 0
  if qa.stableGround>=15 or q.releasedInputTicks>=180 then
   q.settled=qa.stableGround>=15
   q.nativeMovement=q.marioDistance>500 and q.movingFrames>120 and q.maxMarioSpeed>16
   q.hadMovingGrind=(q.routeMovingGrindTicks or 0)>0
   qa.results[#qa.results+1]=q;emit('case-end',q);qa.current=nil
  end
 end
end)
