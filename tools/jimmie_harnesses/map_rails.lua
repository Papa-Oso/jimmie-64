-- Private exact-engine map-load diagnostics. No rail tasks, actor state, RNG,
-- physics or eligibility writes. Warps only select native test scenes.
local Visible=require('skate_visible_rails')
local qa={tick=0,index=1,settle=0,results={},done=false,scenes={
 {name='grounds_first',level=LEVEL_CASTLE_GROUNDS,area=1},
 {name='castle_first',level=LEVEL_CASTLE,area=1},
 {name='castle_basement',level=LEVEL_CASTLE,area=2},
 {name='castle_upper',level=LEVEL_CASTLE,area=3},
 {name='grounds_return',level=LEVEL_CASTLE_GROUNDS,area=1}}}
local function emit(kind,data)print('[map-rails] '..kind..' '..Personality.json(data))end
local function finite(n)return type(n)=='number' and n==n and math.abs(n)<1e8 end
local function numericOnly(t)
 if type(t)=='number' then return finite(t) end
 if type(t)=='string' or type(t)=='boolean' then return true end
 if type(t)~='table' then return false end
 for k,v in pairs(t)do if not numericOnly(k) or not numericOnly(v) then return false end end
 return true
end
local function midpoint(s)
 return {x=(s.a.x+s.b.x)*.5,y=(s.a.y+s.b.y)*.5,z=(s.a.z+s.b.z)*.5}
end
local function readScene(c)
 local world=skateOpportunity and skateOpportunity.world
 local r=world and world.surfaceRails
 if not r then return {case=c.name,error='capture-unavailable'} end
 local scene=smlua_collision_util_get_current_terrain_collision()
 local out={case=c.name,level=c.level,area=c.area,generation=r.generation,
  segmentCount=#r.segments,stats={surfaces=r.stats.surfaces,candidates=r.stats.candidates,rejected=r.stats.rejected},
  captureError=r.error,numericCopiesOnly=numericOnly(r.segments),sceneCurrent=scene~=nil and scene==r.scene,
  visibleSegments=0,matchedLoadedSegments=0,wrongAreaRejected=true,priorSceneRejected=true,
  priorGenerationInvalidated=not qa.previous or r.generation>qa.previous.generation,
  examples={},extraNativeGeometryQueries=0}
 for _,map in ipairs(Visible.maps)do
  if _G[map.level]==c.level and map.area==c.area then out.visibleSegments=#map.segments end
 end
 -- Real captured numeric floor segments through the unmodified matching method.
 -- These diagnostics never call a probe or supply movement authority.
 for _,s in ipairs(r.segments)do
  local p=midpoint(s)
  local v=r:visible(p,s.dx,s.dz,false)
  if v then
   out.matchedLoadedSegments=out.matchedLoadedSegments+1
   if #out.examples<4 then out.examples[#out.examples+1]={point=p,visualLevel=v.level,visualArea=v.area,seed=s.seed} end
   if _G[v.level]~=c.level or v.area~=c.area then out.wrongAreaRejected=false end
  end
 end
 -- Deliberately invalid AREA in a private reader clone, never gNetworkPlayers.
 -- Distinct from the actual native area transitions below.
 local fakeG=setmetatable({gNetworkPlayers={[0]={currLevelNum=c.level,currAreaIndex=999}}},{__index=_G})
 local wrong=setmetatable({g=fakeG,bound=r.bound,scene=r.scene,segments=r.segments,limit=r.limit,error=r.error},getmetatable(r))
 out.wrongAreaFixtureRejected=true
 for _,s in ipairs(r.segments)do
  local p=midpoint(s)
  if wrong:visible(p,s.dx,s.dz,false)~=nil or #wrong:near(p,p,s.dx,s.dz,get_global_timer())~=0 then
   out.wrongAreaFixtureRejected=false;break
  end
 end
 if qa.previous then
  local old=qa.previous.reader
  local p=qa.previous.point or {x=0,y=0,z=0}
  out.priorSceneChanged=old.scene~=scene
  out.priorSceneRejected=old:visible(p,1,0,false)==nil and #old:near(p,p,1,0,get_global_timer())==0
 end
 -- Retain only a terrain identity token and numeric copies already owned by the
 -- runtime, never Surface/object userdata. clear() replaces segment tables.
 qa.previous={generation=r.generation,point=r.segments[1] and midpoint(r.segments[1]),
  reader=setmetatable({g=_G,bound=true,scene=r.scene,segments=r.segments,limit=r.limit},getmetatable(r))}
 out.passed=out.numericCopiesOnly and out.sceneCurrent and out.wrongAreaRejected and out.wrongAreaFixtureRejected
  and out.priorSceneRejected and out.priorGenerationInvalidated and not out.captureError
  and (out.visibleSegments==0 or out.matchedLoadedSegments>0)
 return out
end
emit('policy',{nativeMapTransitions=true,numericCaptureDiagnostics=true,seededRail=false,
 physicsOverrides=false,outcomeOverrides=false,wrongAreaFixture='private reader clone, no network state edits',
 limits='Discovery and invalidation only; not successful autonomous grinds or rendered/controller acceptance'})
hook_event(HOOK_UPDATE,function()
 if qa.done then return end
 qa.tick=qa.tick+1
 if qa.tick>2400 then qa.done=true;emit('failure',{reason='bounded-timeout'});return end
 local c=qa.scenes[qa.index]
 if not c then qa.done=true;emit('COMPLETE',{results=qa.results});return end
 local m,np=gMarioStates[0],gNetworkPlayers[0]
 if not m or not np or not m.area or m.action==0 then return end
 if np.currLevelNum~=c.level or np.currAreaIndex~=c.area then
  if not qa.requested and qa.tick>=120 then
   qa.requested=true;qa.settle=0
   emit('warp',{case=c.name,level=c.level,area=c.area})
   warp_to_level(c.level,c.area,0)
  end
  return
 end
 qa.requested=false;qa.settle=qa.settle+1
 if qa.settle<45 then return end
 local result=readScene(c);qa.results[#qa.results+1]=result;emit('case-end',result)
 qa.index=qa.index+1;qa.settle=0
end)
