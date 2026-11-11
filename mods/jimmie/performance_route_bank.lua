-- A finite local choice for a witnessed route event while the model is unavailable or late.
local Bank={}

local function latest(item,history)
    for i=#history,1,-1 do
        local fact=history[i]
        if fact.actor==item.actor and fact.mode==item.mode and fact.visit==item.visit
            and fact.generation==item.generation and fact.slot==item.slot and fact.epoch==item.epoch
            and fact.level==item.level then
            if fact.id==item.fact_id and fact.kind==item.fact and fact.area==item.area then return fact end
            return nil
        end
    end
end

function Bank.choose(item,history,heard,hash,stars,nowMs,recovery)
    if type(item)~="table" or type(history)~="table" or type(heard)~="table" or type(nowMs)~="number"
        or item.mode~="16" or item.actor~="mario" or type(hash)~="string" or #hash~=64
        or type(item.frame)~="number" or type(item.visit)~="number" or item.visit<1
        or type(item.fact_id)~="string" or item.fact_id=="" or type(stars)~="number" or stars<0 or stars>16 then
        return "S","invalid_context"
    end
    local fact=latest(item,history)
    if not fact or type(fact.frame)~="number" or fact.frame>item.frame then return "S","stale_fact" end
    if item.beat=="castle_door" or item.beat=="bowser_entrance" then
        local expected=item.beat=="castle_door" and 6 or 21
        if fact.kind=="segment_entered" and item.level==expected and item.area==1 then return "A","entrance" end
        return "S","invalid_context"
    end
    if item.beat~="star_hype" or fact.frame~=item.frame or (fact.kind~="course_star" and fact.kind~="secret_star")
        or stars<1 then return "S","invalid_context" end

    local last=heard[#heard]
    if last and last.hash==hash and type(last.time)=="number" and nowMs>=last.time and nowMs-last.time<=120000 then
        return "S","already_heard"
    end
    if recovery then return "A","wall_recovery" end
    if item.take then return "S","stale_fact" end
    if stars==16 then return "A","sixteenth_star" end
    if fact.kind=="course_star" and fact.course==2 and fact.mission==6 and item.level==24 and item.area==1 then
        if fact.objective~="wf_wall" then return "S","invalid_context" end
        return "S","ordinary_wall"
    end
    return "A","other_star"
end

return Bank
