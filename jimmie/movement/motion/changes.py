"""Jimmie's accepted movement changes, in the order they are applied. Read by apply_motion.py.

Each change: name, what (one line), marker (file, text that is in the file only once the change is applied),
edits {file: [(old, new), ...]}. Each old text must be in the file exactly once.
A change with files={path under the mod: source file} replaces whole files instead (no marker, no edits).
pending=True means tested in the private copy but not yet approved for the build Josh plays:
apply_motion.py leaves it out unless run with --include-pending. Delete the flag to release it.
"""
from pathlib import Path
import apply_windup  # ../ollie-candidate: the ollie's main.lua and controller edits

HERE = Path(__file__).resolve().parent
BANK_END = 'function M.new()'

CHANGES = []

# 1. Ollie: ground wind-up, ollie from the pop, deeper landing (2026-11-10).
CHANGES.append(dict(
    name='ollie', what='6-frame ground crouch before trick jumps; ollie starts at the pop; 9-frame landing',
    marker=('original_clip_bank.lua', 'jimmie_ollie_v2_'),
    edits={'main.lua': apply_windup.MAIN, 'original_motion_controller.lua': apply_windup.CONTROLLER,
           'original_clip_bank.lua': [(BANK_END, (HERE / 'ollie_bank_fragment.lua').read_text(encoding='utf-8') + BANK_END)]}))

# 2. Planned hops (onto rails, over obstacles) crouch first, and turns onto and off rails are spread over frames.
RAILHOP_TICKS = 5
CHANGES.append(dict(
    name='railhop', what='planned hops crouch on the spot for 5 frames first; he turns to line up with a rail in the air',
    marker=('skate_opportunities.lua', 'motion:railhop'),
    edits={
     'skate_opportunities.lua': [
      ('local RAIL_GRAVITY,RAIL_FRICTION,RAIL_DRAG,RAIL_MAX_SPEED=2.5,.04,.001,48\n',
       'local RAIL_GRAVITY,RAIL_FRICTION,RAIL_DRAG,RAIL_MAX_SPEED=2.5,.04,.001,48\n'
       '-- motion:railhop. Frames a planned hop crouches on the ground before it leaves.\n'
       'O.WINDUP=%d\n' % RAILHOP_TICKS),
      ('terrain=ctx.terrain,started=ctx.time,approachOrigin=cp(p)}\n',
       'terrain=ctx.terrain,started=ctx.time,approachOrigin=cp(p),windup=plan.contactEntry and 0 or O.WINDUP}\n'),
      (' t.step=t.step+1\n local total=t.phase==\'grind\' and 60 or t.plan.duration\n',
       ' if t.phase==\'air\' and t.step==0 and (t.windup or 0)>0 then\n'
       '  -- Crouch where he stands. The jump was already proved from this exact spot, so nothing moves.\n'
       '  if not self:playersClear(p,p,ctx) then self:cancel(\'fresh-clearance-refused\',ctx);return nil end\n'
       '  if t.windup==O.WINDUP then self:event(\'windup\',ctx,{opportunity=t.kind}) end\n'
       '  t.windup=t.windup-1;t.popped=true\n'
       '  local to=t.plan.landing or t.plan.b\n'
       '  return {position=cp(p),velocity={x=0,y=0,z=0},onGround=true,variant=t.variant,kind=t.kind,grind=false,phase=\'windup\',\n'
       '   windup=(O.WINDUP-1-t.windup)/math.max(1,O.WINDUP-1)*.99,heading=to and dist(p,to)>1 and math.atan2(to.x-p.x,to.z-p.z) or nil,\n'
       '   episode=self.episode,duration=t.plan.duration/30,airTime=0}\n'
       ' end\n'
       ' t.step=t.step+1\n local total=t.phase==\'grind\' and 60 or t.plan.duration\n'),
      ('  raisedPresentation=presentation,\n  incline=presentation and presentation.incline or (grind and',
       '  raisedPresentation=presentation,popped=t.popped,\n'
       '  heading=t.rail and (t.phase==\'air\' or t.phase==\'grind\') and math.atan2(t.rail.b.x-t.rail.a.x,t.rail.b.z-t.rail.a.z) or nil,\n'
       '  incline=presentation and presentation.incline or (grind and'),
     ],
     'main.lua': [
      # Turn over a few frames in the air and in the crouch; on the rail itself stay exactly lined up.
      ('    if math.abs(v.x)+math.abs(v.z)>.01 then p.yaw=math.atan2(v.x,v.z) end\n    p.prevYaw=p.yaw\n',
       '    local wantYaw=out.heading or (math.abs(v.x)+math.abs(v.z)>.01 and math.atan2(v.x,v.z)) or p.yaw\n'
       '    if out.grind or out.phase==\'grind\' then p.yaw=wantYaw\n'
       '    else\n'
       '        local dyaw=(wantYaw-p.yaw+math.pi*3)%(math.pi*2)-math.pi\n'
       '        p.yaw=p.yaw+math.max(-.3,math.min(.3,dyaw))\n'
       '    end\n'
       '    p.prevYaw=p.yaw\n'
       '    p.popped=(out.popped==true and not p.onGround) or nil;p.windup=nil\n'),
      # The crouch shows during the planner's wind-up; the frame the board meets the rail already counts as grinding.
      ('        windup=p.windup and p.onGround and math.max(0,p.windup.t-1)/6 or nil,popped=p.popped==true,\n'
       '        inAir=PHYS_AIR==true and p.onGround==false,railContact=opportunityMotion and opportunityMotion.grind==true,',
       '        windup=(opportunityMotion and opportunityMotion.phase==\'windup\' and opportunityMotion.windup) or (p.windup and p.onGround and math.max(0,p.windup.t-1)/6) or nil,popped=p.popped==true,\n'
       '        inAir=PHYS_AIR==true and p.onGround==false,railContact=opportunityMotion and (opportunityMotion.grind==true or opportunityMotion.phase==\'grind\'),'),
      ('        balanceClip=opportunityMotion and opportunityMotion.grind and opportunityMotion.balanceClip or nil})\n',
       '        balanceClip=opportunityMotion and (opportunityMotion.grind or opportunityMotion.phase==\'grind\') and opportunityMotion.balanceClip or nil})\n'),
     ]}))

# 3. Following: a couple of pushes, then coast in the riding pose; lean into turns.
CHANGES.append(dict(
    name='coast', what='two pushes then a coast in the riding pose instead of kicking non-stop; leans up to about 10 degrees into turns',
    marker=('main.lua', 'motion:coast'),
    edits={
     'main.lua': [
      ('    if p.onGround and spd < desiredSpeed - 1 and not p.windup then\n'
       '        p.pushT = p.pushT + dt\n'
       '        if p.pushT > 0.40 then p.pushT = 0 end\n',
       '    -- motion:coast. After two pushes, roll for a while unless he has nearly stopped or is racing to catch up.\n'
       '    local wantPush = p.onGround and spd < desiredSpeed - 1 and not p.windup\n'
       '    if (p.coastT or 0) > 0 then\n'
       '        p.coastT = p.coastT - dt\n'
       '        if spd > 6 and not (currentSkateIntent and currentSkateIntent.catchUp) then wantPush = false end\n'
       '    end\n'
       '    if not wantPush and (p.coastT or 0) <= 0 then p.pushN = 0 end\n'
       '    if wantPush then\n'
       '        p.pushT = p.pushT + dt\n'
       '        if p.pushT > 0.40 then\n'
       '            p.pushT = 0\n'
       '            p.pushN = (p.pushN or 0) + 1\n'
       '            if p.pushN >= 2 then p.pushN = 0; p.coastT = 0.9; wantPush = false end\n'
       '        end\n'
       '    end\n'
       '    if wantPush then\n'),
      ('    local bank = math.floor(math.max(-600, math.min(600, turn * -5200)))\n',
       '    local bank = math.floor(math.max(-1800, math.min(1800, turn * -24000)))\n'),
      ('    -- Orient the deck lengthwise, with slope and banking on its actual axes.\n',
       '    -- Orient the deck lengthwise, with slope and banking on its actual axes.\n'
       '    p.lean = (p.lean or 0) * 0.7 + (p.onGround and turn * math.min(1, spd / 20) or 0) * 0.3\n'),
      ('        skate_model_angles(p.yaw, slopeVal or 0, turn)\n', '        skate_model_angles(p.yaw, slopeVal or 0, p.lean)\n'),
      ('        flightDuration=flight_playback_seconds(.95,1/30),dying=dying,bailDuration=.9,\n',
       '        speed=jimmieSpeed,flightDuration=flight_playback_seconds(.95,1/30),dying=dying,bailDuration=.9,\n'),
     ],
     'original_motion_controller.lua': [
      ("    if self.push then clip='push';phase=self.push/.4;self.push=self.push+dt end\n",
       "    if self.push then clip='push';phase=self.push/.4;self.push=self.push+dt\n"
       "    elseif (tonumber(c.speed) or 0)>4 and self.bank.clips.pose then clip='pose' end\n"),
     ]}))

# 4. Grinds keep most of the approach speed.
_ENTRY = 'entrySpeed(%s)'
CHANGES.append(dict(
    name='railspeed', what='he keeps 85% of his approach speed when the board meets a rail, instead of only the part pointing along it',
    marker=('skate_opportunities.lua', 'motion:railspeed'),
    edits={'skate_opportunities.lua': [
      ('local function startGrind(t,vx,vy,vz)\n',
       '-- motion:railspeed. Speed along the rail at contact: most of the approach speed carries over,\n'
       '-- as long as he was already heading the rail\'s way.\n'
       'local function entrySpeed(vx,vy,vz,x,y,z)\n'
       ' local along=(vx or 0)*x+(vy or 0)*y+(vz or 0)*z\n'
       ' if along>0 then along=math.max(along,.85*math.sqrt((vx or 0)^2+(vz or 0)^2)) end\n'
       ' return clamp(along,0,RAIL_MAX_SPEED)\n'
       'end\n'
       'local function startGrind(t,vx,vy,vz)\n'),
      (' t.grindSpeed=clamp((vx or 0)*x+(vy or 0)*y+(vz or 0)*z,0,RAIL_MAX_SPEED)\n',
       ' t.grindSpeed=entrySpeed(vx,vy,vz,x,y,z)\n'),
      ('  estimated=clamp((rail.a.x-before.x)*tx+(rail.a.y-before.y)*grade+(rail.a.z-before.z)*tz,0,RAIL_MAX_SPEED)\n',
       '  estimated=entrySpeed(rail.a.x-before.x,rail.a.y-before.y,rail.a.z-before.z,tx,grade,tz)\n'),
      ('  estimated=clamp((p.vx or 0)*tx+(p.vy or 0)*grade+(p.vz or 0)*tz,0,RAIL_MAX_SPEED)\n',
       '  estimated=entrySpeed(p.vx,p.vy,p.vz,tx,grade,tz)\n'),
    ]}))

# 5. Kickflip and heelflip use the longer landing made for the ollie.
CHANGES.append(dict(
    name='fliplanding', what='kickflip and heelflip land with the 9-frame landing instead of the old 6-frame one',
    marker=('original_clip_bank.lua', 'motion:fliplanding'),
    edits={'original_clip_bank.lua': [
      (BANK_END, '-- motion:fliplanding\nfor _,n in ipairs({"kickflip","heelflip"}) do if M.clips[n] and M.clips.land_ollie then M.clips[n].landing="land_ollie" end end\n' + BANK_END),
    ]}))

