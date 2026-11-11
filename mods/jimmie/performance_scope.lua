-- Private performance permissions. The trusted event owner keeps the issuer.
-- A model choice, file label or call to the audio helper cannot create a witness.
local Module = {}

local function basename(value)
    if type(value) ~= "string" then return nil end
    local tail = value:gsub("\\", "/"):match("([^/]+)$")
    return tail and tail:lower()
end

local function whole(value, floor)
    return type(value)=="number" and value>=floor and value<math.huge and value%1==0
end

function Module.new(data)
    local permits = {}
    local issued = setmetatable({}, {__mode="k"})
    local loaded = setmetatable({}, {__mode="k"})
    local bound = {}

    function permits.load(name)
        if name~=basename(name) or not data.listening_audio[data.files[name]] then return nil end
        local snd=audio_sample_load(name)
        if snd then loaded[snd]=name end
        return snd
    end

    function permits.sound_name(sound, registration)
        local actual = loaded[sound]
        local registered = basename(registration)
        if not actual or registered and data.files[registered]~=data.files[actual] then return nil end
        return actual
    end

    local function matches(use, w, origin, event)
        return use.origin==origin and use.event==event and use.actor==w.actor and use.mode==w.mode
            and (origin=="route" or w.event==event)
            and (not use.condition or use.condition==w.condition) and use.fact==w.fact and (not use.beat or use.beat==w.beat) and use.take==w.take
            and (not use.level or use.level==w.level) and (not use.area or use.area==w.area)
    end

    function permits.route_eligible(w)
        local beat=w.take and w.take==data.recovery.id and data.recovery or data.beats[w.beat]
        if w.take and (w.take~=data.recovery.id or w.beat~="star_hype" or w.condition~="wall_recovery") then return false end
        if not beat or data.veto[beat.file] or data.veto[beat.hash] then return false end
        for _,use in ipairs(data.managed[beat.hash] or {}) do
            if matches(use,w,"route",beat.event) then return true end
        end
        return false
    end

    function permits.bind(origin)
        if (origin~="route" and origin~="gameplay" and origin~="stream_drop") or bound[origin] then error("invalid performance issuer") end
        bound[origin]=true
        local scope,seen,recent=nil,{},{}
        return function(witness, live)
            if type(witness)~="table" or type(live)~="function" or type(witness.fact)~="string"
                or (witness.actor~="mario" and witness.actor~="jimmie") or (witness.mode~="16" and witness.mode~="free")
                or type(witness.fact_id)~="string"
                or witness.fact_id=="" or not whole(witness.epoch,0) or not whole(witness.slot,1) or witness.slot>4
                or not whole(witness.generation,0) or not whole(witness.visit,1)
                or not whole(witness.level,1) or not whole(witness.area,1) then return nil end
            if origin=="route" and not permits.route_eligible(witness) then return nil end
            if origin=="gameplay" and (type(witness.event)~="string" or witness.event=="") then return nil end
            if origin=="stream_drop" and (witness.mode~="free" or witness.event~="water_stream_drop"
                or witness.fact~="water_enter" or not data.managed[witness.audio_sha256]) then return nil end
            local key=table.concat({witness.epoch,witness.slot,witness.generation,witness.visit},"/")
            if scope~=key then scope,seen,recent=key,{},{} end
            local id=witness.fact.."/"..witness.fact_id
            if seen[id] then return nil end
            seen[id]=true
            recent[#recent+1]=id
            if #recent>64 then seen[table.remove(recent,1)]=nil end
            local token={}
            issued[token]={origin=origin,live=live,actor=witness.actor,mode=witness.mode,event=witness.event,fact=witness.fact,
                fact_id=witness.fact_id,condition=witness.condition,beat=witness.beat,take=witness.take,level=witness.level,area=witness.area,
                visit=witness.visit,epoch=witness.epoch,generation=witness.generation,slot=witness.slot,
                target=origin=="route" and (witness.take and data.recovery.hash or data.beats[witness.beat].hash) or nil}
            if origin=="stream_drop" then issued[token].target=witness.audio_sha256 end
            return token
        end
    end

    function permits.allows(file, event, token)
        file=basename(file)
        local hash=file and data.files[file]
        if not data.listening_audio[hash] or data.veto[file] or data.veto[hash] then return false end
        local w=token and issued[token]
        if w and w.target and w.target~=hash then return false end
        local uses=data.managed[hash]
        if not uses then return true end -- Previously shipped, outside this review ledger.
        if not w then return false end
        for _,use in ipairs(uses) do
            if matches(use,w,w.origin,event) then
                local ok,valid=pcall(w.live)
                return ok and valid==true
            end
        end
        return false
    end

    function permits.consume(token,file,event)
        if not token then return end
        local w=issued[token]
        issued[token]=nil
        if w and (w.origin=="gameplay" or w.origin=="stream_drop") and file and data.managed[data.files[file]] then
            return {origin=w.origin,file=file,event=event,audio_sha256=data.files[file],actor=w.actor,mode=w.mode,
                    visit=w.visit,epoch=w.epoch,generation=w.generation,slot=w.slot,level=w.level,area=w.area,
                    fact=w.fact,fact_id=w.fact_id}
        end
    end
    return permits
end

return Module
