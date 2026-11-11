-- Jimmie's brain, game side. Reports what happened; plays what the brain already decided.
--
-- The brain (python -m jimmie_brain run) keeps a plan in a ModFS box: for each thing that could
-- happen next, the line Jimmie would say, already voiced. This module loads those lines ahead of
-- time and, when an event fires, looks the answer up locally. No round trip at event time.
--
-- It never decides what happened. Callers report facts from the places that already witness
-- them (the route observer, the skate controller, the water observer). It owns no speech
-- channel either: every line goes through the existing single voice queue via deps.speak.
--
-- deps:
--   json(table) -> string            the mod's existing encoder
--   clock() -> number                monotonic game ms (jimmie_route_now_ms)
--   context() -> table|nil           {epoch,slot,generation,visit,mode,level,nearby}; nil when not in normal play
--   speak(sample, seconds, detail) -> boolean      VOICE.external (plus a performance grant where the build needs one)
--   busy() -> boolean                VOICE.busy
--   load(name) -> sample|nil         audio_sample_load, for mod files and ModFS URIs alike
--   print(line)                      print
--   veto = {["roast_01.ogg"]=true, ...}   owner-rejected files; never loaded
--   quiet() -> boolean               optional: true while nothing ambient should start (arrival greeting pending, etc.)
local M = {}