# 6. Bails have a cause. The dice are rolled when he leaves the ground, the odds come from the trick, his speed
#    and how he lands, and a failed trick goes wrong in the air and falls at touchdown (not a second after a clean landing).
CHANGES.append(dict(
    name='crashcause', what='trick bails happen at touchdown with odds from the trick, speed, drop and landing; a doomed trick visibly under-rotates',
    marker=('main.lua', 'motion:crashcause'),
    edits={
     'trick_outcomes.lua': [
      (" function s:complete(event,scene)\n", " function s:complete(event,scene,opts)\n"),
      ("  local ok,roll=pcall(random,1,M.FAIL_OUT_OF)\n",
       "  -- motion:crashcause. The caller may supply the roll (made at take-off) and the odds out of 1000.\n"
       "  local ok,roll\n"
       "  if type(opts)=='table' and finite(opts.roll) then ok,roll=true,opts.roll else ok,roll=pcall(random,1,M.FAIL_OUT_OF) end\n"),
      ("  local fail=roll<=M.FAIL_COUNT;if fail then self.failures=self.failures+1 end\n"
       "  return fail,{id=event.id,kind=event.kind,clip=event.clip,roll=roll,failed=fail}\n",
       "  local count=type(opts)=='table' and finite(opts.count) and math.max(0,math.min(M.FAIL_OUT_OF,math.floor(opts.count))) or M.FAIL_COUNT\n"
       "  local fail=roll<=count;if fail then self.failures=self.failures+1 end\n"
       "  return fail,{id=event.id,kind=event.kind,clip=event.clip,roll=roll,failed=fail,chance=count}\n"),
     ],
     'original_motion_controller.lua': [
      # The trick is judged the frame the board touches down, not when the landing crouch has finished.
      ("    self.landing={clip=q.landing or 'land',t=0,heading=a.heading,early=(a.phase or 0)<(q.catch or .84)}\n    self.air=nil\n",
       "    self.landing={clip=q.landing or 'land',t=0,heading=a.heading,early=(a.phase or 0)<(q.catch or .84)}\n    self.air=nil\n"
       "    if self.journey then completed=self.journey;completed.early=self.landing.early;self.journey=nil end\n"),
      # A trick that is going to fail runs late, so the board has not come round when he lands.
      ("   phase=math.min(1,phase);a.phase=phase;a.t=a.t+dt\n",
       "   phase=math.min(1,phase)\n   if c.doomed then phase=a.from+(phase-a.from)*.7 end\n   a.phase=phase;a.t=a.t+dt\n"),
      ("earlyLanding=self.landing and self.landing.early or false,completedTrick=",
       "earlyLanding=self.landing and self.landing.early or false,journey=self.journey and self.journey.kind or nil,completedTrick="),
     ],
     'main.lua': [
      ("local function update_pose_animation(dt)\n",
       "-- motion:crashcause. Odds out of 1000 that a trick fails. Globals, because this file is at Lua's limit of local names.\n"
       "function jimmie_bail_odds(clip,kind,speed)\n"
       "    local base=kind=='grind' and 40 or (clip=='kickflip' or clip=='heelflip') and 70 or (clip=='bs_pop_shuvit' or clip=='fs_pop_shuvit') and 45 or 20\n"
       "    return base+math.max(0,math.min(60,((tonumber(speed) or 0)-25)*2))\n"
       "end\n"
       "-- Total odds at touchdown, the part known at take-off, and the name of the biggest landing cause.\n"
       "function jimmie_landing_odds(p,event,speed,planned)\n"
       "    local base=p.trickBase or jimmie_bail_odds(event.clip,event.kind,speed)\n"
       "    local extra,why=0,nil\n"
       "    if event.kind=='trick' and event.early and not p.doomed then extra,why=350,'landed-early' end\n"
       "    local hard=math.max(0,math.min(500,(((p.airTop or p.y or 0)-(p.y or 0))-340)*2))\n"
       "    if hard>extra then why='hard-landing' end\n"
       "    local side=0\n"
       "    if not planned and (tonumber(speed) or 0)>8 and p.yaw then\n"
       "        local a=math.abs(((math.atan2(p.vx or 0,p.vz or 0)-p.yaw+math.pi)%(2*math.pi))-math.pi)\n"
       "        side=math.max(0,math.min(400,(math.min(a,math.pi-a)-.5)*600))\n"
       "        if side>math.max(extra,hard) then why='sideways-landing' end\n"
       "    end\n"
       "    return math.floor(math.min(950,base+extra+hard+side)),base,why\n"
       "end\n"
       "local function update_pose_animation(dt)\n"),
      ("        speed=jimmieSpeed,flightDuration=", "        doomed=p.doomed==true,speed=jimmieSpeed,flightDuration="),
      ("        if out.completedTrick and not dying then\n"
       "            local fail,result=originalOutcomes:complete(out.completedTrick,tostring(originalScene))\n"
       "            if type(result)=='table' then log('[trick-outcome] id='..result.id..' kind='..result.kind..' roll='..result.roll..'/1000 crash='..tostring(fail)) end\n"
       "            if VOICE.skateMemory then VOICE.skateMemory.outcome(out.completedTrick,result) end\n"
       "            if fail then jimmie_dies('board','trick_bail') end\n"
       "        end\n",
       "        if out.journey and PHYS and not p.onGround then\n"
       "            -- Roll once when he leaves the ground. A hop onto a rail is judged when he comes off it.\n"
       "            p.airTop=math.max(p.airTop or p.y,p.y)\n"
       "            if not p.trickRoll then p.trickRoll=math.random(1,1000) end\n"
       "            local key=out.journey..tostring(out.clip)\n"
       "            if p.trickKey~=key then\n"
       "                p.trickKey=key;p.trickBase=jimmie_bail_odds(out.clip,out.journey,jimmieSpeed)\n"
       "                p.doomed=p.trickRoll<=p.trickBase and not (out.journey=='trick' and opportunityMotion and opportunityMotion.kind=='rail')\n"
       "            end\n"
       "        end\n"
       "        if out.completedTrick and not dying then\n"
       "            local odds,base,why=jimmie_landing_odds(p,out.completedTrick,jimmieSpeed,opportunityMotion~=nil)\n"
       "            local fail,result=originalOutcomes:complete(out.completedTrick,tostring(originalScene),{roll=p.trickRoll,count=odds})\n"
       "            if type(result)=='table' then\n"
       "                local cause=not fail and 'none' or (result.roll>base and why) or (result.kind=='grind' and 'off-the-rail' or 'under-rotated')\n"
       "                log('[trick-outcome] id='..result.id..' kind='..result.kind..' roll='..result.roll..'/1000 crash='..tostring(fail)..' chance='..tostring(result.chance)..' cause='..tostring(cause)..' clip='..tostring(result.clip))\n"
       "            end\n"
       "            p.trickRoll,p.trickKey,p.trickBase,p.doomed,p.airTop=nil,nil,nil,nil,nil\n"
       "            if VOICE.skateMemory then VOICE.skateMemory.outcome(out.completedTrick,result) end\n"
       "            if fail then jimmie_dies('board','trick_bail') end\n"
       "        end\n"),
     ]}))

# 7. Longer grinds. A rail used to be measured out to 144 units (240 for known rails) and then he hopped off,
#    which at his speed is 7 to 12 frames. Now it is measured out to 576 units when the rail is that long.
CHANGES.append(dict(
    name='longgrind', what='rails are measured out to 576 units instead of 144, so a grind can last about a second',
    marker=('skate_probes.lua', 'motion:longgrind'),
    edits={'skate_surface_rails.lua': [
      # Fences and other visible rails: this was the cap that applied in the fence tests.
      ('points=math.min(7,math.floor(visual.remaining/24)+1)', 'points=math.min(25,math.floor(visual.remaining/24)+1)'),
     ],
     # The log now also says how much visible rail lay ahead of the entry point, to measure the share ridden.
     'skate_opportunities.lua': [
      ("self:event('rail-opportunity-found',ctx,{from=cp(rail.a),to=cp(rail.b)})",
       "self:event('rail-opportunity-found',ctx,{from=cp(rail.a),to=cp(rail.b),remaining=rail.visual and rail.visual.remaining or nil})"),
     ],
     'skate_probes.lua': [
      ('s.nearGeneric=s.index<=nearCount;s.source=nil;s.visual=nil;s.maxPoints=11',
       's.nearGeneric=s.index<=nearCount;s.source=nil;s.visual=nil;s.maxPoints=25'),
      ('  for _=1,(s.visual and 1 or 2) do\n',
       '  -- motion:longgrind. Four steps of 24 units per update, up to 25 points (576 units).\n'
       '  for _=1,(s.visual and 2 or 4) do\n'),
      ('    if #s.points>=(s.nearGeneric and 7 or s.maxPoints or 11) then',
       '    if #s.points>=(s.nearGeneric and 25 or s.maxPoints or 25) then'),
    ]}))

# 8. When the staged fall is refused (any floor that is not perfectly flat), he used to freeze, flip over in 0.9 s,
#    vanish and reappear. Now he slides to a stop while the fall plays at its real speed, lies a moment, and gets up
#    where he is. The get-up is the fall clip run backwards quickly; there is no separate get-up clip for this path.
FALL_SECONDS, LIE_SECONDS, GETUP_SECONDS = 2.03, 0.35, 0.6
CHANGES.append(dict(
    name='fallhere', what='on uneven floor he slides, falls at real speed and gets up where he is, instead of vanishing and reappearing',
    marker=('main.lua', 'motion:fallhere'),
    edits={
     'original_motion_controller.lua': [
      ("   clip='bail';phase=math.min(1,(self.time or 0)/math.max(dt,c.bailDuration or .9))\n",
       "   clip='bail';phase=math.min(1,(self.time or 0)/math.max(dt,c.bailDuration or .9))\n"
       "   if c.getup then phase=math.max(0,1-c.getup) end\n"),
     ],
     'main.lua': [
      ('    local accepted=begin_original_crash()\n'
       '    if VOICE.skateMemory then VOICE.skateMemory.crash(accepted,speechEvent=="trick_bail") end\n',
       '    local accepted=begin_original_crash()\n'
       '    -- motion:fallhere. The staged fall only runs on perfectly flat floor. Anywhere else, fall and get up on the spot.\n'
       '    JIMMIE_FALL=nil\n'
       '    if not accepted and jimmie and originalBoard then\n'
       '        local q=PHYS or {}\n'
       '        JIMMIE_FALL={vx=q.vx or 0,vz=q.vz or 0,t=0,yaw=q.yaw}\n'
       '        dyingUntil=now()+%s\n'
       '    end\n'
       '    if VOICE.skateMemory then VOICE.skateMemory.crash(accepted or JIMMIE_FALL~=nil,speechEvent=="trick_bail") end\n'
       % (FALL_SECONDS + LIE_SECONDS + GETUP_SECONDS + 0.5)),
      ('dying=dying,bailDuration=.9,',
       'dying=dying,bailDuration=JIMMIE_FALL and %s or .9,getup=JIMMIE_FALL and JIMMIE_FALL.getup or nil,' % FALL_SECONDS),
      ('        if now() >= dyingUntil then\n'
       '            dying = false\n'
       '            despawn_jimmie(true) -- terrain-declined crashes retain pending post-recovery collar\n',
       '        local f=JIMMIE_FALL\n'
       '        if f and originalBoard then\n'
       '            f.t=f.t+dt\n'
       '            if f.t<%(fall)s then\n'
       '                -- Slide on along the floor and slow down; stop at a wall, a ledge or a step.\n'
       '                local nx,nz=jimmie.oPosX+f.vx,jimmie.oPosZ+f.vz\n'
       '                local fy=find_floor_height(nx,jimmie.oPosY+40,nz)\n'
       '                if (f.vx~=0 or f.vz~=0) and fy>-10000 and math.abs(fy-jimmie.oPosY)<=40 and (not Personality or Personality.wallClear(nx,fy,nz)) then\n'
       '                    jimmie.oPosX,jimmie.oPosY,jimmie.oPosZ=nx,fy,nz\n'
       '                else f.vx,f.vz=0,0 end\n'
       '                f.vx,f.vz=f.vx*.86,f.vz*.86\n'
       '            elseif f.t>=%(up)s then f.getup=math.min(1,(f.t-%(up)s)/%(getup)s) end\n'
       '            if f.getup and f.getup>=1 then\n'
       '                local yaw=f.yaw or 0\n'
       '                PHYS={x=jimmie.oPosX,y=jimmie.oPosY,z=jimmie.oPosZ,vx=0,vy=0,vz=0,yaw=yaw,prevYaw=yaw,onGround=true,pushT=0,airT=0}\n'
       '                PHYS_AIR=false;PHYS_PUSHING=false;TRICK_PENDING=nil\n'
       '                JIMMIE_FALL=nil;dying=false;dyingUntil=0;jimmieDeadUntil=0;deathSpin=0\n'
       '                originalController:reset()\n'
       '                originalOutcomes:recovered(tostring(originalScene),jimmie,clock_elapsed_f64())\n'
       "                log('[original-crash] recovered by simple getup')\n"
       '                if VOICE.skateMemory then VOICE.skateMemory.gotUp() end\n'
       '            end\n'
       '            return\n'
       '        end\n'
       '        if now() >= dyingUntil then\n'
       '            dying = false\n'
       '            despawn_jimmie(true) -- terrain-declined crashes retain pending post-recovery collar\n'
       % dict(fall=FALL_SECONDS, up=FALL_SECONDS + LIE_SECONDS, getup=GETUP_SECONDS)),
     ]}))

