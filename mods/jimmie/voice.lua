-- One positional voice channel: event selection, timing, callbacks and telemetry.
-- Funny material competes as eligible choices, not unreachable fallback entries.
local V = {
    ready = false, mode = "companion", context = {}, debug = true,
    lastGlobal = -999, lastByCat = {}, lastByClip = {}, lastByPhrase = {},
    played = 0, quietUntil = -999, busyUntil = -999,
    idleTime = 0, afk = false, runHold = 0, calmHold = 0,
    queue = {}, registered = {}, serial = 0, currentPriority = 0,
    DEFAULT_CAT_GAP = 7, CLIP_REPEAT_GAP = 30, MAX_QUEUE = 6,
    MARIO_PAYOUT_CHANCE = 0.25, MARIO_PAYOUT_GAP = 60,
    lastPayoutClip = nil,
    activePlay = false, activePlays = {}, lastActive = -999, preference = nil,
    lastWater = -999, WATER_GAP = 60, waterSubjects = {},
    lastRoutineReaction = -999, ROUTINE_REACTION_GAP = 16,
    ACTIVE_GAP = 12, ACTIVE_WINDOW = 60, ACTIVE_LIMIT = 3, MAMA_MIA_GAP = 6,
}
local okc, contexts = pcall(require, "clip_contexts")
local okr, registry = pcall(require, "speech_registry")
V.CTX = okc and contexts or {}
V.REGISTRY = okr and registry or {}
-- Generated eligibility data: fragments/silent/owner-rejected clips are unavailable
-- for selection. Audio files are untouched. Missing module = no filtering.
local okEligibility, eligibility = pcall(require, "clip_eligibility")
V.ELIGIBILITY = okEligibility and eligibility or {}
V.performanceScope = require("performance_scope").new(require("performance_rules"))
local function clip_unavailable(name)
    return name ~= nil and V.ELIGIBILITY[name] ~= nil
end
local WaterReaction = require("water_reaction")
V.waterObserver = WaterReaction.new()
V.modeCfg = {
    companion = { gap = 4.2 }, run = { gap = 3.2 }, silent = { gap = math.huge },
}
V.catGap = {
    idle = 18, roast = 16, catchphrase = 12, chat = 12, special = 40, mv_mama_mia = 6,
    chase_near = 14, chase_mid = 12, chase_far = 10, chase_abandoned = 20,
    reunion = 18, respawn = 8, star = 8, level_enter = 20, level_exit = 10,
    vest_yes = 10, vest_no = 10, bet_win = 10, bet_lose = 10,
    boss_bowser = 25, peach_castle = 60, pipe_go = 20, run_mode = 20, real_pink_bitch = 60, real_goo = 90,
}

-- Each weight is for a category, not multiplied by its number of clips.
local POOLS = {
    water_enter = { {"real_honey_oil", 1} },
    -- Active play gets personality between actual reactions; no stationary-only
    -- "I'm waiting" lines, invented outcomes or location claims enter this bank.
    active_play = { {"catchphrase", 4}, {"roast", 2}, {"real_carrier", 2},
        {"real_honey_oil", 2}, {"real_boing_boing", 2}, {"real_swa_swa", 1},
        {"real_unreal", 1}, {"real_whats_happening", 1}, {"real_pink_bitch", 2} },
    idle_long = { {"idle", 1}, {"roast", 3}, {"catchphrase", 3},
        {"real_unreal", 1}, {"real_carrier", 1}, {"real_honey_oil", 1},
        {"real_swa_swa", 1}, {"real_gub_gub", 1}, {"real_boing_boing", 1}, {"real_pink_bitch", 2}, {"real_goo", 1} },
    reunion = { {"reunion", 3}, {"real_whats_happening", 2}, {"real_good_morning", 1},
        {"catchphrase", 2}, {"roast", 1} },
    level_enter = { {"level_enter", 3}, {"real_good_morning", 1}, {"catchphrase", 2}, {"roast", 1} },
    greet = { {"real_good_morning", 3}, {"real_whats_happening", 2}, {"catchphrase", 2} },
    mario_hurt = { {"roast", 3}, {"real_unbelievable", 2}, {"real_unreal", 1}, {"real_holy_shit", 1}, {"catchphrase", 3} },
    boss_bowser = { {"boss_bowser", 1} },
    castle_enter = { {"peach_castle", 1} },
    peach_castle = { {"peach_castle", 1} },
    vest_yes = { {"vest_yes", 3}, {"vest_bets", 1} },
    vest_no = { {"vest_no", 3}, {"vest_bets", 1} },
    chase_near = { {"chase_near", 3}, {"real_come_on", 2}, {"catchphrase", 2}, {"roast", 1} },
    chase_mid = { {"chase_mid", 3}, {"real_come_on", 2}, {"real_unbelievable", 1}, {"catchphrase", 2}, {"roast", 1} },
    chase_far = { {"chase_far", 3}, {"real_come_on", 2}, {"real_no_no_no", 1}, {"catchphrase", 2}, {"roast", 1} },
    chase_board = { {"skateboard", 3}, {"real_come_on", 2}, {"real_unbelievable", 1}, {"catchphrase", 2}, {"roast", 1} },
    trick_ollie = { {"trick_ollie", 2}, {"real_lets_go", 2}, {"real_holy_shit", 1}, {"catchphrase", 3}, {"skate_tricks", 2} },
    trick_kickflip = { {"trick_kickflip", 3}, {"real_holy_shit", 2}, {"real_lets_go", 2}, {"catchphrase", 3}, {"skate_tricks", 2} },
    trick_attempt = { {"skate_tricks", 4}, {"real_come_on", 1}, {"catchphrase", 3}, {"roast", 1} },
    trick_bail = { {"trick_bail", 3}, {"real_unbelievable", 2}, {"real_no_no_no", 2}, {"real_unreal", 1}, {"real_holy_shit", 1}, {"real_pink_bitch", 1}, {"catchphrase", 3}, {"roast", 2}, {"skate_tricks", 3} },
    star = { {"star", 3}, {"real_lets_go", 2}, {"real_holy_shit", 1}, {"catchphrase", 3} },
    respawn = { {"respawn", 3}, {"real_unbelievable", 2}, {"real_unreal", 2}, {"catchphrase", 2}, {"skate_tricks", 2} },
    chat_reaction = { {"chat", 3}, {"roast", 1}, {"real_thank_you_guys", 1} },
}
local AMBIENT = { active_play = true, idle_long = true, idle = true, roast = true, catchphrase = true }
local ROUTINE_TRICK = {trick_attempt = true, trick_ollie = true, trick_kickflip = true}
-- Planning may anticipate these recorded reactions, but never posts the event.
-- Death payouts and the source-triggered Mario echo are outside model control.
local PLANNABLE = { active_play = true, trick_attempt = true, trick_ollie = true,
    trick_kickflip = true, trick_bail = true, chase_near = true, chase_mid = true,
    chase_far = true, chase_board = true, reunion = true, mario_hurt = true, star = true }