local function split(s)
    local out = {}
    for part in (s .. "|"):gmatch("(.-)|") do out[#out + 1] = part end
    return out
end

function M.new(d)
    local self = {}
    local session = string.format("%.0f", d.clock() * 1000)
    local planBox = "jbplan_" .. session
    local lines, plan, ambient, seq = {}, {}, nil, nil
    local nextPoll, delayed, greeted = 0, nil, false
    local lastScope, idleSince, idleSaid = nil, nil, 0
    local airTop, wasAir, lastHealth = nil, false, nil
    local beat, beatAt = nil, nil                 -- the brain's heartbeat: proof it is running right now
    local calledUntil, lastPickup, precisionUntil, wasSwim = 0, -1e9, 0, nil
    local veto = d.veto or {}

    local function scopeOf(w)
        return table.concat({w.epoch, w.slot, w.generation, w.visit}, "/")
    end

    -- Jimmie counts as present for a few seconds after he was last beside Mario: while he is
    -- sprawled on the ground after a bail the game briefly has no companion to measure from,
    -- and that is exactly when he has something to say.
    local nearAt, nearScope = nil, nil
    local function near(w)
        if not w then return false end
        if w.nearby == true then
            nearAt, nearScope = d.clock(), scopeOf(w)
            return true
        end
        return nearAt ~= nil and nearScope == scopeOf(w) and d.clock() - nearAt < 5000
    end

    local function emit(kind, actor, w, extra)
        local row = {}
        if extra then for k, v in pairs(extra) do row[k] = v end end
        row.k, row.a, row.ms, row.f = kind, actor, d.clock(), get_global_timer()
        local m0 = gMarioStates and gMarioStates[0]
        if m0 and m0.numStars then row.n = m0.numStars end
        if w then row.mode, row.scope, row.level = w.mode, scopeOf(w), w.level end
        d.print("[jb] " .. d.json(row))
    end

    -- Load a line's audio once. false = tried and unavailable.
    local loadsLeft, loadsDone = 2, 0
    local function sample(id)
        local l = lines[id]
        if not l then return nil end
        if l.sample == nil and loadsLeft <= 0 then return nil end   -- later: decoding is spread across polls
        if l.sample == nil then
            loadsLeft, loadsDone = loadsLeft - 1, loadsDone + 1
            l.sample = false
            if l.file ~= "" then
                if not veto[l.file] then l.sample = d.load(l.file) or false end
            elseif l.box ~= "" and mod_fs_exists(l.box) then
                mod_fs_reload(l.box)
                l.sample = d.load(string.format(MOD_FS_URI_FORMAT, l.box, "line.ogg")) or false
            else
                l.sample = nil -- the box has not landed yet; try again on the next poll
            end
        end
        return l.sample or nil
    end

    local function read()
        if type(mod_fs_exists) ~= "function" or not mod_fs_exists(planBox) then return end
        local fs = mod_fs_reload(planBox)
        local f = fs and mod_fs_get_file(fs, "plan.txt")
        if not f then return end
        local head = split(mod_fs_file_read_line(f) or "")
        if head[1] ~= "JB1" then return end
        local rows = tonumber(head[3])
        if not rows or rows < 0 or rows > 300 then return end
        if head[4] ~= beat then beat, beatAt = head[4], d.clock() end
        if head[2] ~= seq then
            local newPlan, newAmbient = {}, nil
            for _ = 1, rows do
                local r = split(mod_fs_file_read_line(f) or "")
                if r[1] == "L" then
                    local id = tonumber(r[2])
                    if not id then return end
                    if not lines[id] then
                        lines[id] = {box = r[3] or "", file = r[4] or "", seconds = tonumber(r[5]) or 1.5, text = r[6] or ""}
                    end
                elseif r[1] == "P" then
                    newPlan[r[2]] = {line = tonumber(r[3]), delay = tonumber(r[4]) or 0, scope = r[5], intent = r[6], rule = r[7]}
                elseif r[1] == "N" then
                    newAmbient = {line = tonumber(r[2]), expires = tonumber(r[3]) or 0, scope = r[4], intent = r[5],
                                  rule = r[6], delay = tonumber(r[7]) or 0}
                else
                    return -- malformed: keep the plan we had
                end
            end
            seq, plan = head[2], newPlan
            if not newAmbient then
                ambient = nil
            elseif not ambient or ambient.line ~= newAmbient.line then
                ambient = newAmbient
            end
        end
        loadsLeft = 2
        if ambient then sample(ambient.line) end
        for _, e in pairs(plan) do sample(e.line) end
    end

    local function start(e, onPlay)
        local l, snd = lines[e.line], sample(e.line)
        local w = d.context()
        if not l or not snd then
            emit("dropped", "jimmie", w, {line = e.line, why = "not_loaded"})
            return false
        end
        local began = d.clock()
        local function live()
            local now = d.context()
            return now ~= nil and near(now) and scopeOf(now) == e.scope and d.clock() - began <= 400
        end
        if not live() then return false end
        return d.speak(snd, l.seconds, {
            event = "brain_" .. tostring(e.intent), key = "brain:" .. tostring(e.line), text = l.text, volume = 1.0,
            priority = 66, ttl = 0.4, valid = live,
            onPlay = function()
                emit("played", "jimmie", d.context(), {line = e.line, rule = e.rule, intent = e.intent})
                if e.intent == "boast_call" then calledUntil = d.clock() + 12000 end
                if onPlay then onPlay() end
            end,
        })
    end

    -- Report a witnessed fact and, if the brain had an answer ready for it, say it.
    -- Returns true when a line was started or scheduled. onPlay runs when it is actually heard.
    function self.fact(kind, actor, extra, onPlay)
        local w = d.context()
        emit(kind, actor, w, extra)
        if not near(w) then return false end
        local key = kind .. ":" .. actor
        if extra and extra.condition then key = key .. ":" .. tostring(extra.condition) end
        local e = plan[key]
        if not e or e.scope ~= scopeOf(w) then return false end
        plan[key] = nil -- one answer per plan; the brain re-plans after every fact
        if e.delay > 0 then
            delayed = {entry = e, due = d.clock() + e.delay, onPlay = onPlay}
            return true
        end
        return start(e, onPlay)
    end

    -- True while the brain process is feeding plans. The old canned barks stand down while it is.
    function self.live() return beatAt ~= nil and d.clock() - beatAt < 6000 end

    -- Jimmie has picked a spot and is lining up a trick.
    function self.approach() return self.fact("trick_approach", "jimmie", {toward = true}) end

    -- A physical skate outcome from the skate memory. Whether he had called it decides what it means.
    function self.skate(f)
        if type(f) ~= "table" then return end
        local called = d.clock() < calledUntil
        if f.fact == "trick_bailed" then
            calledUntil = 0
            self.fact("trick_bailed", "jimmie", {condition = called and "called_bail" or "plain_bail", trick = f.trick})
        elseif f.fact == "trick_completed" and f.kind == "trick" then
            calledUntil = 0
            local c = called and "called_land" or (f.condition == "landing_after_getup" and "landing_after_getup" or "clean_landing")
            self.fact("trick_completed", "jimmie", {condition = c, trick = f.trick, row = f.line})
        end
    end

    -- Route observations the 16-star companion already makes.
    local ROUTE = {fell_below_setup = "setback", wall_setup = "precision_setup", possible_wall_attempt = "precision_attempt"}
    function self.route(kind)
        local mapped = ROUTE[kind]
        if not mapped then return end
        if mapped ~= "setback" then precisionUntil = d.clock() + 6000 end
        self.fact(mapped, "mario")
    end

    function self.interact(m, _, kind)
        if not m or m.playerIndex ~= 0 or kind ~= INTERACT_STAR_OR_KEY then return end
        local now = d.clock()
        if now - lastPickup < 3000 then return end
        lastPickup = now
        local level = gNetworkPlayers[0].currLevelNum
        if level == LEVEL_BOWSER_3 then self.fact("grand_star", "mario")
        elseif level == LEVEL_BOWSER_1 or level == LEVEL_BOWSER_2 then self.fact("key", "mario")
        else self.fact("star", "mario") end
    end

    -- Something the player typed in the game chat. The brain picks the answer and sends it back
    -- as the next ambient line, so he replies about a second later, the way he reads chat on stream.
    function self.chat(m, msg)
        if (m and m.playerIndex ~= 0) or type(msg) ~= "string" then return end
        local text = msg:gsub("\\#%x+\\", ""):gsub("[%c\"\\]", " "):gsub("^%s+", ""):gsub("%s+$", "")
        if text == "" or text:sub(1, 1) == "/" then return end
        emit("chat", "mario", d.context(), {text = text:sub(1, 160)})
    end

    function self.death(m)
        if m and m.playerIndex == 0 then self.fact("death", "mario") end
    end

    -- Facts this module can witness by itself from public state.
    local function watch(w, now)
        local m = gMarioStates[0]
        if not m or not m.vel then return end
        local scope = scopeOf(w)
        if scope ~= lastScope then
            lastScope, idleSince, idleSaid, airTop, wasAir, lastHealth = scope, nil, 0, nil, false, m.health
            wasSwim, precisionUntil, calledUntil = (m.action & ACT_FLAG_SWIMMING) ~= 0, 0, 0
            delayed = nil
            self.fact("arrival", "mario")
            return
        end
        local air = (m.action & ACT_FLAG_AIR) ~= 0
        local still = not air and (m.action & ACT_FLAG_INTANGIBLE) == 0
            and math.abs(m.vel.x) < 2 and math.abs(m.vel.y) < 2 and math.abs(m.vel.z) < 2
        if still then
            idleSince = idleSince or now
            local s = (now - idleSince) / 1000
            if s >= 8 and now - idleSaid >= 6000 then
                idleSaid = now
                emit("idle", "mario", w, {s = math.floor(s)})
            end
        else
            idleSince = nil
        end
        local swim = (m.action & ACT_FLAG_SWIMMING) ~= 0
        if swim and wasSwim == false then self.fact("water_enter", "mario") end
        wasSwim = swim
        if air and not wasAir and now < precisionUntil and m.vel.y > 0 then self.fact("precision_jump", "mario") end
        if air then
            if not wasAir or m.pos.y > airTop then airTop = m.pos.y end
        elseif wasAir and airTop and airTop - m.pos.y > 1150 then
            self.fact("fall", "mario")
        end
        wasAir = air
        if lastHealth and m.health < lastHealth - 0xFF and m.health > 0xFF then self.fact("hurt", "mario") end
        lastHealth = m.health
    end

    local lastFrame, why = nil, nil
    function self.update()
        local now = d.clock()
        -- A frame that took far too long, with what this module did during it, so stalls can be traced.
        if lastFrame and now - lastFrame > 120 then
            emit("hitch", "game", nil, {dt = math.floor(now - lastFrame), loads = loadsDone})
        end
        lastFrame, loadsDone = now, 0
        if not greeted then
            greeted = true
            emit("hello", "game", nil, {session = session})
        end
        if now >= nextPoll then
            nextPoll = now + 250
            local ok, err = pcall(read)
            if not ok then d.print("[jb] " .. d.json({k = "link_error", a = "game", ms = now, why = tostring(err)})) end
        end
        local w = d.context()
        if not w then
            delayed = nil
            return
        end
        near(w)
        watch(w, now)
        if delayed and now >= delayed.due then
            local p = delayed
            delayed = nil
            if near(w) and scopeOf(w) == p.entry.scope then start(p.entry, p.onPlay) end
        end
        if ambient and not delayed then
            if now > ambient.expires or ambient.scope ~= scopeOf(w) then
                emit("missed", "jimmie", w, {line = ambient.line, rule = ambient.rule,
                                             why = ambient.scope ~= scopeOf(w) and "left" or (why or "expired")})
                ambient, why = nil, nil
            elseif not near(w) then why = "far"
            elseif d.busy() then why = "busy"
            elseif d.quiet and d.quiet() then why = "quiet"
            elseif not sample(ambient.line) then why = "loading"
            else
                local a = ambient
                ambient, why = nil, nil
                start(a)
            end
        end
    end

    function self.clear()
        delayed, ambient, plan = nil, nil, {}
    end

    function self.session() return session end
    return self
end

return M
