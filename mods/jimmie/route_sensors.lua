-- Read-only engine observations for route_guide. No save, HUD, or Mario setters.
-- Exact indexing and flags: CoopDX v1.5.1 save_file.c/save_file.h/course_defines.h.
local S = {}
-- The packaged inventory contains no external launch profile. Explicit observer options still apply.
local launchProfile=nil
local function integer(v,lo,hi)
    return type(v)=="number" and v==v and v%1==0 and v>=lo and v<=hi
end
local function finite(v) return type(v)=="number" and v==v and math.abs(v)<math.huge end
local function field(object,key)
    if object==nil then return nil end
    local ok,value=pcall(function() return object[key] end)
    if ok then return value end
    return nil
end
local function boolean(v)
    if v==true or v==1 then return true end
    if v==false or v==0 then return false end
    return nil
end
local function bit(value,weight) return math.floor(value/weight)%2==1 end
local function canonical(value)
    if type(value)~="string" then return nil end
    value=value:lower():gsub("\\","/"):gsub("/+$","")
    value=value:match("([^/]+)$") or value
    value=value:gsub("%.lua$",""):gsub("%.zip$","")
    return value:gsub("[^a-z0-9]+","-"):gsub("^%-+",""):gsub("%-+$","")
end
local COSMETIC={jimmie=true,jimmie_text=true,jimmie_live=true,["jimmie-text"]=true,["jimmie-live"]=true,
    ["jimmie-companion"]=true,["jimmie-text-pass"]=true,["jimmie-live-commands"]=true,
    ["day-night-cycle"]=true,["day-night-cycle-dx"]=true}
local GEOMETRY={sm74=true,["sm64-star-road"]=true,["star-road"]=true,["super-mario-74"]=true,
    ["super-mario-star-road"]=true}
local FLAG_WEIGHTS={key1=0x10,key2=0x20,basementUnlocked=0x40,upstairsUnlocked=0x80,
    dddMovedBack=0x100,toad1Collected=0x01000000,mips1Collected=0x08000000,bitfsDoorUnlocked=0x8000}

