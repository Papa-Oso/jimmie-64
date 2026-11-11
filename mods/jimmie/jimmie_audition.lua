-- jimmie_audition.lua
-- Owner-approved reversible audition demo (2026-11-08). DEFAULT OFF.
-- Plays the three approved beats' installed clips only; no movement/model/save changes.
-- Enable/disable via chat command "/jimmie audition on|off"; preview "/jimmie audition 1|2|3".
-- Rollback: restore the saved mod folder from .jimmie-audition-backup-20261108.
local A = { VERSION = "0.1-audition", enabled = false }
local deps = {}

local CLIPS = {
    castle_door = { file = "catchphrase_03.ogg", label = "castle-door greeting", text = "What's happening, guys?" },
    star_hype = { file = "catchphrase_01.ogg", label = "star hype", text = "Holy shit!" },
    bowser_entrance = { file = "boss_bowser_01.ogg", label = "final-Bowser entrance hype", text = "Let's go fuck Bowser." },
}
local cache = {}

local function log(msg)
    if deps.log ~= nil then pcall(deps.log, msg) end
end

local function chat(msg)
    if deps.chat ~= nil then pcall(deps.chat, msg) end
end

local function load_sound(key)
    local spec = CLIPS[key]
    if spec == nil then return nil end
    if cache[key] ~= nil then return cache[key] or nil end
    local snd = nil
    if deps.load_sound ~= nil then snd = deps.load_sound(spec.file) end
    cache[key] = snd or false
    return snd
end

function A.init(options)
    deps = options or {}
    A.enabled = false
    log("[audition] module loaded; default OFF (chat: audition on/off, audition 1|2|3)")
    return A
end

function A.set_enabled(value)
    A.enabled = (value == true)
    chat("audition: " .. (A.enabled and "ON (trigger mode)" or "OFF"))
    return A.enabled
end

local function play(key, why)
    local spec = CLIPS[key]
    if spec == nil then return false end
    local snd = load_sound(key)
    if snd == nil then
        chat("audition: missing sound for " .. tostring(key))
        return false
    end
    if deps.play ~= nil then pcall(deps.play, snd, 1.0) end
    log("[audition] " .. key .. " (" .. tostring(why) .. "): " .. spec.label)
    chat("audition preview: " .. spec.label .. ' — "' .. spec.text .. '"')
    return true
end

-- explicit preview (works while triggers are off; does not enable trigger mode)
function A.preview(key)
    return play(key, "preview")
end

function A.on_star()
    if A.enabled then play("star_hype", "star collected") end
end

function A.on_level(levelNum)
    if not A.enabled then return end
    if levelNum == 6 then
        play("castle_door", "castle interior entered")
    elseif levelNum == 21 then
        play("bowser_entrance", "final Bowser stage entered")
    end
end

function A.command(msg)
    if type(msg) ~= "string" then return false end
    local rest = msg:match("^audition%s*(.*)$")
    if rest == nil then rest = msg:match("^jimmie audition%s*(.*)$") end
    if rest == nil then return false end
    rest = rest:lower()
    if rest == "on" then
        A.set_enabled(true)
        return true
    elseif rest == "off" then
        A.set_enabled(false)
        return true
    elseif rest == "status" then
        chat("audition: " .. (A.enabled and "ON" or "OFF"))
        return true
    elseif rest == "1" or rest == "door" then
        A.preview("castle_door")
        return true
    elseif rest == "2" or rest == "star" then
        A.preview("star_hype")
        return true
    elseif rest == "3" or rest == "bowser" then
        A.preview("bowser_entrance")
        return true
    elseif rest == "on" or rest == "" then
        chat("audition usage: audition on|off|status|1|2|3")
        return true
    end
    return false
end

function A.status()
    return { enabled = A.enabled, clips = (function()
        local n = 0
        for _ in pairs(CLIPS) do n = n + 1 end
        return n
    end)() }
end

return A
