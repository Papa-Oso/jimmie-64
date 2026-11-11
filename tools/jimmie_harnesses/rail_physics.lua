-- Controlled contact-state mechanics fixtures on real native Castle collision.
-- This deliberately seeds grind contact, NOT automatic rail discovery. Flat
-- mechanics use the Castle's broad floor and do not claim it is a narrow rail.
local qa={tick=0,sceneTick=0,index=0,done=false,results={}}
local upper={x=-854.406282602059,y=590,z=-385.79616044948193}
local lower={x=-854.406282602059,y=446,z=-241.79616044948193}
local exit={x=-974.406282602059,y=313.53399658203,z=-169.79616044948193}
local flatA={x=-1100,y=512,z=-1000};local flatB={x=-1100,y=512,z=-850};local flatExit={x=-1100,y=512,z=-650}
qa.cases={
 {name='downhill',a=upper,b=lower,exit=exit,speed=8,accelerates=true},
 {name='downhill_cap',a=upper,b=lower,exit=exit,speed=48},
 {name='uphill_stall',a=lower,b=upper,exit=exit,speed=8,stall=true},
 {name='uphill_momentum',a=lower,b=upper,exit=exit,speed=48,slows=true},
 {name='flat_friction',a=flatA,b=flatB,exit=flatExit,speed=8,slows=true,flatBroadFloor=true},
 {name='flat_stall',a=flatA,b=flatB,exit=flatExit,speed=2,stall=true,flatBroadFloor=true},
}
local function cp(p)return {x=p.x,y=p.y,z=p.z}end
local function emit(k,v)print('[rail-physics] '..k..' '..Personality.json(v))end
originalOutcomes=TrickOutcomes.new{random=function()return 1000 end}
local function context(m,np)
 return {scene=contextState:scene(np),frame=get_global_timer(),time=now(),instance=jimmie,phys=PHYS,area=m.area,
  terrain=smlua_collision_util_get_current_terrain_collision(),player={x=m.pos.x,y=m.pos.y,z=m.pos.z,vx=0,vz=0},
  players={{x=m.pos.x,y=m.pos.y,z=m.pos.z,vx=0,vz=0}},playerInstance=m.marioObj,playerGrounded=true,
  enabled=true,dead=false,paused=false,manual=false,water=false}
end
local function apply(out)
 local q,v=out.position,out.velocity
 PHYS.x,PHYS.y,PHYS.z=q.x,q.y,q.z;PHYS.vx,PHYS.vy,PHYS.vz=v.x,v.y,v.z;PHYS.onGround=out.onGround;PHYS.airT=out.airTime
 opportunityMotion=out;PHYS_AIR=not out.onGround
 for _,o in ipairs({jimmie,originalBoard})do o.oPosX,o.oPosY,o.oPosZ=q.x,q.y,q.z;obj_set_gfx_pos(o,q.x,q.y,q.z);obj_skip_interpolation(o)end
end
local function place(m,np,c)
 local w=skateOpportunity.world
 for _,p in ipairs({c.a,c.b,c.exit})do local f=w:floor(p.x,p.y+24,p.z);if not f or math.abs(f.y-p.y)>2 then return false,'native-fixture-support' end end
 m.pos.x,m.pos.y,m.pos.z=-700,512,-700;m.vel.x,m.vel.y,m.vel.z=0,0,0;set_mario_action(m,ACT_IDLE,0)
 skateOpportunity:cancel('controlled-physics-fixture',{frame=get_global_timer(),time=now()})
 if skateDirector then skateDirector:reset('controlled-physics-fixture')end
 if rejoinHost then rejoinHost:invalidate()end
 local dx,dy,dz=c.b.x-c.a.x,c.b.y-c.a.y,c.b.z-c.a.z;local length=math.sqrt(dx*dx+dy*dy+dz*dz)
 PHYS={x=c.a.x,y=c.a.y,z=c.a.z,vx=c.speed*dx/length,vy=c.speed*dy/length,vz=c.speed*dz/length,onGround=true,airT=0,pushT=0,yaw=math.atan2(dx,dz)};PHYS.prevYaw=PHYS.yaw
 PHYS_AIR=false;PHYS_PUSHING=false;dying=false;nextDeath=now()+1000;opportunityMotion=nil;rejoinTraceResult=nil
 currentSkateIntent=nil;currentSkateSensors=nil;blockedT=0;avoidT=0;detourT=0
 originalController:reset()
 qa.current={case=c.name,controlledContact=true,flatBroadFloor=c.flatBroadFloor==true,speeds={},stalled=false,exit=false,landed=false,frames=0,maxCalls=0,maxSeconds=0}
 if not qa.eventWrapped then
  local old=skateOpportunity.event
  skateOpportunity.event=function(self,kind,ctx,extra)
   if qa.current then
    if kind=='rail-stalled' then qa.current.stalled=true end
    if kind=='rail-exit' then qa.current.exit=true;qa.current.exitReason=extra and extra.reason end
    if kind=='landing-observed' then qa.current.landed=true end
    if kind=='cancelled' then qa.current.cancel=extra and extra.reason end
   end
   return old(self,kind,ctx,extra)
  end
  qa.eventWrapped=true
 end
 local ctx=context(m,np);local plan={a=cp(c.a),b=cp(c.a),landing=cp(c.a),duration=18,contactEntry=true}
 local rail={kind='grind',a=cp(c.a),b=cp(c.b),entry=cp(c.a),exit=cp(c.exit)}
 local out=w:transaction(function()return skateOpportunity:begin(plan,'rail',PHYS,ctx,rail)end)
 if not out then return false,'contact-fixture-refused' end
 apply(out);return true
