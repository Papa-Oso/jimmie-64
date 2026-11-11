-- STAGED ONLY. Read-only finite native checks for instantaneous cosmetic rejoin.
-- No hooks on load, position writes, motion owner, flight, or persisted Surface.
-- Proposal is same-frame only, not a continuous geometry certificate.
local R={};R.__index=R
R.PROFILE={id='original-idle-frame0-scale062',pose='original_idle_frame0',scale=.62,radius=60,supportRadius=60,top=202,margin=4,
 source='independently-decoded-original-stock-idle-frame0'}
local function finite(n) return type(n)=='number' and n==n and math.abs(n)<1e8 end
local function integer(n) return finite(n) and n%1==0 end
local function point(p) return p and finite(p.x) and finite(p.y) and finite(p.z) end
local function copy(p) return {x=p.x,y=p.y,z=p.z} end
local function fail(why) return nil,why end
local function snap(s)
 if s==nil then return nil end
 local n,a,b,c=s.normal,s.vertex1,s.vertex2,s.vertex3
 if not point(n) or not point(a) or not point(b) or not point(c) then return nil end
 return {kind=s.type,flags=s.flags,pool=s.poolType,owned=s.object~=nil,n=copy(n),v={copy(a),copy(b),copy(c)}}
end
local function flat_static(g,s,allowed)
 if not s or s.pool~=g.SURFACE_POOL_STATIC or s.owned or not integer(s.flags) then return false end
 if (s.flags & (g.SURFACE_FLAG_DYNAMIC | g.SURFACE_FLAG_INTANGIBLE))~=0 then return false end
 return allowed[s.kind]==true and math.abs(s.n.x)<=.001 and math.abs(s.n.z)<=.001 and s.n.y>=.9999 and s.n.y<=1.0001
end
local function contains(s,p,r)
 -- Full square on ONE triangle; no corner-sample-only support inference.
 local a,b,c=s.v[1],s.v[2],s.v[3]
 local area=(b.x-a.x)*(c.z-a.z)-(b.z-a.z)*(c.x-a.x)
 if math.abs(area)<1 then return false end
 local sign=area>0 and 1 or -1
 for _,dx in ipairs({-r,r}) do for _,dz in ipairs({-r,r}) do
  for i,u in ipairs(s.v) do local v=s.v[i%3+1]
   if ((v.x-u.x)*(p.z+dz-u.z)-(v.z-u.z)*(p.x+dx-u.x))*sign<1e-5 then return false end
  end
 end end
 return true
end
local function same_surface(a,b)
 if not a or not b or a.kind~=b.kind or a.flags~=b.flags or a.pool~=b.pool or a.owned~=b.owned then return false end
 for _,k in ipairs({'x','y','z'}) do
  if a.n[k]~=b.n[k] then return false end
  for i=1,3 do if a.v[i][k]~=b.v[i][k] then return false end end
 end
 return true
end
function R.new(g)
 g=g or _G;local self=setmetatable({g=g,epoch=0,allowed={}},R)
 for _,name in ipairs({'SURFACE_DEFAULT','SURFACE_HARD','SURFACE_NOT_SLIPPERY','SURFACE_HARD_NOT_SLIPPERY','SURFACE_NO_CAM_COLLISION'}) do
  if integer(g[name]) then self.allowed[g[name]]=true end
 end
 return self
end
-- Host calls on CLEAR_AREAS, LEVEL_INIT, and same-level area changes.
-- Explicit epoch catches reloading the SAME terrain pointer.
function R:invalidate() self.epoch=self.epoch+1 end
function R:stamp()
 local g=self.g;local np=g.gNetworkPlayers and g.gNetworkPlayers[0]
 local terrain=g.smlua_collision_util_get_current_terrain_collision()
 if not np or terrain==nil then return nil end
 local f=g.get_global_timer();if not integer(f) then return nil end
 return {epoch=self.epoch,frame=f,terrain=terrain,level=np.currLevelNum,area=np.currAreaIndex,act=np.currActNum}
end
function R:fresh(s)
 local n=self:stamp()
 return n and s and n.epoch==s.epoch and n.frame==s.frame and n.terrain==s.terrain and
  n.level==s.level and n.area==s.area and n.act==s.act