local TAGS = {
    active_play = { nonsense = true, deadpan = true },
    idle_long = { nonsense = true, deadpan = true },
    reunion = { greet = true }, level_enter = { greet = true },
    greet = { greet = true }, mario_hurt = { deadpan = true }, boss_bowser = { deadpan = true },
    star = { hype = true }, trick_ollie = { hype = true }, trick_kickflip = { hype = true },
    trick_attempt = { attempt = true }, trick_bail = { deadpan = true }, respawn = { deadpan = true },
    level_exit = { signoff = true },
}

local function log(status, event, reason, extra)
    if V.log then V.log(string.format("[voice] %s event=%s reason=%s%s", status,
        tostring(event), tostring(reason), extra and (" " .. extra) or "")) end
end

local function is_death(event)
    return event:match("^death_") ~= nil or event == "game_over"
end

local function is_setback(event)
    return is_death(event) or event == "trick_bail"
end

local function routine_reaction(event)
    return ROUTINE_TRICK[event] == true or event:match("^chase_") ~= nil
end

function V.init(clips, playFn, posFn, nowFn, logFn, loadPoolFn)
    V.CLIPS, V.play, V.pos, V.now, V.log, V.loadPool = clips, playFn, posFn, nowFn, logFn, loadPoolFn
    V.ready = true
    log("ready", "init", "duration-aware-single-channel")
end

function V.register(snd, filename)
    if snd == nil then return end
    local name = tostring(filename):gsub("\\", "/"):match("([^/]+)$")
    V.registered[snd] = { name = name, meta = V.REGISTRY[name] or {} }
end

local function info(snd, key)
    local r = V.registered[snd]
    if r then return r.name, r.meta end
    -- ModAudio.filepath exists in the engine; mocks may use string handles.
    local ok, path = pcall(function() return snd.filepath end)
    if ok and path then
        V.register(snd, path)
        r = V.registered[snd]
        return r.name, r.meta
    end
    return key, {}
end

local function ctx_allowed(cat,event)
    if cat=="peach_castle" and event=="castle_enter" then return V.context.castle_interior==true end
    local spec = V.CTX[cat]
    if not spec or not spec.contexts or #spec.contexts == 0 then return true end
    for _, c in ipairs(spec.contexts) do if V.context[c] then return true end end
    return false
end

function V.setContext(key) V.context[key] = true end
function V.clearContext(key) V.context[key] = nil end
function V.hasContext(key) return V.context[key] == true end
function V.setActivePlay(active) V.activePlay = active == true end
function V.busy() return V.now ~= nil and V.now() < V.busyUntil end

-- A companion skating away from a stationary player is not a player chase.
-- Read Mario's real velocity again when a queued complaint reaches playback.
function V.marioMoving()
    local m = gMarioStates and gMarioStates[0]
    local vel = m and m.vel
    local x, z = vel and vel.x, vel and vel.z
    return type(x) == "number" and type(z) == "number" and x == x and z == z and
        math.abs(x) < math.huge and math.abs(z) < math.huge and x * x + z * z >= 9
end

local function unDuck()
    if V.duckUntil then
        pcall(seq_player_unlower_volume, 0, 12)
        pcall(seq_player_unlower_volume, 3, 12)
        V.duckUntil = nil
    end
end

