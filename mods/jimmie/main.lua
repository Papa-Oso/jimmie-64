-- name: Jimmie Terrain Review Candidate
-- description: Private stock v1.5.1 trial: original motion and bounded recorded voice; no live AI service/title/PB.
--   and instantly respawns. Kick-driven skateboard chase, jump-mimic tricks,
--   50/50 vest lottery. Cosmetic only - never affects Mario or gameplay.

local MOD_VERSION = "stock-motion-0.2.0"
local companionSpawn=require('companion_spawn').new(_G)
local OriginalBank=require('original_clip_bank')
local OriginalMotion=require('original_motion_controller')
local originalController=OriginalMotion.new(OriginalBank.new())
local railPresentation=require('skate_rail_binding').new({anchor=require('skate_rail_presentation'),
    clips=OriginalBank.clips,animationName=smlua_anim_util_get_current_animation_name,setGfxPos=obj_set_gfx_pos})
local originalBoard=nil
local originalBoardModel=nil
local originalSkin='raglan'
local originalScene=0
local requestedOriginalTrick=nil
local originalCrashHost=nil
local originalBrace=nil
local originalBraceModel=nil
local OriginalBrace=require('stock_brace')
local TrickOutcomes=require('trick_outcomes')
local originalOutcomes=TrickOutcomes.new()
-- Private spoken candidate: selected existing authored/real recordings only.
-- No external service, live TTS, native title/PB/rejoin extension or imported motion bank.

-- Passive staged instrumentation; no ownership, movement, death or model changes.
local skateTraceAdapter, skateTraceMotionFrame, skateTraceAllowed, skateTraceFault
local skateTraceUpdateSeconds, skateTraceBounds
local rejoinTraceResult -- same-frame measurement, never a movement owner

-- ---------------------------------------------------------------------------
-- tuning
-- ---------------------------------------------------------------------------
local FOLLOW_DIST       = 110     -- desired distance beside Mario
local WALK_SPEED        = 14      -- units/frame while close
local RUN_SPEED         = 26      -- units/frame while behind
local BOARD_SPEED       = 44      -- kick-driven skateboard catch-up
local BOARD_DIST        = 650     -- distance that triggers the board
local TELEPORT_DIST     = 1600    -- teleport back if this far away
local BARK_GAP          = 1.1     -- min seconds between any two barks
local CHASE_GAP         = 6.0     -- min seconds between chase barks
local IDLE_GAP          = 14.0
local DEATH_MIN         = 35.0    -- jimmie randomly dies every 35-75 s
local DEATH_MAX         = 75.0
local RESPAWN_TIME      = 0.9

-- ---------------------------------------------------------------------------
-- state
-- ---------------------------------------------------------------------------
local jimmie            = nil     -- companion Object
local jimmieDeadUntil   = 0
local dying             = false
local dyingUntil        = 0
local deathSpin         = 0
local lastBark          = 0
local lastChaseBark     = 0
local lastIdleBark      = 0
local lastDeath         = 0
local nextDeath         = 0
local onBoard           = false
local lastBoardBark     = 0
local prevVelY          = 0
local farAway           = false
local vest              = false
local deathCount        = 0
local subtitle          = nil
local subtitleUntil     = 0
local enabled           = true
local bags              = {}      -- category -> shuffle bag
local clips             = {}      -- category -> array of ModAudio
local soundsReady       = false
local VOICE -- shared by the early audio hooks and later gameplay events
local hostDirector
local routeEnabled=false
local okMimic,MimicPolicy=pcall(require,"mimic_director")
local mimicDirector=okMimic and MimicPolicy.new() or nil
local okRuntime, Personality = pcall(require, "personality_runtime")
if not okRuntime then print("[jimmie] personality runtime unavailable: " .. tostring(Personality)); Personality=nil end
local contextState = Personality and Personality.new() or nil
local okSkate, SkateDirector = pcall(require, "skate_director")
if not okSkate then print("[jimmie] skate director unavailable: " .. tostring(SkateDirector)); SkateDirector=nil end
local skateDirector = SkateDirector and SkateDirector.new() or nil
-- Measurement-only recorder: disabled by default, one branch per frame when off.
-- Control arrives through the existing relay.lua hot-reload command channel.
local okTrace, TraceRecorder = true, nil
if not okTrace then print("[jimmie] frame recorder disabled: " .. tostring(TraceRecorder)); TraceRecorder=nil end
-- Silent dry-run performance timeline: default off, never plays audio, read-only.
local okShadow, ShadowPerf = true, nil
if not okShadow then print("[jimmie] shadow mode disabled: " .. tostring(ShadowPerf)); ShadowPerf=nil end
-- Run-mode detection: speedrun systems only after a fast spawn->castle-door time;
-- everything else defaults to normal play.
local okRunMode, RunMode = pcall(require, "run_mode")
if not okRunMode then print("[jimmie] run mode disabled: " .. tostring(RunMode)); RunMode=nil end
local manualMode = nil
local aiEnabled = false -- no external local service in this candidate
local planningMenus = {}
local currentSkateIntent, currentSkateSensors = nil,nil
local safeSpots, nextProbeAt, previousGrounded, lastSkateState = {},0,nil,nil
local marioTrail,trailSerial,trailProgress,farSince={},0,0,nil
local nextActiveChatter = 10
local wasGameplayAllowed = true
local greeted = false
local pendingLevelGreeting = false
local speechLastPhys = nil
local speechWasAir = false
local speechFlight = nil
local speechStars = nil
local speechHealth = nil
-- Staged recovery integration. No model or save changes; one motion owner.
-- Stable ground-skating baseline: navigation experiments remain unconstructed.
-- Keep hooks inert so this build cannot float, take ownership, or capture terrain.
local recoveryController = nil
-- Arcade opportunity layer: inactive ground skating is unchanged.
local okOpportunity, Opportunity = pcall(require, "skate_opportunities")
local okProbes, SkateProbes = pcall(require, "skate_probes")
local skateOpportunity = okOpportunity and okProbes and Opportunity.new(SkateProbes.new(_G)) or nil
local opportunityMotion = nil
local okBalance, Balance = pcall(require, "skate_balance")
if not okBalance then Balance=nil end

-- One-shot placement only. The ordinary integrator remains the movement owner.
local okRejoin, RejoinHost = pcall(require, "rejoin_host")
local rejoinHost = nil
if okRejoin then
    local ok, host = pcall(RejoinHost.new, _G,function(body,board,brace) return body==jimmie and board==originalBoard and (brace==nil or brace==originalBrace) end)
    if ok then rejoinHost = host end
end
local recoveryChoiceFloor = -1
local now -- shared monotonic clock, assigned before callbacks run
local function recovery_suppressed()
    return recoveryController and recoveryController:suppress(now()) or false
end

local CATEGORIES = {
    "death_generic", "death_lava", "death_water", "death_fall", "death_crush",
    "death_enemy", "death_board", "death_left_behind", "death_desync",
    "respawn", "chase_near", "chase_mid", "chase_far", "chase_abandoned",
    "reunion", "trick_ollie", "trick_kickflip", "trick_bail", "board_break",
    "star", "level_enter", "level_exit", "vest_yes", "vest_no", "bet_win",
    "bet_lose", "roast", "chat", "idle", "special", "skateboard", "skate_tricks",
    "catchphrase",
    "real_holy_shit", "real_come_on", "real_good_morning",
    "real_unbelievable", "real_shit_it_down", "real_whats_happening",
    "real_world_record", "real_no_no_no",
    "real_whats_happening", "real_thank_you_guys", "real_lets_go",
    "real_swa_swa", "real_gub_gub", "real_boing_boing",
    "real_carrier", "real_unreal", "real_honey_oil",
}

-- ---------------------------------------------------------------------------
-- helpers
-- ---------------------------------------------------------------------------
-- Preserve timer continuity when the engine frame counter resets on transitions.
local lastClockFrame, monotonicClockFrame = nil, nil
now = function()
    local frame = get_global_timer()
    if lastClockFrame == nil then
        monotonicClockFrame = frame
    elseif frame >= lastClockFrame then
        monotonicClockFrame = monotonicClockFrame + frame - lastClockFrame
    else
        -- New counter epoch. Never send existing cooldowns back into the future.
        monotonicClockFrame = monotonicClockFrame + math.max(0, frame)
    end
    lastClockFrame = frame
    return monotonicClockFrame / 30.0
end

local function log(msg)
    print("[jimmie] " .. tostring(msg))
end

local lastError = nil
local lastChatMsg = nil
local updateCount = 0

local function protect(name, fn)
    return function(...)
        local ok, result = pcall(fn, ...)
        if not ok then
            lastError = name .. ": " .. tostring(result)
            print("[jimmie] SCRIPT ERROR " .. lastError)
            return nil
        end
        return result -- hook return values (especially Mario sound IDs) must survive protection.
    end
end

local function rand(a, b)
    return a + math.random() * (b - a)
end

local function dist3(a, b)
    local dx, dy, dz = a.x - b.x, a.y - b.y, a.z - b.z
    return math.sqrt(dx * dx + dy * dy + dz * dz)
end

-- ---------------------------------------------------------------------------
-- audio
-- ---------------------------------------------------------------------------
local SOUND_FILES = require("sound_files") -- bounded private recorded-voice package

