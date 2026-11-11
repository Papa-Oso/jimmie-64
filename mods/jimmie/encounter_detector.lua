-- encounter_detector.lua: candidate recognition state machine for the wf_wall
-- ("Cannonless", Whomp's Fortress mission 6) encounter.
--
-- PLANNING ARTIFACT. main.lua does not require this module and it is not wired to
-- any speech, audio or gameplay path. It exists so recorded frame traces can be
-- scored offline against labelled attempts before any creative audio is added.
-- The event contract follows docs/CONTEXTUAL_COMMENTARY_GOAL.md:
--   approach -> setup -> attempt -> success | setback | abandoned/unknown.
--
-- Facts the detector may not invent:
--   * region bounds are measured data (docs/cannonless-encounter-20261106/);
--   * an existing saved star is never success evidence;
--   * success needs a new course-2 star flag bit during a confirmed attempt;
--   * a failure diagnosis (late jump, bad angle) is NOT emitted - only the
--     observed result ("below-ledge", "death") is recorded as evidence text;
--   * below min_confidence the detector stays silent.
--
-- API (pure, no engine calls):
--   local ED = require("encounter_detector")
--   local d = ED.new(config)          -- nil-safe; d.ready is false without bounds
--   local event = d:feed(frame, ctx)  -- frame: trace record; ctx: scene/star state
--   local event = d:finish(ctx)       -- end-of-trace cancellation
--   d:state(), d:attemptId()
-- ctx = { course=, level=, act=, area=, star_mask=, stars= } (star_mask = course-2
--       seven-bit star flags; bit (star_id-1) means that mission star is saved).

local ED = {}
ED.VERSION = 1
ED.EVENTS = { "approach", "setup", "attempt", "success", "setback", "abandoned" }

local function finite(v)
    return type(v) == "number" and v == v and math.abs(v) < math.huge
end
local function bitSet(value, bit)
    if not finite(value) then return nil end
    if bit < 0 or bit > 7 then return nil end
    return math.floor(value / (2 ^ bit)) % 2 == 1
end
local function copyInto(target, source)
    for k, v in pairs(source or {}) do
        if type(v) == "table" then
            local nested = {}
            copyInto(nested, v)
            target[k] = nested
        else
            target[k] = v
        end
    end
    return target
end
local function boxConfigured(box)
    return type(box) == "table" and finite(box.x0) and finite(box.x1) and finite(box.y0)
        and finite(box.y1) and finite(box.z0) and finite(box.z1)
end
local function inBox(box, x, y, z, margin)
    if not boxConfigured(box) then return false end
    local m = margin or 0
    return x >= box.x0 - m and x <= box.x1 + m
        and y >= box.y0 - m and y <= box.y1 + m
        and z >= box.z0 - m and z <= box.z1 + m
end
local function resolveActions(list)
    local set = {}
    if type(list) ~= "table" then return set end
    for _, item in ipairs(list) do
        if finite(item) then
            set[math.floor(item)] = true
        elseif type(item) == "string" and type(_G) == "table" and finite(_G[item]) then
            set[math.floor(_G[item])] = true
        end
    end
    return set
end

function ED.defaultConfig()
    return {
        encounter_id = "wf_cannonless",
        course = 2, level = 24, act = 6, star_id = 6,
        require_star_uncollected = true,
        -- Measured world-space bounds; nil until Deliverable 3 measurement.
        region = { approach = nil, setup = nil, attempt = nil, ledge_y = nil },
        dwell = { approach = 6, setup = 10 },
        setup_max_speed = 3.0,
        attempt_actions = {
            "ACT_WALL_KICK_AIR", "ACT_JUMP_KICK", "ACT_AIR_HIT_WALL",
            "ACT_GROUND_BONK", "ACT_BACKWARD_AIR_KB", "ACT_SOFT_BONK",
            "ACT_LEDGE_GRAB", "ACT_BACKFLIP", "ACT_SIDE_FLIP",
        },
        attempt_vy = 6.0,
        attempt_fall_vy = -2.0,
        windows = { success = 330, setback = 240, timeout = 900, cooldown = 60 },
        latch = 120,
        min_confidence = 0.5,
        confidence = { approach = 0.9, setup = 0.7, attempt = 0.8,
                       success = 0.95, setback = 0.7, abandoned = 0.6 },
        hysteresis = { approach = 16, setup = 8 },
    }
end

function ED.normalize(config)
    local cfg = ED.defaultConfig()
    copyInto(cfg, config or {})
    return cfg
end

local D = {}
D.__index = D

function ED.new(config)
    local cfg = ED.normalize(config)
    local self = setmetatable({}, D)
    self.cfg = cfg
    self.attemptActions = resolveActions(cfg.attempt_actions)
    self.ready = boxConfigured(cfg.region.approach) and boxConfigured(cfg.region.setup)
        and boxConfigured(cfg.region.attempt) and finite(cfg.region.ledge_y)
    self:reset()
    return self
end

function D:reset()
    self.mode = "outside"
    self.frame = 0
    self.approachDwell = 0
    self.setupDwell = 0
    self.modeEnterFrame = 0
    self.attempts = 0
    self.attemptNumber = nil
    self.attemptFrame = nil
    self.attemptMaskAtStart = nil
    self.cooldownUntil = 0
    self.lastEvent = nil
    return self
end

function D:state()
    return self.mode
end

function D:attemptId()
    return self.attemptNumber
end

local function starSaved(ctx, starId)
    if ctx == nil or not finite(ctx.star_mask) then return nil end
    return bitSet(ctx.star_mask, starId - 1)
end

local function contextMatches(cfg, ctx)
    if ctx == nil then return true end
    local checks = { { ctx.level, cfg.level }, { ctx.course, cfg.course }, { ctx.act, cfg.act } }
    for _, pair in ipairs(checks) do
        local actual, expected = pair[1], pair[2]
        if finite(actual) and finite(expected) and math.floor(actual) ~= math.floor(expected) then
            return false
        end
    end
    return true
end

function D:emit(kind, reason, frame, evidence, confidenceOverride)
    local conf = confidenceOverride or self.cfg.confidence[kind] or 0
    if conf < self.cfg.min_confidence then
        return nil -- silence beats a low-confidence accusation or announcement
    end
    local event = {
        v = ED.VERSION,
        encounter = self.cfg.encounter_id,
        kind = kind,
        frame = frame,
        expiry_frame = frame + (self.cfg.latch or 120),
        confidence = conf,
        attempt_id = self.attemptNumber,
        reason = reason or "",
        evidence = evidence or "",
    }
    self.lastEvent = event
    return event
end

function D:closeAttempt(frame)
    self.attemptNumber = nil
    self.attemptFrame = nil
    self.attemptMaskAtStart = nil
end

function D:feed(frame, ctx)
    if not self.ready then return nil end
    if type(frame) ~= "table" or not finite(frame.x) or not finite(frame.y) or not finite(frame.z) then
        return nil
    end
    local f = finite(frame.f) and math.floor(frame.f) or (self.frame + 1)
    self.frame = f
    local cfg = self.cfg
    local x, y, z = frame.x, frame.y, frame.z
    local spd = finite(frame.spd) and frame.spd or 0
    local vy = finite(frame.vy) and frame.vy or 0
    local act = finite(frame.act) and math.floor(frame.act) or nil

    -- Scene gate: any other course/level/act cancels without a failure claim.
    if not contextMatches(cfg, ctx) then
        if self.mode ~= "outside" then
            local event = self:emit("abandoned", "context-change", f, "scene")
            self:reset()
            return event
        end
        return nil
    end

    local region = cfg.region
    local inApproach = inBox(region.approach, x, y, z, 0)
    local inSetup = inBox(region.setup, x, y, z, 0)
    local inAttempt = inBox(region.attempt, x, y, z, 0)
    local approachExit = inBox(region.approach, x, y, z, cfg.hysteresis.approach)
    local setupExit = inBox(region.setup, x, y, z, cfg.hysteresis.setup)

    -- Success is the only positive outcome and needs the star bit to change
    -- during a confirmed attempt.
    if self.mode == "attempt" then
        local savedNow = starSaved(ctx, cfg.star_id)
        if savedNow == true and self.attemptMaskAtStart == false
            and f - (self.attemptFrame or f) <= cfg.windows.success then
            local event = self:emit("success", "star-flag-set", f, "course2-star-mask")
            self:closeAttempt(f)
            self.mode = "outside"
            self.approachDwell, self.setupDwell = 0, 0
            self.cooldownUntil = f + cfg.windows.cooldown
            return event
        end
    end

    -- Existing saved star is never an attempt target: stay silent, no success.
    -- Checked AFTER the in-flight attempt block, because the star flag appearing
    -- during a confirmed attempt is success, not a gate violation.
    if cfg.require_star_uncollected and starSaved(ctx, cfg.star_id) == true then
        if self.mode ~= "outside" then
            local event = self:emit("abandoned", "star-already-collected", f, "star-mask")
            self:reset()
            return event
        end
        return nil
    end

    if self.mode == "outside" then
        if f < self.cooldownUntil then return nil end
        if inApproach then
            self.approachDwell = self.approachDwell + 1
            if self.approachDwell >= cfg.dwell.approach then
                -- A suppressed low-confidence transition must not become state.
                local event = self:emit("approach", "entered-region", f, "approach-box")
                if event then self.mode, self.modeEnterFrame = "approach", f end
                return event
            end
        else
            self.approachDwell = 0
        end
        return nil
    end

    if self.mode == "approach" then
        if not approachExit then
            local event = self:emit("abandoned", "left-region", f, "approach-exit")
            self:reset()
            return event
        end
        if spd > cfg.setup_max_speed then self.setupDwell = 0
        elseif inSetup then self.setupDwell = self.setupDwell + 1 end
        if self.setupDwell >= cfg.dwell.setup then
            local event = self:emit("setup", "paused-in-setup", f, "speed+dwell")
            if event then self.mode, self.modeEnterFrame = "setup", f end
            return event
        end
        return nil
    end

    if self.mode == "setup" then
        if not setupExit and not inAttempt then
            self.mode = "approach"
            self.setupDwell = 0
            return nil
        end
        -- Attempt signal: a kick/wall action, a rising jump, or the measured
        -- Cannonless entry (walking/falling off the plank into the clip volume).
        -- None of these alone is proof of intent, hence the volume requirement.
        local actionHit = act ~= nil and self.attemptActions[act] == true
        local risingHit = vy >= cfg.attempt_vy
        local fallingHit = vy <= cfg.attempt_fall_vy
        if inAttempt and (actionHit or risingHit or fallingHit) then
            self.attempts = self.attempts + 1
            self.attemptNumber = self.attempts
            self.attemptFrame = f
            self.attemptMaskAtStart = starSaved(ctx, cfg.star_id) == true
            self.mode = "attempt"
            local evidence = actionHit and "kick-action" or (risingHit and "rising-jump" or "left-plank-fall")
            return self:emit("attempt", evidence, f, evidence)
        end
        if f - self.modeEnterFrame > cfg.windows.timeout then
            local event = self:emit("abandoned", "setup-timeout", f, "timeout")
            self:reset()
            return event
        end
        return nil
    end

    if self.mode == "attempt" then
        -- Observed result only; no inferred cause.
        if finite(region.ledge_y) and y < region.ledge_y and y < region.setup.y0 then
            local event = self:emit("setback", "below-ledge", f, "y<ledge")
            self:closeAttempt(f)
            self.mode = "outside"
            self.cooldownUntil = f + cfg.windows.cooldown
            return event
        end
        if finite(frame.hp) and frame.hp <= 0 then
            local event = self:emit("setback", "death", f, "health")
            self:closeAttempt(f)
            self.mode = "outside"
            self.cooldownUntil = f + cfg.windows.cooldown
            return event
        end
        if f - (self.attemptFrame or f) > cfg.windows.success then
            local event = self:emit("abandoned", "attempt-unresolved", f, "window")
            self:closeAttempt(f)
            self.mode = approachExit and "approach" or "outside"
            return event
        end
        return nil
    end

    return nil
end

function D:finish(ctx)
    if self.mode == "outside" then return nil end
    local frame = self.frame
    local event = self:emit("abandoned", "trace-ended", frame, "end-of-stream")
    self:reset()
    return event
end

return ED