# 9. Trick batches 1 to 3: ten more flips and shuvits, eight grabs, four spins and ten named grinds and slides
#    (made by ../tricks/trick_motion.py), a trick list that lives in the
#    clip bank instead of the picker, per-trick bail odds, and the trick's real name on the outcome facts for speech.
CHANGES.append(dict(
    name='tricks1', what='35 new tricks (flips, shuvits, grabs, spins, named grinds and slides, manuals), fakie versions and combos; picked from a named list in the clip bank; outcome facts carry trick="<name>"; a 180 lands rolling backwards, then he turns back round',
    marker=('original_clip_bank.lua', 'jimmie_tricks_v1_'),
    edits={
     'original_clip_bank.lua': [
      (BANK_END, (HERE / 'tricks1_bank_fragment.lua').read_text(encoding='utf-8') + BANK_END),
      (' local s={clips=M.clips}\n', ' local s={clips=M.clips,tricks=M.trickList,manuals=M.manualList,styles=M.styles}\n'),
     ],
     'original_motion_controller.lua': [
      ("   heading=self.heading\n   if self.landing then\n",
       "   heading=self.heading\n"
       "   if c.manualClip and self.bank.clips[c.manualClip] then\n"
       "    -- Manual: tip onto two wheels straight from the landing and hold it; the trick has already been judged at touchdown.\n"
       "    if self.manual~=c.manualClip then self.manual=c.manualClip;self.manualTime=0 end\n"
       "    self.landing=nil;self.push=nil\n"
       "    clip=self.manual;phase=math.min(1,self.manualTime/self.bank.clips[clip].duration);self.manualTime=self.manualTime+dt\n"
       "   elseif self.manual then\n"
       "    -- Set the other wheels back down: the entry run backwards, twice as fast.\n"
       "    clip=self.manual;self.manualTime=math.min(self.manualTime,self.bank.clips[clip].duration)-dt*2\n"
       "    phase=math.max(0,self.manualTime/self.bank.clips[clip].duration)\n"
       "    if self.manualTime<=0 then self.manual=nil end\n"
       "   elseif self.landing then\n"),
      ("     self.journey=c.trickTakeoff==true and {id=self.serial,kind='trick',clip=chosen} or nil\n    end\n",
       "     self.journey=c.trickTakeoff==true and {id=self.serial,kind='trick',clip=chosen} or nil\n"
       "    else self.journey.out=chosen end\n"),
      ("   clip='windup';phase=c.windup\n",
       "   if not self.winding or c.windup<(self.lastWind or 0) then\n"
       "    -- Decide now whether this jump is a nollie, a boneless or a no-comply: each has its own crouch.\n"
       "    self.winding=true\n"
       "    local want=c.requestedTrick and self.bank.clips[c.requestedTrick]\n"
       "    local r=math.random()\n"
       "    if want then self.style=want.style\n"
       "    elseif self.bank.styles and not c.noSpin then self.style=r<.08 and 'nollie' or r<.13 and 'boneless' or r<.18 and 'nocomply' or nil\n"
       "    else self.style=nil end\n"
       "   end\n"
       "   self.lastWind=c.windup\n"
       "   clip=self.style and self.bank.clips['windup_'..self.style] and ('windup_'..self.style) or 'windup';phase=c.windup\n"),
      ("   self.journey.kind='grind'\n", "   self.journey.kind='grind';self.journey.grind=c.balanceClip\n"),
      ("    local chosen=c.requestedTrick or families[(self.serial-1)%#families+1]\n",
       "    local chosen=c.requestedTrick\n"
       "    if not chosen and self.bank.tricks then\n"
       "     -- Weighted pick from the bank's named tricks: never the same one twice running, and long tricks need the air time.\n"
       "     local total,pool=0,{}\n"
       "     for _,n in ipairs(self.bank.tricks) do\n"
       "      local q=self.bank.clips[n]\n"
       "      if q and n~=self.lastTrick and duration>=(q.minAir or .4) and not (q.spin and c.noSpin) and q.style==self.style then total=total+(q.weight or 1);pool[#pool+1]=n end\n"
       "     end\n"
       "     local roll=math.random()*total\n"
       "     for _,n in ipairs(pool) do roll=roll-(self.bank.clips[n].weight or 1);if roll<=0 then chosen=n;break end end\n"
       "     chosen=chosen or pool[#pool]\n"
       "    end\n"
       "    chosen=chosen or families[(self.serial-1)%#families+1]\n"),
      ("    if not self.bank.clips[chosen] or duration<.4 then chosen='trick' end\n",
       "    if not self.bank.clips[chosen] or duration<.4 then chosen='trick' end\n    self.lastTrick=chosen;self.winding=nil;self.style=nil\n"),
     ],
     'main.lua': [
      ("    local wantPush = p.onGround and spd < desiredSpeed - 1 and not p.windup\n",
       "    local wantPush = p.onGround and spd < desiredSpeed - 1 and not p.windup and not p.fakie and not p.manual\n"),
      ("    local p=PHYS or {}\n    local ok,out=originalController:step({body=jimmie,board=originalBoard,dt=dt,scene=originalScene,\n",
       "    local p=PHYS or {}\n"
       "    -- Manuals: planned when he leaves the ground, started the frame he lands, held for about a second.\n"
       "    if p.manual then\n"
       "        p.manual.t=p.manual.t+dt\n"
       "        if p.manual.t>p.manual.dur or not p.onGround or p.windup or dying or (opportunityMotion and opportunityMotion.phase=='windup') then p.manual=nil end\n"
       "    elseif p.manualPlan and p.onGround and PHYS then\n"
       "        p.manual={clip=p.manualPlan,t=0,dur=.8+math.random()*.8};p.manualPlan=nil\n"
       "    end\n"
       "    local ok,out=originalController:step({body=jimmie,board=originalBoard,dt=dt,scene=originalScene,\n"),
      ("            if not p.trickRoll then p.trickRoll=math.random(1,1000) end\n",
       "            if not p.trickRoll then\n"
       "                p.trickRoll=math.random(1,1000)\n"
       "                -- Still rolling backwards from a 180: this one is a fakie trick, and he stays backwards until it lands.\n"
       "                if p.fakie then p.fakie.hold=math.max(p.fakie.hold,45);p.fakieTrick=true else p.fakieTrick=nil end\n"
       "                local manuals=OriginalBank.manualList\n"
       "                p.manualPlan=manuals and #manuals>0 and not p.fakie and not (opportunityMotion and opportunityMotion.kind=='rail') and math.random()<.3 and manuals[math.random(#manuals)] or nil\n"
       "            end\n"),
      ("    local yaw = (math.floor(heading * 32768 / math.pi) - 16384) % 65536\n",
       "    if PHYS and PHYS.fakie then heading = heading + PHYS.fakie.yaw end\n"
       "    local yaw = (math.floor(heading * 32768 / math.pi) - 16384) % 65536\n"),
      ("        doomed=p.doomed==true,", "        manualClip=p.manual and p.manual.clip or nil,noSpin=opportunityMotion~=nil and opportunityMotion.kind=='rail',doomed=p.doomed==true,"),
      ("        if out.journey and PHYS and not p.onGround then\n",
       "        if p.fakie and p.onGround and not out.completedTrick then\n"
       "            -- Rolling backwards after a 180: hold it, then pivot back round over a few frames.\n"
       "            p.fakie.hold=p.fakie.hold-1\n"
       "            if p.fakie.hold<=0 then\n"
       "                p.fakie.yaw=p.fakie.yaw-math.max(-.35,math.min(.35,p.fakie.yaw))\n"
       "                if math.abs(p.fakie.yaw)<.01 then p.fakie=nil end\n"
       "            end\n"
       "        end\n"
       "        if out.journey and PHYS and not p.onGround then\n"),
      ("            if fail then jimmie_dies('board','trick_bail') end\n        end\n",
       "            if fail then jimmie_dies('board','trick_bail')\n"
       "            elseif type(result)=='table' and result.kind=='trick' and PHYS and OriginalBank.clips[result.clip] and OriginalBank.clips[result.clip].spin then\n"
       "                -- The clip ended turned half way; from this frame the whole model carries that half turn instead.\n"
       "                local already=p.fakie and p.fakie.yaw or 0\n"
       "                if math.abs(already)>.01 then p.fakie=nil else p.fakie={yaw=math.pi*OriginalBank.clips[result.clip].spin,hold=math.random()<.5 and 75 or 20} end\n"
       "                jimmie.oFaceAngleYaw=(jimmie.oFaceAngleYaw+32768)%65536;originalBoard.oFaceAngleYaw=jimmie.oFaceAngleYaw\n"
       "            end\n        end\n"),
      ("    local base=kind=='grind' and 40 or (clip=='kickflip'",
       "    local q=OriginalBank and OriginalBank.clips[clip]\n"
       "    local base=kind=='grind' and 40 or (q and q.odds) or (clip=='kickflip'"),
      ("            if type(result)=='table' then\n                local cause=",
       "            if type(result)=='table' then\n"
       "                -- The trick's real name, for speech (\"kickflip\", \"360 flip\"); a grind is just \"grind\" for now.\n"
       "                local named=OriginalBank.clips[result.clip]\n"
       "                local ground=out.completedTrick.grind and OriginalBank.clips[out.completedTrick.grind]\n"
       "                local gname=ground and ground.name or 'grind'\n"
       "                if result.kind=='grind' then\n"
       "                    -- A flip on the way onto the rail is named with it: \"kickflip to 5-0 grind\".\n"
       "                    local lead=named and named.name and named.name~='ollie' and result.clip~=out.completedTrick.grind and (named.name..' to ') or ''\n"
       "                    result.trick=lead..gname\n"
       "                    local outq=out.completedTrick.out and OriginalBank.clips[out.completedTrick.out]\n"
       "                    if outq and outq.name and outq.name~='ollie' then result.trick=result.trick..' to '..outq.name..' out' end\n"
       "                else result.trick=(named and named.name) or tostring(result.clip) end\n"
       "                if named and named.spin then p.manual=nil end\n"
       "                if p.fakieTrick and result.kind=='trick' then result.trick='fakie '..result.trick end\n"
       "                p.fakieTrick=nil\n"
       "                if p.manual and p.manual.t==0 and not fail and OriginalBank.clips[p.manual.clip] then result.trick=result.trick..' to '..OriginalBank.clips[p.manual.clip].name end\n"
       "                -- How many tricks he has landed in a row with less than three seconds between them.\n"
       "                p.line=fail and 0 or ((p.lineT and now()-p.lineT<3) and (p.line or 0)+1 or 1);p.lineT=now();result.line=p.line\n"
       "                local cause="),
      ("..' clip='..tostring(result.clip))\n", "..' clip='..tostring(result.clip)..' trick='..tostring(result.trick)..' line='..tostring(result.line))\n"),
     ],
     'skate_rail_presentation.lua': [
      ("        and a.clip ~= 'jimmie_stock_v1_board_reverse_balance042' then return reject('unsupported-clip') end\n",
       "        and a.clip ~= 'jimmie_stock_v1_board_reverse_balance042'\n"
       "        and not (JIMMIE_GRIND_BOARDS ~= nil and JIMMIE_GRIND_BOARDS[a.clip] == true) then return reject('unsupported-clip') end\n"),
     ],
     'skate_rail_binding.lua': [
      ("   and controller.output.clip=='balance042' and finite(controller.output.heading)\n",
       "   and (controller.output.clip=='balance042' or (JIMMIE_GRIND_CLIPS~=nil and JIMMIE_GRIND_CLIPS[controller.output.clip]==true)) and finite(controller.output.heading)\n"),
     ],
     'skate_opportunities.lua': [
      ("function O:chooseBalance(ctx)\n local r=self.rng();if not finite(r) then r=.5 end\n",
       "function O:chooseBalance(ctx,visual)\n local r=self.rng();if not finite(r) then r=.5 end\n"
       " if visual then\n"
       "  -- On a visible rail only poses whose contact point lies on the rail line may be used: the 50-50 and the named grinds.\n"
       "  local total,pool=0,{}\n"
       "  for _,g in ipairs(JIMMIE_GRINDS or {}) do if g.clip~=self.lastBalance then total=total+g.weight;pool[#pool+1]=g end end\n"
       "  local pick=r*total\n"
       "  for _,g in ipairs(pool) do pick=pick-g.weight;if pick<=0 then self.lastBalance=g.clip;return g.clip end end\n"
       "  self.lastBalance=pool[1] and pool[#pool].clip or 'balance042';return self.lastBalance\n"
       " end\n"),
      ("balanceClip=rail and (rail.visual and 'balance042' or self:chooseBalance(ctx)) or nil,", "balanceClip=rail and self:chooseBalance(ctx,rail.visual) or nil,"),
     ],
     'performance_skate_memory.lua': [
      ('clip=episode.clip,roll=episode.roll,', 'clip=episode.clip,trick=episode.trick,line=episode.line,roll=episode.roll,'),
      ('pending={id=result.id,kind=result.kind,clip=result.clip,roll=result.roll,', 'pending={id=result.id,kind=result.kind,clip=result.clip,trick=result.trick,line=result.line,roll=result.roll,'),
     ]}))

# 10. Trick batch 5: nollie, nollie kickflip, nollie heelflip, boneless, no-comply, bigspin, frontside bigspin, double heelflip,
#     ollie north, and three wind-ups. The code that uses them is already in change 9 and does nothing until these clips exist.
CHANGES.append(dict(
    name='tricks5', what='nine more tricks with their own wind-ups: nollies, boneless, no-comply, bigspins, double heelflip, ollie north',
    marker=('original_clip_bank.lua', 'M.styles=true'),
    edits={'original_clip_bank.lua': [(BANK_END, (HERE / 'tricks5_bank_fragment.lua').read_text(encoding='utf-8') + BANK_END)]}))

# 11. Hair: the side part Josh approved on 2026-11-07, which had never been carried into the current model.
#     Today's hair with only the crown changed (see ../hair-part/hair_v3.py and its README). Whole-file change:
#     the three outfit model files are replaced; the board and brace files are not touched.
#
# 12. Skin: a little colour. Josh picked "B medium" on 2026-11-11 (see ../skin-tone/README.md). Only skin colours
#     changed, on the model and in the drawn face. It lives in the same three model files as the side part, so the
#     two are one whole-file change: these files have both. (The side-part-only files are still in
#     ../hair-part/built_sidepart/bin.)
# 2026-11-11: with the regular stance the head is pre-mirrored in these files (side part, B medium skin, head mirrored).
MODEL = HERE.parent / 'hair-fix' / 'bin'   # 2026-11-11: the hair fix (smooth back of the head), made from regular-stance; see ../hair-fix/README.md
CHANGES.append(dict(
    name='model', what='approved side part and skin colour "B medium" (three outfit model files replaced; nothing else in them changed)',
    files={'actors/jimmie_orig_%s_geo.bin' % n: MODEL / ('jimmie_orig_%s_geo.bin' % n) for n in ('rg', 'vest', 'tee')}))

# 12a. Regular stance (Josh, 2026-11-11: the real Jimmie skates regular, left foot forward). Every clip had him
#      goofy. Body and board are drawn mirrored front-to-back, which swaps which foot leads in every clip at once
#      without regenerating any of them or changing any timing. The model files pre-mirror the head so the side part
#      and face stay the way round Josh approved. Checks that insisted on the old scale accept the mirrored one.
CHANGES.append(dict(
    name='regular', what='he rides regular (left foot forward) instead of goofy: the model is drawn mirrored; no clip or timing changes',
    marker=('main.lua', 'motion:regular'),
    edits={
     'main.lua': [
      ("    obj_scale(obj, 0.62)\n",
       "    -- motion:regular. Mirrored front-to-back so he rides left foot forward.\n    obj_scale_xyz(obj, 0.62, 0.62, -0.62)\n"),
      # Rolling backwards, frontside and backside swap.
      ("                if p.fakieTrick and result.kind=='trick' then result.trick='fakie '..result.trick end\n",
       "                if p.fakieTrick and result.kind=='trick' then\n"
       "                    local swapped=result.trick:gsub('frontside','@'):gsub('backside','frontside'):gsub('@','backside')\n"
       "                    result.trick='fakie '..swapped\n"
       "                end\n"),
      # Rolling backwards the model is turned half way round, so the lean has to be turned back.
      ("    local bank = math.floor(math.max(-1800, math.min(1800, turn * -24000)))\n",
       "    local bank = math.floor(math.max(-1800, math.min(1800, turn * -24000)))\n"
       "    if PHYS and PHYS.fakie and math.abs(PHYS.fakie.yaw) > math.pi / 2 then bank = -bank end\n"),
     ],
     'original_clip_bank.lua': [(BANK_END, (HERE / 'regular_bank_fragment.lua').read_text(encoding='utf-8') + BANK_END)],
     'native_crash.lua': [
      ("math.abs(scale[k]-M.SCALE)>.00001", "math.abs(math.abs(scale[k])-M.SCALE)>.00001"),
     ],
     'skate_rail_binding.lua': [
      ("not same(scale.z,.62,1e-6) then return nil end", "not same(math.abs(scale.z),.62,1e-6) then return nil end"),
     ]}))

