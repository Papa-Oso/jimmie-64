"""Controlled admission checks on real Castle triangles. Not natural or rendered play.
The candidate is discovered first, then supplied to isolate the moving-player gate.
No engine launch and no installed-file changes.
"""
from pathlib import Path
import json,hashlib,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_jimmie_natural_rails as base
ROOT=Path(__file__).resolve().parents[1]

def case(speed=28,direction=(0,1),origin=(-859.85136960207,512,-617.24525406147),intrusion=False):
 h,r,scan=base.scan();p=h.pt(origin);p.vx=0;p.vy=0;p.vz=20;p.onGround=True
 q=h.pt((-700,512,-700));q.vx=direction[0]*speed;q.vz=direction[1]*speed
 if intrusion:q.x,q.y,q.z=r.a.x,r.a.y,r.a.z
 c=h.opp.new(h.world,h.lua.eval('function()return .5 end'))
 ctx=h.lua.table_from(dict(frame=100,time=10,enabled=True,scene='castle',instance=h.lua.table(),phys=p,area=h.lua.table(),terrain=h.lua.table(),playerInstance=h.lua.table(),player=q,players=h.lua.table_from([q]),playerGrounded=True))
 c.pendingRail=h.lua.table_from(dict(rail=r,time=10,scene='castle',area=ctx.area));c.nextProbe=20
 out=h.lua.eval('function(w,c,p,ctx)return w:transaction(function()return c:step(p,ctx)end)end')(h.world,c,p,ctx)
 return dict(accepted=out is not None and out.kind=='rail',budget=dict(h.world.lastBudget.items()),diagnostic=dict(c.diagnostic.items()),rail_points=len(r.points),scan=scan)

def range_case(contact,gap):
 h,r,_=base.scan();p=h.pt((r.a.x,r.a.y,r.a.z) if contact else (-859.85136960207,512,-617.24525406147));p.vx=0;p.vy=-14 if contact else 0;p.vz=20;p.onGround=True
 q=h.pt((-700,512,-700));q.vx=0;q.vz=0
 c=h.opp.new(h.world,h.lua.eval('function()return .5 end'));ctx=h.lua.table_from(dict(frame=1,time=1/30,enabled=True,scene='castle',instance=h.lua.table(),phys=p,area=h.lua.table(),terrain=h.lua.table(),playerInstance=h.lua.table(),player=q,players=h.lua.table_from([q]),playerGrounded=True))
 if contact:plan=h.lua.table_from(dict(a=p,b=r.a,landing=r.a,duration=18,contactEntry=True))
 else:plan,_=h.run('arc',p,r.a,90,h.lua.table_from(dict(landingRadius=0)))
 start=h.lua.eval('function(w,c,p,ctx,plan,r)return w:transaction(function()return c:begin(plan,"rail",p,ctx,r)end)end')
 advance=h.lua.eval('function(w,c,p,ctx)return w:transaction(function()return c:advance(p,ctx)end)end')
 out=start(h.world,c,p,ctx,plan,r)
 assert out is not None
 for k in ('x','y','z'):p[k]=out.position[k]
 p.vx,p.vy,p.vz=out.velocity.x,out.velocity.y,out.velocity.z;p.onGround=out.onGround
 snapshot=[p.x,p.y,p.z,p.vx,p.vy,p.vz,p.onGround]
 ctx.frame=2;ctx.time=2/30;q.x=p.x+gap;q.z=p.z;q.vx=48
 out=advance(h.world,c,p,ctx)
 events=[dict(e.items()) for e in c.drain(c).values()]
 result=dict(cancelled=c.task is None,no_output=out is None,unchanged=[p.x,p.y,p.z,p.vx,p.vy,p.vz,p.onGround]==snapshot,phase=c.task.phase if c.task else None,events=[{k:v for k,v in e.items() if isinstance(v,(str,int,float,bool))} for e in events])
 if out is not None:
  for k in ('x','y','z'):p[k]=out.position[k]
  p.vx,p.vy,p.vz=out.velocity.x,out.velocity.y,out.velocity.z;p.onGround=out.onGround
  ctx.frame=3;ctx.time=3/30;q.x=p.x+200;q.z=p.z+200;q.vx=0
  advance(h.world,c,p,ctx)
  result['turn_back_does_not_restart_grind']=c.task is None or c.task.phase!='grind'
 return result

