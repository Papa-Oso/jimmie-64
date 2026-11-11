-- User-requested chance AFTER an observed completed trick, never per frame.
-- No hooks, object writes, global RNG seed changes, physics or animation assets.
local M={FAIL_OUT_OF=1000,FAIL_COUNT=75,BRACE_SECONDS=10}
local function finite(n) return type(n)=='number' and n==n and math.abs(n)<1e12 end
function M.new(options)
 local random=(options or {}).random or math.random
 local s={lastCompletion=0,rolls=0,failures=0,pendingRecovery=false}
 function s:reset(scene)
  self.scene=scene;self.lastCompletion=0;self.pendingRecovery=false;self.braceBody=nil;self.braceStart=nil;self.braceUntil=nil
 end
 function s:complete(event,scene,opts)
  if type(event)~='table' or event.source~='motion_controller' or event.scene~=scene or event.eligible~=true or not finite(event.id) or event.id%1~=0 or event.id<=0 or (event.kind~='trick' and event.kind~='grind') then return false,'not-completed-trick' end
  if self.scene~=scene then self:reset(scene) end
  if event.id<=self.lastCompletion then return false,'already-consumed' end
  self.lastCompletion=event.id
  -- motion:crashcause. The caller may supply the roll (made at take-off) and the odds out of 1000.
  local ok,roll
  if type(opts)=='table' and finite(opts.roll) then ok,roll=true,opts.roll else ok,roll=pcall(random,1,M.FAIL_OUT_OF) end
  if not ok or not finite(roll) or roll%1~=0 or roll<1 or roll>M.FAIL_OUT_OF then return false,'random-unavailable' end
  self.rolls=self.rolls+1;self.lastRoll=roll
  local count=type(opts)=='table' and finite(opts.count) and math.max(0,math.min(M.FAIL_OUT_OF,math.floor(opts.count))) or M.FAIL_COUNT
  local fail=roll<=count;if fail then self.failures=self.failures+1 end
  return fail,{id=event.id,kind=event.kind,clip=event.clip,roll=roll,failed=fail,chance=count}
 end
 function s:crashed(scene)
  if self.scene~=scene then self:reset(scene) end
  self.pendingRecovery=true;self.braceBody=nil;self.braceStart=nil;self.braceUntil=nil
 end
 -- Call only AFTER BOTH new cosmetic actors are successfully spawned (or a
 -- future certified get-up has fully completed). A proposal is not recovery.
 function s:recovered(scene,body,seconds)
  if self.scene~=scene or not self.pendingRecovery or not body or not finite(seconds) then return false end
  self.pendingRecovery=false;self.braceBody=body;self.braceStart=seconds;self.braceUntil=seconds+M.BRACE_SECONDS
  return true
 end
 function s:remaining(scene,body,seconds)
  if self.scene~=scene or self.pendingRecovery or not body or body~=self.braceBody or not self.braceUntil or not finite(seconds) then return 0 end
  if seconds<self.braceStart or seconds>=self.braceUntil then self.braceBody=nil;self.braceUntil=nil;return 0 end
  return self.braceUntil-seconds
 end
 return s
end
return M
