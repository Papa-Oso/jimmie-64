-- Finite native geometry probes. Optional numeric surface-hint capture, no actor writes or retained Surfaces.
-- Intentional forgiving gameplay envelope: radius24/top120, NOT the approved
-- native_rejoin visual profile radius116/top360. No continuous or mesh guarantee.
-- Operations share 3000 calls and 4ms; fresh rail admission alone may use 8ms.
-- Both elapsed limits are cooperative. A single native call cannot
-- be preempted; elapsed checks stop subsequent work, not guarantee engine latency.
local M={}; M.__index=M
local CLEAR_OFFSETS={{0,0},{24,0},{-24,0},{0,24},{0,-24}}
local CLEAR_HEIGHTS={8,32,64,96,120}
local SUPPORT_OFFSETS={{1,0},{-1,0},{0,1},{0,-1},{.707,.707},{.707,-.707},{-.707,.707},{-.707,-.707}}
local indexOK,RailIndex=pcall(require,'skate_rail_index')
if not indexOK or type(RailIndex)~='table' then RailIndex=nil end
local surfaceOK,SurfaceRails=pcall(require,'skate_surface_rails')
if not surfaceOK or type(SurfaceRails)~='table' then SurfaceRails=nil end
local anchorOK,RailPresentation=pcall(require,'skate_rail_presentation')
if not anchorOK or type(RailPresentation)~='table' then RailPresentation=nil end
local function num(v) return type(v)=='number' and v==v and math.abs(v)<30000 end
local function pt(p) return p and num(p.x) and num(p.y) and num(p.z) end
local function cp(p) return {x=p.x,y=p.y,z=p.z} end
local function dist(a,b) return math.sqrt((a.x-b.x)^2+(a.y-b.y)^2+(a.z-b.z)^2) end
local function mix(a,b,t) return {x=a.x+(b.x-a.x)*t,y=a.y+(b.y-a.y)*t,z=a.z+(b.z-a.z)*t} end
local function elapsed(v) return type(v)=='number' and v==v and v>=0 and v<math.huge end
function M:_tick()
 local b=self._budget
 if type(self.g.clock_elapsed_f64)~='function' then return end
 if b.calls>=3000 then b.reason='native-query-budget';error(b.reason,0) end
 b.calls=b.calls+1;b.clockReads=b.clockReads+1
 local now=self.g.clock_elapsed_f64()
 if not elapsed(now) or (b.last and now<b.last) then b.reason='invalid-native-clock';error(b.reason,0) end
 b.started=b.started or now;b.last=now;b.elapsed=now-b.started
 if b.elapsed>=(b.timeLimit or .004) then b.reason='native-time-budget';error(b.reason,0) end
end
function M:_native(name,...)
 local b=self._budget
 if b.queries%8==0 then self:_tick() end
 if b.calls>=3000 then b.reason='native-query-budget';error(b.reason,0) end
 b.calls=b.calls+1;b.queries=b.queries+1
 local a,c=self.g[name](...)
 return a,c
end
local function guarded(fn)
 return function(self,...)
  -- Nested operations must propagate errors to the outer transaction, never
  -- swallow budget exhaustion and accept an earlier partially checked rail.
  if self._budget then return fn(self,...) end
  self.lastReject=nil
  self._budget={calls=0,queries=0,clockReads=0,elapsed=0,cleared={}}
  local args=table.pack(...)
  local ok,r=pcall(function()
   self:_tick()
   local result=fn(self,table.unpack(args,1,args.n))
   self:_tick()
   return result
  end)
  local b=self._budget;self._budget=nil
  self.lastBudget={calls=b.calls,queries=b.queries,clockReads=b.clockReads,elapsed=b.elapsed,
   timeLimit=b.timeLimit or .004,reason=b.reason or (not ok and 'native-read-failed' or nil),
   error=not ok and not b.reason and tostring(r):sub(1,120) or nil}
  if ok and not b.reason then return r end
  -- Failed indexed work must not monopolize every new transaction. This is
  -- only a scheduling deferral, never retained geometry/clearance authority.
  local scan=self._railScan
  if scan and scan.indexKey and self.deferRail then
   self:deferRail({indexKey=scan.indexKey},scan.frame,300)
  end
  self._railScan=nil -- no numeric discovery survives a failed transaction
  return nil
 end
end
M.transaction=guarded(function(self,fn) return fn() end)
-- Only a pending, live-player-clear rail admission requests this allowance.
-- It lasts for this outer transaction, including its first committed segment.
-- The 3000-call cap, all proofs and next-frame default remain unchanged.
function M:allowRailAdmission()
 if self._budget then self._budget.timeLimit=.008 end
end
function M.new(g)
 local self=setmetatable({g=g or _G,allowed={}},M)
 for _,s in ipairs({'SURFACE_DEFAULT','SURFACE_HARD','SURFACE_NOT_SLIPPERY','SURFACE_HARD_NOT_SLIPPERY','SURFACE_NO_CAM_COLLISION','SURFACE_SLIPPERY','SURFACE_VERY_SLIPPERY','SURFACE_HARD_SLIPPERY','SURFACE_HARD_VERY_SLIPPERY'}) do local k=self.g[s];if num(k) then self.allowed[k]=true end end
 if SurfaceRails then
  self.surfaceRails=SurfaceRails.new(self.g);self.surfaceRails:bind()
  self.surfaceBudget={tick=function()self:_tick()end,scene=function()return self:_native('smlua_collision_util_get_current_terrain_collision')end}
 end
 return self