# 12b. Jimmie's introduction (Josh, 2026-11-11): on a new file he arrives in the bridge scene instead of Lakitu.
#      The game's scene is untouched; Lakitu and his cloud are hidden and Jimmie is drawn in his place, flitting.
CHANGES.append(dict(
    name='introscene', what='on a new file Jimmie arrives in the bridge scene instead of Lakitu: small, flitting and twirling with sparkles, then the normal companion',
    marker=('main.lua', 'motion:introscene'),
    edits={'main.lua': [
      ("local function on_update()\n", "-- motion:introscene. Jimmie's introduction: on a new file he arrives in the bridge scene in place of Lakitu.\n-- The game's own scene is left exactly as it is (trigger, camera, text box, timing). Lakitu and his cloud are only\n-- made invisible, and Jimmie is drawn around where Lakitu is: small, flitting in loops with twirls and sparkles,\n-- growing as he flies in, then still in front of Mario for the text. When the text box closes he becomes the\n-- normal companion on that spot. Globals, because this file is at Lua's limit of locals.\nJIMMIE_INTRO={}\nfunction jimmie_intro_lakitu()\n    local o=obj_get_first_with_behavior_id(id_bhvCameraLakitu)\n    while o do\n        if o.oBehParams2ndByte~=0 and o.activeFlags~=0 then return o end      -- 0 is the camera Lakitu in the mirror room\n        o=obj_get_next_with_same_behavior_id(o)\n    end\n    return nil\nend\nfunction jimmie_intro_hide(lak,delete)\n    obj_set_model_extended(lak,E_MODEL_NONE)\n    for _,id in ipairs({id_bhvCloud,id_bhvCloudPart}) do\n        local c=obj_get_first_with_behavior_id(id)\n        while c do\n            local nxt=obj_get_next_with_same_behavior_id(c)\n            if math.abs(c.oPosX-lak.oPosX)+math.abs(c.oPosY-lak.oPosY)+math.abs(c.oPosZ-lak.oPosZ)<900 then\n                if delete then obj_mark_for_deletion(c) else obj_set_model_extended(c,E_MODEL_NONE) end\n            end\n            c=nxt\n        end\n    end\n    if delete then obj_mark_for_deletion(lak) end\nend\nfunction jimmie_intro_sparkles(x,y,z,count,spread)\n    for _=1,count do\n        spawn_non_sync_object(id_bhvSparkleSpawn,E_MODEL_NONE,x+(math.random()-.5)*spread,y+math.random()*spread,z+(math.random()-.5)*spread,nil)\n    end\nend\nfunction jimmie_intro_step(m)\n    local s=JIMMIE_INTRO\n    if s.done then return false end\n    local lak=jimmie_intro_lakitu()\n    if not lak then\n        if s.seen then s.done=true end                                         -- the scene is over, or was never on this file\n        return false\n    end\n    s.seen=true\n    if lak.oAction==0 then\n        -- Waiting for Mario to step on the bridge. If he gets past it without triggering the scene (the speedrun\n        -- skip), there is no introduction: Jimmie is simply the companion from then on.\n        if m.pos.z<-2150 then s.done=true;log('[jimmie-intro] phase=skipped frame='..tostring(get_global_timer()));return false end\n        -- He cannot be created once the scene has frozen Mario, so he is created now and kept out of sight.\n        if not (jimmie and originalBoard) then spawn_jimmie() end\n        if jimmie and originalBoard then PHYS=nil;jimmie.oPosY=-10000;originalBoard.oPosY=-10000 end\n        if not s.waiting then s.waiting=true;log('[jimmie-intro] phase=waiting frame='..tostring(get_global_timer())) end\n        return true\n    end\n    jimmie_intro_hide(lak,false)\n    if lak.oAction<2 then return true end\n    if not (jimmie and originalBoard) then spawn_jimmie() end\n    if not (jimmie and originalBoard) then return true end\n    local x,y,z=lak.oPosX,lak.oPosY,lak.oPosZ\n    local dx,dz=m.pos.x-x,m.pos.z-z\n    local heading=math.atan2(dx,dz)+(JIMMIE_INTRO_TURN or math.pi/2)            -- he stands sideways on the board; turned so his face is toward Mario\n    if lak.oCameraLakituFinishedDialog~=0 then\n        -- The text box has closed and control is back. From here he is the ordinary companion: he drops to the\n        -- ground from where he hovered. Lakitu and the cloud, already invisible, are removed.\n        obj_scale_xyz(jimmie,.62,.62,-.62);obj_scale_xyz(originalBoard,.62,.62,-.62)\n        PHYS={x=x,y=y,z=z,vx=0,vy=0,vz=0,yaw=heading,prevYaw=heading,onGround=false,pushT=0,airT=0}\n        PHYS_AIR=false\n        jimmie_intro_sparkles(x,y,z,14,170)\n        jimmie_intro_hide(lak,true)\n        s.done=true;log('[jimmie-intro] phase=companion frame='..tostring(get_global_timer()))\n        return false\n    end\n    if s.frame==get_global_timer() then return true end                          -- once per frame, whichever path called\n    s.frame=get_global_timer();s.tick=(s.tick or 0)+1\n    if not s.arrived then s.arrived=true;jimmie_intro_sparkles(x,y,z,10,200);log('[jimmie-intro] phase=arrive frame='..tostring(get_global_timer())) end\n    if lak.oCameraLakituSpeed==0 and not s.talking then s.talking=true;s.twirl=14;log('[jimmie-intro] phase=talk frame='..tostring(get_global_timer())) end\n    local far=math.sqrt(dx*dx+dz*dz+(m.pos.y-y)^2)\n    local k=1-math.max(0,math.min(1,(far-500)/2500));k=k*k*(3-2*k)\n    local size=.16+(.62-.16)*k                                                   -- a speck far away, full size by the time he stops\n    -- Flitting: he darts in loops and bobs around the path Lakitu flies, less and less as that path slows, and is\n    -- still by the time it stops. The path itself, and so the scene's length, is the game's own.\n    local wild=math.max(0,math.min(1,lak.oCameraLakituSpeed/45));local t=s.tick\n    local fx=wild*130*math.sin(t*.47)*math.cos(t*.13)\n    local fy=wild*85*math.sin(t*.83+1.1)+ (1-wild)*6*math.sin(t*.21)            -- a gentle bob while he hovers and talks\n    local fz=wild*130*math.cos(t*.39+.6)\n    -- Twirls: a quick spin on his own axis every second and a half while darting, and one as he settles.\n    local spin=0\n    if wild>.15 and t%44<13 then spin=(t%44)/13*2*math.pi end\n    if s.twirl and s.twirl>0 then spin=(1-s.twirl/14)*2*math.pi;s.twirl=s.twirl-1 end\n    PHYS=nil;jimmieSpeed=10\n    jimmie.oPosX,jimmie.oPosY,jimmie.oPosZ=x+fx,y+fy,z+fz\n    jimmie.oFaceAngleYaw,jimmie.oFaceAnglePitch,jimmie.oFaceAngleRoll=skate_model_angles(heading+spin,0,0)\n    local fc=s.talking and 'fly_cam' or 'fly'\n    if OriginalBank.clips[fc] then\n        -- Flying pose, off the board; the board waits out of sight until he joins Mario.\n        originalController.bank:apply(jimmie,originalBoard,fc,(s.tick%24)/24,0);originalBoard.oPosY=-10000\n    else update_pose_animation(1/30) end\n    obj_scale_xyz(jimmie,size,size,-size);obj_scale_xyz(originalBoard,size,size,-size)\n    if not s.talking then jimmie_intro_sparkles(x+fx,y+fy+60*size,z+fz,2,150*size)\n    elseif t%9==0 then jimmie_intro_sparkles(x+fx,y+fy+90,z+fz,1,120) end\n    return true\nend\nlocal function on_update()\n"),
      # While the text box is up the game counts as paused and the companion code stops early; the scene runs there too.
      ("        step_original_crash(true)\n        step_recovery(0,true)\n",
       "        step_original_crash(true)\n        step_recovery(0,true)\n        jimmie_intro_step(m)\n"),
      ("    elseif step_skate_opportunity() then\n        update_pose_animation(1 / 30)\n",
       "    elseif jimmie_intro_step(m) then\n        -- The bridge scene owns him this tick (or he has not arrived yet).\n"
       "    elseif step_skate_opportunity() then\n        update_pose_animation(1 / 30)\n"),
    ]}))

# 12c. The mirror room: Jimmie is the camera man seen in the mirror (Josh: "just show jimmie in the mirror").
CHANGES.append(dict(
    name='mirrorroom', what='in the mirror room upstairs, the camera man seen in the mirror is Jimmie on his board instead of Lakitu',
    marker=('main.lua', 'motion:mirrorroom'),
    edits={'main.lua': [
      ("local function on_update()\n", "-- motion:mirrorroom. In the mirror room upstairs the game shows the camera man in the mirror, behind Mario's\n-- reflection. That is Jimmie now: the Lakitu there and his cloud are made invisible and a second Jimmie on his board\n-- is drawn where Lakitu is, looking the way Lakitu looks. Nothing about the room or the camera is changed.\nJIMMIE_MIRROR={}\nfunction jimmie_mirror_step()\n    local s=JIMMIE_MIRROR\n    local lak=obj_get_first_with_behavior_id(id_bhvCameraLakitu)\n    while lak and not (lak.oBehParams2ndByte==0 and lak.activeFlags~=0) do lak=obj_get_next_with_same_behavior_id(lak) end\n    if not lak then s.body=nil;s.board=nil;return end\n    jimmie_intro_hide(lak,false)\n    if not (s.body and s.board and s.body.activeFlags~=0 and s.board.activeFlags~=0) then\n        if id_bhvjimmie==nil or E_MODEL_jimmie==nil or originalBoardModel==nil then return end\n        local okA,body=pcall(spawn_non_sync_object,id_bhvjimmie,E_MODEL_jimmie,lak.oPosX,-10000,lak.oPosZ,function(o) end)\n        local okB,board=pcall(spawn_non_sync_object,id_bhvjimmie,originalBoardModel,lak.oPosX,-10000,lak.oPosZ,function(o) end)\n        if not (okA and okB and body and board) then return end\n        s.body,s.board=body,board\n        smlua_anim_util_set_animation(body,OriginalBank.clips.pose.body);smlua_anim_util_set_animation(board,OriginalBank.clips.pose.board)\n        if not s.logged then s.logged=true;log('[jimmie-mirror] shown frame='..tostring(get_global_timer())) end\n    end\n    -- The game hides its Lakitu while the camera is outside the room; follow that.\n    local hidden=(lak.header.gfx.node.flags & GRAPH_RENDER_INVISIBLE)~=0\n    local face=lak.oFaceAngleYaw*math.pi/32768\n    local yaw=skate_model_angles(face+math.pi/2,0,0)\n    for _,o in ipairs({s.body,s.board}) do\n        o.oPosX,o.oPosZ=lak.oPosX,lak.oPosZ\n        o.oPosY=hidden and -10000 or (lak.oPosY-150)\n        o.oFaceAngleYaw,o.oFaceAnglePitch,o.oFaceAngleRoll=yaw,0,0\n        local a=o.header.gfx.animInfo;a.animFrame=0;a.animFrameAccelAssist=0;a.animAccel=65536\n    end\nend\nlocal function on_update()\n"),
      ("    if companionSpawn:observe(m) then\n", "    jimmie_mirror_step()\n    if companionSpawn:observe(m) then\n"),
    ]}))

# 12c2. Flying poses (arms out; one arm for the camera stick), used by the bridge scene and the opening.
CHANGES.append(dict(
    name='flypose', what='two looping flying poses for the camera-man scenes',
    marker=('original_clip_bank.lua', 'motion:flypose'),
    edits={'original_clip_bank.lua': [(BANK_END, (HERE / 'fly_bank_fragment.lua').read_text(encoding='utf-8') + BANK_END)]}))

# 12c2b. (The first camera-stick shape, camera-man/actors-v1 and bin/, was installed 2026-11-11 and replaced the same day
#        by the second shape below, change camstick2_files.)

