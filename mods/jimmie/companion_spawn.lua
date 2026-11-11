-- Bounded, same-frame placement for the complete cosmetic companion pair.
-- Native queries read scratch tables only. No Mario, collision or save writes.
local Deck=require("performance_submarine_support")
local S={};S.__index=S
S.RADIUS=64;S.TOP=212
local function finite(n)return type(n)=='number' and n==n and math.abs(n)<1e8 end
local function point(p)return p and finite(p.x) and finite(p.y) and finite(p.z) end
local function same(a,b)
 return a and b and a.terrain==b.terrain and a.areaObject==b.areaObject and a.level==b.level and a.area==b.area and a.act==b.act
end
function S.new(g)return setmetatable({g=g or _G,cursor=0,nextTry=0},S)end
function S:invalidate()self.activeDeck=nil;self.deck=nil;self.scene=nil;self.since=nil;self.nextTry=0;self.cursor=0 end
function S:stamp(m)
 local g=self.g;local n=g.gNetworkPlayers and g.gNetworkPlayers[0]
 local terrain=g.smlua_collision_util_get_current_terrain_collision()
 if not n or not m or not m.area or not terrain then return nil end
 return {terrain=terrain,areaObject=m.area,level=n.currLevelNum,area=n.currAreaIndex,act=n.currActNum}
end
function S:observe(m)
 local ok,scene=pcall(self.stamp,self,m)
 if not ok then scene=nil end
 if same(scene,self.scene) then
  if not self.activeDeck or Deck.current(self.g)==self.activeDeck then return false end
  self:invalidate();self.scene=scene;self.since=self.g.get_global_timer();return true
 end
 local changed=self.scene~=nil or scene~=nil
 self:invalidate();self.scene=scene
 if scene then self.since=self.g.get_global_timer() end
 return changed
end
function S:query(name,...)
 self.calls=self.calls+1
 if self.calls>900 or self.g.clock_elapsed_f64()-self.started>.006 then error('spawn-budget') end
 return self.g[name](...)
end
function S:floor(x,y,z)
 local h,s=self:query('find_floor',x,y+48,z)
 if not finite(h) or h< -10000 or not s or not s.normal or not finite(s.normal.y) or s.normal.y<.72 or math.abs(h-y)>64 then return nil end
 if not Deck.surface(self.g,s,self.deck) then return nil end
 for _,name in ipairs({'SURFACE_BURNING','SURFACE_DEATH_PLANE','SURFACE_INSTANT_QUICKSAND','SURFACE_DEEP_QUICKSAND',
  'SURFACE_DEEP_MOVING_QUICKSAND','SURFACE_INSTANT_MOVING_QUICKSAND','SURFACE_VERTICAL_WIND'}) do
  if self.g[name]~=nil and s.type==self.g[name] then return nil end
 end
 local water=self:query('find_water_level',x,z);local gas=self:query('find_poison_gas_level',x,z)
 if not finite(water) or not finite(gas) or water>=h-4 or gas>=h-4 then return nil end
 return h
end
function S:walls(x,y,z,r)
 for _,height in ipairs({4,32,72,112,160,208}) do
  local p={x=x,y=y,z=z};local wall=self:query('resolve_and_return_wall_collisions',p,height,r)
  if wall~=nil or not point(p) or math.abs(p.x-x)>.05 or math.abs(p.y-y)>.05 or math.abs(p.z-z)>.05 then return false end
 end
 return true
end
function S:check(q,m)
 local h=self:floor(q.x,m.floorHeight,q.z)
 if not h then return nil,'floor' end
 q={x=q.x,y=h,z=q.z}
 for _,dx in ipairs({-S.RADIUS,0,S.RADIUS}) do for _,dz in ipairs({-S.RADIUS,0,S.RADIUS}) do
  local side=self:floor(q.x+dx,h,q.z+dz)
  if not side or math.abs(side-h)>40 then return nil,'footprint' end
  local ceiling=self:query('find_ceil',q.x+dx,h+2,q.z+dz)
  if not finite(ceiling) or ceiling<h+S.TOP then return nil,'ceiling' end
 end end
 if not self:walls(q.x,h,q.z,S.RADIUS) then return nil,'wall' end
 -- Reject an apparently clear destination on the far side of a wall.
 local dx,dz=q.x-m.pos.x,q.z-m.pos.z;local steps=math.ceil(math.sqrt(dx*dx+dz*dz)/24)
 local previous=m.floorHeight
 for i=1,steps do
  local x,z=m.pos.x+dx*i/steps,m.pos.z+dz*i/steps
  local y=self:floor(x,previous,z)
  if not y or math.abs(y-previous)>40 or not self:walls(x,y,z,28) then return nil,'blocked-route' end
  previous=y
 end
 return q,'clear'
end
function S:_select(m)
 local g=self.g
 self:observe(m)
 local frame=g.get_global_timer()
 if not self.scene or not finite(frame) or frame-self.since<2 then return nil,'scene-settling' end
 if not m.marioObj or not point(m.pos) or not point(m.vel) or not finite(m.floorHeight) or m.action==0
  or math.abs(m.pos.y-m.floorHeight)>4 or math.abs(m.vel.y)>4 then return nil,'player-airborne' end
 if g.ACT_GROUP_MASK and g.ACT_GROUP_CUTSCENE and (m.action & g.ACT_GROUP_MASK)==g.ACT_GROUP_CUTSCENE then return nil,'player-transition' end
 if g.get_current_play_mode()~=(g.PLAY_MODE_NORMAL or 0) or g.is_game_paused() then return nil,'not-gameplay' end
 if math.abs(m.pos.x)>7600 or math.abs(m.pos.z)>7600 or math.abs(m.pos.y)>14000 then return nil,'coordinate-bound' end
 if frame<self.nextTry then return nil,'retry-delay' end
 self.nextTry=frame+6;self.calls=0;self.started=g.clock_elapsed_f64()
 self.deck=nil
 if self.scene.level==23 and self.scene.area==2 then self.deck=Deck.standing(g,m) end
 local scene=self.scene;local yaw=(m.faceAngle.y or 0)*math.pi/32768
 local last='no-clear-placement';local begin=self.cursor
 for step=0,23 do
  local index=(begin+step)%24;self.cursor=(index+1)%24
  local radius=({160,240,320})[math.floor(index/8)+1]
  local angle=yaw+({2,-2,3,-3,4,1,-1,0})[index%8+1]*math.pi/4
  local q={x=math.floor(m.pos.x+math.sin(angle)*radius+.5),z=math.floor(m.pos.z+math.cos(angle)*radius+.5)}
  local found,why=self:check(q,m);last=why
  if found then
   if not same(scene,self:stamp(m)) or g.get_global_timer()~=frame then return nil,'scene-changed' end
   self.cursor=0;self.nextTry=0
   if self.deck and Deck.current(g)~=self.deck then return nil,'deck-changed' end
   self.activeDeck=self.deck
   return found,'clear' 
  end
 end
 return nil,last
end
function S:select(m)
 local ok,q,why=pcall(self._select,self,m)
 if not ok then self.lastReason='native-read-or-budget';return nil,self.lastReason end
 self.lastReason=why;return q,why
end
return S
