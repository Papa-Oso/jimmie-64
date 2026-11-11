-- Deliberate source-triggered copying bit; never a 44-slot reflex.
-- This policy selects opportunities only. The shared voice channel owns playback.
local Policy={}; local P={};P.__index=P
local SALIENT={
    [11]="mv_here_we_go", [34]="mv_doh", [35]="mv_game_over", [36]="mv_hello",
    [40]="mv_so_longa_bowser", [42]="mv_lets_a_go", [43]="mv_okey_dokey",
}
local MAMMA="mv_mama_mia"
local function finite(v) return type(v)=="number" and v==v and v>-math.huge and v<math.huge end
function Policy.new(options)
    options=type(options)=="table" and options or {}
    return setmetatable({random=options.random,seed=31337,serial=0,clock=0,pending={},lastAttempt={},
        lastOther=-1000000,lastMamma=-1000000,lastByCat={},
        OTHER_GAP=45,CATEGORY_GAP=90,OTHER_CHANCE=0.25,MAMMA_GAP=6},P)
end
function P:roll()
    if self.random then
        local ok,value=pcall(self.random)
        return ok and finite(value) and value>=0 and value<1 and value or 1
    end
    -- Private cosmetic RNG: no new draws from the game's/shared Lua RNG.
    self.seed=(self.seed*48271)%2147483647
    return (self.seed-1)/2147483646
end
function P:reset(scene,now)
    local t=finite(now) and now or self.clock
    self.pending={};self.lastAttempt={};self.scene=scene;self.clock=t
    -- Voice.clearScene(true) separately preserves genuine source audio. This
    -- policy discards old-scene echo memory rather than attaching an impression
    -- to a different scene; actual-play cooldowns and counts remain intact.
    -- Actual-play cooldowns persist; a level transition cannot refresh the bit.
end
function P:plan(sound,now,state)
    if not finite(now) or not finite(sound) or sound%1~=0 then return nil end
    local s=state or {};self.clock=now
    if s.scene and s.scene~=self.scene then self:reset(s.scene,now) end
    if s.playerIndex~=0 or s.enabled==false or s.voiceEnabled==false or
        s.paused==true or s.silent==true or s.mode=="silent" then return nil end
    local mamma=sound==29
    local category=mamma and MAMMA or SALIENT[sound]
    if not category then return nil end
    if mamma then
        -- Preserve the user's signature even during death/AFK/brief despawn.
        if now-self.lastMamma<self.MAMMA_GAP then return nil end
    else
        if s.dead==true or s.afk==true or s.available==false or s.gameplay==false then return nil end
        if now-self.lastOther<self.OTHER_GAP or now-(self.lastByCat[category] or -1000000)<self.CATEGORY_GAP then return nil end
    end
    if now-(self.lastAttempt[category] or -1000000)<0.25 then return nil end
    self.lastAttempt[category]=now -- debounce source notifications, not a playback budget
    if not mamma and self:roll()>=self.OTHER_CHANCE then return nil end
    self.serial=self.serial+1
    local bit={id="mimic-"..self.serial,kind=mamma and "signature_echo" or "deliberate_mimic",
        source_sound=sound,category=category,event=mamma and "mario_mama_mia" or "mimic",
        priority=mamma and 85 or 50,volume=0.8,ttl=mamma and 7 or 3.5,
        notBefore=now+(mamma and 0.45 or 0.35),created_at=now,
        expires_at=now+(mamma and 7 or 3.5),self_awareness="caught_copying"}
    self.pending[category]=bit
    return bit
end
function P:played(category,now,seconds)
    if type(category)~="string" or not finite(now) then return false end
    -- Accept either the known category or its actual registered filename.
    category=category:match("^(.+)_%d+%.ogg$") or category
    local bit=self.pending[category]
    if not bit or now>bit.expires_at or now<bit.created_at then return false end
    self.pending[category]=nil;self.clock=now;self.lastByCat[category]=now
    if category==MAMMA then self.lastMamma=now else self.lastOther=now end
    -- Playback bookkeeping only. The impression itself is the joke.
    return {kind=category==MAMMA and "mama_echo" or "deliberate_mimic",id=bit.id,
        source_sound=bit.source_sound,echo_category=category,at=now,self_awareness="caught_copying"}
end
return Policy