# 12c3. The opening fly-in (and the ending wave): Jimmie is the flying camera man.
CHANGES.append(dict(
    name='opening', what='in the opening fly-in to the pipe and in the ending, the flying camera man is Jimmie',
    marker=('main.lua', 'motion:opening'),
    edits={'main.lua': [
      ("local function on_update()\n", "-- motion:opening. The opening fly-in to the pipe (and the ending, which reuses the same flying camera man):\n-- Lakitu is made invisible and Jimmie is drawn where he is, in his flying pose, with a sparkle trail. The cutscene\n-- object keeps running exactly as before; nothing here moves it, the camera or Mario.\nJIMMIE_OPENING={}\nfunction jimmie_opening_step()\n    local s=JIMMIE_OPENING\n    local lak=obj_get_first_with_behavior_id(id_bhvBeginningLakitu)\n    if not lak or lak.activeFlags==0 then\n        if s.body then\n            if s.body.activeFlags~=0 then obj_mark_for_deletion(s.body) end\n            if s.board and s.board.activeFlags~=0 then obj_mark_for_deletion(s.board) end\n            if s.stick and s.stick.activeFlags~=0 then obj_mark_for_deletion(s.stick) end;s.stick=nil\n            s.body=nil;s.board=nil;log('[jimmie-opening] gone frame='..tostring(get_global_timer()))\n        end\n        return\n    end\n    jimmie_intro_hide(lak,false)\n    if not (s.body and s.body.activeFlags~=0) then\n        if id_bhvjimmie==nil or E_MODEL_jimmie==nil or originalBoardModel==nil or not OriginalBank.clips.fly_cam then return end\n        local okA,body=pcall(spawn_non_sync_object,id_bhvjimmie,E_MODEL_jimmie,lak.oPosX,-10000,lak.oPosZ,function(o) end)\n        local okB,board=pcall(spawn_non_sync_object,id_bhvjimmie,originalBoardModel,lak.oPosX,-10000,lak.oPosZ,function(o) end)\n        if not (okA and okB and body and board) then return end\n        s.body,s.board,s.tick=body,board,0\n        smlua_anim_util_set_animation(body,OriginalBank.clips.fly_cam.body);smlua_anim_util_set_animation(board,OriginalBank.clips.fly_cam.board)\n        log('[jimmie-opening] shown frame='..tostring(get_global_timer()))\n    end\n    s.tick=s.tick+1\n    local hidden=(lak.header.gfx.node.flags & GRAPH_RENDER_INVISIBLE)~=0\n    local o=s.body\n    o.oPosX,o.oPosZ=lak.oPosX,lak.oPosZ\n    o.oPosY=hidden and -10000 or (lak.oPosY-90+10*math.sin(s.tick*.3))\n    local yaw=skate_model_angles(lak.oFaceAngleYaw*math.pi/32768+math.pi/2,0,0)\n    o.oFaceAngleYaw,o.oFaceAnglePitch,o.oFaceAngleRoll=yaw,0,0\n    local a=o.header.gfx.animInfo;local f=s.tick%24;a.animFrame=f;a.animFrameAccelAssist=f*65536;a.animAccel=65536\n    s.board.oPosY=-10000\n    -- The camera stick in his hand: a small model of our own, placed at his holding hand and pointing where he faces.\n    if not (s.stick and s.stick.activeFlags~=0) then\n        local id=smlua_model_util_get_id('jimmie_camstick_geo')\n        if id and id~=E_MODEL_ERROR_MODEL then\n            local ok,st=pcall(spawn_non_sync_object,id_bhvjimmie,id,o.oPosX,-10000,o.oPosZ,function(q) end)\n            if ok and st then s.stick=st end\n        end\n    end\n    if s.stick then\n        local f=lak.oFaceAngleYaw*math.pi/32768;local fx,fz=math.sin(f),math.cos(f);local side=JIMMIE_STICK_SIDE or 24\n        s.stick.oPosX=o.oPosX+fx*59+fz*side;s.stick.oPosZ=o.oPosZ+fz*59-fx*side\n        s.stick.oPosY=hidden and -10000 or (o.oPosY+89)\n        s.stick.oFaceAngleYaw,s.stick.oFaceAnglePitch,s.stick.oFaceAngleRoll=lak.oFaceAngleYaw,0,0\n        obj_scale_xyz(s.stick,.62,.62,.62)\n    end\n    if not hidden and s.tick%2==0 then jimmie_intro_sparkles(o.oPosX,o.oPosY+40,o.oPosZ,1,110) end\nend\nlocal function on_update()\n"),
      ("    jimmie_mirror_step()\n", "    jimmie_mirror_step()\n    jimmie_opening_step()\n"),
    ]}))

# 12d. Corner camera icon: the little Lakitu head beside the camera glyph is a Jimmie head (16x16, drawn for this,
#      ../camera-man/textures/jimmie_cam_head.png). A texture swap only; nothing is timed.
CHANGES.append(dict(
    name='camicon_file', what='the 16x16 Jimmie head picture for the corner camera icon',
    files={'textures/jimmie_cam_head.png': HERE.parent / 'camera-man' / 'textures' / 'jimmie_cam_head.png'}))
CHANGES.append(dict(
    name='camicon', what='the corner camera icon shows a Jimmie head instead of the Lakitu head',
    marker=('main.lua', 'motion:camicon'),
    edits={'main.lua': [
      ("local function on_update()\n",
       "-- motion:camicon. The camera man in the corner of the screen is Jimmie."+"\n"
       "JIMMIE_CAM_ICON=get_texture_info('jimmie_cam_head')\n"
       "if JIMMIE_CAM_ICON then texture_override_set('texture_hud_char_lakitu',JIMMIE_CAM_ICON) end\n"
       "local function on_update()\n"),
    ]}))

# 12c4. Follow-ups Josh asked to have checked (2026-11-11): he holds the camera stick on the bridge too, the
#       camera hangs lower on its line (model file), and Lakitu's flying sound is silenced in both scenes.
CHANGES.append(dict(
    name='camfix', what='camera stick on the bridge too; Lakitu flying sound silenced in the opening and on the bridge',
    marker=('main.lua', 'motion:camfix'),
    edits={'main.lua': [
      ("local function on_update()\n", "-- motion:camfix. Places the camera stick at a flying Jimmie's holding hand, pointing the way he faces.\nfunction jimmie_stick_place(s,x,y,z,face,hidden,size)\n    if not (s.stick and s.stick.activeFlags~=0) then\n        local id=smlua_model_util_get_id('jimmie_camstick_geo')\n        if not id or id==E_MODEL_ERROR_MODEL then return end\n        local ok,st=pcall(spawn_non_sync_object,id_bhvjimmie,id,x,-10000,z,function(q) end)\n        if not (ok and st) then return end\n        s.stick=st\n    end\n    local k=(size or .62)/.62;local fx,fz=math.sin(face),math.cos(face);local side=(JIMMIE_STICK_SIDE or 24)*k\n    s.stick.oPosX=x+fx*59*k+fz*side;s.stick.oPosZ=z+fz*59*k-fx*side\n    s.stick.oPosY=hidden and -10000 or (y+89*k)\n    s.stick.oFaceAngleYaw,s.stick.oFaceAnglePitch,s.stick.oFaceAngleRoll=math.floor(face*32768/math.pi)%65536,0,0\n    obj_scale_xyz(s.stick,size or .62,size or .62,size or .62)\nend\nlocal function on_update()\n"),
      # bridge: stick in his hand while he flies in and talks; gone when he lands
      ("    obj_scale_xyz(jimmie,size,size,-size);obj_scale_xyz(originalBoard,size,size,-size)\n",
       "    obj_scale_xyz(jimmie,size,size,-size);obj_scale_xyz(originalBoard,size,size,-size)\n"
       "    jimmie_stick_place(s,jimmie.oPosX,jimmie.oPosY,jimmie.oPosZ,math.atan2(dx,dz),false,size)\n"
       "    stop_sound(SOUND_AIR_LAKITU_FLY,lak.header.gfx.cameraToObject)\n"),
      ("        jimmie_intro_sparkles(x,y,z,14,170)\n",
       "        jimmie_intro_sparkles(x,y,z,14,170)\n"
       "        if s.stick and s.stick.activeFlags~=0 then obj_mark_for_deletion(s.stick) end;s.stick=nil\n"),
      # opening: silence the same sound there
      ("    s.tick=s.tick+1\n    local hidden=(lak.header.gfx.node.flags & GRAPH_RENDER_INVISIBLE)~=0\n    local o=s.body\n",
       "    s.tick=s.tick+1\n    local hidden=(lak.header.gfx.node.flags & GRAPH_RENDER_INVISIBLE)~=0\n    local o=s.body\n"
       "    stop_sound(SOUND_AIR_LAKITU_FLY_HIGHPRIO,lak.header.gfx.cameraToObject)\n"),
    ]}))

# 12c5. Camera stick, second shape: the camera hangs lower on its line. Goes with `camfix`.
CAMSTICK2 = HERE.parent / 'camera-man' / 'actors' / 'jimmie_camstick'
CHANGES.append(dict(
    name='camstick2_files', what='camera stick model with the camera hanging lower on its line',
    files={'actors/jimmie_camstick/geo.inc.c': CAMSTICK2 / 'geo.inc.c', 'actors/jimmie_camstick/model.inc.c': CAMSTICK2 / 'model.inc.c',
           'actors/jimmie_camstick_geo.bin': HERE.parent / 'camera-man' / 'bin2' / 'jimmie_camstick_geo.bin'}))

# 14. Bowser fights (2026-11-11, from the level pass): Bowser starts talking the moment Mario lands, and Jimmie was
#     not allowed to appear while a text box holds Mario, so he missed the start of every fight.
CHANGES.append(dict(
    name='textspawn', what='Jimmie may appear while Mario is held by a text box (Bowser fights start with one)',
    marker=('companion_spawn.lua', 'motion:textspawn'),
    edits={'companion_spawn.lua': [
      (" if g.ACT_GROUP_MASK and g.ACT_GROUP_CUTSCENE and (m.action & g.ACT_GROUP_MASK)==g.ACT_GROUP_CUTSCENE then return nil,'player-transition' end",
       " -- motion:textspawn. Text boxes are allowed; every other cutscene still keeps him away.\n"
       " local talking=m.action==g.ACT_READING_AUTOMATIC_DIALOG or m.action==g.ACT_WAITING_FOR_DIALOG or m.action==g.ACT_READING_NPC_DIALOG\n"
       " if not talking and g.ACT_GROUP_MASK and g.ACT_GROUP_CUTSCENE and (m.action & g.ACT_GROUP_MASK)==g.ACT_GROUP_CUTSCENE then return nil,'player-transition' end"),
    ]}))

# 13. Swimming (2026-11-11, from the level pass): he never appeared where Mario starts in water.
CHANGES.append(dict(
    name='swimpose', what='a looping swimming pose',
    marker=('original_clip_bank.lua', 'motion:swim'),
    edits={'original_clip_bank.lua': [(BANK_END, (HERE / 'swim_bank_fragment.lua').read_text(encoding='utf-8') + BANK_END)]}))
CHANGES.append(dict(
    name='swim', what='where the skater has no ground, Jimmie swims (deep water) or flies (moving floors) beside Mario instead of being absent',
    marker=('main.lua', 'motion:swim'),
    edits={'main.lua': [
      ("local function on_update()\n", "-- motion:swim. Where the skating Jimmie has no ground to stand on, a second Jimmie is drawn beside Mario instead:\n-- swimming while Mario is in deep water, flying (his camera-man pose) while Mario stands on a moving floor such as\n-- the tilting Bowser arena or a raft. Looks only: no collision, never nearer than arm's length, moves nothing.\nJIMMIE_SWIM={}\nfunction jimmie_swim_step()\n    local s=JIMMIE_SWIM;local m=gMarioStates[0]\n    if not (m and m.marioObj) then return end\n    local mx,my,mz=m.pos.x,m.pos.y,m.pos.z;local f=m.faceAngle.y*math.pi/32768\n    local tx,tz=mx+math.sin(f)*130-math.cos(f)*190,mz+math.cos(f)*130+math.sin(f)*190\n    local mode=nil\n    if jimmie and jimmie.activeFlags~=0 then s.alone=0\n    else\n        s.alone=(s.alone or 0)+1\n        if (m.action & ACT_FLAG_SWIMMING)~=0 or my<m.waterLevel-100 then mode='swim'\n        elseif s.alone>45 and m.floor and m.floor.object~=nil and math.abs(my-m.floorHeight)<4 then mode='fly' end\n    end\n    if obj_get_first_with_behavior_id(id_bhvBeginningLakitu) then mode=nil end\n    if mode then s.hold=20;s.mode=mode else s.hold=(s.hold or 0)-1 end\n    if s.hold<=0 then\n        if s.body then\n            if s.body.activeFlags~=0 then obj_mark_for_deletion(s.body) end\n            if s.board and s.board.activeFlags~=0 then obj_mark_for_deletion(s.board) end\n            s.body=nil;s.board=nil;s.clip=nil;log('[jimmie-swim] out frame='..tostring(get_global_timer()))\n        end\n        return\n    end\n    mode=s.mode\n    if not (s.body and s.body.activeFlags~=0) then\n        if id_bhvjimmie==nil or E_MODEL_jimmie==nil or originalBoardModel==nil or not OriginalBank.clips.swim or not OriginalBank.clips.fly then return end\n        local okA,body=pcall(spawn_non_sync_object,id_bhvjimmie,E_MODEL_jimmie,tx,-10000,tz,function(o) end)\n        local okB,board=pcall(spawn_non_sync_object,id_bhvjimmie,originalBoardModel,tx,-10000,tz,function(o) end)\n        if not (okA and okB and body and board) then return end\n        s.body,s.board,s.tick,s.x,s.y,s.z,s.face,s.clip=body,board,0,tx,my+(mode=='fly' and 500 or 0),tz,f,nil\n        log('[jimmie-swim] in mode='..mode..' frame='..tostring(get_global_timer()))\n    end\n    if s.clip~=mode then\n        s.clip=mode\n        smlua_anim_util_set_animation(s.body,OriginalBank.clips[mode].body);smlua_anim_util_set_animation(s.board,OriginalBank.clips[mode].board)\n    end\n    s.tick=s.tick+1\n    local ty=my+(mode=='fly' and 70 or 0)\n    local dx,dy,dz=tx-s.x,ty-s.y,tz-s.z;local d=math.sqrt(dx*dx+dz*dz)\n    if d>2500 then s.x,s.y,s.z=tx,ty,tz;dx,dy,dz,d=0,0,0,0 end\n    local step=math.min(26,d*.07);local nx,nz=s.x,s.z\n    if d>1 then nx,nz=s.x+dx/d*step,s.z+dz/d*step end\n    local ax,az=nx-mx,nz-mz;local ad=math.sqrt(ax*ax+az*az)\n    if ad<170 and ad>1 then nx,nz=mx+ax/ad*170,mz+az/ad*170 end\n    s.y=s.y+math.max(-14,math.min(14,dy*.08))\n    if mode=='swim' then\n        -- stay in open water: under the surface, off the bottom, never into ground\n        local water,floor=find_water_level(nx,nz),find_floor_height(nx,s.y+200,nz)\n        if water and floor and floor<water-110 then s.x,s.z=nx,nz\n        else water,floor=find_water_level(s.x,s.z),find_floor_height(s.x,s.y+200,s.z) end\n        if water and s.y>water-45 then s.y=water-45 end\n        if floor and s.y<floor+30 then s.y=floor+30 end\n    else s.x,s.z=nx,nz end\n    local turn=(f-s.face+math.pi)%(2*math.pi)-math.pi;s.face=s.face+turn*.08       -- he heads the way Mario is heading\n    local o=s.body\n    o.oPosX,o.oPosZ=s.x,s.z\n    if mode=='swim' then o.oPosY=s.y-30+5*math.sin(s.tick*.13) else o.oPosY=s.y+10*math.sin(s.tick*.3) end\n    local yaw=skate_model_angles(s.face+math.pi/2,0,0)\n    o.oFaceAngleYaw,o.oFaceAnglePitch,o.oFaceAngleRoll=yaw,0,0\n    local a=o.header.gfx.animInfo;local fr=s.tick%24;a.animFrame=fr;a.animFrameAccelAssist=fr*65536;a.animAccel=65536\n    s.board.oPosY=-10000\n    if mode=='fly' and s.tick%3==0 then jimmie_intro_sparkles(o.oPosX,o.oPosY+40,o.oPosZ,1,110) end\nend\nlocal function on_update()\n"),
      ("    jimmie_opening_step()\n", "    jimmie_opening_step()\n    jimmie_swim_step()\n"),
    ]}))

