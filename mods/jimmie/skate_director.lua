-- Independent, grounded character beats. This module never moves an engine object.
-- Positions are SM64 world units, speed outputs are units/frame, timers are seconds.
-- Targets must come from engine-probed spots; the planner cannot invent safe floor.
local D = {}
D.__index = D
D.DEFAULTS = { socialMin = 280, socialMax = 650, rejoinAt = 850, rejoinDone = 520,
    trickMinGap = 6.0, trickMaxGap = 10.5, goalLifetime = 6.5, motionGoalLifetime = 0.10,
    jumpFollowTTL = 0.35, jumpFollowGap = 1.25, jumpFollowRange = 500,
    movingTrickMaxDelta = 1.5, movingTrickMaxDrift = 0.10 }

local function finite(v) return type(v) == "number" and v == v and math.abs(v) < 1e8 end
local function distance(ax, az, bx, bz)
    local dx, dz = ax - bx, az - bz
    return math.sqrt(dx * dx + dz * dz)
end
local function clamp(v, a, b) return math.max(a, math.min(b, v)) end
local function safe_spot(spot)
    return type(spot) == "table" and finite(spot.x) and finite(spot.y) and finite(spot.z)
        and spot.safe == true and spot.landingSafe == true and (spot.clearance or 0) >= 90
        and not spot.hazard
end

function D.new(options)
    options = options or {}
    local self = setmetatable({rng = options.rng or math.random, config = {}, recent = {}}, D)
    for k, v in pairs(D.DEFAULTS) do self.config[k] = options[k] or v end
    self:reset(nil)
    return self
end

function D:random()
    local n = self.rng()
    if not finite(n) then return 0.5 end
    return clamp(n, 0, 0.999999999)
end

function D:reset(scene)
    self.scene, self.time, self.state, self.stateSince = scene, 0, "roam", 0
    self.target, self.targetUntil, self.recent = nil, 0, {}
    self.biasName, self.biasUntil = nil, 0
    self.lastTrick, self.lastTrickAt = nil, -100
    self.nextTrickAt, self.nextGoalAt = 3 + self:random() * 2, 0
    self.sawAir, self.blockedTime = false, 0
    self.episode, self.lastReason = 0, "scene-start"
    self.stoppedTime, self.wasMoving, self.motionGoalAt = 1, false, 0
    self.previousMarioX, self.previousMarioZ, self.setupMoving = nil, nil, false
    self.jumpObservation, self.jumpFollowUntil = nil, nil
    self.movingTrickObservation, self.setupVelocity = nil, nil
end

-- A fresh, consecutive ground-to-rising observation is a cue, not jump proof.
-- A one-use short window may wait for eligibility, never for a later flight.
function D:observeMarioJump(s, playerSpeed, social)
    local previous=self.jumpObservation
    local valid=s.marioMotionValid==true and s.scene~=nil and s.marioInstance~=nil
        and finite(s.marioFrame) and finite(s.marioObservationEpoch)
        and finite(s.marioVY) and finite(s.marioFloorHeight)
    if not valid then self.jumpObservation,self.jumpFollowUntil=nil,nil; return end
    local consecutive=previous and previous.frame+1==s.marioFrame
        and previous.instance==s.marioInstance and previous.epoch==s.marioObservationEpoch
    local nearby=social<=self.config.jumpFollowRange
        and math.abs(s.y-s.marioFloorHeight)<=96
    if not consecutive or not nearby or playerSpeed<12 or s.grounded~=true
        or s.marioRising~=true or (self.jumpFollowUntil and self.time>self.jumpFollowUntil) then
        self.jumpFollowUntil=nil
    end
    if consecutive and previous.grounded and s.marioRising==true
        and s.marioY>previous.y+1 and s.marioY-previous.y<=math.max(80,s.marioVY+12)
        and math.abs(s.marioFloorHeight-previous.floor)<=42
        and distance(s.marioX,s.marioZ,previous.x,previous.z)<=math.max(150,playerSpeed*2)
        and nearby and playerSpeed>=12 and s.grounded==true and self.state~="attempt"
        and self.time-self.lastTrickAt>=self.config.jumpFollowGap then
        self.jumpFollowUntil=self.time+self.config.jumpFollowTTL
    end
    self.jumpObservation={frame=s.marioFrame,instance=s.marioInstance,epoch=s.marioObservationEpoch,
        grounded=s.marioGrounded==true,x=s.marioX,y=s.marioY,z=s.marioZ,floor=s.marioFloorHeight}
