-- Read-only water-entry observations. No motion, audio, RNG, or playback budget.
-- Known no-water samples can establish a conservative shoreline approach.
local M = {}
local Observer = {}; Observer.__index = Observer
local EPS = 0.0000001
local function finite(v) return type(v)=="number" and v==v and v > -math.huge and v < math.huge end
local function known_kind(kind) return kind=="mario" or kind=="companion" end
local function baseline(object,scene,x,y,z,waterLevel,t)
    local hasWater=waterLevel > -10000
    local wet=hasWater and y<waterLevel-15
    local dryTrail=not wet and {{t=t,y=y}} or nil
    return {object=object,scene=scene,x=x,y=y,z=z,water=hasWater and waterLevel or nil,t=t,
        wet=wet,seenWet=wet,drySince=not wet and t or nil,armed=false,
        dryTrail=dryTrail,noWaterTrail=not hasWater and dryTrail or nil}
end
-- At most 256 recent samples. Include the sample just before the window so
-- an interpolation gap cannot manufacture an observed dry interval.
local function add_no_water(trail,t,y)
    trail=trail or {}; trail[#trail+1]={t=t,y=y}
    while #trail>2 and trail[2].t<t-1.2 do table.remove(trail,1) end
    while #trail>256 do table.remove(trail,1) end
    return trail
end
local function trail_start_above(trail,waterLevel)
    if not trail or #trail==0 then return nil end
    local first=#trail+1
    for i=#trail,1,-1 do
        if trail[i].y<waterLevel-15 then break end
        first=i
    end
    return first<=#trail and trail[first].t or nil
end
function M.new() return setmetatable({slots={},lastEntryAt=nil,lastEntryScene=nil},Observer) end
function Observer:reset(kind)
    if kind==nil then self.slots={};self.lastEntryAt=nil;self.lastEntryScene=nil
    elseif known_kind(kind) then self.slots[kind]=nil end
end
function Observer:observe(kind,object,scene,x,y,z,waterLevel,t,alive)
    if not known_kind(kind) then return false end
    local objectType=type(object)
    if alive~=true or (objectType~="table" and objectType~="userdata") or type(scene)~="string" or scene==""
        or not finite(x) or not finite(y) or not finite(z) or not finite(waterLevel) or not finite(t) or t<0 then
        self:reset(kind);return false
    end
    local previous=self.slots[kind]
    if not previous or previous.object~=object or previous.scene~=scene then
        self.slots[kind]=baseline(object,scene,x,y,z,waterLevel,t);return false
    end
    local dt=t-previous.t;local dx,dy,dz=x-previous.x,y-previous.y,z-previous.z
    if dt<=0 or dt>0.2+EPS or dx*dx+dy*dy+dz*dz>180*180 then
        self.slots[kind]=baseline(object,scene,x,y,z,waterLevel,t);return false
    end
    local hasWater=waterLevel>-10000;local wet=hasWater and y<waterLevel-15
    local required=previous.seenWet and 1.0 or 0.3
    local trailThrough=wet and previous.t or t
    local aboveStart=hasWater and trail_start_above(previous.noWaterTrail,waterLevel) or nil
    local verifiedStart=aboveStart and trailThrough-aboveStart+EPS>=required and aboveStart or nil
    local wasArmed=previous.armed
    if hasWater and previous.noWaterTrail then wasArmed=verifiedStart~=nil end
    local entered=wet and not previous.wet and wasArmed and dy<0 and previous.y>=waterLevel-15
    previous.x,previous.y,previous.z,previous.water,previous.t=x,y,z,hasWater and waterLevel or nil,t
    if wet then
        previous.seenWet=true;previous.drySince=nil;previous.armed=false;previous.noWaterTrail=nil;previous.dryTrail=nil
    else
        if previous.wet or previous.drySince==nil then previous.drySince=t end
        previous.dryTrail=add_no_water(previous.dryTrail,t,y)
        -- A dry sample just inside a new box can inherit only a fully observed,
        -- above-surface interval; otherwise rearm from this sample.
        if hasWater and previous.noWaterTrail then
            previous.drySince=aboveStart or t
            previous.noWaterTrail=nil
        elseif not hasWater then previous.noWaterTrail=previous.dryTrail end
        local dryRequired=previous.seenWet and 1.0 or 0.3
        previous.armed=t-previous.drySince+EPS>=dryRequired
    end
    previous.wet=wet
    if not entered then return false end
    local since=self.lastEntryAt and t-self.lastEntryAt
    if self.lastEntryScene==scene and since and since>=0 and since<=0.2+EPS then return false end
    self.lastEntryAt,self.lastEntryScene=t,scene;return true
end
return M