local function mods()
    local report={observed=false,safe=false,customLevel=false,known={},unknown={}}
    local active=gActiveMods
    if active==nil then return report end
    local count=0
    local ok=pcall(function()
        for index,mod in pairs(active) do
            if type(index)=="number" then
                count=count+1
                if count>128 then error("mod-inventory-overflow") end
                local enabled=field(mod,"enabled")
                if enabled~=false and enabled~=0 then
                    local id=canonical(field(mod,"relativePath"))
                    local name=canonical(field(mod,"name"))
                    local category=canonical(field(mod,"category")) or ""
                    if GEOMETRY[id] or GEOMETRY[name] or category=="romhack" or category=="rom-hack"
                        or category=="level" or category=="level-pack" then
                        report.customLevel=true
                        report.unknown[#report.unknown+1]=id or name or "unidentified-mod"
                    elseif COSMETIC[id] or COSMETIC[name] then
                        report.known[#report.known+1]=id or name
                    else report.unknown[#report.unknown+1]=id or name or "unidentified-mod" end
                    if enabled~=nil and boolean(enabled)==nil then error("mod-enabled-state-unknown") end
                end
            end
        end
    end)
    report.observed=ok
    report.safe=ok and not report.customLevel and #report.unknown==0
    table.sort(report.known);table.sort(report.unknown)
    return report
end

function S.capture(m,np,options)
    options=options or {}
    local errors={}
    local function problem(name) errors[#errors+1]=name end
    local function read(fn,name,...)
        if type(fn)~="function" then problem(name..":missing");return nil end
        local ok,value=pcall(fn,...)
        if not ok then problem(name..":error");return nil end
        return value
    end
    local function setting(object,key,kind)
        local raw=field(object,key)
        local value=raw
        if kind=="boolean" then
            -- Do not use Lua's truthiness: engine integer zero means false.
            value=boolean(raw)
            if value==nil then problem(key..":unknown") end
        elseif not integer(value,0,10000) then value=nil;problem(key..":unknown") end
        return value
    end
    local s={route=options.route or "16-star",routeVariant=options.routeVariant or "beginner",
        starMasks={},flags={},observed={starMasks=false,flags=false,totalStars=false,location=false},
        errors=errors,capabilities={mipsClip=false,blj=false},finishConfirmed=false}
    local fileNum=read(get_current_save_file_num,"get_current_save_file_num")
    if integer(fileNum,1,4) then
        s.fileIndex=fileNum-1
        local all=true
        for course=1,24 do
            local value=read(save_file_get_star_flags,"star-mask:"..course,s.fileIndex,course-1)
            if integer(value,0,127) then s.starMasks[course]=value
            else all=false;problem("star-mask:"..course..":invalid") end
        end
        local secret=read(save_file_get_star_flags,"secret-star-mask",s.fileIndex,-1)
        if integer(secret,0,127) then s.secretMask=secret
        else all=false;problem("secret-star-mask:invalid") end
        s.observed.starMasks=all
    else problem("save-file-number:invalid") end
    local rawFlags=read(save_file_get_flags,"save_file_get_flags")
    if integer(rawFlags,0,0xFFFFFFFF) then
        s.rawFlags=rawFlags
        for name,weight in pairs(FLAG_WEIGHTS) do s.flags[name]=bit(rawFlags,weight) end
        s.observed.flags=true
    else problem("save-flags:invalid") end
    local stars=field(m,"numStars")
    if integer(stars,0,120) then s.totalStars=stars;s.observed.totalStars=true
    else problem("total-stars:unknown") end
    local course,level,act,area=field(np,"currCourseNum"),field(np,"currLevelNum"),field(np,"currActNum"),field(np,"currAreaIndex")
    if integer(course,0,10000) then s.course=course else problem("current-course:unknown") end
    if integer(level,1,10000) then s.level=level else problem("current-level:unknown") end
    if integer(act,0,255) then s.act=act else problem("selected-act:unknown") end
    if integer(area,0,255) then s.area=area else problem("current-area:unknown") end
    s.observed.location=s.course~=nil and s.level~=nil and s.act~=nil and s.area~=nil
    s.useGlobalStarIds=setting(gLevelValues,"useGlobalStarIds","boolean")
    s.disableActs=setting(gLevelValues,"disableActs","boolean")
    s.fixCollisionBugs=setting(gLevelValues,"fixCollisionBugs","boolean")
    s.pauseExitAnywhere=setting(gLevelValues,"pauseExitAnywhere","boolean")
    s.stayInLevelAfterStar=setting(gServerSettings,"stayInLevelAfterStar","integer")
    s.thresholds={toad1=setting(gBehaviorValues,"ToadStar1Requirement","integer"),
        mips1=setting(gBehaviorValues,"MipsStar1Requirement","integer"),
        mips2=setting(gBehaviorValues,"MipsStar2Requirement","integer"),
        endlessStairs=setting(gLevelValues,"infiniteStairsRequirement","integer")}
    local inventory=mods()
    s.observed.mods=inventory.observed
    s.activeMods=inventory.known;s.unknownMods=inventory.unknown
    s.customLevel=inventory.customLevel or (s.level~=nil and s.level>38) or (s.course~=nil and s.course>25)
    local profile=launchProfile
    if options.profile~=nil then profile=options.profile end
    local owner=field(profile,"owner")
    local hash=field(profile,"sourceHash")
    local verified=owner=="JIMMIE_ROUTE_LAUNCH_PROFILE_V1" and field(profile,"engineVerified")==true
        and type(hash)=="string" and #hash==64 and hash:match("^[a-fA-F0-9]+$")~=nil
    local normal=s.useGlobalStarIds==false and s.disableActs==false and not s.customLevel
        and s.stayInLevelAfterStar==0 and s.pauseExitAnywhere==true
        and s.thresholds.toad1==12 and s.thresholds.mips1==15 and s.thresholds.mips2==50
        and s.thresholds.endlessStairs==70
    s.profile={engineVerified=verified,modsVerified=inventory.safe,normalSettings=normal,
        source_id="engine_hardcoded",techniqueStatus="unverified"}
    if verified and inventory.safe and normal then
        s.capabilities.mipsClip=field(profile,"mipsClip")==true and s.fixCollisionBugs==false
        s.capabilities.blj=field(profile,"blj")==true
        s.profile.techniqueStatus=(s.capabilities.mipsClip or s.capabilities.blj) and "source-profile-compatible" or "unverified"
    end
    -- An ending course plus the actual ending level is observable finish evidence.
    -- Selected act, star totals, boss proximity and obtained keys are not victory.
    local endingLevel=integer(LEVEL_ENDING,1,10000) and LEVEL_ENDING or 25
    local ending=s.observed.location and s.course==25 and s.level==endingLevel
    s.finishConfirmed=options.finishConfirmed==true or ending
    if s.finishConfirmed then s.finishEvidence=ending and "ending-course-and-level" or "provided-explicit-observation" end
    local pos=field(m,"pos")
    local x,y,z=field(pos,"x"),field(pos,"y"),field(pos,"z")
    if finite(x) and finite(y) and finite(z) then s.position={x=x,y=y,z=z} end
    local action=field(m,"action")
    if integer(action,0,0xFFFFFFFF) then s.action=action end
    return s
end

return S