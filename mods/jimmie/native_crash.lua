-- Stock 1.5.1 staged crash owner. No auto hooks, spawning, Mario or PHYS writes.
-- Flat/open/static admission is deliberately conservative; declined crashes keep
-- the host's existing bail. A certified get-up may retain the pair through an
-- atomic host handback; failures retire it without restoring stale movement.
-- This is a hybrid, not joint-contact physics.
local M={SCALE=.62,HZ=30,BRACE_TICKS=90,STEP_PAD=40,TOP=400,PROOF_SECONDS=.008}
local function finite(n) return type(n)=='number' and n==n and math.abs(n)<1e7 end
local function point(p) return p and finite(p.x) and finite(p.y) and finite(p.z) end
local function copy(p) return {x=p.x,y=p.y,z=p.z} end
local function scaled(data)
 local d={variants={},recoveries={},board_name=data.board_name,board_half={},board_idle={}}
 for i,v in ipairs(data.board_idle) do d.board_idle[i]=v*M.SCALE end
 for i,h in ipairs(data.board_half) do d.board_half[i]=h*M.SCALE end
 local radius=math.sqrt(d.board_half[1]^2+d.board_half[2]^2+d.board_half[3]^2)
 for _,role in ipairs({'variants','recoveries'}) do for i,v in ipairs(data[role]) do
  local q={name=v.name,bounds={}};d[role][i]=q
  for j,b in ipairs(v.bounds) do q.bounds[j]={minY=b.minY*M.SCALE,maxY=b.maxY*M.SCALE,radius=b.radius*M.SCALE};radius=math.max(radius,q.bounds[j].radius) end
 end
 end
 return d,radius
