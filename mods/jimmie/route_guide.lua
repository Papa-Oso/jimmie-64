-- Pure, source-linked route interpretation. It never writes saves or controls Mario.
local ok, Facts = pcall(require, "route_facts")
local G = { facts = ok and Facts or nil }
local function integer(n, lo, hi)
    return type(n)=="number" and n==n and n%1==0 and n>=lo and n<=hi
end
local function clone(v)
    if type(v)~="table" then return v end
    local out={}; for k,item in pairs(v) do out[k]=clone(item) end; return out
end
local function mask(s,course)
    local values=s.starMasks
    if type(values)~="table" then return nil end
    local value=values[course]
    if value==nil then value=values[tostring(course)] end
    return integer(value,0,127) and value or nil
end
local function has_star(s,course,star)
    local value=mask(s,course)
    return value~=nil and math.floor(value/2^(star-1))%2==1
end
local function flag(s,name)
    return type(s.flags)=="table" and s.flags[name]==true
end
local function source_exists(id)
    return G.facts and G.facts.sources and G.facts.sources[id]~=nil
end
local function unknown(reason)
    return {objective_id="unknown",kind="unknown",target_kind="unknown",label="Route objective unavailable",
        direction_text="",source_id="engine_save",confidence=0,why=reason,source_confidence="insufficient observed state"}
end

-- An objective change is not completion. This helper requires collection/access proof.
function G.is_complete(goal,s)
    s=s or {}
    if s.useGlobalStarIds~=false or s.customLevel==true then return false,"incompatible-progress-profile" end
    local completion=type(goal)=="table" and goal.completion or nil
    if type(completion)~="table" then return false,"no-completion-proof" end
    local observed=type(s.observed)=="table" and s.observed or {}
    if completion.kind=="star" then
        if observed.starMasks~=true or not integer(completion.course,1,24)
            or not integer(completion.star_id,1,7) or mask(s,completion.course)==nil then
            return false,"star-mask-unobserved"
        end
        return has_star(s,completion.course,completion.star_id),"course-star-mask"
    elseif completion.kind=="flag" then
        if observed.flags~=true then return false,"save-flags-unobserved" end
        for _,name in ipairs(completion.any or {}) do if flag(s,name) then return true,"save-flag:"..name end end
        if completion.secret_mask and observed.starMasks==true and integer(s.secretMask,0,127) then
            local bit=completion.secret_mask
            if math.floor(s.secretMask/bit)%2==1 then return true,"secret-star-mask" end
        end
        return false,"save-flag-not-set"
    elseif completion.kind=="access" then
        if integer(s.course,0,24) and s.course==completion.course then return true,"observed-course-access" end
        if observed.flags==true then
            for _,name in ipairs(completion.any or {}) do if flag(s,name) then return true,"save-flag:"..name end end
        end
        return false,"access-not-observed"
    elseif completion.kind=="level" then
        return s.level==completion.level,"observed-level-access"
    elseif completion.kind=="finish" then
        return s.finishConfirmed==true,"explicit-finish-observation"
    end
    return false,"unsupported-completion-proof"
end
G.isComplete=G.is_complete

local function completed(id,s)
    return G.is_complete(G.facts.objectives[id],s)
end
local function eligible(id,s)
    local goal=G.facts.objectives[id]
    if not goal or completed(id,s) then return false end
    for _,prior in ipairs(goal.prerequisites or {}) do if not completed(prior,s) then return false end end
    return true
end
local function choose(ids,s,localFirst)
    if localFirst then
        for _,id in ipairs(ids) do
            local goal=G.facts.objectives[id]
            if goal and goal.course==s.course and eligible(id,s) then return id end
        end
    end
    for _,id in ipairs(ids) do if eligible(id,s) then return id end end
    return nil