# 15b. One Jimmie (2026-11-11, Josh): the swimmer no longer blinks in and out; he dives in from where he skated and
#      leaps out to where he gets back on the board.
CHANGES.append(dict(
    name='leap', what='he dives from his skating spot into the water by Mario, and leaps out of the water to where he gets back on his board',
    marker=('main.lua', 'motion:leap'),
    edits={'main.lua': [('local function on_update()\n', "-- motion:leap. One Jimmie, not two: he dives from where he was skating into the water beside Mario, and leaps\n-- from the water to the spot where he gets back on his board. Looks only.\nfunction jimmie_leap_step(s,mode,tx,ty,tz)\n    local L=s.leap\n    if not L then\n        if s.dive then L={x=s.dive.x,y=s.dive.y,z=s.dive.z,t=0,kind='in'};s.dive=nil\n        elseif s.out then L={x=s.x,y=s.y,z=s.z,t=0,kind='out',ex=s.out.x,ey=s.out.y,ez=s.out.z}\n        else return false end\n        local ex,ez=L.ex or tx,L.ez or tz;local d=math.sqrt((ex-L.x)^2+(ez-L.z)^2)\n        if L.kind=='in' then L.n=math.max(14,math.min(45,math.floor(d/40)));L.h=120+d*.12\n        else L.n=math.max(10,math.min(18,math.floor(d/30)));L.h=110 end\n        s.leap=L\n        smlua_anim_util_set_animation(s.body,OriginalBank.clips.fly.body);smlua_anim_util_set_animation(s.board,OriginalBank.clips.fly.board)\n        log('[jimmie-leap] '..L.kind..' frames='..tostring(L.n)..' frame='..tostring(get_global_timer()))\n    end\n    L.t=L.t+1;local u=L.t/L.n;local ex,ey,ez\n    if L.kind=='in' then\n        ex,ey,ez=tx,ty,tz;local w=find_water_level(tx,tz)\n        if w and ey>w-45 then ey=w-45 end\n    else ex,ey,ez=L.ex,L.ey,L.ez;s.hold=20 end\n    local x,y,z=L.x+(ex-L.x)*u,L.y+(ey-L.y)*u+L.h*math.sin(math.pi*u),L.z+(ez-L.z)*u\n    if (ex-L.x)^2+(ez-L.z)^2>1 then s.face=math.atan2(ex-L.x,ez-L.z) end\n    local o=s.body\n    o.oPosX,o.oPosY,o.oPosZ=x,y,z\n    o.oFaceAngleYaw,o.oFaceAnglePitch,o.oFaceAngleRoll=skate_model_angles(s.face+math.pi/2,0,0),0,0\n    local a=o.header.gfx.animInfo;local fr=s.tick%24;a.animFrame=fr;a.animFrameAccelAssist=fr*65536;a.animAccel=65536\n    s.board.oPosY=-10000\n    if L.t>=L.n then\n        s.x,s.y,s.z=ex,ey,ez;s.leap=nil;s.clip=nil\n        if L.kind=='out' then s.out=nil;s.hold=0 end\n    end\n    return true\nend\nlocal function on_update()\n"), ("    local ty=my+(mode=='fly' and 70 or 0)\n", "    local ty=my+(mode=='fly' and 70 or 0)\n    if jimmie_leap_step(s,mode,tx,ty,tz) then return end\n"), ("s.body=nil;s.board=nil;s.clip=nil;log('[jimmie-swim] out frame='", "s.body=nil;s.board=nil;s.clip=nil;s.leap=nil;s.out=nil;log('[jimmie-swim] out frame='")]}))

# 16. Board pull (2026-11-11, Josh's idea): going from swimming or flying back to skating, he pulls his board out
#     from behind his back instead of just popping in on it.
CHANGES.append(dict(
    name='pullpose', what='a 40-frame clip: he pulls a toy-sized board from behind his back, tosses it down, it pops to full size, he hops on',
    marker=('original_clip_bank.lua', 'motion:boardpull'),
    edits={'original_clip_bank.lua': [(BANK_END, (HERE / 'pull_bank_fragment.lua').read_text(encoding='utf-8') + BANK_END)]}))
CHANGES.append(dict(
    name='boardpull', what='he leaves the shore to swim when Mario swims; back on land he pulls out his board first',
    marker=('main.lua', 'motion:boardpull'),
    edits={'main.lua': [
      ("local function on_update()\n", "-- motion:boardpull. When the skater comes back right after the swimming or flying Jimmie, he first stands for\n-- 40 frames and pulls a toy-sized board out from behind his back, tosses it down, it pops to full size and he hops\n-- on. When Mario has been swimming for two seconds the skater simply leaves (the swimming Jimmie takes over).\n-- Looks only; he does not move while the clip plays.\nJIMMIE_PULL={}\nfunction jimmie_pull_size(t)\n    local k={{0,.45},{.62,.45},{.70,1.2},{.78,1},{1,1}}                    -- same table as SIZE in swim/pull_motion.py\n    for i=1,#k-1 do\n        if t<=k[i+1][1] then return k[i][2]+(k[i+1][2]-k[i][2])*(t-k[i][1])/(k[i+1][1]-k[i][1]) end\n    end\n    return 1\nend\nfunction jimmie_pull_step()\n    local s=JIMMIE_PULL\n    if not (jimmie and originalBoard and jimmie.activeFlags~=0 and originalBoard.activeFlags~=0) then s.t=nil;s.wait=nil;s.wet=0;s.had=false;return false end\n    if not s.had then\n        s.had=true\n        if JIMMIE_SWIM and JIMMIE_SWIM.body and JIMMIE_SWIM.body.activeFlags~=0 and OriginalBank.clips.board_pull then\n            -- he is still in the water: wait, unseen, until he has leapt over to this spot\n            s.wait=0;JIMMIE_SWIM.out={x=jimmie.oPosX,y=jimmie.oPosY,z=jimmie.oPosZ}\n        end\n    end\n    local m=gMarioStates[0]\n    if s.wait then\n        s.wait=s.wait+1\n        if JIMMIE_SWIM.out==nil or s.wait>30 then\n            s.wait=nil;JIMMIE_SWIM.out=nil;JIMMIE_SWIM.hold=0;s.t=0\n            log('[jimmie-pull] begin frame='..tostring(get_global_timer()))\n        else\n            PHYS=nil;jimmieSpeed=0\n            originalController.bank:apply(jimmie,originalBoard,'board_pull',0,0)\n            obj_scale_xyz(jimmie,.001,.001,-.001);obj_scale_xyz(originalBoard,.001,.001,-.001)\n            return true\n        end\n    end\n    if not s.t then\n        if m and (m.action & ACT_FLAG_SWIMMING)~=0 then s.wet=(s.wet or 0)+1 else s.wet=0 end\n        if s.wet>60 and not dying and not PHYS_AIR and opportunityMotion==nil then\n            s.wet=0;JIMMIE_SWIM.dive={x=jimmie.oPosX,y=jimmie.oPosY,z=jimmie.oPosZ};despawn_jimmie();log('[jimmie-pull] dived frame='..tostring(get_global_timer()))\n            return true\n        end\n        return false\n    end\n    s.t=s.t+1\n    if s.t>40 then s.t=nil;log('[jimmie-pull] end frame='..tostring(get_global_timer()));return false end\n    PHYS=nil;jimmieSpeed=0\n    local t=(s.t-1)/39;local b=.62*jimmie_pull_size(t)\n    originalController.bank:apply(jimmie,originalBoard,'board_pull',t,0)\n    obj_scale_xyz(jimmie,.62,.62,-.62);obj_scale_xyz(originalBoard,b,b,-b)\n    return true\nend\nlocal function on_update()\n"),
      ("    elseif jimmie_intro_step(m) then\n", "    elseif jimmie_pull_step() then\n        -- He is pulling out his board this tick.\n    elseif jimmie_intro_step(m) then\n"),
    ]}))

# 16b. Wall safety (2026-11-11, Josh: "he's stuck in a wall"): the swimming / flying Jimmie had no wall check.
CHANGES.append(dict(
    name='wallsafe', what='the swimming or flying Jimmie never sits in or behind a wall: other side of Mario, then behind him, else out of sight',
    marker=('main.lua', 'motion:wallsafe'),
    edits={'main.lua': [('local function on_update()\n', "-- motion:wallsafe. True when nothing solid lies between two points at Mario's chest height (sampled every 60 units).\nfunction jimmie_open(ax,ay,az,bx,by,bz)\n    local d=math.sqrt((bx-ax)^2+(bz-az)^2);local n=math.max(1,math.ceil(d/60))\n    for i=1,n do\n        local q={x=ax+(bx-ax)*i/n,y=ay+(by-ay)*i/n,z=az+(bz-az)*i/n}\n        if resolve_and_return_wall_collisions(q,60,45)~=nil then return false end\n        if find_floor_height(q.x,q.y+150,q.z)<-10000 then return false end\n    end\n    return true\nend\nlocal function on_update()\n"), ('    local tx,tz=mx+math.sin(f)*130-math.cos(f)*190,mz+math.cos(f)*130+math.sin(f)*190\n', '    local tx,tz=mx+math.sin(f)*130-math.cos(f)*190,mz+math.cos(f)*130+math.sin(f)*190\n    -- Never beside Mario through a wall: try his other side, then behind him; otherwise stay out of sight.\n    local shut=false\n    if not jimmie_open(mx,my,mz,tx,my,tz) then\n        local ax,az=mx+math.sin(f)*130+math.cos(f)*190,mz+math.cos(f)*130-math.sin(f)*190\n        local bx,bz=mx-math.sin(f)*180,mz-math.cos(f)*180\n        if jimmie_open(mx,my,mz,ax,my,az) then tx,tz=ax,az elseif jimmie_open(mx,my,mz,bx,my,bz) then tx,tz=bx,bz else shut=true end\n    end\n'), ('    if d>2500 then s.x,s.y,s.z=tx,ty,tz;dx,dy,dz,d=0,0,0,0 end\n', '    if d>2500 then s.x,s.y,s.z=tx,ty,tz;dx,dy,dz,d=0,0,0,0 end\n    if not shut and not jimmie_open(mx,my,mz,s.x,my,s.z) then s.x,s.z=tx,tz;dx,dz,d=0,0,0 end   -- a wall came between them\n'), ("    s.board.oPosY=-10000\n    if mode=='fly' and s.tick%3==0 then", "    s.board.oPosY=-10000\n    if shut then o.oPosY=-10000 end\n    if mode=='fly' and not shut and s.tick%3==0 then")]}))

# 16c. Bubbles (2026-11-11, Josh): the swimming Jimmie breathes bubbles like Mario.
CHANGES.append(dict(
    name='bubbles', what='the swimming Jimmie lets out a bubble about once a second',
    marker=('main.lua', 'motion:bubbles'),
    edits={'main.lua': [('    local yaw=skate_model_angles(s.face+math.pi/2,0,0)\n', "    -- motion:bubbles. The game's own bubble, from his mouth, about once a second while he swims.\n    if mode=='swim' and not shut and s.tick%32==0 and id_bhvBubbleMaybe and E_MODEL_BUBBLE then\n        pcall(spawn_non_sync_object,id_bhvBubbleMaybe,E_MODEL_BUBBLE,s.x+math.sin(s.face)*45,o.oPosY+70,s.z+math.cos(s.face)*45,function(q) end)\n    end\n    local yaw=skate_model_angles(s.face+math.pi/2,0,0)\n")]}))

# 17. Keeping up (2026-11-11, from keep-up/KEEP_UP.md): crossing hops stopped him dead and flew at a fixed slow speed.
CHANGES.append(dict(
    name='keepup', what='hops keep pace with a fast Mario (short crouch, flight at his speed); no optional tricks beyond 420 units; no falls beyond 450',
    marker=('skate_opportunities.lua', 'motion:keepup'),
    edits={'skate_opportunities.lua': [(' if self.world.invalidateRails then self.world:invalidateRails() end\n self.episode=self.episode+1\n', " -- motion:keepup. While Mario is moving fast, a crossing hop travels at his pace instead of a fixed slow one and\n -- the crouch before it is 2 frames instead of 5. The path is the one already proved; only its timing changes.\n local quick=false\n if kind=='follow' and not plan.contactEntry and ctx.player then\n  local sp=math.sqrt((ctx.player.vx or 0)^2+(ctx.player.vz or 0)^2)\n  if sp>=16 then quick=true;plan.duration=math.max(9,math.min(plan.duration,math.ceil(dist(plan.a,plan.b)/math.max(22,sp)))) end\n end\n if self.world.invalidateRails then self.world:invalidateRails() end\n self.episode=self.episode+1\n"), ('approachOrigin=cp(p),windup=plan.contactEntry and 0 or O.WINDUP}', 'approachOrigin=cp(p),windup=plan.contactEntry and 0 or (quick and 2 or O.WINDUP)}')], 'skate_director.lua': [('    local catchingUp=rejoin or social>560\n', '    local catchingUp=rejoin or social>420 -- motion:keepup (was 560): no optional tricks until he is closer\n')], 'main.lua': [('function jimmie_bail_odds(clip,kind,speed)\n', '-- motion:keepup. More than 450 units behind a moving Mario: no falls until he has caught up.\nfunction jimmie_behind()\n    local m=gMarioStates[0]\n    if not (m and jimmie and jimmie.activeFlags~=0) or m.forwardVel<12 then return false end\n    local dx,dz=m.pos.x-jimmie.oPosX,m.pos.z-jimmie.oPosZ\n    return dx*dx+dz*dz>450*450\nend\nfunction jimmie_bail_odds(clip,kind,speed)\n    if jimmie_behind() then return 0 end\n'), ('function jimmie_landing_odds(p,event,speed,planned)\n', 'function jimmie_landing_odds(p,event,speed,planned)\n    if jimmie_behind() then return 0,0,nil end\n')]}))