end

-- Random moving tricks need a straight, settled opportunity, not just enough speed.
-- Compare native-frame velocities: straight walking changes by <=1.1 units/frame,
-- while level-floor braking changes by 4 and a full walking turn by ~6 at speed32.
-- These conservative tolerances select opportunities; they do not predict a safe flight.
function D:observeMovingTrick(s, dt)
    local previous = self.movingTrickObservation
    local valid = finite(dt) and dt > 0 and s.marioMotionValid == true
        and s.scene ~= nil and s.marioInstance ~= nil
        and finite(s.marioFrame) and s.marioFrame % 1 == 0
        and finite(s.marioObservationEpoch) and finite(s.marioVX) and finite(s.marioVZ)
        and finite(s.speed)
    if not valid then self.movingTrickObservation = nil; return false end
    local vx, vz = s.marioVX, s.marioVZ
    self.movingTrickObservation = {frame=s.marioFrame,instance=s.marioInstance,
        epoch=s.marioObservationEpoch,vx=vx,vz=vz,x=s.marioX,z=s.marioZ}
    if not previous or previous.frame + 1 ~= s.marioFrame
        or previous.instance ~= s.marioInstance or previous.epoch ~= s.marioObservationEpoch then
        return false
    end
    local speed = math.sqrt(vx*vx + vz*vz)
    if distance(vx,vz,previous.vx,previous.vz) > self.config.movingTrickMaxDelta
        or distance(s.marioX,s.marioZ,previous.x,previous.z) > math.max(150,speed*2) then
        return false
    end
    -- Small individual steering changes must not accumulate into a stale setup.
    local anchor = self.setupMoving and self.state == "setup" and self.setupVelocity
    return not anchor or distance(vx,vz,anchor.vx,anchor.vz)
        <= math.max(self.config.movingTrickMaxDelta,anchor.speed*self.config.movingTrickMaxDrift)
end

-- The AI can suggest a beat. It cannot lower the hard trick cooldown or safety tests.
function D:bias(name, ttl)
    if name == "none" then return true end
    if name ~= "roam" and name ~= "showoff" and name ~= "rejoin" and name ~= "observe" then
        return false
    end
    self.biasName, self.biasUntil = name, self.time + clamp(tonumber(ttl) or 6, 0, 12)
    return true
end

function D:enter(state, reason)
    if state == "setup" and self.state ~= "setup" and JIMMIE_BRAIN then pcall(JIMMIE_BRAIN.approach) end
    if self.state ~= state then self.state, self.stateSince = state, self.time end
    self.lastReason = reason
end

