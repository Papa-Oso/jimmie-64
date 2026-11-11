-- Pure presentation-only prototype. No hooks, globals, collision or PHYS writes.
-- Source anchors: original board mesh truck underside edges, balance042, scale .62.
local M = {}
local HALF = 35.34
local MAX_OFFSET = 32
local CONTACT_TOLERANCE = 0.12
local function finite(n)
    return type(n) == 'number' and n == n and n > -math.huge and n < math.huge
end
local function point(p)
    return type(p) == 'table' and finite(p.x) and finite(p.y) and finite(p.z)
        and math.abs(p.x) <= 32768 and math.abs(p.y) <= 32768 and math.abs(p.z) <= 32768
end
local function v(x,y,z) return {x=x,y=y,z=z} end
local function sub(a,b) return v(a.x-b.x,a.y-b.y,a.z-b.z) end
local function dot(a,b) return a.x*b.x+a.y*b.y+a.z*b.z end
local function mul(a,k) return v(a.x*k,a.y*k,a.z*k) end
local function add(a,b) return v(a.x+b.x,a.y+b.y,a.z+b.z) end
local function norm(a) return math.sqrt(dot(a,a)) end
local function reject(reason) return {ok=false,reason=reason} end
local function angle(n)
    return finite(n) and n == math.floor(n) and n >= -32768 and n <= 65535
end
local function radians(n)
    -- Engine sins/coss index is (u16)angle >> 4, not full s16 precision.
    return math.floor((n % 65536)/16)*2*math.pi/4096
end

-- Pure smooth entry/exit envelope. entry/exit are independent normalized ramps:
-- 0 means absent; 1 means complete. Caller supplies phase/identity continuity.
function M.blend(entry,exit)
    if not finite(entry) or not finite(exit) or entry < 0 or entry > 1 or exit < 0 or exit > 1 then
        return nil,'invalid-blend'
    end
    local function smooth(t) return t*t*(3-2*t) end
    return math.min(smooth(entry),smooth(exit))
end

-- args: root, rail={a,b,verified=true}, heading/incline radians, native={yaw,pitch,roll},
-- clip exact board animation name, blend [0,1], optional safetyMargin >= 0.
-- Verified means caller has current visual-top evidence, not collision validity.
function M.compute(a)
    if type(a) ~= 'table' then return reject('invalid-input') end
    if not point(a.root) then return reject('invalid-root') end
    local rail = a.rail
    if type(rail) ~= 'table' or rail.verified ~= true then return reject('unverified-rail') end
    if not point(rail.a) or not point(rail.b) then return reject('invalid-segment') end
    if a.clip ~= 'jimmie_original_v1_board_balance042'
        and a.clip ~= 'jimmie_stock_v1_board_reverse_balance042'
        and not (JIMMIE_GRIND_BOARDS ~= nil and JIMMIE_GRIND_BOARDS[a.clip] == true) then return reject('unsupported-clip') end
    if not finite(a.blend) or a.blend < 0 or a.blend > 1 then return reject('invalid-blend') end
    if not finite(a.heading) or math.abs(a.heading) > 2*math.pi
        or not finite(a.incline) or math.abs(a.incline) > math.pi/3 then return reject('invalid-travel') end
    local n = a.native
    if type(n) ~= 'table' or not angle(n.yaw) or not angle(n.pitch) or not angle(n.roll) then
        return reject('invalid-native-angles')
    end
    if n.pitch % 65536 ~= 0 then return reject('unsupported-bank') end
    local margin = a.safetyMargin
    if margin == nil then margin = 2 end
    if not finite(margin) or margin < 0 or margin > 32 then return reject('invalid-margin') end
    local line = sub(rail.b,rail.a)
    local length = norm(line)
    if length < 1e-6 then return reject('degenerate-segment') end
    local unit = mul(line,1/length)
    if math.sqrt(unit.x*unit.x+unit.z*unit.z) < .5 then return reject('incompatible-slope') end
    local inset = HALF+margin
    if length < 2*inset then return reject('segment-too-short') end
    local travel = v(math.sin(a.heading)*math.cos(a.incline),math.sin(a.incline),
        math.cos(a.heading)*math.cos(a.incline))
    -- Segment may be reversed. Travel orientation and object orientation may not.
    if HALF*norm(sub(travel,mul(unit,dot(travel,unit)))) > CONTACT_TOLERANCE then
        return reject('travel-misaligned')
    end
    local yaw,roll = radians(n.yaw),radians(n.roll)
    local cy,sy,cr,sr = math.cos(yaw),math.sin(yaw),math.cos(roll),math.sin(roll)
    local axis = v(cy*cr,sr,-sy*cr)
    if dot(axis,travel) < math.cos(.0034) then return reject('native-misaligned') end
    local axisAlong = dot(axis,unit)
    local residual = HALF*norm(sub(axis,mul(unit,axisAlong)))
    if residual > CONTACT_TOLERANCE then return reject('truck-contact-residual') end
    local along = dot(sub(a.root,rail.a),unit)
    -- Do not clamp to the endpoint: a nonlocal anchor must be rejected.
    if along < inset or along > length-inset then return reject('outside-contact-interior') end
    local center = add(rail.a,mul(unit,along))
    -- Local mean truck point (0,+3.10,-3.10) includes clip translation.
    -- Reverse rotates the mesh, not its root translation, so mean is unchanged.
    local anchor = v(-3.1*cy*sr-3.1*sy,3.1*cr,3.1*sy*sr-3.1*cy)
    local full = sub(sub(center,a.root),anchor)
    if math.sqrt(full.x*full.x+full.z*full.z) > MAX_OFFSET or math.abs(full.y) > MAX_OFFSET then
        return reject('offset-out-of-bounds')
    end
    local delta = mul(full,a.blend)
    local presented = add(a.root,delta)
    local truckCenter = add(presented,anchor)
    local truckA,truckB = add(truckCenter,mul(axis,-HALF)),add(truckCenter,mul(axis,HALF))
    local function segmentDistance(p)
        local t = math.max(0,math.min(length,dot(sub(p,rail.a),unit)))
        return norm(sub(p,add(rail.a,mul(unit,t))))
    end
    return {
        ok=true,reason=a.blend == 1 and 'full-blend' or 'blending',
        delta=delta,fullDelta=full,root=presented,contactCenter=center,
        truckCenter=truckCenter,axis=axis,
        truckA=truckA,
        truckB=truckB,
        maxTruckResidual=math.max(segmentDistance(truckA),segmentDistance(truckB)),
        fullBlendTruckResidual=residual,contactTolerance=CONTACT_TOLERANCE,
        -- Exact CENTER contact is an algebraic claim, only at blend=1.
        -- Two-truck contact is tolerance-limited by native angle quantization.
        centerContact=a.blend == 1,
        exactTruckContact=a.blend == 1 and residual < 1e-8,
        inset=inset,along=along,length=length,
    }
end

-- Fresh equal values avoid accidental aliasing between body/board/brace callers.
-- Apply each to its immutable physical root; never add to prior gfx output.
function M.paired(result)
    if type(result) ~= 'table' or result.ok ~= true or not point(result.delta)
        or math.sqrt(result.delta.x^2+result.delta.z^2) > 32 or math.abs(result.delta.y) > 32 then
        return nil,'invalid-result'
    end
    local d = result.delta
    return {body=v(d.x,d.y,d.z),board=v(d.x,d.y,d.z),brace=v(d.x,d.y,d.z)}
end
return M
