-- Read-only route facts and finite approved performances for the personal 16-star companion.
local Module = {}
local transition=require("performance_route_transition")
local nativeBank=require("performance_route_bank")
local bankWall=require("performance_wall_recovery")
local bankFiles=require("performance_rules").files
local recovery=require("performance_wall_recovery")
local variant=require("performance_recovery_take")
local fileHashes=require("performance_rules").files
-- The host waits one second after level initialization before it can place Jimmie.
-- Give him one short entrance window, measured from Mario's actual arrival.
local ARRIVAL_WINDOW_MS = 2000
local CLIPS = {
    castle_door={file="catchphrase_03.ogg",text="What's happening, guys?",event="level_enter"},
    star_hype={file="catchphrase_01.ogg",text="Holy shit!",event="star"},
    bowser_entrance={file="boss_bowser_01.ogg",text="Let's go fuck Bowser.",event="boss_bowser"},
}

function Module.new(deps)
    local self={}
    local observer=require("stock_route_observer").new({enabled=true,expected_mod_path="jimmie"})
    local mode=require("route_mode16").new()
    local Detector=require("encounter_detector")
    local wallConfig=Detector.normalize(require("route_wall_bounds"))
    local wall=Detector.new(wallConfig)
    local samples, history, spoken, flags = {}, {}, {}, {}
    local mission={}
    for id,fact in pairs(require("route_facts").objectives) do
        if fact.kind=="star" and fact.course and fact.star_id then mission[fact.course.."/"..fact.star_id]=id end
    end
    local epoch, slot, generation, ticket = nil, nil, 0, 0
    local previous, lastReceipt, pending, sceneKey, currentGoal, lastMode
    local entered, lastFrame, grandSeen = {}, nil, false
    local arrival
    local dance=require("performance_star_dance").new(deps.voice)
    local visit = 0
    local function log(kind,data)
        data.kind=kind
        print("[j16] "..deps.json(data))
    end
    local function append(list,row,max)
        list[#list+1]=row
        if #list>max then table.remove(list,1) end
    end
    local function modeName() return (mode.current()) end
    local function place()
        local np=gNetworkPlayers[0]
        if not np then return nil end
        return tostring(np.currLevelNum).."/"..tostring(np.currAreaIndex).."/"..tostring(np.currActNum)
    end
    local function cancel()
        if pending then pending.valid=false;pending=nil end
    end
    local function record(kind,data)
        data.actor=data.actor or "mario"
        data.frame=get_global_timer()
        data.mode=modeName()
        if sceneKey and sceneKey==place() then data.visit=visit end
        log(kind,data)
        if JIMMIE_BRAIN then JIMMIE_BRAIN.route(kind) end
        append(history,{kind=kind,actor=data.actor,objective=data.objective,mission=data.mission,
                        id=data.id,mode=data.mode,generation=generation,epoch=epoch,slot=slot,course=data.course,area=data.area,
                        matched_reference=data.matched_reference,level=data.level,frame=data.frame,visit=data.visit},8)
    end
    local function resetAttempt()
        dance.clear()
        observer.reset("new_file_or_clock")
        wall:reset(); mode.reset(); deps.resetHint(); cancel()
        history,spoken,flags,entered={},{},{},{}
        sceneKey,currentGoal,previous,lastReceipt,grandSeen,arrival=nil,nil,nil,nil,false,nil
        generation=generation+1
    end
    local existingRoastRule=deps.voice.ELIGIBILITY["roast_03.ogg"]
    local function syncMode()
        local current,selection,reason=mode.current()
        if current~=lastMode then
            dance.clear();cancel();generation=generation+1;lastMode=current
            deps.voice.ELIGIBILITY["roast_03.ogg"]=current=="16" and {reasons={"run_pool_exclusion"}} or existingRoastRule
            if deps.voice.mode~="silent" then deps.voice.setMode(current=="16" and "run" or "companion") end
            log("mode",{mode=current,selection=selection,reason=reason,epoch=epoch,slot=slot})
        end
        return current
    end
    local function validWorld(m,np)
        return deps.gameplay() and m and m.playerIndex==0 and m.marioObj and np
            and (np.currLevelSyncValid==true or np.currLevelSyncValid==1)
            and (np.currAreaSyncValid==true or np.currAreaSyncValid==1)
            and get_dialog_id()==-1 and not is_game_paused() and get_current_play_mode()==PLAY_MODE_NORMAL
    end
    local function entryBeat(np)
        if np.currAreaIndex~=1 then return nil end
        if np.currLevelNum==6 then return "castle_door" end
        if np.currLevelNum==21 then return "bowser_entrance" end
    end
    local function awaitingGreeting()
        if not arrival or entered[arrival.beat] or arrival.generation~=generation or modeName()~="16"
            or place()~=sceneKey then return false end
        local age=jimmie_route_now_ms()-arrival.at
        return age>=0 and age<=ARRIVAL_WINDOW_MS
    end
    local function ready(item)
        local m,np=gMarioStates[0],gNetworkPlayers[0]
        local status=observer.brief()
        local elapsed=jimmie_route_now_ms()-item.started
        return item.valid and modeName()=="16" and validWorld(m,np) and status=="observing"
            and generation==item.generation and place()==item.scene and item.visit==visit
            and get_current_save_file_num()==item.slot and jimmie_route_file_epoch()==item.epoch
            and elapsed>=0 and elapsed<=320 and not deps.voice.busy()
            and deps.nearby()
    end

    local function bankDecision(item)
        local selected=item.take and variant or CLIPS[item.beat]
        local hash=selected and bankFiles[selected.file]
        local token,reason=nativeBank.choose(item,history,spoken,hash,item.stars,jimmie_route_now_ms(),bankWall.matches(item,history))
        return transition.choose(token,reason,item)
    end
    local function witnessed(item)
        local token,reason=bankDecision(item)
        if item.transition and item.transition.beat then return token=="A" end
        return reason~="stale_fact" and reason~="invalid_context"
    end
    local function request(beat,m,np,started,kind,id,progress)
        if modeName()~="16" or not validWorld(m,np) or not samples[beat] or not deps.nearby() then return end
        local t=jimmie_route_now_ms()
        if pending or deps.voice.busy() or flags[beat] and t-flags[beat]<65000 then return end
        ticket=ticket+1
        local item={ticket=ticket,beat=beat,epoch=epoch,slot=slot,generation=generation,scene=place(),
                    visit=visit,level=np.currLevelNum,area=np.currAreaIndex,actor="mario",mode=modeName(),
                    fact=kind,fact_id=id,started=started,valid=true,transition=progress}
        item.frame=get_global_timer()
        if recovery.matches(item,history) then
            if not samples[variant.id] then return end
            item.take,item.condition=variant.id,"wall_recovery"
        end
        if not ready(item) or deps.eligible and not deps.eligible(item) then return end
        local recent,heard,heardFiles={},{},{}
        for _,event in ipairs(history) do
            local age=get_global_timer()-event.frame
            if age>=0 and age<=900 and event.visit==visit and event.generation==generation and event.epoch==epoch and event.slot==slot
                and event.mode==item.mode then recent[#recent+1]=event end
        end
        for _,performance in ipairs(spoken) do
            if t-performance.time<=120000 then heard[#heard+1]=performance.beat; heardFiles[#heardFiles+1]=performance.hash end
        end
        local body={version=1,ticket=ticket,beat=beat,mode="16",actor="mario",scene=item.scene,visit=visit,epoch=epoch,
                    slot=slot,stars=m.numStars,objective=currentGoal,history=recent,spoken=heard,
                    memory_schema=1,generation=generation,frame=get_global_timer(),fact=kind,fact_id=id}
        if item.take then body.take=item.take;body.take_sha256=variant.hash;body.heard_files=heardFiles end
        item.stars,item.frame=m.numStars,get_global_timer()
        local token,reason=bankDecision(item)
        body.native_bank={token=token,reason=reason}
        if progress then body.route_transition=progress;body.objective=progress.after end
        item.sent=jimmie_route_offer(ticket,deps.json(body))
        pending=item
        log("offered",{ticket=ticket,beat=beat,scene=item.scene,visit=visit,actor=item.actor,mode=item.mode,
                       fact=kind,fact_id=id,observed_qpc_ms=started,take=item.take})
    end
    local function dispatch()
        local item=pending
        if not item then return end
        if not ready(item) then cancel();log("expired",{ticket=item.ticket});return end
        local elapsed=jimmie_route_now_ms()-item.started
        local choice=item.sent and jimmie_route_reply(item.ticket) or nil
        if not choice and item.sent and elapsed<240 then return end
        local source=choice and "worker" or "bank"
        if not choice then
            local reason
            choice,reason=bankDecision(item)
            log("bank_choice",{ticket=item.ticket,token=choice,reason=reason,transport=item.sent and "deadline" or "rejected",
                               fact_id=item.fact_id,elapsed_ms=elapsed})
        end
        if choice=="A" and item.transition and item.transition.beat then
            local allowed,reason=bankDecision(item)
            if allowed~="A" then
                choice="S"
                log("route_quiet",{ticket=item.ticket,fact_id=item.fact_id,reason=reason})
            end
        end
        pending=nil
        if choice~="A" then item.valid=false;log("silent",{ticket=item.ticket,source=source});return end
        local clip=item.take and variant or CLIPS[item.beat]
        local sound=samples[item.take or item.beat]
        local valid=function() return ready(item) and witnessed(item) and (not item.take or recovery.matches(item,history)) end
        local grant=deps.authorize and deps.authorize(item,valid)
        if deps.authorize and not grant then
            item.valid=false
            log("scope_rejected",{ticket=item.ticket,beat=item.beat,fact=item.fact,fact_id=item.fact_id})
            return
        end
        deps.voice.external(sound,deps.duration(clip.file),{
            event=clip.event,key=clip.file,text=clip.text,volume=1.0,priority=69,ttl=0.32,
            valid=valid,
            onPlay=function()
                if item.beat=="star_hype" then dance.started(item,sound) end
                flags[item.beat]=jimmie_route_now_ms()
                append(spoken,{beat=item.beat,hash=fileHashes[clip.file],time=flags[item.beat]},4)
                log("played",{beat=item.beat,ticket=item.ticket,source=source,take=item.take,file=clip.file,elapsed_ms=flags[item.beat]-item.started,
                              visit=item.visit,fact=item.fact,fact_id=item.fact_id})
            end,
        },grant)
    end
    local function motion(m,np,frame)
        local act=np.currActNum
        if np.currLevelNum~=LEVEL_WF or np.currAreaIndex~=1 or np.currCourseNum~=2
                or type(act)~="number" or act<1 or act>6 or modeName()~="16"
                or not validWorld(m,np) then
            if previous then wall:reset();previous=nil end
            return
        end
        -- Mission 6 is the wall star on each stock act. The selected act scopes the sampled geometry.
        if act~=wallConfig.act then
            wallConfig.act=act
            wall=Detector.new(wallConfig)
            previous=nil
        end
        if previous then
            local dx,dy,dz=m.pos.x-previous.x,m.pos.y-previous.y,m.pos.z-previous.z
            if previous.frame+1~=frame or dx*dx+dy*dy+dz*dz>180*180 then wall:reset() end
        end
        local sample={f=frame,x=m.pos.x,y=m.pos.y,z=m.pos.z,spd=m.forwardVel,vy=m.vel.y,act=m.action,hp=m.health}
        previous={frame=frame,x=sample.x,y=sample.y,z=sample.z}
        local event=wall:feed(sample,{level=np.currLevelNum,area=np.currAreaIndex,act=act,course=np.currCourseNum,
                           star_mask=save_file_get_star_flags(slot-1,1)})
        if event and (event.kind=="setup" or event.kind=="attempt" or
                event.kind=="setback" and event.reason=="below-ledge") then
            record(({setup="wall_setup",attempt="possible_wall_attempt",setback="fell_below_setup"})[event.kind],
                   {level=LEVEL_WF,act=act,objective="wf_wall"})
        end
    end
    function self.update()
        local m,np=gMarioStates[0],gNetworkPlayers[0]
        if not deps.gameplay() or not m or not m.marioObj or not np then cancel();return end
        local frame,identity,file=get_global_timer(),jimmie_route_file_epoch(),get_current_save_file_num()
        if file==nil or file<1 or file>4 then cancel();return end
        if identity~=epoch or file~=slot or lastFrame and frame<lastFrame then
            resetAttempt();epoch,slot=identity,file
        end
        lastFrame=frame
        observer.update(m,np,frame)
        local status,goal=observer.brief()
        if status=="observing" then mode.location(np.currLevelNum,np.currAreaIndex,jimmie_route_now_ms(),m.numStars) end
        mode.update(deps.hint(),m.numStars)
        local current=syncMode()
        if status~="observing" then cancel();wall:reset();previous=nil;return end
        -- Rate-limit path sampling to the existing encounter; issue a goal record only when it changes.
        if goal~=currentGoal then
            currentGoal=goal
            log("reference",{id=goal,mode=current,scene=place(),stars=m.numStars})
        end
        local scene=place()
        if scene~=sceneKey then
            cancel();wall:reset();previous=nil
            visit=visit+1
            sceneKey=scene
            local id=string.format("entry:%d:%d:%d",slot,epoch,visit)
            local at=jimmie_route_now_ms()
            local beat=current=="16" and entryBeat(np)
            arrival=beat and {id=id,beat=beat,generation=generation,at=at} or nil
            record("segment_entered",{id=id,level=np.currLevelNum,area=np.currAreaIndex,act=np.currActNum,
                                      objective=goal,observed_qpc_ms=at})
        end
        -- Mario can arrive before Jimmie has a safe spawn. Speak only on their first
        -- encounter in this visit, with its own dispatch clock and the original entry id.
        if arrival and not awaitingGreeting() then arrival=nil end
        if arrival and validWorld(m,np) and deps.nearby() then
            local beat,id=arrival.beat,arrival.id
            arrival=nil
            entered[beat]=true
            request(beat,m,np,jimmie_route_now_ms(),"segment_entered",id)
        end
        motion(m,np,frame)
        dispatch()
    end
    function self.clear()
        dance.clear();observer.scene_changed(); generation=generation+1
        cancel();previous=nil;wall:reset();sceneKey=nil;currentGoal=nil;arrival=nil
    end
    function self.interaction(m,o,interaction,accepted)
        if m.playerIndex~=0 or not accepted or interaction~=INTERACT_STAR_OR_KEY or not o then return end
        local np=gNetworkPlayers[0]
        if not np or not deps.gameplay() then return end
        local started=jimmie_route_now_ms()
        if (o.oInteractionSubtype & INT_SUBTYPE_GRAND_STAR)~=0 then
            if not grandSeen and modeName()=="16" and m.numStars==16 and validWorld(m,np)
                    and np.currLevelNum==LEVEL_BOWSER_3 and np.currCourseNum==18
                    and (obj_has_behavior_id(o,id_bhvGrandStar)==1 or obj_has_behavior_id(o,id_bhvGrandStar)==true) and m.action==ACT_JUMBO_STAR_CUTSCENE
                    and (o.oInteractStatus & INT_STATUS_INTERACTED)~=0 and observer.brief()=="observing" then
                grandSeen=true
                record("final_grand_star",{level=np.currLevelNum,objective="final_bowser",stars=m.numStars})
                mode.finish();cancel()
            end
            return
        end
        local ordinary=obj_has_behavior_id(o,id_bhvStar)
        local key=obj_has_behavior_id(o,id_bhvBowserKey)
        if (ordinary==0 or ordinary==false) and (key==0 or key==false) then return end
        local oldStatus,before=observer.brief()
        observer.on_interact(m,o,interaction,accepted,np,get_global_timer())
        local e=observer.latest()
        if not e or e.id==lastReceipt or e.frame~=get_global_timer() or e.progress~="new" then return end
        lastReceipt=e.id
        mode.receipt(e,m.numStars);mode.update(deps.hint(),m.numStars);syncMode()
        local actual=e.kind=="course_star" and mission[e.course.."/"..e.star_id] or nil
        if e.kind=="secret_star" and e.star_id==1 then actual="toad1" end
        if e.kind=="key" then actual=e.key_id==1 and "first_key" or "second_key" end
        local status,after=observer.brief()
        local progress
        if modeName()=="16" and status=="observing" then
            progress=transition.describe(e,actual,oldStatus=="observing" and before or nil,after,m.numStars)
        end
        record(e.kind,{objective=actual,route_transition=progress,matched_reference=e.completed_reference_objective_id,level=e.level,
                       course=e.course,area=e.area,mission=e.star_id,key=e.key_id,id=e.id,stars=m.numStars})
        if e.kind~="key" then request("star_hype",m,np,started,e.kind,e.id,progress) end
    end
    function self.death(m)
        if m and m.playerIndex==0 then record("mario_death",{level=gNetworkPlayers[0].currLevelNum});cancel() end
    end
    function self.command(msg)
        local selection=(msg or ""):lower():match("^%s*(.-)%s*$")
        if selection~="" and selection~="status" and mode.select(selection) then cancel();syncMode() end
        local current,choice=mode.current()
        djui_chat_message_create("Jimmie: "..(current=="16" and "16-star run" or "free roam").." ("..choice.."). /j16 auto | 16 | free")
        return true
    end
    function self.ownsStar() return modeName()=="16" end
    function self.ownsCastle() return modeName()=="16" end
    function self.ownsBowser() return modeName()=="16" end
    self.awaitingGreeting=awaitingGreeting
    function self.holdsArrivalVoice()
        return awaitingGreeting() or (pending~=nil and pending.fact=="segment_entered" and ready(pending))
    end
    function self.current() return mode.current() end
    function self.performanceContext()
        local m,np=gMarioStates[0],gNetworkPlayers[0]
        if not validWorld(m,np) or observer.brief()~="observing" or sceneKey~=place() or visit<1
            or slot~=get_current_save_file_num() or epoch~=jimmie_route_file_epoch() then return nil end
        return {actor="mario",mode=modeName(),epoch=epoch,slot=slot,generation=generation,visit=visit,
                scene=sceneKey,level=np.currLevelNum,area=np.currAreaIndex}
    end
    function self.starDuringDance(m) return dance.sound(m,self.performanceContext()) end
    for id,clip in pairs(CLIPS) do
        local sample=deps.load(clip.file)
        if sample then deps.voice.register(sample,clip.file);samples[id]=sample end
    end
    if variant.file==CLIPS.star_hype.file then
        samples[variant.id]=samples.star_hype
    else
        local sample=deps.load(variant.file)
        if sample then deps.voice.register(sample,variant.file);samples[variant.id]=sample end
    end
    return self
end
return Module
