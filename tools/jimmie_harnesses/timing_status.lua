-- Negative-only exact-engine snapshot check. Diagnostic Start remains ineligible.
-- This never starts, resets, completes or persists a native run.
local samples=0
local done=false
hook_event(HOOK_UPDATE,function()
    if done or not gameplayReady or in_jimmie_title() then return end
    samples=samples+1
    if samples<90 then return end
    assert(type(jimmie_get_run_status)=='function','Native personal snapshot binding absent')
    local a=jimmie_get_run_status()
    assert(type(a)=='table' and a.phase=='invalid','Diagnostic run must remain invalid')
    assert(a.elapsed_ms==0 and a.best_ms==0 and a.pb_known==false,'Diagnostic run must not invent elapsed/PB')
    assert(type(a.reason)=='string' and #a.reason>0 and type(a.timing_basis)=='string')
    assert(a.location_valid==true and a.level==16 and a.area==1,'Native current Castle location missing')
    for k,v in pairs(a) do
        assert(type(k)=='string' and (type(v)=='string' or type(v)=='number' or type(v)=='boolean'),'Only copied scalar fields allowed')
    end
    a.phase='running';a.best_ms=1;a.location_valid=false;a.level=99
    local b=jimmie_get_run_status()
    assert(b~=a and b.phase=='invalid' and b.best_ms==0 and b.pb_known==false,'Lua mutation reached native authority')
    assert(b.location_valid==true and b.level==16,'Lua mutation changed native location')
    done=true
    print('[personal-status] COMPLETE diagnosticInvalid=true copiedScalars=true mutationIsolated=true locationValid=true positiveStartProven=false')
end)
