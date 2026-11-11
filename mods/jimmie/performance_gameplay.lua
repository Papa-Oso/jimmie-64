-- Attach evidence only at the native movement and idle call sites in the private candidate.
local Module={}
local facts={
    skate_recovery={fact="trick_completed",actor="jimmie"},
    trick_attempt={fact="trick_takeoff",actor="jimmie"},
    trick_ollie={fact="trick_landed",actor="jimmie"},
    trick_kickflip={fact="trick_landed",actor="jimmie"},
    idle_long={fact="mario_stationary",actor="mario"},
}

local function stationary()
    local m=gMarioStates[0]
    return m and m.vel and m.action and (m.action & (ACT_FLAG_AIR | ACT_FLAG_INTANGIBLE))==0
        and math.abs(m.vel.x)<2 and math.abs(m.vel.y)<2 and math.abs(m.vel.z)<2
end

function Module.bind(scope, director, skating)
    local issue=scope.bind("gameplay")
    return function(event, fact, record)
        local expected=facts[event]
        if not expected or expected.fact~=fact or event=="idle_long" and not stationary() then return nil end
        local landing=event=="skate_recovery" or event=="trick_ollie" or event=="trick_kickflip"
        if landing and (not skating.valid(record) or (event=="skate_recovery" and record.condition~="landing_after_getup")) then return nil end
        local route=director()
        local w=route and route.performanceContext()
        if not w then return nil end
        local frame=get_global_timer()
        local started=jimmie_route_now_ms()
        w.actor,w.event,w.fact=expected.actor,event,fact
        w.fact_id=string.format("%s:%d:%d",event,w.visit,frame)
        if landing then w.condition=record.condition;w.fact_id="skate/"..w.visit.."/"..record.id end
        return issue(w,function()
            local current=route.performanceContext()
            if not current or current.generation~=w.generation or current.visit~=w.visit or current.epoch~=w.epoch
                or current.slot~=w.slot or current.mode~=w.mode or current.scene~=w.scene then return false end
            local elapsed=jimmie_route_now_ms()-started
            return (not landing or skating.valid(record)) and elapsed>=0 and elapsed<=320 and (event~="idle_long" or stationary())
        end)
    end
end

return Module
