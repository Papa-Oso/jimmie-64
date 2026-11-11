-- Behavior modes are independent of PB eligibility and of Jimmie's voice-density settings.
local M = {}
function M.new()
    local self = {}
    local selected, active, finished = "auto", false, false
    local quick, opening, wall, blue = false, false, false, false
    local groundsAt, doorSeen, reason
    local early = {bob_chain=true,wf_wall=true,wf_blue=true,wf_king=true,wf_tower=true,wf_cage=true,ccm_wall=true,ccm_penguin=true}
    function self.reset()
        active, finished, quick, opening, wall, blue = false, false, false, false, false, false
        selected = "auto"
        groundsAt, doorSeen, reason = nil, false, nil
    end
    function self.select(choice)
        if choice ~= "auto" and choice ~= "16" and choice ~= "free" then return false end
        selected = choice
        return true
    end
    function self.update(door_hint, stars)
        if door_hint == "speedrun" then quick = true end
        if type(stars)=="number" and stars>16 then finished = true end
    end
    function self.location(level,area,ms,stars)
        if groundsAt and stars==16 and (level==21 or level==34) then
            active,reason=true,"final_stage_at_sixteen"
        end
        if doorSeen then return end
        if level==16 and area==1 and stars==0 then
            groundsAt=groundsAt or ms
        elseif groundsAt and level==6 and area==1 then
            quick=quick or (stars==0 and ms>=groundsAt and ms-groundsAt<=20000)
            doorSeen=true
        elseif groundsAt and level~=16 then
            doorSeen=true
        end
    end
    function self.receipt(receipt, stars)
        if receipt.progress ~= "new" or not groundsAt then return end
        local id = receipt.completed_reference_objective_id
        if id == "bob_chain" and stars == 1 then opening = true end
        if opening and id == "wf_wall" and stars <= 3 then wall = true end
        if opening and id == "wf_blue" and stars <= 3 then blue = true end
        -- A slow castle entry can still be corroborated by three distinct early objectives.
        if quick and early[id] and stars==1 then active,reason=true,"quick_door_and_early_objective"
        elseif opening and wall and blue then active,reason=true,"three_early_route_receipts" end
    end
    function self.finish() finished = true end
    function self.current()
        if finished then return "free",selected,"route_ended" end
        if selected=="free" then return "free",selected,"player_choice" end
        if selected=="16" then return "16",selected,"player_choice" end
        if active then return "16",selected,reason end
        return "free",selected,"insufficient_route_evidence"
    end
    return self
end
return M
