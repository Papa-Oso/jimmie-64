-- STAGED: request policy plus bounded read-only native candidate search.
-- The only position/pose commit lives in main, after canCommit() in the same call.
local Native=require('native_rejoin')
local Policy=require('rejoin_policy')
local H={};H.__index=H
local function finite(v) return type(v)=='number' and v==v and math.abs(v)<1e8 end
local function cp(v) return {x=v.x,y=v.y,z=v.z} end
local function sameScene(a,b)
 return a and b and a.epoch==b.epoch and a.terrain==b.terrain and a.level==b.level and a.area==b.area and a.act==b.act
end
function H.new(g,owns)
 assert(type(owns)=="function","exact owned body/board/brace callback required")
 local self=setmetatable({g=g,policy=Policy.new(),attempts=0,owns=owns},H)
 -- A private API view imposes ONE deadline on all native candidate checks.
 -- It does not change the engine clock or native module source.
 local api=setmetatable({}, {__index=g})
 api.clock_elapsed_f64=function()
  local t=g.clock_elapsed_f64()
  if not finite(t) or (self.started and (t<self.started or t-self.started>.006)) then error('whole-search-budget') end
  return t
 end
 self.native=Native.new(api)
 return self
end
function H:invalidate()
 if self.offer then self:resolve(self.offer,false) end
 self.native:invalidate();self.sceneStamp=nil;self.scene=nil;self.offer=nil
 self.policy:clearEvidence()
end
function H:pause()
 if self.offer then self:resolve(self.offer,false) end
 self.policy:clearEvidence();self.offer=nil
end
function H:ready(o,id,board,boardId,brace)
 local g=self.g
 for _,name in ipairs({'obj_get_model_id_extended','obj_set_gfx_pos','obj_set_gfx_angle','obj_skip_interpolation','clock_elapsed_f64'}) do
  if type(g[name])~='function' then return false end
 end
 if not o or not board or o==board or not self.owns(o,board,brace) then return false end
 for _,entry in ipairs({{o,id},{board,boardId}}) do
  local actor,model=entry[1],entry[2]
  if not finite(model) or model<=0 or model==g.E_MODEL_ERROR_MODEL or actor.activeFlags==0 or g.obj_get_model_id_extended(actor)~=model then return false end
  local gfx=actor.header and actor.header.gfx
  if not gfx or not gfx.animInfo or gfx.throwMatrix~=nil or actor.oGraphYOffset~=0 then return false end
  local scale=gfx.scale;if not scale then return false end
  for _,k in ipairs({'x','y','z'}) do if not finite(scale[k]) or math.abs(scale[k]-.62)>1e-6 then return false end end
 end
 if brace and brace.activeFlags==0 then return false end
 return true
end
function H:_step(dt,s)
 if self.offer then self:resolve(self.offer,false) end
 self.offer=nil;self.attempts=0
 local stamp=self.native:stamp()
 if not stamp then self:pause();return nil,'missing-scene' end
 if not sameScene(stamp,self.sceneStamp) then
  -- An area change needs an epoch even when terrain allocation is reused.
  self.native:invalidate();stamp=self.native:stamp();self.scene={};self.sceneStamp=stamp
 end
 s.scene=self.scene;s.frame=stamp.frame
 local request,reason=self.policy:step(dt,s)
 if not request then return nil,reason end
 local function refused(why)
  self.policy:resolve(request.id,false);return nil,why
 end
 if not self:ready(s.object,s.idleModel,s.board,s.boardModel,s.brace) then return refused('unverified-live-model-transform') end
 self.started=self.g.clock_elapsed_f64()
 if not finite(self.started) then self.started=nil;return refused('invalid-search-clock') end
 s.ownedObjects={[s.object]=true,[s.board]=true}
 if s.brace then s.ownedObjects[s.brace]=true end
 local yaw=s.yaw
 if not finite(yaw) then self.started=nil;return refused('invalid-heading') end
 local last='no-candidate'
 -- Side first, then rear/front alternatives. Radius is destination spacing only.
 for _,radius in ipairs({240,300,360}) do
  for _,quarter in ipairs({2,-2,3,-3,4,1,-1,0}) do
   local t=self.g.clock_elapsed_f64()
   if not finite(t) or t<self.started or t-self.started>.006 then
    self.started=nil;return refused('whole-search-budget')
   end
   local angle=yaw+quarter*math.pi/4
   local q={x=s.mario.x+math.sin(angle)*radius,y=s.mario.y,z=s.mario.z+math.cos(angle)*radius}
   self.attempts=self.attempts+1
   local proof,why=self.native:propose(q,{stamp=stamp,profileId=Native.PROFILE.id,
    pose=Native.PROFILE.pose,scale=.62,pitch=0,roll=0,ownedObjects=s.ownedObjects,allowNativeFiniteProbes=true})
   if proof then
    self.offer={request=request,proof=proof,object=s.object,idleModel=s.idleModel,yaw=yaw,
     mario=cp(s.mario),started=self.started,attempts=self.attempts,board=s.board,boardModel=s.boardModel,brace=s.brace}
    self.started=nil;return self.offer,'proposal'
   end
   last=why or last
  end
 end
 self.started=nil;return refused(last)
end
function H:step(dt,s)
 local ok,offer,why=pcall(self._step,self,dt,s)
 self.started=nil
 if not ok then
  if self.policy.pending then self.policy:resolve(self.policy.pending,false) end
  self:pause();return nil,'host-read-failed'
 end
 self.lastDecision=why
 return offer,why
end
function H:canCommit(offer,o,id)
 local ok,valid=pcall(function()
  if offer~=self.offer or not offer or o~=offer.object or id~=offer.idleModel or not self:ready(o,id,offer.board,offer.boardModel,offer.brace) then return false end
  local t=self.g.clock_elapsed_f64()
  if not finite(t) or t<offer.started or t-offer.started>.006 then return false end
  local m=self.g.gMarioStates[0]
  if not m or m.pos.x~=offer.mario.x or m.pos.y~=offer.mario.y or m.pos.z~=offer.mario.z then return false end
  return self.native:fresh(offer.proof.stamp)==true and self.policy.pending==offer.request.id
 end)
 return ok and valid==true
end
function H:resolve(offer,placed)
 if not offer or offer~=self.offer then return false end
 self.offer=nil
 return self.policy:resolve(offer.request.id,placed)
end
return H