end
hook_event(HOOK_UPDATE,function()
 if qa.done then return end;qa.tick=qa.tick+1
 local m,np=gMarioStates[0],gNetworkPlayers[0]
 if not m or not np or not m.area or m.action==0 then return end
 if not qa.warped and np.currLevelNum==16 and qa.tick>=120 then qa.warped=true;warp_to_level(6,1,0);return end
 if np.currLevelNum~=6 or np.currAreaIndex~=1 then return end
 qa.sceneTick=qa.sceneTick+1;if qa.sceneTick<40 then return end
 if not qa.current then
  qa.index=qa.index+1;local c=qa.cases[qa.index]
  if not c then qa.done=true;emit('COMPLETE',{results=qa.results,controlledContact=true});return end
  if not jimmie or not originalBoard or not PHYS then qa.done=true;emit('failure',{reason='pair-not-ready'});return end
  local ok,reason=place(m,np,c)
  if not ok then qa.done=true;emit('failure',{case=c.name,reason=reason});return end
 end
 local c,q=qa.cases[qa.index],qa.current;q.frames=q.frames+1
 local task=skateOpportunity.task;local motion=opportunityMotion
 if task and motion and motion.grind and motion.phase~='dismount' then q.speeds[#q.speeds+1]=task.grindSpeed end
 local budget=skateOpportunity.world.lastBudget or {};q.maxCalls=math.max(q.maxCalls,budget.calls or 0);q.maxSeconds=math.max(q.maxSeconds,budget.elapsed or 0)
 if budget.reason then q.cancel=budget.reason end
 if q.frames<=3 or motion and (motion.phase~=qa.lastPhase or motion.grind) then
  emit('trace',{case=c.name,frame=get_global_timer(),age=q.frames,phase=motion and motion.phase,grind=motion and motion.grind,
   speed=task and task.grindSpeed,grade=task and task.grindGrade,position=PHYS and {x=PHYS.x,y=PHYS.y,z=PHYS.z,grounded=PHYS.onGround},
   clip=originalController.output and originalController.output.clip,budget=budget})
 end
 qa.lastPhase=motion and motion.phase
 m.pos.x,m.pos.y,m.pos.z=-700,512,-700;m.vel.x,m.vel.y,m.vel.z=0,0,0;m.forwardVel=0
 if m.controller then m.controller.buttonDown=0;m.controller.buttonPressed=0;m.controller.stickX=0;m.controller.stickY=0;m.controller.stickMag=0 end
 if q.landed or q.cancel or q.frames>=145 then
  local bounded=true;for _,speed in ipairs(q.speeds)do if speed<0 or speed>48 then bounded=false end end
  q.grounded=PHYS and PHYS.onGround==true
  q.passed=q.landed and q.exit and q.grounded and not q.cancel and bounded and #q.speeds>=2
   and (not c.stall or q.stalled) and (not c.accelerates or q.speeds[2]>q.speeds[1]) and (not c.slows or q.speeds[2]<q.speeds[1])
  qa.results[#qa.results+1]=q;emit('case-end',q);qa.current=nil
 end
end)