# 17b. Stale objects (2026-11-11, found in my own test): leaving a level while the swimmer / flyer was showing left
#      it holding freed objects; in the next level it dragged, then deleted, an unrelated object.
CHANGES.append(dict(
    name='stalefix', what='the swimming / flying Jimmie lets go of its objects when the level changes (it could drag and delete an unrelated object)',
    marker=('main.lua', 'motion:stalefix'),
    edits={'main.lua': [('local function on_update()\n', '-- motion:stalefix. When the level or area changes the game frees every object. The swimming / flying Jimmie must\n-- drop its handles then, or it would move (and later delete) whatever object the game puts in the same slot next.\nfunction jimmie_swim_forget()\n    local s=JIMMIE_SWIM\n    s.body=nil;s.board=nil;s.clip=nil;s.leap=nil;s.out=nil;s.dive=nil;s.hold=0;s.alone=0\n    if JIMMIE_PULL then JIMMIE_PULL.wait=nil;JIMMIE_PULL.t=nil end\nend\nfunction jimmie_is_mine(o)\n    if not o or o.activeFlags==0 then return false end\n    local r=obj_has_behavior_id(o,id_bhvjimmie)\n    return r==true or r==1\nend\nhook_event(HOOK_ON_WARP,jimmie_swim_forget)\nif HOOK_ON_CLEAR_AREAS then hook_event(HOOK_ON_CLEAR_AREAS,jimmie_swim_forget) end\nlocal function on_update()\n'), ('    if not (m and m.marioObj) then return end\n    local mx,my,mz=m.pos.x,m.pos.y,m.pos.z;local f=m.faceAngle.y*math.pi/32768\n', '    if not (m and m.marioObj) then return end\n    if s.body and not (jimmie_is_mine(s.body) and jimmie_is_mine(s.board)) then jimmie_swim_forget() end\n    local mx,my,mz=m.pos.x,m.pos.y,m.pos.z;local f=m.faceAngle.y*math.pi/32768\n')]}))

# 18. Reactions (2026-11-11, step 4 of the v1.1 plan): looks only, no lines, no UI.
CHANGES.append(dict(
    name='reactpose', what='two reaction clips: a cheer and a wince',
    marker=('original_clip_bank.lua', 'motion:react'),
    edits={'original_clip_bank.lua': [(BANK_END, (HERE / 'react_bank_fragment.lua').read_text(encoding='utf-8') + BANK_END)]}))
CHANGES.append(dict(
    name='react', what='he cheers a triple jump, long jump, wall kick and star, and winces at a hurt, a big fall and a death',
    marker=('main.lua', 'motion:react'),
    edits={'main.lua': [('local function on_update()\n', "-- motion:react. He reacts to what Mario does, with his body only: a cheer for a triple jump, long jump, wall kick\n-- or star; a wince when Mario is hurt, lands a big fall or dies. Played over his riding stance for 24 frames while\n-- he keeps rolling; never during a trick, a grind, a fall or in the air. Nothing here moves him or Mario.\nJIMMIE_REACT={cool={}}\nfunction jimmie_react_step(m)\n    local s=JIMMIE_REACT;local f=get_global_timer()\n    if not m or not m.marioObj then return end\n    -- what Mario just did\n    local act=m.action;local cause,kind=nil,nil\n    if act~=s.act then\n        if act==ACT_TRIPLE_JUMP or act==ACT_SPECIAL_TRIPLE_JUMP or act==ACT_FLYING_TRIPLE_JUMP then cause,kind='triple_jump','cheer'\n        elseif act==ACT_LONG_JUMP then cause,kind='long_jump','cheer'\n        elseif act==ACT_WALL_KICK_AIR then cause,kind='wall_kick','cheer'\n        elseif act==ACT_HARD_BACKWARD_GROUND_KB or act==ACT_HARD_FORWARD_GROUND_KB then cause,kind='big_fall','wince'\n        elseif (act & ACT_GROUP_MASK)==ACT_GROUP_CUTSCENE and (act==ACT_STANDING_DEATH or act==ACT_DEATH_ON_BACK or act==ACT_DEATH_ON_STOMACH\n            or act==ACT_QUICKSAND_DEATH or act==ACT_ELECTROCUTION or act==ACT_SUFFOCATION) then cause,kind='death','wince' end\n    end\n    s.act=act\n    if not cause and s.hurt and m.hurtCounter>s.hurt then cause,kind='hurt','wince' end\n    s.hurt=m.hurtCounter\n    if not cause and s.stars and m.numStars>s.stars then cause,kind='star','cheer' end\n    s.stars=m.numStars\n    if cause then\n        -- the same move twice in a row is not news: long jumps at most every 10 seconds, the rest every 4\n        local wait=(cause=='long_jump' and 300 or 120)\n        if f-(s.cool[cause] or -9999)>=wait then s.cool[cause]=f;s.want={kind=kind,cause=cause,frame=f} end\n    end\n    if s.want and f-s.want.frame>(s.want.cause=='star' and 600 or 45) then s.want=nil end      -- too late to react\n    local p=PHYS\n    local free=jimmie and originalBoard and jimmie.activeFlags~=0 and p and p.onGround and not PHYS_AIR and not dying\n        and opportunityMotion==nil and not p.windup and not p.manual and not p.fakie\n    if not free then s.t=nil;return end\n    if s.want and not s.t then\n        local dx,dz=m.pos.x-jimmie.oPosX,m.pos.z-jimmie.oPosZ\n        if dx*dx+dz*dz<1800*1800 and OriginalBank.clips['react_'..s.want.kind] then\n            s.t=0;s.kind=s.want.kind\n            log('[jimmie-react] '..s.kind..' cause='..s.want.cause..' frame='..tostring(f))\n            local c=s.want.cause\n            if JIMMIE_BRAIN and (c=='triple_jump' or c=='long_jump' or c=='wall_kick') then pcall(JIMMIE_BRAIN.fact,'mario_move','mario',{move=c}) end\n        end\n        s.want=nil\n    end\n    if s.t then\n        s.t=s.t+1\n        if s.t>24 then s.t=nil;return end\n        originalController.bank:apply(jimmie,originalBoard,'react_'..s.kind,(s.t-1)/23,0)\n    end\nend\nlocal function on_update()\n"), ('    update_jumps()\n    update_host(m,true)\n', '    jimmie_react_step(m)\n    update_jumps()\n    update_host(m,true)\n')]}))

# 19. Wing Cap (2026-11-11, level table: Tower of the Wing Cap, he was there under half the time): while Mario flies
#     and the skater has no ground, Jimmie flies beside him; the flyer may keep up with a flying Mario.
CHANGES.append(dict(
    name='flywing', what='he flies beside Mario while Mario flies with the Wing Cap',
    marker=('main.lua', 'motion:flywing'),
    edits={'main.lua': [("        elseif s.alone>45 and m.floor and m.floor.object~=nil and math.abs(my-m.floorHeight)<4 then mode='fly' end\n", "        elseif s.alone>45 and m.floor and m.floor.object~=nil and math.abs(my-m.floorHeight)<4 then mode='fly'\n        elseif s.alone>45 and m.action==ACT_FLYING then mode='fly' end   -- motion:flywing. Mario flying with the Wing Cap\n"), ('    local step=math.min(26,d*.07);local nx,nz=s.x,s.z\n', "    local step=mode=='fly' and math.min(95,d*.3) or math.min(26,d*.07);local nx,nz=s.x,s.z\n"), ('    s.y=s.y+math.max(-14,math.min(14,dy*.08))\n', "    local rise=mode=='fly' and 70 or 14;s.y=s.y+math.max(-rise,math.min(rise,dy*(mode=='fly' and .3 or .08)))\n"), ('        if find_floor_height(q.x,q.y+150,q.z)<-10000 then return false end\n', "        if JIMMIE_SWIM.mode~='fly' and find_floor_height(q.x,q.y+150,q.z)<-10000 then return false end\n")]}))

# 20. Hair from behind (2026-11-11): now part of `model` above (MODEL points at hair-fix/bin). A separate later entry let
#     a reinstall copy the older bins back first, which reverted the hair once.

# 21. Air swim (2026-11-11, Josh to the release session: "can we use his swimming animation for flying too?"):
#     where the looks-only Jimmie flies beside Mario (moving floors, Wing Cap) he uses the swim stroke; no sparkles.
CHANGES.append(dict(
    name='airswim', what='beside Mario in the air he uses the swimming stroke instead of the flying pose; no sparkles there',
    marker=('main.lua', 'motion:airswim'),
    edits={'main.lua': [('        smlua_anim_util_set_animation(s.body,OriginalBank.clips[mode].body);smlua_anim_util_set_animation(s.board,OriginalBank.clips[mode].board)\n', '        -- motion:airswim. Beside Mario he swims through the air too; the flying pose stays for the camera-man scenes and his dives.\n        smlua_anim_util_set_animation(s.body,OriginalBank.clips.swim.body);smlua_anim_util_set_animation(s.board,OriginalBank.clips.swim.board)\n'), ("    if mode=='fly' and not shut and s.tick%3==0 then jimmie_intro_sparkles(o.oPosX,o.oPosY+40,o.oPosZ,1,110) end\n", '')]}))

# 22. Neck brace (2026-11-11, Josh: "his neck brace doesnt stay on his neck when he skates"): it followed the body's
#     animation but not the body's mirror.
CHANGES.append(dict(
    name='bracefix', what='the neck brace is mirrored like the body, so it stays on his neck in pushes, leans and tricks',
    marker=('stock_brace.lua', 'motion:bracefix'),
    edits={'stock_brace.lua': [(' g.obj_scale(brace,M.SCALE)\n', " -- motion:bracefix. Drawn with the body's own scale: since the regular stance the body is mirrored front to back,\n -- and a brace drawn un-mirrored sat on the wrong side in every pose that is not symmetric (pushes, leans, tricks).\n local sc=body.header.gfx.scale\n if sc and g.obj_scale_xyz then g.obj_scale_xyz(brace,sc.x,sc.y,sc.z) else g.obj_scale(brace,M.SCALE) end\n")]}))

# 23. Effects for v1.1.3 (2026-11-11, Josh: shadow, dust, sparks, sounds). Each is its own change so any can be dropped.
#     Rules: looks and sound only; Lua's own math.random, never the game's random; effect objects capped.
SHADOW = HERE.parent / 'effects'
CHANGES.append(dict(
    name='shadow_files', what='a model that draws only the game’s round ground shadow',
    files={'actors/jimmie_shadow/geo.inc.c': SHADOW / 'actors' / 'jimmie_shadow' / 'geo.inc.c', 'actors/jimmie_shadow/model.inc.c': SHADOW / 'actors' / 'jimmie_shadow' / 'model.inc.c',
           'actors/jimmie_shadow_geo.bin': SHADOW / 'bin' / 'jimmie_shadow_geo.bin'}))
CHANGES.append(dict(
    name='shadow', what='his ground shadow is back: under the skater and under him when he swims through the air',
    marker=('main.lua', 'motion:shadow'),
    edits={'main.lua': [('local function on_update()\n', "-- motion:shadow. His ground shadow, lost when the model moved to the animated skeleton (those model files never\n-- asked for one). A separate object that draws nothing but the game's own round shadow, placed at his feet each\n-- frame: under the skater, and under him when he swims through the air; not underwater, not in cutscenes.\nJIMMIE_FX={}\nfunction jimmie_fx_forget() JIMMIE_FX.shadow=nil;JIMMIE_FX.shadow2=nil end\nhook_event(HOOK_ON_WARP,jimmie_fx_forget)\nif HOOK_ON_CLEAR_AREAS then hook_event(HOOK_ON_CLEAR_AREAS,jimmie_fx_forget) end\nfunction jimmie_shadow_place(key,x,y,z,size)\n    local s=JIMMIE_FX;local o=s[key]\n    if o and not jimmie_is_mine(o) then o=nil;s[key]=nil end\n    if not x then if o then o.oPosY=-10000 end return end\n    if not o then\n        local id=smlua_model_util_get_id('jimmie_shadow_geo')\n        if not id or id==E_MODEL_ERROR_MODEL or id_bhvjimmie==nil then return end\n        local ok,q=pcall(spawn_non_sync_object,id_bhvjimmie,id,x,y,z,function(q) end)\n        if not (ok and q) then return end\n        o=q;s[key]=o\n    end\n    o.oPosX,o.oPosY,o.oPosZ=x,y,z;o.oInteractType=0;o.oCollisionDistance=0\n    obj_scale_xyz(o,size,size,size)\nend\nfunction jimmie_shadow_step()\n    local m=gMarioStates[0]\n    if not m or (m.action & ACT_GROUP_MASK)==ACT_GROUP_CUTSCENE then return end     -- scenes keep whatever was there\n    if jimmie and jimmie.activeFlags~=0 and not (JIMMIE_PULL and JIMMIE_PULL.wait) then\n        jimmie_shadow_place('shadow',jimmie.oPosX,jimmie.oPosY,jimmie.oPosZ,1.1)\n    else jimmie_shadow_place('shadow') end\n    local d=JIMMIE_SWIM\n    if d and d.body and jimmie_is_mine(d.body) and d.mode=='fly' and not d.leap and d.body.oPosY>-9000 then\n        jimmie_shadow_place('shadow2',d.body.oPosX,d.body.oPosY,d.body.oPosZ,1.1)\n    else jimmie_shadow_place('shadow2') end\nend\nlocal function on_update()\n"), ('    update_original_brace()\n    railPresentation:publish', '    update_original_brace()\n    jimmie_shadow_step()\n    railPresentation:publish')]}))

