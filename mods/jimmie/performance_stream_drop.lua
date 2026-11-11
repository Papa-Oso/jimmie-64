-- Play the two owner-named stream bits only from the trusted water observer.
local M={}

function M.new(voice,director,clips,clock,log)
    local issue=voice.performanceScope.bind("stream_drop")
    local sounds={}
    local heard=nil
    for id,clip in pairs(clips) do
        local snd=voice.performanceScope.load(clip.file)
        if snd then voice.register(snd,clip.file);sounds[id]=snd end
    end
    return function(row)
        if row.mode~="free" or row.fact~="water_enter" or voice.mode=="silent" or voice.busy() then return false end
        local callback=heard and row.previous_id==heard.id and row.previous_actor~=row.actor
            and heard.variant=="question" and row.since_previous_ms and row.since_previous_ms<=8000
        if not callback and (voice.now()-voice.lastWater<voice.WATER_GAP
                or heard and clock()-heard.time<voice.WATER_GAP*1000) then return false end
        local id=callback and "bees" or row.actor=="jimmie" and "whole" or "question"
        local clip,sound=clips[id],sounds[id]
        if not sound then return false end
        local which=row.actor=="mario" and "mario" or "companion"
        local source=voice.waterSubjects[which]
        if not source then return false end
        local token,subject=source.token,source.subject
        local function live()
            local w=director.performanceContext()
            local water=voice.waterSubjects[which]
            local age=clock()-row.qpc_ms
            return w and w.mode=="free" and w.epoch==row.epoch and w.slot==row.slot and w.generation==row.generation
                and w.visit==row.visit and w.scene==row.scene and water and water.token==token and water.subject==subject
                and water.scene==row.water_scene and water.wet and voice.available() and voice.distance()<=1400 and age>=0 and age<=320
        end
        if not live() then return false end
        local grant=issue({epoch=row.epoch,slot=row.slot,generation=row.generation,visit=row.visit,level=row.level,area=row.area,
            actor=row.actor,mode=row.mode,event="water_stream_drop",fact=row.fact,fact_id=row.id,condition=id,audio_sha256=clip.hash},live)
        if not grant then return false end
        return voice.external(sound,clip.seconds,{event="water_stream_drop",key=clip.file,text=clip.label,
            maxDistance=1400,volume=1.0,priority=60,ttl=.32,valid=live,
            onPlay=function()
                heard={id=row.id,variant=id,time=clock()}
                voice.lastWater=voice.now()
                log({fact_id=row.id,actor=row.actor,visit=row.visit,mode=row.mode,variant=id,file=clip.file,hash=clip.hash,
                     credit="stream_clip",ms=clock()-row.qpc_ms,previous_id=row.previous_id})
            end},grant)
    end
end

return M
