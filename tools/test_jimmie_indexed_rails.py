"""Private actual-Castle index discovery tests. Offline, not native or played proof."""
from pathlib import Path
import sys,json,hashlib,math
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_jimmie_natural_rails as base
ROOT=Path(__file__).resolve().parents[1]
CASES=[('upper',(-890,512,-490),(-700,512,-700)),('lower_left',(-1000,0,100),(-700,0,200)),('lower_center',(-700,0,100),(-1000,0,200)),('mid_left',(-1000,305,-100),(-700,305,-100)),('upper_behind',(-1000,512,-600),(-700,512,-650)),('upper_right',(-700,512,-500),(-1000,512,-650))]
def harness():
 h=base.model.Harness(base.MOD)
 h.lua.globals().package.loaded.skate_rail_index=h.lua.execute((base.MOD/'skate_rail_index.lua').read_text())
 h.lua.execute('g.LEVEL_CASTLE=6;g.gNetworkPlayers={[0]={currLevelNum=6,currAreaIndex=1}}')
 h.mod=h.lua.execute((base.MOD/'skate_probes.lua').read_text());h.world=h.mod.new(h.lua.globals().g)
 return h

def scan(origin,target,moving=0,sabotage=None,defer=False):
 h=harness();p=h.pt(origin);q=h.pt(target)
 p.y=base.model.floor_id(p.x,p.y+24,p.z)[0];q.y=base.model.floor_id(q.x,q.y+24,q.z)[0]
 start=[p.x,p.y,p.z];player=[q.x,q.y,q.z]
 ctx=h.lua.table_from(dict(frame=0,epoch=0,speed=moving,forwardX=q.x-p.x,forwardZ=q.z-p.z));peak=0;r=None;reached=False;initial_key=None
 for frame in range(1,121):
  ctx.frame=frame
  if moving:
   p.z=origin[2]+moving*(frame-1);p.y=base.model.floor_id(p.x,p.y+24,p.z)[0]
   q.z=target[2]+moving*(frame-1);q.y=base.model.floor_id(q.x,q.y+24,q.z)[0]
  s=h.world._railScan
  if sabotage and s is not None and s.phase==4:
   reached=True
   if sabotage=='water':h.lua.execute('g.find_water_level=function()return 1000 end')
   else:q.x,q.y,q.z=s.points[1].x,s.points[1].y,s.points[1].z
  r,d=h.run('railScan',p,q,ctx);peak=max(peak,d['budget']['calls'])
  if reached:break
  if r is not None and r.indexKey is None:
   # The bounded near-actor prefix is tested separately; continue to index work.
   r=None
  if r is not None:
   if defer and initial_key is None:
    initial_key=r.indexKey;h.world.deferRail(h.world,r,frame);r=None
   else:break
 return h,r,dict(found=r is not None,indexed=r is not None and r.indexKey is not None,frames=frame,peak_calls=peak,start=start,player=player,sabotage_reached=reached,first_key=initial_key,selected_key=r.indexKey if r else None)

