-- The stock sub is an anchored collision object until the second key or upstairs door removes it.
local Deck = {}

function Deck.current(g)
    local np=g.gNetworkPlayers and g.gNetworkPlayers[0]
    local route=g.JIMMIE_ROUTE16
    if not np or np.currLevelNum~=23 or np.currAreaIndex~=2 or np.currCourseNum~=9
            or not route or route.current()~="16" or (g.save_file_get_flags() & 0xA0)~=0 then return nil end
    local sub=g.obj_get_first_with_behavior_id(g.id_bhvBowsersSub)
    if not sub or sub.activeFlags==0 or sub.oPosX~=0 or sub.oPosY~=0 or sub.oPosZ~=0
            or sub.oFaceAnglePitch~=0 or sub.oFaceAngleYaw~=0 or sub.oFaceAngleRoll~=0
            or sub.oVelX~=0 or sub.oVelY~=0 or sub.oVelZ~=0 then return nil end
    return sub
end

function Deck.standing(g,m)
    if not m.floor or not m.floor.object then return nil end
    local sub=Deck.current(g)
    if not sub or m.floor.object~=sub then return nil end
    local context=g.JIMMIE_ROUTE16.performanceContext()
    if context and context.mode=="16" and context.level==23 and context.area==2 then return sub end
end

function Deck.surface(g,s,sub)
    if type(s.flags)~="number" or (s.flags & g.SURFACE_FLAG_INTANGIBLE)~=0 then return false end
    if sub then
        return s.object==sub and s.poolType==g.SURFACE_POOL_DYNAMIC and (s.flags & g.SURFACE_FLAG_DYNAMIC)~=0
    end
    return s.object==nil and s.poolType==g.SURFACE_POOL_STATIC and (s.flags & g.SURFACE_FLAG_DYNAMIC)==0
end

return Deck
