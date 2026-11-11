-- Append ONLY to a disposable native test main. No Mario/camera/save mutation.
-- Real post-trick failure requests one ordinary kickflip and lets its existing
-- movement, completion, crash gate and paired recovery run without forced success.
;(function()
 local probe={ticks=0,phase='wait',complete=false}
 assert(TrickOutcomes.BRACE_SECONDS==10,'Latest collar duration must be ten seconds')
 local function require_ok(ok,message) if not ok then error('[trick-outcomes] '..message) end end
 -- Deterministic boundary + duplicate check, with no production RNG changes.
 local e={source='motion_controller',scene='test',id=1,kind='trick',clip='kickflip',eligible=true}
 local calls=0
 local yes=TrickOutcomes.new{random=function() calls=calls+1;return 75 end}
 local no=TrickOutcomes.new{random=function() return 76 end}
 require_ok(yes:complete(e,'test') and not yes:complete(e,'test') and calls==1,'hit boundary/duplicate')
 require_ok(not no:complete(e,'test') and no.rolls==1,'miss boundary')
 print('[trick-outcomes] BOUNDARIES hit75=true miss76=true duplicateRoll=false')
 hook_event(HOOK_UPDATE,function()
  if probe.complete then return end
  if not gameplayReady or in_jimmie_title() then return end
  probe.ticks=probe.ticks+1
  if not probe.start and original_pair_valid() and PHYS then probe.start=probe.ticks end
  if not probe.start then return end
  local age=probe.ticks-probe.start;local seconds=clock_elapsed_f64()
  if age>=330 and probe.phase=='wait' and original_pair_valid() and PHYS and PHYS.onGround and not dying then
   require_ok(original_pair_valid() and PHYS and PHYS.onGround and not dying,'grounded companion required')
   probe.body=jimmie;probe.phys=PHYS;probe.scene=tostring(originalScene)
   local count=0
   originalOutcomes=TrickOutcomes.new{random=function() count=count+1;return count==1 and 75 or 1000 end}
   requestedOriginalTrick='kickflip';TRICK_PENDING=true;probe.phase='trick'
   print('[trick-outcomes] REQUEST actualKickflip=true firstCompletedRoll=75')
  end
  if probe.phase=='trick' and originalOutcomes.failures==1 then
   require_ok(originalOutcomes.rolls>=1 and originalOutcomes.pendingRecovery,'completed hit must arm recovery')
   require_ok(dying or (originalCrashHost and originalCrashHost.active),'hit must trigger existing crash/bail path')
   require_ok(not originalBrace,'collar must not run during crash')
   probe.phase='recover';probe.crashTime=seconds
   print('[trick-outcomes] ACTUAL_HIT id='..tostring(originalOutcomes.lastCompletion)..' ragdollAccepted='..tostring(originalCrashHost and originalCrashHost.active))
  end
  if probe.phase=='recover' then
   if originalOutcomes.pendingRecovery then require_ok(not originalBrace,'no collar before recovery') end
   if original_pair_valid() and not dying and not originalOutcomes.pendingRecovery then
    probe.recovery=jimmie==probe.body and 'getup' or 'respawn'
    if probe.recovery=='getup' then
     require_ok(originalCrashHost and originalCrashHost.reason=='recovered','same-pair recovery must commit through crash host')
     require_ok(PHYS~=probe.phys and PHYS.onGround and PHYS.vx==0 and PHYS.vy==0 and PHYS.vz==0,'get-up must install fresh grounded PHYS')
    end
    require_ok(originalOutcomes.braceBody==jimmie,'recovered pair must own collar')
    require_ok(math.abs(originalOutcomes.braceUntil-originalOutcomes.braceStart-TrickOutcomes.BRACE_SECONDS)<1e-8,'deadline must be exactly10seconds')
    require_ok(originalBrace~=nil,'post-recovery collar must appear')
    probe.phase='brace';probe.deadline=originalOutcomes.braceUntil;probe.recoveredAt=originalOutcomes.braceStart;probe.newBody=jimmie
    print(string.format('[trick-outcomes] RECOVERED paired=true recovery=%s deadlineDelta=%.9f crashToRecovery=%.4f',probe.recovery,probe.deadline-probe.recoveredAt,seconds-probe.crashTime))
   end
  end
  if probe.phase=='brace' then
   require_ok(original_pair_valid() and jimmie==probe.newBody,'new pair must survive collar interval')
   if seconds<probe.deadline-.04 then require_ok(originalBrace~=nil,'collar expired early') end
   -- The main update samples the same monotonic clock just before this hook.
   -- Allow one update for the first draw/cleanup after crossing the deadline.
   if seconds>probe.deadline+.05 then
    require_ok(not originalBrace,'collar did not expire after real-time deadline')
    require_ok(originalOutcomes:remaining(probe.scene,jimmie,seconds)==0,'remaining time must be zero')
    require_ok(originalOutcomes.failures==1,'duplicate crash lottery')
    probe.complete=true
    print(string.format('[trick-outcomes] COMPLETE actualCompletedHit=true pairedRecovery=true recovery=%s braceSeconds=10 expiredAfter=%.6f main=__MAIN_SHA__ controller=__CONTROLLER_SHA__',probe.recovery,seconds-probe.recoveredAt))
   end
  end
  if age==900 and not probe.complete then error('[trick-outcomes] timed out in '..probe.phase) end
 end)
end)()
