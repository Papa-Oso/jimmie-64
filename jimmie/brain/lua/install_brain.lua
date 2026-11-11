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