def main():
 checks={};results={}
 for name,origin,target in CASES:
  h,r,d=scan(origin,target);results[name]=d;checks[name]=d['found'] and d['indexed'];checks[name+'_budget']=d['peak_calls']<3000
 for speed in (2,4,8):
  h,r,d=scan(CASES[0][1],CASES[0][2],moving=speed);results['moving'+str(speed)]=d;checks['moving'+str(speed)]=d['found'] and d['indexed']
 # Large player relocation remains a scan-lifecycle interruption, not spacing.
 for sabotage in ('water','player'):
  h,r,d=scan(CASES[0][1],CASES[0][2],sabotage=sabotage);results[sabotage]=d;checks[('player_relocation' if sabotage=='player' else sabotage)+'_freshly_refused']=d['sabotage_reached'] and not d['found']
 h,r,d=scan(CASES[0][1],CASES[0][2]);fresh,diag=h.run('validateRail',r,r.a);checks['indexed_overlap_fresh_proof_allowed']=fresh is not None
 bad=h.pt((float('nan'),r.a.y,r.a.z));fresh,diag=h.run('validateRail',r,bad);checks['indexed_invalid_player_refused']=fresh is None
 h,r,d=scan(CASES[0][1],CASES[0][2],defer=True);results['deferred']=d;checks['deferred_yields_alternative']=d['found'] and d['first_key']!=d['selected_key']
 h=harness();p=h.pt(CASES[0][1]);q=h.pt(CASES[0][2]);h.lua.execute('g.gNetworkPlayers[0].currLevelNum=16')
 checks['other_level_no_index']=len(h.lua.eval('function(w,p,q)return w:transaction(function()return w:_indexedHints(p,q,0,1,1)end)end')(h.world,p,q))==0
 h.lua.execute('g.gNetworkPlayers[0].currLevelNum=6;g.gNetworkPlayers[0].currAreaIndex=2')
 checks['other_area_no_index']=len(h.lua.eval('function(w,p,q)return w:transaction(function()return w:_indexedHints(p,q,0,1,1)end)end')(h.world,p,q))==0
 # A forced budget failure defers its indexed seed before discarding scan state.
 h=harness();p=h.pt(CASES[0][1]);q=h.pt(CASES[0][2]);ctx=h.lua.table_from(dict(frame=1,epoch=0,speed=0,forwardX=q.x-p.x,forwardZ=q.z-p.z))
 # Isolate indexed-budget failure after the bounded near prefix had its turn.
 h.world._nearScanNext=90
 # Start the failing clock AFTER hint collection, so this case still targets
 # an owned indexed seed rather than the now-budgeted hint loop itself.
 h.lua.eval('function(w,g)w.savedHints=w._indexedHints;w._indexedHints=function(self,...)local hints=self.savedHints(self,...);local n=0;g.clock_elapsed_f64=function()n=n+.001;return n end;return hints end end')(h.world,h.lua.globals().g)
 h.run('railScan',p,q,ctx);deferred=list(h.world._railDeferred.keys()) if h.world._railDeferred else []
 checks['budget_failure_defers_seed']=h.world.lastBudget.reason=='native-time-budget' and bool(deferred) and h.world._railScan is None
 h.lua.execute('g.clock_elapsed_f64=function()return 0 end')
 h.world._indexedHints=h.world.savedHints
 nextkeys=[v.key for v in h.lua.eval('function(w,p,q)return w:transaction(function()return w:_indexedHints(p,q,0,1,2)end)end')(h.world,p,q).values()]
 checks['budget_failure_yields_next_seed']=all(k not in nextkeys for k in deferred)
 expirykeys=[v.key for v in h.lua.eval('function(w,p,q)return w:transaction(function()return w:_indexedHints(p,q,0,1,400)end)end')(h.world,p,q).values()]
 checks['deferral_is_temporary']=any(k in expirykeys for k in deferred)
 # Failed indexed exits must eventually allow generic fallback, not reset rank1 forever.
 h=harness();p=h.pt(CASES[0][1]);q=h.pt(CASES[0][2]);ctx=h.lua.table_from(dict(frame=1,epoch=0,speed=0,forwardX=q.x-p.x,forwardZ=q.z-p.z))
 h.lua.eval('function(w)local old=w.support;w.support=function(self,p,r)if r==64 then return nil end;return old(self,p,r)end end')(h.world)
 fallback=False
 for frame in range(1,421):
  ctx.frame=frame;h.run('railScan',p,q,ctx);scan0=h.world._railScan
  if scan0 is not None and scan0.index>len(scan0.hints)+(scan0.nearCount or 0):fallback=True;break
 checks['failed_exits_allow_generic_fallback']=fallback
 results['failed_exit_fallback_frame']=frame
 # Default upper discovery must offer the affordable local seed before the index.
 h=harness();p=h.pt(CASES[0][1]);q=h.pt(CASES[0][2]);ctx=h.lua.table_from(dict(frame=1,epoch=0,speed=0,forwardX=190,forwardZ=-210));near=None
 for frame in range(1,31):
  ctx.frame=frame;near,_=h.run('railScan',p,q,ctx)
  if near is not None:break
 checks['upper_near_seed_precedes_index']=near is not None and near.indexKey is None and frame<=16
 checks['upper_near_seed_short_fresh_rail']=near is not None and len(near.points)==7 and abs(near.a.z+385.79616044948)<.01
 if near is not None:
  h.lua.execute('g.find_water_level=function()return 1000 end');refused,_=h.run('validateRail',near,q)
  checks['upper_near_seed_reproves_water']=refused is None
 else:checks['upper_near_seed_reproves_water']=False
 results['near_seed_frame']=frame
 # A slow unfinished near-prefix cannot consume a fresh prefix after expiry.
 h=harness();p=h.pt(CASES[0][1]);q=h.pt(CASES[0][2]);ctx=h.lua.table_from(dict(frame=1,epoch=0,speed=0,forwardX=190,forwardZ=-210));h.run('railScan',p,q,ctx)
 old=h.world._railScan;old.nearGeneric=True;old.started=-121;old.frame=1;h.world._nearScanNext=0;ctx.frame=2
 h.run('railScan',p,q,ctx)
 checks['expired_near_prefix_yields_index']=h.world._nearScanNext>=92 and h.world._railScan is not None and h.world._railScan.nearCount==0
 report=dict(passed=all(checks.values()),checks=checks,results=results,source_sha256={n:hashlib.sha256((base.MOD/n).read_bytes()).hexdigest() for n in ('skate_probes.lua','skate_opportunities.lua','skate_rail_index.lua')},limits='Offline actual Castle floor triangles with approximate wall adapter. Actor and player initial heights are measured from real support. Moving samples are query trajectories, not simulated native locomotion or played acceptance. No seeded grind plan.')
 out=ROOT/'build/natural-rails';out.mkdir(parents=True,exist_ok=True);(out/'indexed-discovery.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
