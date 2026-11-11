-- Geometry-derived candidate hints only. Never a collision certificate.
-- Copies numeric static floor data at load; no Surface, object or Mario writes.
local R={};R.__index=R
local visibleOK,Visible=pcall(require,'skate_visible_rails')
if not visibleOK or type(Visible)~='table' then Visible=nil end
local function finite(n)return type(n)=='number' and n==n and math.abs(n)<30000 end
local function point(p)return p and finite(p.x) and finite(p.y) and finite(p.z) end
local function copy(p)return {x=p.x,y=p.y,z=p.z} end
local function clamp(x,a,b)return math.max(a,math.min(b,x)) end
local function mid(a,b)return {x=(a.x+b.x)*.5,y=(a.y+b.y)*.5,z=(a.z+b.z)*.5} end
local function key(p)return string.format('%.3f,%.3f,%.3f',p.x,p.y,p.z) end
function R.new(g)
 local self=setmetatable({g=g or _G,allowed={},limit=2048},R)
 for _,name in ipairs({'SURFACE_DEFAULT','SURFACE_HARD','SURFACE_NOT_SLIPPERY','SURFACE_HARD_NOT_SLIPPERY','SURFACE_NO_CAM_COLLISION','SURFACE_SLIPPERY','SURFACE_VERY_SLIPPERY','SURFACE_HARD_SLIPPERY','SURFACE_HARD_VERY_SLIPPERY'}) do
  local v=self.g[name];if finite(v) then self.allowed[v]=true end
 end
 self:clear(nil);return self
end
function R:clear(scene)
 self.scene=scene;self.generation=(self.generation or 0)+1;self.segments={};self.seen={}
 self.stats={surfaces=0,candidates=0,rejected=0};self.error=nil
