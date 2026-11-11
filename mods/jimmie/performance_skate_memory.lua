-- Facts about the skater come from his movement, crash acceptance and paired get-up.
local M={}
local scopeKeys={"epoch","slot","generation","visit","mode","scene","level","area","physicalScene","body","board"}
local function same(a,b)
    if not a or not b then return false end
    for _,k in ipairs(scopeKeys) do if a[k]~=b[k] then return false end end
    return true
end
local function recent(a,b)
    return a and b.frame>=a.frame and b.frame-a.frame<=900 and b.qpc_ms>=a.qpc_ms and b.qpc_ms-a.qpc_ms<=30000
end
local function link(f)
    return {fact=f.fact,id=f.id,frame=f.frame,qpc_ms=f.qpc_ms}
end

function M.new(context,report)
    local scope,lastID,pending,fall,getup,current=nil,0,nil,nil,nil,nil
    local self={}
    function self.clear()
        scope,lastID,pending,fall,getup,current=nil,0,nil,nil,nil,nil
    end
    local function witness()
        local w=context()
        if not w or not same(w,scope) or w.frame<scope.frame or w.qpc_ms<scope.qpc_ms then self.clear() end
        scope=w
        return w
    end
    local function note(w,source,fact,condition,episode,basis)
        local record={actor="jimmie",fact=fact,condition=condition,source=source,id=episode.id,kind=episode.kind,
            clip=episode.clip,trick=episode.trick,line=episode.line,roll=episode.roll,frame=w.frame,qpc_ms=w.qpc_ms,mode=w.mode,scene=w.scene,
            epoch=w.epoch,slot=w.slot,generation=w.generation,visit=w.visit,level=w.level,area=w.area,
            nearby=w.nearby==true,grounded=w.grounded==true,basis=basis or {}}
        current=record
        report(record)
        return record
    end
    function self.outcome(event,result)
        local w=witness()
        if not w or not w.grounded or type(result)~="table" or type(event)~="table" or
            event.source~="motion_controller" or event.eligible~=true or event.scene~=w.physicalScene or
            type(result.id)~="number" or result.id%1~=0 or result.id<=lastID or result.id~=event.id or
            result.kind~=event.kind or (result.kind~="trick" and result.kind~="grind") or result.clip~=event.clip or
            type(result.roll)~="number" or result.roll%1~=0 or result.roll<1 or result.roll>1000 or
            type(result.failed)~="boolean" then return nil end
        lastID,current,pending=result.id,nil,nil
        if result.failed then
            fall,getup=nil,nil
            pending={id=result.id,kind=result.kind,clip=result.clip,trick=result.trick,line=result.line,roll=result.roll,frame=w.frame,qpc_ms=w.qpc_ms}
            return nil
        end
        local history={}
        if fall and getup and recent(fall,w) and getup.frame<w.frame and fall.id<result.id then
            history={link(fall),link(getup)}
        end
        fall,getup=nil,nil
        return note(w,"motion_controller","trick_completed",#history==2 and "landing_after_getup" or "clean_landing",result,history)
    end
    function self.crash(accepted,isTrick)
        local w=witness()
        local p=pending
        pending,fall,getup,current=nil,nil,nil,nil
        if not w or not isTrick or accepted~=true or not p or w.frame~=p.frame or not recent(p,w) then return end
        fall=note(w,"crash_owner","trick_bailed","own_bail",p)
    end
    function self.gotUp()
        local w=witness()
        if not w or not w.grounded or not fall or getup or current~=fall or not recent(fall,w) or w.frame<=fall.frame then return end
        getup=note(w,"paired_getup","got_up","own_getup",fall,{link(fall)})
    end
    function self.valid(record)
        local w=witness()
        return w~=nil and record~=nil and record==current and record.fact=="trick_completed" and
            record.nearby and w.nearby and w.frame>=record.frame and w.qpc_ms>=record.qpc_ms and w.qpc_ms-record.qpc_ms<=320
    end
    return self
end
return M
