-- Test-only appended harness. No Mario/camera/save writes. Dummy backend cannot
-- prove audible quality. QA auditions test decoding + the shared audio channel,
-- not gameplay event detection; normal event playback is logged separately.
local voiceProbeTick=0
local voiceProbeStart=nil
local voiceProbeSeen={}
local voiceProbeAuditions={}
local voiceProbeOriginalPlayed=VOICE.onPlayed
VOICE.onPlayed=function(meta,event,seconds)
    if voiceProbeOriginalPlayed then voiceProbeOriginalPlayed(meta,event,seconds) end
    assert(gameplayReady and not in_jimmie_title(),'companion speech before gameplay/title handoff')
    local actual=meta and VOICE.REGISTRY[meta.name] or {}
    local source=actual and actual.source or 'unknown'
    print('[fork-spoken] PLAY event='..tostring(event)..' source='..tostring(source)..' clip='..tostring(meta and meta.name))
    if event=='qa_audition' then voiceProbeAuditions[source]=true else voiceProbeSeen[source]=true end
end
hook_event(HOOK_UPDATE,function()
    if not gameplayReady or in_jimmie_title() or not jimmie or not originalBoard then return end
    voiceProbeTick=voiceProbeTick+1
    if not voiceProbeStart then
        voiceProbeStart=voiceProbeTick
        local count=0
        for cat,files in pairs(SOUND_FILES) do
            local pool=load_category(cat)
            assert(#pool==#files,'bounded sample load failed: '..cat)
            count=count+#pool
        end
        assert(count==37,'unexpected sample count')
        print('[fork-spoken] LOADED 37 allowed recordings; no new model/service')
    end
    local age=voiceProbeTick-voiceProbeStart
    if age==180 or age==450 then
        local name=age==180 and 'mv_mama_mia_01.ogg' or 'real_boing_boing_01.ogg'
        local cat=age==180 and 'mv_mama_mia' or 'real_boing_boing'
        local meta=VOICE.REGISTRY[name]
        local accepted=VOICE.external(load_category(cat)[1],meta.seconds,
            {event='qa_audition',key=name,text=meta.text,ttl=6,priority=80})
        print('[fork-spoken] QA_REQUEST clip='..name..' accepted='..tostring(accepted))
    end
    if age==660 then
        assert(voiceProbeAuditions.authored and voiceProbeAuditions.real_vod,'both QA source playbacks required')
        print('[fork-spoken] COMPLETE decoded37; shared-channel authored+real QA starts; normalAuthored='..tostring(voiceProbeSeen.authored==true)..' normalReal='..tostring(voiceProbeSeen.real_vod==true))
    end
end)