end
function R:_propose(candidate,ctx)
 local g,p=self.g,R.PROFILE
 for _,name in ipairs({'find_floor','find_ceil','find_water_level','find_poison_gas_level',
  'resolve_and_return_wall_collisions','get_global_timer','smlua_collision_util_get_current_terrain_collision',
  'obj_get_first','obj_get_next','clock_elapsed_f64'}) do
  if type(g[name])~='function' then return fail('missing-api:'..name) end
 end
 for _,name in ipairs({'SURFACE_POOL_STATIC','SURFACE_FLAG_DYNAMIC','SURFACE_FLAG_INTANGIBLE','NUM_OBJ_LISTS','MAX_PLAYERS'}) do
  if not integer(g[name]) then return fail('missing-constant:'..name) end
 end
 if g.NUM_OBJ_LISTS<1 or g.NUM_OBJ_LISTS>32 or g.MAX_PLAYERS<1 or g.MAX_PLAYERS>64 then return fail('unsupported-engine-limits') end
 if not point(candidate) or type(ctx)~='table' then return fail('invalid-input') end
 if ctx.profileId~=p.id or ctx.pose~=p.pose or ctx.scale~=p.scale or ctx.pitch~=0 or ctx.roll~=0 then return fail('unverified-pose-profile') end
 if ctx.allowNativeFiniteProbes~=true then return fail('finite-probe-contract-not-accepted') end
 local stamp=self:stamp();if not stamp or not self:fresh(ctx.stamp) then return fail('stale-scene-or-frame') end
 local started=g.clock_elapsed_f64();if not finite(started) then return fail('invalid-clock') end
 local function budget() local t=g.clock_elapsed_f64();return finite(t) and t>=started and t-started<=.006 end
 -- Ordinary SM64 region and all signed-16-bit query coordinates are bounded.
 if math.abs(candidate.x)>7800 or math.abs(candidate.z)>7800 or candidate.y< -15000 or candidate.y>15000 then return fail('coordinate-bound') end
 local m=g.gMarioStates and g.gMarioStates[0]
 if not m or not point(m.pos) or not point(m.vel) or not finite(m.floorHeight) then return fail('missing-player') end
 if math.abs(m.pos.x)>7900 or math.abs(m.pos.z)>7900 or math.abs(m.pos.y)>15000 then return fail('player-coordinate-bound') end
 if m.vel.y~=0 or math.abs(m.pos.y-m.floorHeight)>2 then return fail('player-not-on-stable-floor') end
 local dx,dz=candidate.x-m.pos.x,candidate.z-m.pos.z;local dist=math.sqrt(dx*dx+dz*dz)
 if dist<190 or dist>420 or math.abs(candidate.y-m.floorHeight)>64 then return fail('outside-near-player-band') end
 local mh,ms=g.find_floor(m.pos.x,m.pos.y+20,m.pos.z);local marioFloor=snap(ms);ms=nil
 if not finite(mh) or math.abs(mh-m.floorHeight)>1 or not flat_static(g,marioFloor,self.allowed) then return fail('player-floor-not-static-dry-type') end
 -- Integral x/z survive native Vec3f write-back exactly; no false wall from rounding.
 local cx,cz=math.floor(candidate.x+.5),math.floor(candidate.z+.5)
 local h,s=g.find_floor(cx,mh+32,cz);local support=snap(s);s=nil
 if not finite(h) or math.abs(h-mh)>32 or not flat_static(g,support,self.allowed) then return fail('candidate-floor-not-static-flat') end
 local q={x=cx,y=h,z=cz}
 if not contains(support,q,p.supportRadius+p.margin) then return fail('footprint-crosses-triangle-edge') end
 -- Finite body-footprint checks, NOT proof against tiny interior hazards/ceilings.
 local r=p.radius+p.margin
 local offsets={{0,0},{r,0},{-r,0},{0,r},{0,-r},{r,r},{r,-r},{-r,r},{-r,-r},
  {r/2,r/2},{r/2,-r/2},{-r/2,r/2},{-r/2,-r/2}}
 for _,o in ipairs(offsets) do
  if not budget() then return fail('proof-time-budget') end
  local x,z=q.x+o[1],q.z+o[2]
  local water=g.find_water_level(x,z);local gas=g.find_poison_gas_level(x,z)
  if not finite(water) or not finite(gas) then return fail('missing-hazard-level') end
  if water>=h-p.margin or gas>=h-p.margin then return fail('water-or-gas') end
  local ch,cs=g.find_ceil(x,h+2,z)
  if not finite(ch) or ch<h+p.top+p.margin then return fail('ceiling-clearance') end
  if cs~=nil and not snap(cs) then return fail('unreadable-ceiling') end;cs=nil
 end
 -- Native helper mutates a NEW Lua table, never an actor or engine position.
 for _,y in ipairs({4,16,40,80,120,160,202}) do
  local temp={x=q.x,y=q.y,z=q.z};local wall=g.resolve_and_return_wall_collisions(temp,y,r)
  if wall~=nil or not point(temp) or temp.x~=q.x or temp.y~=q.y or temp.z~=q.z then return fail('wall-clearance') end
 end
 -- gMarioStates/gNetworkPlayers are native indexable tables, no Surface retained.
 if not g.gMarioStates or not g.gNetworkPlayers then return fail('missing-player-inventory') end
 for i=0,g.MAX_PLAYERS-1 do
  local np,player=g.gNetworkPlayers[i],g.gMarioStates[i]
  if np and (i==0 or np.connected) and np.currLevelNum==stamp.level and np.currAreaIndex==stamp.area then
   if not player or not point(player.pos) then return fail('unreadable-connected-player') end
   local x,z=q.x-player.pos.x,q.z-player.pos.z
   if x*x+z*z<(r+70)^2 and math.abs(q.y-player.pos.y)<p.top+160 then return fail('player-separation') end
  end
 end
 local count=0
 for list=0,g.NUM_OBJ_LISTS-1 do
  local obj=g.obj_get_first(list)
  while obj~=nil do
   count=count+1;if count>1024 or not budget() then return fail('actor-inventory-budget') end
   if not (ctx.ownedObjects and ctx.ownedObjects[obj]==true) then
    local ox,oy,oz=obj.oPosX,obj.oPosY,obj.oPosZ
    if not finite(ox) or not finite(oy) or not finite(oz) then return fail('unreadable-object') end
    local rr,hh=obj.hitboxRadius,obj.hitboxHeight
    if not finite(rr) or rr<0 or not finite(hh) or hh<0 then return fail('unreadable-object-bounds') end
    -- Native hitboxes plus buffer, not a claim about every model's visual mesh.
    rr=math.max(rr,finite(obj.hurtboxRadius) and obj.hurtboxRadius or 0,70)
    hh=math.max(hh,finite(obj.hurtboxHeight) and obj.hurtboxHeight or 0,200)
    if (q.x-ox)^2+(q.z-oz)^2<(r+rr+16)^2 and q.y+p.top+16>oy and q.y<oy+hh+16 then return fail('object-separation') end
   end
   obj=g.obj_get_next(obj)
  end
 end
 local h2,s2=g.find_floor(q.x,h+32,q.z);local final=snap(s2);s2=nil
 if not finite(h2) or h2~=h or not same_surface(support,final) then return fail('floor-changed') end
 if not self:fresh(stamp) then return fail('scene-or-frame-changed') end
 if not budget() then return fail('proof-time-budget') end
 return {position=q,stamp=stamp,profileId=p.id,pose=p.pose,pitch=0,roll=0,proposalOnly=true,
  method='native-finite-placement-checks',continuousClearance=false,support='single-static-triangle-full-wheel-square',actorsChecked=count,
  marioSupport={height=mh,normal=copy(marioFloor.n),kind=marioFloor.kind,triangle=marioFloor.v},
  destinationSupport={height=h,normal=copy(support.n),kind=support.kind,triangle=support.v}}
end
function R:propose(candidate,ctx)
 local ok,result,reason=pcall(self._propose,self,candidate,ctx)
 if not ok then return nil,'native-read-failed' end
 return result,reason
end
return R
