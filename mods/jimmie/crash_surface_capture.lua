-- STAGED ONLY. Conservative static landing certificates, not pathfinding.
-- Full-square support by one triangle or a bounded coplanar triangle union. Whole-body AABB vs every captured
-- static triangle (walls, sloped sheets and ceilings), not NPC-sensitive walls.
-- Derived from the existing static_landing.lua: only optional proof-time budget
-- checks and bounded flat support union added below. Source hash is recorded in verification.json.
local A={};A.__index=A
function A:within_budget()
 if not self.deadline then return true end
 local ok,t=pcall(self.now)
 return ok and type(t)=='number' and t==t and t<=self.deadline
end
A.DEFAULTS={radius=116,supportRadius=116,margin=4,top=208,floorTolerance=1.0,maxSlope=.001,
 maxTriangles=16384,maxSurfaceRefs=32768,maxCandidates=24,maxSearchFloors=16384,nearMario=900,
 belowMario=360,aboveMario=180,maxTravel=6000,maxClearanceChecks=16384}
-- A moving player can cover 1,800-2,600 units during a smooth recovery arc.
-- Probe actual static support along that prediction, never invent a landing.
A.DEFAULTS.predictionSeconds=2
A.DEFAULTS.maxLead=2200
-- Optional HELD idle_00 materialization profile: 46 contains the measured
-- wheel contact radius <=45.20 at any yaw. Body/hazard radius stays116 and
-- headroom360 reserves later legacy animation. Host must deliberately hold
-- the existing idle frame, pitch/roll zero; default support stays116.
A.PROFILES={steady_idle={radius=116,supportRadius=46,top=360,margin=4}}
local function finite(x) return type(x)=='number' and x==x and math.abs(x)<1e8 end
local function point(p) return p and finite(p.x) and finite(p.y) and finite(p.z) end
local function copy(p) return {x=p.x,y=p.y,z=p.z} end
local function clamp(x,a,b) return math.max(a,math.min(b,x)) end
local function horizontal(a,b) return math.sqrt((a.x-b.x)^2+(a.z-b.z)^2) end
local function distance(a,b) return math.sqrt((a.x-b.x)^2+(a.y-b.y)^2+(a.z-b.z)^2) end
local function cross(a,b,c) return (b.x-a.x)*(c.z-a.z)-(b.z-a.z)*(c.x-a.x) end
local function clip(poly,axis,limit,above)
 local out={}
 for i,a in ipairs(poly) do
  local b=poly[i%#poly+1];local ina=above and a[axis]>=limit or not above and a[axis]<=limit
  local inb=above and b[axis]>=limit or not above and b[axis]<=limit
  if ina then out[#out+1]=a end
  if ina~=inb then
   local t=(limit-a[axis])/(b[axis]-a[axis])
   out[#out+1]={x=a.x+(b.x-a.x)*t,y=a.y+(b.y-a.y)*t,z=a.z+(b.z-a.z)*t}
  end
 end
 return out
end
local function intersects_box(tri,x0,y0,z0,x1,y1,z1)
 if tri.maxX<x0 or tri.minX>x1 or tri.maxY<y0 or tri.minY>y1 or tri.maxZ<z0 or tri.minZ>z1 then return false end
 local p=tri.v
 for _,k in ipairs({{'x',x0,true},{'x',x1,false},{'y',y0,true},{'y',y1,false},{'z',z0,true},{'z',z1,false}}) do
  p=clip(p,k[1],k[2],k[3]);if #p==0 then return false end
 end
 return #p>0
end
local function floor_y(tri,x,z)
 return tri.v[1].y-(tri.n.x*(x-tri.v[1].x)+tri.n.z*(z-tri.v[1].z))/tri.n.y
end
local function contained(tri,x,z,r)
 local sign=tri.area>0 and 1 or -1
 for _,dx in ipairs({-r,r}) do for _,dz in ipairs({-r,r}) do
  local p={x=x+dx,z=z+dz}
  for i,a in ipairs(tri.v) do
   if cross(a,tri.v[i%3+1],p)*sign<1e-6 then return false end
  end
 end end
 return true
end
local function signature(s)
 local v={s.vertex1,s.vertex2,s.vertex3}
 if not point(s.normal) or not point(v[1]) or not point(v[2]) or not point(v[3]) then return nil end
 local p={tostring(s.type),tostring(s.flags or 0),s.normal.x,s.normal.y,s.normal.z}
 for _,a in ipairs(v) do p[#p+1]=a.x;p[#p+1]=a.y;p[#p+1]=a.z end
 return table.concat(p,':')
end
function A.new(api,options)
 local self=setmetatable({api=api or {},c={},allowed={}},A)
 for k,v in pairs(A.DEFAULTS) do
  local supplied=(options or {})[k]
  if k=='supportRadius' and supplied==nil then supplied=(options or {}).radius end
  self.c[k]=supplied or v;assert(finite(self.c[k]) and self.c[k]>0,k)
 end
 assert(self.c.supportRadius<=self.c.radius,'support larger than body')
 -- Explicit allowlist. Unknown/special/slippery/death/lava/quicksand/wind/warp
 -- surface types never become recovery support by default.
 for _,n in ipairs({'SURFACE_DEFAULT','SURFACE_HARD','SURFACE_NOT_SLIPPERY','SURFACE_HARD_NOT_SLIPPERY','SURFACE_NO_CAM_COLLISION'}) do
  local value=self.api[n]
  if finite(value) then self.allowed[value]=true end
 end
 self:clear(nil)
 return self
end
function A:clear(scene)
 self.scene=scene;self.generation=(self.generation or 0)+1;self.revision=0
 self.tris={};self.byKey={};self.references={};self.seenReferences={};self.complete=false;self.error=nil;self.quietRevision=nil;self.quietTicks=0;self.engineCaptureEligible=false;self.stats={queries=0,checks=0,searches=0}
end
function A:track_reference(surface,tri)
 if self.seenReferences[surface] then return true end
 if #self.references>=self.c.maxSurfaceRefs then self.error='reference-budget';return false end
 self.references[#self.references+1]={source=surface,tri=tri}
 self.seenReferences[surface]=true
 return true
end
function A:add_surface(surface,dynamic,scene)
 if scene~=self.scene then self:clear(scene) end
 if not surface or dynamic==true or surface.object~=nil then return false end
 local flags=surface.flags or 0
 if not finite(flags) or flags%1~=0 then self.error='invalid-flags';return false end
 local dynamicFlag=self.api.SURFACE_FLAG_DYNAMIC
 local intangible=self.api.SURFACE_FLAG_INTANGIBLE
 if dynamicFlag and (flags & dynamicFlag)~=0 then return false end
 if intangible and (flags & intangible)~=0 then return false end
 if (self.api.SURFACE_CAMERA_BOUNDARY and surface.type==self.api.SURFACE_CAMERA_BOUNDARY) or
  (self.api.SURFACE_RAYCAST and surface.type==self.api.SURFACE_RAYCAST) then return false end
 local key=signature(surface)
 if not key then self.error='invalid-surface';return false end
 if self.byKey[key] then
  if not self.seenReferences[surface] then
   self:track_reference(surface,self.byKey[key]);self.revision=self.revision+1;self.complete=false
  end
  return false
 end
 if #self.tris>=self.c.maxTriangles then self.error='capture-budget';return false end
 local v={copy(surface.vertex1),copy(surface.vertex2),copy(surface.vertex3)}
 local n=copy(surface.normal)
 local norm=math.sqrt(n.x*n.x+n.y*n.y+n.z*n.z)
 if norm<.99 or norm>1.01 then self.error='invalid-normal';return false end
 local e1={x=v[2].x-v[1].x,y=v[2].y-v[1].y,z=v[2].z-v[1].z}
 local e2={x=v[3].x-v[1].x,y=v[3].y-v[1].y,z=v[3].z-v[1].z}
 local cx,cy,cz=e1.y*e2.z-e1.z*e2.y,e1.z*e2.x-e1.x*e2.z,e1.x*e2.y-e1.y*e2.x
 local area3=math.sqrt(cx*cx+cy*cy+cz*cz)
 if area3<1e-5 or math.abs((cx*n.x+cy*n.y+cz*n.z)/area3)<.9999 then self.error='inconsistent-normal';return false end
 local tri={v=v,n=n,key=key,kind=surface.type,captureFlags=flags,source=surface,area=cross(v[1],v[2],v[3]),
  minX=math.min(v[1].x,v[2].x,v[3].x),maxX=math.max(v[1].x,v[2].x,v[3].x),
  minY=math.min(v[1].y,v[2].y,v[3].y),maxY=math.max(v[1].y,v[2].y,v[3].y),
  minZ=math.min(v[1].z,v[2].z,v[3].z),maxZ=math.max(v[1].z,v[2].z,v[3].z)}
 tri.support=self.allowed[tri.kind]==true and n.y>0 and math.abs(n.x)<=self.c.maxSlope and math.abs(n.z)<=self.c.maxSlope and math.abs(tri.area)>1
 if not self:track_reference(surface,tri) then return false end
 self.tris[#self.tris+1]=tri;self.byKey[key]=tri;self.revision=self.revision+1
 self.complete=false
 return true
end
-- Only signal after the current scene's complete static surface load.
function A:finish(scene)
 if scene~=self.scene then return false end
 if self.bound and not self.engineCaptureEligible then return false end
 self.complete=#self.tris>0 and not self.error
 return self.complete
end
function A:sync(ctx)
 if type(self.api.scene)=='function' then
  local ok,scene=pcall(self.api.scene)
  if not ok or scene==nil then return false,'missing-scene' end
  if scene~=self.scene then self:clear(scene) end
 end
 if self.scene~=ctx.scene then return false,'wrong-scene' end
 if self.error then return false,self.error end
 if not self.complete then return false,'incomplete-capture' end
 return true
end
-- Convenience for composition. Consumers must still compare stamps before and
-- after a proof and treat tris/byKey as read-only numeric capture data.
function A:stamp(ctx)
 local ready,reason=self:sync(ctx)
 return {scene=self.scene,generation=self.generation,revision=self.revision,ready=ready,
  reason=reason,radius=self.c.radius,supportRadius=self.c.supportRadius,top=self.c.top}
end
local function query(api,name,...)
 if type(api[name])~='function' then return nil,nil,'missing-'..name end
 local ok,a,b=pcall(api[name],...)
 if not ok then return nil,nil,'failed-'..name end
 return a,b
end
-- move_surface() deliberately bypasses ADD_SURFACE in the engine. Keep live
-- references, including geometry duplicates, and reject a changed/deleted
-- userdata without attempting to reconstruct a partial capture. X_PROJECTION
-- is engine-derived AFTER the add hook and is the only ignored flag bit.
function A:references_current()
 self.proofPhase='live-references';self.stats.referenceScans=(self.stats.referenceScans or 0)+1
 local projection=self.api.SURFACE_FLAG_X_PROJECTION or 8
 -- One protected scan, no per-reference closures/temporary vertex arrays.
 -- Equality to already-validated finite snapshots also rejects NaN/nil values.
 local ok,matching=pcall(function()
  for index,record in ipairs(self.references) do
   if index%32==1 and not self:within_budget() then return false end
   local source,t=record.source,record.tri
   local flags=source.flags or 0
   if source.object~=nil or source.type~=t.kind or not finite(flags) or flags%1~=0 or
    (flags & ~projection)~=(t.captureFlags & ~projection) then return false end
   local n=source.normal
   if n.x~=t.n.x or n.y~=t.n.y or n.z~=t.n.z then return false end
   local a,b,c=source.vertex1,source.vertex2,source.vertex3
   local x,y,z=t.v[1],t.v[2],t.v[3]
   if a.x~=x.x or a.y~=x.y or a.z~=x.z or b.x~=y.x or b.y~=y.y or b.z~=y.z or
    c.x~=z.x or c.y~=z.y or c.z~=z.z then return false end
  end
  return true
 end)
 if not ok or not matching then
  if not self:within_budget() then return false end
  self.error='static-geometry-changed';self.complete=false;return false
 end
 return true
end
-- Subtract each convex support triangle from the uncovered footprint. Unlike
-- a convex hull, corner tests or summed triangle areas, this preserves holes and
-- overlapping triangles do not count twice. All candidates must be exactly flat,
-- safe, coplanar captured surfaces. Bound both work and intermediate fragments.
local function area2(poly)
 local sum=0
 for i,a in ipairs(poly) do local b=poly[i%#poly+1];sum=sum+a.x*b.z-b.x*a.z end
 return math.abs(sum)
end
local function edge_clip(poly,a,b,sign,inside)
 local out={}
 for i,p in ipairs(poly) do
  local q=poly[i%#poly+1];local dp=cross(a,b,p)*sign;local dq=cross(a,b,q)*sign
  local ip=inside and dp>=0 or not inside and dp<=0
  local iq=inside and dq>=0 or not inside and dq<=0
  if ip then out[#out+1]=p end
  if ip~=iq then local t=dp/(dp-dq);out[#out+1]={x=p.x+(q.x-p.x)*t,z=p.z+(q.z-p.z)*t} end
 end
 return out
end
function A:covered_flat_square(tri,x,y,z,r)
 local diagnostic={method='triangle-union',candidates=0,fragments=1,uncoveredArea=4*r*r}
 self.supportDiagnostics=diagnostic
 local pieces={{{x=x-r,z=z-r},{x=x+r,z=z-r},{x=x+r,z=z+r},{x=x-r,z=z+r}}}
 local function subtract(t)
  if not t.support or math.abs(t.n.x)>1e-8 or math.abs(t.n.z)>1e-8 or math.abs(t.minY-y)>1e-7 or math.abs(t.maxY-y)>1e-7 or t.maxX<x-r or t.minX>x+r or t.maxZ<z-r or t.minZ>z+r then return true end
  diagnostic.candidates=diagnostic.candidates+1
  if diagnostic.candidates>128 then return false,'support-candidate-budget' end
  local result={};local sign=t.area>0 and 1 or -1
  for _,piece in ipairs(pieces) do
   if not self:within_budget() then return false,'proof-time-budget' end
   local current=piece
   for i,a in ipairs(t.v) do
    if #current<3 then break end
    local b=t.v[i%3+1];local outside=edge_clip(current,a,b,sign,false)
    -- Floating-point clipping may leave zero-width boundaries. A sub-nanounit
    -- area tolerance removes only arithmetic dust; the support margin is4units.
    if #outside>=3 and area2(outside)>1e-8 then result[#result+1]=outside end
    if #result>64 then return false,'support-fragment-budget' end
    current=edge_clip(current,a,b,sign,true)
   end
  end
  pieces=result;diagnostic.fragments=#pieces
  diagnostic.uncoveredArea=0;for _,piece in ipairs(pieces) do diagnostic.uncoveredArea=diagnostic.uncoveredArea+area2(piece)/2 end
  return true
 end
 local ok,why=subtract(tri);if not ok then return false,why end
 for index,t in ipairs(self.tris) do
  if #pieces==0 then return true end
  if index%32==1 and not self:within_budget() then return false,'proof-time-budget' end
  if t~=tri then ok,why=subtract(t);if not ok then return false,why end end
 end
 return #pieces==0,'insufficient-footprint'
end
function A:validate(target,ctx,options)
 self.stats.queries=self.stats.queries+1
 local ok,reason=self:sync(ctx);if not ok then return nil,reason end
 if not point(target) or target.scene~=self.scene or target.generation~=self.generation or target.revision~=self.revision then return nil,'stale-target' end
 local tri=self.byKey[target.key]
 if not tri or not tri.support then return nil,'missing-static-support' end
 local x,y,z=target.x,target.y,target.z;local r=self.c.radius+self.c.margin
 local sr=self.c.supportRadius+self.c.margin
 self.proofPhase='support-coverage'
 if contained(tri,x,z,sr) then self.supportDiagnostics={method='single-triangle',candidates=1,fragments=0,uncoveredArea=0}
 else
  local covered,why=self:covered_flat_square(tri,x,y,z,sr)
  if not covered then return nil,why end
 end
 local center=floor_y(tri,x,z)
 if math.abs(center-y)>.001 then return nil,'changed-height' end
 -- Current engine root query detects removal/replacement of captured support.
 -- Object-owned floors reject, never mask an unsafe static destination.
 self.proofPhase='current-floor'
 local h,s,err=query(self.api,'floor',x,y+8,z)
 if err or not finite(h) or math.abs(h-y)>self.c.floorTolerance or not s then return nil,err or 'support-not-current' end
 if s.object~=nil or signature(s)~=tri.key then return nil,'support-replaced' end
 self.proofPhase='hazards'
 local water,_,waterErr=query(self.api,'water',x,z)
 local gas,__,gasErr=query(self.api,'gas',x,z)
 if waterErr or gasErr or not finite(water) or not finite(gas) then return nil,waterErr or gasErr or 'missing-hazard-level' end
 -- SM64/Jimmie hazard contact is root based. This does not certify that every
 -- rendered vertex is dry; full footprint support/body geometry IS certified.
 if water>y-4 then return nil,'water-at-contact' end
 if gas>y-4 then return nil,'gas-at-contact' end
 local supportHigh=-math.huge
 for _,dx in ipairs({-sr,sr}) do for _,dz in ipairs({-sr,sr}) do supportHigh=math.max(supportHigh,floor_y(tri,x+dx,z+dz)) end end
 if supportHigh-y>self.c.floorTolerance then return nil,'support-too-sloped' end
 self.proofPhase='static-obstructions'
 local checks=0
 for _,other in ipairs(self.tris) do
  checks=checks+1
  if checks%32==1 and not self:within_budget() then return nil,'proof-time-budget' end
  if checks>self.c.maxClearanceChecks then return nil,'clearance-budget' end
  if other~=tri then
   -- Every static triangle class is checked. A thin ceiling/steep floor sheet
   -- is not silently lost by a wall-normal filter. AABB is conservative.
   if intersects_box(other,x-r,supportHigh+1,z-r,x+r,y+self.c.top+2,z+r) then return nil,'body-obstruction' end
   if not self.allowed[other.kind] and intersects_box(other,x-r,y-2,z-r,x+r,y+2,z+r) then return nil,'hazard-overlap' end
  end
 end
 self.stats.checks=self.stats.checks+checks
 -- Rejected candidates grant no authority, so their obsolete snapshot can only
 -- cause a conservative rejection. A potentially successful certificate must
 -- scan ALL live references here, after floor/water/gas callbacks and before
 -- the final stamp check. This avoids repeated full scans for blocked choices.
 -- A synchronous caller may build multiple PROVISIONAL region certificates,
 -- then perform ONE shared references_current() and final stamp check after ALL
 -- callbacks. A provisional certificate must never authorize rendering alone.
 if not (options and options.provisional==true) then
  if not self:references_current() then return nil,self.error or 'proof-time-budget' end
 end
 self.proofPhase='final-stamp'
 -- Queries may themselves cause a scene/capture transition. Certify afterwards.
 ok,reason=self:sync(ctx);if not ok then return nil,reason end
 if target.generation~=self.generation or target.revision~=self.revision then return nil,'capture-changed' end
 return {x=x,y=y,z=z,key=tri.key,scene=self.scene,generation=self.generation,
  revision=self.revision,checkedFrame=ctx.frame,provisional=options and options.provisional==true}
end
function A:select(ctx)
 local ok,reason=self:sync(ctx);if not ok then return nil,reason end
 if not point(ctx.p) or not point(ctx.mario) then return nil,'invalid-position' end
 self.stats.searches=self.stats.searches+1
 local aim=copy(ctx.mario)
 if point(ctx.marioVelocity) and ctx.recoveryHidden~=true then
  local vx,vz=ctx.marioVelocity.x*self.c.predictionSeconds,ctx.marioVelocity.z*self.c.predictionSeconds
  local length=math.sqrt(vx*vx+vz*vz)
  if length>self.c.maxLead then vx,vz=vx*self.c.maxLead/length,vz*self.c.maxLead/length end
  aim.x,aim.z=aim.x+vx,aim.z+vz
 end
 local proposals={};local seen={};local searched=0
 local function offer(tri,x,z,predicted)
  local r=self.c.supportRadius+self.c.margin
  if not contained(tri,x,z,r) then return end
  local y=floor_y(tri,x,z);local t={x=x,y=y,z=z}
  if horizontal(t,ctx.mario)>(predicted and self.c.maxLead or self.c.nearMario) or y<ctx.mario.y-self.c.belowMario or
   y>ctx.mario.y+self.c.aboveMario or (ctx.recoveryHidden~=true and distance(t,ctx.p)>self.c.maxTravel) then return end
  local key=tri.key..':'..x..':'..z
  if seen[key] then return end;seen[key]=true
  t.key=tri.key;t.scene=self.scene;t.generation=self.generation;t.revision=self.revision
  t.score=horizontal(t,aim)+math.abs(y-ctx.mario.y)*1.6+distance(t,ctx.p)*.08
  proposals[#proposals+1]=t
  table.sort(proposals,function(a,b) return a.score<b.score end)
  if #proposals>self.c.maxCandidates then table.remove(proposals) end
 end
 for _,tri in ipairs(self.tris) do
  searched=searched+1;if searched>self.c.maxSearchFloors then return nil,'search-budget' end
  local reach=math.max(self.c.nearMario,horizontal(aim,ctx.mario))
  if tri.support and tri.maxX>=ctx.mario.x-reach and tri.minX<=ctx.mario.x+reach and
   tri.maxZ>=ctx.mario.z-reach and tri.minZ<=ctx.mario.z+reach then
   offer(tri,(tri.v[1].x+tri.v[2].x+tri.v[3].x)/3,(tri.v[1].z+tri.v[2].z+tri.v[3].z)/3)
   if horizontal(aim,ctx.mario)>1 then
    for _,t in ipairs({.25,.5,.75,1}) do
     offer(tri,ctx.mario.x+(aim.x-ctx.mario.x)*t,ctx.mario.z+(aim.z-ctx.mario.z)*t,true)
    end
   end
   for _,radius in ipairs({240,420,650}) do for i=0,7 do
    local a=i*math.pi/4
    offer(tri,ctx.mario.x+math.sin(a)*radius,ctx.mario.z+math.cos(a)*radius)
   end end
  end
 end
 for _,p in ipairs(proposals) do
  local cert,why=self:validate(p,ctx)
  if cert then return cert end
  reason=why
 end
 return nil,reason or 'no-safe-static-platform'
end
-- This binding is EXPLICIT. It installs no hooks at require() time.
-- A fresh level load is required; hot-loading mid-scene stays unready.
function A:bind_engine()
 local api=self.api
 if self.bound then return true end
 if type(api.hook)~='function' or api.HOOK_ON_ADD_SURFACE==nil or
  api.HOOK_ON_CLEAR_AREAS==nil or api.HOOK_ON_LEVEL_INIT==nil or api.HOOK_UPDATE==nil or type(api.scene)~='function' then return false end
 -- A mid-scene bind cannot see preexisting surfaces. Quarantine that terrain
 -- pointer until CLEAR_AREAS or a genuinely different terrain load is observed.
 local ok,initial=pcall(api.scene);if not ok then return false end
 self:clear(initial);self.quarantineToken=initial
 local function terrain()
  local success,token=pcall(api.scene)
  if not success then self.error='scene-read-error';self.complete=false;return nil end
  return token
 end
 api.hook(api.HOOK_ON_CLEAR_AREAS,function()
  self:clear(nil);self.engineCaptureEligible=true
 end)
 api.hook(api.HOOK_ON_ADD_SURFACE,function(s,dynamic)
  local success=pcall(function()
   local token=terrain();if token==nil then return end
   local eligible=self.engineCaptureEligible or token~=self.quarantineToken
   if token~=self.scene then self:clear(token) end
   self.engineCaptureEligible=eligible
   self:add_surface(s,dynamic,token)
  end)
  if not success then self.error='surface-read-error';self.complete=false end
 end)
 api.hook(api.HOOK_ON_LEVEL_INIT,function()
  local token=terrain();if token~=nil then self:finish(token) end
 end)
 -- Engine area loads are synchronous. Two quiet update intervals complete
 -- same-level area loads, which do not necessarily send LEVEL_INIT. This only
 -- completes an eligible fresh capture, never a quarantined hot-loaded scene.
 api.hook(api.HOOK_UPDATE,function()
  local token=terrain();if token==nil then return end
  if token~=self.scene then
   self:clear(token);self.engineCaptureEligible=token~=self.quarantineToken
  end
  if self.quietRevision~=self.revision then self.quietRevision=self.revision;self.quietTicks=0
  else self.quietTicks=self.quietTicks+1 end
  if self.quietTicks>=2 and not self.complete then self:finish(token) end
 end)
 self.bound=true
 return true
end
-- Concrete SM64 adapter. Constants/functions are resolved once. No fallback
-- booleans, fabricated dry probes, object collision, Mario/NPC writes or globals.
function A.engine(globals,options)
 local g=globals or _G
 local api={scene=g.smlua_collision_util_get_current_terrain_collision,floor=g.find_floor,
  water=g.find_water_level,gas=g.find_poison_gas_level,hook=g.hook_event}
 for _,name in ipairs({'SURFACE_DEFAULT','SURFACE_HARD','SURFACE_NOT_SLIPPERY','SURFACE_HARD_NOT_SLIPPERY',
  'SURFACE_NO_CAM_COLLISION','SURFACE_FLAG_DYNAMIC','SURFACE_FLAG_INTANGIBLE','SURFACE_CAMERA_BOUNDARY',
  'SURFACE_RAYCAST','SURFACE_FLAG_X_PROJECTION','HOOK_ON_ADD_SURFACE','HOOK_ON_CLEAR_AREAS','HOOK_ON_LEVEL_INIT','HOOK_UPDATE'}) do api[name]=g[name] end
 return A.new(api,options)
end
return A