def main():
 results={str(s):case(s) for s in (0,8,20,28,32,40,48,49)}
 results['away']=case(40,(0,-1));results['player_intrusion']=case(intrusion=True)
 results['blocked_entry']=case(origin=(-890,512,-490))
 checks={str(s)+'_allowed':results[str(s)]['accepted'] for s in (0,8,20,28,32)}
 # These longer approaches intentionally lose the new 400-unit entry window.
 for key in ('40','48','player_intrusion'):
  checks[key+'_late_entry_refused']=not results[key]['accepted'] and results[key]['diagnostic'].get('railReason')=='entry-outside-follow-window'
 checks.update({k+'_refused':not results[k]['accepted'] for k in ('49','away','blocked_entry')})
 results['stationary_player_intrusion']=case(speed=0,intrusion=True)
 checks['player_overlap_allowed']=results['stationary_player_intrusion']['accepted']
 checks['whole_entry_budget']=all(r['budget']['calls']<=3000 and not r['budget'].get('reason') for r in results.values())
 checks['extended_real_rail']=results['28']['rail_points']==11
 for contact in (False,True):
  key='grind_hard_range' if contact else 'entry_hard_range';result=range_case(contact,1001);results[key]=result
  checks[key+'_continuous_handback']=result['cancelled'] and result['no_output'] and result['unchanged'] and any(e.get('reason')=='player-outpaced-rail' for e in result['events'])
 result=range_case(True,850);results['soft_range']=result
 checks['soft_range_checked_dismount']=result['phase'] in ('dismount','exit') and any(e.get('reason')=='companion-range' for e in result['events'])
 checks['turn_back_no_reboost']=result.get('turn_back_does_not_restart_grind',False)
 # A first-step clearance refusal must not consume ownership/cooldown/RNG.
 h,r,_=base.scan();p=h.pt((-859.85136960207,512,-617.24525406147));p.vx=0;p.vy=0;p.vz=20;p.onGround=True;q=h.pt((-700,512,-700));q.vx=0;q.vz=28
 c=h.opp.new(h.world,h.lua.eval('function()return .5 end'));ctx=h.lua.table_from(dict(frame=100,time=10,enabled=True,scene='castle',instance=h.lua.table(),phys=p,area=h.lua.table(),terrain=h.lua.table(),playerInstance=h.lua.table(),player=q,players=h.lua.table_from([q]),playerGrounded=True))
 c.pendingRail=h.lua.table_from(dict(rail=r,time=10,scene='castle',area=ctx.area));c.nextProbe=20
 restore=h.lua.eval('function(w,p)local original=w.segment;w.segment=function(self,a,b,m)if a==p then return nil end;return original(self,a,b,m)end;return function()w.segment=original end end')(h.world,p)
 step=h.lua.eval('function(w,c,p,ctx)return w:transaction(function()return c:step(p,ctx)end)end')
 out=step(h.world,c,p,ctx)
 checks['entry_refusal_does_not_commit']=out is None and c.task is None and c.episode==0 and c.nextFollow==0 and c.pendingRail is not None
 restore();q.x,q.z=p.x+60,p.z;before=h.calls;ctx.frame=101;ctx.time=10+1/30
 out=step(h.world,c,p,ctx)
 checks['near_player_fresh_proof_allowed']=out is not None and out.kind=='rail' and h.calls>before and c.episode==1
 checks['cleared_entry_reuses_candidate']=out is not None and out.kind=='rail' and c.episode==1
 # Invalid observed player state still cancels ownership before native proof.
 q.x=float('nan');before=h.calls;ctx.frame=102;ctx.time=10+2/30;out=step(h.world,c,p,ctx)
 checks['invalid_player_cancels_without_native_proof']=out is None and h.calls==before and c.task is None and c.pendingRail is None and c.episode==1 and c.diagnostic.reason=='not-gameplay'
 # A stationary Mario no longer bypasses actual contact momentum viability.
 h,r,_=base.scan();p=h.pt((r.b.x,r.b.y,r.b.z));p.vx=0;p.vy=0;p.vz=0;q=h.pt((-700,512,-700));q.vx=0;q.vz=0
 c=h.opp.new(h.world,h.lua.eval('function()return .5 end'));ctx=h.lua.table_from(dict(player=q));r.a,r.b=r.b,r.a
 result=c.railKeepsUp(c,p,r,ctx,h.lua.table_from(dict(contactEntry=True,duration=18)))
 checks['stationary_zero_momentum_uphill_not_selected']=isinstance(result,tuple) and result[0] is False and result[1]=='predicted-momentum-stall'
 report=dict(passed=all(checks.values()),checks=checks,results=results,source_sha256={n:hashlib.sha256((base.MOD/n).read_bytes()).hexdigest() for n in ('skate_probes.lua','skate_opportunities.lua')},limits='Controlled pending-candidate admission with actual static Castle triangles and approximate offline wall adapter. Not natural discovery, native execution, human play or visual acceptance. Mario velocity is varied at fixed positions to isolate policy.')
 out=ROOT/'build/natural-rails';out.mkdir(parents=True,exist_ok=True);(out/'moving-eligibility.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
