"""Controlled rail physics tests: pure energy + actual Castle static query adapter.
These seed contact states to isolate mechanics; they are NOT natural discovery.
Flat case slides over real broad native floor, not a claimed detected narrow rail.
"""
from pathlib import Path
import json,sys,math,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_jimmie_natural_rails as base
from lupa import LuaRuntime
ROOT=Path(__file__).resolve().parents[1]
def run_case(name,a,b,exit,speed,block_exit=False):
 h=base.model.Harness(base.MOD);P=h.pt
 if block_exit:h.world.arc=h.lua.eval('function()return nil end')
 rail=h.lua.table_from(dict(kind='grind',a=P(a),b=P(b),exit=P(exit)))
 length=math.dist(a,b);v=[speed*(b[i]-a[i])/length for i in range(3)]
 p=P(a);p.vx,p.vy,p.vz=v;p.onGround=True;q=P((-700,512,-700));q.vx=0;q.vz=0
 c=h.opp.new(h.world,h.lua.eval('function()return .5 end'));ctx=h.lua.table_from(dict(frame=1,time=1/30,enabled=True,scene='castle',instance=h.lua.table(),phys=p,area=h.lua.table(),terrain=h.lua.table(),playerInstance=h.lua.table(),player=q,players=h.lua.table_from([q]),playerGrounded=True))
 plan=h.lua.table_from(dict(a=P(a),b=P(a),landing=P(a),duration=18,contactEntry=True))
 step=h.lua.eval('function(w,c,p,ctx,plan,rail)return w:transaction(function()if plan then return c:begin(plan,"rail",p,ctx,rail) else return c:advance(p,ctx)end end)end')
 rows=[];events=[]
 for frame in range(1,151):
  ctx.frame=frame;ctx.time=frame/30
  out=step(h.world,c,p,ctx,plan if frame==1 else None,rail)
  if h.world.lastBudget.reason:raise AssertionError((name,frame,h.world.lastBudget.reason))
  if out:
   for k in ('x','y','z'):p[k]=out.position[k]
   p.vx,p.vy,p.vz=out.velocity.x,out.velocity.y,out.velocity.z;p.onGround=out.onGround
   rows.append(dict(frame=frame,phase=out.phase,grind=out.grind,speed=c.task.grindSpeed if c.task else None,pos=[p.x,p.y,p.z],grounded=p.onGround))
  for e in c.drain(c).values():events.append({k:v for k,v in e.items() if isinstance(v,(str,int,float,bool))})
  if c.task is None:break
 return dict(name=name,frames=frame,rows=rows,events=events,final_grounded=p.onGround,initial=speed)
def main():
 l=LuaRuntime(unpack_returned_tuples=True);O=l.execute((base.MOD/'skate_opportunities.lua').read_text());checks={};pure={}
 for name,grade in [('uphill',.70710678),('flat',0),('downhill',-.70710678)]:
  speed=24;distance=0;values=[];energy=.5*speed*speed
  dissipative=True
  # Slippery passive glide takes longer to stop; live rides still cap at 60 ticks.
  for i in range(720):
   nxt,delta,acc=O.railDynamics(speed,grade);distance+=delta
   next_energy=.5*nxt*nxt+2.5*grade*distance
   dissipative=dissipative and next_energy<=energy+1e-7;energy=next_energy;speed=nxt;values.append(speed)
  pure[name]=dict(first=values[0],last=speed,distance=distance,max_speed=max(values),energy_nonincreasing=dissipative)
 checks['uphill_slows_and_stops']=pure['uphill']['first']<24 and pure['uphill']['last']==0
 checks['flat_friction_stops']=pure['flat']['first']<24 and pure['flat']['last']==0
 checks['downhill_accelerates_but_capped']=24<pure['downhill']['first']<=pure['downhill']['max_speed']<=48
 checks['all_unpowered_energy_nonincreasing']=all(r['energy_nonincreasing'] for r in pure.values())
 checks['rest_flat_not_powered']=O.railDynamics(0,0)[0]==0
 checks['rest_uphill_not_powered']=O.railDynamics(0,.7)[0]==0
 checks['downhill_can_roll_from_rest']=O.railDynamics(0,-.7)[0]>0
 upper=(-854.406282602059,590,-385.79616044948193);lower=(-854.406282602059,446,-241.79616044948193);exit=(-974.406282602059,313.53399658203,-169.79616044948193)
 cases=[run_case('native_slope_downhill',upper,lower,exit,8),run_case('native_slope_uphill_stall',lower,upper,exit,8),run_case('native_slope_uphill_momentum',lower,upper,exit,48),run_case('real_flat_floor_friction',(-1100,512,-1000),(-1100,512,-850),(-1100,512,-650),8),run_case('real_flat_floor_stall',(-1100,512,-1000),(-1100,512,-850),(-1100,512,-650),2)]
 for case in cases:
  name=case['name'];grind=[r for r in case['rows'] if r['grind'] and r['phase']!='dismount'];stalls=[e for e in case['events'] if e['kind']=='rail-stalled']
  checks[name+'_bounded']=case['frames']<150
  checks[name+'_grounded_exit']=case['final_grounded'] and any(e['kind']=='landing-observed' for e in case['events'])
  checks[name+'_speed_cap']=all(0<=r['speed']<=48 for r in grind if r['speed'] is not None)
  if 'stall' in name:checks[name+'_stalls']=bool(stalls)
  elif 'downhill' in name:checks[name+'_accelerates']=len(grind)>1 and grind[1]['speed']>grind[0]['speed']
  else:checks[name+'_slows']=len(grind)>1 and grind[1]['speed']<grind[0]['speed']
 blocked=run_case('blocked_dismount',lower,upper,exit,2,True)
 checks['blocked_dismount_bounded']=blocked['frames']<=12
 checks['blocked_dismount_safe_supported_handback']=blocked['final_grounded'] and any(e['kind']=='rail-stall-handback' for e in blocked['events'])
 checks['blocked_dismount_no_phantom_landing']=not any(e['kind']=='landing-observed' for e in blocked['events'])
 cases.append(blocked)
 report=dict(passed=all(checks.values()),checks=checks,pure=pure,cases=cases,source_sha256=hashlib.sha256((base.MOD/'skate_opportunities.lua').read_bytes()).hexdigest(),limits='Pure Lua dynamics plus existing approximate static Castle collision adapter. Controlled seeded-contact mechanics, not native engine/render or natural discovery. Flat mechanics use actual broad Castle floor, not a claimed grindable narrow rail.')
 out=ROOT/'build/natural-rails';out.mkdir(exist_ok=True,parents=True);(out/'physics-focused.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(passed=report['passed'],checks=checks,pure=pure,cases=[{k:v for k,v in c.items() if k not in ('rows','events')} for c in cases]),indent=2));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
