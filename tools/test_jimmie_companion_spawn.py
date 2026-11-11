from pathlib import Path
import json,hashlib
from lupa import LuaRuntime
ROOT=Path(__file__).resolve().parents[1];MOD=ROOT/'mods/jimmie'
def harness(extra=''):
 l=LuaRuntime(unpack_returned_tuples=True)
 l.execute('''
 g={SURFACE_POOL_STATIC=0,SURFACE_FLAG_DYNAMIC=1,SURFACE_FLAG_INTANGIBLE=4,SURFACE_BURNING=1,
 ACT_GROUP_MASK=0x1c0,ACT_GROUP_CUTSCENE=0x100,PLAY_MODE_NORMAL=0}
 frame=0;terrain={};area={};floor={normal={x=0,y=1,z=0},type=0,flags=0,poolType=0}
 m={area=area,marioObj={},pos={x=0,y=0,z=0},vel={x=0,y=0,z=0},floorHeight=0,action=1,faceAngle={y=0}}
 g.gNetworkPlayers={[0]={currLevelNum=6,currAreaIndex=1,currActNum=1}}
 g.smlua_collision_util_get_current_terrain_collision=function()return terrain end
 g.get_global_timer=function()return frame end
 g.clock_elapsed_f64=function()return 0 end
 g.get_current_play_mode=function()return 0 end
 g.is_game_paused=function()return false end
 g.find_floor=function()return 0,floor end
 g.find_ceil=function()return 20000,nil end
 g.find_water_level=function()return -11000 end
 g.find_poison_gas_level=function()return -11000 end
 g.resolve_and_return_wall_collisions=function()return nil end
 ''')
 mod=l.execute((MOD/'companion_spawn.lua').read_text());s=mod.new(l.globals().g)
 s.observe(s,l.globals().m);l.execute('frame=3;'+extra)
 return l,s
checks={}
def choose(l,s):return s.select(s,l.globals().m)
l,s=harness();q,r=choose(l,s);checks['open_floor_spawn']=q is not None and q.y==0 and q.x==160
for name,setup in [('wall','g.resolve_and_return_wall_collisions=function()return {} end'),
 ('wall_mutation','g.resolve_and_return_wall_collisions=function(p)p.x=p.x+1 end'),
 ('ceiling','g.find_ceil=function()return 150 end'),('void','g.find_floor=function()return -11000,nil end'),
 ('water','g.find_water_level=function()return 0 end'),('gas','g.find_poison_gas_level=function()return 0 end'),
 ('hazard','floor.type=1'),('dynamic','floor.poolType=1'),('cutscene','m.action=0x100'),('airborne','m.pos.y=150'),
 ('paused','g.is_game_paused=function()return true end'),('mode','g.get_current_play_mode=function()return 2 end'),
 ('missing_api','g.find_ceil=nil'),('budget','g.clock_elapsed_f64=function()return frame*.01 end; g.find_floor=function()frame=frame+1;return 0,floor end'),
 ('boundary','m.pos.x=7900')]:
 l,s=harness(setup);q,r=choose(l,s);checks[name+'_refused']=q is None
l,s=harness('g.resolve_and_return_wall_collisions=function(p)if p.x>50 then return {} end end')
q,r=choose(l,s);checks['blocked_side_chooses_other']=q is not None and q.x<0
l,s=harness('g.resolve_and_return_wall_collisions=function(p)if p.x>50 and p.x<110 then return {} end end')
q,r=choose(l,s);checks['wall_between_clear_destination_refused']=q is not None and q.x<0
l,s=harness('frame=1');q,r=choose(l,s);checks['scene_settles']=q is None
l,s=harness();l.execute('g.gNetworkPlayers[0].currAreaIndex=2');q,r=choose(l,s);checks['same_level_area_restarts']=q is None
l,s=harness();s.invalidate(s);q,r=choose(l,s);checks['same_terrain_reload_restarts']=q is None
l,s=harness('g.find_ceil=function()terrain={};return 20000 end');q,r=choose(l,s);checks['mid_query_scene_change_refused']=q is None
l,s=harness('g.resolve_and_return_wall_collisions=function()return {} end');choose(l,s);l.execute('g.resolve_and_return_wall_collisions=function()return nil end');q,r=choose(l,s);checks['retry_bounded']=q is None
l.execute('frame=9');q,r=choose(l,s);checks['clear_retry_recovers']=q is not None
main=(MOD/'main.lua').read_text();checks['old_fixed_offset_removed']='m.pos.x - 60, m.pos.y + 40, m.pos.z' not in main
checks['sync_no_direct_spawn']='spawn_jimmie()' not in main.split('local function on_sync_valid()',1)[1].split('local function on_death',1)[0]
checks['main_parses']=l.eval('function(s)return load(s)~=nil end')(main)
report={'passed':all(checks.values()),'checks':checks,'source_sha256':hashlib.sha256((MOD/'companion_spawn.lua').read_bytes()).hexdigest(),'limits':'Lua synthetic geometry fixtures only; native collision runs are separate.'}
out=ROOT/'build/wall-respawn';out.mkdir(parents=True,exist_ok=True);(out/'unit-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(0 if report['passed'] else 1)
