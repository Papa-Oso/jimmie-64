-- Native eligibility for a recording whose use is limited to this particular recovery.
local M={}

function M.matches(item,history)
    if item.beat~="star_hype" or item.fact~="course_star" or item.actor~="mario" or item.mode~="16"
        or item.level~=24 or item.area~=1 or type(item.scene)~="string" or not item.scene:match("^24/1/[1-6]$")
        or type(item.frame)~="number" or type(item.fact_id)~="string" or item.fact_id=="" then return false end
    local fall,setup,last,previousFrame
    for _,event in ipairs(history) do
        local f=event.frame
        if event.actor=="mario" and event.mode=="16" and event.level==24 and event.visit==item.visit
            and event.epoch==item.epoch and event.slot==item.slot and event.generation==item.generation
            and type(f)=="number" and item.frame-f<=900 then
            if f>item.frame then return false end
            if previousFrame and f<previousFrame then return false end
            previousFrame,last=f,event
            if event.objective=="wf_wall" and f<item.frame then
                if event.kind=="fell_below_setup" then
                    fall,setup=f,nil
                elseif event.kind=="wall_setup" and fall and f>fall then
                    setup=f
                end
            end
        end
    end
    return setup~=nil and last~=nil and last.frame==item.frame and last.kind=="course_star" and last.id==item.fact_id
        and last.course==2 and last.area==1 and last.mission==6 and last.objective=="wf_wall"
end

return M
