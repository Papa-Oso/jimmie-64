-- TEST ONLY: append to disposable integrated main, never production source.
-- One naturally admitted get-up, then an explicit proof-loss fault to prove the
-- safe paired-respawn fallback. Does not move Mario or modify native terrain.
;(function()
 local p={phase='wait',sawGetup=false,costs={},complete=false,renders={fall={},getup={},idle={}}}
 p.hostCosts={};p.intervals={};p.maxSamples=300
 local data=require('crash_clips')
 local function proof_line(label,out)
  out=out or originalCrashHost:status(false);local q=out.proof or {};local s=out.snapshot or {}
  print(string.format('[fall-getup] PROOF label=%s phase=%s tick=%s frame=%s seconds=%s proofPhase=%s certificates=%s reused=%s scans=%s triangles=%s references=%s failed=%s reason=%s',
   label,tostring(s.phase),tostring(s.ticks),tostring(s.frame),tostring(q.seconds),tostring(q.phase),tostring(q.certificates),tostring(q.reusedRegions),tostring(q.referenceScans),tostring(q.triangles),tostring(q.references),tostring(q.failed),tostring(q.reason or out.reason)))
 end
 local function performance_line()
  local function stats(a)
   if #a==0 then return 0,0 end
   table.sort(a);return a[math.max(1,math.ceil(#a*.95))]*1000,a[#a]*1000
  end
  local ap,am=stats(p.costs);local hp,hm=stats(p.hostCosts);local ip,im=stats(p.intervals)
  print(string.format('[fall-getup] PERF adapterSamples=%d adapterStepP95Ms=%.4f adapterStepMaxMs=%.4f hostSamples=%d hostUpdateP95Ms=%.4f hostUpdateMaxMs=%.4f intervalSamples=%d ownedIntervalP95Ms=%.4f ownedIntervalMaxMs=%.4f gpuRenderMeasured=false',#p.costs,ap,am,#p.hostCosts,hp,hm,#p.intervals,ip,im))
 end
 local function need(ok,text)
  if not ok then
   p.complete=true -- stop both test hooks before throwing; one useful failure, not repeated spam
   proof_line('FAIL:'..text);performance_line()
   print('[fall-getup] FAILED phase='..tostring(p.phase)..' reason='..text)
   error('[fall-getup] '..text)
  end
 end
 local step=originalCrashHost.step
 originalCrashHost.step=function(self,e)
  if p.complete then return step(self,e) end
  local was=self.active;local start=clock_elapsed_f64();local out=step(self,e)
  if was or out.active then
   if #p.costs<p.maxSamples then p.costs[#p.costs+1]=clock_elapsed_f64()-start end
   if e.paused~=true then p.ownedFrame=e.frame end
   if out.retire or (out.snapshot and (out.snapshot.ticks==1 or out.snapshot.ticks%15==0)) then proof_line(out.retire and 'retire' or 'sample',out) end
  end
  return out
 end
 hook_event(HOOK_UPDATE,function()
  if p.complete then return end
  local t=clock_elapsed_f64()
  local frame=get_global_timer()
  if p.ownedFrame==frame and p.sampledFrame~=frame then
   p.sampledFrame=frame
   local work=skateTraceUpdateSeconds
   if type(work)=='number' and work==work and work>=0 and #p.hostCosts<p.maxSamples then p.hostCosts[#p.hostCosts+1]=work end
   -- Adjacent owned observations only: exclude the deliberate gap between crashes.
   if p.lastOwnedFrame==frame-1 and t>=p.lastOwnedTime and #p.intervals<p.maxSamples then p.intervals[#p.intervals+1]=t-p.lastOwnedTime end
   p.lastOwnedFrame=frame;p.lastOwnedTime=t
  end
  if not p.started and original_pair_valid() and PHYS and skateTraceAllowed==true then p.started=t end
  if not p.started then return end
  if p.phase=='wait' and t-p.started>=6 and original_pair_valid() and PHYS and PHYS.onGround and not dying then
   -- Keep unrelated random trick failures from interrupting this recovery test.
   originalOutcomes=TrickOutcomes.new{random=function() return 1000 end}
   -- Controlled reversed stance fixture only; roots, Mario and native terrain are unchanged.
   originalController:reset()
   need(originalController:step({body=jimmie,board=originalBoard,scene=originalScene,dt=0,inAir=false,pushing=false}),'fixture idle bind failed')
   originalController.heading=1
   need(originalController:step({body=jimmie,board=originalBoard,scene=originalScene,dt=0,inAir=false,pushing=false}),'fixture reversed pose failed')
   p.firstHeading=originalController.heading
   need(smlua_anim_util_get_current_animation_name(originalBoard)==OriginalBank.clips.idle.boardReverse,'controlled reversed board not installed')
   p.firstBody=jimmie;p.firstBoard=originalBoard;p.firstPhys=PHYS;jimmie_dies('board','trick_bail')
   need(originalCrashHost.active,'real flat terrain must admit first crash: '..tostring(originalCrashHost.reason))
   p.phase='first';print('[fall-getup] BEGIN actualTerrain=true controlledStance=1')
  elseif p.phase=='first' then
   local out=originalCrashHost:status(false)
   if out.active then
    need(jimmie==p.firstBody and originalBoard==p.firstBoard,'exclusive pair changed during fall/getup')
    need(originalBrace==nil,'brace must wait for completed recovery')
    need(not railPresentation:status().active,'raised-rail publication must yield to crash')
    if out.snapshot.phase=='getup' then
     p.sawGetup=true
     need(smlua_anim_util_get_current_animation_name(jimmie):find('_getup')~=nil,'get-up animation not installed')
    end
   else
    need(originalCrashHost.reason=='recovered','first get-up retired: '..tostring(originalCrashHost.reason))
    need(p.sawGetup and original_pair_valid() and jimmie==p.firstBody and originalBoard==p.firstBoard,'get-up must preserve pair')
    need(PHYS~=p.firstPhys and PHYS.onGround and PHYS.vx==0 and PHYS.vy==0 and PHYS.vz==0,'fresh grounded PHYS required')
    need(not dying and activeClip=='idle','idle ownership not restored')
    need(not railPresentation:status().active,'raised-rail publication retained after get-up')
    need(originalController.heading==p.firstHeading and originalController.output.heading==p.firstHeading,'committed riding heading was reset')
    need(smlua_anim_util_get_current_animation_name(originalBoard)==OriginalBank.clips.idle.boardReverse,'reversed idle board missing at commit')
    need(originalOutcomes.braceBody==jimmie and originalBrace~=nil,'get-up collar missing')
    need(math.abs(originalOutcomes.braceUntil-originalOutcomes.braceStart-10)<1e-8,'get-up collar deadline must be10seconds')
    p.recovered=t;p.phase='hold'
    print('[fall-getup] GETUP_COMMITTED samePair=true freshPhys=true idle=true braceSeconds=10')
   end
  elseif p.phase=='hold' and t-p.recovered>=1 and original_pair_valid() and PHYS and PHYS.onGround and not dying then
   need(originalBrace~=nil,'collar must persist after get-up')
   p.secondBody=jimmie;p.secondBoard=originalBoard;jimmie_dies('board','trick_bail');p.phase='second'
   p.secondAdmitted=originalCrashHost.active;p.faultInjected=false
   need(p.secondAdmitted,'second actual-terrain crash must be admitted to prove get-up proof-loss fallback: '..tostring(originalCrashHost.reason))
   print('[fall-getup] SECOND admitted='..tostring(p.secondAdmitted))
  elseif p.phase=='second' then
   local out=originalCrashHost:status(false)
   if p.secondAdmitted and out.active and out.snapshot.phase=='getup' and not p.faultInjected then
    -- Invalidate only this disposable adapter's proof. Do not fake a valid
    -- capture, move any surface or restore a stale proof afterwards.
    originalCrashHost.capture.error='injected-getup-proof-loss';p.faultInjected=true
    print('[fall-getup] FAULT proofLossDuringGetup=true')
   end
   if not jimmie then
    need(originalBoard==nil and PHYS==nil,'fallback must retire pair and stale PHYS together')
    p.sawRetire=true
   end
   if p.sawRetire and original_pair_valid() then
    need(p.faultInjected,'ordinary bail is not proof-loss-during-getup evidence')
    need(jimmie~=p.secondBody and originalBoard~=p.secondBoard,'fallback must replace both actors')
    need(originalOutcomes.braceBody==jimmie and originalBrace~=nil,'fallback collar must start at respawn')
    need(math.abs(originalOutcomes.braceUntil-originalOutcomes.braceStart-10)<1e-8,'fallback collar deadline must be10seconds')
    p.deadline=originalOutcomes.braceUntil;p.phase='expiry'
    print('[fall-getup] FALLBACK_RESPAWN paired=true braceSeconds=10 injected='..tostring(p.faultInjected))
   end
  elseif p.phase=='expiry' and t>p.deadline+.08 then
   need(original_pair_valid() and not dying,'following pair missing after fallback')
   need(not originalBrace and originalOutcomes:remaining(tostring(originalScene),jimmie,t)==0,'ten-second collar did not expire')
   for _,phase in ipairs({'fall','getup','idle'}) do for _,role in ipairs({'body','board'}) do need((p.renders[phase][role] or 0)>0,'missing render-hook readback '..phase..'/'..role) end end
   need(#p.hostCosts>0 and #p.intervals>0,'missing host/interval timing samples')
   performance_line()
   table.sort(p.costs);local n=#p.costs;p.complete=true
   print(string.format('[fall-getup] COMPLETE getup=true samePair=true fallback=true braceExpired=true reversed=true renderReadback=body+board/fall+getup+idle callbacks=%d p95Ms=%.4f maxMs=%.4f main=__MAIN_SHA__ crash=b20bee08fcadc743a605fc4dab2ac668bc729f414cec6ad157bedf9d1fa6f27b clips=8b7efb4c64b34d20a7c61101346b95154f20939224544d1173f60218801e8a63 native=bb56e624d68fe9e2ff2380f555975e0984946100f8da394aca638dd9ae53feef controller=2e04e7e1b76055d33cd2bf781a38f15916e41d139268b5e4cf7615f599548ad3',n,p.costs[math.max(1,math.ceil(n*.95))]*1000,p.costs[n]*1000))
  end
  if t-p.started>38 and not p.complete then need(false,'timeout in '..p.phase) end
 end)
 hook_event(HOOK_ON_OBJECT_RENDER,function(o)
  if p.complete or (p.phase~='first' and p.phase~='hold') or (o~=jimmie and o~=originalBoard) then return end
  local out=originalCrashHost:status(false);local snap=out.snapshot;local phase,expected,frame
  local role=o==jimmie and 'body' or 'board'
  if out.active and snap.ticks>0 then
   phase=snap.phase=='getup' and 'getup' or 'fall'
   local clips=phase=='getup' and data.recoveries or data.variants
   expected=role=='body' and clips[snap.variant].name or data.board_name
   frame=role=='body' and snap.frame or 0
  elseif out.reason=='recovered' and originalController.output and originalController.output.clip=='idle' then
   phase='idle';expected=role=='body' and OriginalBank.clips.idle.body or OriginalBank.clips.idle.boardReverse
   frame=originalController.output.frame
  else return end
  local name=smlua_anim_util_get_current_animation_name(o);local gfx=o.header.gfx
  need(name==expected and gfx.animInfo.animFrame==frame,'render pose mismatch '..phase..'/'..role)
  local d=math.max(math.abs(gfx.pos.x-o.oPosX),math.abs(gfx.pos.y-o.oPosY),math.abs(gfx.pos.z-o.oPosZ))
  need(d<.02,'stale raised-rail offset during '..phase..'/'..role)
  if not p.renders[phase][role] then
   print(string.format('[fall-getup] RENDER phase=%s role=%s clip=%s frame=%d gfxDelta=%.6f',phase,role,name,frame,d))
  end
  p.renders[phase][role]=(p.renders[phase][role] or 0)+1
 end)
end)()