end
function R:add(surface,dynamic,scene)
 if scene~=self.scene then self:clear(scene) end
 if not surface or dynamic==true or surface.object~=nil then return false end
 local g=self.g;local kind,flags,pool=surface.type,surface.flags,surface.poolType
 if not finite(g.SURFACE_POOL_STATIC) or pool~=g.SURFACE_POOL_STATIC or not self.allowed[kind]
  or not finite(flags) or flags%1~=0 or not finite(g.SURFACE_FLAG_DYNAMIC) or not finite(g.SURFACE_FLAG_INTANGIBLE)
  or (flags & (g.SURFACE_FLAG_DYNAMIC|g.SURFACE_FLAG_INTANGIBLE))~=0 then return false end
 local nr=surface.normal;if not nr then return false end
 local n=copy(nr);if not point(n) or n.y<.65 or n.y>1.001 then return false end
 local v={};for i=1,3 do local q=surface['vertex'..i];if not q then return false end;v[i]=copy(q);if not point(v[i]) then return false end end
 self.stats.surfaces=self.stats.surfaces+1
 local longest=0;local edges={}
 for i=1,3 do
  local a,b,c=v[i],v[i%3+1],v[(i+1)%3+1]
  local dx,dz=b.x-a.x,b.z-a.z;local length=math.sqrt(dx*dx+dz*dz)
  edges[#edges+1]={a=a,b=b,c=c,length=length};longest=math.max(longest,length)
 end
 if longest<120 then return false end
 local added=false
 for _,e in ipairs(edges) do
  if e.length>=120 and e.length>=longest*.85 then
   local dx,dz=(e.b.x-e.a.x)/e.length,(e.b.z-e.a.z)/e.length
   local width=math.abs((e.c.x-e.a.x)*dz-(e.c.z-e.a.z)*dx)
   local grade=(e.b.y-e.a.y)/e.length
   -- Skinny triangulation is only a hint: live two-sided width still decides.
   local crossSlope=math.abs(-dz*n.x+dx*n.z)
   if width>=12 and width<=90 and math.abs(grade)<=.8 and crossSlope>=.12 then
    local variants={{mid(e.a,e.c),mid(e.b,e.c),'mid-cap'}}
    local projected=(e.c.x-e.a.x)*dx+(e.c.z-e.a.z)*dz
    local edgeHeight=e.a.y+grade*projected
    if edgeHeight-e.c.y>=8 then
     -- Native cap-side walls can reach the high edge. A point two units inside
     -- that measured edge is a candidate above them, not waived wall clearance.
     local t=2/width
     local function inside(a)return {x=a.x+(e.c.x-a.x)*t,y=a.y+(e.c.y-a.y)*t,z=a.z+(e.c.z-a.z)*t}end
     variants[#variants+1]={inside(e.a),inside(e.b),'crest-interior'}
    end
    for _,variant in ipairs(variants) do
     local a,b=variant[1],variant[2]
     local ka,kb=key(a),key(b);local signature=ka<kb and ka..':'..kb or kb..':'..ka
     if not self.seen[signature] and #self.segments<self.limit then
      self.seen[signature]=true
      local id=#self.segments+1
      self.segments[id]={a=a,b=b,dx=dx,dz=dz,length=math.sqrt((b.x-a.x)^2+(b.z-a.z)^2),grade=grade,id=id,
       crossSlope=math.abs(-dz*n.x+dx*n.z),kind=kind,seed=variant[3]}
      added=true
     end
    end
   end
  end
 end
 self.stats.candidates=#self.segments;return added
end
function R:visible(p,dx,dz,needRemaining,budget,sceneChecked)
 local g=self.g;local np=g.gNetworkPlayers and g.gNetworkPlayers[0]
 if self.bound and not sceneChecked then
  local scene;if budget then scene=budget.scene() else scene=g.smlua_collision_util_get_current_terrain_collision() end
  local ok=true
  if not ok or scene==nil or scene~=self.scene then return nil end
 end
 if not Visible or not np then return nil end
 local best,score
 for _,map in ipairs(Visible.maps or {}) do
  if g[map.level] and np.currLevelNum==g[map.level] and np.currAreaIndex==map.area then
   for i,v in ipairs(map.segments) do
    if i>512 then break end
    if budget and i%16==1 then budget.tick() end
    local ax,ay,az,bx,by,bz=table.unpack(v)
    local x,z=bx-ax,bz-az;local length=math.sqrt(x*x+z*z)
    local ux,uz=x/length,z/length;local dot=ux*dx+uz*dz
    if math.abs(dot)>=.995 then
     local along=(p.x-ax)*ux+(p.z-az)*uz
     if along>=42 and along<=length-42 then
      local t=along/length;local q={x=ax+x*t,y=ay+(by-ay)*t,z=az+z*t}
      local lateral=math.sqrt((q.x-p.x)^2+(q.z-p.z)^2)
      local remaining=dot>0 and length-42-along or along-42
      local cost=lateral+math.abs(q.y-p.y)
      if lateral<=24 and math.abs(q.y-p.y)<=28 and (not needRemaining or remaining>=72)
       and (not score or cost<score) then
       best={a={x=ax,y=ay,z=az},b={x=bx,y=by,z=bz},point=q,remaining=remaining,
        source='verified-static-alpha',level=map.level,area=map.area};score=cost
      end
     end
    end
   end
  end
 end
 return best
end
function R:near(p,player,fx,fz,frame,deferred,budget)
 local hints={}
 local np=self.g.gNetworkPlayers and self.g.gNetworkPlayers[0];local mapped=false
 for _,map in ipairs(Visible and Visible.maps or {}) do
  if np and self.g[map.level] and np.currLevelNum==self.g[map.level] and np.currAreaIndex==map.area then mapped=true;break end
 end
 if not mapped then return hints end
 if not point(p) or not point(player) or self.error then return hints end
 if self.bound then
  local scene;if budget then scene=budget.scene() else scene=self.g.smlua_collision_util_get_current_terrain_collision() end
  if scene==nil or scene~=self.scene then return hints end
 end
 for i=1,math.min(#self.segments,self.limit) do
  if budget and i%8==1 then budget.tick() end
  local s=self.segments[i];local projected=(p.x-s.a.x)*s.dx+(p.z-s.a.z)*s.dz
  for _,sign in ipairs({1,-1}) do
   -- A modest longitudinal lead gives a flat rail actual landing momentum.
   -- This is a candidate, not a forced boost or a moved actor.
   for variant,lead in ipairs({180,0}) do
    local along=clamp(projected+sign*lead,12,math.max(12,s.length-12))
    local q={x=s.a.x+s.dx*along,y=s.a.y+s.grade*along,z=s.a.z+s.dz*along}
    local d=math.sqrt((q.x-p.x)^2+(q.z-p.z)^2)
    local gap=math.sqrt((q.x-player.x)^2+(q.z-player.z)^2)
    local id=100000+s.id*4+(sign==1 and 0 or 2)+variant-1
    local advance=((q.x-p.x)*s.dx+(q.z-p.z)*s.dz)*sign
    local entryMomentum=variant==1 and advance>=144
    local contact=variant==2 and d<=8 and math.abs(q.y-p.y)<=12
    -- Player distance ranks optional hints; it is not a collision veto.
    if (entryMomentum or contact) and d<=500 and math.abs(q.y-p.y)<=180 and (not deferred or not deferred[id] or frame>=deferred[id]) then
     local dx,dz=s.dx*sign,s.dz*sign
     local visual=self:visible(q,dx,dz,true,budget,true)
     if visual then
     local vx,vz=visual.b.x-visual.a.x,visual.b.z-visual.a.z
     local vl=math.sqrt(vx*vx+vz*vz);local orientation=vx*dx+vz*dz>=0 and 1 or -1
     dx,dz=vx/vl*orientation,vz/vl*orientation
     hints[#hints+1]={x=q.x,y=q.y,z=q.z,dx=dx,dz=dz,key=id,source='static-surface-edge',seed=s.seed,
      points=math.min(25,math.floor(visual.remaining/24)+1),visual=visual,
      score=d+.2*gap+40*(1-dx*fx-dz*fz)+(variant==2 and 28 or 0)-32}
     -- Bounded top24 insertion; never sort thousands of generated candidates.
     if #hints>24 then
      local worst=1;for j=2,#hints do if hints[j].score>hints[worst].score then worst=j end end
      table.remove(hints,worst)
     end
     end
    end
   end
  end
 end
 return hints
end
function R:bind()
 local g=self.g
 if self.bound then return true end
 if type(g.hook_event)~='function' or type(g.smlua_collision_util_get_current_terrain_collision)~='function'
  or g.HOOK_ON_ADD_SURFACE==nil or g.HOOK_ON_CLEAR_AREAS==nil then return false end
 g.hook_event(g.HOOK_ON_CLEAR_AREAS,function()self:clear(nil)end)
 g.hook_event(g.HOOK_ON_ADD_SURFACE,function(s,dynamic)
  local ok=pcall(function()
   local scene=g.smlua_collision_util_get_current_terrain_collision()
   if scene~=nil then self:add(s,dynamic,scene) end
  end)
  if not ok then self.error='surface-copy-failed' end
 end)
 self.bound=true;return true
end
return R
