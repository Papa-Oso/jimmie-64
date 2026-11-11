"""Private actual-Castle Lua rail regression. Uses the existing local triangle
adapter; no install, engine launch, personal writes, or public collision export.
This adapter is not native/rendered proof. Pair with guarded headless receipts.
"""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
ADAPTER=ROOT.parent/'jimmie-64/docs/skating-playtest-fix-20261107/castle-geometry'
sys.path.insert(0,str(ADAPTER))
import test_actual_collision_lua as model
MOD=ROOT/'mods/jimmie'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def scan(moving=False,sabotage=None):
 h=model.Harness(MOD);p=h.pt((-890,512,-490));q=h.pt((-700,512,-700))
 ctx=h.lua.table_from(dict(frame=0,epoch=0,speed=0,forwardX=190,forwardZ=-210));peak=0;hit=False;r=None
 for frame in range(1,125):
  ctx.frame=frame
  if moving and frame>1:
   # Deliberately change the live approach direction while traversing the local
   # neighborhood. Numeric hints remain anchored; final clearance stays live.
   p.x=-890-frame*.1;p.z=-490-frame*4
   ctx.forwardX=q.x-p.x;ctx.forwardZ=q.z-p.z
  s=h.world._railScan
  if sabotage and s is not None and s.phase==4:
   hit=True
   if sabotage=='water':h.lua.execute('g.find_water_level=function() return 1000 end')
   else:q.x,q.y,q.z=s.points[1].x,s.points[1].y,s.points[1].z
  r,d=h.run('railScan',p,q,ctx);peak=max(peak,d['budget']['calls'])
  if r is not None or hit:break
 return h,r,dict(frames=frame,proposal=r is not None,peak_calls=peak,sabotage_reached=hit)
