-- Observed game context and bounded local-director transport. No Mario writes.
local R = {}
local function finite(n) return type(n) == "number" and n == n and math.abs(n) < math.huge end
local function num(n, fallback) return finite(n) and n or (fallback or 0) end
local function quote(s)
    return '"' .. tostring(s):gsub('[%z\1-\31\\"]', function(c)
        local escapes = {['"']='\\"', ['\\']='\\\\', ['\n']='\\n', ['\r']='\\r', ['\t']='\\t'}
        return escapes[c] or string.format('\\u%04x', string.byte(c))
    end) .. '"'
end
function R.json(v, depth)
    depth = depth or 0
    if depth > 7 then return "null" end
    local kind = type(v)
    if kind == "nil" then return "null" end
    if kind == "boolean" then return v and "true" or "false" end
    if kind == "number" then return finite(v) and tostring(v) or "null" end
    if kind == "string" then return quote(v) end
    if kind ~= "table" then return "null" end
    local array = true
    for k in pairs(v) do if type(k) ~= "number" then array = false; break end end
    local out = {}
    if array then
        for _, item in ipairs(v) do out[#out+1] = R.json(item, depth+1) end
        return "[" .. table.concat(out, ",") .. "]"
    end
    local keys = {}
    for k in pairs(v) do if type(k) == "string" then keys[#keys+1] = k end end
    table.sort(keys)
    for _, k in ipairs(keys) do out[#out+1] = quote(k) .. ":" .. R.json(v[k], depth+1) end
    return "{" .. table.concat(out, ",") .. "}"
end
local function flag(fn)
    if type(fn) ~= "function" then return false end
    local ok, value = pcall(fn)
    return ok and value == true
end
local gameplayEpoch = 0
local function gameplay(m)
    if m == nil or m.marioObj == nil or (tonumber(m.health) or 0x880) <= 255 then return false end
    if flag(is_game_paused) or flag(djui_console_is_open) then return false end
    if type(get_current_play_mode) == "function" then
        local ok, mode = pcall(get_current_play_mode)
        if ok and mode ~= (PLAY_MODE_NORMAL or 0) then return false end
    end
    for _, name in ipairs({"ACT_READING_NPC_DIALOG", "ACT_READING_SIGN", "ACT_WAITING_FOR_DIALOG", "ACT_STAR_DANCE_EXIT", "ACT_STAR_DANCE_NO_EXIT", "ACT_INTRO_CUTSCENE"}) do
        if _G[name] ~= nil and m.action == _G[name] then return false end
    end
    return true
end
function R.gameplay(m)
    local allowed = gameplay(m)
    -- Main skips Director updates while paused/in dialogs. Invalidate jump
    -- observations even if the engine frame counter also stops during a pause.
    if not allowed then gameplayEpoch = gameplayEpoch + 1 end
    return allowed
end
local function hazard(surface)
    if surface == nil then return true end
    for _, name in ipairs({"SURFACE_BURNING", "SURFACE_DEATH_PLANE", "SURFACE_INSTANT_QUICKSAND", "SURFACE_DEEP_QUICKSAND", "SURFACE_DEEP_MOVING_QUICKSAND", "SURFACE_INSTANT_MOVING_QUICKSAND", "SURFACE_VERTICAL_WIND"}) do
        if _G[name] ~= nil and surface.type == _G[name] then return true end
    end
    return surface.normal ~= nil and num(surface.normal.y, 1) < 0.72
end
function R.floor(x, y, z)
    if type(find_floor) ~= "function" or not finite(x) or not finite(y) or not finite(z) then return nil end
    local ok, h, surface = pcall(find_floor, x, y+80, z)
    if not ok or not finite(h) or h <= -10000 or math.abs(h-y) > 96 or hazard(surface) then return nil end
    if type(find_water_level) == "function" then
        local okw, water = pcall(find_water_level, x, z)
        if okw and finite(water) and water > h+10 then return nil end
    end
    return h
end
function R.wallClear(x,y,z)
    if type(resolve_and_return_wall_collisions) ~= "function" then return false end
    for _,offset in ipairs({36,100}) do
        local scratch={x=x,y=y,z=z}
        local ok,wall=pcall(resolve_and_return_wall_collisions,scratch,offset,32)
        if not ok or wall~=nil or math.abs(scratch.x-x)>0.1 or math.abs(scratch.z-z)>0.1 then return false end
    end
    return true
end
function R.path(p, x, y, z)
    local dx,dz=x-p.x,z-p.z
    local length=math.sqrt(dx*dx+dz*dz)
    local steps=math.max(1,math.ceil(length/40))
    local sideX,sideZ=-dz/(length+0.001)*28,dx/(length+0.001)*28
    local previous=p.y
    for i=1,steps do
        local k=i/steps
        local px,pz=p.x+dx*k,p.z+dz*k
        local h=R.floor(px,previous,pz)
        if h==nil or h-previous>42 or previous-h>70 or not R.wallClear(px,h,pz) then return false end
        local left=R.floor(px+sideX,h,pz+sideZ)
        local right=R.floor(px-sideX,h,pz-sideZ)
        if left==nil or right==nil or math.abs(left-h)>36 or math.abs(right-h)>36 then return false end
        previous=h
    end
    return math.abs(previous-y)<70
end
function R.spots(p,m,trail,progress)
    local result={}
    local heading=num(m.faceAngle and m.faceAngle.y)*math.pi/32768
    local ms=math.sqrt(num(m.vel.x)^2+num(m.vel.z)^2)
    local fx,fz=math.sin(heading),math.cos(heading)
    if ms>3 then fx,fz=m.vel.x/ms,m.vel.z/ms end
    local goalX,goalZ=m.pos.x-fx*300+fz*130,m.pos.z-fz*300-fx*130
    local function add(x,z,kind,score)
        local y=R.floor(x,p.y,z)
        if y~=nil and R.path(p,x,y,z) then
            result[#result+1]={x=x,y=y,z=z,safe=true,landingSafe=true,clearance=100,kind=kind,score=score or 0}
            return true
        end
        return false
    end
    if ms>=12 then
        -- Predict a steering point, not a forced ahead-of-Mario actor position.
        -- Existing checked paths and ground integrator remain authoritative.
        local lead=math.min(400,ms*5)
        local side=((p.x-m.pos.x)*fz-(p.z-m.pos.z)*fx)<0 and -1 or 1
        add(m.pos.x+fx*lead+fz*150*side,m.pos.z+fz*lead-fx*150*side,"predictive_pace",100)
        add(m.pos.x+fx*lead-fz*150*side,m.pos.z+fz*lead+fx*150*side,"predictive_pace",90)
    end
    for i=1,10 do
        local angle=heading+(i-1)*math.pi*0.2
        local radius=320+(i%3)*80
        add(m.pos.x+math.sin(angle)*radius,m.pos.z+math.cos(angle)*radius,"flat",(i%3)*0.1)
    end
    -- Actual Mario trail supplies checked detours around corners. Never use old
    -- passed nodes or invent a straight path through intervening geometry.
    local nearest,nearestD=nil,math.huge
    for i,node in ipairs(trail or {}) do
        if node.seq>(progress or 0) then
            local d=(node.x-p.x)^2+(node.z-p.z)^2
            if d<nearestD and d<700*700 and R.path(p,node.x,node.y,node.z) then nearest,nearestD=i,d end
        end
    end
    if nearest then
        for i=nearest,math.min(#trail,nearest+5) do
            local node=trail[i]
            if node.seq>(progress or 0) then add(node.x,node.z,"route",100+i-nearest) end
        end
    end
    -- Small safe steps keep navigation progressing when a distant final goal
    -- cannot be seen from here. The director scores progress and recent visits.
    for i=1,16 do
        local angle=heading+(i-1)*math.pi/8
        local radius=240
        add(p.x+math.sin(angle)*radius,p.z+math.cos(angle)*radius,"rejoin_step",0)
    end
    return result
end
function R.ceilingClear(x,y,z)
    if type(find_ceil)~="function" then return false end
    local ok,h=pcall(find_ceil,x,y+10,z)
    return ok and finite(h) and h-y>=360
end
local function mario_motion_group(action)
    -- Native post-landing actions can retain a large downward velocity until
    -- the next ground step, after the next frame's jump-cancel opportunity.
    -- Whitelist the native groups/flags instead of guessing contact from vy.
    -- Unknown/missing constants and custom action contracts fail closed.
    if not finite(action) or action<=0 or action>0xFFFFFFFF or action%1~=0
        or ACT_GROUP_MASK~=0x1C0 or ACT_GROUP_STATIONARY~=0 or ACT_GROUP_MOVING~=0x40
        or ACT_GROUP_AIRBORNE~=0x80 or ACT_FLAG_STATIONARY~=0x200 or ACT_FLAG_MOVING~=0x400
        or ACT_FLAG_AIR~=0x800 or ACT_FLAG_SWIMMING~=0x2000 or ACT_FLAG_METAL_WATER~=0x4000
        or ACT_FLAG_CUSTOM_ACTION~=0x40000000 then return nil end
    if (action & (ACT_FLAG_SWIMMING | ACT_FLAG_METAL_WATER | ACT_FLAG_CUSTOM_ACTION))~=0 then return nil end
    local group=action & ACT_GROUP_MASK
    if (action & ACT_FLAG_AIR)==0 and
        ((group==ACT_GROUP_STATIONARY and (action & ACT_FLAG_STATIONARY)~=0)
        or (group==ACT_GROUP_MOVING and (action & ACT_FLAG_MOVING)~=0)) then return "ground" end
    if group==ACT_GROUP_AIRBORNE and (action & ACT_FLAG_AIR)~=0 then return "air" end
    return nil
end
function R.sensors(p,m,opts)
    opts = opts or {}
    local pos,vel = m.pos or {},m.vel or {}
    local paused = not R.gameplay(m)
    local frame
    if type(get_global_timer)=="function" then
        local ok,value=pcall(get_global_timer)
        if ok and finite(value) and value%1==0 then frame=value end
    end
    local marioGroup=mario_motion_group(m.action)
    local floorType=type(m.floor)
    local marioMotionValid = m.marioObj~=nil and frame~=nil and marioGroup~=nil
        and (floorType=="userdata" or floorType=="table")
        and finite(pos.x) and finite(pos.y) and finite(pos.z)
        and finite(vel.x) and finite(vel.y) and finite(vel.z)
        and finite(m.floorHeight) and m.floorHeight>-10000
    local aboveFloor = marioMotionValid and pos.y-m.floorHeight or nil
    local heading = num(p.yaw)
    local speed = math.sqrt(num(p.vx)^2+num(p.vz)^2)
    local fx, fz = math.sin(heading), math.cos(heading)
    if speed > 1 then fx,fz = p.vx/speed,p.vz/speed end
    local ahead = R.floor(p.x+fx*90,p.y,p.z+fz*90)
    local landingDistance = math.max(160, speed*23)
    local landingX,landingZ = p.x+fx*landingDistance,p.z+fz*landingDistance
    local landing = R.floor(landingX,p.y,landingZ)
    local safe = p.onGround ~= true or R.floor(p.x,p.y,p.z) ~= nil
    return {scene=opts.scene,enabled=opts.enabled,paused=paused,dead=opts.dead,manual=opts.manual,
        x=p.x,y=p.y,z=p.z,marioX=pos.x,marioY=pos.y,marioZ=pos.z,
        marioSpeed=math.sqrt(num(vel.x)^2+num(vel.z)^2),marioVX=num(vel.x),marioVZ=num(vel.z),speed=speed,grounded=p.onGround==true,
        marioMotionValid=marioMotionValid,marioFrame=frame,marioInstance=m.marioObj,
        marioObservationEpoch=gameplayEpoch,marioVY=vel.y,marioFloorHeight=m.floorHeight,
        marioGrounded=marioMotionValid and marioGroup=="ground" and math.abs(aboveFloor)<=4 and vel.y<=4,
        marioRising=marioMotionValid and marioGroup=="air" and aboveFloor>4 and vel.y>4,
        inWater=opts.inWater==true,onLava=opts.onLava==true,floorSafe=safe,
        forwardSafe=ahead~=nil and ahead-p.y<42 and p.y-ahead<70,
        landingSafe=landing~=nil and R.path(p,landingX,landing or p.y,landingZ) and R.ceilingClear(p.x,p.y,p.z) and R.ceilingClear(landingX,landing or p.y,landingZ),
        blocked=opts.blocked==true,justLanded=opts.justLanded==true,justBailed=opts.justBailed==true,
        spots=opts.spots or {},targetSafe=opts.targetSafe}
end
local C = {}; C.__index = C
function R.new()
    return setmetatable({epoch=0,seq=0,lastEmit=-999,history={},spoken={},last_decision="",decision_status="none",tricks_attempted=0,tricks_landed=0,bails=0,catch_up_resets=0},C)
end
function C:reset()
    self.epoch=self.epoch+1; self.history={}; self.spoken={}; self.lastEvent="level_enter"
    self.last_decision=""; self.decision_status="none"; self.lastEmit=-999
end
function C:scene(np)
    np=np or {}
    return string.format("%d:%d:%d:%d",num(np.currLevelNum),num(np.currAreaIndex),num(np.currActNum),self.epoch)
end
function C:note(kind,t)
    if self.history[#self.history] and self.history[#self.history].kind==kind and t-self.history[#self.history].t<0.3 then return end
    self.history[#self.history+1]={kind=tostring(kind):sub(1,40),t=t}
    if #self.history>8 then table.remove(self.history,1) end
    self.lastEvent=kind
    if kind=="trick_attempt" then self.tricks_attempted=self.tricks_attempted+1 end
    if kind=="trick_ollie" or kind=="trick_kickflip" then self.tricks_landed=self.tricks_landed+1 end
    if kind=="death_board" or kind=="death_fall" then self.bails=self.bails+1 end
    if kind=="catch_up" then self.catch_up_resets=self.catch_up_resets+1 end
end
function C:speech(meta,event,seconds,t)
    self.spoken[#self.spoken+1]={event=event,text=tostring(meta and meta.text or ""):sub(1,150),text_status=meta and meta.text_status,t=t,seconds=seconds}
    if #self.spoken>4 then table.remove(self.spoken,1) end
end
function C:emit(data,t,output)
    if t-self.lastEmit<0.95 then return false end
    self.seq=self.seq+1; self.lastEmit=t
    data.v=1; data.seq=self.seq; data.event=self.lastEvent or "none"
    data.tricks_attempted=self.tricks_attempted; data.tricks_landed=self.tricks_landed; data.bails=self.bails; data.catch_up_resets=self.catch_up_resets
    data.last_decision=self.last_decision; data.decision_status=self.decision_status
    data.history={}; data.spoken={}
    for _,ev in ipairs(self.history) do data.history[#data.history+1]={kind=ev.kind,age=math.max(0,t-ev.t)} end
    for _,ev in ipairs(self.spoken) do data.spoken[#data.spoken+1]={event=ev.event,text=ev.text,text_status=ev.text_status,age=math.max(0,t-ev.t)} end
    output("[jimmie-state] " .. R.json(data)); return true
end
function C:validate(payload,scene,quiet,manual)
    if type(payload)~="table" then return false,"invalid" end
    local id=payload.id
    if type(id)~="string" or #id<1 or #id>80 or not id:match("^[%w%-]+$") then return false,"invalid-id" end
    if id==self.last_decision then return false,"duplicate" end
    local reason
    if payload.v~=1 or payload.name~="director" then reason="version"
    elseif payload.scene~=scene then reason="scene"
    elseif not finite(payload.seq) or payload.seq%1~=0 or payload.seq>self.seq or self.seq-payload.seq>8 then reason="stale"
    elseif not finite(payload.expires_seq) or payload.expires_seq<self.seq or payload.expires_seq>payload.seq+8 then reason="expired"
    elseif quiet or (manual and payload.intent~="none") then reason="manual-or-quiet"
    elseif payload.intent~="none" and payload.intent~="roam" and payload.intent~="showoff" and payload.intent~="rejoin" then reason="intent"
    elseif payload.clip~=nil and (type(payload.clip)~="string" or not payload.clip:match("^[%w_]+%.ogg$")) then reason="clip"
    end
    self.last_decision=id; self.decision_status=reason and "rejected" or "accepted"
    return reason==nil,reason or "valid"
end
return R
