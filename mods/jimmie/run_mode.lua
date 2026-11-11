-- run_mode.lua: decide whether this session is a speedrun attempt.
--
-- Owner rule (2026-11-06): measure the time from spawn in the Castle Grounds
-- (level 16 area 1) to entering the castle door / interior (level 16 area 2).
-- If that time is within WINDOW seconds, the session is a speedrun and speedrun
-- systems (route backseating, route coach, run payoffs) are enabled. Otherwise the
-- session defaults to normal play and those systems stay off.
--
-- Default is deliberately conservative: until the door crossing is observed the
-- mode is "unknown", which callers treat as normal play. The module is read-only:
-- no saves, no Mario state, no audio, no input.

local RM = {}
RM.VERSION = 1
RM.DEFAULT_WINDOW = 20.0

local window = RM.DEFAULT_WINDOW
local mode = "unknown"      -- unknown | speedrun | normal
local spawnAt = nil
local decided = false
local forced = nil
local logFn = nil
local lastLevel, lastArea = nil, nil

function RM.log(message)
    local line = "[jimmie] [runmode] " .. tostring(message)
    if logFn ~= nil then
        pcall(logFn, line)
    elseif type(print) == "function" then
        print(line)
    end
end

-- Injectable for deterministic tests: {log=fn, window=seconds}.
function RM.setup(options)
    options = options or {}
    if options.log ~= nil then logFn = options.log end
    if options.window ~= nil then window = math.max(0.5, tonumber(options.window) or window) end
    return RM
end

function RM.setWindow(seconds)
    window = math.max(0.5, tonumber(seconds) or window)
    RM.log(string.format("window=%.1fs", window))
    return window
end

function RM.mode()
    return mode
end

function RM.isSpeedrun()
    return mode == "speedrun"
end

function RM.isNormal()
    return mode == "normal"
end

function RM.status()
    return { mode = mode, window = window, spawn = spawnAt, decided = decided,
             forced = forced, last_level = lastLevel, last_area = lastArea }
end

-- QA override; force(nil) returns to automatic detection from a clean state.
function RM.force(value)
    if value == nil then
        forced, mode, spawnAt, decided = nil, "unknown", nil, false
        RM.log("force=auto")
        return mode
    end
    if value ~= "speedrun" and value ~= "normal" then return mode end
    forced, mode, decided = value, value, true
    RM.log("force=" .. tostring(value))
    return mode
end

function RM.reset()
    mode, spawnAt, decided, forced = "unknown", nil, false, nil
    return mode
end

-- Observe the current scene. Call once per frame (or on scene changes) with the
-- level id, area index and a monotonic time in seconds.
function RM.observe(level, area, t)
    if forced ~= nil or decided then return mode end
    level, area = tonumber(level) or 0, tonumber(area) or 0
    t = tonumber(t) or 0
    if level ~= lastLevel or area ~= lastArea then
        RM.log(string.format("scene level=%s area=%s t=%.2f",
            tostring(level), tostring(area), t))
        lastLevel, lastArea = level, area
    end
    local inGrounds = level == 16 and area == 1     -- LEVEL_CASTLE_GROUNDS
    local inInterior = level == 6 and area == 1     -- LEVEL_CASTLE (1F / basement)
    if inGrounds then
        if spawnAt == nil then
            spawnAt = t
            RM.log(string.format("timing start t=%.2f", t))
        end
        return mode
    end
    if inInterior then
        if spawnAt ~= nil then
            local elapsed = t - spawnAt
            mode = elapsed <= window and "speedrun" or "normal"
            decided = true
            RM.log(string.format("decided mode=%s elapsed=%.2fs window=%.1fs",
                mode, elapsed, window))
        end
        return mode
    end
    -- Left the castle route before the door: a speedrun start is off the table.
    if spawnAt ~= nil then
        mode = "normal"
        decided = true
        RM.log(string.format("left castle route at level=%s area=%s -> normal",
            tostring(level), tostring(area)))
    end
    return mode
end

return RM