function D:pick(s, rejoin)
    local best, bestScore = nil, -math.huge
    for _, spot in ipairs(s.spots or {}) do
        if safe_spot(spot) then
            local social = distance(spot.x, spot.z, s.marioX, s.marioZ)
            local travel = distance(spot.x, spot.z, s.x, s.z)
            local minBand = rejoin and 180 or self.config.socialMin
            local maxBand = rejoin and self.config.rejoinDone or self.config.socialMax
            if social >= minBand and social <= maxBand and travel > 75 then
                local score = (tonumber(spot.score) or 0) * 0.15
                score = score + (rejoin and (-social * 0.3 - travel * 0.08)
                    or (100 - math.abs(social - 470) * 0.18 - math.abs(travel - 340) * 0.10))
                if self.biasName == "roam" then score = score + social * 0.05 end
                if self.biasName == "showoff" and spot.kind == "flat" then score = score + 12 end
                for _, old in ipairs(self.recent) do
                    if distance(spot.x, spot.z, old.x, old.z) < 140 then score = score - 65 end
                end
                -- One draw per evaluated goal, never a per-frame probability of acting.
                score = score + self:random() * 12
                if score > bestScore then best, bestScore = spot, score end
            end
        end
    end
    if best then
        self.target = {x = best.x, y = best.y, z = best.z, kind = best.kind or "flat"}
        self.targetUntil = self.time + self.config.goalLifetime
        self.recent[#self.recent + 1] = {x = best.x, z = best.z}
        while #self.recent > 3 do table.remove(self.recent, 1) end
        self.episode = self.episode + 1
        return true
    end
    self.target = nil
    return false
end

function D:result(active, reason, event)
    local intent = {active = active, state = self.state, reason = reason or self.lastReason,
        event = event, speed = 0, brake = active, socialMin = self.config.socialMin,
        socialMax = self.config.socialMax, episode = self.episode}
    if self.target then
        intent.targetX, intent.targetY, intent.targetZ = self.target.x, self.target.y, self.target.z
        intent.goalKind = self.target.kind
    end
    return intent
end

-- Motion goals are short-lived route/trail observations, not idle destinations.
-- A local rejoin step is useful even when its endpoint is still far from Mario.
function D:pickMotion(s, rejoin, playerSpeed)
    local gap = distance(s.x, s.z, s.marioX, s.marioZ)
    local vx, vz = tonumber(s.marioVX) or 0, tonumber(s.marioVZ) or 0
    local vm = math.sqrt(vx*vx + vz*vz)
    local best, bestScore = nil, -math.huge
    for _, spot in ipairs(s.spots or {}) do
        if safe_spot(spot) then
            local dx, dz = spot.x-s.x, spot.z-s.z
            local travel = math.sqrt(dx*dx + dz*dz)
            local social = distance(spot.x,spot.z,s.marioX,s.marioZ)
            local progress = gap-social
            local forward = vm>1 and (dx*vx+dz*vz)/vm or progress
            local route = spot.kind=="route"
            local pace = spot.kind=="pace" or spot.kind=="predictive_pace"
            local step = spot.kind=="rejoin_step"
            local useful = route or (step and progress>12) or
                (pace and (forward>-35 or gap>650)) or
                (not pace and not step and progress>35 and gap>450)
            if travel>45 and useful then
                -- A route may first go away from Mario to get around a wall.
                -- Root supplies only collision-checked, useful trail nodes.
                local score = route and (rejoin and 340 or 240) or
                    (pace and (rejoin and 200 or 340) or (step and 180 or 0))
                score = score + (tonumber(spot.score) or 0)*25 + progress*0.12
                    - math.abs(travel-260)*0.035
                if not route and not rejoin then score=score-math.abs(social-330)*0.08 end
                local predictive=spot.kind=="predictive_pace"
                local bestPredictive=best~=nil and best.kind=="predictive_pace"
                if (predictive and not bestPredictive) or
                    (predictive==bestPredictive and score>bestScore) then best,bestScore=spot,score end
            end
        end
    end
    if not best then self.target=nil; return false end
    self.target={x=best.x,y=best.y,z=best.z,kind=best.kind or "flat"}
    self.targetUntil=self.time+self.config.motionGoalLifetime
    self.motionGoalAt=self.targetUntil
    return true
end

function D:launch(speed, jumpFollow)
    local kickWeight=self.biasName=="showoff" and 0.8 or 0.58
    if self.lastTrick=="kickflip" then kickWeight=kickWeight*0.45 end
    if self.lastTrick=="ollie" then kickWeight=math.min(0.9,kickWeight+0.25) end
    if jumpFollow then kickWeight = self.lastTrick == "kickflip" and 0.14 or 0.30 end
    local trick=self:random()<kickWeight and "kickflip" or "ollie"
    self.lastTrick,self.lastTrickAt=trick,self.time
    self.nextTrickAt=self.time+self.config.trickMinGap+self:random()*
        (self.config.trickMaxGap-self.config.trickMinGap)
    self.sawAir=false
    self.jumpFollowUntil=nil
    self:enter("attempt",jumpFollow and "mario-jump-follow" or "intentional-trick")
    local out=self:result(true,nil,"trick_attempt")
    out.speed,out.brake,out.trick=speed,false,trick
    out.trickVariant,out.jumpVelocity=trick=="kickflip" and 1 or 0,trick=="kickflip" and 44 or 40
    if jumpFollow then out.jumpFollow=true end
    return out
end

function D:motion(s, playerSpeed, social, safeLaunch, rejoin, event, movingTrickStable)
    local catchingUp=rejoin or social>560
    local movingSetup=self.state=="setup" and self.setupMoving
    local state=rejoin and "rejoin" or "keep_up"
    if not movingSetup then self:enter(state,rejoin and "following-checked-route" or "pace-moving-Mario") end
    local travel=self.target and distance(self.target.x,self.target.z,s.x,s.z) or 0
    if not self.target or self.time>=self.motionGoalAt or s.targetSafe==false or travel<105 then
        self:pickMotion(s,rejoin,playerSpeed)
    end
    if not self.target then
        if movingSetup then self:enter(state,"waiting-for-checked-route"); self.setupMoving=false end
        return self:result(true,"waiting-for-checked-route",event)
    end
    -- Keep speed allowance separate from separation: fast alongside skating may still trick.
    local fastPace=self.target.kind=="predictive_pace" and playerSpeed>58
    local pace
    if playerSpeed>=3 then
        if self.target and self.target.kind=="predictive_pace" then
            local vx,vz=tonumber(s.marioVX) or 0,tonumber(s.marioVZ) or 0
            local vm=math.sqrt(vx*vx+vz*vz)
            local lag=vm>1 and ((s.marioX-s.x)*vx+(s.marioZ-s.z)*vz)/vm or 0
            -- Match Mario's travel speed alongside; close longitudinal lag.
            pace=playerSpeed+clamp(lag*0.09,-16,24)
        else
            pace=playerSpeed+2.5+(social-340)*0.055
        end
        if catchingUp then pace=math.max(pace,playerSpeed+10) end
        pace=clamp(pace,math.max(8,playerSpeed*0.65),96)
    else
        pace=clamp(30+(social-520)*0.065,30,96)
    end
    local stable=not catchingUp and social<=600 and (tonumber(s.speed) or 0)>=math.max(8,playerSpeed*0.8)
    if self.jumpFollowUntil and stable and safeLaunch and playerSpeed>=12 then
        self.setupMoving=false
        local out=self:launch(pace,true); out.catchUp=fastPace; return out
    end
    local due=self.time>=self.nextTrickAt and self.time-self.lastTrickAt>=self.config.trickMinGap
    if movingSetup then
        if not safeLaunch or not stable or not movingTrickStable or s.targetSafe == false then
            self.setupMoving=false; self.setupVelocity=nil; self:enter(state,"pace-before-trick")
        elseif self.time-self.stateSince>=0.38 then
            local out=self:launch(pace); out.catchUp=fastPace; return out
        end
    elseif stable and safeLaunch and due and playerSpeed>=12 and movingTrickStable
        and s.targetSafe ~= false then
        self.setupVelocity={vx=s.marioVX,vz=s.marioVZ,
            speed=math.sqrt(s.marioVX*s.marioVX+s.marioVZ*s.marioVZ)}
        self.setupMoving=true; self:enter("setup","rolling-trick-opportunity")
    end
    local out=self:result(true,nil,event)
    out.speed,out.brake,out.catchUp=pace,false,catchingUp or fastPace
    return out
end

function D:step(dt, s)
    s = s or {}
    if s.scene ~= self.scene then self:reset(s.scene) end
    dt = clamp(tonumber(dt) or 0, 0, 0.25)
    if s.enabled == false or s.paused or s.dead or s.manual ~= nil then
        self.target, self.sawAir = nil, false
        self.jumpObservation,self.jumpFollowUntil=nil,nil
        self.movingTrickObservation,self.setupVelocity,self.setupMoving=nil,nil,false
        self:enter("suspended", s.manual ~= nil and "manual" or
            (s.dead and "dead" or (s.paused and "paused" or "disabled")))
        self.nextTrickAt = math.max(self.nextTrickAt, self.time + 1)
        return self:result(false)
    end
    if not (finite(s.x) and finite(s.y) and finite(s.z) and finite(s.marioX)
        and finite(s.marioY) and finite(s.marioZ)) then
        self.target = nil; self.jumpObservation,self.jumpFollowUntil=nil,nil
        self.movingTrickObservation,self.setupVelocity,self.setupMoving=nil,nil,false
        self:enter("observe", "missing-sensors")
        return self:result(true)
    end
    self.time = self.time + dt
    if self.biasName and self.time >= self.biasUntil then self.biasName = nil end
    if self.state == "suspended" then self:enter("roam", "autonomy-resumed") end
    local social = distance(s.x, s.z, s.marioX, s.marioZ)
    local speed = tonumber(s.speed) or 0
    local vx,vz=tonumber(s.marioVX) or 0,tonumber(s.marioVZ) or 0
    local playerSpeed=math.max(tonumber(s.marioSpeed) or 0,math.sqrt(vx*vx+vz*vz))
    if self.previousMarioX and dt>0 then
        local measured=distance(s.marioX,s.marioZ,self.previousMarioX,self.previousMarioZ)/(dt*30)
        playerSpeed=math.max(playerSpeed,math.min(96,measured))
    end
    self.previousMarioX,self.previousMarioZ=s.marioX,s.marioZ
    local moving=playerSpeed>=12 or (social>600 and playerSpeed>=3)
    if moving then self.stoppedTime,self.wasMoving=0,true
    else self.stoppedTime=self.stoppedTime+dt end
    local pacing=moving or (self.wasMoving and self.stoppedTime<1)
    if not pacing then self.wasMoving=false end
    self:observeMarioJump(s,playerSpeed,social)
    local movingTrickStable = self:observeMovingTrick(s,dt)
    local safe = s.floorSafe == true and not s.inWater and not s.onLava
    local safeLaunch = safe and s.grounded == true and s.forwardSafe == true
        and s.landingSafe == true and not s.blocked and speed >= 8
    local event
    if not safe then
        self.target, self.sawAir = nil, false
        self.jumpFollowUntil=nil
        self:enter("recover", "unsafe-floor")
        self.nextTrickAt = math.max(self.nextTrickAt, self.time + 1)
        return self:result(true)
    end
    if s.justBailed then
        self.jumpFollowUntil=nil
        self:enter("recover", "physical-bail")
        self.sawAir = false
        self.nextTrickAt = self.time + self.config.trickMinGap + self:random() *
            (self.config.trickMaxGap - self.config.trickMinGap)
        return self:result(true, nil, "trick_bailed")
    end
    if self.state == "attempt" then
        if not s.grounded then self.sawAir = true end
        if s.justLanded and self.sawAir then
            self:enter("recover", "physical-landing")
            self.sawAir, event = false, "trick_landed"
        elseif self.time - self.stateSince > 3.5 then
            self:enter("recover", "flight-timeout")
        elseif s.grounded and not self.sawAir and self.time - self.stateSince > 0.65 then
            self:enter("recover", "launch-not-observed")
        else
            local out = self:result(true, "awaiting-physical-outcome")
            out.speed, out.brake = math.max(26,playerSpeed+2.5), false
            out.catchUp = social>560 or (self.target and self.target.kind=="predictive_pace" and playerSpeed>58)
            out.preserveMomentum = not s.grounded
            return out
        end
    end
    if self.state == "recover" then
        if (not pacing and self.time - self.stateSince < 1.15) or not s.grounded then
            local out = self:result(true, nil, event)
            out.speed, out.brake = 12, false
            return out
        end
        self.target = nil
        self.nextGoalAt = self.time
        self:enter("roam", "recovered")
    end
    if self.biasName=="rejoin" and social<=self.config.rejoinDone then self.biasName=nil end
    local rejoin=social>self.config.rejoinAt or (self.state=="rejoin" and social>self.config.rejoinDone)
        or self.biasName=="rejoin"
    if pacing or rejoin then
        if self.state=="setup" and not self.setupMoving then self:enter("keep_up","Mario-started-moving") end
        return self:motion(s,playerSpeed,social,safeLaunch,rejoin,event,movingTrickStable)
    end
    if self.state=="keep_up" or self.state=="rejoin" or self.setupMoving then
        self.target,self.setupMoving=nil,false
        self.nextGoalAt=self.time
        self:enter("roam","Mario-stopped")
    end
    if self.biasName == "observe" and social <= self.config.socialMax then
        self.target = nil; self:enter("observe", "ai-observe")
        return self:result(true)
    elseif self.state == "observe" then self:enter("roam", "look-for-spot") end
    self.blockedTime = s.blocked and (self.blockedTime + dt) or 0
    if s.targetSafe == false or self.time >= self.targetUntil or self.blockedTime > 0.7 then
        self.target = nil
        self.nextGoalAt = self.time
        if self.state == "setup" then self:enter("roam", "spot-invalidated") end
        self.blockedTime = 0
    end
    if not self.target then
        if self.time < self.nextGoalAt then return self:result(true, "waiting-for-probes", event) end
        if not self:pick(s, self.state == "rejoin") then
            self.nextGoalAt = self.time + 0.5
            self:enter(self.state == "rejoin" and "rejoin" or "observe", "no-safe-spot")
            return self:result(true, nil, event)
        end
        if self.state ~= "rejoin" then self:enter("approach", "chosen-spot"); event = "spot_found" end
    end
    local travel = distance(self.target.x, self.target.z, s.x, s.z)
    if self.state == "rejoin" then
        local out = self:result(true, nil, event)
        out.speed, out.brake = clamp(28 + (social - 520) * 0.045, 28, 58), false
        return out
    end
    local due = self.time >= self.nextTrickAt and self.time - self.lastTrickAt >= self.config.trickMinGap
    if self.state == "setup" then
        if not safeLaunch then
            self:enter("approach", "setup-safety-changed")
        elseif self.time - self.stateSince >= 0.38 then
            return self:launch(28)
        end
        if self.state == "setup" then
            local out = self:result(true, "lining-up", event)
            out.speed, out.brake = 18, false
            return out
        end
    end
    if safeLaunch and due and speed >= 8 and travel >= 80 and travel <= 430 then
        self:enter("setup", "safe-opportunity")
        local out = self:result(true, nil, event)
        out.speed, out.brake = 18, false
        return out
    end
    if travel < 95 then
        self:enter("roam", "spot-visited")
        -- Hold a readable beat before selecting the next place; no per-frame reroll.
        self.target = nil
        self.nextGoalAt = self.time + 0.75 + self:random() * 0.65
        return self:result(true, "spot-dwell", event)
    end
    local out = self:result(true, nil, event)
    out.speed, out.brake = clamp(24 + travel * 0.025, 26, 38), false
    return out
end

return D
