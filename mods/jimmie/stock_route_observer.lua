-- Silent stock v1.5.1 observation stage. No movement, save, voice or IPC writes.
-- Loading this module installs no hooks. Reference route is not the owner's route.
local Sensors = require("route_sensors")
local Guide = require("route_guide")
local O = { VERSION = 1 }
local function integer(n, lo, hi)
    return type(n)=="number" and n==n and n%1==0 and n>=lo and n<=hi
end
local function field(o,k)
    local ok,v=pcall(function() return o[k] end)
    if ok then return v end
end
local function clone(v)
    if type(v)~="table" then return v end
    local c={};for k,x in pairs(v) do c[k]=clone(x) end;return c
end
local function has(v,b)
    return integer(v,0,0xFFFFFFFF) and integer(b,1,0x80000000) and math.floor(v/b)%2==1
end
local function path(v)
    if type(v)~="string" then return nil end
    return v:lower():gsub("\\","/"):gsub("/+$","")
end
local function enabled(v) return v==true or v==1 end
local function disabled(v) return v==false or v==0 end
local function scene(s)
    return table.concat({s.fileIndex,s.course,s.level,s.area,s.act},":")
end
local function safe_inventory(expected)
    if not expected or gActiveMods==nil then return false end
    local seen,count=false,0
    local ok=pcall(function()
        for key,mod in pairs(gActiveMods) do
            if type(key)=="number" then
                count=count+1;if count>128 then error("inventory overflow") end
                local on=field(mod,"enabled")
                if on~=false and on~=0 then
                    if on~=nil and not enabled(on) then error("unknown enabled state") end
                    if path(field(mod,"relativePath"))~=expected then error("other active mod") end
                    seen=true
                end
            end
        end
    end)
    return ok and seen
end
local function solo()
    if gNetworkPlayers==nil then return false end
    local ok,result=pcall(function()
        local count=0
        for key,np in pairs(gNetworkPlayers) do
            if type(key)=="number" then
                count=count+1;if count>64 then return false end
                if key~=0 then
                    local connected=field(np,"connected")
                    if connected~=false and connected~=0 then return false end
                end
            end
        end
        return true
    end)
    return ok and result
end
local function collection_bit(s,kind,index)
    if kind=="course_star" then return has(s.starMasks[s.course],2^(index-1)) end
    if kind=="secret_star" then return has(s.secretMask,2^(index-1)) end
    if kind=="key" then return s.flags[index==1 and "key1" or "key2"]==true end
    return nil
end
local function matches(goal,event)
    local c=goal and goal.completion
    if not c then return false end
    if event.kind=="course_star" then
        return c.kind=="star" and c.course==event.course and c.star_id==event.star_id
    elseif event.kind=="secret_star" then
        return c.kind=="flag" and c.secret_mask==2^(event.star_id-1)
    elseif event.kind=="key" then
        return goal.objective_id==(event.key_id==1 and "first_key" or "second_key")
    end
    return false