def main():
 checks={};results={}
 # Large between-frame player relocation still invalidates numeric discovery.
 # This is a lifecycle check, not the removed personal-space veto.
 for name,kwargs in [('upper',{}),('moving_turn',dict(moving=True)),('fresh_water',dict(sabotage='water')),('fresh_player_relocation',dict(sabotage='player'))]:
  h,r,d=scan(**kwargs);results[name]=d;checks[name]=(r is not None)==(not name.startswith('fresh_'));checks[name+'_budget']=d['peak_calls']<=3000
  if name.startswith('fresh_'):checks[name+'_reached']=d['sabotage_reached']
 h,rail,_=scan();P=h.pt;q=P((-700,512,-700))
 result,d=h.run('validateRail',rail,q);checks['retained_rail_freshly_proven']=result is not None
 result,d=h.run('arc',P((-890,512,-490)),rail.a,90,h.lua.table_from(dict(landingRadius=0)));checks['blocked_initial_entry_refused']=result is None
 result,d=h.run('arc',P((-890.63597153868,512,-563.82190709381)),rail.a,90,h.lua.table_from(dict(landingRadius=0)));checks['actual_moving_entry_pose_clear']=result is not None
 h.lua.execute('g.find_water_level=function() return 1000 end');result,d=h.run('validateRail',rail,q);checks['cached_rail_new_water_refused']=result is None
 h,rail,_=scan();result,d=h.run('validateRail',rail,rail.a);checks['cached_rail_player_overlap_allowed']=result is not None
 for name,bad in [('nan',h.pt((float('nan'),512,0))),('infinity',h.pt((0,float('inf'),0))),('missing',h.lua.table_from(dict(x=0,y=512)))]:
  result,d=h.run('validateRail',rail,bad);checks['cached_rail_invalid_player_'+name+'_refused']=result is None
 h=model.Harness(MOD);P=h.pt
 for name,method,args in [('wall','clear',[P((-716,512,-460))]),('ceiling','clear',[P((-716,1620,-430))]),('wide_footprint','support',[P((-843,305,-100)),28])]:
  result,d=h.run(method,*args);checks[name+'_refused']=not d['accepted']
 result,d=h.run('featureAt',P((-843.5,614,-430)),0,1);checks['bad_cap_junction_not_rail']=result is None or result.feature!='two-sided-rail'
 result,d=h.run('featureAt',P((-996,228*512/485,-100)),0,1);checks['broad_stairs_not_rail']=result is None or result.feature!='two-sided-rail'
 p,q=P((-890,512,-490)),P((-700,512,-700));ctx=h.lua.table_from(dict(frame=1,epoch=0,speed=0,forwardX=190,forwardZ=-210))
 h.run('railScan',p,q,ctx);index=h.world._railScan.index;h.run('railScan',p,q,ctx);checks['duplicate_frame_no_progress']=h.world._railScan.index==index
 ctx.frame=2;ctx.epoch=1;h.run('railScan',p,q,ctx);checks['epoch_restarts']=h.world._railScan.epoch==1 and h.world._railScan.started==2
 h.lua.execute('local n=0;g.clock_elapsed_f64=function() n=n+.001;return n end');ctx.frame=3;h.run('railScan',p,q,ctx);checks['elapsed_budget_refuses']=h.world.lastBudget.reason=='native-time-budget' and h.world._railScan is None
 # Ordinary required follow crossing wins over optional rail selection.
 h=model.Harness(MOD);p,q=h.pt((-939.5,512,-390)),h.pt((-939.5,0,200));p.onGround=True;q.vx=0;q.vz=0
 controller=h.opp.new(h.world,h.lua.eval('function() return .5 end'));checks['no_six_second_startup_delay']=controller.nextFun==0
 ctx=h.lua.table_from(dict(frame=1,time=1,enabled=True,scene='castle',instance=h.lua.table(),phys=p,area=h.lua.table(),terrain=h.lua.table(),playerInstance=h.lua.table(),player=q,players=h.lua.table_from([q]),playerGrounded=True))
 step=h.lua.eval('function(w,c,p,ctx)return w:transaction(function()return c:step(p,ctx)end)end')
 out=step(h.world,controller,p,ctx);checks['required_follow_priority']=out is not None and out.kind=='follow'
 controller.nextFun=100;h.lua.eval('function(c,ctx)c:cancel("scene",ctx)end')(controller,ctx);checks['lifecycle_clears_old_fun_delay']=controller.nextFun==0 and controller.pendingRail is None
 # A budget refusal revokes movement, retaining numeric hints for fresh proof.
 controller.pendingRail=h.lua.table_from(dict(rail=h.lua.table(),time=1,scene='castle',area=ctx.area))
 h.lua.eval('function(c,ctx)c:cancel("native-time-budget",ctx)end')(controller,ctx)
 checks['budget_keeps_hint_not_task']=controller.pendingRail is not None and controller.task is None
 h.lua.eval('function(c,ctx)c:cancel("not-gameplay",ctx)end')(controller,ctx)
 checks['gameplay_cancel_drops_hint']=controller.pendingRail is None
 # The retained rail cannot launch on a different area/scene/actor identity.
 controller.pendingRail=h.lua.table_from(dict(rail=h.lua.table_from(dict(a=h.pt((-850,590,-385)))),time=1,scene='old',area=ctx.area));ctx.frame=2;ctx.time=2;step(h.world,controller,p,ctx);checks['wrong_scene_hint_discarded']=controller.pendingRail is None
 # Contact entry must not double-charge full validation plus full trimming.
 h,rail,_=scan();p=h.pt((rail.a.x,rail.a.y,rail.a.z));p.onGround=True;q=h.pt((-700,512,-700));q.vx=0;q.vz=0
 controller=h.opp.new(h.world,h.lua.eval('function()return .5 end'))
 ctx=h.lua.table_from(dict(frame=30,time=10,enabled=True,scene='castle',instance=h.lua.table(),phys=p,area=h.lua.table(),terrain=h.lua.table(),playerInstance=h.lua.table(),player=q,players=h.lua.table_from([q]),playerGrounded=True))
 controller.pendingRail=h.lua.table_from(dict(rail=rail,time=10,scene='castle',area=ctx.area));controller.nextProbe=20
 out=h.lua.eval('function(w,c,p,ctx)return w:transaction(function()return c:step(p,ctx)end)end')(h.world,controller,p,ctx)
 checks['actual_rail_contact_entry']=out is not None and out.grind is True
 checks['contact_entry_budget']=h.world.lastBudget.reason is None and h.world.lastBudget.calls<3000
 # Exact-point geometry reuse is limited to a single synchronous transaction.
 h=model.Harness(MOD);p=h.pt((-1100,512,-1000))
 reused=h.lua.eval('function(w,p)return w:transaction(function()local first=w:clear(p);local before=w._budget.calls;local second=w:clear(p);return {first=first,second=second,extra=w._budget.calls-before}end)end')(h.world,p)
 checks['same_transaction_exact_clear_reused']=reused is not None and reused.first is True and reused.second is True and reused.extra==0
 player_clear=h.lua.eval('function(w,p)return w:transaction(function()w:clear(p);return w:segment(p,p,p)end)end')(h.world,p)
 checks['cached_geometry_allows_player_overlap']=player_clear is True
 invalid_clear=h.lua.eval('function(w,p)return w:transaction(function()w:clear(p);return w:segment(p,p,{x=0/0,y=p.y,z=p.z})end)end')(h.world,p)
 checks['cached_geometry_still_rejects_invalid_player']=not invalid_clear
 h.lua.execute('g.find_water_level=function()return 1000 end');result,d=h.run('clear',p)
 checks['next_transaction_sees_new_hazard']=not result
 h=model.Harness(MOD);c=h.opp.new(h.world,h.lua.eval('function()return .5 end'));ctx=h.lua.table_from(dict(frame=50,time=1))
 c.pendingRail=h.lua.table_from(dict(rail=h.lua.table_from(dict(indexKey=12)),time=1,scene='castle'))
 cancel=h.lua.eval('function(c,ctx)c:cancel("native-time-budget",ctx)end')
 cancel(c,ctx);one=c.pendingRail is not None;cancel(c,ctx);two=c.pendingRail is not None;cancel(c,ctx)
 checks['third_budget_failure_yields_candidate']=one and two and c.pendingRail is None and h.world._railDeferred[12]==350
 h.lua.eval('function(c,ctx)c:cancel("areas-cleared",ctx)end')(c,ctx)
 checks['lifecycle_clears_deferred_index']=h.world._railDeferred is None
 # Floor snapshots read each native component once, then validate the copy.
 h=model.Harness(MOD)
 result=h.lua.eval("""function(w,g)
  local reads=0
  local function vector(x,y,z)local data={x=x,y=y,z=z};return setmetatable({},{__index=function(_,k)reads=reads+1;return data[k]end})end
  local surf={type=0,poolType=0,flags=0,normal=vector(0,1,0),vertex1=vector(0,512,0),vertex2=vector(100,512,0),vertex3=vector(0,512,100)}
  g.find_floor=function()return 512,surf end
  local floor=w:floor(20,536,20)
  return {accepted=floor~=nil,reads=reads}
 end""")(h.world,h.lua.globals().g)
 checks['floor_components_read_once']=result.accepted is True and result.reads==12
 h.lua.execute('g.find_floor=function()return 512,{type=0,poolType=0,flags=0,normal={x=0,y=1,z=0},vertex1={x=0/0,y=512,z=0},vertex2={x=100,y=512,z=0},vertex3={x=0,y=512,z=100}}end')
 result,d=h.run('floor',20,536,20);checks['copied_invalid_vertex_refused']=result is None
 # Admission allowance is bounded and transaction-local; query cap is unchanged.
 h=model.Harness(MOD)
 budget_case=h.lua.eval("""function(w,g,admit,elapsed,calls)
  local now=0;g.clock_elapsed_f64=function()return now end
  return w:transaction(function()
   if admit then w:allowRailAdmission() end
   now=elapsed
   if calls then w._budget.calls=calls end
   w:_tick();return true
  end)
 end""")
 checks['ordinary_four_ms_refuses']=budget_case(h.world,h.lua.globals().g,False,.005,None) is None
 checks['admission_five_ms_allowed']=budget_case(h.world,h.lua.globals().g,True,.005,None) is True
 checks['admission_eight_ms_refuses']=budget_case(h.world,h.lua.globals().g,True,.008,None) is None
 checks['admission_query_cap_unchanged']=budget_case(h.world,h.lua.globals().g,True,.001,3000) is None and h.world.lastBudget.reason=='native-query-budget'
 checks['next_transaction_four_ms_restored']=budget_case(h.world,h.lua.globals().g,False,.005,None) is None and h.world.lastBudget.timeLimit==.004
 report=dict(passed=all(checks.values()),checks=checks,results=results,source_sha256={n:sha(MOD/n) for n in ('skate_probes.lua','skate_opportunities.lua')},adapter_sha256=sha(ADAPTER/'test_actual_collision_lua.py'),collision_sha256=model.geo.META['collision_sha256'],limits='Offline actual static Castle triangles with approximate wall adapter, not native or rendered play. No forced rail plan or source map coordinates.')
 out=ROOT/'build/natural-rails';out.mkdir(parents=True,exist_ok=True);(out/'focused.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