end
-- deps = {core, renderer, capture}; each is the returned Lua module.
-- opts.owns(body, board) must verify exact host-owned live pair identity.
function M.new(g,data,deps,opts)
 opts=opts or {};assert(type(opts.owns)=='function','exact pair ownership callback required')
 local d,radius=scaled(data)
 local capture=deps.capture.engine(g,{radius=radius+M.STEP_PAD,supportRadius=radius+M.STEP_PAD,top=M.TOP,maxSlope=.00000001,maxTriangles=8192,maxSurfaceRefs=16384,maxClearanceChecks=8192})
 local self={capture=capture,data=d,radius=radius,braceTicks=0,active=false,reason='idle',regions={}}
 local render=deps.renderer.new(d)
 capture.now=g.clock_elapsed_f64
 local function now()
  if type(capture.now)~='function' then return nil end
  local ok,t=pcall(capture.now);if ok and finite(t) then return t end
 end
 local function valid_pair(body,board)
  if not body or not board or body==board then return false end
  local ok,owned=pcall(opts.owns,body,board);if not ok or owned~=true then return false end
  if type(g.gMarioStates)~='table' then return false end
  for _,m in pairs(g.gMarioStates) do if m and (m.marioObj==body or m.marioObj==board or m.heldObj==body or m.heldObj==board or m.riddenObj==body or m.riddenObj==board) then return false end end
  local safe,answer=pcall(function()
   for _,o in ipairs({body,board}) do
    if o.activeFlags==0 or not o.header or not o.header.gfx or not o.header.gfx.animInfo then return false end
    local scale=o.header.gfx.scale
    if not scale then return false end
    for _,k in ipairs({'x','y','z'}) do if not finite(scale[k]) or math.abs(math.abs(scale[k])-M.SCALE)>.00001 then return false end end
   end
   return true
  end)
  return safe and answer
 end
 local function token()
  local ok,t=pcall(g.smlua_collision_util_get_current_terrain_collision);if ok then return t end
 end
 local function stamp_current()
  return self.stamp and token()==self.stamp.scene and capture.scene==self.stamp.scene and capture.generation==self.stamp.generation and capture.revision==self.stamp.revision and capture.complete and not capture.error
 end
 local function region_for(x,z,r)
  for _,v in ipairs(self.regions) do
   if math.abs(x-v.x)+r<=v.radius and math.abs(z-v.z)+r<=v.radius then return v end
  end
 end
 local world={}
 function world.floor(x,y,z)
  if not stamp_current() then error('capture changed') end
  local v=region_for(x,z,0);if not v then error('outside certified support') end
  return {y=v.y,ny=1,safe=true,dynamic=false}
 end
 function world.wall(old,p,r,envelope)
  if not stamp_current() or not point(p) or not point(old) then return nil end
  -- Use the larger full sphere/cylinder bound, including board vertical rotation.
  r=math.max(r,self.radius)
  local region
  for _,v in ipairs(self.regions) do
   if math.max(math.abs(old.x-v.x),math.abs(p.x-v.x))+r<=v.radius and math.max(math.abs(old.z-v.z),math.abs(p.z-v.z))+r<=v.radius then region=v;break end
  end
  if not region or p.y+envelope.maxY>region.y+M.TOP then return nil end
  -- Floor projection is done by the core. Final rendered bounds are checked
  -- after projection, so downward microsteps never authorize a drawn penetration.
  return {pos=copy(p),blocked=false}
 end
 local core=deps.core.new(d,world);self.core=core
 local function prepare_work(positions,frame)
  self.regions={};self.stamp=nil
    local t=token();if t==nil then return false,'missing-terrain' end
  local ctx={scene=t,frame=frame};local stamp=capture:stamp(ctx)
  if not stamp.ready then return false,stamp.reason end
  for _,p in ipairs(positions) do
   capture.proofPhase='floor-lookup'
   local ok,h,s=pcall(g.find_floor,p.x,p.y+8,p.z)
   if not ok or not finite(h) or not s or s.object~=nil then return false,'missing-static-floor' end
   -- Root queries stay fresh even when static footprint geometry is shared.
   local tri
   for index,record in ipairs(capture.references) do
    if index%32==1 and not capture:within_budget() then return false,'proof-time-budget' end
    if record.source==s then tri=record.tri;break end
   end
   if not tri or not tri.support or math.abs(tri.n.x)>1e-8 or math.abs(tri.n.z)>1e-8 then return false,'unsupported-floor' end
   -- Reuse only a region proved earlier in THIS call, with 20 units reserved
   -- for travel. All later sweeps and final poses still need containment.
   local shared=region_for(p.x,p.z,self.radius+M.STEP_PAD/2)
   if shared and math.abs(h-shared.y)<=.001 then
    capture.proofPhase='reused-root-hazards'
    local waterOk,water=pcall(capture.api.water,p.x,p.z)
    local gasOk,gas=pcall(capture.api.gas,p.x,p.z)
    if not waterOk or not gasOk or not finite(water) or not finite(gas) then return false,'missing-hazard-level' end
    if water>h-4 then return false,'water-at-contact' end
    if gas>h-4 then return false,'gas-at-contact' end
    self.proofReuseCount=self.proofReuseCount+1
   else
    self.proofCertificateCount=self.proofCertificateCount+1
    local cert,why=capture:validate({x=p.x,y=h,z=p.z,key=tri.key,scene=t,generation=stamp.generation,revision=stamp.revision},ctx,{provisional=true})
    if not cert then return false,why end
    self.regions[#self.regions+1]={x=p.x,y=h,z=p.z,radius=capture.c.radius}
   end
  end
  if not capture:references_current() then return false,capture.error or 'proof-time-budget' end
  self.stamp=stamp
  if not stamp_current() then return false,'capture-changed' end
  return true
 end
 local function prepare(positions,frame)
  local started=now();self.lastProofSeconds=nil;self.proofCertificateCount=0;self.proofReuseCount=0
  capture.proofPhase='capture-stamp'
  if not started then return false,'missing-proof-clock' end
  capture.deadline=started+M.PROOF_SECONDS
  local scans=capture.stats.referenceScans or 0
  local ran,ok,why=pcall(prepare_work,positions,frame)
  if not ran then why='proof-error: '..tostring(ok);ok=false end
  local ended=now();self.lastProofSeconds=ended and ended-started or nil
  if ok and (not ended or ended>capture.deadline) then ok=false;why='proof-time-budget' end
  self.lastProof={seconds=self.lastProofSeconds,phase=capture.proofPhase,certificates=self.proofCertificateCount,reusedRegions=self.proofReuseCount,
   referenceScans=(capture.stats.referenceScans or 0)-scans,triangles=#capture.tris,references=#capture.references,
   failed=not ok,reason=why}
  if not ok then self.stamp=nil;self.regions={} end
  return ok,why
 end
 local function project_rotating_floor(s)
  -- A changing pose can sweep a corner down while its root is moving UP.
  -- On the certified flat plane, project that penetration before rendering;
  -- preserve upward momentum and let the existing core own downward impacts.
  local clips=s.phase=='getup' and d.recoveries or d.variants
  local b=clips[s.variant].bounds[s.frame+1]
  local r=region_for(s.body.x,s.body.z,b.radius)
  local clear=s.phase=='getup' and 2*(1-s.frame/(#d.recoveries[s.variant].bounds-1)) or 2
  if r then core.body.y=math.max(core.body.y,r.y+clear-b.minY) end
  local h=d.board_half;local sx,cx=math.sin(s.board.pitch),math.cos(s.board.pitch);local sz,cz=math.sin(s.board.roll),math.cos(s.board.roll)
  local extent=math.abs(sz*cx)*h[1]+math.abs(cz*cx)*h[2]+math.abs(sx)*h[3]
  r=region_for(s.board.x,s.board.z,math.sqrt(h[1]^2+h[2]^2+h[3]^2))
  local boardClear=clear
  if s.phase=='getup' and s.frame<#d.recoveries[s.variant].bounds-1 then boardClear=math.max(.35,clear) end -- stock angle/LUT rounding guard
  if r then core.board.y=math.max(core.board.y,r.y+boardClear+extent) end
  return core:snapshot()
 end
 local function pose_safe(s)
  if not stamp_current() then return false,'capture-changed' end
  local clips=s.phase=='getup' and d.recoveries or d.variants
  local b=clips[s.variant].bounds[s.frame+1]
  local region=region_for(s.body.x,s.body.z,b.radius)
  if not region or s.body.y+b.minY<region.y-.001 or s.body.y+b.maxY>region.y+M.TOP then return false,'body-outside-proof' end
  local half=d.board_half;local sx,cx=math.sin(s.board.pitch),math.cos(s.board.pitch);local sz,cz=math.sin(s.board.roll),math.cos(s.board.roll)
  local vertical=math.abs(sz*cx)*half[1]+math.abs(cz*cx)*half[2]+math.abs(sx)*half[3]
  local br=math.sqrt(half[1]^2+half[2]^2+half[3]^2)
  region=region_for(s.board.x,s.board.z,br)
  if not region or s.board.y-vertical<region.y-.001 or s.board.y+vertical>region.y+M.TOP then return false,'board-outside-proof' end
  return true
 end
 function self:bind() return capture:bind_engine() end
 -- Final get-up remains exclusively owned until one same-update host commit.
 -- The callback must install BOTH idle actors and rebuild PHYS before returning
 -- true. A false/throw means the host must retire the pair, never retry a write.
 function self:commit_recovery(e,commit)
  if not self.active or not core.ready or type(commit)~='function' or not e or e.scene~=self.scene or e.frame~=self.previousFrame or not valid_pair(self.body,self.board) or not stamp_current() then return false,'stale-recovery-offer' end
  local p={x=core.body.x,y=core.getupFloor,z=core.body.z,yaw=core.body.yaw,heading=core.heading or 0,scene=self.scene,frame=self.previousFrame}
  local ok,result=pcall(commit,self.body,self.board,p)
  if not ok or result~=true then self.reason='recovery-commit-failed';self:release(false);return false,self.reason end
  render:forget();self.active=false;core.active=false;self.reason='recovered'
  self.body=nil;self.board=nil;self.regions={};self.stamp=nil
  return true,p
 end
 function self:status(retire)
  return {active=self.active,owned=self.active,ready=self.active and core.ready==true,retire=retire==true,braceTicks=self.braceTicks,reason=self.reason,proofSeconds=self.lastProofSeconds,proof=self.lastProof,support=self.capture.supportDiagnostics,snapshot=core:snapshot()}
 end
 -- release(false) drops references without touching potentially deleted objects.
 -- After release(true), host must retire BOTH objects in this same update.
 function self:release(objectsValid)
  local ok,why=true,nil
  if render.saved then
   if objectsValid~=false and valid_pair(self.body,self.board) then ok,why=render:release()
   else render.saved=nil;render.body=nil;render.board=nil end
  end
  self.active=false;core.active=false;self.body=nil;self.board=nil;self.regions={};self.stamp=nil
  return ok,why
 end
 function self:reset(reason,objectsValid)
  self:release(objectsValid);core:reset(reason);self.braceTicks=0;self.scene=nil;self.previousFrame=nil;self.sequence=nil;self.reason=reason or 'reset'
 end
 function self:begin(e,body,board)
  if self.active then return false,'already-active' end
  if type(e)~='table' or e.kind~='companion_crash' or e.source~='companion' or not point(e.pos) or not point(e.velocity) or not finite(e.yaw) or not finite(e.frame) or e.frame%1~=0 or not finite(e.sequence) or e.sequence%1~=0 or type(e.scene)~='string' or e.scene=='' then return false,'invalid-event' end
  if self.scene==e.scene and self.sequence and e.sequence<=self.sequence then return false,'duplicate-event' end
  -- Legacy counter retained for API compatibility; outcomes owns the post-recovery ten-second collar.
  self.scene=e.scene;self.sequence=e.sequence;self.previousFrame=e.frame;self.braceTicks=M.BRACE_TICKS
  if not valid_pair(body,board) then self.reason='invalid-pair';return false,self.reason end
  local ok,why=prepare({e.pos},e.frame)
  if not ok then self.reason=why;return false,why end
  if math.abs(e.pos.y-self.regions[1].y)>8 or math.abs(e.velocity.y)>120 then self.reason='ground-entry-required';return false,self.reason end
  ok,why=core:begin(e);if not ok then self.reason=why;return false,why end
  ok,why=pose_safe(core:snapshot());if not ok then core.active=false;self.reason=why;return false,why end
  ok,why=render:bind(body,board);if not ok then core.active=false;self.reason=why;return false,why end
  self.body=body;self.board=board;self.active=true;self.reason='crash'
  -- Normal motion owner must yield before the first step. begin never draws.
  return true
 end
 function self:step(e)
  if type(e)~='table' or not finite(e.frame) or e.frame%1~=0 or type(e.scene)~='string' then return self:status(false) end
  if self.scene and e.scene~=self.scene or e.enabled==false then
   local retire=self.active;self:reset('scene-or-disable',e.objectsValid);return self:status(retire)
  end
  if e.paused then self.previousFrame=e.frame;if self.active then core:step(e) end;return self:status(false) end
  if self.previousFrame and e.frame<=self.previousFrame then return self:status(false) end
  if self.previousFrame and e.frame-self.previousFrame>4 then local retire=self.active;self:reset('stale-clock',e.objectsValid);return self:status(retire) end
  self.previousFrame=e.frame;self.braceTicks=math.max(0,self.braceTicks-1)
  if not self.active then return self:status(false) end
  if not valid_pair(self.body,self.board) or e.ownerAlive==false then self:release(false);self.reason='owner-removed';return self:status(true) end
  local ok,why=prepare({core.body,core.board},e.frame)
  if ok then
   local snap=core:step(e)
   if snap.active then
    snap=project_rotating_floor(snap)
    ok,why=pose_safe(snap)
    if ok then ok,why=render:apply(snap) end
    if ok then return self:status(false) end
   else why=snap.reason end
  end
  self.reason=why or 'retire';self:release(true);return self:status(true)
 end
 return self
end
return M
