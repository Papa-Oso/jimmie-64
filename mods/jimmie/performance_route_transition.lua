-- Reference goals can change inside the stock interaction hook, before the next update.
local Transition = {}

local function rabbitGoal(id)
    return id=="verify_mips_clip" or id=="mips_unavailable" or id=="mips_clip"
end

function Transition.describe(event, objective, before, after, stars)
    if event.progress~="new" or not event.id or not after then return nil end
    local row={fact_id=event.id, before=before, after=after, earned=objective,
               matched=event.completed_reference_objective_id}
    if event.kind~="course_star" and event.kind~="secret_star" then return row end
    if stars==15 and rabbitGoal(after) then
        row.beat="rabbit_ahead"
    elseif stars==16 and event.kind=="course_star" and event.course==9 and event.level==23
            and event.star_id==1 and objective=="ddd_sub" and row.matched=="ddd_sub"
            and before=="ddd_sub" and after=="second_key" then
        row.beat="submarine_earned"
    elseif stars==16 and objective~="ddd_sub" and (after=="ddd_sub" or rabbitGoal(after)) then
        row.beat="submarine_outstanding"
    end
    return row
end

function Transition.choose(token, reason, item)
    local row=item.transition
    if not row or not row.beat then return token,reason end
    if row.fact_id~=item.fact_id then return "S","stale_fact" end
    -- Keep heard-audio, scope and recovery decisions from the existing native bank.
    if token~="A" or item.take then return token,reason end
    if row.beat=="submarine_earned" then return "A",row.beat end
    return "S",row.beat
end

return Transition