end
function O.new(config)
    config=config or {}
    local self={}
    local active=config.enabled==true
    local expected=path(config.expected_mod_path)
    local epoch,serial,sceneSerial=1,0,0
    local previous,lastFrame,lastPoll,saveIndex,goal,snapshot=nil,nil,nil,nil,nil,nil
    local receipts,duplicates={},{}
    local reason=active and "awaiting-observation" or "disabled"
    local function clear(why)
        epoch=epoch+1;serial=0;sceneSerial=0
        previous,lastFrame,lastPoll,saveIndex,goal,snapshot=nil,nil,nil,nil,nil,nil
        receipts,duplicates={},{};reason=why
    end
    local function suspend(why)
        previous,goal,snapshot=nil,nil,nil;reason=why
    end
    local function frame_check(frame)
        if not integer(frame,0,0xFFFFFFFF) then suspend("frame-unobserved");return false end
        if lastFrame and frame<lastFrame then clear("frame-rewind") end
        lastFrame=frame;return true
    end
    local function preflight(m,np,frame)
        if not active then return nil,"disabled" end
        -- Identity and cheap safety checks run even between expensive save snapshots.
        local ok,fileNum=false,nil
        if type(get_current_save_file_num)=="function" then ok,fileNum=pcall(get_current_save_file_num) end
        if not ok or not integer(fileNum,1,4) then return nil,"save-identity-unobserved" end
        if saveIndex~=nil and saveIndex~=fileNum-1 then clear("save-slot-changed");lastFrame=frame end
        saveIndex=fileNum-1
        if field(m,"playerIndex")~=0 or np==nil then return nil,"local-player-unobserved" end
        if not enabled(field(np,"currLevelSyncValid")) or not enabled(field(np,"currAreaSyncValid")) then return nil,"scene-unsynchronized" end
        if not safe_inventory(expected) then return nil,"mod-inventory-unverified" end
        if not solo() then return nil,"multiplayer-or-player-inventory-unknown" end
        if not disabled(field(gLevelValues,"useGlobalStarIds")) or not disabled(field(gLevelValues,"disableActs"))
            or not enabled(field(gLevelValues,"pauseExitAnywhere"))
            or field(gServerSettings,"stayInLevelAfterStar")~=0
            or field(gBehaviorValues,"ToadStar1Requirement")~=12
            or field(gBehaviorValues,"MipsStar1Requirement")~=15
            or field(gBehaviorValues,"MipsStar2Requirement")~=50
            or field(gLevelValues,"infiniteStairsRequirement")~=70 then return nil,"unsupported-profile" end
        if not integer(field(np,"currCourseNum"),0,25) or not integer(field(np,"currLevelNum"),1,38)
            or not integer(field(np,"currAreaIndex"),1,255) or not integer(field(np,"currActNum"),0,255)
            then return nil,"unsupported-scene" end
        if previous and (previous.course~=np.currCourseNum or previous.level~=np.currLevelNum
            or previous.area~=np.currAreaIndex or previous.act~=np.currActNum) then
            suspend("scene-changed");lastPoll=nil
        end
        return true
    end
    local function capture(m,np,frame)
        local ready,why=preflight(m,np,frame)
        if not ready then return nil,why end
        -- Never inherit a custom native launch profile or assert binary attestation.
        local s=Sensors.capture(m,np,{profile={}})
        if not s.observed.location or not s.observed.starMasks or not s.observed.flags
            or not s.observed.totalStars then return nil,"incomplete-observation" end
        if not s.profile.normalSettings or s.customLevel then return nil,"unsupported-profile" end
        if not integer(s.area,1,255) or not integer(s.course,0,25) then return nil,"unsupported-scene" end
        if saveIndex~=nil and saveIndex~=s.fileIndex then clear("save-slot-changed");lastFrame=frame end
        saveIndex=s.fileIndex;s.frame=frame
        -- The stock observer has its own exact path check. This is NOT a binary hash check.
        s.profile.modsVerified=true;s.profile.engineVerified=false
        s.capabilities.mipsClip=false;s.capabilities.blj=false
        return s
    end
    local function accept(s)
        previous=s;snapshot=s;goal=Guide.evaluate(s);reason="observing"
    end
    function self.reset(why) clear(why or "explicit-reset") end
    function self.set_enabled(value)
        active=value==true;clear(active and "awaiting-observation" or "disabled")
    end
    function self.scene_changed()
        -- Retain immutable origin receipts; never carry a pre-transition baseline forward.
        sceneSerial=sceneSerial+1;previous,goal,snapshot,lastPoll=nil,nil,nil,nil
        duplicates={};reason=active and "scene-transition" or "disabled"
    end
    function self.update(m,np,frame)
        if not active then return end
        if not frame_check(frame) then return end
        local ready,problem=preflight(m,np,frame)
        if not ready then suspend(problem);return end
        if lastPoll and frame-lastPoll<8 then return end
        lastPoll=frame
        local s,why=capture(m,np,frame)
        if not s then suspend(why);return end
        accept(s)
    end
    function self.on_interact(m,obj,interactType,interactValue,np,frame)
        if not active or field(m,"playerIndex")~=0 or not enabled(interactValue) then return end
        if not integer(INTERACT_STAR_OR_KEY,1,0xFFFFFFFF) or interactType~=INTERACT_STAR_OR_KEY then return end
        if not has(field(obj,"oInteractStatus"),INT_STATUS_INTERACTED) then return end
        if type(obj_has_behavior_id)~="function" or id_bhvBowserKey==nil then return end
        if not integer(INT_SUBTYPE_GRAND_STAR,1,0x80000000) then return end
        if not integer(field(obj,"oInteractionSubtype"),0,0xFFFFFFFF) then return end
        -- Grand Star is not run completion. Ending confirmation remains a separate observation.
        if has(field(obj,"oInteractionSubtype"),INT_SUBTYPE_GRAND_STAR) then return end
        if not frame_check(frame) then return end
        local s,why=capture(m,np,frame)
        if not s then suspend(why);return end
        local ok,isKey=pcall(obj_has_behavior_id,obj,id_bhvBowserKey)
        if not ok or (isKey~=true and isKey~=false and isKey~=0 and isKey~=1) then return end
        local event={actor="mario_local",source="HOOK_ON_INTERACT:accepted",epoch=epoch,
            scene_serial=sceneSerial,file_index=s.fileIndex,course=s.course,level=s.level,
            area=s.area,act=s.act,frame=frame,progress="unknown",technique=nil}
        local index
        if enabled(isKey) then
            if s.level==30 and s.course==16 then index=1
            elseif s.level==33 and s.course==17 then index=2 else return end
            event.kind="key";event.key_id=index
        else
            local params=field(obj,"oBehParams")
            if not integer(params,0,0xFFFFFFFF) or s.course>24 then return end
            index=math.floor(params/0x1000000)%32+1
            if index>7 then return end
            event.kind=s.course==0 and "secret_star" or "course_star";event.star_id=index
        end
        if not collection_bit(s,event.kind,index) then return end
        local identity=table.concat({scene(s),event.kind,index},":")
        for _,old in ipairs(duplicates) do
            if old.identity==identity and frame-old.frame<=30 then return end
        end
        local before=previous
        if before and scene(before)==scene(s) and frame>=before.frame and frame-before.frame<=30 then
            event.progress=collection_bit(before,event.kind,index) and "already-collected" or "new"
            local oldGoal=Guide.evaluate(before)
            if event.progress=="new" and matches(oldGoal,event) and Guide.is_complete(oldGoal,s) then
                event.completed_reference_objective_id=oldGoal.objective_id
            end
        end
        serial=serial+1;event.id=tostring(epoch)..":"..tostring(serial)
        receipts[#receipts+1]=event;if #receipts>32 then table.remove(receipts,1) end
        duplicates[#duplicates+1]={identity=identity,frame=frame}
        if #duplicates>8 then table.remove(duplicates,1) end
        accept(s)
    end
    function self.brief()
        return reason, goal and goal.objective_id, epoch
    end
    function self.latest()
        return clone(receipts[#receipts])
    end
    function self.state()
        return {schema=1,enabled=active,status=reason,epoch=epoch,
            reference="beginner-16-star-not-personal-route",goal=clone(goal),
            snapshot=clone(snapshot),receipts=clone(receipts)}
    end
    return self
end
local installed
function O.install(config)
    config=config or {}
    if config.enabled~=true then return nil,"disabled" end
    if installed then return installed,"already-installed" end
    if type(config.expected_mod_path)~="string" or config.expected_mod_path=="" then return nil,"expected-mod-path-required" end
    if type(hook_event)~="function" or HOOK_UPDATE==nil or HOOK_ON_INTERACT==nil
        or HOOK_ON_LEVEL_INIT==nil then return nil,"required-hooks-unavailable" end
    local self=O.new(config)
    hook_event(HOOK_UPDATE,function()
        self.update(field(gMarioStates,0),field(gNetworkPlayers,0),gGlobalTimer)
    end)
    hook_event(HOOK_ON_INTERACT,function(m,obj,kind,value)
        self.on_interact(m,obj,kind,value,field(gNetworkPlayers,0),gGlobalTimer)
        -- Deliberately no return value: never overrides the engine's interaction.
    end)
    hook_event(HOOK_ON_LEVEL_INIT,function() self.scene_changed() end)
    installed=self;return self,"installed-silent"
end
return O