local function load_category(cat)
    if clips[cat] ~= nil then return clips[cat] end
    local list = {}
    for _, name in ipairs(SOUND_FILES[cat] or {}) do
        local ok, snd = pcall(VOICE.performanceScope.load, name)
        if ok and snd ~= nil then
            list[#list + 1] = snd
            if VOICE ~= nil and VOICE.register ~= nil then VOICE.register(snd, name) end
        end
    end
    clips[cat] = list
    if #list > 0 then log(string.format("loaded %d clips for %s", #list, cat)) end
    return list
end

local function load_all_sounds()
    if soundsReady then return end
    soundsReady = true
    for _, cat in ipairs(CATEGORIES) do
        load_category(cat)
    end
end

local function pick(cat)
    local list = load_category(cat)
    if #list == 0 then return nil end
    local bag = bags[cat]
    if bag == nil or #bag == 0 then
        bag = {}
        for i = 1, #list do bag[i] = list[i] end
        for i = #bag, 2, -1 do
            local j = math.random(i)
            bag[i], bag[j] = bag[j], bag[i]
        end
        bags[cat] = bag
    end
    return table.remove(bag)
end

local function audio_pos()
    local v = { x = 0, y = 0, z = 0 }
    if jimmie ~= nil and object_pos_to_vec3f ~= nil then
        object_pos_to_vec3f(v, jimmie)
    else
        local m = gMarioStates[0]
        if m ~= nil then v = { x = m.pos.x, y = m.pos.y, z = m.pos.z } end
    end
    return v
end

local JIMMIE_VOICE_GAIN = require("voice_gain")
local function play_clip(snd, volume, grant, event)
    local registered = VOICE and VOICE.registered and VOICE.registered[snd]
    local name = registered and registered.name
    if not name then
        local pathOk, path = pcall(function() return snd.filepath end)
        if pathOk and type(path) == "string" then
            name = path:gsub("\\", "/"):match("([^/]+)$")
        end
    end
    local scope=VOICE and VOICE.performanceScope
    name=scope and scope.sound_name(snd,name)
    if not scope or not name or VOICE.ELIGIBILITY[name] or not scope.allows(name,event,grant) then return false end
    local receipt=scope.consume(grant,name,event)
    local gain = JIMMIE_VOICE_GAIN.volume(name, volume or 1.0)
    local ok = pcall(audio_sample_play, snd, audio_pos(), gain)
    if ok and receipt then print("[performance-start] "..Personality.json(receipt)) end
    if not ok then log("audio_sample_play failed") end
    return ok
end

-- ---------------------------------------------------------------------------
-- Observe Mario voice without replacing native character sounds
-- HOOK_CHARACTER_SOUND receives a CharacterSound slot, not a raw sound ID.
-- A numeric return overrides native audio; nil preserves the engine's lookup.
-- Queue Jimmie's source-triggered response separately, then leave Mario alone.
-- ---------------------------------------------------------------------------
local voiceEnabled = true
local function on_character_sound(m,sound)
    if not enabled or not voiceEnabled or m==nil or m.playerIndex~=0 or VOICE==nil then return nil end
    local scene=contextState and contextState:scene(gNetworkPlayers and gNetworkPlayers[0]) or "scene"
    local bit
    if mimicDirector then
        bit=mimicDirector:plan(sound,now(),{playerIndex=m.playerIndex,enabled=enabled,voiceEnabled=voiceEnabled,
            scene=scene,silent=VOICE.mode=="silent",afk=VOICE.afk,dead=dying,
            available=jimmie~=nil,gameplay=not Personality or Personality.gameplay(m)})
    elseif sound==29 then
        bit={category="mv_mama_mia",event="mario_mama_mia",ttl=7,priority=85,notBefore=now()+0.45}
    end
    if sound==29 and m.playerIndex==0 and JIMMIE_BRAIN and JIMMIE_BRAIN.live() then
        JIMMIE_BRAIN.fact("mario_voice","mario",{cue="mamma_mia"})
    end
    if bit then
        VOICE.post(bit.event,{cats={bit.category},ttl=bit.ttl,priority=bit.priority,
            volume=0.8,notBefore=bit.notBefore})
    end
    return nil
end

local okv
okv, VOICE = pcall(require, "voice")
if not okv then error("bounded voice failed to load: " .. tostring(VOICE)) end
if VOICE ~= nil then
    VOICE.init(nil, play_clip, audio_pos, now, log, load_category)
    VOICE.available = function()
        local m=gMarioStates[0]
        return enabled and not dying and jimmie~=nil and m~=nil and m.marioObj~=nil
    end
    VOICE.distance = function()
        local m = gMarioStates[0]
        if not enabled or jimmie == nil or m == nil or m.marioObj == nil then return math.huge end
        return dist3(m.pos, {x=jimmie.oPosX, y=jimmie.oPosY, z=jimmie.oPosZ})
    end
    VOICE.onStopped=function() subtitle=nil;subtitleUntil=0 end
    VOICE.onPlayed = function(meta, event, seconds)
        lastBark = now()
        if mimicDirector and (event=="mimic" or event=="mario_mama_mia") and meta and meta.name then
            mimicDirector:played(meta.name,now(),seconds)
        end
        if contextState then contextState:speech(meta,event,seconds,now()) end
        if meta ~= nil and meta.text ~= nil and meta.text ~= "" then
            subtitle = (event=="water_stream_drop" and "Stream clip: " or "Jimmie: ") .. meta.text
            subtitleUntil = now() + seconds
        end
    end
end

-- Default-OFF real-clip reaction playback path (single whole clips only).
local okPlayback, PerformancePlayback = true, nil
if not okPlayback then
    print("[jimmie] performance playback disabled: " .. tostring(PerformancePlayback))
    PerformancePlayback = nil
end
if PerformancePlayback ~= nil and ShadowPerf ~= nil then
    PerformancePlayback.init(VOICE)
    ShadowPerf.setEventHandler(function(variant, event)
        if PerformancePlayback ~= nil then
            PerformancePlayback.onEvent(variant, event)
        end
    end)
end

local okHost, HostRuntime=true,nil
if okHost and HostRuntime and VOICE then hostDirector=HostRuntime.new({voice=VOICE,now=now,log=log})
elseif not okHost then log("host runtime unavailable: "..tostring(HostRuntime)) end

-- Audition wiring (owner-approved reversible demo build, default OFF; 2026-11-08).
-- Rollback: restore .jimmie-audition-backup-20261108\mods\jimmie\jimmie over this folder.
-- NOTE: no new chunk-level locals here (main.lua is at the Lua 200-local limit);
-- a closure keeps the module reference in a global, not a local.
Audition = nil
pcall(function()
    local mod = require("jimmie_audition")
    mod.init({
        log = log,
        chat = djui_chat_message_create,
        play = play_clip,
        load_sound = function(name)
            local ok, snd = pcall(VOICE.performanceScope.load, name)
            if ok then return snd end
            return nil
        end,
    })
    Audition = mod
end)
if Audition == nil then log("[audition] module unavailable") end

local function say(cat, volume, gap)
    if VOICE ~= nil then
        if VOICE.ready ~= true then
            pcall(VOICE.init, nil, play_clip, audio_pos, now, log, load_category)
        end
        if VOICE.say(cat, volume or 1.0) then
            lastBark = now()
            return true
        end
        return false
    end
    local t = now()
    if t - lastBark < BARK_GAP then return false end
    local snd = pick(cat)
    if snd == nil then return false end
    lastBark = t
    return play_clip(snd, volume or 1.0)
end

local function say_any(cats, volume, gap)
    for _, cat in ipairs(cats) do
        if say(cat, volume, gap) then return true end
    end
    return false
end

-- ---------------------------------------------------------------------------
-- companion behavior (custom, does nothing on its own; HOOK_UPDATE moves it)
-- ---------------------------------------------------------------------------
local function jimmie_init(obj)
    obj.oFlags = OBJ_FLAG_UPDATE_GFX_POS_AND_ANGLE
    obj.oInteractType = 0
    obj.oCollisionDistance = 0
    obj.oGraphYOffset = 0
    obj.hookRender = 1 -- only this private body/board/brace behavior
    -- Approved v4 is 207 game units tall including the board at this scale.
    -- motion:regular. Mirrored front-to-back so he rides left foot forward.
    obj_scale_xyz(obj, 0.62, 0.62, -0.62)
    -- Local cosmetic companion pair. No player or network object ownership.
end

local function jimmie_loop(obj)
end

local id_bhvjimmie = nil
local E_MODEL_jimmie = nil

local function register_behavior()
    id_bhvjimmie = hook_behavior(nil, OBJ_LIST_DEFAULT, false,
        protect('bhv_init', jimmie_init), protect('bhv_loop', jimmie_loop), 'bhvJimmieOriginalStock')
    local function load_skin(skin)
        local names={raglan='jimmie_orig_rg_geo',vest='jimmie_orig_vest_geo',tee='jimmie_orig_tee_geo'}
        local body=smlua_model_util_get_id(names[skin] or names.raglan)
        local board=smlua_model_util_get_id('jimmie_orig_board_geo')
        if not body or body<=0 or body==E_MODEL_ERROR_MODEL or not board or board<=0 or board==E_MODEL_ERROR_MODEL then
            log('original stock actors unavailable; companion disabled');E_MODEL_jimmie=nil;return false
        end
        E_MODEL_jimmie=body;originalBoardModel=board;originalSkin=skin
        CLIPS={};for key in pairs(OriginalBank.clips) do CLIPS[key]={body} end
        if jimmie then obj_set_model_extended(jimmie,body) end
        originalController:reset();return true
    end
    _G.reload_skin=function(prefix)
        local map={jimmie3rg='raglan',jimmie3='vest',jimmie3nv='tee'}
        return load_skin(map[prefix] or prefix)
    end
    load_skin(originalSkin)
    poseFrame=1;poseTimer=0;activeClip='idle'
end

-- ---------------------------------------------------------------------------
-- spawn / despawn
-- ---------------------------------------------------------------------------
local function hide_jimmie()
    if jimmie ~= nil then
        jimmie.oPosY = -10000
        if originalBoard then originalBoard.oPosY=-10000 end
    end
end

local function despawn_jimmie(preserveBrace)
    if VOICE and VOICE.skateMemory then VOICE.skateMemory.clear() end
    railPresentation:clear()
    if not preserveBrace then originalOutcomes:reset(tostring(originalScene)) end
    dying=false;dyingUntil=0;deathSpin=0
    PHYS=nil;PHYS_AIR=false;PHYS_PUSHING=false;TRICK_PENDING=nil
    if originalCrashHost and not preserveBrace then
        originalCrashHost:reset('pair-removed',jimmie~=nil and originalBoard~=nil and jimmie.activeFlags~=0 and originalBoard.activeFlags~=0)
    end
    if originalBrace then pcall(obj_mark_for_deletion,originalBrace);originalBrace=nil end
    originalController:reset()
    if originalBoard then pcall(obj_mark_for_deletion,originalBoard);originalBoard=nil end
    if rejoinHost then rejoinHost:invalidate() end
    if recoveryController then recoveryController:retire() end
    if jimmie ~= nil then
        local ok = pcall(obj_mark_for_deletion, jimmie)
        if not ok then hide_jimmie() end
        jimmie = nil
    end
end

local function spawn_jimmie()
    if not enabled or now()<jimmieDeadUntil then return end
    if jimmie and originalBoard and jimmie.activeFlags~=0 and originalBoard.activeFlags~=0 then return end
    if jimmie or originalBoard then despawn_jimmie() end
    local m = gMarioStates[0]
    if m == nil or m.marioObj == nil or id_bhvjimmie == nil or E_MODEL_jimmie == nil then
        return
    end
    local placement=companionSpawn:select(m)
    if not placement then return end -- retry after native arrival, never force an unchecked point
    local ok, obj = pcall(spawn_non_sync_object, id_bhvjimmie, E_MODEL_jimmie,
        placement.x, placement.y, placement.z,
        function(o)
            o.oInteractType = 0
            o.oInteractStatus = 0
            o.oCollisionDistance = 0
            o.oOpacity = 255
            o.oFlags = OBJ_FLAG_UPDATE_GFX_POS_AND_ANGLE
        end)
    if ok and obj ~= nil then
        jimmie = obj
        local boardOk,board=pcall(spawn_non_sync_object,id_bhvjimmie,originalBoardModel,obj.oPosX,obj.oPosY,obj.oPosZ,function(o) end)
        if not boardOk or not board then obj_mark_for_deletion(obj);jimmie=nil;log('board spawn failed');return end
        originalBoard=board;originalController:reset()
        originalOutcomes:recovered(tostring(originalScene),jimmie,clock_elapsed_f64())
        PHYS = nil
        WPT = nil
        WANDER = nil
        autonomyT = 0
        safeSpots,nextProbeAt,previousGrounded = {},0,nil
        if skateDirector then skateDirector:reset(contextState and contextState:scene(gNetworkPlayers and gNetworkPlayers[0]) or "spawn") end
        liveMode = manualMode or (skateDirector and "auto" or "follow")
        log("spawned companion")
        if VOICE ~= nil then
            local np=gNetworkPlayers and gNetworkPlayers[0]
            local castleArrival=(pendingLevelGreeting or not greeted) and np and
                np.currLevelNum==(LEVEL_CASTLE or 6) and np.currAreaIndex==1
            if castleArrival then
                VOICE.setContext("castle_interior")
                if not (JIMMIE_ROUTE16 and JIMMIE_ROUTE16.ownsCastle()) then VOICE.post("castle_enter",{ttl=4,priority=65}) end
            elseif deathCount > 0 and now() - lastDeath < 12 then
                VOICE.post("respawn", { ttl = 6 })
            elseif pendingLevelGreeting then
                if not (JIMMIE_ROUTE16 and JIMMIE_ROUTE16.awaitingGreeting()) then
                    VOICE.post("level_enter", { ttl = 4 })
                end
            elseif not greeted then
                VOICE.post("greet", { ttl = 4 })
            end
        end
        greeted = true
        pendingLevelGreeting = false
    else
        log("spawn failed: " .. tostring(obj))
    end
end

-- ---------------------------------------------------------------------------
-- death / respawn
-- ---------------------------------------------------------------------------
-- Inserted in main's local scope. No parallel movement owner or Mario writes.
local function original_pair_valid()
    return jimmie~=nil and originalBoard~=nil and jimmie.activeFlags~=0 and originalBoard.activeFlags~=0
end
local function remove_original_brace()
    if originalBrace then pcall(obj_mark_for_deletion,originalBrace);originalBrace=nil end
end
local function update_original_brace()
    local remaining=originalOutcomes:remaining(tostring(originalScene),jimmie,clock_elapsed_f64())
    if not original_pair_valid() or remaining<=0 then remove_original_brace();return end
    if not originalBraceModel then return end
    if not originalBrace then
        local ok,o=pcall(spawn_non_sync_object,id_bhvjimmie,originalBraceModel,jimmie.oPosX,jimmie.oPosY,jimmie.oPosZ,function(o) end)
        if not ok or not o then return end
        originalBrace=o
    end
    local ok,why=OriginalBrace.apply(_G,originalBrace,jimmie,remaining,function(accessory,body)
        return accessory==originalBrace and body==jimmie and original_pair_valid()
    end)
    if not ok then remove_original_brace();log('brace unavailable: '..tostring(why)) end
end
local function step_original_crash(paused)
    if not originalCrashHost then return false end
    local m=gMarioStates[0]
    local out=originalCrashHost:step({frame=get_global_timer(),scene=tostring(originalScene),enabled=enabled,
        paused=paused==true,ownerAlive=m~=nil and m.marioObj~=nil,objectsValid=original_pair_valid()})
-- Insert before `if out.retire then` inside step_original_crash. No other owner
-- may run between the proved ready snapshot and this atomic paired handback.
    if out.ready and not paused then
        local committed,why=originalCrashHost:commit_recovery({frame=get_global_timer(),scene=tostring(originalScene)},function(body,board,q)
            if not dying or not original_pair_valid() or body~=jimmie or board~=originalBoard or q.scene~=tostring(originalScene) then return false end
            local owner=gMarioStates[0]
            if not enabled or not owner or not owner.marioObj then return false end
            if q.heading~=0 and q.heading~=1 then return false end
            railPresentation:clear() -- discard any old raised-rail render publication
            local travelYaw=q.yaw+math.pi/2
            local rebuilt={x=q.x,y=q.y,z=q.z,vx=0,vy=0,vz=0,yaw=travelYaw,prevYaw=travelYaw,onGround=true,pushT=0,airT=0}
            originalController:reset()
            local posed=originalController:step({body=body,board=board,scene=originalScene,dt=0,inAir=false,pushing=false})
            if not posed then return false end
            -- Reset/rebind first, then restore the committed forward/reversed stance.
            originalController.heading=q.heading
            if q.heading==1 then
                posed=originalController:step({body=body,board=board,scene=originalScene,dt=0,inAir=false,pushing=false})
                if not posed then return false end
            end
            local gfxYaw=(math.floor(q.yaw*32768/math.pi+.5)+32768)%65536-32768
            for _,actor in ipairs({body,board}) do
                actor.oPosX,actor.oPosY,actor.oPosZ=q.x,q.y,q.z
                actor.oFaceAngleYaw,actor.oFaceAnglePitch,actor.oFaceAngleRoll=gfxYaw,0,0
                actor.oVelX,actor.oVelY,actor.oVelZ,actor.oForwardVel=0,0,0,0
                actor.oInteractType,actor.oCollisionDistance,actor.oGraphYOffset=0,0,0
                obj_set_gfx_pos(actor,q.x,q.y,q.z);obj_set_gfx_angle(actor,0,gfxYaw,0);obj_skip_interpolation(actor)
            end
            PHYS=rebuilt;PHYS_AIR=false;PHYS_PUSHING=false;TRICK_PENDING=nil
            activeClip,poseFrame,poseTimer='idle',1,0
            dying=false;dyingUntil=0;jimmieDeadUntil=0;deathSpin=0
            speechLastPhys,speechWasAir,speechFlight=rebuilt,false,nil
            previousGrounded,currentSkateIntent,currentSkateSensors=nil,nil,nil
            WPT,WANDER=nil,nil;avoidT,blockedT,detourT,autonomyT=0,0,0,0
            safeSpots,nextProbeAt={},0
            if rejoinHost then rejoinHost:invalidate() end
            if skateOpportunity then skateOpportunity:cancel('getup-complete',{frame=get_global_timer(),time=now()}) end
            opportunityMotion=nil
            -- Start the existing ten-second collar only after the paired pose and
            -- new PHYS are installed. A stale offer never starts this clock.
            if not originalOutcomes:recovered(tostring(originalScene),body,clock_elapsed_f64()) then error('recovery outcome not armed') end
            return true
        end)
        if committed then update_original_brace();log('[original-crash] recovered by getup');if VOICE.skateMemory then VOICE.skateMemory.gotUp() end;return true end
        -- Failed/partial handback is never retried. Existing pair retirement below
        -- clears any partial write and falls back to a fresh paired respawn.
        originalCrashHost:release(false) -- early stale offers must relinquish ownership immediately
        out.retire=true;out.reason=why or 'getup-commit-failed'
    end

    if out.retire then
        -- Never resume the entry velocity/root restored by renderer.release.
        -- Retire the complete cosmetic pair; existing bounded respawn starts fresh.
        dying=false;despawn_jimmie(true);PHYS=nil;PHYS_AIR=false;PHYS_PUSHING=false;TRICK_PENDING=nil
        jimmieDeadUntil=now()+RESPAWN_TIME
        speechLastPhys,speechWasAir,speechFlight=nil,false,nil
        log('[original-crash] retired reason='..tostring(out.reason))
        return true
    end
    if out.owned then
        originalController:step({body=jimmie,board=originalBoard,scene=originalScene,externalOwner=true,dt=0})
        update_original_brace()
        return true
    end
    return false
end
local function begin_original_crash()
    if not originalCrashHost or not original_pair_valid() then return end
    local p=PHYS or {}
    local ok,why=originalCrashHost:begin({kind='companion_crash',source='companion',
        pos={x=jimmie.oPosX,y=jimmie.oPosY,z=jimmie.oPosZ},
        velocity={x=(p.vx or 0)*30,y=(p.vy or 0)*30,z=(p.vz or 0)*30},
        yaw=(jimmie.oFaceAngleYaw or 0)*math.pi/32768,heading=originalController.heading or 0,frame=get_global_timer(),scene=tostring(originalScene),sequence=deathCount},jimmie,originalBoard)
    log('[original-crash] begin accepted='..tostring(ok)..' reason='..tostring(why))
    if ok then originalController:step({body=jimmie,board=originalBoard,scene=originalScene,externalOwner=true,dt=0}) end
    return ok
end

local function jimmie_dies(reason, speechEvent)
    if jimmie == nil or dying then return end
    originalOutcomes:crashed(tostring(originalScene))
    if skateOpportunity then skateOpportunity:cancel('companion-crash',{frame=get_global_timer(),time=now()}) end
    opportunityMotion=nil
    deathCount = deathCount + 1
    lastDeath = now()
    if contextState then contextState:note(speechEvent or ("death_" .. tostring(reason)),now()) end
    previousGrounded,currentSkateIntent=nil,nil
    if skateDirector then skateDirector:reset(contextState and contextState:scene(gNetworkPlayers and gNetworkPlayers[0]) or "death") end
    local cats = { "death_" .. tostring(reason), "death_generic",
        "real_holy_shit", "real_unbelievable", "real_no_no_no" }
    local voiced = false
    if VOICE ~= nil and VOICE.post ~= nil then
        voiced = VOICE.post(speechEvent or ("death_" .. tostring(reason)), { cats = cats, volume = 1.0, t = now() })
    end
    if not voiced then say_any(cats, 1.0) end
    dying = true
    dyingUntil = now() + 0.9
    local accepted=begin_original_crash()
    -- motion:fallhere. The staged fall only runs on perfectly flat floor. Anywhere else, fall and get up on the spot.
    JIMMIE_FALL=nil
    if not accepted and jimmie and originalBoard then
        local q=PHYS or {}
        JIMMIE_FALL={vx=q.vx or 0,vz=q.vz or 0,t=0,yaw=q.yaw}
        dyingUntil=now()+3.48
    end
    if VOICE.skateMemory then VOICE.skateMemory.crash(accepted or JIMMIE_FALL~=nil,speechEvent=="trick_bail") end
    deathSpin = 0
    jimmieDeadUntil = dyingUntil + RESPAWN_TIME
    nextDeath = now() + rand(DEATH_MIN, DEATH_MAX)
    subtitle = nil
end

-- ---------------------------------------------------------------------------
-- movement
-- ---------------------------------------------------------------------------
-- Legacy debug timing labels; original bank metadata owns runtime animation.
local CLIP_SECONDS = {
    idle = 32 / 30, pose = 24 / 30, push = 29 / 30,
    trick = 22 / 30, trick2 = 33 / 30, bail = 61 / 30,
}
local PUSH_SECONDS = 0.40 -- unchanged physical kick cadence, including recovery
local poseAnimation = {}

local function pose_index(elapsed, duration, count, looping)
    local phase = math.max(0, elapsed) / duration
    if looping then phase = (phase + 0.00000001) % 1 else phase = math.min(1, phase) end
    return math.min(count, math.floor(phase * count + 0.0000001) + 1)
end

local function flight_playback_seconds(native, dt)
    -- Predict only playback length. The movement integrator remains untouched.
    -- Its next n ticks cover n*vy - 2*n*(n+1), with gravity 4 units/tick.
    if opportunityMotion and not opportunityMotion.grind then return math.max(dt,math.min(native,(opportunityMotion.duration or native)-1/30)) end
    if PHYS == nil or type(find_floor_height) ~= "function" then return native end
    local ok, floor = pcall(find_floor_height, PHYS.x, PHYS.y + 30, PHYS.z)
    if not ok or type(floor) ~= "number" or floor <= -10000 then return native end
    local height = math.max(0, PHYS.y - floor)
    local v = (tonumber(PHYS.vy) or 0) - 2
    local ticks = (v + math.sqrt(v * v + 8 * height)) / 4
    return math.max(dt, math.min(native, ticks / 30))
end

-- motion:crashcause. Odds out of 1000 that a trick fails. Globals, because this file is at Lua's limit of local names.
-- motion:keepup. More than 450 units behind a moving Mario: no falls until he has caught up.
function jimmie_behind()
    local m=gMarioStates[0]
    if not (m and jimmie and jimmie.activeFlags~=0) or m.forwardVel<12 then return false end
    local dx,dz=m.pos.x-jimmie.oPosX,m.pos.z-jimmie.oPosZ
    return dx*dx+dz*dz>450*450
end
function jimmie_bail_odds(clip,kind,speed)
    if jimmie_behind() then return 0 end
    local q=OriginalBank and OriginalBank.clips[clip]
    local base=kind=='grind' and 40 or (q and q.odds) or (clip=='kickflip' or clip=='heelflip') and 70 or (clip=='bs_pop_shuvit' or clip=='fs_pop_shuvit') and 45 or 20
    return base+math.max(0,math.min(60,((tonumber(speed) or 0)-25)*2))
end
-- Total odds at touchdown, the part known at take-off, and the name of the biggest landing cause.
function jimmie_landing_odds(p,event,speed,planned)
    if jimmie_behind() then return 0,0,nil end
    local base=p.trickBase or jimmie_bail_odds(event.clip,event.kind,speed)
    local extra,why=0,nil
    if event.kind=='trick' and event.early and not p.doomed then extra,why=350,'landed-early' end
    local hard=math.max(0,math.min(500,(((p.airTop or p.y or 0)-(p.y or 0))-340)*2))
    if hard>extra then why='hard-landing' end
    local side=0
    if not planned and (tonumber(speed) or 0)>8 and p.yaw then
        local a=math.abs(((math.atan2(p.vx or 0,p.vz or 0)-p.yaw+math.pi)%(2*math.pi))-math.pi)
        side=math.max(0,math.min(400,(math.min(a,math.pi-a)-.5)*600))
        if side>math.max(extra,hard) then why='sideways-landing' end
    end
    return math.floor(math.min(950,base+extra+hard+side)),base,why
end
local function update_pose_animation(dt)
    if not enabled or not jimmie or not originalBoard then return end
    for _,field in ipairs({'oPosX','oPosY','oPosZ','oFaceAngleYaw','oFaceAnglePitch','oFaceAngleRoll','oOpacity'}) do originalBoard[field]=jimmie[field] end
    local p=PHYS or {}
    -- Manuals: planned when he leaves the ground, started the frame he lands, held for about a second.
    if p.manual then
        p.manual.t=p.manual.t+dt
        if p.manual.t>p.manual.dur or not p.onGround or p.windup or dying or (opportunityMotion and opportunityMotion.phase=='windup') then p.manual=nil end
    elseif p.manualPlan and p.onGround and PHYS then
        p.manual={clip=p.manualPlan,t=0,dur=.8+math.random()*.8};p.manualPlan=nil
    end
    local ok,out=originalController:step({body=jimmie,board=originalBoard,dt=dt,scene=originalScene,
        trickTakeoff=(p.vy or 0)>0 and PHYS_AIR==true and p.onGround==false,
        windup=(opportunityMotion and opportunityMotion.phase=='windup' and opportunityMotion.windup) or (p.windup and p.onGround and math.max(0,p.windup.t-1)/6) or nil,popped=p.popped==true,
        inAir=PHYS_AIR==true and p.onGround==false,railContact=opportunityMotion and (opportunityMotion.grind==true or opportunityMotion.phase=='grind'),airTime=p.airT,pushing=PHYS_PUSHING==true,pushTime=p.pushT,
        manualClip=p.manual and p.manual.clip or nil,noSpin=opportunityMotion~=nil and opportunityMotion.kind=='rail',doomed=p.doomed==true,speed=jimmieSpeed,flightDuration=flight_playback_seconds(.95,1/30),dying=dying,bailDuration=JIMMIE_FALL and 2.03 or .9,getup=JIMMIE_FALL and JIMMIE_FALL.getup or nil,
        debugClip=POSE_TEST and DEBUG_CLIP or nil,requestedTrick=requestedOriginalTrick,
        balanceClip=opportunityMotion and (opportunityMotion.grind or opportunityMotion.phase=='grind') and opportunityMotion.balanceClip or nil})
    if ok and type(out)=='table' then
        activeClip=out.clip;poseFrame=out.frame+1;poseTimer=out.phase*OriginalBank.clips[out.clip].duration
        if p.fakie and p.onGround and not out.completedTrick then
            -- Rolling backwards after a 180: hold it, then pivot back round over a few frames.
            p.fakie.hold=p.fakie.hold-1
            if p.fakie.hold<=0 then
                p.fakie.yaw=p.fakie.yaw-math.max(-.35,math.min(.35,p.fakie.yaw))
                if math.abs(p.fakie.yaw)<.01 then p.fakie=nil end
            end
        end
        if out.journey and PHYS and not p.onGround then
            -- Roll once when he leaves the ground. A hop onto a rail is judged when he comes off it.
            p.airTop=math.max(p.airTop or p.y,p.y)
            if not p.trickRoll then
                p.trickRoll=math.random(1,1000)
                -- Still rolling backwards from a 180: this one is a fakie trick, and he stays backwards until it lands.
                if p.fakie then p.fakie.hold=math.max(p.fakie.hold,45);p.fakieTrick=true else p.fakieTrick=nil end
                local manuals=OriginalBank.manualList
                p.manualPlan=manuals and #manuals>0 and not p.fakie and not (opportunityMotion and opportunityMotion.kind=='rail') and math.random()<.3 and manuals[math.random(#manuals)] or nil
            end
            local key=out.journey..tostring(out.clip)
            if p.trickKey~=key then
                p.trickKey=key;p.trickBase=jimmie_bail_odds(out.clip,out.journey,jimmieSpeed)
                p.doomed=p.trickRoll<=p.trickBase and not (out.journey=='trick' and opportunityMotion and opportunityMotion.kind=='rail')
            end
        end
        if out.completedTrick and not dying then
            local odds,base,why=jimmie_landing_odds(p,out.completedTrick,jimmieSpeed,opportunityMotion~=nil)
            local fail,result=originalOutcomes:complete(out.completedTrick,tostring(originalScene),{roll=p.trickRoll,count=odds})
            if type(result)=='table' then
                -- The trick's real name, for speech ("kickflip", "360 flip"); a grind is just "grind" for now.
                local named=OriginalBank.clips[result.clip]
                local ground=out.completedTrick.grind and OriginalBank.clips[out.completedTrick.grind]
                local gname=ground and ground.name or 'grind'
                if result.kind=='grind' then
                    -- A flip on the way onto the rail is named with it: "kickflip to 5-0 grind".
                    local lead=named and named.name and named.name~='ollie' and result.clip~=out.completedTrick.grind and (named.name..' to ') or ''
                    result.trick=lead..gname
                    local outq=out.completedTrick.out and OriginalBank.clips[out.completedTrick.out]
                    if outq and outq.name and outq.name~='ollie' then result.trick=result.trick..' to '..outq.name..' out' end
                else result.trick=(named and named.name) or tostring(result.clip) end
                if named and named.spin then p.manual=nil end
                if p.fakieTrick and result.kind=='trick' then
                    local swapped=result.trick:gsub('frontside','@'):gsub('backside','frontside'):gsub('@','backside')
                    result.trick='fakie '..swapped
                end
                p.fakieTrick=nil
                if p.manual and p.manual.t==0 and not fail and OriginalBank.clips[p.manual.clip] then result.trick=result.trick..' to '..OriginalBank.clips[p.manual.clip].name end
                -- How many tricks he has landed in a row with less than three seconds between them.
                p.line=fail and 0 or ((p.lineT and now()-p.lineT<3) and (p.line or 0)+1 or 1);p.lineT=now();result.line=p.line
                local cause=not fail and 'none' or (result.roll>base and why) or (result.kind=='grind' and 'off-the-rail' or 'under-rotated')
                log('[trick-outcome] id='..result.id..' kind='..result.kind..' roll='..result.roll..'/1000 crash='..tostring(fail)..' chance='..tostring(result.chance)..' cause='..tostring(cause)..' clip='..tostring(result.clip)..' trick='..tostring(result.trick)..' line='..tostring(result.line))
            end
            p.trickRoll,p.trickKey,p.trickBase,p.doomed,p.airTop=nil,nil,nil,nil,nil
            if VOICE.skateMemory then VOICE.skateMemory.outcome(out.completedTrick,result) end
            if fail then jimmie_dies('board','trick_bail')
            elseif type(result)=='table' and result.kind=='trick' and PHYS and OriginalBank.clips[result.clip] and OriginalBank.clips[result.clip].spin then
                -- The clip ended turned half way; from this frame the whole model carries that half turn instead.
                local already=p.fakie and p.fakie.yaw or 0
                if math.abs(already)>.01 then p.fakie=nil else p.fakie={yaw=math.pi*OriginalBank.clips[result.clip].spin,hold=math.random()<.5 and 75 or 20} end
                jimmie.oFaceAngleYaw=(jimmie.oFaceAngleYaw+32768)%65536;originalBoard.oFaceAngleYaw=jimmie.oFaceAngleYaw
            end
        end
    end
end

-- Wheels roll along the deck (+local X) and resist motion across the axle.
local function skate_rolling_velocity(vx, vz, yaw)
    local forwardX, forwardZ = math.sin(yaw), math.cos(yaw)
    local along = (vx * forwardX + vz * forwardZ) * 0.988
    local across = (vx * forwardZ - vz * forwardX) * 0.20
    return along * forwardX + across * forwardZ,
           along * forwardZ - across * forwardX
end

local function skate_model_angles(heading, slope, turn)
    -- SM64 mtxf_rotate_zxy_and_translate maps +X to (cos(yaw),0,-sin(yaw)).
    -- Subtract a quarter turn so the deck nose follows (sin(heading),cos(heading)).
    if PHYS and PHYS.fakie then heading = heading + PHYS.fakie.yaw end
    local yaw = (math.floor(heading * 32768 / math.pi) - 16384) % 65536
    -- With a local-X deck, pitch banks around its length; roll lifts its nose.
    local bank = math.floor(math.max(-1800, math.min(1800, turn * -24000)))
    if PHYS and PHYS.fakie and math.abs(PHYS.fakie.yaw) > math.pi / 2 then bank = -bank end
    local incline = math.floor(math.max(-700, math.min(700, slope * 1600)))
    return yaw, bank, incline
end

local function has_native_bail() return true end

local function step_recovery(dt,paused)
    if not recoveryController or not PHYS or not jimmie then return false end
    local m=gMarioStates[0]
    local scene=recoveryController.world.scene
    if type(recoveryController.world.api.scene)=="function" then
        local ok,value=pcall(recoveryController.world.api.scene)
        if ok then scene=value end
    end
    local out=recoveryController:step(jimmie,PHYS,m,{frame=get_global_timer(),now=now(),dt=dt,
        scene=scene,enabled=enabled,alive=not dying,paused=paused,
        manual=manualMode~=nil and manualMode~="follow",assistActive=false,
        traversalNeeded=(currentSkateSensors and not currentSkateSensors.forwardSafe) or m.pos.y-PHYS.y>42})
    skateTraceMotionFrame=get_global_timer()
    if out.duplicate then return true end
    if recoveryController:apply(out,PHYS,jimmie) then
        recoveryChoiceFloor=contextState and contextState.seq or recoveryChoiceFloor
        TRICK_PENDING=nil
        PHYS_PUSHING,PHYS_AIR=out.source=="formation" and out.pushing==true,false
        jimmieSpeed=(out.source=="assist" or out.source=="formation") and math.sqrt(PHYS.vx^2+PHYS.vz^2) or 0
        speechLastPhys,speechWasAir,speechFlight=PHYS,false,nil
        previousGrounded,currentSkateIntent,currentSkateSensors=nil,nil,nil
        if out.started or out.completed then
            planningMenus={}
            safeSpots,nextProbeAt,farSince={},0,nil
            if skateDirector then skateDirector:reset(contextState and contextState:scene(gNetworkPlayers and gNetworkPlayers[0]) or "recovery") end
        end
        if out.completed and contextState then contextState:note("catch_up",now()) end
        return true
    end
    return false
end

-- No trick, landing or movement owner is created by this one-frame placement.
-- One-shot cosmetic relocation after a fresh, measured original-idle proof.
-- This does not create a second ordinary movement owner or alter Mario.
local function try_rejoin(dt)
 local host=rejoinHost
 if not host then return false end
 local m,p,o,b=gMarioStates[0],PHYS,jimmie,originalBoard
 if not m or not p or not o or not b then host:pause();return false end
 local marioObject=m.marioObj;local brace=originalBrace
 local before={x=p.x,y=p.y,z=p.z,vx=p.vx,vy=p.vy,vz=p.vz,onGround=p.onGround,yaw=p.yaw,pushT=p.pushT,airT=p.airT}
 local target=currentSkateIntent
 local gap=math.sqrt((m.pos.x-p.x)^2+(m.pos.z-p.z)^2)
 local blocked=(currentSkateSensors and currentSkateSensors.forwardSafe==false) or (tonumber(blockedT) or 0)>.25
 local wants=target and target.active and target.targetX and target.targetZ and (target.targetX-p.x)^2+(target.targetZ-p.z)^2>80*80 or false
 wants=wants or (blocked and gap>=220)
 local stable=type(m.floorHeight)=='number' and m.vel.y==0 and math.abs(m.pos.y-m.floorHeight)<=2
 local offer,why=host:step(dt,{object=o,idleModel=E_MODEL_jimmie,board=b,boardModel=originalBoardModel,brace=brace,yaw=p.yaw,
  skater={x=p.x,y=p.y,z=p.z},mario={x=m.pos.x,y=m.pos.y,z=m.pos.z},enabled=enabled,paused=skateTraceAllowed~=true,dead=dying,
  manual=(manualMode~=nil and manualMode~='follow') or liveMode=='wait' or liveMode=='hold' or POSE_TEST==true,
  grounded=p.onGround,vy=p.vy,marioStable=stable,wantsMove=wants,blocked=blocked})
 if why~=host.lastReason and ((host.attempts or 0)>0 or (host.policy.stallAge or 0)>1.5 or (host.policy.blockedAge or 0)>1.5 or (host.policy.heightAge or 0)>1) then
  log('[terrain-rejoin] decision='..tostring(why)..' gap='..math.floor(gap));host.lastReason=why
 end
 if not offer then return false end
 local function eligible()
  if host~=rejoinHost or not original_pair_valid() or jimmie~=o or originalBoard~=b or originalBrace~=brace or PHYS~=p or not enabled or dying then return false end
  if gMarioStates[0]~=m or m.marioObj~=marioObject or not marioObject then return false end
  for k,v in pairs(before) do if p[k]~=v then return false end end
  return type(m.floorHeight)=='number' and m.vel.y==0 and math.abs(m.pos.y-m.floorHeight)<=2 and (manualMode==nil or manualMode=='follow') and liveMode~='wait' and liveMode~='hold' and not POSE_TEST
   and (not Personality or Personality.gameplay(m)) and (type(is_game_paused)~='function' or not is_game_paused())
 end
 if not eligible() or not host:canCommit(offer,o,E_MODEL_jimmie) then host:resolve(offer,false);return false end
 local q=offer.proof.position;local yaw=skate_model_angles(offer.yaw,0,0)
 local newPhys={x=q.x,y=q.y,z=q.z,vx=0,vy=0,vz=0,yaw=offer.yaw,prevYaw=offer.yaw,onGround=true,pushT=0,airT=0}
 local committed,err=pcall(function()
  originalController:reset()
  local ok=originalController:step({body=o,board=b,scene=originalScene,dt=0,inAir=false,pushing=false})
  if not ok or not eligible() or not host:canCommit(offer,o,E_MODEL_jimmie) then error('paired-idle-or-final-proof-failed') end
  -- The proved pose is already installed. No callback between this check and root writes.
  PHYS=newPhys;PHYS_PUSHING=false;PHYS_AIR=false;TRICK_PENDING=nil
  for _,actor in ipairs({o,b}) do
   actor.oPosX,actor.oPosY,actor.oPosZ=q.x,q.y,q.z
   actor.oFaceAngleYaw,actor.oFaceAnglePitch,actor.oFaceAngleRoll=yaw,0,0
   actor.oVelX,actor.oVelY,actor.oVelZ,actor.oForwardVel=0,0,0,0
   actor.oInteractType,actor.oCollisionDistance,actor.oGraphYOffset=0,0,0
   obj_set_gfx_pos(actor,q.x,q.y,q.z);obj_set_gfx_angle(actor,0,yaw,0);obj_skip_interpolation(actor)
  end
  activeClip,poseFrame,poseTimer='idle',1,0
  speechLastPhys,speechWasAir,speechFlight=newPhys,false,nil
  previousGrounded,currentSkateIntent,currentSkateSensors,lastSkateState=nil,nil,nil,nil
  safeSpots,nextProbeAt,farSince={},0,nil;marioTrail,trailSerial,trailProgress={},0,0
  WPT,WANDER=nil,nil;avoidT,blockedT,detourT,autonomyT,wanderWait=0,0,0,0,0
  slopeVal,jimmieSpeed,prevVelY=0,0,0;farAway,onBoard=false,false;planningMenus={}
  recoveryChoiceFloor=contextState and contextState.seq or recoveryChoiceFloor
  if skateOpportunity then skateOpportunity:cancel('paired-rejoin',{frame=get_global_timer(),time=now()}) end
  opportunityMotion=nil
  if skateDirector then skateDirector:reset(contextState and contextState:scene(gNetworkPlayers[0]) or 'rejoin') end
  if VOICE then
   VOICE.trickSetup=nil
   local flights={trick_attempt=true,trick_ollie=true,trick_kickflip=true,trick_bail=true}
   for i=#VOICE.queue,1,-1 do if flights[VOICE.queue[i].event] then table.remove(VOICE.queue,i) end end
   if VOICE.preference and flights[VOICE.preference.event] then VOICE.preference=nil end
  end
  update_original_brace()
  if originalBrace then obj_skip_interpolation(originalBrace) end
 end)
 host:resolve(offer,true) -- after a possible write, never retry the same placement
 rejoinTraceResult={frame=get_global_timer(),source='rejoin',mode=committed and 'placed' or 'partial',reason=offer.request.reason,owned=false,commit=committed or nil,stamp={frame=offer.proof.stamp.frame}}
 skateTraceMotionFrame=rejoinTraceResult.frame
 if committed then
  if contextState then pcall(contextState.note,contextState,'catch_up',now()) end
  log(string.format('[terrain-rejoin] placed reason=%s x=%.2f y=%.2f z=%.2f',offer.request.reason,q.x,q.y,q.z))
 else
  log('[terrain-rejoin] partial; retiring pair: '..tostring(err));despawn_jimmie(true);jimmieDeadUntil=now()+RESPAWN_TIME;rejoinHost=nil
 end
 return true
end

local function update_movement(dt)
    local m = gMarioStates[0]
    if m == nil or m.marioObj == nil then return end
    if jimmie == nil then
        if now() >= jimmieDeadUntil then spawn_jimmie() end
        return
    end

    jimmie.oCollisionDistance = 0
    jimmie.oInteractType = 0

    if dying then
        if has_native_bail() then
            -- The original authored bail contains the fall. Keep its root visible;
            -- the old fake spin/sink would rotate them twice and bury them.
            jimmie.oFaceAnglePitch = 0
            jimmie.oFaceAngleRoll = 0
        else
            deathSpin = deathSpin + dt * 14
            jimmie.oFaceAnglePitch = math.floor(math.sin(deathSpin * 1.7) * 0x7000)
            jimmie.oFaceAngleRoll = math.floor(math.cos(deathSpin * 1.1) * 0x5000)
            jimmie.oPosY = jimmie.oPosY - dt * 260
        end
        local f=JIMMIE_FALL
        if f and originalBoard then
            f.t=f.t+dt
            if f.t<2.03 then
                -- Slide on along the floor and slow down; stop at a wall, a ledge or a step.
                local nx,nz=jimmie.oPosX+f.vx,jimmie.oPosZ+f.vz
                local fy=find_floor_height(nx,jimmie.oPosY+40,nz)
                if (f.vx~=0 or f.vz~=0) and fy>-10000 and math.abs(fy-jimmie.oPosY)<=40 and (not Personality or Personality.wallClear(nx,fy,nz)) then
                    jimmie.oPosX,jimmie.oPosY,jimmie.oPosZ=nx,fy,nz
                else f.vx,f.vz=0,0 end
                f.vx,f.vz=f.vx*.86,f.vz*.86
            elseif f.t>=2.38 then f.getup=math.min(1,(f.t-2.38)/0.6) end
            if f.getup and f.getup>=1 then
                local yaw=f.yaw or 0
                PHYS={x=jimmie.oPosX,y=jimmie.oPosY,z=jimmie.oPosZ,vx=0,vy=0,vz=0,yaw=yaw,prevYaw=yaw,onGround=true,pushT=0,airT=0}
                PHYS_AIR=false;PHYS_PUSHING=false;TRICK_PENDING=nil
                JIMMIE_FALL=nil;dying=false;dyingUntil=0;jimmieDeadUntil=0;deathSpin=0
                originalController:reset()
                originalOutcomes:recovered(tostring(originalScene),jimmie,clock_elapsed_f64())
                log('[original-crash] recovered by simple getup')
                if VOICE.skateMemory then VOICE.skateMemory.gotUp() end
            end
            return
        end
        if now() >= dyingUntil then
            dying = false
            despawn_jimmie(true) -- terrain-declined crashes retain pending post-recovery collar
            PHYS=nil;PHYS_AIR=false;PHYS_PUSHING=false;TRICK_PENDING=nil
            speechLastPhys,speechWasAir,speechFlight=nil,false,nil
        end
        return
    end

    if PHYS == nil then
        PHYS = {
            x = jimmie.oPosX, y = jimmie.oPosY, z = jimmie.oPosZ,
            vx = 0, vy = 0, vz = 0,
            yaw = (m.faceAngle.y or 0) * math.pi / 32768,
            onGround = true, pushT = 0, airT = 0,
        }
    end
    local p = PHYS
    if TRICK_PENDING == true and p.onGround then
        TRICK_PENDING = nil
        if not p.windup then p.windup = {t = 0, vy = 46, variant = 1 - (tonumber(trickVariant) or 0)} end
    end

    -- Behavior chooses a checked goal; the existing integrator owns all motion.
    if skateDirector and Personality then
        local scene = contextState and contextState:scene(gNetworkPlayers and gNetworkPlayers[0]) or "scene"
        local marioGround=Personality.floor(m.pos.x,m.pos.y,m.pos.z)
        local lastTrail=marioTrail[#marioTrail]
        if marioGround and (lastTrail==nil or (lastTrail.x-m.pos.x)^2+(lastTrail.z-m.pos.z)^2>=90*90) then
            trailSerial=trailSerial+1
            marioTrail[#marioTrail+1]={x=m.pos.x,y=marioGround,z=m.pos.z,seq=trailSerial}
            if #marioTrail>80 then table.remove(marioTrail,1) end
        end
        for _,node in ipairs(marioTrail) do
            if node.seq>trailProgress and (node.x-p.x)^2+(node.z-p.z)^2<90*90 then trailProgress=node.seq end
        end
        if now() >= nextProbeAt then
            safeSpots=Personality.spots(p,m,marioTrail,trailProgress)
            local moving=math.sqrt(m.vel.x*m.vel.x+m.vel.z*m.vel.z)>=12
            nextProbeAt=now()+(moving and 0.10 or 0.30)
        end
        local target=skateDirector.target
        local targetSafe
        if target then targetSafe=Personality.path(p,target.x,target.y,target.z) end
        currentSkateSensors=Personality.sensors(p,m,{scene=scene,enabled=enabled,dead=dying,
            manual=manualMode,blocked=(tonumber(blockedT) or 0)>0.25,
            inWater=VOICE and VOICE.hasContext("water"),onLava=VOICE and VOICE.hasContext("lava"),
            justLanded=previousGrounded==false and p.onGround==true,spots=safeSpots,targetSafe=targetSafe})
        previousGrounded=p.onGround
        currentSkateIntent=skateDirector:step(dt,currentSkateSensors)
        if currentSkateIntent.state ~= lastSkateState then
            lastSkateState=currentSkateIntent.state
            log("[skate] state=" .. tostring(lastSkateState) .. " reason=" .. tostring(currentSkateIntent.reason))
        end
        if currentSkateIntent.event and currentSkateIntent.event~="trick_attempt" and contextState then contextState:note(currentSkateIntent.event,now()) end
        if currentSkateIntent.trick and p.onGround and currentSkateSensors.forwardSafe and currentSkateSensors.landingSafe then
            if not p.windup then p.windup={t=0,vy=currentSkateIntent.jumpVelocity or 40,variant=currentSkateIntent.trickVariant or 0} end
        end
    end
    -- Wind-up: crouch on the ground for 6 frames, then leave. Other hops (ledges, steps) are unchanged.
    if p.windup then
        if not p.onGround then p.windup=nil
        else
            p.windup.t=p.windup.t+1
            if p.windup.t>6 then
                p.vy=p.windup.vy; p.onGround=false; p.airT=0; p.popped=true
                trickVariant=p.windup.variant; p.windup=nil
            end
        end
    end

    local mYaw = (m.faceAngle.y or 0) * math.pi / 32768
    local fx, fz = math.sin(mYaw), math.cos(mYaw)

    -- track how fast Mario is moving (for autonomy decisions)
    prevMarioX = tonumber(prevMarioX) or m.pos.x
    prevMarioZ = tonumber(prevMarioZ) or m.pos.z
    local mdx, mdz = m.pos.x - prevMarioX, m.pos.z - prevMarioZ
    marioSpeed = math.sqrt(mdx * mdx + mdz * mdz) * 30.0
    prevMarioX, prevMarioZ = m.pos.x, m.pos.z
    local marioDist = math.sqrt((m.pos.x - p.x) * (m.pos.x - p.x) + (m.pos.z - p.z) * (m.pos.z - p.z))

    if skateDirector == nil then
    -- autonomy: when Mario stays still and Jimmie is nearby, he goes off to skate
    autonomyT = tonumber(autonomyT) or 0
    if marioSpeed < 10 and liveMode ~= "wait" and liveMode ~= "hold" then
        local keen = math.max(0.15, math.min(1.0, 1.0 - marioDist / 700.0))
        autonomyT = autonomyT + dt
        if autonomyT > 2.0 and math.random() < 0.03 * keen then
            autonomyT = 0
            liveMode = "free"
            WANDER = nil
        end
    else
        autonomyT = 0
    end
    if liveMode == "free" and marioSpeed > 22 and marioDist > 240 then
        liveMode = "follow"
        WANDER = nil
    end

    end

    local tx, tz
    if liveMode == "wait" or liveMode == "hold" then
        tx = liveHoldX or p.x
        tz = liveHoldZ or p.z
    elseif liveMode == "free" then
        if WANDER == nil then
            local r = 120 + math.random() * 160
            if marioDist > 420 then
                -- soft pull: aim closer to Mario the further he has drifted
                r = 60 + math.random() * 110
            end
            local base = math.atan2(p.x - m.pos.x, p.z - m.pos.z)
            local a = base + (math.random() - 0.5) * 1.4
            WANDER = { m.pos.x + math.sin(a) * r, m.pos.z + math.cos(a) * r }
            wanderWait = 0
        end
        tx, tz = WANDER[1], WANDER[2]
        local wd = math.sqrt((tx - p.x) * (tx - p.x) + (tz - p.z) * (tz - p.z))
        if wd < 60 then
            wanderWait = (tonumber(wanderWait) or 0) + dt
            if wanderWait > 1.3 + math.random() * 1.6 then
                WANDER = nil
            end
        end
    elseif liveMode == "orbit" or liveMode == "board" then
        orbitA = (orbitA or 0) + dt * 1.4
        tx = m.pos.x + math.cos(orbitA) * 300
        tz = m.pos.z + math.sin(orbitA) * 300
    elseif liveMode == "away" then
        tx = m.pos.x + fx * 900
        tz = m.pos.z + fz * 900
    else
        -- longer leash: further ahead and further to the side
        tx = m.pos.x + fx * 220 + fz * 120
        tz = m.pos.z + fz * 220 - fx * 120
    end
    -- waypoint route: if a detour node is active, steer to it instead
    if WPT ~= nil then
        local wd = math.sqrt((WPT[1] - p.x) * (WPT[1] - p.x) + (WPT[2] - p.z) * (WPT[2] - p.z))
        if wd < 80 then
            WPT = nil
        else
            tx, tz = WPT[1], WPT[2]
        end
    end
    if currentSkateIntent and currentSkateIntent.active then
        tx,tz=currentSkateIntent.targetX or p.x,currentSkateIntent.targetZ or p.z
    end
    local dx, dz = tx - p.x, tz - p.z
    local dist = math.sqrt(dx * dx + dz * dz)
    local maxSpeed = 0
    if liveMode == "wait" or liveMode == "hold" then
        maxSpeed = 0
    elseif liveMode == "free" then
        maxSpeed = 16 + math.min(18, dist * 0.10)
    elseif liveMode == "away" then
        maxSpeed = 54
    else
        -- soft attraction: speed rises continuously with distance, no bands
        maxSpeed = math.max(0, math.min(64, (dist - 60) * 0.32))
    end
    if currentSkateIntent and currentSkateIntent.active then
        maxSpeed=math.min(currentSkateIntent.catchUp and 96 or 58,currentSkateIntent.speed or 0)
        if currentSkateIntent.brake or (p.onGround and currentSkateSensors and not currentSkateSensors.forwardSafe) then maxSpeed=0 end
    end
    local desiredSpeed = math.min(maxSpeed, dist * ((currentSkateIntent and currentSkateIntent.catchUp) and 1.2 or 0.8))
    local invd = 1.0 / (dist + 0.001)
    local ndx, ndz = dx * invd, dz * invd

    -- obstacle avoidance with commitment (avoids left/right oscillation)
    avoidT = tonumber(avoidT) or 0
    blockedT = tonumber(blockedT) or 0
    detourT = tonumber(detourT) or 0
    if detourT > 0 then
        local lx, lz = -ndz, ndx
        ndx, ndz = lx * (detourSign or 1), lz * (detourSign or 1)
        detourT = detourT - dt
    end
    if avoidT > 0 then
        local lx, lz = -ndz, ndx
        local ax, az = ndx + lx * (avoidSign or 1) * 0.9, ndz + lz * (avoidSign or 1) * 0.9
        local al = math.sqrt(ax * ax + az * az) + 0.001
        ndx, ndz = ax / al, az / al
        avoidT = avoidT - dt
    else
        local aheadH = find_floor_height(p.x + ndx * 60, p.y + 40, p.z + ndz * 60)
        if aheadH > p.y + 48 then
            local lx, lz = -ndz, ndx
            local lh = find_floor_height(p.x + (ndx * 0.4 + lx) * 80, p.y + 40, p.z + (ndz * 0.4 + lz) * 80)
            local rh = find_floor_height(p.x + (ndx * 0.4 - lx) * 80, p.y + 40, p.z + (ndz * 0.4 - lz) * 80)
            avoidSign = (lh <= rh) and 1 or -1
            avoidT = 0.55
            blockedT = blockedT + dt
            if blockedT > 0.6 and WPT == nil then
                WPT = { p.x + lx * avoidSign * 240, p.z + lz * avoidSign * 240 }
                blockedT = 0
            end
            local ax, az = ndx + lx * avoidSign * 1.1, ndz + lz * avoidSign * 1.1
            local al = math.sqrt(ax * ax + az * az) + 0.001
            ndx, ndz = ax / al, az / al
        else
            blockedT = 0
        end
    end

    -- ledge ahead: ollie off it or drop with momentum
    local edgeH = find_floor_height(p.x + ndx * 46, p.y + 40, p.z + ndz * 46)
    if p.onGround and edgeH < p.y - 70 and not (currentSkateIntent and currentSkateIntent.active) then
        p.vy = math.max(16, math.min(34, (tonumber(jimmieSpeed) or 0) * 0.5))
        p.onGround = false
        p.airT = 0
        trickVariant = 1 - (tonumber(trickVariant) or 0)
    end

    -- kick-push toward the target direction while below desired speed
    local spd = math.sqrt(p.vx * p.vx + p.vz * p.vz)
    local pushing = false
    -- motion:coast. After two pushes, roll for a while unless he has nearly stopped or is racing to catch up.
    local wantPush = p.onGround and spd < desiredSpeed - 1 and not p.windup and not p.fakie and not p.manual
    if (p.coastT or 0) > 0 then
        p.coastT = p.coastT - dt
        if spd > 6 and not (currentSkateIntent and currentSkateIntent.catchUp) then wantPush = false end
    end
    if not wantPush and (p.coastT or 0) <= 0 then p.pushN = 0 end
    if wantPush then
        p.pushT = p.pushT + dt
        if p.pushT > 0.40 then
            p.pushT = 0
            p.pushN = (p.pushN or 0) + 1
            if p.pushN >= 2 then p.pushN = 0; p.coastT = 0.9; wantPush = false end
        end
    end
    if wantPush then
        if p.pushT < 0.16 then
            pushing = true
            p.vx = p.vx + ndx * 3.0
            p.vz = p.vz + ndz * 3.0
        end
    else
        p.pushT = 0
    end

    -- carve toward the desired velocity (lateral grip)
    local dvx, dvz = ndx * desiredSpeed - p.vx, ndz * desiredSpeed - p.vz
    local dlen = math.sqrt(dvx * dvx + dvz * dvz)
    if dlen > 0.001 and not (not p.onGround and currentSkateIntent and currentSkateIntent.preserveMomentum) then
        local amax = (p.onGround and 2.2 or 0.9)
        local k = math.min(1.0, amax / dlen)
        p.vx = p.vx + dvx * k
        p.vz = p.vz + dvz * k
    end

    -- board faces its velocity; when slow, face the target
    local vel = math.sqrt(p.vx * p.vx + p.vz * p.vz)
    local wantYaw
    if vel > 1.5 then
        wantYaw = math.atan2(p.vx, p.vz)
    else
        wantYaw = math.atan2(dx, dz)
    end
    -- carve: never snap, limit angular speed (rad/s)
    local dyaw = (wantYaw - p.yaw + math.pi * 3) % (math.pi * 2) - math.pi
    local maxYawRate = 2.4 * dt
    dyaw = math.max(-maxYawRate, math.min(maxYawRate, dyaw))
    p.yaw = p.yaw + dyaw
    local prevYaw = p.prevYaw or p.yaw
    local turn = (p.yaw - prevYaw + math.pi * 3) % (math.pi * 2) - math.pi
    p.prevYaw = p.yaw

    -- Ground wheel traction: keep rolling momentum, remove sideways slip.
    if p.onGround then
        p.vx, p.vz = skate_rolling_velocity(p.vx, p.vz, p.yaw)
    else
        p.vx = p.vx * 0.998
        p.vz = p.vz * 0.998
    end

    if p.onGround then
        local ah = find_floor_height(p.x + math.sin(p.yaw) * 24, p.y + 40, p.z + math.cos(p.yaw) * 24)
        local dh = ah - p.y
        local slope = math.max(-1.0, math.min(1.0, dh / 24))
        p.vx = p.vx + math.sin(p.yaw) * (-slope) * 0.55
        p.vz = p.vz + math.cos(p.yaw) * (-slope) * 0.55
        slopeVal = math.max(-0.35, math.min(0.35, slope))
    end

    spd = math.sqrt(p.vx * p.vx + p.vz * p.vz)
    local cap = currentSkateIntent and currentSkateIntent.catchUp and 100 or 66
    if spd > cap then
        p.vx = p.vx * (cap / spd)
        p.vz = p.vz * (cap / spd)
    end

    if skateDirector == nil and p.onGround and spd > 18 and math.random() < (liveMode == "free" and 0.012 or 0.0025) then
        p.vy = 40
        p.onGround = false
    end

    if p.onGround then
        p.airT = 0
        p.y = find_floor_height(p.x, p.y + 30, p.z)
    else
        p.airT = (tonumber(p.airT) or 0) + dt
        p.vy = p.vy - 4.0
        p.y = p.y + p.vy
    end

    local nx = p.x + p.vx
    local nz = p.z + p.vz

    if p.onGround then
        p.airT = 0
        local hereH = find_floor_height(p.x, p.y + 30, p.z)
        local stepH = find_floor_height(nx, p.y + 55, nz)
        if stepH > hereH + 42 and stepH > p.y + 38 then
            local stepUp = stepH - p.y
            if stepUp <= 150 and spd > 8 and (not (currentSkateIntent and currentSkateIntent.active) or
                (currentSkateSensors and currentSkateSensors.forwardSafe and currentSkateSensors.landingSafe)) then
                p.vy = math.min(62, math.sqrt(2 * 4.0 * stepUp) + 8)
                p.onGround = false
                p.airT = 0
                trickVariant = 1 - (tonumber(trickVariant) or 0)
                p.vx = p.vx * 0.75
                p.vz = p.vz * 0.75
            else
                p.vx = 0
                p.vz = 0
            end
        end
    end
    if currentSkateIntent and currentSkateIntent.active and Personality then
        local nextFloor=p.y
        if p.onGround then nextFloor=Personality.floor(nx,p.y,nz) end
        if (p.onGround and nextFloor==nil) or not Personality.wallClear(nx,nextFloor or p.y,nz) then
            nx,nz,p.vx,p.vz=p.x,p.z,0,0
        end
    end
    p.x = nx
    p.z = nz

    local floorY = find_floor_height(p.x, p.y + 30, p.z)
    if p.y <= floorY then
        if not p.onGround and p.vy < -68 then
            p.y = floorY
            PHYS = nil
            jimmie_dies("fall")
            return
        end
        p.y = floorY
        p.vy = 0
        p.onGround = true
        p.popped = nil
    end
    if p.y < -2000 then
        PHYS = nil
        p.x = m.pos.x
        p.z = m.pos.z
        p.y = m.pos.y + 40
    end

    jimmie.oPosX = p.x
    jimmie.oPosY = p.y
    jimmie.oPosZ = p.z
    -- Orient the deck lengthwise, with slope and banking on its actual axes.
    p.lean = (p.lean or 0) * 0.7 + (p.onGround and turn * math.min(1, spd / 20) or 0) * 0.3
    jimmie.oFaceAngleYaw, jimmie.oFaceAnglePitch, jimmie.oFaceAngleRoll =
        skate_model_angles(p.yaw, slopeVal or 0, p.lean)

    jimmieSpeed = spd
    if p.onGround and spd > 10 and (now() - (lastRoll or 0)) > 0.38 then
        lastRoll = now()
        local roll = load_category("skate_roll")
        if roll ~= nil and roll[1] ~= nil then
            pcall(audio_sample_play, roll[1], audio_pos(), 0.20)
        end
    end
    PHYS_PUSHING = pushing
    PHYS_AIR = not p.onGround
end


-- One bounded owner only during a proved local hop/grind. Never controls Mario.
local function step_skate_opportunity()
    opportunityMotion=nil
    if not skateOpportunity then return false end
    local m,p,o=gMarioStates[0],PHYS,jimmie
    local np=gNetworkPlayers and gNetworkPlayers[0]
    if not m or not p or not o or not Personality then return false end
    local scene=contextState and contextState:scene(np) or "scene"
    local sensors=Personality.sensors(p,m,{scene=scene,enabled=enabled,dead=dying,manual=manualMode})
    local players={}
    for i=0,(MAX_PLAYERS or 1)-1 do
        local n,u=gNetworkPlayers and gNetworkPlayers[i],gMarioStates and gMarioStates[i]
        if u and n and (i==0 or n.connected) and n.currLevelNum==np.currLevelNum and n.currAreaIndex==np.currAreaIndex then
            players[#players+1]={x=u.pos.x,y=u.pos.y,z=u.pos.z,vx=u.vel.x,vz=u.vel.z}
        end
    end
    local terrain=type(smlua_collision_util_get_current_terrain_collision)=="function" and smlua_collision_util_get_current_terrain_collision() or nil
    local ctx={scene=scene,frame=get_global_timer(),time=now(),instance=o,phys=p,area=m.area,terrain=terrain,
        player={x=m.pos.x,y=m.pos.y,z=m.pos.z,vx=m.vel.x,vz=m.vel.z},players=players,
        playerInstance=m.marioObj,playerGrounded=sensors.marioGrounded,playerRising=sensors.marioRising,
        enabled=enabled,dead=dying,paused=not sensors or sensors.paused,
        manual=manualMode~=nil and manualMode~="follow",water=VOICE and (VOICE.hasContext("water") or VOICE.hasContext("lava"))}
    local ok,out=pcall(function() return skateOpportunity.world:transaction(function() return skateOpportunity:step(p,ctx) end) end)
    if skateOpportunity.world.lastBudget and skateOpportunity.world.lastBudget.reason then skateOpportunity:cancel(skateOpportunity.world.lastBudget.reason,ctx) end
    if not ok then
        log("[skate-opportunity] disabled after error: "..tostring(out));skateOpportunity=nil;return false
    end
    for _,event in ipairs(skateOpportunity:drain()) do
        log("[skate-opportunity] "..Personality.json(event))
    end
    if not out then return false end
    local q,v=out.position,out.velocity
    p.x,p.y,p.z=q.x,q.y,q.z;p.vx,p.vy,p.vz=v.x,v.y,v.z;p.onGround=out.onGround
    p.pushT=0;p.airT=out.airTime
    local wantYaw=out.heading or (math.abs(v.x)+math.abs(v.z)>.01 and math.atan2(v.x,v.z)) or p.yaw
    if out.grind or out.phase=='grind' then p.yaw=wantYaw
    else
        local dyaw=(wantYaw-p.yaw+math.pi*3)%(math.pi*2)-math.pi
        p.yaw=p.yaw+math.max(-.3,math.min(.3,dyaw))
    end
    p.prevYaw=p.yaw
    p.popped=(out.popped==true and not p.onGround) or nil;p.windup=nil
    o.oPosX,o.oPosY,o.oPosZ=p.x,p.y,p.z
    o.oCollisionDistance,o.oInteractType=0,0
    o.oFaceAngleYaw,o.oFaceAnglePitch,o.oFaceAngleRoll=skate_model_angles(p.yaw,0,0)
    if out.grind then
        local incline=math.max(-math.pi/3,math.min(math.pi/3,tonumber(out.incline) or 0))
        o.oFaceAngleRoll=math.floor(incline*32768/math.pi)
    end
    jimmieSpeed=math.sqrt(v.x*v.x+v.z*v.z)
    trickVariant=out.variant;PHYS_PUSHING=false;PHYS_AIR=not p.onGround;TRICK_PENDING=nil
    opportunityMotion=out
    if rejoinHost then rejoinHost:pause() end
    if skateDirector then skateDirector:reset(scene) end
    currentSkateIntent=nil;safeSpots={};nextProbeAt=0;WPT=nil
    return true
end

local function event_bark(event, cats, volume, fact)
    if contextState then contextState:note(event,now()) end
    if VOICE ~= nil and VOICE.post ~= nil then
        if fact=="trick_landed" then return false end
        local grant=fact and VOICE.performanceWitness and VOICE.performanceWitness(event,fact)
        return VOICE.post(event, { cats = cats, volume = volume, t = now(), performanceGrant=grant })
    end
    return say_any(cats or { event }, volume)
end

local function update_chatter()
    if recoveryController and recoveryController:quiet(now()) then return end
    local m = gMarioStates[0]
    if m == nil or m.marioObj == nil then return end
    if jimmie == nil then return end
    local dist = dist3(m.pos, { x = jimmie.oPosX, y = jimmie.oPosY, z = jimmie.oPosZ })
    local t = now()
    local marioMoving = VOICE and VOICE.marioMoving and VOICE.marioMoving() or false

    if marioMoving and dist > 900 then
        if t - lastChaseBark > CHASE_GAP then
            lastChaseBark = t
            -- One catch-up event: the generic far line must not consume the
            -- channel immediately before the actual skateboard complaint.
            if PHYS ~= nil and PHYS.onGround and (tonumber(jimmieSpeed) or 0) > 1 and t - lastBoardBark > 12 then
                lastBoardBark = t
                event_bark("chase_board", nil, 1.0)
            else
                event_bark("chase_far", nil, 1.0)
            end
        end
    elseif marioMoving and dist > 420 then
        if t - lastChaseBark > CHASE_GAP + 2 then
            lastChaseBark = t
            event_bark("chase_mid", { "chase_mid", "real_come_on" }, 0.8)
        end
    elseif marioMoving and dist > 230 then
        if t - lastChaseBark > CHASE_GAP * 2 then
            lastChaseBark = t
            event_bark("chase_near", { "chase_near", "real_come_on" }, 0.7)
        end
    end

    if marioMoving and dist > 900 then farAway = true end
    if farAway and dist < 180 then
        farAway = false
        event_bark("reunion", { "reunion", "real_come_on" }, 1.0)
    end

    -- idle chatter when Mario stands still
    local idle = math.abs(m.vel.x) < 2 and math.abs(m.vel.z) < 2
    if idle and t - lastIdleBark > IDLE_GAP and t - lastBark > 4.0 then
        lastIdleBark = t
        event_bark("idle_long", { "idle", "roast", "catchphrase", "real_whats_happening", "real_swa_swa", "real_gub_gub", "real_boing_boing", "real_carrier", "real_unreal", "real_honey_oil" }, 0.8, "mario_stationary")
    end

    -- Normal movement has its own bounded personality opportunity.
    if VOICE and VOICE.activePlay and t >= nextActiveChatter then
        nextActiveChatter=t+14+math.random()*4
        VOICE.post("active_play", {volume=0.85,ttl=1.5})
    end

    -- Follow reliability takes priority over timer-driven slapstick.
    -- Real Mario deaths, physical falls and the explicit /jimmie poof command
    -- retain their existing handlers. Time passing alone is not a death event.
end

-- ---------------------------------------------------------------------------
-- jumps -> tricks / bails
-- ---------------------------------------------------------------------------
-- React to the companion's actual completed flight, not a random outcome
-- guessed when Mario jumps. The movement system still owns every trick/bail.
local function update_jumps()
    -- Commands and geometry proposals are not event evidence. These flags are
    -- emitted only on later observed matching motion/contact by the owner.
    local motion=recoveryController and recoveryController.last
    if motion and motion.source=="assist" then
        if motion.takeoff then event_bark("trick_attempt",nil,0.9,"trick_takeoff") end
        if motion.landed then
            if motion.reason=="grind-landing-observed" then
                if contextState then contextState:note("grind_landing",now()) end
            else event_bark("trick_ollie",nil,1.0,"trick_landed") end
        end
        if contextState and motion.grindContactObserved then contextState:note("grind_contact",now()) end
        if contextState and motion.edgeRideObserved then contextState:note("edge_ride",now()) end
    end
    local p = PHYS
    if p ~= nil and p == speechLastPhys and not dying and not recovery_suppressed() then
        if not p.onGround then
            if not speechWasAir then
                speechFlight = originalController.output and originalController.output.clip or nil
                event_bark("trick_attempt", nil, 0.9, "trick_takeoff")
            end
            speechWasAir = true
        elseif speechWasAir then
            local ev = (speechFlight=='kickflip' or speechFlight=='trick2') and 'trick_kickflip' or speechFlight=='trick' and 'trick_ollie' or nil
            if ev then event_bark(ev, nil, 1.0, "trick_landed") end -- do not falsely name a heel/shuv as a kickflip
            speechWasAir = false
            speechFlight = nil
        end
    else
        speechWasAir = false
        speechFlight = nil
    end
    speechLastPhys = p
    local m = gMarioStates[0]
    if m == nil then return end
    local stars = tonumber(m.numStars)
    if stars ~= nil then
        if speechStars ~= nil and stars > speechStars and not (JIMMIE_ROUTE16 and JIMMIE_ROUTE16.ownsStar()) then event_bark("star", nil, 1.0)
            if Audition ~= nil then Audition.on_star() end
        end
        speechStars = stars
    end
    local health = tonumber(m.health)
    if health ~= nil then
        if speechHealth ~= nil and health > 255 and health < speechHealth then
            event_bark("mario_hurt", nil, 1.0)
        end
        speechHealth = health
    end
end

-- ---------------------------------------------------------------------------
-- vest lottery
-- ---------------------------------------------------------------------------
local function roll_vest()
    vest = math.random() < 0.5
    log("vest roll: " .. tostring(vest))
end

-- ---------------------------------------------------------------------------
-- hooks
-- ---------------------------------------------------------------------------
-- The native title has an initialization-only Mario, not active gameplay.
-- Identify its private inert warp marker, never a level number owned by another mod.
local titleWasActive, gameplayReady = false, false
-- Native host/sync starts before the intro's inert marker exists.
-- Only a real gameplay level-init admits the cosmetic companion.
local function in_jimmie_title()
    if not gameplayReady then return true end
    if type(area_get_warp_node) ~= "function" then return false end
    local marker = area_get_warp_node(0xEE)
    return marker ~= nil and marker.node.destLevel == 16
        and marker.node.destArea == 7 and marker.node.destNode == 0xED
end

-- A certificate is published only after this tick's final pose/brace update.
-- The next native render consumes the SAME global timer value, before gfx matrices.
local function rail_presentation_context()
    local m=gMarioStates and gMarioStates[0]
    -- Pure render-time guards: Personality.gameplay increments an observation epoch.
    local paused=skateTraceAllowed~=true or in_jimmie_title() or not m or (tonumber(m.health) or 0x880)<=255
    for _,name in ipairs({"is_game_paused","djui_console_is_open"}) do
        local fn=_G[name]
        if type(fn)=="function" then local ok,value=pcall(fn);paused=paused or not ok or value==true end
    end
    if type(get_current_play_mode)=="function" then
        local ok,mode=pcall(get_current_play_mode);paused=paused or not ok or mode~=(PLAY_MODE_NORMAL or 0)
    end
    for _,name in ipairs({"ACT_READING_NPC_DIALOG","ACT_READING_SIGN","ACT_WAITING_FOR_DIALOG",
        "ACT_STAR_DANCE_EXIT","ACT_STAR_DANCE_NO_EXIT","ACT_INTRO_CUTSCENE"}) do
        paused=paused or (m and _G[name]~=nil and m.action==_G[name])
    end
    return {body=jimmie,board=originalBoard,brace=originalBrace,controller=originalController,
        motion=opportunityMotion,scene=originalScene,
        sceneKey=contextState and contextState:scene(gNetworkPlayers and gNetworkPlayers[0]) or "scene",
        frame=get_global_timer(),enabled=enabled and m~=nil and m.marioObj~=nil,
        paused=paused,dying=dying,
        externalOwner=originalController.external==true or (originalCrashHost and originalCrashHost.active==true)
            or recovery_suppressed() or (rejoinHost and rejoinHost.offer~=nil),players=gMarioStates}
end
local function render_rail_presentation(o)
    if o~=jimmie and o~=originalBoard and o~=originalBrace then return end
    railPresentation:render(o,rail_presentation_context())
end

local function on_level_init(typ, levelNum, areaIdx, nodeId, arg)
    gameplayReady = true
    companionSpawn:invalidate()
    originalScene=originalScene+1
    if Audition ~= nil and not JIMMIE_ROUTE16 then Audition.on_level(levelNum) end
    if contextState then contextState:reset() end
    planningMenus={}
    if mimicDirector then mimicDirector:reset(contextState and contextState:scene(gNetworkPlayers and gNetworkPlayers[0]) or "level",now()) end
    if hostDirector then hostDirector:reset(contextState and contextState:scene(gNetworkPlayers and gNetworkPlayers[0]) or "level") end
    marioTrail,trailSerial,trailProgress,farSince={},0,0,nil
    safeSpots,nextProbeAt,previousGrounded,currentSkateIntent,lastSkateState={},0,nil,nil,nil
    nextActiveChatter=now()+10
    if skateDirector then skateDirector:reset(contextState and contextState:scene(gNetworkPlayers and gNetworkPlayers[0]) or "level") end
    if VOICE ~= nil then
        VOICE.clearScene(true) -- only a genuine source Mamma Mia may bridge a scene transition.
    end
    despawn_jimmie()
    roll_vest()
    jimmieDeadUntil = now() + 1.0
    nextDeath = now() + rand(DEATH_MIN, DEATH_MAX)
    pendingLevelGreeting = true
    speechStars = nil
    speechHealth = nil
    speechLastPhys = nil
    speechWasAir = false
    speechFlight = nil
end

local function on_sync_valid()
    -- Sync may arrive while Mario is still leaving a painting. The regular
    -- gameplay update owns spawning after delay, scene and geometry checks.
    companionSpawn:invalidate()
end

local function on_death(m)
    if not enabled or m == nil or m.playerIndex ~= 0 or dying then return end
    -- One speech event owns this death: an occasional payout replaces the
    -- ordinary death bark, rather than playing over a second companion bark.
    jimmie_dies("generic", "death_mario")
end

local function spawn_graffiti()
    if GRAFFITI_MODEL == nil or graffitiSpawned then return end
    if now() < 8 then return end
    local m = gMarioStates[0]
    if m == nil or m.marioObj == nil then return end
    local yaw = (m.faceAngle.y or 0) * math.pi / 32768
    local dist = 650
    local side = 200
    local px = m.pos.x + math.sin(yaw) * dist + math.cos(yaw) * side
    local pz = m.pos.z + math.cos(yaw) * dist + math.sin(yaw) * side
    local obj = spawn_sync_object(id_bhvgraffiti, GRAFFITI_MODEL, px, m.pos.y + 40, pz, nil)
    log(string.format("mural spawn at %.1f,%.1f,%.1f (mario %.1f,%.1f,%.1f yaw=%d)",
        px, m.pos.y + 40, pz, m.pos.x, m.pos.y, m.pos.z, m.faceAngle.y or 0))
    if obj ~= nil then
        obj.oFaceAngleYaw = (m.faceAngle.y + 0x8000) % 0x10000
        graffitiSpawned = true
        log("graffiti mural spawned")
    end
end

local find_landmark

local LEVEL_LABELS = { [6]="Peach's Castle", [16]="Castle Grounds", [9]="Bob-omb Battlefield", [24]="Whomp's Fortress",
    [12]="Jolly Roger Bay", [5]="Cool Cool Mountain", [4]="Big Boo's Haunt", [7]="Hazy Maze Cave",
    [22]="Lethal Lava Land", [8]="Shifting Sand Land", [23]="Dire Dire Docks", [10]="Snowman's Land",
    [11]="Wet Dry World", [36]="Tall Tall Mountain", [13]="Tiny Huge Island", [14]="Tick Tock Clock", [15]="Rainbow Ride" }
-- Read-only save snapshots for the local route log; never a gameplay command.
local function route_progress_snapshot(s)
    local function integer(n,lo,hi) return type(n)=="number" and n==n and n%1==0 and n>=lo and n<=hi end
    if type(s)~="table" or type(s.observed)~="table" or s.observed.starMasks~=true
        or not integer(s.fileIndex,0,3) or type(s.saveBank)~="boolean"
        or not integer(s.secretMask,0,127) or type(s.starMasks)~="table" then return nil end
    local masks={}
    for i=1,24 do
        local value=s.starMasks[i]
        if not integer(value,0,127) then return nil end
        masks[i]=value
    end
    local profile=type(s.profile)=="table" and s.profile or {}
    local standard=s.useGlobalStarIds==false and s.disableActs==false and s.customLevel==false
        and profile.modsVerified==true
    return {v=1,file_index=s.fileIndex,backup_bank=s.saveBank,course_masks=masks,secret_mask=s.secretMask,standard=standard}
end

local function director_bridge(m,allowed)
    if not aiEnabled then return end
    if not contextState then return end
    local np=gNetworkPlayers and gNetworkPlayers[0] or {}
    local scene=contextState:scene(np)
    if PENDING_DIRECTOR then
        local payload=PENDING_DIRECTOR; PENDING_DIRECTOR=nil
        local valid,reason=contextState:validate(payload,scene,not allowed or not aiEnabled or recovery_suppressed() or (tonumber(payload.seq) or -1)<=recoveryChoiceFloor,manualMode~=nil)
        if valid then
            local acted=false
            if payload.intent~="none" and skateDirector then acted=skateDirector:bias(payload.intent,6) or acted end
            if payload.clip and VOICE and VOICE.preferChoice then
                local menu=planningMenus[payload.seq]
                if menu and menu.scene==scene and menu.clips[payload.clip] then
                    acted=VOICE.preferChoice(menu.event,payload.clip,{id=payload.id,ttl=12}) or acted
                end
            end
            if not acted then contextState.decision_status="rejected"; reason="no-current-opportunity" end
        end
        log("[director] id="..tostring(payload.id).." status="..contextState.decision_status.." reason="..tostring(reason))
    end
    if now()-contextState.lastEmit<0.95 then return end
    local contexts={}
    if VOICE then for k,v in pairs(VOICE.context) do if v then contexts[#contexts+1]=k end end end
    table.sort(contexts)
    local candidates={}
    local p=PHYS
    local distance=jimmie and dist3(m.pos,{x=jimmie.oPosX,y=jimmie.oPosY,z=jimmie.oPosZ}) or 9999
    local behavior=skateDirector and skateDirector.state or "follow"
    local planningEvent="active_play"
    local marioMoving=VOICE and VOICE.marioMoving and VOICE.marioMoving() or false
    if recovery_suppressed() then behavior="catch_up";planningEvent="active_play"
    elseif p and not p.onGround then planningEvent=(trickVariant or 0)==1 and "trick_kickflip" or "trick_ollie"
    elseif behavior=="approach" or behavior=="setup" or behavior=="roam" then planningEvent="trick_attempt"
    elseif marioMoving and distance>900 then planningEvent=(p and p.onGround and (jimmieSpeed or 0)>1 and now()-lastBoardBark>12) and "chase_board" or "chase_far"
    elseif marioMoving and distance>420 then planningEvent="chase_mid"
    elseif marioMoving and distance>230 then planningEvent="chase_near" end
    if allowed and aiEnabled and not recovery_suppressed() and VOICE and VOICE.planCandidates then candidates=VOICE.planCandidates(planningEvent) end
    local routeGoal,hostContext
    if hostDirector then routeGoal,hostContext=hostDirector:context() end
    local emitted=contextState:emit({scene=scene,level=np.currLevelNum or 0,level_name=LEVEL_LABELS[np.currLevelNum] or "SM64 course",
        area=np.currAreaIndex or 0,act=np.currActNum or 0,stars=m.numStars or 0,health=math.floor((m.health or 0)/256),
        mario_speed=math.sqrt(m.vel.x*m.vel.x+m.vel.z*m.vel.z),distance=distance,
        mode=VOICE and VOICE.mode or "silent",quiet=not allowed or not aiEnabled,paused=not allowed,manual=manualMode~=nil,
        grounded=p~=nil and p.onGround==true,behavior=behavior,
        episode=skateDirector and skateDirector.episode or 0,contexts=contexts,candidates=candidates,planning_event=planningEvent,route_goal=routeGoal,host=hostContext,
        route_progress=route_progress_snapshot(hostDirector and hostDirector.snapshot)},now(),print)
    if emitted then
        local offered={}
        for _,candidate in ipairs(candidates) do offered[candidate.clip]=true end
        planningMenus[contextState.seq]={scene=scene,event=planningEvent,clips=offered}
        planningMenus[contextState.seq-8]=nil
    end
end

local function update_host(m,allowed)
    if not hostDirector then return end
    local np=gNetworkPlayers and gNetworkPlayers[0] or {}
    local history={}
    if contextState then for _,event in ipairs(contextState.history) do
        history[#history+1]={kind=event.kind,age=math.max(0,now()-event.t)}
    end end
    hostDirector:update(1/30,m,np,{scene=contextState and contextState:scene(np) or "scene",
        enabled=enabled and routeEnabled and (RunMode == nil or RunMode.isSpeedrun()),
        allowed=allowed,dead=dying,
        manual=manualMode~=nil and manualMode~="follow",silent=VOICE and VOICE.mode=="silent",
        afk=VOICE and VOICE.afk,history=history})
end

-- motion:introscene. Jimmie's introduction: on a new file he arrives in the bridge scene in place of Lakitu.
-- The game's own scene is left exactly as it is (trigger, camera, text box, timing). Lakitu and his cloud are only
-- made invisible, and Jimmie is drawn around where Lakitu is: small, flitting in loops with twirls and sparkles,
-- growing as he flies in, then still in front of Mario for the text. When the text box closes he becomes the
-- normal companion on that spot. Globals, because this file is at Lua's limit of locals.
JIMMIE_INTRO={}
function jimmie_intro_lakitu()
    local o=obj_get_first_with_behavior_id(id_bhvCameraLakitu)
    while o do
        if o.oBehParams2ndByte~=0 and o.activeFlags~=0 then return o end      -- 0 is the camera Lakitu in the mirror room
        o=obj_get_next_with_same_behavior_id(o)
    end
    return nil
end
function jimmie_intro_hide(lak,delete)
    obj_set_model_extended(lak,E_MODEL_NONE)
    for _,id in ipairs({id_bhvCloud,id_bhvCloudPart}) do
        local c=obj_get_first_with_behavior_id(id)
        while c do
            local nxt=obj_get_next_with_same_behavior_id(c)
            if math.abs(c.oPosX-lak.oPosX)+math.abs(c.oPosY-lak.oPosY)+math.abs(c.oPosZ-lak.oPosZ)<900 then
                if delete then obj_mark_for_deletion(c) else obj_set_model_extended(c,E_MODEL_NONE) end
            end
            c=nxt
        end
    end
    if delete then obj_mark_for_deletion(lak) end
end
function jimmie_intro_sparkles(x,y,z,count,spread)
    for _=1,count do
        -- motion:sparklefx. Our own sparkle objects (same sparkle model) instead of the game's sparkle spawner, which
        -- draws from the game's shared random numbers every frame.
        if jimmie_fx_spawn then
            jimmie_fx_spawn(E_MODEL_SPARKLES_ANIMATION or E_MODEL_SPARKLES,x+(math.random()-.5)*spread,y+math.random()*spread,z+(math.random()-.5)*spread,
                {life=10,s0=.9,s1=.45,vy=1,frames=5})
        end
    end
end
function jimmie_intro_step(m)
    local s=JIMMIE_INTRO
    if s.done then return false end
    local lak=jimmie_intro_lakitu()
    if not lak then
        if s.seen then s.done=true end                                         -- the scene is over, or was never on this file
        return false
    end
    s.seen=true
    if lak.oAction==0 then
        -- Waiting for Mario to step on the bridge. If he gets past it without triggering the scene (the speedrun
        -- skip), there is no introduction: Jimmie is simply the companion from then on.
        if m.pos.z<-2150 then s.done=true;log('[jimmie-intro] phase=skipped frame='..tostring(get_global_timer()));return false end
        -- He cannot be created once the scene has frozen Mario, so he is created now and kept out of sight.
        if not (jimmie and originalBoard) then spawn_jimmie() end
        if jimmie and originalBoard then PHYS=nil;jimmie.oPosY=-10000;originalBoard.oPosY=-10000 end
        if not s.waiting then s.waiting=true;log('[jimmie-intro] phase=waiting frame='..tostring(get_global_timer())) end
        return true
    end
    jimmie_intro_hide(lak,false)
    if lak.oAction<2 then return true end
    if not (jimmie and originalBoard) then spawn_jimmie() end
    if not (jimmie and originalBoard) then return true end
    local x,y,z=lak.oPosX,lak.oPosY,lak.oPosZ
    local dx,dz=m.pos.x-x,m.pos.z-z
    local heading=math.atan2(dx,dz)+(JIMMIE_INTRO_TURN or math.pi/2)            -- he stands sideways on the board; turned so his face is toward Mario
    if lak.oCameraLakituFinishedDialog~=0 then
        -- The text box has closed and control is back. From here he is the ordinary companion: he drops to the
        -- ground from where he hovered. Lakitu and the cloud, already invisible, are removed.
        obj_scale_xyz(jimmie,.62,.62,-.62);obj_scale_xyz(originalBoard,.62,.62,-.62)
        PHYS={x=x,y=y,z=z,vx=0,vy=0,vz=0,yaw=heading,prevYaw=heading,onGround=false,pushT=0,airT=0}
        PHYS_AIR=false
        jimmie_intro_sparkles(x,y,z,14,170)
        if s.stick and s.stick.activeFlags~=0 then obj_mark_for_deletion(s.stick) end;s.stick=nil
        jimmie_intro_hide(lak,true)
        s.done=true;log('[jimmie-intro] phase=companion frame='..tostring(get_global_timer()))
        return false
    end
    if s.frame==get_global_timer() then return true end                          -- once per frame, whichever path called
    s.frame=get_global_timer();s.tick=(s.tick or 0)+1
    if not s.arrived then s.arrived=true;jimmie_intro_sparkles(x,y,z,10,200);log('[jimmie-intro] phase=arrive frame='..tostring(get_global_timer())) end
    if lak.oCameraLakituSpeed==0 and not s.talking then s.talking=true;s.twirl=14;log('[jimmie-intro] phase=talk frame='..tostring(get_global_timer())) end
    local far=math.sqrt(dx*dx+dz*dz+(m.pos.y-y)^2)
    local k=1-math.max(0,math.min(1,(far-500)/2500));k=k*k*(3-2*k)
    local size=.16+(.62-.16)*k                                                   -- a speck far away, full size by the time he stops
    -- Flitting: he darts in loops and bobs around the path Lakitu flies, less and less as that path slows, and is
    -- still by the time it stops. The path itself, and so the scene's length, is the game's own.
    local wild=math.max(0,math.min(1,lak.oCameraLakituSpeed/45));local t=s.tick
    local fx=wild*130*math.sin(t*.47)*math.cos(t*.13)
    local fy=wild*85*math.sin(t*.83+1.1)+ (1-wild)*6*math.sin(t*.21)            -- a gentle bob while he hovers and talks
    local fz=wild*130*math.cos(t*.39+.6)
    -- Twirls: a quick spin on his own axis every second and a half while darting, and one as he settles.
    local spin=0
    if wild>.15 and t%44<13 then spin=(t%44)/13*2*math.pi end
    if s.twirl and s.twirl>0 then spin=(1-s.twirl/14)*2*math.pi;s.twirl=s.twirl-1 end
    PHYS=nil;jimmieSpeed=10
    jimmie.oPosX,jimmie.oPosY,jimmie.oPosZ=x+fx,y+fy,z+fz
    jimmie.oFaceAngleYaw,jimmie.oFaceAnglePitch,jimmie.oFaceAngleRoll=skate_model_angles(heading+spin,0,0)
    local fc='swim'   -- motion:fairyswim. He swims through the air like a fairy; no camera stick.
    if OriginalBank.clips[fc] then
        -- Flying pose, off the board; the board waits out of sight until he joins Mario.
        originalController.bank:apply(jimmie,originalBoard,fc,(s.tick%24)/24,0);originalBoard.oPosY=-10000
    else update_pose_animation(1/30) end
    obj_scale_xyz(jimmie,size,size,-size);obj_scale_xyz(originalBoard,size,size,-size)
    jimmie_stick_place(s,jimmie.oPosX,jimmie.oPosY,jimmie.oPosZ,math.atan2(dx,dz),false,size)
    stop_sound(SOUND_AIR_LAKITU_FLY,lak.header.gfx.cameraToObject)
    if not s.talking then jimmie_intro_sparkles(x+fx,y+fy+60*size,z+fz,2,150*size)
    elseif t%9==0 then jimmie_intro_sparkles(x+fx,y+fy+90,z+fz,1,120) end
    return true
end
-- motion:mirrorroom. In the mirror room upstairs the game shows the camera man in the mirror, behind Mario's
-- reflection. That is Jimmie now: the Lakitu there and his cloud are made invisible and a second Jimmie on his board
-- is drawn where Lakitu is, looking the way Lakitu looks. Nothing about the room or the camera is changed.
JIMMIE_MIRROR={}
function jimmie_mirror_step()
    local s=JIMMIE_MIRROR
    local lak=obj_get_first_with_behavior_id(id_bhvCameraLakitu)
    while lak and not (lak.oBehParams2ndByte==0 and lak.activeFlags~=0) do lak=obj_get_next_with_same_behavior_id(lak) end
    if not lak then s.body=nil;s.board=nil;return end
    jimmie_intro_hide(lak,false)
    if not (s.body and s.board and s.body.activeFlags~=0 and s.board.activeFlags~=0) then
        if id_bhvjimmie==nil or E_MODEL_jimmie==nil or originalBoardModel==nil then return end
        local okA,body=pcall(spawn_non_sync_object,id_bhvjimmie,E_MODEL_jimmie,lak.oPosX,-10000,lak.oPosZ,function(o) end)
        local okB,board=pcall(spawn_non_sync_object,id_bhvjimmie,originalBoardModel,lak.oPosX,-10000,lak.oPosZ,function(o) end)
        if not (okA and okB and body and board) then return end
        s.body,s.board=body,board
        smlua_anim_util_set_animation(body,OriginalBank.clips.pose.body);smlua_anim_util_set_animation(board,OriginalBank.clips.pose.board)
        if not s.logged then s.logged=true;log('[jimmie-mirror] shown frame='..tostring(get_global_timer())) end
    end
    -- The game hides its Lakitu while the camera is outside the room; follow that.
    local hidden=(lak.header.gfx.node.flags & GRAPH_RENDER_INVISIBLE)~=0
    local face=lak.oFaceAngleYaw*math.pi/32768
    local yaw=skate_model_angles(face+math.pi/2,0,0)
    for _,o in ipairs({s.body,s.board}) do
        o.oPosX,o.oPosZ=lak.oPosX,lak.oPosZ
        o.oPosY=hidden and -10000 or (lak.oPosY-150)
        o.oFaceAngleYaw,o.oFaceAnglePitch,o.oFaceAngleRoll=yaw,0,0
        local a=o.header.gfx.animInfo;a.animFrame=0;a.animFrameAccelAssist=0;a.animAccel=65536
    end
end
-- motion:opening. The opening fly-in to the pipe (and the ending, which reuses the same flying camera man):
-- Lakitu is made invisible and Jimmie is drawn where he is, in his flying pose, with a sparkle trail. The cutscene
-- object keeps running exactly as before; nothing here moves it, the camera or Mario.
JIMMIE_OPENING={}
function jimmie_opening_step()
    local s=JIMMIE_OPENING
    local lak=obj_get_first_with_behavior_id(id_bhvBeginningLakitu)
    if not lak or lak.activeFlags==0 then
        if s.body then
            if s.body.activeFlags~=0 then obj_mark_for_deletion(s.body) end
            if s.board and s.board.activeFlags~=0 then obj_mark_for_deletion(s.board) end
            if s.stick and s.stick.activeFlags~=0 then obj_mark_for_deletion(s.stick) end;s.stick=nil
            s.body=nil;s.board=nil;log('[jimmie-opening] gone frame='..tostring(get_global_timer()))
        end
        return
    end
    jimmie_intro_hide(lak,false)
    if not (s.body and s.body.activeFlags~=0) then
        if id_bhvjimmie==nil or E_MODEL_jimmie==nil or originalBoardModel==nil or not OriginalBank.clips.fly_cam then return end
        local okA,body=pcall(spawn_non_sync_object,id_bhvjimmie,E_MODEL_jimmie,lak.oPosX,-10000,lak.oPosZ,function(o) end)
        local okB,board=pcall(spawn_non_sync_object,id_bhvjimmie,originalBoardModel,lak.oPosX,-10000,lak.oPosZ,function(o) end)
        if not (okA and okB and body and board) then return end
        s.body,s.board,s.tick=body,board,0
        smlua_anim_util_set_animation(body,OriginalBank.clips.swim.body);smlua_anim_util_set_animation(board,OriginalBank.clips.swim.board)
        log('[jimmie-opening] shown frame='..tostring(get_global_timer()))
    end
    s.tick=s.tick+1
    local hidden=(lak.header.gfx.node.flags & GRAPH_RENDER_INVISIBLE)~=0
    local o=s.body
    stop_sound(SOUND_AIR_LAKITU_FLY_HIGHPRIO,lak.header.gfx.cameraToObject)
    o.oPosX,o.oPosZ=lak.oPosX,lak.oPosZ
    o.oPosY=hidden and -10000 or (lak.oPosY-90+10*math.sin(s.tick*.3))
    local yaw=skate_model_angles(lak.oFaceAngleYaw*math.pi/32768+math.pi/2,0,0)
    o.oFaceAngleYaw,o.oFaceAnglePitch,o.oFaceAngleRoll=yaw,0,0
    local a=o.header.gfx.animInfo;local f=s.tick%24;a.animFrame=f;a.animFrameAccelAssist=f*65536;a.animAccel=65536
    s.board.oPosY=-10000
    -- The camera stick in his hand: a small model of our own, placed at his holding hand and pointing where he faces.
    if not (s.stick and s.stick.activeFlags~=0) then
        local id=nil   -- no camera stick
        if id and id~=E_MODEL_ERROR_MODEL then
            local ok,st=pcall(spawn_non_sync_object,id_bhvjimmie,id,o.oPosX,-10000,o.oPosZ,function(q) end)
            if ok and st then s.stick=st end
        end
    end
    if s.stick then
        local f=lak.oFaceAngleYaw*math.pi/32768;local fx,fz=math.sin(f),math.cos(f);local side=JIMMIE_STICK_SIDE or 24
        s.stick.oPosX=o.oPosX+fx*59+fz*side;s.stick.oPosZ=o.oPosZ+fz*59-fx*side
        s.stick.oPosY=hidden and -10000 or (o.oPosY+89)
        s.stick.oFaceAngleYaw,s.stick.oFaceAnglePitch,s.stick.oFaceAngleRoll=lak.oFaceAngleYaw,0,0
        obj_scale_xyz(s.stick,.62,.62,.62)
    end
    if not hidden and s.tick%2==0 then jimmie_intro_sparkles(o.oPosX,o.oPosY+40,o.oPosZ,1,110) end
end
-- motion:camicon. The camera man in the corner of the screen is Jimmie.
JIMMIE_CAM_ICON=get_texture_info('jimmie_cam_head')
if JIMMIE_CAM_ICON then texture_override_set('texture_hud_char_lakitu',JIMMIE_CAM_ICON) end
-- motion:camfix. Places the camera stick at a flying Jimmie's holding hand, pointing the way he faces.
function jimmie_stick_place(s,x,y,z,face,hidden,size)
    do return end   -- no camera stick
    if not (s.stick and s.stick.activeFlags~=0) then
        local id=smlua_model_util_get_id('jimmie_camstick_geo')
        if not id or id==E_MODEL_ERROR_MODEL then return end
        local ok,st=pcall(spawn_non_sync_object,id_bhvjimmie,id,x,-10000,z,function(q) end)
        if not (ok and st) then return end
        s.stick=st
    end
    local k=(size or .62)/.62;local fx,fz=math.sin(face),math.cos(face);local side=(JIMMIE_STICK_SIDE or 24)*k
    s.stick.oPosX=x+fx*59*k+fz*side;s.stick.oPosZ=z+fz*59*k-fx*side
    s.stick.oPosY=hidden and -10000 or (y+89*k)
    s.stick.oFaceAngleYaw,s.stick.oFaceAnglePitch,s.stick.oFaceAngleRoll=math.floor(face*32768/math.pi)%65536,0,0
    obj_scale_xyz(s.stick,size or .62,size or .62,size or .62)
end
-- motion:swim. Where the skating Jimmie has no ground to stand on, a second Jimmie is drawn beside Mario instead:
-- swimming while Mario is in deep water, flying (his camera-man pose) while Mario stands on a moving floor such as
-- the tilting Bowser arena or a raft. Looks only: no collision, never nearer than arm's length, moves nothing.
JIMMIE_SWIM={}
function jimmie_swim_step()
    local s=JIMMIE_SWIM;local m=gMarioStates[0]
    if not (m and m.marioObj) then return end
    if s.body and not (jimmie_is_mine(s.body) and jimmie_is_mine(s.board)) then jimmie_swim_forget() end
    local mx,my,mz=m.pos.x,m.pos.y,m.pos.z;local f=m.faceAngle.y*math.pi/32768
    local tx,tz=mx+math.sin(f)*130-math.cos(f)*190,mz+math.cos(f)*130+math.sin(f)*190
    -- Never beside Mario through a wall: try his other side, then behind him; otherwise stay out of sight.
    local shut=false
    if not jimmie_open(mx,my,mz,tx,my,tz) then
        local ax,az=mx+math.sin(f)*130+math.cos(f)*190,mz+math.cos(f)*130-math.sin(f)*190
        local bx,bz=mx-math.sin(f)*180,mz-math.cos(f)*180
        if jimmie_open(mx,my,mz,ax,my,az) then tx,tz=ax,az elseif jimmie_open(mx,my,mz,bx,my,bz) then tx,tz=bx,bz else shut=true end
    end
    local mode=nil
    if jimmie and jimmie.activeFlags~=0 then s.alone=0
    else
        s.alone=(s.alone or 0)+1
        if (m.action & ACT_FLAG_SWIMMING)~=0 or my<m.waterLevel-100 then mode='swim'
        elseif s.alone>45 and m.floor and m.floor.object~=nil and math.abs(my-m.floorHeight)<4 then mode='fly'
        elseif s.alone>45 and m.action==ACT_FLYING then mode='fly' end   -- motion:flywing. Mario flying with the Wing Cap
    end
    if obj_get_first_with_behavior_id(id_bhvBeginningLakitu) then mode=nil end
    if mode then s.hold=20;s.mode=mode else s.hold=(s.hold or 0)-1 end
    if s.hold<=0 then
        if s.body then
            if s.body.activeFlags~=0 then obj_mark_for_deletion(s.body) end
            if s.board and s.board.activeFlags~=0 then obj_mark_for_deletion(s.board) end
            s.body=nil;s.board=nil;s.clip=nil;s.leap=nil;s.out=nil;log('[jimmie-swim] out frame='..tostring(get_global_timer()))
        end
        return
    end
    mode=s.mode
    if not (s.body and s.body.activeFlags~=0) then
        if id_bhvjimmie==nil or E_MODEL_jimmie==nil or originalBoardModel==nil or not OriginalBank.clips.swim or not OriginalBank.clips.fly then return end
        local okA,body=pcall(spawn_non_sync_object,id_bhvjimmie,E_MODEL_jimmie,tx,-10000,tz,function(o) end)
        local okB,board=pcall(spawn_non_sync_object,id_bhvjimmie,originalBoardModel,tx,-10000,tz,function(o) end)
        if not (okA and okB and body and board) then return end
        s.body,s.board,s.tick,s.x,s.y,s.z,s.face,s.clip=body,board,0,tx,my+(mode=='fly' and 500 or 0),tz,f,nil
        log('[jimmie-swim] in mode='..mode..' frame='..tostring(get_global_timer()))
    end
    if s.clip~=mode then
        s.clip=mode
        -- motion:airswim. Beside Mario he swims through the air too; the flying pose stays for the camera-man scenes and his dives.
        smlua_anim_util_set_animation(s.body,OriginalBank.clips.swim.body);smlua_anim_util_set_animation(s.board,OriginalBank.clips.swim.board)
    end
    s.tick=s.tick+1
    local ty=my+(mode=='fly' and 70 or 0)
    if jimmie_leap_step(s,mode,tx,ty,tz) then return end
    local dx,dy,dz=tx-s.x,ty-s.y,tz-s.z;local d=math.sqrt(dx*dx+dz*dz)
    if d>2500 then s.x,s.y,s.z=tx,ty,tz;dx,dy,dz,d=0,0,0,0 end
    if not shut and not jimmie_open(mx,my,mz,s.x,my,s.z) then s.x,s.z=tx,tz;dx,dz,d=0,0,0 end   -- a wall came between them
    local step=mode=='fly' and math.min(95,d*.3) or math.min(26,d*.07);local nx,nz=s.x,s.z
    if d>1 then nx,nz=s.x+dx/d*step,s.z+dz/d*step end
    local ax,az=nx-mx,nz-mz;local ad=math.sqrt(ax*ax+az*az)
    if ad<170 and ad>1 then nx,nz=mx+ax/ad*170,mz+az/ad*170 end
    local rise=mode=='fly' and 70 or 14;s.y=s.y+math.max(-rise,math.min(rise,dy*(mode=='fly' and .3 or .08)))
    if mode=='swim' then
        -- stay in open water: under the surface, off the bottom, never into ground
        local water,floor=find_water_level(nx,nz),find_floor_height(nx,s.y+200,nz)
        if water and floor and floor<water-110 then s.x,s.z=nx,nz
        else water,floor=find_water_level(s.x,s.z),find_floor_height(s.x,s.y+200,s.z) end
        if water and s.y>water-45 then s.y=water-45 end
        if floor and s.y<floor+30 then s.y=floor+30 end
    else s.x,s.z=nx,nz end
    local turn=(f-s.face+math.pi)%(2*math.pi)-math.pi;s.face=s.face+turn*.08       -- he heads the way Mario is heading
    local o=s.body
    o.oPosX,o.oPosZ=s.x,s.z
    if mode=='swim' then o.oPosY=s.y-30+5*math.sin(s.tick*.13) else o.oPosY=s.y+10*math.sin(s.tick*.3) end
    -- motion:bubbles. The game's own bubble, from his mouth, about once a second while he swims.
    if mode=='swim' and not shut and s.tick%32==0 and id_bhvBubbleMaybe and E_MODEL_BUBBLE then
        -- motion:bubblefx. Our own bubble object instead of the game's bubble behaviour, which draws from the game's
        -- random numbers. Same model; it rises and is removed at the surface.
        local bw=find_water_level(s.x,s.z);local by=o.oPosY+70
        if jimmie_fx_spawn and bw and by<bw-30 then
            jimmie_fx_spawn(E_MODEL_BUBBLE,s.x+math.sin(s.face)*45,by,s.z+math.cos(s.face)*45,
                {life=math.max(4,math.min(40,math.floor((bw-by)/6))),s0=.5,s1=.9,vy=6,vx=(math.random()-.5)*1.5,vz=(math.random()-.5)*1.5})
        end
    end
    local yaw=skate_model_angles(s.face+math.pi/2,0,0)
    o.oFaceAngleYaw,o.oFaceAnglePitch,o.oFaceAngleRoll=yaw,0,0
    local a=o.header.gfx.animInfo;local fr=s.tick%24;a.animFrame=fr;a.animFrameAccelAssist=fr*65536;a.animAccel=65536
    s.board.oPosY=-10000
    if shut then o.oPosY=-10000 end
end
-- motion:leap. One Jimmie, not two: he dives from where he was skating into the water beside Mario, and leaps
-- from the water to the spot where he gets back on his board. Looks only.
function jimmie_leap_step(s,mode,tx,ty,tz)
    local L=s.leap
    if not L then
        if s.dive then L={x=s.dive.x,y=s.dive.y,z=s.dive.z,t=0,kind='in'};s.dive=nil
        elseif s.out then L={x=s.x,y=s.y,z=s.z,t=0,kind='out',ex=s.out.x,ey=s.out.y,ez=s.out.z}
        else return false end
        local ex,ez=L.ex or tx,L.ez or tz;local d=math.sqrt((ex-L.x)^2+(ez-L.z)^2)
        if L.kind=='in' then L.n=math.max(14,math.min(45,math.floor(d/40)));L.h=120+d*.12
        else L.n=math.max(10,math.min(18,math.floor(d/30)));L.h=110 end
        s.leap=L
        smlua_anim_util_set_animation(s.body,OriginalBank.clips.fly.body);smlua_anim_util_set_animation(s.board,OriginalBank.clips.fly.board)
        log('[jimmie-leap] '..L.kind..' frames='..tostring(L.n)..' frame='..tostring(get_global_timer()))
    end
    L.t=L.t+1;local u=L.t/L.n;local ex,ey,ez
    if L.kind=='in' then
        ex,ey,ez=tx,ty,tz;local w=find_water_level(tx,tz)
        if w and ey>w-45 then ey=w-45 end
    else ex,ey,ez=L.ex,L.ey,L.ez;s.hold=20 end
    local x,y,z=L.x+(ex-L.x)*u,L.y+(ey-L.y)*u+L.h*math.sin(math.pi*u),L.z+(ez-L.z)*u
    if (ex-L.x)^2+(ez-L.z)^2>1 then s.face=math.atan2(ex-L.x,ez-L.z) end
    local o=s.body
    o.oPosX,o.oPosY,o.oPosZ=x,y,z
    o.oFaceAngleYaw,o.oFaceAnglePitch,o.oFaceAngleRoll=skate_model_angles(s.face+math.pi/2,0,0),0,0
    local a=o.header.gfx.animInfo;local fr=s.tick%24;a.animFrame=fr;a.animFrameAccelAssist=fr*65536;a.animAccel=65536
    s.board.oPosY=-10000
    if L.t>=L.n then
        s.x,s.y,s.z=ex,ey,ez;s.leap=nil;s.clip=nil
        if L.kind=='out' then s.out=nil;s.hold=0 end
    end
    return true
end
-- motion:boardpull. When the skater comes back right after the swimming or flying Jimmie, he first stands for
-- 40 frames and pulls a toy-sized board out from behind his back, tosses it down, it pops to full size and he hops
-- on. When Mario has been swimming for two seconds the skater simply leaves (the swimming Jimmie takes over).
-- Looks only; he does not move while the clip plays.
JIMMIE_PULL={}
function jimmie_pull_size(t)
    local k={{0,.45},{.62,.45},{.70,1.2},{.78,1},{1,1}}                    -- same table as SIZE in swim/pull_motion.py
    for i=1,#k-1 do
        if t<=k[i+1][1] then return k[i][2]+(k[i+1][2]-k[i][2])*(t-k[i][1])/(k[i+1][1]-k[i][1]) end
    end
    return 1
end
function jimmie_pull_step()
    local s=JIMMIE_PULL
    if not (jimmie and originalBoard and jimmie.activeFlags~=0 and originalBoard.activeFlags~=0) then s.t=nil;s.wait=nil;s.wet=0;s.had=false;return false end
    if not s.had then
        s.had=true
        if JIMMIE_SWIM and JIMMIE_SWIM.body and JIMMIE_SWIM.body.activeFlags~=0 and OriginalBank.clips.board_pull then
            -- he is still in the water: wait, unseen, until he has leapt over to this spot
            s.wait=0;JIMMIE_SWIM.out={x=jimmie.oPosX,y=jimmie.oPosY,z=jimmie.oPosZ}
        end
    end
    local m=gMarioStates[0]
    if s.wait then
        s.wait=s.wait+1
        if JIMMIE_SWIM.out==nil or s.wait>30 then
            s.wait=nil;JIMMIE_SWIM.out=nil;JIMMIE_SWIM.hold=0;s.t=0
            log('[jimmie-pull] begin frame='..tostring(get_global_timer()))
        else
            PHYS=nil;jimmieSpeed=0
            originalController.bank:apply(jimmie,originalBoard,'board_pull',0,0)
            obj_scale_xyz(jimmie,.001,.001,-.001);obj_scale_xyz(originalBoard,.001,.001,-.001)
            return true
        end
    end
    if not s.t then
        if m and (m.action & ACT_FLAG_SWIMMING)~=0 then s.wet=(s.wet or 0)+1 else s.wet=0 end
        if s.wet>60 and not dying and not PHYS_AIR and opportunityMotion==nil then
            s.wet=0;JIMMIE_SWIM.dive={x=jimmie.oPosX,y=jimmie.oPosY,z=jimmie.oPosZ};despawn_jimmie();log('[jimmie-pull] dived frame='..tostring(get_global_timer()))
            return true
        end
        return false
    end
    s.t=s.t+1
    if s.t>40 then s.t=nil;log('[jimmie-pull] end frame='..tostring(get_global_timer()));return false end
    PHYS=nil;jimmieSpeed=0
    local t=(s.t-1)/39;local b=.62*jimmie_pull_size(t)
    originalController.bank:apply(jimmie,originalBoard,'board_pull',t,0)
    obj_scale_xyz(jimmie,.62,.62,-.62);obj_scale_xyz(originalBoard,b,b,-b)
    return true
end
-- motion:wallsafe. True when nothing solid lies between two points at Mario's chest height (sampled every 60 units).
function jimmie_open(ax,ay,az,bx,by,bz)
    local d=math.sqrt((bx-ax)^2+(bz-az)^2);local n=math.max(1,math.ceil(d/60))
    for i=1,n do
        local q={x=ax+(bx-ax)*i/n,y=ay+(by-ay)*i/n,z=az+(bz-az)*i/n}
        if resolve_and_return_wall_collisions(q,60,45)~=nil then return false end
        if JIMMIE_SWIM.mode~='fly' and find_floor_height(q.x,q.y+150,q.z)<-10000 then return false end
    end
    return true
end
-- motion:stalefix. When the level or area changes the game frees every object. The swimming / flying Jimmie must
-- drop its handles then, or it would move (and later delete) whatever object the game puts in the same slot next.
function jimmie_swim_forget()
    local s=JIMMIE_SWIM
    s.body=nil;s.board=nil;s.clip=nil;s.leap=nil;s.out=nil;s.dive=nil;s.hold=0;s.alone=0
    if JIMMIE_PULL then JIMMIE_PULL.wait=nil;JIMMIE_PULL.t=nil end
end
function jimmie_is_mine(o)
    if not o or o.activeFlags==0 then return false end
    local r=obj_has_behavior_id(o,id_bhvjimmie)
    return r==true or r==1
end
hook_event(HOOK_ON_WARP,jimmie_swim_forget)
if HOOK_ON_CLEAR_AREAS then hook_event(HOOK_ON_CLEAR_AREAS,jimmie_swim_forget) end
-- motion:react. He reacts to what Mario does, with his body only: a cheer for a triple jump, long jump, wall kick
-- or star; a wince when Mario is hurt, lands a big fall or dies. Played over his riding stance for 24 frames while
-- he keeps rolling; never during a trick, a grind, a fall or in the air. Nothing here moves him or Mario.
JIMMIE_REACT={cool={}}
function jimmie_react_step(m)
    local s=JIMMIE_REACT;local f=get_global_timer()
    if not m or not m.marioObj then return end
    -- what Mario just did
    local act=m.action;local cause,kind=nil,nil
    if act~=s.act then
        if act==ACT_TRIPLE_JUMP or act==ACT_SPECIAL_TRIPLE_JUMP or act==ACT_FLYING_TRIPLE_JUMP then cause,kind='triple_jump','cheer'
        elseif act==ACT_LONG_JUMP then cause,kind='long_jump','cheer'
        elseif act==ACT_WALL_KICK_AIR then cause,kind='wall_kick','cheer'
        elseif act==ACT_HARD_BACKWARD_GROUND_KB or act==ACT_HARD_FORWARD_GROUND_KB then cause,kind='big_fall','wince'
        elseif (act & ACT_GROUP_MASK)==ACT_GROUP_CUTSCENE and (act==ACT_STANDING_DEATH or act==ACT_DEATH_ON_BACK or act==ACT_DEATH_ON_STOMACH
            or act==ACT_QUICKSAND_DEATH or act==ACT_ELECTROCUTION or act==ACT_SUFFOCATION) then cause,kind='death','wince' end
    end
    s.act=act
    if not cause and s.hurt and m.hurtCounter>s.hurt then cause,kind='hurt','wince' end
    s.hurt=m.hurtCounter
    if not cause and s.stars and m.numStars>s.stars then cause,kind='star','cheer' end
    s.stars=m.numStars
    if cause then
        -- the same move twice in a row is not news: long jumps at most every 10 seconds, the rest every 4
        local wait=(cause=='long_jump' and 300 or 120)
        if f-(s.cool[cause] or -9999)>=wait then s.cool[cause]=f;s.want={kind=kind,cause=cause,frame=f} end
    end
    if s.want and f-s.want.frame>(s.want.cause=='star' and 600 or 45) then s.want=nil end      -- too late to react
    local p=PHYS
    local free=jimmie and originalBoard and jimmie.activeFlags~=0 and p and p.onGround and not PHYS_AIR and not dying
        and opportunityMotion==nil and not p.windup and not p.manual and not p.fakie
    if not free then s.t=nil;return end
    if s.want and not s.t then
        local dx,dz=m.pos.x-jimmie.oPosX,m.pos.z-jimmie.oPosZ
        if dx*dx+dz*dz<1800*1800 and OriginalBank.clips['react_'..s.want.kind] then
            s.t=0;s.kind=s.want.kind
            log('[jimmie-react] '..s.kind..' cause='..s.want.cause..' frame='..tostring(f))
            local c=s.want.cause
            if JIMMIE_BRAIN and (c=='triple_jump' or c=='long_jump' or c=='wall_kick') then pcall(JIMMIE_BRAIN.fact,'mario_move','mario',{move=c}) end
        end
        s.want=nil
    end
    if s.t then
        s.t=s.t+1
        if s.t>24 then s.t=nil;return end
        originalController.bank:apply(jimmie,originalBoard,'react_'..s.kind,(s.t-1)/23,0)
    end
end
-- motion:shadow. His ground shadow, lost when the model moved to the animated skeleton (those model files never
-- asked for one). A separate object that draws nothing but the game's own round shadow, placed at his feet each
-- frame: under the skater, and under him when he swims through the air; not underwater, not in cutscenes.
JIMMIE_FX={}
function jimmie_fx_forget() JIMMIE_FX.shadow=nil;JIMMIE_FX.shadow2=nil end
hook_event(HOOK_ON_WARP,jimmie_fx_forget)
if HOOK_ON_CLEAR_AREAS then hook_event(HOOK_ON_CLEAR_AREAS,jimmie_fx_forget) end
function jimmie_shadow_place(key,x,y,z,size)
    local s=JIMMIE_FX;local o=s[key]
    if o and not jimmie_is_mine(o) then o=nil;s[key]=nil end
    if not x then if o then o.oPosY=-10000 end return end
    if not o then
        local id=smlua_model_util_get_id('jimmie_shadow_geo')
        if not id or id==E_MODEL_ERROR_MODEL or id_bhvjimmie==nil then return end
        local ok,q=pcall(spawn_non_sync_object,id_bhvjimmie,id,x,y,z,function(q) end)
        if not (ok and q) then return end
        o=q;s[key]=o
    end
    o.oPosX,o.oPosY,o.oPosZ=x,y,z;o.oInteractType=0;o.oCollisionDistance=0
    obj_scale_xyz(o,size,size,size)
end
function jimmie_shadow_step()
    local m=gMarioStates[0]
    if not m or (m.action & ACT_GROUP_MASK)==ACT_GROUP_CUTSCENE then return end     -- scenes keep whatever was there
    if jimmie and jimmie.activeFlags~=0 and not (JIMMIE_PULL and JIMMIE_PULL.wait) then
        jimmie_shadow_place('shadow',jimmie.oPosX,jimmie.oPosY,jimmie.oPosZ,1.1)
    else jimmie_shadow_place('shadow') end
    local d=JIMMIE_SWIM
    if d and d.body and jimmie_is_mine(d.body) and d.mode=='fly' and not d.leap and d.body.oPosY>-9000 then
        jimmie_shadow_place('shadow2',d.body.oPosX,d.body.oPosY,d.body.oPosZ,1.1)
    else jimmie_shadow_place('shadow2') end
end
-- motion:fxcore. Shared by the dust, spark and sound changes. Effect objects are our own: spawned with Jimmie's inert
-- behaviour and a stock particle model, moved and removed here. Lua's math.random only; the game's random number
-- generator is never called. At most 24 live effect objects; when full, new effects are simply not made.
JIMMIE_FX=JIMMIE_FX or {}
JIMMIE_FX.list={};JIMMIE_FX.prev={}
function jimmie_fx_clear() JIMMIE_FX.list={};JIMMIE_FX.prev={} end
hook_event(HOOK_ON_WARP,jimmie_fx_clear)
if HOOK_ON_CLEAR_AREAS then hook_event(HOOK_ON_CLEAR_AREAS,jimmie_fx_clear) end
function jimmie_fx_spawn(model,x,y,z,q)
    local L=JIMMIE_FX.list
    if #L>=24 or not model or id_bhvjimmie==nil then return end
    local ok,o=pcall(spawn_non_sync_object,id_bhvjimmie,model,x,y,z,function(o) end)
    if not (ok and o) then return end
    obj_set_billboard(o);o.oInteractType=0;o.oCollisionDistance=0
    q.o=o;q.t=0;obj_scale_xyz(o,q.s0,q.s0,q.s0);L[#L+1]=q
end
function jimmie_fx_tick()
    local L=JIMMIE_FX.list;local f=get_global_timer()
    if JIMMIE_FX.ticked==f then return end;JIMMIE_FX.ticked=f
    for i=#L,1,-1 do
        local q=L[i];local o=q.o
        if not jimmie_is_mine(o) then table.remove(L,i)
        else
            q.t=q.t+1
            if q.t>=q.life then obj_mark_for_deletion(o);table.remove(L,i)
            else
                local k=q.t/q.life
                o.oPosX,o.oPosY,o.oPosZ=o.oPosX+(q.vx or 0),o.oPosY+(q.vy or 0),o.oPosZ+(q.vz or 0)
                if q.grav then q.vy=(q.vy or 0)-q.grav end
                local s=q.s0+(q.s1-q.s0)*k;obj_scale_xyz(o,s,s,s)
                if q.fade then o.oOpacity=math.floor(q.fade*(1-k)) end
                if q.frames then o.oAnimState=math.floor(k*q.frames) end
            end
        end
    end
end
function jimmie_effects_step()
    jimmie_fx_tick()
    local m=gMarioStates[0];local s=JIMMIE_FX.prev
    if not m or (m.action & ACT_GROUP_MASK)==ACT_GROUP_CUTSCENE then return end          -- no effects during scenes or text
    if jimmie_fx_water then jimmie_fx_water() end
    local alive=jimmie and jimmie.activeFlags~=0
    local crash=alive and originalCrashHost~=nil and originalCrashHost.active==true
    local p=PHYS
    if not alive or (JIMMIE_PULL and (JIMMIE_PULL.wait or JIMMIE_PULL.t)) then s.have=false;s.crash=false;return end
    local st={x=jimmie.oPosX,y=jimmie.oPosY,z=jimmie.oPosZ,obj=jimmie,crash=crash,tick=get_global_timer(),turn=0,speed=0}
    st.bailed=crash and not s.crash;s.crash=crash
    if p and not crash then
        st.speed=math.sqrt((p.vx or 0)^2+(p.vz or 0)^2);st.ground=p.onGround==true and not PHYS_AIR
        st.grind=opportunityMotion~=nil and (opportunityMotion.grind==true or opportunityMotion.phase=='grind')
        st.push=PHYS_PUSHING==true;st.yaw=p.yaw or 0
        if s.have then
            st.pushed=st.push and not s.push;st.landed=st.ground and not s.ground;st.popped=(not st.ground) and s.ground
            st.turn=math.abs(((st.yaw-s.yaw+math.pi)%(2*math.pi))-math.pi)
        end
        s.have=true;s.push=st.push;s.ground=st.ground;s.yaw=st.yaw
    else s.have=false end
    if jimmie_fx_dust then jimmie_fx_dust(st) end
    if jimmie_fx_sparks then jimmie_fx_sparks(st) end
    if jimmie_fx_sounds then jimmie_fx_sounds(st) end
end
-- motion:dust. The game's white puff model: one when he pushes off, two when he lands, one every few frames in a hard
-- turn, four bigger ones when he bails.
function jimmie_fx_dust(st)
    local function puff(n,size,spread)
        for _=1,n do
            jimmie_fx_spawn(E_MODEL_MIST,st.x+(math.random()-.5)*spread,st.y+8,st.z+(math.random()-.5)*spread,{life=12,s0=size*.5,s1=size*1.6,vy=1.2,fade=190})
        end
    end
    if st.bailed then puff(4,2.2,90);return end
    if not st.ground then return end
    if st.pushed then puff(1,1.0,20) end
    if st.landed then puff(2,1.3,50) end
    if st.turn>.07 and st.speed>12 and st.tick%5==0 then puff(1,1.0,30) end
end
-- motion:sparks. While he grinds: a small spark every other frame, thrown back and up from the board, falling.
function jimmie_fx_sparks(st)
    if not st.grind or st.tick%2~=0 then return end
    local b=(st.yaw or 0)+math.pi
    jimmie_fx_spawn(E_MODEL_SPARKLES,st.x+(math.random()-.5)*30,st.y+6,st.z+(math.random()-.5)*30,
        {life=9,s0=.45,s1=.1,vx=math.sin(b)*4+(math.random()-.5)*5,vy=5+math.random()*4,vz=math.cos(b)*4+(math.random()-.5)*5,grav=1.1,frames=5})
end
local function on_update()
    railPresentation:clear() -- early returns, pause and ownership changes fail closed
    if in_jimmie_title() then
        if not titleWasActive then
            despawn_jimmie()
            if RunMode then RunMode.reset() end
            if VOICE then VOICE.clearScene(false) end
            subtitle = nil
        end
        titleWasActive, skateTraceAllowed, wasGameplayAllowed = true, false, false
        return
    elseif titleWasActive then
        titleWasActive = false
        if RunMode then RunMode.reset() end
    end
    local m = gMarioStates[0]
    if m == nil or m.marioObj == nil then
        despawn_jimmie() -- owner loss must clear crash/death state even without scene hooks
        return
    end
    jimmie_mirror_step()
    if jimmie_fx_tick then jimmie_fx_tick() end
    jimmie_opening_step()
    jimmie_swim_step()
    if companionSpawn:observe(m) then
        despawn_jimmie()
        originalScene=originalScene+1
        marioTrail,trailSerial,trailProgress,farSince={},0,0,nil
    end
    local allowed=enabled and (not Personality or Personality.gameplay(m))
    skateTraceAllowed=allowed
    -- Owner rule: spawn in Castle Grounds -> entering the castle door within the
    -- window marks a speedrun; otherwise the session stays in normal play.
    if RunMode ~= nil and not JIMMIE_ROUTE16 then
        local npRun = gNetworkPlayers ~= nil and gNetworkPlayers[0] or nil
        if npRun ~= nil then
            local before = RunMode.mode()
            RunMode.observe(npRun.currLevelNum or 0, npRun.currAreaIndex or 0, now())
            local after = RunMode.mode()
            if after ~= before then
                log("[runmode] mode=" .. tostring(after))
                if VOICE ~= nil then
                    if after == "speedrun" then VOICE.setMode("run") end
                    if after == "normal" then VOICE.setMode("companion") end
                end
            end
        end
    end
    if VOICE and VOICE.setActivePlay then
        local moving=math.sqrt(m.vel.x*m.vel.x+m.vel.z*m.vel.z)>3 or
            (PHYS and math.sqrt((PHYS.vx or 0)^2+(PHYS.vz or 0)^2)>6)
        VOICE.setActivePlay(allowed and jimmie~=nil and not dying and moving and (manualMode==nil or manualMode=="follow"))
    end
    if not allowed then
        if skateOpportunity then skateOpportunity:cancel("gameplay-paused",{frame=get_global_timer(),time=now()}) end
        opportunityMotion=nil
        if rejoinHost then rejoinHost:pause() end
        step_original_crash(true)
        step_recovery(0,true)
        jimmie_intro_step(m)
        if VOICE then
            local finishing=JIMMIE_ROUTE16 and JIMMIE_ROUTE16.starDuringDance(m)
            if wasGameplayAllowed or VOICE.keptDanceSound~=finishing then VOICE.clearScene(true,finishing) end
        end
        wasGameplayAllowed=false
        update_host(m,false)
        director_bridge(m,false)
        return
    end
    if VOICE and VOICE.keptDanceSound then VOICE.clearScene(true) end
    wasGameplayAllowed=true

    -- Cosmetic speech observation only; both motion integrators stay unchanged.
    if VOICE and VOICE.observeWater then
        local scene = contextState and contextState:scene(gNetworkPlayers and gNetworkPlayers[0]) or "scene"
        VOICE.observeWater("mario",m.marioObj,scene,m.pos.x,m.pos.y,m.pos.z,(m.health or 0)>0)
        VOICE.observeWater("companion",jimmie,scene,jimmie and jimmie.oPosX,jimmie and jimmie.oPosY,
            jimmie and jimmie.oPosZ,jimmie~=nil and not dying and not recovery_suppressed())
    end

    -- auto voice contexts: hub (castle grounds region), water, lava
    voiceCtxT = (tonumber(voiceCtxT) or 0) + 1
    if VOICE ~= nil and voiceCtxT % 15 == 0 then
        local m = gMarioStates[0]
        local px, py, pz = m.pos.x, m.pos.y, m.pos.z
        if jimmie ~= nil and not recovery_suppressed() then px, py, pz = jimmie.oPosX, jimmie.oPosY, jimmie.oPosZ end
        local np = gNetworkPlayers ~= nil and gNetworkPlayers[0] or nil
        local hub = np ~= nil and np.currLevelNum == LEVEL_CASTLE_GROUNDS and np.currAreaIndex == 1
        if hub then VOICE.setContext("hub") else VOICE.clearContext("hub") end
        local castleInterior=np~=nil and np.currLevelNum==(LEVEL_CASTLE or 6) and np.currAreaIndex==1
        if castleInterior then VOICE.setContext("castle_interior") else VOICE.clearContext("castle_interior") end
        local wl = find_water_level(px, pz)
        if wl ~= nil and wl > -10000 and py < wl - 15 then VOICE.setContext("water")
        else VOICE.clearContext("water") end
        local h, surf = find_floor(px, py + 30, pz)
        local burning = false
        if surf ~= nil and SURFACE_BURNING ~= nil and surf.type == SURFACE_BURNING then burning = true end
        if burning then VOICE.setContext("lava") else VOICE.clearContext("lava") end
    end
    if VOICE ~= nil and VOICE.update ~= nil then VOICE.update() end
    if VOICE ~= nil and VOICE.autoMode ~= nil then VOICE.autoMode(1 / 30, math.sqrt(m.vel.x * m.vel.x + m.vel.z * m.vel.z)) end
    -- landmark proximity contexts (Peach painting / Bowser / castle door)
    if VOICE ~= nil and voiceCtxT % 20 == 0 then
        local function near(modelId, radius)
            local o = find_landmark(modelId)
            if o == nil then return false end
            local mm = gMarioStates[0]
            local dx = o.oPosX - mm.pos.x
            local dz = o.oPosZ - mm.pos.z
            return (dx * dx + dz * dz) < radius * radius
        end
        local peachNearby = near(E_MODEL_PEACH, 600)
        if peachNearby then
            if not VOICE.hasContext("peach") then
                VOICE.setContext("peach"); VOICE.post("peach_castle", {ttl=2})
            end
        else VOICE.clearContext("peach") end
        local bossNearby = near(E_MODEL_BOWSER, 1600) or near(E_MODEL_BOWSER2, 1600)
        if bossNearby then
            if not VOICE.hasContext("boss") then
                VOICE.setContext("boss"); if not (JIMMIE_ROUTE16 and JIMMIE_ROUTE16.ownsBowser()) then VOICE.post("boss_bowser",{ttl=6,priority=70}) end
            end
        else VOICE.clearContext("boss") end
        -- castle entrance zone (static geometry is not an object; use coordinates)
        local mm = gMarioStates[0]
        local doorDX = mm.pos.x - (-1328)
        local np = gNetworkPlayers ~= nil and gNetworkPlayers[0] or nil
        local grounds = np ~= nil and np.currLevelNum == LEVEL_CASTLE_GROUNDS and np.currAreaIndex == 1
        local doorZone = grounds and (doorDX > -900 and doorDX < 900 and mm.pos.z < 3950 and mm.pos.z > 3050)
        if doorZone then
            VOICE.setContext("castle_door")
            VOICE.setContext("hub")
        else
            VOICE.clearContext("castle_door")
        end
        -- Do not infer an interior Peach painting from outdoor coordinates.
    end
    updateCount = updateCount + 1
    -- Jimmie 64 graffiti sign/mural removed per user request (was spawned on level load).
    -- spawn_graffiti()
    if PENDING_CMD ~= nil and gMarioStates[0] ~= nil and gMarioStates[0].marioObj ~= nil then
        local c = PENDING_CMD
        if (c.name == "pose" or c.name == "anim" or c.name == "trick") and jimmie == nil then
            -- wait until the companion exists
        else
            PENDING_CMD = nil
            apply_live_command(c)
        end
    end
    if not enabled then if rejoinHost then rejoinHost:pause() end; return end
    load_all_sounds()
    if step_original_crash(false) then
        -- Crash renderer is the exclusive owner this tick.
    elseif jimmie_pull_step() then
        -- He is pulling out his board this tick.
    elseif jimmie_intro_step(m) then
        -- The bridge scene owns him this tick (or he has not arrived yet).
    elseif step_skate_opportunity() then
        update_pose_animation(1 / 30)
    elseif not try_rejoin(1 / 30) then
        update_movement(1 / 30)
        update_pose_animation(1 / 30)
    end
    jimmie_react_step(m)
    update_jumps()
    update_host(m,true)
    director_bridge(m,true)
    update_chatter()
    update_original_brace()
    jimmie_shadow_step()
    jimmie_effects_step()
    railPresentation:publish(rail_presentation_context())
end

local function on_hud_render()
    if in_jimmie_title() then return end
    -- only draw once the area is loaded
    local m = gMarioStates[0]
    if m == nil or m.marioObj == nil then return end

    djui_hud_set_resolution(RESOLUTION_DJUI)
    djui_hud_set_font(FONT_MENU)

    local t = now()
    local loaded = 0
    for _, list in pairs(clips) do loaded = loaded + #list end
    djui_hud_set_color(255, 230, 120, 255)
    if DEBUG_HUD == true then
    djui_hud_print_text(string.format("JIMMIE v9.9  deaths:%d  vest:%s%s  snd:%d  mdl:%d",
        deathCount, vest and "YES" or "NO", onBoard and " [board]" or "", loaded, E_MODEL_jimmie or -1), 18, 46, 0.7)
    end

    local mm2 = gMarioStates[0]
    if DEBUG_HUD == true then
    djui_hud_print_text(string.format("mode:%s pose:%s spd:%s id:%s jim:%s,%s mario:%s,%s dst:%s",
        tostring(liveMode), tostring(activeClip) .. ":" .. tostring(poseFrame),
        tostring(math.floor(tonumber(jimmieSpeed) or 0)),
        tostring((CLIPS and CLIPS[activeClip] and CLIPS[activeClip][poseFrame]) or 0),
        tostring(jimmie and math.floor(jimmie.oPosX)), tostring(jimmie and math.floor(jimmie.oPosZ)),
        tostring(mm2 and math.floor(mm2.pos.x)), tostring(mm2 and math.floor(mm2.pos.z)),
        tostring(mm2 and jimmie and math.floor(math.sqrt((mm2.pos.x-jimmie.oPosX)*(mm2.pos.x-jimmie.oPosX)+(mm2.pos.z-jimmie.oPosZ)*(mm2.pos.z-jimmie.oPosZ))) or -1)), 18, 70, 0.5)
    end
    if lastError ~= nil then
        djui_hud_set_color(255, 80, 80, 255)
        djui_hud_print_text("ERR: " .. lastError, 18, 220, 0.6)
    end

    if subtitle ~= nil and t < subtitleUntil then
        djui_hud_set_color(255, 255, 255, 255)
        local width=djui_hud_get_screen_width()
        -- Keep long captions clear of the native corner HUD.
        local maxWidth=width*0.65
        local scale=0.5
        -- FONT_MENU is taller than the old fixed 20-unit row spacing.
        local _,fontHeight=djui_hud_measure_text("Ag")
        local lineStep=math.ceil(fontHeight*scale)+3
        local lines,line={},""
        for word in subtitle:gmatch("%S+") do
            local candidate=line=="" and word or (line.." "..word)
            if line~="" and djui_hud_measure_text(candidate)*scale>maxWidth then
                lines[#lines+1]=line;line=word
            else line=candidate end
        end
        if line~="" then lines[#lines+1]=line end
        for i,text in ipairs(lines) do
            local w=djui_hud_measure_text(text)*scale
            djui_hud_print_text(text,(width-w)/2,djui_hud_get_screen_height()-65-(#lines-i)*lineStep,scale)
        end
    end
    djui_hud_reset_color()
end

-- Subtitles are emitted by VOICE.onPlayed for the selected clip.

-- ---------------------------------------------------------------------------
-- chat commands
-- ---------------------------------------------------------------------------
local function on_jimmie_command(msg)
    if JIMMIE_ROUTE16 and type(msg)=="string" and msg:match("^audition") then djui_chat_message_create("Use /j16 status for this companion."); return true end
    if Audition ~= nil and Audition.command ~= nil and Audition.command(msg) then return true end
    if type(msg)=="string" and msg:sub(1,5)=="trace" then
        if not skateTraceAdapter then djui_chat_message_create("Skate trace unavailable");return true end
        local r=skateTraceAdapter.recorder
        if msg=="trace stop" then r:stop("user-finished")
        elseif msg=="trace start" then
            r:start("grounded-follow-stage-20261107-manual-"..tostring(type(get_time)=="function" and get_time() or 0).."-"..tostring(get_global_timer()))
        else
            local phase,label=msg:match("^trace (begin) ([%w_-]+)$")
            if not phase then phase,label=msg:match("^trace (end) ([%w_-]+)$") end
            if phase then r:mark(label,phase) end
        end
        djui_chat_message_create("Skate trace "..(r.enabled and "recording/draining" or "stopped"))
        return true
    elseif msg == "auto" then
        manualMode=nil; liveMode="auto"
        if skateDirector then skateDirector:reset(contextState and contextState:scene(gNetworkPlayers and gNetworkPlayers[0]) or "auto") end
        djui_chat_message_create("Jimmie: doing my thing")
        return true
    elseif msg == "route" then
        routeEnabled=not routeEnabled
        djui_chat_message_create("Jimmie backseating: "..(routeEnabled and "ON" or "OFF"))
        return true
    elseif msg == "ai" then
        aiEnabled=not aiEnabled
        djui_chat_message_create("Jimmie live planner: " .. (aiEnabled and "ON" or "OFF"))
        return true
    elseif msg == "off" then
        enabled = false
        if VOICE ~= nil then VOICE.clearScene() end
        despawn_jimmie()
        djui_chat_message_create("jimmie: disabled")
        return true
    elseif msg == "on" then
        enabled = true
        spawn_jimmie()
        djui_chat_message_create("jimmie: enabled")
        return true
    elseif msg == "poof" then
        jimmie_dies("generic")
        djui_chat_message_create("jimmie: poof!")
        return true
    elseif msg == "vest" then
        vest = not vest
        if VOICE ~= nil then VOICE.post(vest and "vest_yes" or "vest_no", {ttl=3}) end
        djui_chat_message_create("jimmie vest: " .. (vest and "YES" or "NO"))
        return true
    elseif msg == "audio" then
        load_all_sounds()
        say("chase_mid", 1.0)
        djui_chat_message_create("jimmie: audio test")
        return true
    elseif msg == "wait" or msg == "hold" or msg == "stay" then
        manualMode="wait"
        liveMode = "wait"
        liveHoldX, liveHoldY, liveHoldZ = jimmie and jimmie.oPosX or nil, jimmie and jimmie.oPosY or nil, jimmie and jimmie.oPosZ or nil
        djui_chat_message_create("Jimmie: waiting here")
        subtitle = "Jimmie: waiting here"
        subtitleUntil = now() + 4.0
        return true
    elseif msg == "away" or msg == "leave" or msg == "go" then
        manualMode="away"
        liveMode = "away"
        djui_chat_message_create("Jimmie: fine, I'll go")
        subtitle = "Jimmie: fine, I'll go"
        subtitleUntil = now() + 4.0
        return true
    elseif msg == "follow" or msg == "come" or msg == "comeback" then
        manualMode="follow"
        liveMode = "follow"
        djui_chat_message_create("Jimmie: alright, I'm coming")
        subtitle = "Jimmie: alright, I'm coming"
        subtitleUntil = now() + 4.0
        return true
    elseif msg == "orbit" or msg == "skate" then
        manualMode="orbit"
        liveMode = "orbit"
        djui_chat_message_create("Jimmie: skate mode")
        subtitle = "Jimmie: skate mode"
        subtitleUntil = now() + 4.0
        return true
    elseif msg == "voice" then
        voiceEnabled = not voiceEnabled
        djui_chat_message_create("Jimmie imitations: " .. (voiceEnabled and "ON" or "OFF"))
        return true
    end
    return false
end

-- ---------------------------------------------------------------------------
-- init
-- ---------------------------------------------------------------------------




-- ---------------------------------------------------------------------------
-- live command relay: relay.lua is a require()d module, so the game's live
-- reload can hot-swap it while running. The bridge rewrites relay.lua with:
--   apply_live_command({ name = "wait", text = "...", audio = "live_N.ogg" })
-- ---------------------------------------------------------------------------
liveMode = "follow"
liveHoldX, liveHoldY, liveHoldZ = nil, nil, nil

local TARGET_MODELS = {
    sign = E_MODEL_WOODEN_SIGNPOST,
    butterfly = E_MODEL_BUTTERFLY,
    coin = E_MODEL_YELLOW_COIN,
    goomba = E_MODEL_GOOMBA,
    castle = E_MODEL_CASTLE_GROUNDS_METAL_DOOR,
}

find_landmark = function(modelId)
    local m = gMarioStates[0]
    if m == nil then return nil end
    local best, bestD = nil, 1e12
    local lists = { OBJ_LIST_LEVEL, OBJ_LIST_GENACTOR, OBJ_LIST_DEFAULT }
    for _, list in ipairs(lists) do
        local o = obj_get_first(list)
        while o ~= nil do
            local ok, mid = pcall(obj_get_model_id_extended, o)
            if ok and mid == modelId then
                local dx = (o.oPosX or 0) - m.pos.x
                local dz = (o.oPosZ or 0) - m.pos.z
                local d = math.sqrt(dx * dx + dz * dz)
                if d < bestD then bestD = d; best = o end
            end
            local nxt = obj_get_next(o)
            if nxt == o then break end
            o = nxt
        end
    end
    return best
end

function apply_live_command(payload)
    if payload == nil then return end
    local name = tostring(payload.name or "say")
    if name == "wait" or name == "hold" then
        manualMode="wait"
        liveMode = "wait"
        local mm = gMarioStates[0]
        local landmark = nil
        if payload.target ~= nil and TARGET_MODELS[payload.target] ~= nil then
            landmark = find_landmark(TARGET_MODELS[payload.target])
        end
        if landmark ~= nil and mm ~= nil then
            local dx = mm.pos.x - landmark.oPosX
            local dz = mm.pos.z - landmark.oPosZ
            local d = math.sqrt(dx * dx + dz * dz) + 0.001
            liveHoldX = landmark.oPosX + (dx / d) * 90
            liveHoldY = landmark.oPosY + 30
            liveHoldZ = landmark.oPosZ + (dz / d) * 90
        elseif payload.over_there and mm ~= nil then
            local yaw = (mm.faceAngle.y or 0) * math.pi / 32768
            liveHoldX = mm.pos.x + math.sin(yaw) * 220
            liveHoldY = mm.pos.y + 30
            liveHoldZ = mm.pos.z + math.cos(yaw) * 220
        else
            liveHoldX, liveHoldY, liveHoldZ = jimmie and jimmie.oPosX or nil, jimmie and jimmie.oPosY or nil, jimmie and jimmie.oPosZ or nil
        end
    elseif name == "leave" or name == "away" or name == "go_away" then
        manualMode="away"
        liveMode = "away"
    elseif name == "follow" or name == "come" or name == "come_back" then
        manualMode="follow"
        liveMode = "follow"
    elseif name == "vest" then
        if payload.vest ~= nil then vest = payload.vest end
    elseif name == "pose" then
        local mm = gMarioStates[0]
        if mm ~= nil and jimmie ~= nil then
            local myaw = mm.faceAngle.y or 0
            local fwd = myaw * math.pi / 32768
            local px = mm.pos.x + math.sin(fwd) * 110 + math.cos(fwd) * 140
            local pz = mm.pos.z + math.cos(fwd) * 110 - math.sin(fwd) * 140
            manualMode="wait"
        liveMode = "wait"
            liveHoldX = px
            liveHoldY = mm.pos.y + 20
            liveHoldZ = pz
            jimmie.oPosX = px
            jimmie.oPosY = mm.pos.y + 20
            jimmie.oPosZ = pz
            -- face back toward Mario (and the camera behind him)
            local ddx, ddz = mm.pos.x - px, mm.pos.z - pz
            jimmie.oFaceAngleYaw = (math.floor(math.atan2(ddx, ddz) * 32768 / math.pi) + 32768) % 65536
        end
    elseif name == "anim" then
        local mm = gMarioStates[0]
        local cam = geo_get_current_camera()
        if mm ~= nil and jimmie ~= nil then
            local px, pz
            if cam ~= nil then
                local cx, cz = cam.pos.x, cam.pos.z
                local dx, dz = mm.pos.x - cx, mm.pos.z - cz
                px = cx + dx * 1.30
                pz = cz + dz * 1.30
            else
                local myaw = mm.faceAngle.y or 0
                local fwd = myaw * math.pi / 32768
                px = mm.pos.x + math.sin(fwd) * 150
                pz = mm.pos.z - math.cos(fwd) * 150
            end
            manualMode="wait"
        liveMode = "wait"
            liveHoldX = px
            liveHoldY = mm.pos.y + 20
            liveHoldZ = pz
            jimmie.oPosX = px
            jimmie.oPosY = mm.pos.y + 20
            jimmie.oPosZ = pz
            if cam ~= nil then
                local ddx, ddz = cam.pos.x - px, cam.pos.z - pz
                jimmie.oFaceAngleYaw = math.floor(math.atan2(ddx, -ddz) * 32768 / math.pi) % 65536
            else
                local myaw = mm.faceAngle.y or 0
                jimmie.oFaceAngleYaw = myaw % 0x10000
            end
            POSE_TEST = true
            DEBUG_CLIP = payload.target
            poseAnimation = {} -- replay from sample one, including repeated debug requests
        end
    elseif name == "quad" then
        local mm = gMarioStates[0]
        if mm ~= nil and TESTTEX_MODEL ~= nil then
            local yaw = (mm.faceAngle.y or 0) * math.pi / 32768
            local px = mm.pos.x + math.sin(yaw) * 150 + math.cos(yaw) * 120
            local pz = mm.pos.z + math.cos(yaw) * 150 - math.sin(yaw) * 120
            local o = spawn_sync_object(id_bhvgraffiti, TESTTEX_MODEL, px, mm.pos.y + 120, pz, nil)
                if o ~= nil then
                    o.oFaceAngleYaw = (mm.faceAngle.y + 0x8000) % 0x10000
                    o.oPosX = mm.pos.x + math.sin((mm.faceAngle.y or 0) * math.pi / 32768) * 260
                    o.oPosZ = mm.pos.z + math.cos((mm.faceAngle.y or 0) * math.pi / 32768) * 260
                end
            if o ~= nil then o.oFaceAngleYaw = (mm.faceAngle.y + 0x8000) % 0x10000 end
            log("test textured quad spawned")
        end
    elseif name == "ctx" then
        if VOICE ~= nil and payload.text ~= nil then VOICE.setContext(tostring(payload.text)) end
    elseif name == "voice" then
        if payload.text ~= nil then say(tostring(payload.text), 1.0) end
    elseif name == "voicetest" then
        if VOICE ~= nil and payload.text ~= nil and VOICE.test ~= nil then VOICE.test(tostring(payload.text)) end
    elseif name == "pos" then
        local mm = gMarioStates[0]
        log(string.format("[voice] pos mario=%.0f,%.0f,%.0f jimmie=%s", mm.pos.x, mm.pos.y, mm.pos.z,
            tostring(jimmie ~= nil and math.floor(jimmie.oPosX) or -1) .. "," ..
            tostring(jimmie ~= nil and math.floor(jimmie.oPosZ) or -1)))
    elseif name == "modelids" then
        log(string.format("[voice] ids sign=%s door=%s peach=%s bowser=%s butterfly=%s",
            tostring(E_MODEL_WOODEN_SIGNPOST), tostring(E_MODEL_CASTLE_GROUNDS_METAL_DOOR),
            tostring(E_MODEL_PEACH), tostring(E_MODEL_BOWSER), tostring(E_MODEL_BUTTERFLY)))
    elseif name == "objscan" then
        local lists = { OBJ_LIST_LEVEL, OBJ_LIST_GENACTOR, OBJ_LIST_DEFAULT }
        for li, list in ipairs(lists) do
            local n = 0
            local samples = {}
            local o = obj_get_first(list)
            while o ~= nil and n < 400 do
                n = n + 1
                if #samples < 6 then
                    local ok, mid = pcall(obj_get_model_id_extended, o)
                    samples[#samples + 1] = tostring(ok and mid or "ERR")
                end
                local nxt = obj_get_next(o)
                if nxt == o then break end
                o = nxt
            end
            log(string.format("[voice] objscan list%d n=%d ids=%s", li, n,
                table.concat(samples, ",")))
            local hit = find_landmark(E_MODEL_WOODEN_SIGNPOST)
            log("[voice] objscan find_landmark sign -> " .. tostring(hit ~= nil))
        end
    elseif name == "chattest" then
        if VOICE ~= nil and VOICE.post ~= nil then
            VOICE.post("chat_reaction", { cats = { "chat" }, t = now() })
        end
    elseif name == "skin" then
        local want = (payload ~= nil and payload.text ~= nil) and payload.text or "vest"
        local prefix = "jimmie3"
        if want == "tee" or want == "novest" then prefix = "jimmie3nv" end
        if want == "raglan" or want == "promo" then prefix = "jimmie3rg" end
        if _G.reload_skin ~= nil then _G.reload_skin(prefix) end
        log("skin command -> " .. prefix)
    elseif name == "statue" then
        local mm = gMarioStates[0]
        local yaw = (mm.faceAngle.y or 0) * math.pi / 32768
        local px = mm.pos.x + math.sin(yaw) * 220
        local pz = mm.pos.z + math.cos(yaw) * 220
        local py = find_floor_height(px, mm.pos.y + 50, pz)
        local ok, mid = pcall(smlua_model_util_get_id, string.format("%s_idle_00_geo", (_G.G_SKIN_PREFIX or "jimmie3")))
        if ok and mid ~= nil and mid > 0 then
            local o = spawn_sync_object(id_bhvgraffiti, mid, px, py, pz, nil)
            if o ~= nil then
                o.oFaceAngleYaw = (mm.faceAngle.y or 0) % 0x10000
                log("statue spawned")
            end
        end
    elseif name == "fasttest" then
        local mm = gMarioStates[0]
        local yaw = (mm.faceAngle.y or 0) * math.pi / 32768
        local px = mm.pos.x + math.sin(yaw) * 200
        local pz = mm.pos.z + math.cos(yaw) * 200
        local py = find_floor_height(px, mm.pos.y + 50, pz)
        local ok, mid = pcall(smlua_model_util_get_id, "fast64test_geo")
        if ok and mid ~= nil and mid > 0 then
            local o = spawn_sync_object(id_bhvgraffiti, mid, px, py, pz, nil)
            if o ~= nil then
                o.oFaceAngleYaw = (mm.faceAngle.y or 0) % 0x10000
                log("fast64 test spawned")
            end
        else
            log("fast64 model id not found")
        end
    elseif name == "landmarks" then
        local function report(label, modelId)
            local o = find_landmark(modelId)
            if o == nil then log("[voice] landmark " .. label .. " = none"); return end
            local mm = gMarioStates[0]
            local dx, dz = o.oPosX - mm.pos.x, o.oPosZ - mm.pos.z
            log(string.format("[voice] landmark %s dist=%.0f pos=%.0f,%.0f", label,
                math.sqrt(dx * dx + dz * dz), o.oPosX, o.oPosZ))
        end
        report("peach", E_MODEL_PEACH)
        report("bowser", E_MODEL_BOWSER)
        report("bowser2", E_MODEL_BOWSER2)
        report("door", E_MODEL_CASTLE_GROUNDS_METAL_DOOR)
        report("sign", E_MODEL_WOODEN_SIGNPOST)
    elseif name == "voicegated" then
        if VOICE ~= nil and payload.text ~= nil and VOICE.testGated ~= nil then VOICE.testGated(tostring(payload.text)) end
    elseif name == "run" then
        if VOICE ~= nil then VOICE.setMode("run") end
    elseif name == "companion" then
        if VOICE ~= nil then VOICE.setMode("companion") end
    elseif name == "trick" then
        TRICK_PENDING = true
    elseif name == "debug" then
        DEBUG_HUD = not DEBUG_HUD
    elseif name == "orbit" or name == "skate" then
        manualMode="orbit"
        liveMode = "orbit"
    elseif name == "die" then
        jimmie_dies("generic")
    elseif name == "trace" then
        -- Measurement-only control for frame_recorder.lua. No speech or gameplay
        -- path reads this data; disabled until an explicit relay command.
        if TraceRecorder ~= nil then
            if payload.off == true then
                TraceRecorder.stop()
            elseif payload.dump == true then
                TraceRecorder.dump()
            else
                TraceRecorder.start()
            end
            local st = TraceRecorder.status()
            log(string.format("[trace] enabled=%s frames=%d exported=%d batches=%d",
                tostring(st.enabled), st.frames, st.exported, st.batches))
        else
            log("[trace] recorder not loaded")
        end
    elseif name == "shadow" then
        -- QA only: silent would-play logging for the Cannonless encounter.
        -- Default off; enabling changes nothing audible. `allow_collected_star`
        -- is an explicit validation override for saves where the star exists.
        if ShadowPerf ~= nil then
            ShadowPerf.enable(payload.on == true,
                { allow_collected_star = payload.allow_collected_star == true })
            local st = ShadowPerf.status()
            log(string.format("[shadow] enabled=%s frames=%d",
                tostring(st.enabled), tonumber(st.frames) or 0))
        else
            log("[shadow] module not loaded")
        end
    elseif name == "perf" then
        -- Default-OFF enablement path for whole-phrase reactions. Enabling plays
        -- real single clips through the existing voice channel on confirmed events.
        if PerformancePlayback ~= nil then
            PerformancePlayback.enable(payload.on == true)
            log("[perf] enabled=" .. tostring(PerformancePlayback.enabled))
        else
            log("[perf] module not loaded")
        end
    elseif name == "runmode" then
        -- QA/status control for the spawn->castle-door detection. `window` tunes
        -- the threshold; `force` = speedrun|normal|auto overrides detection.
        if RunMode ~= nil then
            if payload.window ~= nil then RunMode.setWindow(tonumber(payload.window)) end
            if payload.force == "speedrun" or payload.force == "normal" then
                RunMode.force(payload.force)
            elseif payload.force == "auto" then
                RunMode.force(nil)
            end
            local st = RunMode.status()
            log(string.format(
                "[runmode] mode=%s window=%.1fs spawn=%s decided=%s forced=%s last=%s/%s",
                tostring(st.mode), tonumber(st.window) or 0, tostring(st.spawn),
                tostring(st.decided), tostring(st.forced),
                tostring(st.last_level), tostring(st.last_area)))
        else
            log("[runmode] module not loaded")
        end
    elseif name == "warp" and JIMMIE_DEV_COMMANDS then
        -- Measurement-only: move Mario to a level/area/act for collision probing.
        local level, area, act = tonumber(payload.level), tonumber(payload.area), tonumber(payload.act)
        if level ~= nil and type(warp_to_level) == "function" then
            local okWarp = warp_to_level(math.floor(level), math.floor(area or 1), math.floor(act or 1))
            log(string.format("[warp] level=%d area=%d act=%d ok=%s",
                math.floor(level), math.floor(area or 1), math.floor(act or 1), tostring(okWarp)))
        else
            log("[warp] invalid request")
        end
    elseif name == "probe" then
        -- Measurement-only collision scan: floor heights and wall proximity.
        local mmProbe = gMarioStates[0]
        local cx = tonumber(payload.x) or (mmProbe ~= nil and mmProbe.pos.x or nil)
        local cz = tonumber(payload.z) or (mmProbe ~= nil and mmProbe.pos.z or nil)
        local cy = tonumber(payload.y)
        local step = tonumber(payload.step) or 40
        local radius = tonumber(payload.radius) or 0
        local ymin, ymax, ystep = tonumber(payload.ymin), tonumber(payload.ymax), tonumber(payload.ystep)
        if cx == nil or cz == nil or type(find_floor) ~= "function" then
            log("[probe] invalid request")
        elseif ymin ~= nil and ymax ~= nil then
            local scratch = { x = cx, y = ymin, z = cz }
            for y = ymin, ymax, (ystep or step) do
                scratch.x, scratch.y, scratch.z = cx, y, cz
                local okWall, wall = pcall(resolve_and_return_wall_collisions, scratch, 36, 32)
                log(string.format("[probe] wall x=%.0f z=%.0f y=%.0f hit=%s",
                    cx, cz, y, tostring(okWall and wall ~= nil)))
            end
        else
            local mm = mmProbe
            if cy == nil then cy = (mm ~= nil and mm.pos.y or 0) + 200 end
            local xs, zs = {}, {}
            for x = cx - radius, cx + radius, step do xs[#xs + 1] = x end
            for z = cz - radius, cz + radius, step do zs[#zs + 1] = z end
            if #xs > 50 then log("[probe] grid too wide, clipped") end
            for i = 1, math.min(#xs, 50) do
                for j = 1, math.min(#zs, 50) do
                    local x, z = xs[i], zs[j]
                    local okFloor, h = pcall(find_floor, x, cy, z)
                    local floor = (okFloor and h ~= nil and h > -10000) and string.format("%.0f", h) or "none"
                    local scratch = { x = x, y = cy, z = z }
                    local okWall, wall = pcall(resolve_and_return_wall_collisions, scratch, 36, 32)
                    log(string.format("[probe] cell x=%.0f z=%.0f floor=%s wall=%s",
                        x, z, floor, (okWall and wall ~= nil) and "1" or "0"))
                end
            end
        end
    elseif name == "compat" then
        -- Measurement-only engine compatibility flags (same semantics as
        -- route_sensors.lua). Read-only; no setting is changed. Engine structs may
        -- be userdata, so every field read goes through pcall instead of a table check.
        local function flag(owner, key)
            if owner == nil then return "unknown" end
            local ok, value = pcall(function() return owner[key] end)
            if not ok or value == nil then return "unknown" end
            if type(value) == "boolean" then return tostring(value) end
            if type(value) == "number" then return tostring(value) end
            return type(value)
        end
        local lv = gLevelValues
        local gs = gServerSettings
        log(string.format("[compat] types gLevelValues=%s gServerSettings=%s",
            type(lv), type(gs)))
        log(string.format("[compat] fixCollisionBugs=%s useGlobalStarIds=%s disableActs=%s pauseExitAnywhere=%s",
            flag(lv, "fixCollisionBugs"), flag(lv, "useGlobalStarIds"),
            flag(lv, "disableActs"), flag(lv, "pauseExitAnywhere")))
        log(string.format("[compat] fixCollisionBugsFalseLedgeGrab=%s fixCollisionBugsPickBestWall=%s",
            flag(lv, "fixCollisionBugsFalseLedgeGrab"), flag(lv, "fixCollisionBugsPickBestWall")))
        log(string.format("[compat] stayInLevelAfterStar=%s",
            flag(gs, "stayInLevelAfterStar")))
        if type(get_current_save_file_num) == "function" then
            local fileNum = get_current_save_file_num()
            local mask = -1
            if type(save_file_get_star_flags) == "function" then
                mask = save_file_get_star_flags(fileNum - 1, 1)
            end
            log(string.format("[compat] save_file=%s course2_mask=%s", tostring(fileNum), tostring(mask)))
        end
    elseif name == "cast" then
        -- Measurement-only: reproduce the engine's floor selection for a ledge-grab
        -- search. For each candidate nextPos.y, calls find_floor(cx, y+lift, cz) and
        -- logs the returned surface height and normal. Read-only; no Mario writes.
        local mmCast = gMarioStates[0]
        local cx = tonumber(payload.x) or (mmCast ~= nil and mmCast.pos.x or nil)
        local cz = tonumber(payload.z) or (mmCast ~= nil and mmCast.pos.z or nil)
        local ymin, ymax = tonumber(payload.ymin), tonumber(payload.ymax)
        local ystep = tonumber(payload.ystep) or 10
        local lift = tonumber(payload.lift) or 160
        if cx == nil or cz == nil or ymin == nil or ymax == nil or type(find_floor) ~= "function" then
            log("[cast] invalid request")
        else
            for y = ymin, ymax, ystep do
                local okF, h, surf = pcall(find_floor, cx, y + lift, cz)
                local nx, ny, nz = "nil", "nil", "nil"
                if okF and surf ~= nil then
                    local okN, n = pcall(function() return surf.normal end)
                    if okN and n ~= nil then
                        local okX, vx = pcall(function() return n.x end)
                        local okY, vy = pcall(function() return n.y end)
                        local okZ, vz = pcall(function() return n.z end)
                        if okX then nx = string.format("%.3f", vx) end
                        if okY then ny = string.format("%.3f", vy) end
                        if okZ then nz = string.format("%.3f", vz) end
                    end
                end
                local okW, wall = pcall(resolve_and_return_wall_collisions, { x = cx, y = y, z = cz }, 36, 32)
                log(string.format("[cast] x=%.0f z=%.0f nextpos_y=%.0f search_y=%.0f floor=%s normal=(%s,%s,%s) wall=%s",
                    cx, cz, y, y + lift, tostring(okF and h or "err"), nx, ny, nz,
                    (okW and wall ~= nil) and "1" or "0"))
            end
        end
    elseif name == "stage" and JIMMIE_DEV_COMMANDS then
        -- Measurement-only staged placement for mechanism verification. Attempts
        -- memory-only writes to Mario position/velocity and a freefall action.
        -- Documented MarioState fields are read-only; this logs whether the engine
        -- accepted the write. Never touches the save file.
        local mmStage = gMarioStates[0]
        if mmStage == nil then
            log("[stage] no Mario")
        else
            local okStage, errStage = pcall(function()
                mmStage.pos.x = tonumber(payload.x) or mmStage.pos.x
                mmStage.pos.y = tonumber(payload.y) or mmStage.pos.y
                mmStage.pos.z = tonumber(payload.z) or mmStage.pos.z
                mmStage.vel.x = tonumber(payload.vx) or 0
                mmStage.vel.y = tonumber(payload.vy) or 0
                mmStage.vel.z = tonumber(payload.vz) or 0
                if type(set_mario_action) == "function" then
                    set_mario_action(mmStage, _G.ACT_FREEFALL or 0x0100088C, 0)
                end
            end)
            log(string.format("[stage] attempted x=%s y=%s z=%s vx=%s vy=%s vz=%s ok=%s err=%s",
                tostring(payload.x), tostring(payload.y), tostring(payload.z),
                tostring(payload.vx), tostring(payload.vy), tostring(payload.vz),
                tostring(okStage), tostring(errStage)))
        end
    end
    local function show_reply()
        if payload.text ~= nil then
            subtitle = "Jimmie: " .. tostring(payload.text)
            subtitleUntil = now() + (tonumber(payload.seconds) or 7.0)
            djui_chat_message_create(subtitle)
        end
    end
    if payload.audio ~= nil and payload.audio ~= "" then
        local ok, snd = pcall(VOICE.performanceScope.load, tostring(payload.audio))
        if ok and snd ~= nil and VOICE ~= nil then
            VOICE.register(snd, tostring(payload.audio))
            VOICE.external(snd, tonumber(payload.seconds), {text=payload.text, onPlay=show_reply, ttl=6})
        end
    else
        show_reply()
    end
end

local okDirectorRelay,directorRelayErr=true,nil
if not okDirectorRelay then print("[jimmie] director relay unavailable: "..tostring(directorRelayErr)) end
local okRelay, relayErr = true, nil
if not okRelay then print("[jimmie] relay require failed: " .. tostring(relayErr)) end

register_behavior()
do
local CrashNative=require('native_crash')
local CrashData=require('crash_clips')
originalCrashHost=CrashNative.new(_G,CrashData,{core=require('crash'),renderer=require('stock_renderer'),capture=require('crash_surface_capture')},
    {owns=function(body,board) return body==jimmie and board==originalBoard and original_pair_valid() end})
local crashBound,crashWhy=originalCrashHost:bind()
if not crashBound then log('crash capture unavailable: '..tostring(crashWhy)) end
local braceId=smlua_model_util_get_id(OriginalBrace.MODEL)
if braceId and braceId>0 and braceId~=E_MODEL_ERROR_MODEL then originalBraceModel=braceId end
end

-- Measurement reads are local copies only. Missing stamps/bounds remain unknown.
local function skate_trace_snapshot(phase)
    local nav=recoveryController
    local w=nav and nav.world or {}
    local motion=nav and nav.last or {}
    if rejoinTraceResult and rejoinTraceResult.frame==get_global_timer() then motion=rejoinTraceResult end
    local np=gNetworkPlayers and gNetworkPlayers[0]
    local scene=contextState and contextState:scene(np) or
        (tostring(np and np.currLevelNum)..":"..tostring(np and np.currAreaIndex)..":"..tostring(np and np.currActNum))
    local stamp=nav and nav.cacheStamp
    local candidates={}
    for i,c in ipairs(nav and nav.grinds or {}) do
        if i>3 then break end
        candidates[#candidates+1]={id=c.id,kind=c.kind,width=c.width,a=c.a,b=c.b,pose="held-idle_00"}
    end
    -- A cached empty list can mean refused/budget-exhausted scan. It is NOT
    -- evidence of no rail. Only an explicit completed scan may mark available.
    local scan=nav and nav.lastRailScan
    local scanStamp=scan and scan.stamp
    local currentTerrain
    if type(smlua_collision_util_get_current_terrain_collision)=="function" then
        local ok,value=pcall(smlua_collision_util_get_current_terrain_collision)
        if ok then currentTerrain=value end
    end
    local bounds
    if skateTraceBounds then
        if phase=="update" then skateTraceBounds:observe(jimmie,get_global_timer(),scene,CLIPS,activeClip,poseFrame)
        else bounds=skateTraceBounds:bounds(jimmie,get_global_timer(),scene,CLIPS,activeClip,poseFrame) end
    end
    return {frame=get_global_timer(),scene=scene,currentTerrain=currentTerrain,instance=jimmie and tostring(jimmie) or nil,
        mario=gMarioStates[0],phys=PHYS,object=jimmie,enabled=enabled,alive=not dying,
        paused=skateTraceAllowed~=true,manual=manualMode~=nil and manualMode~="follow",
        waiting=liveMode=="wait" or liveMode=="hold",
        hidden=jimmie and jimmie.oPosY==-10000 or false,
        motion=motion,motionFresh=skateTraceMotionFrame==get_global_timer(),
        updateWorkSeconds=skateTraceUpdateSeconds,
        capture={scene=w.scene,generation=w.generation,revision=w.revision,complete=w.complete,error=w.error},
        proof=motion.stamp,
        rails={available=scan and scan.ok==true or false,
            frame=scan and scan.frame,scene=scanStamp and scanStamp.scene,generation=scanStamp and scanStamp.generation,
            revision=scanStamp and scanStamp.revision,recognized=scan and scan.count,
            eligible=scan and scan.eligible,reason=scan and scan.reason or "recognition-outcome-not-exposed",
            candidates=candidates},
        bounds=bounds}
end
local function skate_trace_call(method)
    if not skateTraceAdapter or skateTraceFault then return end
    local ok,err=pcall(skateTraceAdapter[method],skateTraceAdapter)
    if not ok then
        skateTraceFault=true
        print("[jimmie] skate trace unavailable: "..tostring(err))
    end
end
-- Native-bounds telemetry is not valid for the new articulated model.
local function unused_trace_gate() end
local function skate_trace_now()
    if type(clock_elapsed_f64)~="function" then return nil end
    local ok,value=pcall(clock_elapsed_f64)
    if ok and type(value)=="number" and value==value and math.abs(value)<math.huge then return value end
end
local checked_update=protect("update",on_update)
local function measured_update()
    skateTraceMotionFrame=nil;skateTraceAllowed=false;rejoinTraceResult=nil
    local started=skate_trace_now()
    checked_update()
    local finished=skate_trace_now()
    skateTraceUpdateSeconds=started and finished and finished>=started and finished-started or nil
    skate_trace_call("onUpdate")
end
local checked_hud=protect("hud",on_hud_render)
local function measured_hud()
    checked_hud()
    skate_trace_call("onHud")
end
if HOOK_ON_EXIT~=nil then
    hook_event(HOOK_ON_EXIT,function()
        if not skateTraceAdapter or skateTraceFault then return end
        local ok=pcall(function()
            local r=skateTraceAdapter.recorder;r:stop("engine-exit")
            -- Exit-only bounded drain: <=13 lines total, never a frame-time loop.
            for _=1,12 do if r:drain() then break end end
        end)
        if not ok then skateTraceFault=true end
    end)
end

if HOOK_ON_CLEAR_AREAS ~= nil then
    hook_event(HOOK_ON_CLEAR_AREAS, function() gameplayReady=false; companionSpawn:invalidate(); despawn_jimmie(); originalScene=originalScene+1; if rejoinHost then rejoinHost:invalidate() end; if skateOpportunity then skateOpportunity:cancel("areas-cleared",{frame=get_global_timer(),time=now()}) end; opportunityMotion=nil end)
end
hook_event(HOOK_ON_OBJECT_RENDER, protect("rail_presentation", render_rail_presentation))
hook_event(HOOK_UPDATE, measured_update)
hook_event(HOOK_ON_LEVEL_INIT, protect("level_init", on_level_init))
hook_event(HOOK_ON_SYNC_VALID, protect("sync_valid", on_sync_valid))
hook_event(HOOK_ON_DEATH, protect("death", on_death))
hook_event(HOOK_ON_HUD_RENDER, measured_hud)
hook_event(HOOK_ON_CHAT_MESSAGE, protect("chatmsg", function(sender, msg)
        if VOICE ~= nil and VOICE.post ~= nil then
            VOICE.post("chat_reaction", { cats = { "chat" } })
        end
    lastChatMsg = tostring(msg)
    return true
end))
if HOOK_CHARACTER_SOUND ~= nil then
    hook_event(HOOK_CHARACTER_SOUND, protect("char_sound", on_character_sound))
end
hook_chat_command("jimmie", "[on|off|auto|ai|route|wait|follow|skate|poof|vest|audio|voice|audition on|audition off|audition 1|audition 2|audition 3]", protect("cmd", on_jimmie_command))

log("jimmie Companion v" .. MOD_VERSION .. " loaded")





-- Review controls use stock chat hooks, never Mario input/physics.
hook_chat_command('jmotion','[ollie|kickflip|heelflip|bs_pop_shuvit|fs_pop_shuvit|crash|crashdemo|auto|status]',function(text)
 local name=tostring(text or ''):lower():match('^%s*(.-)%s*$')
 if name=='status' then djui_chat_message_create('Jimmie original motion: '..tostring(activeClip)..' / '..tostring(originalSkin));return true end
 if name=='auto' then requestedOriginalTrick=nil;return true end
 if name=='crash' or name=='crashdemo' then if jimmie and not dying then jimmie_dies('board','trick_bail') end;return true end
 if name=='ollie' then name='trick' end
 if name=='trick' or name=='kickflip' or name=='heelflip' or name=='bs_pop_shuvit' or name=='fs_pop_shuvit' then
  requestedOriginalTrick=name
  if PHYS and PHYS.onGround and not dying then TRICK_PENDING=true end
  return true
 end
 return false
end)

;(function()
-- Appended inside a closure in the private, pinned package's existing companion mod.
if type(jimmie_route_enabled) ~= "function" or not jimmie_route_enabled() then return end
JIMMIE_ROUTE16 = require("route_companion16").new({
    json = Personality.json,
    voice = VOICE,
    eligible = VOICE.performanceScope.route_eligible,
    authorize = VOICE.performanceScope.bind("route"),
    gameplay = function() return enabled and gameplayReady and not in_jimmie_title() end,
    hint = function() return RunMode and RunMode.mode() or "unknown" end,
    resetHint = function() if RunMode then RunMode.reset() end end,
    nearby = function()
        return VOICE.ready and VOICE.available() and VOICE.distance() <= 1400
    end,
    load = function(name) return VOICE.performanceScope.load(name) end,
    duration = function(file)
        local row=VOICE.REGISTRY[file]
        return row and row.seconds or 1.5
    end,
})
do
-- Installed after the physical controller and the private route director are ready.
local function context()
    local w=JIMMIE_ROUTE16.performanceContext()
    if not w or not original_pair_valid() then return nil end
    w.physicalScene,w.body,w.board=tostring(originalScene),jimmie,originalBoard
    w.frame,w.qpc_ms=get_global_timer(),jimmie_route_now_ms()
    w.grounded=PHYS~=nil and PHYS.onGround==true
    local distance=VOICE.distance()
    w.nearby=VOICE.available() and distance~=nil and distance<=1400 or false
    return w
end
local take=require("performance_skate_take")
local allowed=require("performance_rules").skate_generic
local sample
if take.file then
    sample=VOICE.performanceScope.load(take.file)
    if sample then VOICE.register(sample,take.file) end
end
local lastHeard
local function observed(fact)
    print("[jimmie-skate-memory] "..Personality.json(fact))
    if JIMMIE_BRAIN then JIMMIE_BRAIN.skate(fact) end
    if fact.fact~="trick_completed" or fact.kind~="trick" or not fact.nearby or VOICE.busy() or VOICE.holdsArrivalVoice() then return end
    local current=function() return VOICE.skateMemory.valid(fact) end
    if not current() then return end
    if take.file and fact.condition=="landing_after_getup" and fact.mode==take.mode then
        if not sample or lastHeard and fact.qpc_ms-lastHeard<65000 then return end
        local grant=VOICE.performanceWitness("skate_recovery","trick_completed",fact)
        if grant then
            VOICE.external(sample,take.seconds,{event="skate_recovery",text=take.words,priority=55,ttl=.32,valid=current,
                onPlay=function() lastHeard=jimmie_route_now_ms() end},grant)
        end
        return
    end
    local event=({trick="trick_ollie",trick2="trick_kickflip",kickflip="trick_kickflip"})[fact.clip]
    if not event or not allowed[fact.mode] or not allowed[fact.mode][event] then return end
    local grant=VOICE.performanceWitness(event,"trick_landed",fact)
    if grant then VOICE.post(event,{performanceGrant=grant,volume=1.0,t=now()}) end
end
VOICE.skateMemory=require("performance_skate_memory").new(context,observed)

end
VOICE.performanceWitness=require("performance_gameplay").bind(VOICE.performanceScope,function() return JIMMIE_ROUTE16 end,VOICE.skateMemory)
companionSpawn.g=setmetatable({JIMMIE_ROUTE16=JIMMIE_ROUTE16},{__index=companionSpawn.g})
VOICE.holdsArrivalVoice=JIMMIE_ROUTE16.holdsArrivalVoice
local streamDrops=require("performance_stream_drop").new(VOICE,JIMMIE_ROUTE16,require("performance_stream_assets"),
    jimmie_route_now_ms,function(row) print("[jimmie-stream-drop] "..Personality.json(row)) end)
VOICE.waterFact=require("performance_water_memory").bind(function(kind,subject)
    local w=JIMMIE_ROUTE16.performanceContext()
    local m=gMarioStates[0]
    if not w or w.mode~="free" or not original_pair_valid() or not m then return nil end
    if kind=="mario" and subject==m.marioObj then w.actor="mario"
    elseif kind=="companion" and subject==jimmie and not dying and not recovery_suppressed() then w.actor="jimmie"
    else return nil end
    w.distance=VOICE.distance()
    w.nearby=VOICE.available() and w.distance~=nil and w.distance<=1400
    w.body,w.board,w.physicalScene=jimmie,originalBoard,tostring(originalScene)
    w.frame,w.qpc_ms=get_global_timer(),jimmie_route_now_ms()
    return w
end,function(row) print("[jimmie-water] "..Personality.json(row));streamDrops(row);return true end)
hook_event(HOOK_UPDATE,JIMMIE_ROUTE16.update)
hook_event(HOOK_ON_CLEAR_AREAS,JIMMIE_ROUTE16.clear)
hook_event(HOOK_ON_INTERACT,JIMMIE_ROUTE16.interaction)
hook_event(HOOK_ON_DEATH,JIMMIE_ROUTE16.death)
hook_chat_command("j16","[auto|16|free|status] Companion behavior",JIMMIE_ROUTE16.command)
print("[j16] ready")

end)()

;(function()
-- Appended inside the companion mod's main closure by tools/build_game.py, after VOICE and
-- JIMMIE_ROUTE16 exist. While the brain process is running, every word Jimmie says comes from
-- it; when it is not, the build behaves like its parent.
if type(jimmie_route_enabled) ~= "function" or not jimmie_route_enabled() then return end
local VETO = {["roast_01.ogg"] = true, ["roast_02.ogg"] = true}
-- Where his voice comes from. Close by, it is him. When he has fallen behind, it is a point 1800
-- units from Mario in his direction, so he is still heard, from the right side, as if calling over.
local function heard_from()
    local p, m = VOICE.pos(), gMarioStates[0]
    local d = VOICE.distance()
    if p and m and m.pos and d and d > 1800 and d < math.huge then
        local k = 1800 / d
        return { x = m.pos.x + (p.x - m.pos.x) * k, y = m.pos.y + (p.y - m.pos.y) * k, z = m.pos.z + (p.z - m.pos.z) * k }
    end
    return p
end

local function speak(sample, seconds, detail)
    local t = VOICE.now()
    if detail.valid and not detail.valid() then return false end
    if VOICE.currentSnd then pcall(audio_sample_stop, VOICE.currentSnd) end   -- a reaction cuts a ramble off
    local ok = pcall(audio_sample_play, sample, heard_from(), detail.volume or 1.0)
    if not ok then return false end
    VOICE.currentSnd, VOICE.currentPriority, VOICE.currentEvent = sample, 66, detail.event
    VOICE.currentValid, VOICE.currentInterruptible = nil, false
    VOICE.busyUntil, VOICE.duckUntil, VOICE.lastGlobal = t + seconds + 0.15, t + seconds + 0.15, t
    pcall(seq_player_lower_volume, 0, 6, 52)
    pcall(seq_player_lower_volume, 3, 6, 52)
    VOICE.queue = {}
    if detail.event == "brain_reply" and detail.text and djui_chat_message_create then   -- an answer to chat shows in chat too
        pcall(djui_chat_message_create, "\\#ffd75e\\Jimmie\\#dcdcdc\\: " .. detail.text)
    end
    if detail.onPlay then pcall(detail.onPlay) end
    return true
end
JIMMIE_BRAIN = require("jimmie_brain_link").new({
    json = Personality.json,
    clock = jimmie_route_now_ms,
    print = print,
    busy = VOICE.busy,
    veto = VETO,
    load = function(name)
        local ok, snd = pcall(audio_sample_load, name)
        return ok and snd or nil
    end,
    context = function()
        local w = JIMMIE_ROUTE16.performanceContext()
        if not w then return nil end
        local distance = VOICE.distance()
        w.nearby = VOICE.ready and VOICE.available() and distance ~= nil and distance < math.huge   -- any distance: see heard_from()
        return w
    end,
    speak = speak,
})
hook_event(HOOK_UPDATE, JIMMIE_BRAIN.update)
hook_event(HOOK_ON_CLEAR_AREAS, JIMMIE_BRAIN.clear)
hook_event(HOOK_ON_INTERACT, JIMMIE_BRAIN.interact)
hook_event(HOOK_ON_DEATH, JIMMIE_BRAIN.death)
if HOOK_ON_CHAT_MESSAGE then hook_event(HOOK_ON_CHAT_MESSAGE, function(m, msg) pcall(JIMMIE_BRAIN.chat, m, msg) end) end
print("[jb] link ready")

-- Every text box, one box each, in Jimmie's voice (jimmie_dialogs.lua): reading never costs time.
do
    local ok, boxes = pcall(require, "jimmie_dialogs")
    local done = 0
    if ok and type(boxes) == "table" and type(smlua_text_utils_dialog_replace) == "function" then
        for _, d in ipairs(boxes) do
            if pcall(smlua_text_utils_dialog_replace, d[1], 1, d[2], d[3], d[4], d[5]) then done = done + 1 end
        end
    end
    print("[jdlg] text boxes replaced: " .. done)
end

-- The run clock on screen, and the three tells that decide whether this file is a 16-star run.
-- The game program does the timing (jimmie_run_state); this only decides whether to show it.
if type(jimmie_run_state) == "function" then
    local TELLS = require("jimmie_run_tells")
    local tells = TELLS.new()
    local lastPhase, lastStars, lastVerdict, flashUntil, flashText = nil, 0, nil, 0, nil
    -- Splits, attempt count and the text-box variants live in one global table: this closure is
    -- close to Lua's limit of local variables.
    JIMMIE_RUN = { attempts = 0, delta = nil, splits = nil, variants = nil, rows = {} }
    do
        local okS, SPLITS = pcall(require, "jimmie_run_splits")
        if okS and type(SPLITS) == "table" and type(mod_storage_load_number) == "function" then
            JIMMIE_RUN.fmt = SPLITS.delta
            JIMMIE_RUN.splits = SPLITS.new(mod_storage_load_number, mod_storage_save_number)
        end
        local okV, variants = pcall(require, "jimmie_dialog_variants")
        local okD, boxes = pcall(require, "jimmie_dialogs")
        if okV and okD and type(variants) == "table" and type(boxes) == "table" then
            JIMMIE_RUN.variants = variants
            for _, d in ipairs(boxes) do if variants[d[1]] then JIMMIE_RUN.rows[d[1]] = d end end
        end
    end
    -- From the second attempt of a session on, text boxes that have variants use one, in turn.
    local function retext(attempt)
        if not JIMMIE_RUN.variants or type(smlua_text_utils_dialog_replace) ~= "function" then return end
        for id, list in pairs(JIMMIE_RUN.variants) do
            local d = JIMMIE_RUN.rows[id]
            local text = attempt >= 2 and list[(attempt - 2) % #list + 1] or (d and d[5])
            if d and text then pcall(smlua_text_utils_dialog_replace, id, 1, d[2], d[3], d[4], text) end
        end
    end
    -- Changing his mode is the game's decision, not something the player typed: no chat message.
    local function set_mode(name)
        local chat = djui_chat_message_create
        djui_chat_message_create = function() end
        pcall(JIMMIE_ROUTE16.command, name)
        djui_chat_message_create = chat
    end
    local function say(row) print("[jrun] " .. Personality.json(row)) end
    local function run_update()
        local phase, ms, best, stars = jimmie_run_state()
        if phase == 1 and lastPhase ~= 1 then
            tells.begin()
            lastStars, lastVerdict = 0, nil
            JIMMIE_RUN.attempts, JIMMIE_RUN.delta = JIMMIE_RUN.attempts + 1, nil
            say({ event = "begin", best_ms = best, attempt = JIMMIE_RUN.attempts })
            retext(JIMMIE_RUN.attempts)
            if JIMMIE_RUN.attempts >= 2 and JIMMIE_BRAIN then
                pcall(JIMMIE_BRAIN.fact, "attempt", "mario", { n = JIMMIE_RUN.attempts })
            end
        end
        if phase == 2 and lastPhase == 1 then
            say({ event = "finish", ms = ms, best_ms = best, stars = stars })
            if JIMMIE_RUN.splits and lastVerdict ~= "not" then JIMMIE_RUN.splits.finish(ms <= best, jimmie_run_split) end
            flashText, flashUntil = (ms <= best and "NEW BEST " or "FINISH ") .. TELLS.clock(ms), ms + 1e12
        end
        lastPhase = phase
        if phase ~= 1 then return end
        local m, np = gMarioStates[0], gNetworkPlayers[0]
        if not m or not np then return end
        local t, level = ms / 1000, np.currLevelNum
        if stars > lastStars then
            tells.star(t, level, stars)
            JIMMIE_RUN.delta = nil
            if JIMMIE_RUN.splits and tells.verdict() ~= "not" then JIMMIE_RUN.delta = JIMMIE_RUN.splits.star(stars, jimmie_run_split(stars)) end
            flashText, flashUntil = string.format("STAR %d  %s", stars, TELLS.clock(jimmie_run_split(stars))), ms + 6000
            if JIMMIE_RUN.delta and JIMMIE_RUN.fmt then flashText = flashText .. "  " .. JIMMIE_RUN.fmt(JIMMIE_RUN.delta) end
            say({ event = "split", star = stars, ms = jimmie_run_split(stars), level = level, delta_ms = JIMMIE_RUN.delta })
            lastStars = stars
        end
        if get_global_timer() % 10 == 0 then
            local still = m.vel and math.abs(m.vel.x) < 2 and math.abs(m.vel.y) < 2 and math.abs(m.vel.z) < 2
            tells.observe(t, level, stars, still)
        end
        local verdict, why = tells.verdict()
        if verdict ~= lastVerdict then
            say({ event = "verdict", verdict = verdict, why = why, s = math.floor(t), level = level, stars = stars })
            -- Jimmie follows the decision: route companion for a run, free roam otherwise.
            if verdict == "run" then set_mode("16")
            elseif verdict == "not" then set_mode("free") end
            lastVerdict = verdict
        end
    end
    local function run_hud()
        local phase, ms, best, stars = jimmie_run_state()
        local text
        if phase == 2 and flashText then text = flashText
        elseif phase == 1 and tells.shows() then text = TELLS.clock(ms)
        else return end
        djui_hud_set_resolution(RESOLUTION_N64)
        djui_hud_set_font(FONT_NORMAL)
        local scale = 0.5
        local width = djui_hud_get_screen_width()
        local w = djui_hud_measure_text(text) * scale
        local x, y = (width - w) / 2, 4
        djui_hud_set_color(0, 0, 0, 170)
        djui_hud_print_text(text, x + 1, y + 1, scale)
        if phase == 2 then djui_hud_set_color(255, 220, 90, 255) else djui_hud_set_color(255, 255, 255, 255) end
        djui_hud_print_text(text, x, y, scale)
        if phase == 1 then
            local sub = (ms < flashUntil and flashText) or ("BEST " .. TELLS.clock(best))
            local sw = djui_hud_measure_text(sub) * 0.3
            djui_hud_set_color(0, 0, 0, 170)
            djui_hud_print_text(sub, (width - sw) / 2 + 1, y + 18, 0.3)
            -- A split is green when ahead of the reference, red when behind; everything else gold.
            if ms < flashUntil and JIMMIE_RUN.delta then
                if JIMMIE_RUN.delta < 0 then djui_hud_set_color(110, 230, 120, 255) else djui_hud_set_color(240, 110, 100, 255) end
            else djui_hud_set_color(255, 220, 90, 255) end
            djui_hud_print_text(sub, (width - sw) / 2, y + 17, 0.3)
        end
        djui_hud_reset_color()
    end
    hook_event(HOOK_UPDATE, function() pcall(run_update) end)
    hook_event(HOOK_ON_HUD_RENDER, function() pcall(run_hud) end)
    print("[jrun] ready")
end

end)()