# 24. Effect core, dust, sparks, sounds (v1.1.3). `fxcore` is needed by the other three; each of those can be skipped.
CHANGES.append(dict(
    name='fxcore', what='shared effect plumbing: our own particle objects, capped at 24, no game random numbers',
    marker=('main.lua', 'motion:fxcore'),
    edits={'main.lua': [('local function on_update()\n', "-- motion:fxcore. Shared by the dust, spark and sound changes. Effect objects are our own: spawned with Jimmie's inert\n-- behaviour and a stock particle model, moved and removed here. Lua's math.random only; the game's random number\n-- generator is never called. At most 24 live effect objects; when full, new effects are simply not made.\nJIMMIE_FX=JIMMIE_FX or {}\nJIMMIE_FX.list={};JIMMIE_FX.prev={}\nfunction jimmie_fx_clear() JIMMIE_FX.list={};JIMMIE_FX.prev={} end\nhook_event(HOOK_ON_WARP,jimmie_fx_clear)\nif HOOK_ON_CLEAR_AREAS then hook_event(HOOK_ON_CLEAR_AREAS,jimmie_fx_clear) end\nfunction jimmie_fx_spawn(model,x,y,z,q)\n    local L=JIMMIE_FX.list\n    if #L>=24 or not model or id_bhvjimmie==nil then return end\n    local ok,o=pcall(spawn_non_sync_object,id_bhvjimmie,model,x,y,z,function(o) end)\n    if not (ok and o) then return end\n    obj_set_billboard(o);o.oInteractType=0;o.oCollisionDistance=0\n    q.o=o;q.t=0;obj_scale_xyz(o,q.s0,q.s0,q.s0);L[#L+1]=q\nend\nfunction jimmie_fx_tick()\n    local L=JIMMIE_FX.list\n    for i=#L,1,-1 do\n        local q=L[i];local o=q.o\n        if not jimmie_is_mine(o) then table.remove(L,i)\n        else\n            q.t=q.t+1\n            if q.t>=q.life then obj_mark_for_deletion(o);table.remove(L,i)\n            else\n                local k=q.t/q.life\n                o.oPosX,o.oPosY,o.oPosZ=o.oPosX+(q.vx or 0),o.oPosY+(q.vy or 0),o.oPosZ+(q.vz or 0)\n                if q.grav then q.vy=(q.vy or 0)-q.grav end\n                local s=q.s0+(q.s1-q.s0)*k;obj_scale_xyz(o,s,s,s)\n                if q.fade then o.oOpacity=math.floor(q.fade*(1-k)) end\n                if q.frames then o.oAnimState=math.floor(k*q.frames) end\n            end\n        end\n    end\nend\nfunction jimmie_effects_step()\n    jimmie_fx_tick()\n    local m=gMarioStates[0];local s=JIMMIE_FX.prev\n    if not m or (m.action & ACT_GROUP_MASK)==ACT_GROUP_CUTSCENE then return end          -- no effects during scenes or text\n    if jimmie_fx_water then jimmie_fx_water() end\n    local alive=jimmie and jimmie.activeFlags~=0\n    local crash=alive and originalCrashHost~=nil and originalCrashHost.active==true\n    local p=PHYS\n    if not alive or (JIMMIE_PULL and (JIMMIE_PULL.wait or JIMMIE_PULL.t)) then s.have=false;s.crash=false;return end\n    local st={x=jimmie.oPosX,y=jimmie.oPosY,z=jimmie.oPosZ,obj=jimmie,crash=crash,tick=get_global_timer(),turn=0,speed=0}\n    st.bailed=crash and not s.crash;s.crash=crash\n    if p and not crash then\n        st.speed=math.sqrt((p.vx or 0)^2+(p.vz or 0)^2);st.ground=p.onGround==true and not PHYS_AIR\n        st.grind=opportunityMotion~=nil and (opportunityMotion.grind==true or opportunityMotion.phase=='grind')\n        st.push=PHYS_PUSHING==true;st.yaw=p.yaw or 0\n        if s.have then\n            st.pushed=st.push and not s.push;st.landed=st.ground and not s.ground;st.popped=(not st.ground) and s.ground\n            st.turn=math.abs(((st.yaw-s.yaw+math.pi)%(2*math.pi))-math.pi)\n        end\n        s.have=true;s.push=st.push;s.ground=st.ground;s.yaw=st.yaw\n    else s.have=false end\n    if jimmie_fx_dust then jimmie_fx_dust(st) end\n    if jimmie_fx_sparks then jimmie_fx_sparks(st) end\n    if jimmie_fx_sounds then jimmie_fx_sounds(st) end\nend\nlocal function on_update()\n"), ('    railPresentation:publish(rail_presentation_context())\n', '    jimmie_effects_step()\n    railPresentation:publish(rail_presentation_context())\n')]}))
CHANGES.append(dict(
    name='dust', what='dust puffs when he pushes off, lands, turns hard, and bigger ones when he bails',
    marker=('main.lua', 'motion:dust'),
    edits={'main.lua': [('local function on_update()\n', "-- motion:dust. The game's white puff model: one when he pushes off, two when he lands, one every few frames in a hard\n-- turn, four bigger ones when he bails.\nfunction jimmie_fx_dust(st)\n    local function puff(n,size,spread)\n        for _=1,n do\n            jimmie_fx_spawn(E_MODEL_MIST,st.x+(math.random()-.5)*spread,st.y+8,st.z+(math.random()-.5)*spread,{life=12,s0=size*.5,s1=size*1.6,vy=1.2,fade=190})\n        end\n    end\n    if st.bailed then puff(4,2.2,90);return end\n    if not st.ground then return end\n    if st.pushed then puff(1,1.0,20) end\n    if st.landed then puff(2,1.3,50) end\n    if st.turn>.07 and st.speed>12 and st.tick%5==0 then puff(1,1.0,30) end\nend\nlocal function on_update()\n")]}))
CHANGES.append(dict(
    name='sparks', what='sparks from the board while he grinds',
    marker=('main.lua', 'motion:sparks'),
    edits={'main.lua': [('local function on_update()\n', '-- motion:sparks. While he grinds: a small spark every other frame, thrown back and up from the board, falling.\nfunction jimmie_fx_sparks(st)\n    if not st.grind or st.tick%2~=0 then return end\n    local b=(st.yaw or 0)+math.pi\n    jimmie_fx_spawn(E_MODEL_SPARKLES,st.x+(math.random()-.5)*30,st.y+6,st.z+(math.random()-.5)*30,\n        {life=9,s0=.45,s1=.1,vx=math.sin(b)*4+(math.random()-.5)*5,vy=5+math.random()*4,vz=math.cos(b)*4+(math.random()-.5)*5,grav=1.1,frames=5})\nend\nlocal function on_update()\n')]}))
# skatesounds: removed 2026-11-11. Josh after playing: "The sounds are terrible. we need to get rid of skate sounds for 1.1.3".

# 25. Bubbles without the game's random numbers (v1.1.3): the released bubbles used the stock bubble behaviour,
#     which calls the game's random number generator. Needs `fxcore`.
CHANGES.append(dict(
    name='bubblefx', what='his swimming bubbles are our own objects, so they no longer draw from the game\u2019s random numbers',
    marker=('main.lua', 'motion:bubblefx'),
    edits={'main.lua': [('        pcall(spawn_non_sync_object,id_bhvBubbleMaybe,E_MODEL_BUBBLE,s.x+math.sin(s.face)*45,o.oPosY+70,s.z+math.cos(s.face)*45,function(q) end)\n', "        -- motion:bubblefx. Our own bubble object instead of the game's bubble behaviour, which draws from the game's\n        -- random numbers. Same model; it rises and is removed at the surface.\n        local bw=find_water_level(s.x,s.z);local by=o.oPosY+70\n        if jimmie_fx_spawn and bw and by<bw-30 then\n            jimmie_fx_spawn(E_MODEL_BUBBLE,s.x+math.sin(s.face)*45,by,s.z+math.cos(s.face)*45,\n                {life=math.max(4,math.min(40,math.floor((bw-by)/6))),s0=.5,s1=.9,vy=6,vx=(math.random()-.5)*1.5,vz=(math.random()-.5)*1.5})\n        end\n")]}))

# 25b. Scene sparkles without the game's random numbers (v1.1.3): opening fly-in, bridge arrival and his dive used the
#      stock sparkle spawner. Needs `fxcore`. Looks only; the scenes' frames are not touched.
CHANGES.append(dict(
    name='sparklefx', what='the sparkles in the opening and bridge scenes are our own objects, so they no longer draw from the game random numbers',
    marker=('main.lua', 'motion:sparklefx'),
    edits={'main.lua': [('        spawn_non_sync_object(id_bhvSparkleSpawn,E_MODEL_NONE,x+(math.random()-.5)*spread,y+math.random()*spread,z+(math.random()-.5)*spread,nil)\n', "        -- motion:sparklefx. Our own sparkle objects (same sparkle model) instead of the game's sparkle spawner, which\n        -- draws from the game's shared random numbers every frame.\n        if jimmie_fx_spawn then\n            jimmie_fx_spawn(E_MODEL_SPARKLES_ANIMATION or E_MODEL_SPARKLES,x+(math.random()-.5)*spread,y+math.random()*spread,z+(math.random()-.5)*spread,\n                {life=10,s0=.9,s1=.45,vy=1,frames=5})\n        end\n"), ('    jimmie_opening_step()\n    jimmie_swim_step()\n', '    if jimmie_fx_tick then jimmie_fx_tick() end\n    jimmie_opening_step()\n    jimmie_swim_step()\n'), ('function jimmie_fx_tick()\n    local L=JIMMIE_FX.list\n', 'function jimmie_fx_tick()\n    local L=JIMMIE_FX.list;local f=get_global_timer()\n    if JIMMIE_FX.ticked==f then return end;JIMMIE_FX.ticked=f\n')]}))

# 25c. Fairy swim (2026-11-11, Josh: "get rid of the camera stick and instead just have jimmy doing the swimming animation
#      like a fairy swimming while flying around"): opening fly-in, ending and bridge arrival use the swim clip; the
#      camera stick is no longer made. Looks only; clip is 24 frames like the flying poses; scene frames untouched.
CHANGES.append(dict(
    name='fairyswim', what='in the opening, the ending and the bridge arrival he swims through the air; no camera stick',
    marker=('main.lua', 'motion:fairyswim'),
    edits={'main.lua': [("    local fc=s.talking and 'fly_cam' or 'fly'\n", "    local fc='swim'   -- motion:fairyswim. He swims through the air like a fairy; no camera stick.\n"), ('        smlua_anim_util_set_animation(body,OriginalBank.clips.fly_cam.body);smlua_anim_util_set_animation(board,OriginalBank.clips.fly_cam.board)\n', '        smlua_anim_util_set_animation(body,OriginalBank.clips.swim.body);smlua_anim_util_set_animation(board,OriginalBank.clips.swim.board)\n'), ("    if not (s.stick and s.stick.activeFlags~=0) then\n        local id=smlua_model_util_get_id('jimmie_camstick_geo')\n        if id and id~=E_MODEL_ERROR_MODEL then\n", '    if not (s.stick and s.stick.activeFlags~=0) then\n        local id=nil   -- no camera stick\n        if id and id~=E_MODEL_ERROR_MODEL then\n'), ('function jimmie_stick_place(s,x,y,z,face,hidden,size)\n', 'function jimmie_stick_place(s,x,y,z,face,hidden,size)\n    do return end   -- no camera stick\n')]}))

# 26. Long grinds (2026-11-11, Josh after playing: "he should be able to grind a lot longer, and especially if im
#     walking along a fence, he should hop on and grind it"). Nothing is forced or named: a visible rail that runs
#     the way Mario is heading is measured out to 1728 units (was 576); a grind may last 6 s (was 2) at Mario's
#     pace; the wait before the next rail is 4-8 s (was 9-16); he steps off if the rail leaves Mario behind.
CHANGES.append(dict(
    name='grindmore', pending=True, what='longer grinds on rails that run the way Mario is heading, rails more often, steps off if it leaves Mario behind',
    marker=('skate_opportunities.lua', 'motion:grindmore'),
    edits={'skate_surface_rails.lua': [('points=math.min(25,math.floor(visual.remaining/24)+1)', 'points=math.min((dx*fx+dz*fz)>=.7 and 73 or 25,math.floor(visual.remaining/24)+1)')], 'skate_opportunities.lua': [("  if k<1 and (speed<=.01 or t.grindTicks>=60) then\n   t.phase='dismount';t.exitTry=0;t.dismountReason='momentum-stall'\n", "  -- motion:grindmore. Up to 6 seconds on a rail (was 2). He steps off early if the rail is carrying him away from Mario.\n  local leaving=dist(p,ctx.player)>700\n  if k<1 and (speed<=.01 or t.grindTicks>=180 or leaving) then\n   t.phase='dismount';t.exitTry=0;t.dismountReason=leaving and 'left-player-behind' or 'momentum-stall'\n"), (' while progress<total and grindFrames<60 do\n', ' while progress<total and grindFrames<180 do\n'), (" if horizon>105 then return false,'optional-trip-too-long' end\n", " if horizon>230 then return false,'optional-trip-too-long' end\n"), (' if dist(rail.exit,predicted)>650 then\n', ' if dist(rail.exit,predicted)>650 and not O.railPace(rail,rail.a,m) then\n'), (' local nextFun=ctx.time+9+self.rng()*7\n', ' local nextFun=ctx.time+4+self.rng()*4\n')]}))

# Tried and dropped on 2026-11-10: a dust puff at the pop and landing (the game's own white puff objects).
# It spawned without errors but was too faint to see on sand in the captures, so it is not applied.
