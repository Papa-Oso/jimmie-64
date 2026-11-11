from pathlib import Path
import json,hashlib
from lupa import LuaRuntime
P=Path(__file__).resolve().parent;ROOT=P.parent;BASE=ROOT/'mods/jimmie';OUT=ROOT/'build/outcome-tests';OUT.mkdir(parents=True,exist_ok=True)
LUA=r'''
local function expect(v,m) if not v then error(m or 'assertion') end end
function make()
 local b={header={gfx={animInfo={}}}};local d={header={gfx={animInfo={}}}}
 local c=MOTION.new(BANK.new())
 local function step(args)
  local q={body=b,board=d,scene=1,dt=1/30,flightDuration=.7};for k,v in pairs(args or {}) do q[k]=v end
  local ok,out=c:step(q);expect(ok or q.externalOwner,out);return out
 end
 return c,step,b
end
function landed(step)
 local events={}
 for i=1,20 do local out=step();if out.completedTrick then events[#events+1]=out.completedTrick;expect(out.clip~='idle','completion after riding') end end
 return events
end
function run(name)
 if name=='lottery' then
  local roll=0;local count=0;local o=OUTCOMES.new{random=function(a,b) expect(a==1 and b==1000);roll=roll+1;return roll end}
  for id=1,1000 do local fail=o:complete({source='motion_controller',scene='1',id=id,kind='trick',eligible=true},'1');if fail then count=count+1 end end
  expect(count==75 and o.rolls==1000);return
 end
 if name=='duplicates' then
  local calls=0;local o=OUTCOMES.new{random=function() calls=calls+1;return 75 end};local e={source='motion_controller',scene='1',id=1,kind='trick',eligible=true}
  expect(o:complete(e,'1'));for i=1,20 do expect(not o:complete(e,'1')) end;expect(calls==1);e.id=2;o=OUTCOMES.new{random=function() return 76 end};expect(not o:complete(e,'1'));return
 end
 if name=='respawn_clock' then
  local o=OUTCOMES.new();local old,new={},{};o:crashed('1');expect(o:remaining('1',old,9)==0);expect(not o:recovered('1',nil,10));expect(o.pendingRecovery)
  expect(OUTCOMES.BRACE_SECONDS==10);expect(o:recovered('1',new,20));expect(o:remaining('1',new,20)==10);expect(not o:recovered('1',new,21));expect(o:remaining('1',new,25)==5);expect(o:remaining('1',new,29.999)>0);expect(o:remaining('1',new,30)==0);return
 end
 if name=='new_crash_scene' then
  local o=OUTCOMES.new();local b={};o:crashed('1');o:recovered('1',b,10);o:crashed('1');expect(o:remaining('1',b,11)==0);o:reset('2');expect(not o:recovered('2',{},20));return
 end
 if name=='invalid_event' then local o=OUTCOMES.new{random=function() error('must not roll') end};expect(not o:complete({source='motion_controller',scene='wrong',id=1,kind='trick',eligible=true},'1'));expect(o.rolls==0);return end
 local c,step=make()
 for i=1,10 do step{inAir=true,airTime=i/30,trickTakeoff=name~='fall',requestedTrick='kickflip'} end
 if name=='interrupt' then step{externalOwner=true};local events=landed(step);expect(#events==0);return end
 if name=='debug' then step{debugClip='trick'};local events=landed(step);expect(#events==0);return end
 if name=='grind' then
  for i=1,20 do local out=step{railContact=true,balanceClip='balance038'};expect(not out.completedTrick) end
  for i=1,10 do step{inAir=true,airTime=i/30,trickTakeoff=false} end
  local events=landed(step);expect(#events==1 and events[1].kind=='grind');return
 end
 local events=landed(step)
 if name=='fall' then expect(#events==0);return end
 expect(#events==1 and events[1].kind=='trick' and events[1].clip=='kickflip')
 local o=OUTCOMES.new{random=function() return 1 end};expect(o:complete(events[1],'1'));expect(not o:complete(events[1],'1'));return
end
'''
def runtime():
 l=LuaRuntime(unpack_returned_tuples=True);l.execute('function smlua_anim_util_register_animation(...) end;function smlua_anim_util_set_animation(o,name) o.header.gfx.animInfo.curAnim=name end')
 for key,path in [('BANK',BASE/'original_clip_bank.lua'),('MOTION',BASE/'original_motion_controller.lua'),('OUTCOMES',BASE/'trick_outcomes.lua')]:l.globals()[key]=l.execute(path.read_text(encoding='utf-8-sig'))
 l.execute(LUA);return l
if __name__=='__main__':
 names=['completed_trick','fall','interrupt','debug','grind','lottery','duplicates','respawn_clock','new_crash_scene','invalid_event'];results=[]
 for name in names:
  try:runtime().globals().run(name);results.append({'name':name,'passed':True})
  except Exception as e:results.append({'name':name,'passed':False,'error':str(e)})
 l=runtime();compile_result=l.eval('function(code) local f,e=load(code);return f~=nil,e end')((BASE/'main.lua').read_text());assert compile_result[0],compile_result
 harness_result=l.eval('function(code) local f,e=load(code);return f~=nil,e end')((BASE/'main.lua').read_text()+'\n'+(P/'jimmie_harnesses/outcomes.template.lua').read_text());assert harness_result[0],harness_result
 report={'harness_compiles':True,'passed':sum(x['passed'] for x in results),'total':len(results),'cases':results,'main_compiles':True,'native_game_run':False,'sources':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [BASE/'original_clip_bank.lua',BASE/'main.lua',BASE/'original_motion_controller.lua',BASE/'trick_outcomes.lua']}}
 (OUT/'verification.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2));assert report['passed']==report['total']
