-- Is this a 16-star run, or is the player just playing?
--
-- The game program times every new save file from the moment it is chosen. This module watches
-- three tells in the first minutes and decides whether the clock should stay on screen:
--
--   door    Mario goes inside the castle soon after starting
--   course  the first painting he jumps into is one the 16-star route opens with
--   star    his first star comes quickly, in one of those courses
--
-- Owner's rule (2026-11-10): miss all three and the clock stops; one tell missed badly enough
-- stops it on its own. Hit any tell and it is a run. Stopping only hides the clock: the game
-- program keeps timing, so a real run is never lost to a wrong guess.
--
-- Pure logic, no engine calls: the caller feeds it time, place and star count. Times in seconds.
local M = {}

M.DEFAULTS = {
    castle_level = 6,                         -- inside the castle
    route_courses = { [9] = true, [24] = true, [5] = true },   -- Bob-omb Battlefield, Whomp's Fortress, Cool Cool Mountain
    course_levels = { [4]=true,[5]=true,[7]=true,[8]=true,[9]=true,[10]=true,[11]=true,[12]=true,[13]=true,
                      [14]=true,[15]=true,[22]=true,[23]=true,[24]=true,[36]=true },   -- the fifteen main courses
    door  = { by = 40,  bad = 150 },          -- inside the castle within 40 s; not inside by 150 s is a bad miss
    course = { by = 90, bad = 300 },          -- in a route course within 90 s; none by 300 s, or a different course first, is a bad miss
    star  = { by = 240 },                     -- first star within 240 s; a first star anywhere else is a bad miss
    idle_bad = 60,                            -- standing still this long before the first star is a bad miss
}

local function copy(t)
    local out = {}
    for k, v in pairs(t) do out[k] = type(v) == "table" and copy(v) or v end
    return out
end

function M.new(options)
    local cfg = copy(M.DEFAULTS)
    for k, v in pairs(options or {}) do cfg[k] = v end
    local self = {}
    local started, verdict, reason
    local tell = {}                           -- name -> "hit" | "miss"
    local idleSince, firstCourse, beenInside

    local function decide(v, why)
        if verdict == nil then verdict, reason = v, why end
    end

    local function settle()
        if verdict then return end
        local hits, open = 0, 0
        for _, name in ipairs({ "door", "course", "star" }) do
            if tell[name] == "hit" then hits = hits + 1 elseif tell[name] == nil then open = open + 1 end
        end
        if open == 0 then
            if hits == 0 then decide("not", "missed all three tells") else decide("run", hits .. " of 3 tells") end
        end
    end

    -- A new timed attempt began.
    function self.begin()
        started, verdict, reason, tell, idleSince, firstCourse, beenInside = 0, nil, nil, {}, nil, nil, nil
    end

    -- Called a few times a second. t = seconds since the attempt began; still = Mario is not moving.
    function self.observe(t, level, stars, still)
        if not started or verdict then return end
        if tell.door == nil then
            if level == cfg.castle_level and t <= cfg.door.by then tell.door = "hit"
            elseif t > cfg.door.by then tell.door = "miss" end
        end
        if level == cfg.castle_level or cfg.course_levels[level] then beenInside = true end
        if not beenInside and t > cfg.door.bad then return decide("not", "never went into the castle") end
        if cfg.course_levels[level] and not firstCourse then
            firstCourse = level
            if cfg.route_courses[level] then
                if tell.course == nil and t <= cfg.course.by then tell.course = "hit" end
            else
                return decide("not", "first course is not on the route")
            end
        end
        if tell.course == nil and t > cfg.course.by then tell.course = "miss" end
        if not firstCourse and t > cfg.course.bad then return decide("not", "no course entered") end
        if tell.star == nil and stars == 0 and t > cfg.star.by then tell.star = "miss" end
        if stars == 0 then
            if still then
                idleSince = idleSince or t
                if t - idleSince > cfg.idle_bad then return decide("not", "stood still too long") end
            else
                idleSince = nil
            end
        end
        settle()
    end

    -- Mario collected a star. level = where.
    function self.star(t, level, stars)
        if not started or verdict or stars ~= 1 then return end
        if not cfg.route_courses[level] then return decide("not", "first star is not on the route") end
        if tell.star == nil then tell.star = t <= cfg.star.by and "hit" or "miss" end
        if tell.door == nil then tell.door = "miss" end
        if tell.course == nil then tell.course = "miss" end
        settle()
    end

    -- "watching" until decided, then "run" or "not". The clock shows while watching or run.
    function self.verdict() return verdict or (started and "watching" or "idle"), reason end
    function self.tells() return { door = tell.door, course = tell.course, star = tell.star } end
    function self.shows() return started ~= nil and verdict ~= "not" end
    return self
end

-- mm:ss.cc for the screen.
function M.clock(ms)
    if type(ms) ~= "number" or ms < 0 then return "--:--.--" end
    local cs = math.floor(ms / 10)
    return string.format("%02d:%02d.%02d", math.floor(cs / 6000), math.floor(cs / 100) % 60, cs % 100)
end

return M
