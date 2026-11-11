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
    local function say(row) print("[jrun] " .. Personality.json(row)) end
    local function run_update()
        local phase, ms, best, stars = jimmie_run_state()
        if phase == 1 and lastPhase ~= 1 then
            tells.begin()
            lastStars, lastVerdict = 0, nil
            say({ event = "begin", best_ms = best })
        end
        if phase == 2 and lastPhase == 1 then
            say({ event = "finish", ms = ms, best_ms = best, stars = stars })
            flashText, flashUntil = (ms <= best and "NEW BEST " or "FINISH ") .. TELLS.clock(ms), ms + 1e12
        end
        lastPhase = phase
        if phase ~= 1 then return end
        local m, np = gMarioStates[0], gNetworkPlayers[0]
        if not m or not np then return end
        local t, level = ms / 1000, np.currLevelNum
        if stars > lastStars then
            tells.star(t, level, stars)
            flashText, flashUntil = string.format("STAR %d  %s", stars, TELLS.clock(jimmie_run_split(stars))), ms + 4000
            say({ event = "split", star = stars, ms = jimmie_run_split(stars), level = level })
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
            if verdict == "run" then pcall(JIMMIE_ROUTE16.command, "16")
            elseif verdict == "not" then pcall(JIMMIE_ROUTE16.command, "free") end
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
            djui_hud_set_color(255, 220, 90, 255)
            djui_hud_print_text(sub, (width - sw) / 2, y + 17, 0.3)
        end
        djui_hud_reset_color()
    end
    hook_event(HOOK_UPDATE, function() pcall(run_update) end)
    hook_event(HOOK_ON_HUD_RENDER, function() pcall(run_hud) end)
    print("[jrun] ready")
end
