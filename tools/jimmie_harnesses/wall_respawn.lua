-- Exact native warp destinations and unmodified live spawning. No seeded
-- companion coordinates, collision overrides, scene edits or outcome overrides.
local qa={tick=0,index=1,sceneTick=0,results={},done=false,cases={
 {name='grounds',level=LEVEL_CASTLE_GROUNDS,area=1},
 {name='bob_first',level=LEVEL_BOB,area=1},
 {name='bob_star_exit',level=LEVEL_CASTLE,area=1,node=0x32},
 {name='bob_second',level=LEVEL_BOB,area=1},
 {name='bob_death_exit',level=LEVEL_CASTLE,area=1,node=0x64},
 {name='bob_third',level=LEVEL_BOB,area=1},
 {name='bob_star_exit_repeat',level=LEVEL_CASTLE,area=1,node=0x32},
 {name='castle_basement',level=LEVEL_CASTLE,area=2},
 {name='castle_upper',level=LEVEL_CASTLE,area=3},
 {name='grounds_return',level=LEVEL_CASTLE_GROUNDS,area=1}}}
local function emit(kind,data)print('[wall-respawn] '..kind..' '..Personality.json(data))end
local function audit(o,m)
 local q={x=o.oPosX,y=o.oPosY,z=o.oPosZ};local wallCount=0;local ceiling=20000
 for _,height in ipairs({4,32,72,112,160,208}) do
  local scratch={x=q.x,y=q.y,z=q.z};local wall=resolve_and_return_wall_collisions(scratch,height,64)
  if wall or math.abs(scratch.x-q.x)>.05 or math.abs(scratch.z-q.z)>.05 then wallCount=wallCount+1 end
 end
 local supported=true
 for _,dx in ipairs({-64,0,64}) do for _,dz in ipairs({-64,0,64}) do
  local h,s=find_floor(q.x+dx,q.y+48,q.z+dz)
  if not s or math.abs(h-q.y)>40 then supported=false end
  local ch=find_ceil(q.x+dx,q.y+2,q.z+dz);ceiling=math.min(ceiling,ch-q.y)
 end end
 return {position=q,mario={x=m.pos.x,y=m.pos.y,z=m.pos.z},action=m.action,
  wallHits=wallCount,ceilingGap=ceiling,footprintSupported=supported,
  boardSameRoot=originalBoard and math.abs(originalBoard.oPosX-q.x)<.1 and math.abs(originalBoard.oPosY-q.y)<.1 and math.abs(originalBoard.oPosZ-q.z)<.1,
  passed=wallCount==0 and ceiling>=212 and supported}
end
emit('policy',{nativeWarps=true,companionPositionWrites=false,physicsOverrides=false,saveIsolation=true,
 limits='Actual collision and native painting-exit nodes; diagnostic A closes isolated exit menus. Not rendered/controller-device acceptance or an actual star collection.'})
hook_event(HOOK_BEFORE_MARIO_UPDATE,function(m)
 if not qa.done and m.playerIndex==0 and qa.sceneTick%15==0 then
  -- Native input only, to acknowledge the isolated course-done screen.
  m.controller.buttonPressed=m.controller.buttonPressed | A_BUTTON
 end
end)
hook_event(HOOK_UPDATE,function()
 if qa.done then return end
 qa.tick=qa.tick+1
 if qa.tick<120 then return end
 local c=qa.cases[qa.index]
 if not c then qa.done=true;emit('COMPLETE',{results=qa.results});return end
 local m,np=gMarioStates[0],gNetworkPlayers[0]
 if not m or not m.area or not np then return end
 if not qa.requested then
  qa.requested=true;qa.sceneTick=0;qa.seen=nil;qa.transitionFrames=0;qa.premature=0
  emit('warp',{case=c.name,level=c.level,area=c.area,node=c.node})
  if c.node then warp_to_warpnode(c.level,c.area,1,c.node) else warp_to_level(c.level,c.area,1) end
  return
 end
 if np.currLevelNum~=c.level or np.currAreaIndex~=c.area then return end
 qa.sceneTick=qa.sceneTick+1
 if (m.action & ACT_GROUP_MASK)==ACT_GROUP_CUTSCENE then
  qa.transitionFrames=qa.transitionFrames+1
  if jimmie then qa.premature=qa.premature+1 end
 end
 if not qa.seen and jimmie and originalBoard and jimmie.activeFlags~=0 and originalBoard.activeFlags~=0 then
  qa.seen=audit(jimmie,m);qa.seen.atFrame=qa.sceneTick
  emit('spawn',qa.seen)
 end
 if qa.sceneTick%120==0 then emit('status',{case=c.name,frame=qa.sceneTick,action=m.action,reason=companionSpawn.lastReason,
  pos={x=m.pos.x,y=m.pos.y,z=m.pos.z},floor=m.floorHeight,vy=m.vel.y,mode=get_current_play_mode()}) end
 if (qa.seen and qa.sceneTick>=qa.seen.atFrame+20) or qa.sceneTick>=720 then
  local result={case=c.name,level=c.level,area=c.area,node=c.node,spawn=qa.seen,transitionFrames=qa.transitionFrames,
   prematureSpawns=qa.premature,passed=qa.seen~=nil and qa.seen.passed and qa.seen.boardSameRoot and qa.premature==0,
   lastReason=companionSpawn.lastReason,frames=qa.sceneTick}
  qa.results[#qa.results+1]=result;emit('case-end',result)
  qa.index=qa.index+1;qa.requested=false
 end
end)