end
function M:deny(reason) self.lastReject=reason;return nil end
function M:_floor(x,y,z)
 local g=self.g
 if not pt({x=x,y=y,z=z}) or math.abs(x)>7900 or math.abs(z)>7900 then return nil end
 if not num(g.SURFACE_POOL_STATIC) or not num(g.SURFACE_FLAG_DYNAMIC) or not num(g.SURFACE_FLAG_INTANGIBLE) then return nil end
 local h,s=self:_native("find_floor",x,y,z)
 if not num(h) or not s then return self:deny('no-static-floor') end
 local kind,flags=s.type,s.flags
 if not self.allowed[kind] then return self:deny('floor-type-refused') end
 if s.poolType~=g.SURFACE_POOL_STATIC or s.object~=nil then return self:deny('nonstatic-floor') end
 if not num(flags) or flags%1~=0 or (flags & (g.SURFACE_FLAG_DYNAMIC|g.SURFACE_FLAG_INTANGIBLE))~=0 then return nil end
 local nr,v1r,v2r,v3r=s.normal,s.vertex1,s.vertex2,s.vertex3
 if not nr or not v1r or not v2r or not v3r then return self:deny('floor-slope-or-data-refused') end
 -- Read each native userdata component once, then validate the numeric copy.
 -- The old validate-then-copy path doubled expensive userdata field accesses.
 local n,v1,v2,v3=cp(nr),cp(v1r),cp(v2r),cp(v3r)
 if not pt(n) or n.y<.65 or n.y>1.001 or not pt(v1) or not pt(v2) or not pt(v3) then return self:deny('floor-slope-or-data-refused') end
 local out={x=x,y=h,z=z,normal=n,type=kind,vertices={v1,v2,v3}}
 s=nil
 local water,gas=self:_native("find_water_level",x,z),self:_native("find_poison_gas_level",x,z)
 if not num(water) or not num(gas) or water>=h-4 or gas>=h-4 then return nil end
 return out
end
M.floor=guarded(M._floor)
function M:away(p,player)
 -- Jimmie has no Mario interaction/collision. Optional skating may pass close
 -- to or through players; a personal-space radius must not veto a fun route.
 -- Keep the shared predicate for fresh finite-state validation only. Terrain,
 -- raised presentation, follow range, momentum and recovery rules are separate.
 local q=player and (player.pos or player)
 return pt(p) and pt(q)
end
function M:_clear(p)
 if not pt(p) then return nil end
 -- Exact-point reuse lasts only for this synchronous read-only transaction.
 -- It avoids checking shared segment endpoints repeatedly, never a later frame.
 -- Player exclusion is outside this cache and is still checked at every sample.
 local cache=self._budget and self._budget.cleared
 local xs=cache and cache[p.x];local ys=xs and xs[p.y]
 if ys and ys[p.z] then return true end
 local g=self.g
 for _,o in ipairs(CLEAR_OFFSETS) do
  local x,z=p.x+o[1],p.z+o[2]
  local ch,cs=self:_native("find_ceil",x,p.y+4,z)
  if not num(ch) or ch<p.y+124 then return self:deny('ceiling-clearance') end
  if cs~=nil and (not pt(cs.normal) or not pt(cs.vertex1) or not pt(cs.vertex2) or not pt(cs.vertex3)) then return nil end
  cs=nil
  local water,gas=self:_native("find_water_level",x,z),self:_native("find_poison_gas_level",x,z)
  if not num(water) or not num(gas) or water>=p.y-4 or gas>=p.y-4 then return nil end
 end
 local q=cp(p)
 for _,h in ipairs(CLEAR_HEIGHTS) do
  q.x,q.y,q.z=p.x,p.y,p.z
  local wall=self:_native("resolve_and_return_wall_collisions",q,h,24)
  if wall~=nil or not pt(q) or math.abs(q.x-p.x)>.01 or math.abs(q.y-p.y)>.01 or math.abs(q.z-p.z)>.01 then return self:deny('wall-clearance') end
 end
 -- Reject terrain protruding into the lower body (ordinary support is allowed).
 local fh,fs=self:_native("find_floor",p.x,p.y+120,p.z);fs=nil
 if not num(fh) or (fh>p.y+4 and fh<=p.y+120) then return self:deny('lower-body-terrain') end
 if fh>=p.y-4 and not self:floor(p.x,p.y+120,p.z) then return nil end
 if cache then
  cache[p.x]=cache[p.x] or {};local x=cache[p.x];x[p.y]=x[p.y] or {};x[p.y][p.z]=true
 end
 return true
end
M.clear=guarded(M._clear)
function M:_support(p,r)
 if not pt(p) then return nil end;r=r or 32
 if not num(r) or r<0 or r>64 then return nil end
 local center=self:floor(p.x,p.y+24,p.z)
 if not center or math.abs(center.y-p.y)>18 then return self:deny('landing-center') end
 local n=center.normal
 if r>0 then for _,o in ipairs(SUPPORT_OFFSETS) do
  -- Compare the actual support plane, not a horizontal plane that rejects stairs.
  local ox,oz=o[1]*r,o[2]*r
  local expected=center.y-(n.x*ox+n.z*oz)/n.y
  local f=self:floor(p.x+ox,expected+24,p.z+oz)
  if not f or math.abs(f.y-expected)>18 then return self:deny('landing-footprint') end
 end end
 if not self:clear(p) then return nil end
 return center
end
M.support=guarded(M._support)
function M:_segment(a,b,player)
 if not pt(a) or not pt(b) or dist(a,b)>650 then return nil end
 local count=math.max(1,math.ceil(dist(a,b)/24))
 for i=0,count do local p=mix(a,b,i/count);if not self:clear(p) or (player and not self:away(p,player)) then return nil end end
 return true
end
M.segment=guarded(M._segment)
function M:at(plan,t)
 if not num(t) or t<0 or t>1 then return nil end
 -- A late barrier vault pops up before translating across the obstacle.
 -- This bounded arcade curve is not a claim of ballistic/continuous physics.
 local u=plan.launchEase and t*t or t
 local p=mix(plan.a,plan.b,u);p.y=p.y+4*plan.lift*t*(1-t);return p
