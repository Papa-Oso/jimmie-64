-- Finish an already-started route take during its own local star dance.
local Module={}

function Module.new(voice)
    local active
    local self={}
    local function current()
        return active and voice.currentEvent=="star" and voice.currentSnd==active.sound and voice.played==active.serial
    end
    function self.started(item,sound)
        active={sound=sound,serial=voice.played,mode=item.mode,epoch=item.epoch,slot=item.slot,
                generation=item.generation,visit=item.visit,scene=item.scene}
    end
    function self.sound(m,ctx)
        if not current() or not ctx or not m or m.playerIndex~=0 or m.health<=255 or not voice.busy()
            or not voice.available() or voice.distance()>1400 or (djui_console_is_open and djui_console_is_open())
            or (m.action~=ACT_STAR_DANCE_EXIT and m.action~=ACT_STAR_DANCE_NO_EXIT) then return nil end
        if ctx.mode~=active.mode or ctx.epoch~=active.epoch or ctx.slot~=active.slot or ctx.generation~=active.generation
            or ctx.visit~=active.visit or ctx.scene~=active.scene then return nil end
        return active.sound
    end
    function self.clear()
        if current() then voice.clearScene(true) end
        active=nil
    end
    return self
end

return Module
