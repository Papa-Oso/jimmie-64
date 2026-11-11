"""Private real-map shape discovery tests, not native or rendered acceptance."""
from pathlib import Path
import sys,re,struct,subprocess,math,json,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_jimmie_natural_rails as base
ROOT=Path(__file__).resolve().parents[1];MOD=ROOT/'mods/jimmie'
MODEL=base.model

def load_bob():
 text=(ROOT/'levels/bob/areas/1/collision.inc.c').read_text()
 nums=re.search(r'ROM_ASSET_LOAD_COLLISION\([^,]+,\s*(0x[0-9a-fA-F]+),\s*[^,]+,\s*(0x[0-9a-fA-F]+),\s*(\d+)\)',text)
 assert nums,text
 rom,off,size=int(nums[1],16),int(nums[2],16),int(nums[3])
 raw=subprocess.check_output([str(MODEL.geo.NATIVE/'tools/mio0.exe'),'-d','-o',hex(rom),str(MODEL.geo.ROM),'-'])
 data=raw[off:off+size];words=struct.unpack('>'+str(len(data)//2)+'h',data);assert words[0]==0x40
 count=words[1];vertices=[words[i:i+3] for i in range(2,2+count*3,3)];i=2+count*3;triangles=[]
 while words[i]!=0x41:
  kind,count=words[i:i+2];i+=2;stride=4 if kind in (4,14,36,37,39,44,45) else 3
  for _ in range(count):
   vs=[vertices[j] for j in words[i:i+3]];a,b,c=vs
   ab=[b[k]-a[k] for k in range(3)];ac=[c[k]-a[k] for k in range(3)]
   n=[ab[1]*ac[2]-ab[2]*ac[1],ab[2]*ac[0]-ab[0]*ac[2],ab[0]*ac[1]-ab[1]*ac[0]];length=math.sqrt(sum(x*x for x in n));assert length
   n=[x/length for x in n];triangles.append(dict(index=len(triangles),type=kind,vertices=vs,normal=n,origin=-sum(n[k]*a[k] for k in range(3))));i+=stride
 return triangles,hashlib.sha256(data).hexdigest()

def install_geometry(tris):
 MODEL.TRIS=tris;MODEL.FLOORS=[t for t in tris if t['normal'][1]>.01];MODEL.CEILS=[t for t in tris if t['normal'][1]<-.01];MODEL.WALLS=[t for t in tris if abs(t['normal'][1])<=.01]
 MODEL.BOUNDS={t['index']:tuple((min(v[k] for v in t['vertices']),max(v[k] for v in t['vertices'])) for k in range(3)) for t in tris}
 MODEL.floor_id.cache_clear();MODEL.ceil_id.cache_clear()

def harness(level=6):
 h=MODEL.Harness(MOD)
 h.lua.execute('g.LEVEL_CASTLE=6;g.LEVEL_BOB=9;g.gNetworkPlayers={[0]={currLevelNum='+str(level)+',currAreaIndex=1}}')
 for name in ('skate_visible_rails','skate_surface_rails','skate_rail_presentation'):
  h.lua.globals().package.loaded[name]=h.lua.execute((MOD/(name+'.lua')).read_text())
 h.mod=h.lua.execute((MOD/'skate_probes.lua').read_text());h.world=h.mod.new(h.lua.globals().g)
 for surf in h.surfaces.values():h.world.surfaceRails.add(h.world.surfaceRails,surf,False,'fixture')
 return h

def find(h,xyz,target,dx=1,dz=0):
 p=h.pt(xyz);q=h.pt(target);ctx=h.lua.table_from(dict(frame=1,epoch=0,speed=28,forwardX=dx,forwardZ=dz))
 for frame in range(1,181):
  ctx.frame=frame;r,d=h.run('railScan',p,q,ctx)
  if r:return r,dict(frames=frame,calls=d['budget']['calls'],source=r.shapeSource,visual_top=r.visual.a.y if r.visual else None)
 return None,dict(frames=frame,reason=h.world.lastReject)

def admission(h,rail,xyz,target,block=False):
 p=h.pt(xyz);p.onGround=True;player=h.pt(target);player.vx=0;player.vz=0
 c=h.opp.new(h.world,h.lua.eval('function()return .5 end'));c.nextProbe=2
 ctx=h.lua.table_from(dict(frame=30,time=1,enabled=True,scene='fixture',area=h.lua.table(),terrain=h.lua.table(),instance=h.lua.table(),phys=p,player=player,players=h.lua.table_from([player]),playerInstance=h.lua.table(),playerGrounded=True))
 c.pendingRail=h.lua.table_from(dict(rail=rail,time=1,scene='fixture',area=ctx.area))
 if block:h.lua.eval('function(w)w._raisedClear=function(self)return self:deny("test-fresh-presentation-block")end end')(h.world)
 out=h.lua.eval('function(w,c,p,ctx)return w:transaction(function()return c:step(p,ctx)end)end')(h.world,c,p,ctx)
 return dict(accepted=out is not None,committed=c.episode>0,calls=h.world.lastBudget.calls,budget_reason=h.world.lastBudget.reason,reason=h.world.lastReject)

def journey(h,rail,xyz,target):
 p=h.pt(xyz);p.onGround=True;p.yaw=math.atan2(rail.b.x-rail.a.x,rail.b.z-rail.a.z)
 player=h.pt(target);player.vx=0;player.vz=0
 plan,_=h.run('arc',p,rail.a,90,h.lua.table_from(dict(landingRadius=0)))
 c=h.opp.new(h.world,h.lua.eval('function()return .5 end'))
 ctx=h.lua.table_from(dict(frame=1,time=1/30,scene='fixture',area=h.lua.table(),terrain=h.lua.table(),instance=h.lua.table(),phys=p,player=player,players=h.lua.table_from([player])))
 call=h.lua.eval('function(w,c,p,ctx,plan,rail,first)return w:transaction(function()if first then return c:begin(plan,"rail",p,ctx,rail)else return c:advance(p,ctx)end end)end')
 events=[];certs=0;peak=0
 for frame in range(1,151):
  ctx.frame=frame;ctx.time=frame/30
  out=call(h.world,c,p,ctx,plan,rail,frame==1)
  peak=max(peak,h.world.lastBudget.calls)
  for e in c.drain(c).values():events.append(dict(kind=e.kind,frame=e.frame,reason=e.reason))
  if out:
   for k in ('x','y','z'):p[k]=out.position[k]
   p.vx,p.vy,p.vz=out.velocity.x,out.velocity.y,out.velocity.z;p.onGround=out.onGround
   if abs(p.vx)+abs(p.vz)>.01:p.yaw=math.atan2(p.vx,p.vz)
   if out.raisedPresentation:certs+=1
  if c.task is None or out is None:break
 return dict(passed=any(e['kind']=='landing-observed' for e in events),frames=frame,certified_grind_ticks=certs,peak_calls=peak,reason=h.world.lastReject,events=events)

def main():
 checks={};results={};install_geometry(MODEL.geo.TRIANGLES)
 h=harness();checks['castle_numeric_caps_found']=len(h.world.surfaceRails.segments)>0
 r,d=find(h,(-2400,512,-1160),(-2000,512,-1160));results['castle']=d
 checks['pictured_banister_discovered']=r is not None and r.shapeSource=='static-surface-edge' and r.visual is not None and r.visual.a.y==614
 checks['raised_above_balcony_floor']=r is not None and 90<r.a.y-512<110
 if r:
  p=h.pt((-2400,512,-1160));q=h.pt((-2000,512,-1160));q.vx=28;q.vz=0
  plan,d=h.run('arc',p,r.a,90,h.lua.table_from(dict(landingRadius=0)));checks['castle_actual_entry_clear']=plan is not None
  controller=h.opp.new(h.world,h.lua.eval('function()return .5 end'));ctx=h.lua.table_from(dict(player=q))
  eligible=controller.railKeepsUp(controller,p,r,ctx,plan) if plan else False
  checks['castle_actual_momentum_viable']=eligible is True
  cert,diag=h.run('raisedPresentation',r.a,r.a,r,h.lua.table_from(dict(frame=1,player=q)));results['castle_presentation']=dict(accepted=cert is not None,reason=h.world.lastReject,diagnostic=diag);checks['castle_shifted_clearance']=cert is not None
  results['castle_admission']=admission(h,r,(-2400,512,-1160),(-2000,512,-1160));checks['castle_full_fresh_admission_budget']=results['castle_admission']['accepted'] and results['castle_admission']['calls']<3000
  results['castle_journey']=journey(h,r,(-2400,512,-1160),(-2000,512,-1160));checks['castle_complete_controller_journey']=results['castle_journey']['passed']
  h.lua.execute('g.find_water_level=function()return 1000 end');fresh,d=h.run('validateRail',r,q);checks['new_water_still_refuses']=fresh is None

 h=harness();rail,_=find(h,(-2400,512,-1160),(-2000,512,-1160));denied=admission(h,rail,(-2400,512,-1160),(-2000,512,-1160),block=True)
 checks['fresh_shifted_block_prevents_entry_commit']=not denied['accepted'] and not denied['committed'] and denied['reason']=='test-fresh-presentation-block'
 # Each presentation refusal uses a new transaction and an unchanged actual
 # discovered cap. No previous successful certificate can authorize a later tick.
 for name,mutation in (
  ('ceiling',"g.find_ceil=function(x,y,z)return y+100,nil end"),
  ('wall',"g.resolve_and_return_wall_collisions=function(p,h,r)return {} end"),
  ('water',"g.find_water_level=function()return 1000 end"),
  ('unrelated_low_floor',"local old=g.find_floor;g.find_floor=function(x,y,z)if y>900 then return 620,{type=0,poolType=0,flags=0,normal={x=0,y=1,z=0},vertex1={x=x-5,y=620,z=z-5},vertex2={x=x+5,y=620,z=z-5},vertex3={x=x,y=620,z=z+5}} end;return old(x,y,z)end"),
  ('dynamic_support',"local old=g.find_floor;g.find_floor=function(x,y,z)local a,b=old(x,y,z);if b then b.poolType=1 end;return a,b end")):
  h=harness();rail,_=find(h,(-2400,512,-1160),(-2000,512,-1160));h.lua.execute(mutation)
  cert,diag=h.run('raisedPresentation',rail.a,rail.a,rail,h.lua.table_from(dict(frame=2,player=h.pt((-2000,512,-1160)))))
  checks['fresh_presentation_'+name+'_refused']=cert is None
 h=harness();rail,_=find(h,(-2400,512,-1160),(-2000,512,-1160))
 cert,diag=h.run('raisedPresentation',rail.a,rail.a,rail,h.lua.table_from(dict(frame=2,player=rail.a)));checks['shifted_player_overlap_allowed']=cert is not None
 for name,bad in [('nan',h.pt((float('nan'),rail.a.y,rail.a.z))),('infinity',h.pt((rail.a.x,float('inf'),rail.a.z))),('missing',h.lua.table_from(dict(x=rail.a.x,y=rail.a.y)))]:
  cert,diag=h.run('raisedPresentation',rail.a,rail.a,rail,h.lua.table_from(dict(frame=2,player=bad)));checks['shifted_invalid_player_'+name+'_refused']=cert is None
  hints=h.world.surfaceRails.near(h.world.surfaceRails,rail.a,bad,1,0,2,None);checks['discovery_invalid_player_'+name+'_refused']=len(hints)==0
 # Removing only the late probe veto is insufficient: near() must also offer
 # geometry-derived hints that occupy the player's former 140-unit bubble.
 hints=h.world.surfaceRails.near(h.world.surfaceRails,h.pt((-2400,512,-1160)),rail.a,1,0,2,None)
 checks['surface_discovery_player_overlap_allowed']=any(math.hypot(v.x-rail.a.x,v.z-rail.a.z)<140 for v in hints.values())
 rail.visual.a.y=rail.visual.a.y+1
 cert,diag=h.run('raisedPresentation',rail.a,rail.a,rail,h.lua.table_from(dict(frame=2,player=h.pt((-2000,512,-1160)))));checks['changed_visual_descriptor_refused']=cert is None
 h=harness();rail,_=find(h,(-2400,512,-1160),(-2000,512,-1160));h.world.surfaceRails.bound=True
 h.lua.execute('g.smlua_collision_util_get_current_terrain_collision=function()return "new-scene" end')
 cert,diag=h.run('raisedPresentation',rail.a,rail.a,rail,h.lua.table_from(dict(frame=2,player=h.pt((-2000,512,-1160)))));checks['new_scene_cannot_reuse_visual_line']=cert is None

 h=harness();h.world.surfaceRails.bound=True
 h.lua.execute('sceneReads=0;g.smlua_collision_util_get_current_terrain_collision=function()sceneReads=sceneReads+1;return "fixture" end')
 sample=h.lua.eval('function(w,p,q)return w:transaction(function()local before=w._budget.queries;local h=w:_indexedHints(p,q,1,0,1);return {delta=w._budget.queries-before,count=#h}end)end')(h.world,h.pt((-2400,512,-1160)),h.pt((-2000,512,-1160)))
 checks['native_scene_reads_in_shared_query_budget']=sample is not None and sample.delta==h.lua.globals().sceneReads and sample.delta>0
 checks['surface_hint_queue_bounded']=sample is not None and sample.count<=24
 h.lua.execute('local n=0;g.clock_elapsed_f64=function()n=n+.001;return n end')
 result=h.lua.eval('function(w,p,q)return w:transaction(function()return w:_indexedHints(p,q,1,0,2)end)end')(h.world,h.pt((-2400,512,-1160)),h.pt((-2000,512,-1160)))
 checks['surface_discovery_cooperatively_interrupts']=result is None and h.world.lastBudget.reason=='native-time-budget'
 h=harness();capture=h.world.surfaceRails
 before=len(capture.segments);capture.add(capture,h.surfaces[1999],True,'fixture');checks['dynamic_does_not_add']=len(capture.segments)==before
 snapshot=[(v.a.x,v.a.y,v.a.z,v.b.x,v.b.y,v.b.z) for v in capture.segments.values()]
 h.surfaces[1999].vertex1.x=123;checks['numeric_capture_not_userdata_reference']=snapshot==[(v.a.x,v.a.y,v.a.z,v.b.x,v.b.y,v.b.z) for v in capture.segments.values()]
 capture.clear(capture,'new-area');checks['area_clear_removes_candidates']=len(capture.segments)==0
 h=harness();h.lua.execute('g.gNetworkPlayers[0].currLevelNum=16');hints=h.world.surfaceRails.near(h.world.surfaceRails,h.pt((-2400,512,-1160)),h.pt((-2000,512,-1160)),1,0,1,None);checks['unknown_visible_map_not_assumed']=len(hints)==0
 bob,hash0=load_bob();install_geometry(bob);h=harness(9);results['bob_triangles']=len(bob);results['bob_collision_sha256']=hash0
 dx,dz=-.843723256,-.536778416;p=(-72.057727,768,2861.002140);q=(p[0]+540*dx,768,p[2]+540*dz)
 r,d=find(h,p,q,dx,dz);results['bob']=d
 checks['bob_fence_shape_discovered']=r is not None and r.shapeSource=='static-surface-edge' and r.visual is not None and r.visual.a.y==891
 if r:
  plan,d=h.run('arc',h.pt(p),r.a,90,h.lua.table_from(dict(landingRadius=0)));checks['bob_actual_entry_clear']=plan is not None
  player=h.pt(q);player.vx=28*dx;player.vz=28*dz;c=h.opp.new(h.world,h.lua.eval('function()return .5 end'));ctx=h.lua.table_from(dict(player=player))
  checks['bob_actual_momentum_viable']=c.railKeepsUp(c,h.pt(p),r,ctx,plan) is True if plan else False
  cert,diag=h.run('raisedPresentation',r.a,r.a,r,h.lua.table_from(dict(frame=1,player=player)));results['bob_presentation']=dict(accepted=cert is not None,reason=h.world.lastReject,diagnostic=diag);checks['bob_shifted_clearance']=cert is not None
  results['bob_admission']=admission(h,r,p,q);checks['bob_full_fresh_admission_budget']=results['bob_admission']['accepted'] and results['bob_admission']['calls']<3000
  results['bob_journey']=journey(h,r,p,q);checks['bob_complete_controller_journey']=results['bob_journey']['passed']
 else:checks['bob_actual_entry_clear']=False;checks['bob_actual_momentum_viable']=False
 report=dict(passed=all(checks.values()),checks=checks,results=results,source_sha256={n:hashlib.sha256((MOD/n).read_bytes()).hexdigest() for n in ('skate_surface_rails.lua','skate_visible_rails.lua','skate_probes.lua','skate_opportunities.lua','skate_rail_presentation.lua')},limits='Actual private static collision with approximate offline wall adapter. Geometry-derived discovery and finite shifted-envelope sampling; not continuous collision, native locomotion, renderer or human-play acceptance.')
 out=ROOT/'build/raised-rails';out.mkdir(parents=True,exist_ok=True);(out/'surface-focused.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