end
function M:_arc(a,b,clearance,options)
 local player=options and (options.pos or options.x) and options or nil
 local radius=(options and options.landingRadius) or 32
 if not num(radius) or radius<0 or radius>64 then return nil end
 if not pt(a) or not pt(b) then return nil end
 local d=math.sqrt((a.x-b.x)^2+(a.z-b.z)^2)
 if d<8 or d>600 or b.y-a.y>180 or a.y-b.y>640 then return self:deny('arc-range') end
 if not self:support(b,radius) then return nil end
 clearance=clearance or 60;if not num(clearance) or clearance<0 or clearance>180 then return nil end
 local lift=math.max(60,clearance)+math.abs(b.y-a.y)/2+((options and options.launchEase) and 8 or 0)
 local plan={a=cp(a),b=cp(b),landing=cp(b),kind='jump',lift=lift,launchEase=options and options.launchEase==true,
  points={},continuousClearance=false,method='finite-native-probes'}
 -- Adaptive subdivision bounds chord plus curvature rather than charging every
 -- interval for the steepest endpoint derivative of a long descending jump.
 local points={self:at(plan,0)}
 local function subdivide(t0,a0,t1,b1,depth)
  local tm=(t0+t1)/2;local mid=self:at(plan,tm)
  local curve=dist(mid,mix(a0,b1,.5))
  if dist(a0,b1)+2*curve<=24 then points[#points+1]=b1;return #points<=128 end
  if depth>=12 or #points>=128 then return false end
  return subdivide(t0,a0,tm,mid,depth+1) and subdivide(tm,mid,t1,b1,depth+1)
 end
 if not subdivide(0,points[1],1,self:at(plan,1),0) then return self:deny('arc-sample-limit') end
 local length=0;local prev;local peak=-math.huge
 for _,q in ipairs(points) do
  if not self:clear(q) or (player and not self:away(q,player)) then return nil end
  if prev then length=length+dist(prev,q) end;prev=q;peak=math.max(peak,q.y)
 end
 if peak>math.max(a.y,b.y)+400 then return self:deny('arc-height-limit') end
 plan.points=points;plan.peak=peak;plan.duration=math.max(18,math.min(36,math.ceil(length/28)))
 return plan
end
M.arc=guarded(M._arc)
M.barrier=guarded(function(self,p,player)
 if not pt(p) or not pt(player) then return nil end
 local dx,dz=player.x-p.x,player.z-p.z;local length=math.sqrt(dx*dx+dz*dz)
 if length<1 then return nil end;dx,dz=dx/length,dz/length
 for _,ahead in ipairs({32,64,96,128}) do
  if ahead<length then
   local q={x=p.x+dx*ahead,y=p.y,z=p.z+dz*ahead}
   local top=self:floor(q.x,p.y+220,q.z)
   if not top or top.y>p.y+32 or top.y<p.y-55 or not self:clear(q) then
    return {distance=ahead,height=top and top.y or nil,reason=self.lastReject or 'height-transition'}
   end
  end
 end
 return nil
end)
-- Classify two-sided narrow tops separately from broad one-sided ledges.
-- A classification is a discovery hint, not an authorized grind or landing.
function M:_crossSection(p,dx,dz,raisedCrown)
 local edges={};local found=0
 for i=1,2 do
  local sign=i==1 and -1 or 1
  local edge=0
  for r=6,102,6 do
   local f=self:floor(p.x-dz*r*sign,p.y+24,p.z+dx*r*sign)
   if not f then
    -- Preserve measured wet-side drop recognition. Never use this lower
    -- unapproved surface as a landing; all returned exits stay broad and dry.
    local h=self:_native("find_floor",p.x-dz*r*sign,p.y+24,p.z+dx*r*sign)
    if num(h) and h>-10000 and h<p.y-28 then edge=r;break end
    return nil
   end
   if f.y<p.y-28 then edge=r;break end
   if math.abs(f.y-p.y)>(raisedCrown==32 and 32 or 18) then return nil end
  end
  edges[i]=edge;if edge>0 then found=found+1 end
 end
 if found==0 then return nil end
 if found==1 then
  return {feature='one-sided-ledge',edgeSide=edges[1]>0 and -1 or 1,
   edgeDistance=math.max(edges[1],edges[2]),continuousClearance=false}
 end
 local width=edges[1]+edges[2]-6
 if width<12 or width>180 then return nil end
 return {feature='two-sided-rail',width=width,continuousClearance=false}
end
function M:_width(p,dx,dz,raisedCrown)
 local feature=self:_crossSection(p,dx,dz,raisedCrown)
 return feature and feature.feature=='two-sided-rail' and feature.width or nil
end
M.featureAt=guarded(function(self,p,dx,dz)
 if not pt(p) or not num(dx) or not num(dz) then return nil end
 local length=math.sqrt(dx*dx+dz*dz);if length<.001 then return nil end
 local q=self:floor(p.x,p.y+24,p.z)
 if not q or math.abs(q.y-p.y)>2 then return nil end
 return self:_crossSection(q,dx/length,dz/length)
end)
function M:_railNear(p,player)
 if not pt(p) or not pt(player and (player.pos or player)) then return nil end
 -- Only nine nearby starts and eight headings; no world-coordinate scripts.
 for _,offset in ipairs({{0,0},{48,0},{-48,0},{0,48},{0,-48},{48,48},{48,-48},{-48,48},{-48,-48}}) do
  local a=self:floor(p.x+offset[1],p.y+180,p.z+offset[2])
  if a and math.abs(a.y-p.y)<=180 and self:away(a,player) and self:clear(a) then
   for j=0,7 do
    local dx,dz=math.cos(j*math.pi/4),math.sin(j*math.pi/4)
    local width=self:_width(a,dx,dz)
    if width then
     local points={cp(a)};local last=a
     for step=1,18 do
      local q=self:floor(a.x+dx*step*24,last.y+24,a.z+dz*step*24)
      if not q or math.abs(q.y-last.y)>32 or not self:_width(q,dx,dz) or not self:away(q,player) or not self:segment(last,q,player) then break end
      points[#points+1]=cp(q);last=q
     end
     if #points>=4 then
      for _,offset in ipairs({{48,0},{96,0},{144,0},{192,0},{72,120},{72,-120},{72,192},{72,-192}}) do
       local exit=self:floor(last.x+dx*offset[1]-dz*offset[2],last.y+180,last.z+dz*offset[1]+dx*offset[2])
       if exit and self:away(exit,player) and self:support(exit,64) then
        local arc=self:arc(last,exit,60,player)
        if arc then return {kind='grind',a=cp(a),b=cp(last),entry=cp(a),exit=cp(exit),exitArc=arc,width=width,points=points,continuousClearance=false,method='finite-native-probes'} end
       end
      end
     end
    end
   end
  end
 end
 return nil
end
M.railNear=guarded(M._railNear)
-- Incremental discovery retains only numeric hints, NEVER clearance authority.
-- Caller supplies a numeric lifecycle epoch and consecutive native frame numbers;
-- bump epoch on terrain/scene/actor changes, or call invalidateRails explicitly.
function M:invalidateRails() self._railScan=nil end
function M:resetRailHints() self._railScan=nil;self._railDeferred=nil;self._nearScanNext=nil end
function M:railScanActive() return self._railScan~=nil end
local scanOffsets={{48,0},{0,48},{0,-48},{96,48},{96,-48},{192,96},{192,-96},{24,0},{72,0},{96,0},{0,0},{192,0}}
local scanAngles={0,math.pi/2,math.pi,-math.pi/2,math.pi/4,-math.pi/4,3*math.pi/4,-3*math.pi/4}
local headingsPerStart=#scanAngles+2
-- Sloped top fall line supplies a longitudinal hint, never clearance authority.
-- Flat tops retain the original eight headings; two-sided width is mandatory.
local function slopeHeading(a,fx,fz,reverse)
 local nx,nz=a.normal.x,a.normal.z;local length=math.sqrt(nx*nx+nz*nz)
 if length<.05 then return nil end
 nx,nz=nx/length,nz/length
 if nx*fx+nz*fz<0 then nx,nz=-nx,-nz end
 if reverse then nx,nz=-nx,-nz end
 return nx,nz
end
-- On a raised flat cap, inspect a separate nearby sloped entry rather than
-- extending a grind across its possibly broad/one-sided junction. The two
-- shorter triangle edges avoid preferring the triangulation diagonal. Only
-- numeric vertices are retained, and the ordinary final proof and entry arc
-- remain mandatory. At most two neighbors per geometry-heading attempt.
function M:_neighborEntry(a,p,player,fx,fz,edgeIndex)
 if a.y<p.y+28 or math.abs(a.normal.y-1)>.001 then return nil end
 local edges={}
 for i=1,3 do
  local v,w=a.vertices[i],a.vertices[i%3+1]
  local x,z=w.x-v.x,w.z-v.z;local length=math.sqrt(x*x+z*z)
  if length>.001 then edges[#edges+1]={x=x/length,z=z/length,length=length} end
 end
 table.sort(edges,function(a,b) return a.length<b.length end)
 local e=edges[edgeIndex];if not e then return nil end
 for _,sign in ipairs({1,-1}) do
  local q=self:floor(a.x+e.x*72*sign,a.y+24,a.z+e.z*72*sign)
  if q and math.abs(q.y-p.y)<=180 and self:away(q,player) then
   local dx,dz=slopeHeading(q,e.x*sign,e.z*sign,false)
   if dx then
    local width=self:_width(q,dx,dz)
    if width and self:clear(q) then return q,dx,dz,width end
   end
  end
 end
 return nil
end
local exits={{48,0},{96,0},{144,0},{192,0},{72,120},{72,-120},{72,192},{72,-192}}
local function nextCandidate(s)
 if s.indexKey and s.deferred then s.deferred[s.indexKey]=s.frame+300 end
 s.phase=1;s.index=s.index+1;s.points=nil;s.exit=nil;s.exitIndex=nil;s.exitSide=nil;s.indexKey=nil
end
-- Map data supplies candidate numbers only. Unknown maps retain generic discovery.
-- No indexed point bypasses current native support/width/entry/exit/player checks.
function M:deferRail(rail,frame,delay)
 if not rail or not elapsed(frame) or not elapsed(rail.indexKey) then return end
 self._railDeferred=self._railDeferred or {}
 self._railDeferred[rail.indexKey]=frame+(delay or 90)
end
function M:_indexedHints(p,player,fx,fz,frame)
 local g=self.g;local index=RailIndex
 local np=g.gNetworkPlayers and g.gNetworkPlayers[0]
 local hints=self.surfaceRails and self.surfaceRails:near(p,player,fx,fz,frame,self._railDeferred,self.surfaceBudget) or {}
 local mapped=index and np and g[index.level] and np.currLevelNum==g[index.level] and np.currAreaIndex==index.area
 for i=1,mapped and math.min(#index.hints,512) or 0 do
  if i%16==1 then self:_tick() end
  local v=index.hints[i]
  local distance=math.sqrt((v[1]-p.x)^2+(v[3]-p.z)^2)
  if distance<=500 and math.abs(v[2]-p.y)<=180 then
   local q={x=v[1],y=v[2],z=v[3]}
   if self:away(q,player) then
    for _,sign in ipairs({1,-1}) do
     local dx,dz=v[4]*sign,v[5]*sign
     local key=i*2+(sign==1 and 0 or 1)
     local deferred=self._railDeferred and self._railDeferred[key]
     if not deferred or frame>=deferred then
      hints[#hints+1]={x=q.x,y=q.y,z=q.z,dx=dx,dz=dz,key=key,
       score=distance+.2*dist(q,player)+40*(1-dx*fx-dz*fz)}
     end
    end
   end
  end
 end
 table.sort(hints,function(a,b) return a.score<b.score end)
 -- At most512 examined numeric hints and24 queued directional candidates.
 while #hints>24 do hints[#hints]=nil end
 return hints
end
function M:_railScanStep(p,player,ctx)
 player=player and (player.pos or player)
 if not pt(p) or not pt(player) or not ctx or not elapsed(ctx.frame) or ctx.frame%1~=0
  or not elapsed(ctx.epoch) or ctx.epoch%1~=0 then self:invalidateRails();return nil end
 local speed=ctx.speed or 0
 if not num(speed) or speed<0 or speed>96 then self:invalidateRails();return nil end
 local fx,fz=ctx.forwardX or player.x-p.x,ctx.forwardZ or player.z-p.z
 if not num(fx) or not num(fz) then self:invalidateRails();return nil end
 local length=math.sqrt(fx*fx+fz*fz)
 if length<.001 then fx,fz=1,0 else fx,fz=fx/length,fz/length end
 local s=self._railScan
 if s and ctx.epoch==s.epoch and ctx.frame==s.frame then return nil end -- duplicate frame cannot advance
 if s and (ctx.epoch~=s.epoch or ctx.frame~=s.frame+1 or dist(p,s.previous)>96
  or dist(player,s.player)>96 or dist(p,s.origin)>600 or ctx.frame-s.started>120) then
  if s.indexKey then self:deferRail({indexKey=s.indexKey},ctx.frame,300) end
  if s.nearGeneric then self._nearScanNext=math.max(self._nearScanNext or 0,ctx.frame+90) end
  s=nil
 end
 if not s then
  s={phase=1,index=1,frame=ctx.frame,epoch=ctx.epoch,origin=cp(p),previous=cp(p),player=cp(player),started=ctx.frame,fx=fx,fz=fz,lookahead=speed>=8 and math.min(480,speed*10) or 0}
  self._railDeferred=self._railDeferred or {};s.deferred=self._railDeferred
  s.hints=self:_indexedHints(p,player,fx,fz,ctx.frame)
  s.nearCount=0
  if #s.hints>0 and s.lookahead==0 and ctx.frame>=(self._nearScanNext or 0) then
   s.nearCount=12;self._nearScanNext=ctx.frame+90
  end
  self._railScan=s
 end
 s.frame=ctx.frame;s.previous=cp(p);s.player=cp(player)
 -- Discovery belongs to a bounded static neighborhood, not a moving sampling
 -- lattice. Turning/following does not erase geometry hints. No old probe
 -- certifies a plan: phase four rechecks everything against the live player.
 fx,fz=s.fx,s.fz
 local origin=s.origin
 local extra=s.lookahead>0 and 1 or 0
 local hintCount=#(s.hints or {})
 -- While Mario is resting, give the nearest two floor sites a turn
 -- before the map-wide ranked list. They retain the shorter, affordable rail.
 local nearCount=s.nearCount or 0
 local candidateCount=hintCount+(#scanOffsets+extra)*headingsPerStart
 if s.index>candidateCount then self:invalidateRails();return nil end
 if s.phase==1 then
  -- Four hints maximum, sharing the same 3000-query/4ms transaction.
  -- Extension, exit and final fresh proof remain incremental operations.
  for attempt=1,4 do
  if s.index>candidateCount then self:invalidateRails();return nil end
  local a,dx,dz,width
  if s.index>nearCount and s.index<=hintCount+nearCount then
   local hint=s.hints[s.index-nearCount];s.indexKey=hint.key;s.nearGeneric=false;s.source=hint.source;s.visual=hint.visual;s.maxPoints=hint.points or 11
   a=self:floor(hint.x,hint.y+24,hint.z);dx,dz=hint.dx,hint.dz
   if not a or math.abs(a.y-hint.y)>2 then a=nil end
  else
   local localIndex=s.index<=nearCount and s.index or s.index-hintCount
   s.nearGeneric=s.index<=nearCount;s.source=nil;s.visual=nil;s.maxPoints=25
   local offsetIndex=math.floor((localIndex-1)/headingsPerStart)+1
   local offset=extra==1 and offsetIndex==1 and {s.lookahead,0} or scanOffsets[offsetIndex-extra]
   local heading=(localIndex-1)%headingsPerStart+1
   local angle=scanAngles[math.max(1,heading-2)]
   dx,dz=fx*math.cos(angle)-fz*math.sin(angle),fz*math.cos(angle)+fx*math.sin(angle)
   a=self:floor(origin.x+fx*offset[1]-fz*offset[2],origin.y+180,origin.z+fz*offset[1]+fx*offset[2])
   if a and math.abs(a.y-origin.y)<=180 and self:away(a,player) and heading<=2 then
    dx,dz=slopeHeading(a,fx,fz,heading==2)
    if not dx then
     local neighbor,nx,nz,nw=self:_neighborEntry(a,origin,player,fx,fz,heading)
     if neighbor then a,dx,dz,width=neighbor,nx,nz,nw end
    end
   end
  end
  if a and math.abs(a.y-origin.y)<=180 and self:away(a,player) then
   width=width or (dx and self:_width(a,dx,dz,s.visual and 32))
   if width and self:clear(a) then
    s.points={cp(a)};s.dx=dx;s.dz=dz;s.width=width;s.phase=2;return nil
   end
  end
  nextCandidate(s)
  end
  return nil
 elseif s.phase==2 then
  -- Two bounded extensions per update keep discovery useful while following.
  -- A verified rail may continue for 240 horizontal units, rather than forcing
  -- every grind to end after 144. Final full proof still shares the same budget.
  -- motion:longgrind. Four steps of 24 units per update, up to 25 points (576 units).
  for _=1,(s.visual and 2 or 4) do
   local a,last=s.points[1],s.points[#s.points]
   local q=self:floor(a.x+s.dx*#s.points*24,last.y+24,a.z+s.dz*#s.points*24)
   local accepted=q and math.abs(q.y-last.y)<=32 and self:away(q,player)
    and self:_width(q,s.dx,s.dz,s.visual and 32) and self:segment(last,q,player)
   if accepted and s.visual then
    -- A shorter real segment is preferable to entering a corner that the raised
    -- whole-pair envelope cannot clear. This is only a numeric discovery prefix;
    -- contact still performs an entirely fresh presentation proof every tick.
    accepted=self:raisedPresentation(last,q,{a=a,b=q,shapeSource=s.source,visual=s.visual},
     {frame=ctx.frame,player=player})~=nil
   end
   if accepted then
    s.points[#s.points+1]=cp(q)
    if #s.points>=(s.nearGeneric and 25 or s.maxPoints or 25) then s.phase=3;s.exitIndex=1;break end
   elseif #s.points>=4 then s.phase=3;s.exitIndex=1;break
   else nextCandidate(s);break end
  end
  return nil
 elseif s.phase==3 then
  local last=s.points[#s.points];local o=exits[s.exitIndex]
  if not o then nextCandidate(s);return nil end
  s.exitIndex=s.exitIndex+1
  -- Raised rails try the player's side first, without removing either side.
  -- Freeze ordering for this candidate so a moving player cannot duplicate or
  -- skip offsets. Every candidate still needs current support and exit proof.
  if s.exitSide==nil then
   local side=(player.x-last.x)*(-s.dz)+(player.z-last.z)*s.dx
   s.exitSide=s.visual and side<0 and -1 or 1
  end
  local lateral=o[2]*s.exitSide
  local q=self:floor(last.x+s.dx*o[1]-s.dz*lateral,last.y+180,last.z+s.dz*o[1]+s.dx*lateral)
  if q and self:away(q,player) and self:support(q,64) then s.exit=cp(q);s.phase=4 end
  return nil
 end
 -- All retained hints are checked again NOW. No earlier frame's probe results
 -- certify entry, segment, width, exit support or exit flight in the returned plan.
 local points={};local width
 for i,hint in ipairs(s.points) do
  local q=self:floor(hint.x,hint.y+24,hint.z)
  if not q or math.abs(q.y-hint.y)>2 or not self:away(q,player) then nextCandidate(s);return nil end
  local w=self:_width(q,s.dx,s.dz,s.visual and 32)
  if not w or (i==1 and not self:clear(q)) then nextCandidate(s);return nil end
  if i>1 and not self:segment(points[i-1],q,player) then nextCandidate(s);return nil end
  width=width and math.min(width,w) or w;points[i]=cp(q)
 end
 local exit=self:support(s.exit,64)
 if not exit or math.abs(exit.y-s.exit.y)>2 or not self:away(exit,player) then s.phase=3;return nil end
 local a,b=points[1],points[#points]
 local arc=self:arc(b,exit,60,player)
 if not arc then s.phase=3;return nil end
 self:invalidateRails()
 return {kind='grind',feature='two-sided-rail',a=a,b=b,entry=cp(a),exit=cp(exit),exitArc=arc,
  width=width,points=points,continuousClearance=false,method='finite-native-probes',validatedFrame=ctx.frame,epoch=ctx.epoch,indexKey=s.indexKey,shapeSource=s.source,visual=s.visual}
end
M.railScan=guarded(M._railScanStep)

-- Raised geometry has a distinct visual top. This is a fresh finite sampled
-- presentation envelope, not continuous mesh collision or altered Mario terrain.
local function samePoint(a,b) return pt(a) and pt(b) and a.x==b.x and a.y==b.y and a.z==b.z end
local function sameLine(a,b) return a and b and samePoint(a.a,b.a) and samePoint(a.b,b.b) end
local function sameFace(a,b)
 if not a or not b or a.type~=b.type then return false end
 for i=1,3 do if not samePoint(a.vertices[i],b.vertices[i]) then return false end end
 return true
end
local function connectedFace(a,b)
 local shared=0
 for _,v in ipairs(a.vertices) do for _,w in ipairs(b.vertices) do if samePoint(v,w) then shared=shared+1;break end end end
 return shared>=2
end
function M:_raisedWidth(p,dx,dz,supports)
 local edges={}
 for _,sign in ipairs({-1,1}) do
  local edge
  for radius=6,102,6 do
   local f=self:floor(p.x-dz*radius*sign,p.y+32,p.z+dx*radius*sign)
   if not f then
    local height=self:_native('find_floor',p.x-dz*radius*sign,p.y+32,p.z+dx*radius*sign)
    if num(height) and height>-10000 and height<p.y-28 then edge=radius;break end
    return nil
   end
   if f.y<p.y-28 then edge=radius;break end
   if math.abs(f.y-p.y)>32 then return nil end
   local own=false
   for _,support in ipairs(supports) do if sameFace(f,support) then own=true;break end end
   if not own then return nil end
  end
  if not edge then return nil end;edges[#edges+1]=edge
 end
 local width=edges[1]+edges[2]-6
 return width>=12 and width<=90 and width or nil
end
local RAISED_HEIGHTS={8,32,64,128,192,256,360}
function M:_raisedClear(p,players,supports)
 if not pt(p) then return nil end
 for _,player in ipairs(players) do if not self:away(p,player) then return self:deny('raised-player-clearance') end end
 for i=0,8 do
  local o=SUPPORT_OFFSETS[i];local x,z=p.x+(o and o[1]*116 or 0),p.z+(o and o[2]*116 or 0)
  local ceiling,cs=self:_native('find_ceil',x,p.y+4,z)
  if not num(ceiling) or ceiling<p.y+364 then return self:deny('raised-ceiling-clearance') end
  if cs and (not pt(cs.normal) or not pt(cs.vertex1) or not pt(cs.vertex2) or not pt(cs.vertex3)) then return nil end
  cs=nil
  local water,gas=self:_native('find_water_level',x,z),self:_native('find_poison_gas_level',x,z)
  if not num(water) or not num(gas) or water>=p.y-4 or gas>=p.y-4 then return self:deny('raised-wet-envelope') end
  local height=self:_native('find_floor',x,p.y+360,z)
  if not num(height) then return nil end
  if height>p.y+4 and height<=p.y+360 then
   -- The source map's invisible sloped cap may sit above the rendered wood.
   -- Exempt only an EXACT freshly checked supporting triangle, never a nearby
   -- unrelated low floor, moving object, or old captured Surface userdata.
   local own=false
   if height<=p.y+32 then
    local floor=self:floor(x,p.y+360,z)
    for _,support in ipairs(supports) do if sameFace(floor,support) then own=true;break end end
   end
   if not own then return self:deny('raised-body-terrain') end
  end
 end
 local q=cp(p)
 for _,height in ipairs(RAISED_HEIGHTS) do
  q.x,q.y,q.z=p.x,p.y,p.z
  local wall=self:_native('resolve_and_return_wall_collisions',q,height,116)
  if wall~=nil or not pt(q) or dist(q,p)>.01 then return self:deny('raised-wall-clearance') end
 end
 return true
end
M.raisedPresentation=guarded(function(self,previous,q,rail,ctx)
 if not RailPresentation or not self.surfaceRails or not pt(previous) or not pt(q) or not rail
  or rail.shapeSource~='static-surface-edge' or not rail.visual or not ctx or not num(ctx.frame) then return nil end
 local dx,dz=rail.b.x-rail.a.x,rail.b.z-rail.a.z;local length=math.sqrt(dx*dx+dz*dz)
 if length<1 then return nil end;dx,dz=dx/length,dz/length
 local visual=self.surfaceRails:visible(q,dx,dz,false,self.surfaceBudget)
 if not sameLine(visual,rail.visual) then return self:deny('raised-visible-line-changed') end
 local vx,vz=visual.b.x-visual.a.x,visual.b.z-visual.a.z
 local sign=vx*dx+vz*dz>=0 and 1 or -1
 local incline=math.atan((visual.b.y-visual.a.y)/math.sqrt(vx*vx+vz*vz))*sign
 local heading=math.abs(q.x-previous.x)+math.abs(q.z-previous.z)>.01 and math.atan(q.x-previous.x,q.z-previous.z) or (previous.yaw or math.atan(dx,dz))
 -- Native object positions are float32; certify that exact render root without
 -- rounding or changing the companion's double-precision physics state.
 local function f32(n) return (string.unpack('f',string.pack('f',n))) end
 previous={x=f32(previous.x),y=f32(previous.y),z=f32(previous.z)}
 q={x=f32(q.x),y=f32(q.y),z=f32(q.z)}
 local native={yaw=(math.floor(heading*32768/math.pi)-16384)%65536,pitch=0,roll=math.floor(incline*32768/math.pi)}
 local function anchor(root)
  return RailPresentation.compute{root=root,rail={a=visual.a,b=visual.b,verified=true},heading=heading,incline=incline,
   native=native,clip='jimmie_original_v1_board_balance042',blend=1,safetyMargin=6.66}
 end
 local first,last=anchor(previous),anchor(q)
 if not first.ok or not last.ok then return self:deny('raised-anchor-'..tostring(not first.ok and first.reason or last.reason)) end
 local roots={previous};if not samePoint(previous,q) then roots[#roots+1]=q end
 local supports={}
 for _,p in ipairs(roots) do
  local matched=self.surfaceRails:visible(p,dx,dz,false,self.surfaceBudget)
  if not sameLine(matched,visual) then return self:deny('raised-span-outside-visible') end
  for _,offset in ipairs({-35.34,0,35.34}) do
   local f=self:floor(p.x+dx*offset,p.y+32,p.z+dz*offset)
   if not f or math.abs(f.y-p.y)>32 or math.abs(-dz*f.normal.x+dx*f.normal.z)<.12
    or not sameLine(self.surfaceRails:visible(f,dx,dz,false,self.surfaceBudget),visual) then return self:deny('raised-truck-support') end
   supports[#supports+1]=f
  end
 end
 -- Read both sides of a crowned support. Add only faces connected by a full
 -- edge to the just-observed cap, and independently matched to the same visible
 -- line. This handles the two triangles per side without exempting another rail.
 local neighbors={}
 for _,p in ipairs(roots) do
  for offset=-42,42,6 do
   local f=self:floor(p.x-dz*offset,p.y+32,p.z+dx*offset)
   if f and math.abs(f.y-p.y)<=32 and math.abs(-dz*f.normal.x+dx*f.normal.z)>=.12
    and sameLine(self.surfaceRails:visible(f,dx,dz,false,self.surfaceBudget),visual) then neighbors[#neighbors+1]=f end
  end
 end
 for _=1,4 do
  local changed=false
  for i=#neighbors,1,-1 do
   local f=neighbors[i]
   for _,support in ipairs(supports) do
    if connectedFace(f,support) then supports[#supports+1]=f;table.remove(neighbors,i);changed=true;break end
   end
  end
  if not changed then break end
 end
 for _,p in ipairs(roots) do
  if not self:_raisedWidth(p,dx,dz,supports) then return self:deny('raised-width-changed') end
 end
 local players=ctx.players or {ctx.player}
 -- Exact success reuse is local to this one synchronous certificate. The same
 -- players and freshly collected support set apply; nothing survives the call.
 local cleared={}
 local function clearPoint(p)
  local xs=cleared[p.x];local ys=xs and xs[p.y]
  if ys and ys[p.z] then return true end
  if not self:_raisedClear(p,players,supports) then return nil end
  cleared[p.x]=cleared[p.x] or {};xs=cleared[p.x];xs[p.y]=xs[p.y] or {};xs[p.y][p.z]=true
  return true
 end
 local function sweep(a,b)
  local n=math.max(1,math.ceil(dist(a,b)/8))
  for i=0,n do if not clearPoint(mix(a,b,i/n)) then return nil end end
  return true
 end
 -- Check turning on/off the graphics correction as well as this tick's travel.
 if not sweep(previous,q) or not sweep(previous,first.root) or not sweep(first.root,last.root) or not sweep(last.root,q) then return nil end
 return {visual={a=cp(visual.a),b=cp(visual.b)},physical=cp(q),heading=heading,incline=incline,
  certifiedDelta=cp(last.delta),native=native,certificateFrame=ctx.frame,
  maxTruckResidual=last.maxTruckResidual,method='finite-native-shifted-envelope',radius=116,top=360}
end)


-- Trim only a prefix the actor has actually reached on the ORIGINAL segment.
-- No lateral translation, endpoint extension, cached clearance or pace-gate change.
M.trimRail=guarded(function(self,p,rail,player)
 player=player and (player.pos or player)
 if not pt(p) or not pt(player) or not rail or rail.kind~='grind'
  or not pt(rail.a) or not pt(rail.b) or not pt(rail.exit) then return nil end
 local a,b=rail.a,rail.b
 local dx,dz=b.x-a.x,b.z-a.z;local length=math.sqrt(dx*dx+dz*dz)
 if length<72 or length>600 then return nil end
 local t=((p.x-a.x)*dx+(p.z-a.z)*dz)/(length*length)
 if t<0 or t>1 or (1-t)*length<72 then return nil end
 local start=mix(a,b,t)
 if (p.x-start.x)^2+(p.z-start.z)^2>8^2 or math.abs(p.y-start.y)>12 then return nil end
 -- Actor's actual feet also need native safe support; proximity to a rail line
 -- alone must not claim contact from empty space or a lower neighbouring floor.
 local contact=self:floor(p.x,p.y+24,p.z)
 if not contact or math.abs(contact.y-p.y)>12 or math.abs(contact.y-start.y)>2
  or not self:away(p,player) or not self:clear(p) then return nil end
 local points={};local width;local count=math.max(1,math.ceil(dist(start,b)/24))
 for i=0,count do
  local hint=mix(start,b,i/count)
  local q=self:floor(hint.x,hint.y+24,hint.z)
  if not q or math.abs(q.y-hint.y)>2 or not self:away(q,player) then return nil end
  local w=self:_width(q,dx/length,dz/length,rail.visual and 32)
  if not w or (i==0 and not self:clear(q)) then return nil end
  if i>0 and not self:segment(points[#points],q,player) then return nil end
  width=width and math.min(width,w) or w;points[#points+1]=cp(q)
 end
 local exit=self:support(rail.exit,64)
 if not exit or math.abs(exit.y-rail.exit.y)>2 or not self:away(exit,player) then return nil end
 local arc=self:arc(points[#points],exit,60,player)
 if not arc then return nil end
 return {kind='grind',feature='two-sided-rail',a=points[1],b=points[#points],entry=cp(points[1]),
  exit=cp(exit),exitArc=arc,width=width,points=points,continuousClearance=false,
  method='finite-native-probes',trimmedPrefix=t*length,indexKey=rail.indexKey,shapeSource=rail.shapeSource,visual=rail.visual}
end)

M.validateRail=guarded(function(self,rail,player)
 if not rail or rail.kind~='grind' or not pt(rail.a) or not pt(rail.b) or not pt(rail.exit) then return nil end
 local dx,dz=rail.b.x-rail.a.x,rail.b.z-rail.a.z
 local length=math.sqrt(dx*dx+dz*dz)
 if length<72 or length>600 then return nil end
 local count=math.ceil(dist(rail.a,rail.b)/24);local points={};local width
 for i=0,count do
  local hint=mix(rail.a,rail.b,i/count)
  local q=self:floor(hint.x,hint.y+24,hint.z)
  if not q or math.abs(q.y-hint.y)>2 or not self:away(q,player) then return nil end
  local w=self:_width(q,dx/length,dz/length,rail.visual and 32)
  if not w or (i==0 and not self:clear(q)) then return nil end
  if i>0 and not self:segment(points[#points],q,player) then return nil end
  width=width and math.min(width,w) or w;points[#points+1]=cp(q)
 end
 local exit=self:support(rail.exit,64)
 if not exit or math.abs(exit.y-rail.exit.y)>2 or not self:away(exit,player) then return nil end
 local arc=self:arc(points[#points],exit,60,player)
 if not arc then return nil end
 return {kind='grind',feature='two-sided-rail',a=points[1],b=points[#points],entry=cp(points[1]),
  exit=cp(exit),exitArc=arc,width=width,points=points,continuousClearance=false,method='finite-native-probes',indexKey=rail.indexKey,shapeSource=rail.shapeSource,visual=rail.visual}
end)

return M



