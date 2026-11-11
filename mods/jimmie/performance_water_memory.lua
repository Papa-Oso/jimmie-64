-- A witnessed shoreline crossing for the free-exploration dialogue editor.
local M={}
local scope={"epoch","slot","generation","visit","scene","body","board","physicalScene"}

local function same(previous,current)
    if not previous then return false end
    for _,key in ipairs(scope) do
        if current[key]==nil or current[key]~=previous[key] then return false end
    end
    return true
end

function M.bind(context,log)
    local last,serial=nil,0
    return function(kind,subject,waterScene,x,y,z,surface)
        local w=context(kind,subject)
        if not w or w.mode~="free" or not w.nearby or (w.actor~="mario" and w.actor~="jimmie")
                or type(surface)~="number" or surface<=-10000 or y>=surface-15 then return end
        local prior=same(last,w) and last.record or nil
        if prior and (w.frame<=prior.frame or w.qpc_ms<prior.qpc_ms) then return end
        serial=serial+1
        local row={id=string.format("water/%d/%d/%d/%d/%d",w.slot,w.epoch,w.generation,w.visit,serial),
            fact="water_enter",source="water_reaction.observe",actor=w.actor,mode=w.mode,slot=w.slot,epoch=w.epoch,
            generation=w.generation,visit=w.visit,scene=w.scene,physical_scene=w.physicalScene,water_scene=waterScene,
            level=w.level,area=w.area,frame=w.frame,qpc_ms=w.qpc_ms,x=x,y=y,z=z,surface=surface,distance=w.distance}
        if prior then
            row.previous_id,row.previous_actor,row.since_previous_ms=prior.id,prior.actor,w.qpc_ms-prior.qpc_ms
        end
        w.record=row
        last=w
        return log(row)
    end
end

return M
