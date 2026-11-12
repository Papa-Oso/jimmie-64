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
    -- Owner, 2026-11-11: on a new file he does not talk until Mario has met him on the castle bridge.
    -- JIMMIE_INTRO.seen is set while that meeting is still to come; .done once he has joined (or it was skipped).
    if JIMMIE_INTRO and JIMMIE_INTRO.seen and not JIMMIE_INTRO.done then return false end
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
            JIMMIE_RUN.attempts, JIMMIE_RUN.delta, JIMMIE_RUN.t0 = JIMMIE_RUN.attempts + 1, nil, nil
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
        local level = np.currLevelNum
        -- The tells are judged from the moment the player can first move, not from file select: on a
        -- new file the opening holds Mario for about a minute, which used to read as "stood still too
        -- long" and hid the clock before play began. The clock itself still counts from file select.
        local free = ACT_GROUP_MASK == nil or (m.action & ACT_GROUP_MASK) ~= ACT_GROUP_CUTSCENE
        if not JIMMIE_RUN.t0 then
            if not free then return end
            JIMMIE_RUN.t0, JIMMIE_RUN.held, JIMMIE_RUN.last, JIMMIE_RUN.signs, JIMMIE_RUN.reading = ms, 0, ms, {}, false
        end
        -- Time held by a scene or a text box is not the player's: it is left out of the judging.
        if not free then JIMMIE_RUN.held = JIMMIE_RUN.held + (ms - JIMMIE_RUN.last) end
        JIMMIE_RUN.last = ms
        local t = (ms - JIMMIE_RUN.t0 - JIMMIE_RUN.held) / 1000
        -- Two signs for the tells. Stopping to talk to someone or read a sign around the castle (not
        -- the bridge meeting itself, and not a course, where the first star's boss talks). And meeting
        -- Jimmie on the bridge at all, which runners usually jump past.
        local pending = JIMMIE_INTRO and JIMMIE_INTRO.seen and not JIMMIE_INTRO.done
        local reading = m.action == ACT_READING_NPC_DIALOG or m.action == ACT_READING_SIGN
        if reading and not JIMMIE_RUN.reading and not pending and (level == 6 or level == 16 or level == 26) then
            JIMMIE_RUN.signs.talk = true
        end
        JIMMIE_RUN.reading = reading
        -- In the water outside the castle: no run goes there before the first star.
        if level == 16 and ACT_GROUP_SUBMERGED and (m.action & ACT_GROUP_MASK) == ACT_GROUP_SUBMERGED then JIMMIE_RUN.signs.water = true end
        if pending and not JIMMIE_RUN.signs.met and type(jimmie_intro_lakitu) == "function" then
            local okL, lak = pcall(jimmie_intro_lakitu)
            if okL and lak and lak.oAction ~= 0 then JIMMIE_RUN.signs.met = true end
        end
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
            -- Being held by a text box or a scene is not the player standing around.
            local still = free and m.vel and math.abs(m.vel.x) < 2 and math.abs(m.vel.y) < 2 and math.abs(m.vel.z) < 2
            tells.observe(t, level, stars, still, JIMMIE_RUN.signs)
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