function V.clearScene(preserveSourceEcho,finishSound)
    V.waterObserver = WaterReaction.new()
    V.waterSubjects = {}
    -- The actual Mario call may straddle a death/level transition. Only callers
    -- explicitly suspending gameplay can retain this short-lived response;
    -- off/silent mode and ordinary scene clearing remain absolute.
    local echoes = {}
    if preserveSourceEcho == true and V.now then
        local t = V.now()
        for _, pending in ipairs(V.queue) do
            if pending.event == "mario_mama_mia" and t <= pending.expires then
                echoes[#echoes + 1] = pending -- keep the original expiry/cue time
            end
        end
    end
    local keep=finishSound~=nil and finishSound==V.currentSnd and V.currentEvent=="star" and V.busy()
    V.keptDanceSound=keep and finishSound or nil
    if V.currentSnd and not keep then
        pcall(audio_sample_stop,V.currentSnd)
        if V.onStopped then pcall(V.onStopped,V.currentEvent,"scene-cleared") end
    end
    if not keep then
        V.currentSnd, V.currentPriority = nil, 0
        V.currentEvent,V.currentValid,V.currentInterruptible=nil,nil,false
    end
    V.queue, V.context, V.setback, V.trickSetup = echoes, {}, nil, nil
    V.preference = nil
    V.quietUntil=-999
    V.idleTime, V.afk, V.activePlay = 0, false, false
    if not keep then V.busyUntil=-999;unDuck() end
end

function V.setMode(mode)
    if not V.modeCfg[mode] then return end
    V.mode = mode
    if mode == "silent" then V.clearScene() end
end

-- Retained for callers that reserve the channel without playback. Never shortens a lock.
function V.claim(seconds)
    if V.now then V.busyUntil = math.max(V.busyUntil, V.now() + (seconds or 6)) end
end

function V.autoMode(dt, speed)
    if V.mode == "silent" then return end
    V.idleTime = speed < 3 and (V.idleTime + dt) or 0
    V.afk = V.idleTime > 15
    if speed > 28 then
        V.runHold, V.calmHold = math.min(2.1, V.runHold + dt), 0
    elseif speed < 8 then
        V.calmHold, V.runHold = math.min(3.1, V.calmHold + dt), 0
    end
    if V.mode == "companion" and V.runHold > 2 then
        V.setMode("run"); V.runHold = 0
    elseif V.mode == "run" and V.calmHold > 3 then
        V.setMode("companion"); V.calmHold = 0
    end
end

local function pools_for(event, detail)
    if event == "mario_mama_mia" then return {{"mv_mama_mia", 1}} end
    if is_death(event) then
        local result = { {event, 4}, {"death_generic", 1}, {"real_unbelievable", 2},
            {"real_no_no_no", 2}, {"real_unreal", 1}, {"real_holy_shit", 1},
            {"real_shit_it_down", 1}, {"catchphrase", 3}, {"roast", 2} }
        -- Forced death reactions normally bypass category cooldowns. Payout
        -- must retain its own hard cooldown, committed only by actual playback.
        if event == "death_mario" and
            V.now() - (V.lastByCat.real_pay_em_out or -999) >= V.MARIO_PAYOUT_GAP then
            result[#result + 1] = {"real_pay_em_out", 1}
        end
        if event == "death_board" or event == "death_fall" then
            local setup = V.trickSetup and V.now() <= V.trickSetup.expires
            result[#result + 1] = {"trick_bail", setup and 6 or 3}
            result[#result + 1] = {"skate_tricks", 3}
        end
        return result
    end
    if event == "respawn" and not (V.setback and V.now() <= V.setback.expires) then
        return { {"respawn", 1}, {"skate_tricks", 1} }
    end
    if detail.exact then return { {event, 1} } end
    if event == "active_play" then
        local result = {}
        for _, entry in ipairs(POOLS.active_play) do result[#result + 1] = entry end
        -- Existing nearby-character lines remain tied to their actual context.
        if V.context.boss then result[#result + 1] = {"boss_bowser", 3} end
        if V.context.peach then result[#result + 1] = {"peach_castle", 2} end
        return result
    end
    if POOLS[event] then return POOLS[event] end
    local result = {}
    for _, cat in ipairs(detail.cats or {event}) do result[#result + 1] = {cat, 1} end
    return result
end

local function tag_allowed(event, cat, meta)
    for _, tag in ipairs(meta.tags or {}) do if tag == "excluded" then return false end end
    for _, tag in ipairs(meta.tags or {}) do
        if tag == "idle_only" then
            local m = gMarioStates and gMarioStates[0]
            local vel = m and m.vel
            if event ~= "idle_long" or not vel or type(vel.x) ~= "number" or type(vel.z) ~= "number" or
                not (math.abs(vel.x) < 2 and math.abs(vel.z) < 2) then return false end
        end
    end
    if event == "mario_mama_mia" then
        return cat == "mv_mama_mia" and meta.phrase == "mama_mia"
    end
    local registryEvent = event
    if event == "active_play" then
        for _, tag in ipairs(meta.tags or {}) do if tag == "idle_only" then return false end end
        -- Neutral signatures were filed under idle_long although their words do
        -- not require Mario to stand still. Specific outcomes/claims stay gated.
        local neutral = false
        for _, tag in ipairs(meta.tags or {}) do
            if tag == "nonsense" or tag == "deadpan" then neutral = true end
        end
        if (cat == "catchphrase" or cat:match("^real_")) and neutral then
            registryEvent = "idle_long"
        elseif cat == "roast" and meta.phrase == "i_know_this_map_better_than_you" then
            registryEvent = "idle_long"
        elseif cat == "boss_bowser" and V.context.boss then
            registryEvent = "boss_bowser"
        elseif cat == "peach_castle" and V.context.peach then
            registryEvent = "peach_castle"
        else return false end
    end
    if meta.events then
        local matches = false
        for _, allowed in ipairs(meta.events) do
            if registryEvent == allowed or (allowed:sub(-1) == "*" and
                registryEvent:sub(1, #allowed - 1) == allowed:sub(1, -2)) then matches = true; break end
        end
        if not matches then return false end
    end
    if cat ~= "catchphrase" then return true end
    -- Broad catchphrase packs include greetings, signoffs and world-record claims.
    -- Only explicitly tagged lines can enter generic gameplay pools.
    local allowed = TAGS[event] or (event:match("^chase_") and {deadpan = true, attempt = true}) or
        (is_death(event) and {deadpan = true}) or {}
    for _, tag in ipairs(meta.tags or {}) do if allowed[tag] then return true end end
    return false
end

local function near_enough(item)
    if V.distance == nil then return true end
    local ok, distance = pcall(V.distance)
    if not ok or type(distance) ~= "number" then return false end
    local range = item.maxDistance or (AMBIENT[item.event] and 700 or
        (item.event:match("^chase_") and 2200 or 1400))
    return distance <= range
end

-- Category count is not a creative preference. Archive phrases occupy many
-- small categories; authored AI performances occupy a few large banks. Keep
-- each source's strongest eligible context weight, then distribute it across
-- its eligible categories. This is not a fixed playback ratio or an approval
-- of any recording. Existing eligibility, event and cooldown gates run first.
local function balanced_groups(groups)
    local result, totals, peaks = {}, {}, {}
    for _, group in ipairs(groups) do
        local buckets, order = {}, {}
        for _, clip in ipairs(group.clips) do
            local source = clip.meta.source
            if source ~= "authored" and source ~= "real_vod" then source = "unknown" end
            if not buckets[source] then buckets[source] = {}; order[#order + 1] = source end
            buckets[source][#buckets[source] + 1] = clip
        end
        for _, source in ipairs(order) do
            -- Split a mixed category without giving it extra total weight.
            local weight = group.weight * #buckets[source] / #group.clips
            result[#result + 1] = {cat = group.cat, source = source,
                weight = weight, clips = buckets[source]}
            totals[source] = (totals[source] or 0) + weight
            peaks[source] = math.max(peaks[source] or 0, weight)
        end
    end
    for _, group in ipairs(result) do
        group.weight = group.weight * peaks[group.source] / totals[group.source]
    end
    return result
end

-- Equal access to the finite menu is not equal playback. Rotate takes and
-- categories inside each source lane, then interleave those lanes. Lua still
-- revalidates every chosen recording at its actual event; the model may choose
-- either source or silence. Unknown provenance is never relabelled as authored.
local function candidate_menu(groups, turn)
    local lanes, order, offsets, result = {}, {}, {}, {}
    for n = 1, #groups do
        local group = groups[(turn + n - 1) % #groups + 1]
        local source = group.source or "unknown"
        if not lanes[source] then lanes[source] = {}; order[#order + 1] = source; offsets[source] = 1 end
        lanes[source][#lanes[source] + 1] = group
    end
    local flattened = {}
    for _, source in ipairs(order) do
        local clips, round, added = {}, 0, true
        while added and #clips < 10 do
            added = false
            for _, group in ipairs(lanes[source]) do
                if round < #group.clips then
                    local clip = group.clips[(turn + round) % #group.clips + 1]
                    clips[#clips + 1] = {clip = clip.key, category = group.cat,
                        phrase = clip.phrase, text = clip.meta.text or "",
                        source = clip.meta.source, text_status = clip.meta.text_status,
                        seconds = tonumber(clip.meta.seconds) or 6}
                    added = true
                    if #clips == 10 then break end
                end
            end
            round = round + 1
        end
        flattened[source] = clips
    end
    while #result < 10 do
        local added = false
        for _, source in ipairs(order) do
            local clip = flattened[source][offsets[source]]
            if clip then
                result[#result + 1] = clip; offsets[source] = offsets[source] + 1; added = true
                if #result == 10 then break end
            end
        end
        if not added then break end
    end
    return result
end

local function choices(item, t)
    if item.snd and not V.performanceScope.allows(V.performanceScope.sound_name(item.snd, info(item.snd)), item.event, item.performanceGrant) then return {} end
    if item.snd then return {{cat = "live", weight = 1, clips = {
        {snd = item.snd, key = item.key, phrase = item.key,
         meta = {seconds = item.seconds, text = item.text}} }}} end
    local result, seen = {}, {}
    for _, spec in ipairs(pools_for(item.event, item.detail)) do
        local cat, weight = spec[1], spec[2]
        if not seen[cat] and ctx_allowed(cat,item.event) and
            (item.force or t - (V.lastByCat[cat] or -999) >= (V.catGap[cat] or V.DEFAULT_CAT_GAP)) then
            seen[cat] = true
            local pool = V.loadPool and V.loadPool(cat) or (V.CLIPS and V.CLIPS[cat]) or {}
            local eligible = {}
            for idx, snd in ipairs(pool) do
                local key, meta = info(snd, cat .. ":" .. idx)
                local phrase = meta.phrase or key
                local unavailable = clip_unavailable(key) or not V.performanceScope.allows(V.performanceScope.sound_name(snd,key), item.event, item.detail and item.detail.performanceGrant)
                local callback = is_setback(item.event) and V.setback and
                    V.setback.phrase == phrase and V.setback.repeats == 0 and
                    t - V.setback.t >= 4 and t <= V.setback.expires
                -- This recognizable call-and-response is tied to a real Mario
                -- sound, not generic chatter. Its own six-second guard permits
                -- another genuine call without waiting the generic 30 seconds.
                local echo = item.event == "mario_mama_mia" and phrase == "mama_mia" and
                    t - (V.lastByPhrase[phrase] or -999) >= V.MAMA_MIA_GAP
                if (not item.detail.clip or key == item.detail.clip) and
                    not unavailable and
                    tag_allowed(item.event, cat, meta) and
                    (callback or echo or t - (V.lastByPhrase[phrase] or -999) >= V.CLIP_REPEAT_GAP) and
                    (callback or echo or t - (V.lastByClip[key] or -999) >= V.CLIP_REPEAT_GAP) then
                    eligible[#eligible + 1] = {snd = snd, key = key, phrase = phrase,
                        meta = meta, callback = callback}
                end
            end
            if cat == "real_honey_oil" and item.event == "water_enter" then
                -- The complete source question is the water punchline; older
                -- short takes remain a fallback if it is temporarily unavailable.
                for _, candidate in ipairs(eligible) do
                    if candidate.key == "real_honey_oil_03.ogg" then eligible = {candidate}; break end
                end
            end
            if cat == "real_pay_em_out" and #eligible > 1 and V.lastPayoutClip then
                -- Alternate valid performances when several are available.
                for i = #eligible, 1, -1 do
                    if eligible[i].key == V.lastPayoutClip then table.remove(eligible, i) end
                end
            end
            if #eligible > 0 then result[#result + 1] = {cat = cat, weight = weight, clips = eligible} end
        end
    end
    if item.event == "death_mario" then
        for i, group in ipairs(result) do
            if group.cat == "real_pay_em_out" then
                -- Roll only once per eligible event, after all normal validity
                -- checks. Missing/repeated takes fall back to the normal bank.
                if item.payoutRoll == nil then item.payoutRoll = math.random() end
                if item.payoutRoll < V.MARIO_PAYOUT_CHANCE then return {group} end
                table.remove(result, i)
                break
            end
        end
    end
    return balanced_groups(result)
end

local function active_budget(t)
    if not V.activePlay then return false, "inactive-play" end
    if t - V.lastActive < V.ACTIVE_GAP then return false, "active-gap" end
    local recent = 0
    for _, playedAt in ipairs(V.activePlays) do
        if t - playedAt < V.ACTIVE_WINDOW then recent = recent + 1 end
    end
    if recent >= V.ACTIVE_LIMIT then return false, "active-budget" end
    return true
end

local function attempt(item)
    local t = V.now()
    if V.mode == "silent" then return false, "silent", false end
    if t > item.expires then return false, "expired", false end
    if item.event:match("^chase_") and not V.marioMoving() then return false, "player-not-moving", false end
    if routine_reaction(item.event) and t - V.lastRoutineReaction < V.ROUTINE_REACTION_GAP then
        local landing = item.event == "trick_ollie" or item.event == "trick_kickflip"
        local finishingSetup = landing and V.trickSetup and t <= V.trickSetup.expires
        if not finishingSetup then return false, "routine-reaction-cooldown", false end
    end
    if item.event == "water_enter" and t - V.lastWater < V.WATER_GAP then return false, "water-cooldown", false end
    if item.valid then
        local ok,current=pcall(item.valid)
        if not ok or current~=true then return false,"context-changed",false end
    end
    if t < (item.notBefore or -999) then return false, "waiting-for-cue", true end
    -- Mario's source sound can arrive just before the companion's brief death
    -- despawn. Preserve that response until respawn, but still enforce actual
    -- proximity once an audio position exists and never extend its original TTL.
    if item.event == "mario_mama_mia" and V.available then
        local ok, available = pcall(V.available)
        if not ok or not available then return false, "companion-unavailable", true end
    end
    if not near_enough(item) then return false, "distance", false end
    if AMBIENT[item.event] and V.holdsArrivalVoice and V.holdsArrivalVoice() then
        return false,"entrance-reserved",false
    end
    if V.afk and AMBIENT[item.event] then return false, "afk", false end
    if item.event == "active_play" then
        local allowed, reason = active_budget(t)
        if not allowed then return false, reason, false end
    end
    if not item.force and t < V.quietUntil then return false, "post-death-quiet", true end
    local important=item.event=="star" or item.event=="mario_hurt" or item.event=="boss_bowser" or
        item.event=="respawn" or item.event=="mario_mama_mia" or is_death(item.event)
    local canInterruptRoute=V.currentEvent=="route_coach" and V.currentInterruptible==true and
        important and item.priority>=65
    if V.busy() and not item.force and not canInterruptRoute then return false, "busy", true end
    local gap = AMBIENT[item.event] and 8 or V.modeCfg[V.mode].gap
    if item.priority >= 60 or item.event == "route_coach" then gap = 1.0 end
    if not item.force and t - V.lastGlobal < gap then return false, "gap", true end
    local groups = choices(item, t)
    local chosen, clip, preferenceId
    local preference = V.preference
    if preference and t > preference.expires then V.preference = nil; preference = nil end
    if preference and preference.event == item.event then
        for _, group in ipairs(groups) do
            for _, candidate in ipairs(group.clips) do
                if candidate.key == preference.clip then
                    chosen, clip, preferenceId = group, candidate, preference.id
                    break
                end
            end
            if clip then break end
        end
        -- A real matching opportunity that no longer admits the planned clip
        -- falls back normally; it cannot hold a stale line for another context.
        if not clip then V.preference = nil end
    end
    if #groups == 0 then return false, "no-eligible-clip", false end
    if not clip then
        local total = 0
        for _, group in ipairs(groups) do total = total + group.weight end
        local roll = math.random() * total
        chosen = groups[#groups]
        for _, group in ipairs(groups) do
            roll = roll - group.weight
            if roll < 0 then chosen = group; break end
        end
        clip = chosen.clips[math.random(#chosen.clips)]
    end
    local seconds = tonumber(clip.meta.seconds) or 6
    if seconds <= 0 or seconds ~= seconds then seconds = 6 end
    local grant = item.performanceGrant or (item.detail and item.detail.performanceGrant)
    local name = V.performanceScope.sound_name(clip.snd, info(clip.snd))
    if clip_unavailable(name) or not V.performanceScope.allows(name,item.event,grant) then return false,"performance-scope",false end
    -- An interruption happens only after a valid replacement is selected.
    if V.busy() and V.currentSnd then
        pcall(audio_sample_stop,V.currentSnd)
        if V.onStopped then pcall(V.onStopped,V.currentEvent,"interrupted") end
    end
    local ok, result = pcall(V.play, clip.snd, item.volume, grant, item.event)
    if not ok or result == false then return false, "playback-failed", false end
    if preferenceId then V.preference = nil end -- consume only actual successful playback
    V.currentSnd, V.currentPriority = clip.snd, item.priority
    V.currentEvent,V.currentValid=item.event,item.valid
    V.currentInterruptible=item.event=="route_coach" and item.interruptible==true
    V.busyUntil, V.duckUntil = t + seconds + 0.15, t + seconds + 0.15
    pcall(seq_player_lower_volume, 0, 6, 52)
    pcall(seq_player_lower_volume, 3, 6, 52)
    V.lastGlobal, V.lastByCat[chosen.cat] = t, t
    if routine_reaction(item.event) then V.lastRoutineReaction = t end
    if item.event == "water_enter" then V.lastWater = t end
    if item.event == "active_play" then
        local recent = {}
        for _, playedAt in ipairs(V.activePlays) do
            if t - playedAt < V.ACTIVE_WINDOW then recent[#recent + 1] = playedAt end
        end
        recent[#recent + 1] = t
        V.activePlays, V.lastActive = recent, t
    end
    if chosen.cat == "real_pay_em_out" then V.lastPayoutClip = clip.key end
    V.lastByClip[clip.key], V.lastByPhrase[clip.phrase] = t, t
    V.played = V.played + 1
    if item.event == "trick_attempt" then V.trickSetup = {expires = t + 7} end
    if is_setback(item.event) then
        local repeats = clip.callback and 1 or 0
        -- At most one deliberate callback across a short chain of real setbacks.
        if V.setback and t <= V.setback.expires then repeats = math.max(repeats, V.setback.repeats) end
        V.setback = {t = t, expires = t + 22, phrase = clip.phrase, repeats = repeats}
    end
    if is_death(item.event) then V.quietUntil = math.max(t + 2.5, V.busyUntil + 0.35) end
    if is_setback(item.event) or item.event == "trick_ollie" or item.event == "trick_kickflip" then
        V.trickSetup = nil
    end
    log("played", item.event, preferenceId and "model-preferred" or (clip.callback and "setback-callback" or "selected"),
        string.format("cat=%s clip=%s seconds=%.2f latency=%.2f%s", chosen.cat, clip.key, seconds, t - item.t,
            preferenceId and (" id=" .. preferenceId) or ""))
    if V.onPlayed then
        local meta = {}
        for key, value in pairs(clip.meta) do meta[key] = value end
        meta.name = clip.key
        pcall(V.onPlayed, meta, item.event, seconds)
    end
    if item.onPlay then pcall(item.onPlay, clip.meta.text, seconds) end
    return true, "played", false
end

local function enqueue(item, reason)
    for i, pending in ipairs(V.queue) do
        if pending.event == item.event and not item.snd then
            -- Refresh to the newest actual event, without growing the queue.
            V.queue[i] = item
            log("deferred", item.event, reason .. "-coalesced")
            return true
        end
    end
    if #V.queue >= V.MAX_QUEUE then
        local lowest = 1
        for i = 2, #V.queue do
            if V.queue[i].priority < V.queue[lowest].priority then lowest = i end
        end
        if V.queue[lowest].priority >= item.priority then
            log("dropped", item.event, "queue-full")
            return false
        end
        log("dropped", V.queue[lowest].event, "superseded")
        table.remove(V.queue, lowest)
    end
    V.queue[#V.queue + 1] = item
    log("deferred", item.event, reason)
    return true
end

local function submit(item, allowQueue)
    if V.now == nil or V.play == nil then return false end
    if JIMMIE_BRAIN and JIMMIE_BRAIN.live() then return false end
    local played, reason, retry = attempt(item)
    if played then return true end
    if allowQueue and retry then return enqueue(item, reason) end
    log("dropped", item.event, reason)
    return false
end

local function make_item(event, detail)
    detail = detail or {}
    local t = V.now()
    local death = is_death(event)
    local echo = event == "mario_mama_mia"
    local priority = detail.priority or (echo and 85 or (death and 100 or
        ((event == "star" or event == "trick_bail" or event == "respawn" or
          event == "trick_ollie" or event == "trick_kickflip" or event == "mario_hurt") and 65 or
        (AMBIENT[event] and 10 or 40))))
    local ttl = detail.ttl or (echo and 7 or (death and 1 or (event == "trick_attempt" and 0.8 or
        (AMBIENT[event] and 1.5 or 3))))
    V.serial = V.serial + 1
    return { event = event, detail = detail, volume = detail.volume or 1,
        priority = priority, t = detail.t or t, expires = (detail.t or t) + ttl,
        notBefore = detail.notBefore or (echo and t + 0.45 or t),
        force = death, serial = V.serial, maxDistance = detail.maxDistance,
        valid = type(detail.valid) == "function" and detail.valid or nil }
end

-- Observe real downward surface crossings, not every underwater frame.
-- The pure observer suppresses spawning/warping into water and brief bobbing.
function V.observeWater(kind, subject, scene, x, y, z, alive)
    if V.now == nil then return false end
    local t = V.now()
    if kind ~= "mario" and kind ~= "companion" then return false end
    local function finite(n) return type(n)=="number" and n==n and n>-math.huge and n<math.huge end
    local subjectType=type(subject)
    local valid=alive==true and (subjectType=="table" or subjectType=="userdata")
        and type(scene)=="string" and scene~="" and finite(x) and finite(y) and finite(z) and finite(t) and t>=0
    local ok, wl = false, nil
    if valid then ok, wl = pcall(find_water_level, x, z) end
    if not valid or not ok or not finite(wl) then
        V.waterSubjects[kind]=nil
        V.waterObserver:reset(kind)
        return false
    end
    local wet = wl > -10000 and y < wl - 15
    local previous = V.waterSubjects[kind]
    local continuous = previous and previous.subject == subject and previous.scene == scene and
        type(x) == "number" and type(y) == "number" and type(z) == "number" and
        type(previous.x) == "number" and type(previous.y) == "number" and type(previous.z) == "number" and
        t > previous.t and t - previous.t <= 0.2 and
        (x-previous.x)^2 + (y-previous.y)^2 + (z-previous.z)^2 <= 180^2
    local token = continuous and previous.token or {}
    V.waterSubjects[kind] = subject and alive and {subject=subject,scene=scene,wet=wet,t=t,
        x=x,y=y,z=z,token=token} or nil
    local entered = V.waterObserver:observe(kind, subject, scene, x, y, z, ok and wl or nil, t, alive)
    if entered and V.waterFact and V.waterFact(kind,subject,scene,x,y,z,wl) then return true end
    if not entered or t - V.lastWater < V.WATER_GAP then return false end
    return V.post("water_enter", {ttl=1.5, priority=40, valid=function()
        local current = V.waterSubjects[kind]
        return current ~= nil and current.subject == subject and current.scene == scene and
            current.token == token and current.wet == true and V.now() - current.t <= 0.2
    end})
end

function V.post(event, detail)
    if V.now == nil then return false end
    event = tostring(event)
    if is_death(event) then
        V.preference = nil
        -- No delayed celebration may survive a failure, even if its bark is unavailable.
        local echoes = {}
        for _, pending in ipairs(V.queue) do
            if pending.event == "mario_mama_mia" and V.now() <= pending.expires then
                echoes[#echoes + 1] = pending
            end
        end
        V.queue = echoes
        V.quietUntil = math.max(V.quietUntil, V.now() + 2.5)
    elseif event == "trick_ollie" or event == "trick_kickflip" or event == "trick_bail" then
        -- A setup may never arrive after the trick has already resolved.
        for i = #V.queue, 1, -1 do
            if V.queue[i].event == "trick_attempt" then table.remove(V.queue, i) end
        end
    end
    return submit(make_item(event, detail), true)
end

-- A bounded deterministic view of eligible active-play recordings. Inspection
-- consumes no RNG draw, event serial, queue entry or playback cooldown.
function V.candidates(event, detail)
    if event ~= "active_play" or V.now == nil or not V.ready then return {} end
    local t = V.now()
    if V.mode == "silent" or V.afk or not active_budget(t) or V.busy() or
        t < V.quietUntil or t - V.lastGlobal < 8 then return {} end
    detail = detail or {}
    local item = {event = event, detail = {}, force = false, priority = 10,
        maxDistance = math.min(700, tonumber(detail.maxDistance) or 700)}
    if not near_enough(item) then return {} end
    local groups = choices(item, t)
    local result = {}
    if #groups == 0 then return result end
    return candidate_menu(groups, math.floor(t / V.ACTIVE_GAP))
end

-- Unlike candidates(), this is a planning menu, not permission to speak now.
-- It deliberately ignores transient activity, AFK, distance, budget and channel
-- locks. Every real event still passes those gates in attempt() before any use.
function V.planCandidates(event)
    if not PLANNABLE[event] or V.now == nil or not V.ready or V.mode == "silent" then return {} end
    local t = V.now()
    local groups = choices({event = event, detail = {}, force = false}, t)
    local result = {}
    if #groups == 0 then return result end
    return candidate_menu(groups, math.floor(t / V.ACTIVE_GAP))
end

function V.preferChoice(event, clip, detail)
    if not PLANNABLE[event] or type(clip) ~= "string" or #clip > 128 or
        not clip:match("^[%w_%-]+%.ogg$") then return false end
    if detail ~= nil and type(detail) ~= "table" then return false end
    detail = detail or {}
    local id, ttl = detail.id or "model", tonumber(detail.ttl) or 12
    if type(id) ~= "string" or #id < 1 or #id > 80 or not id:match("^[%w_%-]+$") or
        ttl ~= ttl or ttl <= 0 then return false end
    for _, candidate in ipairs(V.planCandidates(event)) do
        if candidate.clip == clip then
            V.preference = {event = event, clip = clip, id = id, expires = V.now() + math.min(12, ttl)}
            return true -- acknowledgement of a plan, never playback or an event
        end
    end
    return false
end

function V.postChoice(event, clip, detail)
    if event ~= "active_play" or type(clip) ~= "string" or #clip > 128 or
        not clip:match("^[%w_%-]+%.ogg$") then return false end
    detail = detail or {}
    -- External choices narrow eligibility; they cannot force/preempt audio,
    -- forge outcomes, extend distance/TTL or load an arbitrary audio path.
    return V.post(event, {clip = clip, volume = math.max(0, math.min(1, tonumber(detail.volume) or 0.8)),
        ttl = math.max(0.1, math.min(1.5, tonumber(detail.ttl) or 1.5)),
        maxDistance = math.max(0, math.min(700, tonumber(detail.maxDistance) or 700))})
end

function V.say(cat, volume, force)
    if V.now == nil then return false end
    local item = make_item(tostring(cat), {volume = volume, exact = true})
    item.force = force == true
    return submit(item, false)
end

function V.external(snd, seconds, detail, grant)
    if snd == nil or V.now == nil then return false end
    local externalKey = info(snd)
    detail = detail or {}
    local name=V.performanceScope.sound_name(snd,externalKey)
    if clip_unavailable(name) or not V.performanceScope.allows(name,detail.event or "live_reply",grant) then return false end
    local item = make_item(detail.event or "live_reply", detail)
    item.priority, item.force = detail.priority or 80, false
    item.performanceGrant=grant
    item.snd, item.seconds, item.text = snd, seconds, detail.text
    item.key = grant and name or detail.key or ("external:" .. tostring(V.serial))
    item.onPlay = detail.onPlay
    item.valid=type(detail.valid)=="function" and detail.valid or nil
    item.interruptible=item.event=="route_coach" and detail.interruptible==true
    return submit(item, true)
end

function V.update()
    if V.now == nil then return end
    local t = V.now()
    if V.currentSnd and V.currentInterruptible and V.currentValid then
        local ok,current=pcall(V.currentValid)
        if not ok or current~=true then
            pcall(audio_sample_stop,V.currentSnd)
            if V.onStopped then pcall(V.onStopped,V.currentEvent,"context-changed") end
            V.currentSnd,V.currentPriority,V.currentEvent,V.currentValid,V.currentInterruptible=nil,0,nil,nil,false
            V.busyUntil=t
            unDuck()
        end
    end
    if V.currentSnd and t >= V.busyUntil then
        V.currentSnd,V.currentPriority,V.currentEvent,V.currentValid,V.currentInterruptible=nil,0,nil,nil,false
    end
    if V.duckUntil and t >= V.duckUntil then unDuck() end
    if V.setback and t > V.setback.expires then V.setback = nil end
    if V.preference and t > V.preference.expires then V.preference = nil end
    table.sort(V.queue, function(a, b)
        if a.priority == b.priority then return a.serial < b.serial end
        return a.priority > b.priority
    end)
    local i = 1
    while i <= #V.queue do
        local item = V.queue[i]
        local played, reason, retry = attempt(item)
        if played or not retry then
            table.remove(V.queue, i)
            if not played then log("dropped", item.event, reason) end
            if played then return end
        else
            i = i + 1
        end
    end
end

-- QA uses the same channel; it can never talk over an active line.
function V.test(cat) return V.say(cat, 1, false) end
function V.testGated(cat) return V.test(cat) end
return V
