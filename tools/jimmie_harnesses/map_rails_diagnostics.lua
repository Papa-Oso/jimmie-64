-- Passive diagnostic appended after the native controller-route harness.
-- No replay probes, geometry edits, movement authority or result substitution.
local diagnostic={pending={},count=0,active=nil}
local world=skateOpportunity.world
local clear,away,playersClear=world.clear,world.away,skateOpportunity.playersClear
local observedClear=function(self,p)
 local result=clear(self,p)
 local ctx=diagnostic.active
 if ctx and not result and not ctx.failure then
  ctx.failure={check='world.clear',point=pos(p),lastReject=self.lastReject}
 end
 return result
end
local observedAway=function(self,p,player)
 local result=away(self,p,player)
 local ctx=diagnostic.active
 if ctx and not result and not ctx.failure then
  local q=player and (player.pos or player)
  ctx.failure={check='world.away',point=pos(p),player=pos(q),
   horizontalDistance=q and math.sqrt((p.x-q.x)^2+(p.z-q.z)^2),requiredDistance=140}
 end
 return result
end
skateOpportunity.playersClear=function(self,a,b,ctx)
 local task=self.task
 if not task or not task.rail or diagnostic.count>=12 then return playersClear(self,a,b,ctx) end
 local data={frame=ctx.frame,episode=self.episode,phase=task.phase,extraNativeQueries=0,overrides=false}
 diagnostic.active=data;world.clear=observedClear;world.away=observedAway
 local result=playersClear(self,a,b,ctx)
 world.clear=clear;world.away=away;diagnostic.active=nil
 if not result then
  diagnostic.count=diagnostic.count+1;data.result=false
  data.from=pos(a);data.to=pos(b);data.rail=railSnapshot(task.rail);data.players={}
  for _,p in ipairs(ctx.players or {ctx.player})do
   local q=p.pos or p;data.players[#data.players+1]={position=pos(q),vx=p.vx,vy=p.vy,vz=p.vz}
  end
  data.lastReject=world.lastReject
  diagnostic.pending[#diagnostic.pending+1]=data
 end
 return result
end
hook_event(HOOK_UPDATE,function()
 -- A propagated native-budget error must never leave diagnostic wrappers active.
 world.clear=clear;world.away=away;diagnostic.active=nil
 for _,data in ipairs(diagnostic.pending)do emit('fresh-clearance-witness',data)end
 diagnostic.pending={}
end)