end
local function objective(id,s,why)
    local original=G.facts.objectives[id]
    if not original or not source_exists(original.source_id) then return unknown("unverified-objective") end
    local out=clone(original)
    out.target_kind=out.kind
    out.cue_id=id
    out.why=why
    if out.alternate and out.alternate.objective_id and completed(out.alternate.objective_id,s) then out.alternate=nil end
    local same=out.course==s.course and (out.course~=0 or
        (out.level==s.level and (out.area==nil or out.area==s.area)))
    out.delivery=same and "local" or "travel"
    if out.kind=="star" and not same then
        out.kind="travel"
        local entry=G.facts.courses[out.course]
        if entry then
            out.direction_text=entry.entry.." Next objective: "..out.label.."."
            out.source_ids[#out.source_ids+1]=entry.source_id
        end
    elseif out.kind=="key" and out.arena_level==s.level then
        out.direction_text=id=="first_key" and "Defeat first Bowser and collect his key." or
            "Defeat second Bowser and collect his key."
    end
    if same and out.required_act and s.act~=out.required_act then
        out.cue_id=nil
        out.reselect_act=out.required_act
        out.direction_text="Select act "..out.required_act.." for this objective. "..out.direction_text
        out.why=why.."; selected act does not expose the required setup"
    elseif same and out.act_range and (not integer(s.act,out.act_range[1],out.act_range[2])) then
        out.cue_id=nil
        out.reselect_act=out.act_range[1]
        out.direction_text="Select an act from "..out.act_range[1].." to "..out.act_range[2]..". "..out.direction_text
        out.why=why.."; selected act does not spawn the documented owl setup"
    end
    if s.stayInLevelAfterStar~=nil and s.stayInLevelAfterStar~=0 then
        out.caution="Stay/nonstop mode changes exits; collection identity remains based on observed star masks."
    end
    return out
end
local function technique_gate(id,s,reason,direction,alternate)
    local out=objective(id,s,reason)
    out.cue_id=nil
    out.objective_id="verify_"..id
    out.kind="gate"; out.target_kind="gate"; out.confidence=0.5
    out.direction_text=direction
    out.alternate=alternate
    return out
end

function G.evaluate(s)
    s=s or {}
    if not G.facts then return unknown("route-facts-unavailable") end
    if s.route~="16-star" then return unknown("explicit-route-goal-required") end
    local observed=type(s.observed)=="table" and s.observed or {}
    if observed.starMasks~=true or observed.flags~=true or observed.totalStars~=true then
        return unknown("save-progress-not-observed")
    end
    if s.useGlobalStarIds~=false then return unknown("canonical-star-id-schema-not-verified") end
    if s.customLevel==true then return unknown("unsupported-level-or-act-profile") end
    if s.disableActs~=false then return unknown("act-profile-not-verified") end
    if type(s.thresholds)=="table" and
        ((s.thresholds.toad1~=nil and s.thresholds.toad1~=12) or
         (s.thresholds.mips1~=nil and s.thresholds.mips1~=15)) then
        return unknown("reference-route-thresholds-altered")
    end
    if not integer(s.totalStars,0,120) or not integer(s.course,0,25) or not integer(s.level,1,38) then
        return unknown("invalid-progress-or-location")
    end
    for _,name in ipairs({"key1","key2","basementUnlocked","upstairsUnlocked","dddMovedBack",
        "toad1Collected","mips1Collected","bitfsDoorUnlocked"}) do
        if type(s.flags)~="table" or type(s.flags[name])~="boolean" then return unknown("save-flag-missing:"..name) end
    end
    for _,course in ipairs({1,2,4,6,7,8,9,16,17,18}) do
        if mask(s,course)==nil then return unknown("star-mask-missing:"..course) end
    end
    local variant=s.routeVariant or "beginner"
    if variant~="beginner" and variant~="standard" and variant~="intermediate" then
        return unknown("unsupported-route-variant")
    end
    local key1=flag(s,"key1") or flag(s,"basementUnlocked")
    local key2=flag(s,"key2") or flag(s,"upstairsUnlocked")
    if s.finishConfirmed==true then
        local out=objective("final_bowser",s,"grand-star or ending transition explicitly observed")
        out.objective_id="run_complete"; out.cue_id=nil; out.label="Run finish observed"; out.confidence=1
        out.direction_text="The finish transition is confirmed."
        return out
    end
    -- Existing progress wins over the reference route. Never backfill removed Sub.
    if key2 and s.totalStars>=16 then
        if s.level==34 then return objective("final_bowser",s,"final arena observed; victory still unconfirmed") end
        if s.course==18 then return objective("final_stage",s,"final stage access observed; boss still ahead") end
        if type(s.capabilities)~="table" or s.capabilities.blj~=true then
            return technique_gate("upstairs_skips",s,"BLJ capability not verified for the active profile",
                "The reference route uses the fifty-star-door and endless-staircase skips. Verify active BLJ support before precise coaching.",
                {label="Normal upstairs gates",direction_text="Without verified skips, the normal gates require fifty and seventy stars.",source_id="uk_blj"})
        end
        return objective("upstairs_skips",s,"second key or upstairs access observed; sixteen-star threshold reached")
    end
    if not key1 then
        if s.totalStars>=8 then
            if variant~="beginner" and s.course==16 and s.level~=30 and not completed("bitdw_reds",s) then
                return objective("bitdw_reds",s,"standard branch takes Dark World reds before the first key")
            end
            return objective("first_key",s,"eight-star gate reached; first key has not been observed")
        end
        local nextId=choose(G.facts.early,s,true)
        return nextId and objective(nextId,s,"collect an uncollected early-route star toward the eight-star gate") or
            unknown("no-source-backed-early-objective")
    end
    if not key2 and (completed("ddd_sub",s) or flag(s,"dddMovedBack") or s.course==17 or s.level==33) then
        return objective("second_key",s,"Fire Sea access observed; second key has not been observed")
    end
    if s.totalStars<15 or (key2 and s.totalStars<16) then
        -- Toad-before-fifteen is routing advice, not a reason to add a seventeenth star.
        if s.totalStars>=12 and s.totalStars<15 and not completed("toad1",s) then
            return objective("toad1",s,"Toad's twelve-star threshold reached; take him before the fifteenth star")
        end
        local basement=variant=="beginner" and G.facts.basement or G.facts.basementStandard
        local nextId=choose(basement,s,true)
        if not nextId then nextId=choose(G.facts.early,s,true) end
        return nextId and objective(nextId,s,"resume an uncollected source-backed star while preserving observed detours") or
            unknown("reference-star-options-exhausted-before-gate")
    end
    local accessed=s.course==9 or s.level==23 or flag(s,"bitfsDoorUnlocked") or flag(s,"dddMovedBack")
    if accessed or s.totalStars>=30 then
        return objective("ddd_sub",s,accessed and "Dire, Dire Docks access already observed" or "normal thirty-star door threshold reached")
    end
    if flag(s,"mips1Collected") then
        local out=technique_gate("mips_clip",s,"first MIPS star collected; the rabbit will not respawn on basement reload and current presence is unverified",
            "MIPS's first star is collected, so the first rabbit will not respawn after a basement reload. Its current presence is unverified.",
            {label="Normal thirty-star door",direction_text="Continue to thirty stars for the normal Dire, Dire Docks door; this changes the reference route.",source_id="uk_mips"})
        out.objective_id="mips_unavailable"; return out
    end
    if type(s.capabilities)~="table" or s.capabilities.mipsClip~=true then
        return technique_gate("mips_clip",s,"MIPS clip compatibility not verified for the active profile",
            "The reference route uses the yellow rabbit to pass the thirty-star door. Verify the active MIPS clip setup before precise coaching.",
            {label="Normal thirty-star door",direction_text="The normal door route opens at thirty stars and changes this reference route.",source_id="uk_mips"})
    end
    local out=objective("mips_clip",s,"fifteen-star threshold reached; first rabbit's star remains uncollected")
    out.caution="Do not collect MIPS's star. If the rabbit did not spawn after the fifteenth star, reload the basement."
    return out
end

return G