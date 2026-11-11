"""Offline binding/lifecycle/source-order checks. No game launch or writes outside stdout."""
from pathlib import Path
import hashlib
from lupa.lua53 import LuaRuntime
ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / 'mods/jimmie'
prototype = (ROOT/'tools/raised_rails/presentation_anchor.lua').read_bytes()
runtime = (MOD/'skate_rail_presentation.lua').read_bytes()
expected = '764cdfc2335dc0b6db7ffd6ee6a09f65e66d18f91a825de51e8078a71c86b953'
assert hashlib.sha256(prototype).hexdigest() == expected
assert hashlib.sha256(runtime).hexdigest() == expected
assert runtime == prototype
lua = LuaRuntime(unpack_returned_tuples=True)
lua.globals().MOD = str(MOD).replace('\\','/')
lua.execute(r'''
package.path=MOD..'/?.lua;'..package.path
local animations={}
smlua_anim_util_register_animation=function(name,flags) animations[name]={flags=flags,name=name} end
smlua_anim_util_set_animation=function(o,name) o.header.gfx.animInfo.curAnim=animations[name] end
local Bank=require('original_clip_bank')
local Motion=require('original_motion_controller')
local Anchor=require('skate_rail_presentation')
local Binding=require('skate_rail_binding')
local groups=0
local function group(name,fn) fn();groups=groups+1;print('PASS '..name) end
local function eq(a,b) assert(math.abs(a-b)<1e-6,tostring(a)..' != '..tostring(b)) end
local function object()
 return {activeFlags=1,oPosX=-720,oPosY=603.7559814453125,oPosZ=-429,
  oFaceAngleYaw=0,oFaceAnglePitch=0,oFaceAngleRoll=0,oGraphYOffset=0,
  header={gfx={angle={x=0,y=0,z=0},pos={x=-720,y=603.7559814453125,z=-429},
   scale={x=.6200000047683716,y=.6200000047683716,z=.6200000047683716},animInfo={}}}}
end
local function setup(reverse,brace)
 local c={body=object(),board=object(),scene=7,sceneKey='castle/1/7',frame=42,enabled=true,players={[0]={marioObj=object()}}}
 c.controller=Motion.new(Bank.new());c.controller.heading=reverse and 1 or 0
 -- First assignment resets the controller. Assign identity before setting parity.
 c.controller.body=c.body;c.controller.board=c.board;c.controller.scene=c.scene
 assert(c.controller:step({body=c.body,board=c.board,scene=c.scene,railContact=true,balanceClip='balance042',dt=1/30}))
 if brace then
  c.brace=object()
  for k,v in pairs(c.body.header.gfx.animInfo) do c.brace.header.gfx.animInfo[k]=v end
 end
 local cert={physical={x=c.body.oPosX,y=c.body.oPosY,z=c.body.oPosZ},visual={a={x=-818,y=614,z=-429},b={x=-622,y=614,z=-429}},
  heading=math.pi/2,incline=0,native={yaw=0,pitch=0,roll=0},certificateFrame=c.frame}
 local result=Anchor.compute({root=cert.physical,rail={a=cert.visual.a,b=cert.visual.b,verified=true},
  heading=cert.heading,incline=cert.incline,native=cert.native,
  clip=reverse and Bank.clips.balance042.boardReverse or Bank.clips.balance042.board,blend=1,safetyMargin=6.66})
 assert(result.ok);cert.certifiedDelta=result.fullDelta
 c.motion={grind=true,raisedPresentation=cert}
 local writes={}
 local b=Binding.new({anchor=Anchor,clips=Bank.clips,
  animationName=function(o) return o.header.gfx.animInfo.curAnim and o.header.gfx.animInfo.curAnim.name end,
  setGfxPos=function(o,x,y,z) writes[#writes+1]=o;o.header.gfx.pos={x=x,y=y,z=z} end})
 return b,c,writes
end
local function renderAll(b,c)
 for _,o in ipairs({c.body,c.board,c.brace}) do assert(b:render(o,c)) end
end
group('shared absolute offset and physical isolation',function()
 local b,c,w=setup(false,true);assert(b:publish(c));renderAll(b,c)
 for _,o in ipairs({c.body,c.board,c.brace}) do eq(o.header.gfx.pos.y,610.9);eq(o.header.gfx.pos.z,-425.9);eq(o.oPosY,603.7559814453125) end
 assert(#w==3 and c.players[0].marioObj.header.gfx.pos.y==603.7559814453125)
end)
group('forward and reverse exact bank names',function()
 for _,r in ipairs({false,true}) do local b,c=setup(r);assert(b:publish(c));renderAll(b,c)
  assert(c.board.header.gfx.animInfo.curAnim.name==(r and Bank.clips.balance042.boardReverse or Bank.clips.balance042.board)) end
end)
group('certificate invalid stale delta and native fields',function()
 local mutations={function(c)c.motion.raisedPresentation=nil end,function(c)c.motion.raisedPresentation.certificateFrame=41 end,
 function(c)c.motion.raisedPresentation.certifiedDelta.y=0 end,function(c)c.motion.raisedPresentation.native.yaw=1 end,
 function(c)c.motion.raisedPresentation.physical.y=c.motion.raisedPresentation.physical.y+1e-7 end,
 function(c)c.motion.raisedPresentation.visual.b.x=0/0 end}
 for _,mutate in ipairs(mutations) do local b,c=setup();mutate(c);assert(not b:publish(c)) end
end)
group('same frame only and scene identity invalidation',function()
 for _,mutate in ipairs({function(c)c.frame=43 end,function(c)c.scene=8 end,function(c)c.sceneKey='bob' end,
 function(c)c.body=object() end,function(c)c.controller=Motion.new(Bank.new()) end}) do
  local b,c=setup();assert(b:publish(c));mutate(c);assert(not b:render(c.board,c));assert(not b:status().active)
 end
end)
group('physical angles scale and graph offset mismatch',function()
 for _,mutate in ipairs({function(c)c.board.oPosY=c.board.oPosY+1 end,function(c)c.body.oFaceAngleRoll=1 end,
 function(c)c.board.header.gfx.scale.x=.63 end,function(c)c.body.oGraphYOffset=1 end,
 function(c)c.board.header.gfx.throwMatrix={} end,function(c)c.board.activeFlags=0 end}) do
  local b,c=setup();assert(b:publish(c));mutate(c);assert(not b:render(c.body,c))
 end
end)
group('clip pointer parity and animation frame checks',function()
 for _,mutate in ipairs({function(c)c.controller.output.clip='idle' end,function(c)c.controller.output.heading=1 end,
 function(c)c.board.header.gfx.animInfo.curAnim=animations[Bank.clips.idle.board] end,
 function(c)c.board.header.gfx.animInfo.animFrame=1 end,function(c)c.body.header.gfx.animInfo.animAccel=0 end,
 function(c)c.body.header.gfx.animInfo.animFrameAccelAssist=1 end}) do
  local b,c=setup();assert(b:publish(c));mutate(c);assert(not b:render(c.body,c))
 end
end)
group('native renderer bookkeeping preserves pinned pose',function()
 local b,c=setup(false,true);assert(b:publish(c))
 for _,o in ipairs({c.body,c.board,c.brace}) do assert(b:render(o,c))
  local a=o.header.gfx.animInfo;a.animTimer=900;a.prevAnimPtr=a.curAnim;a.prevAnimFrame=a.animFrame;a.prevAnimFrameTimestamp=c.frame
 end
 renderAll(b,c)
end)
group('crash external owner disable dying and rejoin',function()
 for _,mutate in ipairs({function(c)c.externalOwner=true end,function(c)c.dying=true end,
 function(c)c.enabled=false end,function(c)c.controller.external=true end}) do
  local b,c,w=setup();assert(b:publish(c));mutate(c);assert(not b:render(c.body,c));assert(#w==0)
 end
 local b,c,w=setup();assert(b:publish(c));renderAll(b,c);c.externalOwner=true
 c.body.header.gfx.pos.y=99;local n=#w;assert(not b:render(c.body,c));assert(#w==n and c.body.header.gfx.pos.y==99)
end)
group('pause resets without preserving old permission; resume recertifies',function()
 local b,c=setup(false,true);assert(b:publish(c));renderAll(b,c);c.paused=true
 for _,o in ipairs({c.body,c.board,c.brace}) do assert(not b:render(o,c));eq(o.header.gfx.pos.y,o.oPosY) end
 c.paused=false;c.frame=43;assert(not b:publish(c));c.motion.raisedPresentation.certificateFrame=43
 assert(b:publish(c));renderAll(b,c)
end)
group('brace spawned removed or replaced invalidates trio',function()
 for _,mutate in ipairs({function(c)c.brace=nil end,function(c)c.brace=object() end}) do
  local b,c=setup(false,true);assert(b:publish(c));mutate(c);assert(not b:render(c.body,c)) end
 local b,c=setup();assert(b:publish(c));c.brace=object();assert(not b:render(c.body,c))
end)
group('100 repeated render cycles never accumulate; status is copy',function()
 local b,c=setup(false,true);assert(b:publish(c))
 for i=1,100 do renderAll(b,c) end
 eq(c.body.header.gfx.pos.y,610.9);assert(b:status().rendered==300)
 local s=b:status();s.active=false;s.rendered=0;assert(b:status().rendered==300)
 local record=s.lastRenderByPart.body
 assert(record.source=='HOOK_ON_OBJECT_RENDER' and record.frame==42 and record.certificateFrame==42 and record.publicationId==1 and record.ownerRole=='body')
 eq(record.gfx.y,610.9);record.gfx.y=0;record.delta.y=0;record.native.yaw=99
 eq(b:status().lastRenderByPart.body.gfx.y,610.9);assert(b:status().lastRenderByPart.body.native.yaw==0)
 assert(b:publish(c));assert(b:status().lastRenderByPart.body.publicationId==1)
 assert(b:render(c.body,c));assert(b:status().lastRenderByPart.body.publicationId==2)
end)
group('ledge no certificate and non-grind exit preserve baseline',function()
 local b,c,w=setup();c.motion.raisedPresentation=nil;assert(not b:publish(c));assert(not b:render(c.body,c));assert(#w==0)
 b,c,w=setup();assert(b:publish(c));renderAll(b,c);c.motion.grind=false;assert(not b:render(c.body,c));eq(c.body.header.gfx.pos.y,c.body.oPosY)
end)
group('foreign Mario held ridden protected from writes',function()
 local b,c,w=setup();assert(b:publish(c));assert(not b:render(object(),c));assert(not b:render(c.players[0].marioObj,c));assert(#w==0)
 for _,field in ipairs({'marioObj','heldObj','riddenObj'}) do b,c,w=setup();c.players[0][field]=c.body;assert(not b:publish(c));assert(not b:render(c.body,c));assert(#w==0) end
end)
group('immutable certificate and graphics-angle mismatch fail closed',function()
 local b,c=setup();assert(b:publish(c));c.motion.raisedPresentation.visual.a.y=615;assert(not b:render(c.body,c))
 b,c=setup();assert(b:publish(c));c.board.header.gfx.angle.y=16;assert(not b:render(c.board,c))
 b,c=setup();assert(b:publish(c));c.motion.raisedPresentation.certificateFrame=41;assert(not b:render(c.body,c))
end)
group('update-time stale gfx is ignored; explicit lifecycle clear',function()
 local b,c=setup();c.body.header.gfx.angle.y=999;assert(b:publish(c));c.body.header.gfx.angle.y=0;renderAll(b,c)
 b:clear();assert(not b:render(c.body,c));eq(c.body.header.gfx.pos.y,c.body.oPosY)
end)
assert(groups==15)
''')
# Compile actual runtime main without executing game calls, including local-variable limits.
compile_lua = lua.eval('function(s) local f,e=load(s); assert(f,e); return true end')
assert compile_lua((MOD/'main.lua').read_text())
render = (ROOT/'src/game/rendering_graph_node.c').read_text()
start = render.index('static void geo_process_object(struct Object *node) {')
section = render[start:]
assert section.index('if (!node->header.gfx.inited)') < section.index('HOOK_ON_OBJECT_RENDER') < section.index('mtxf_rotate_zxy_and_translate(mtxf, node->header.gfx.pos') < section.index('geo_set_animation_globals(')
node = (ROOT/'src/engine/graph_node.c').read_text()
assert 'obj->animTimer == gAreaUpdateCounter || anim->flags & ANIM_FLAG_2' in node
main = (MOD/'main.lua').read_text()
assert 'update_original_brace()\n    railPresentation:publish(rail_presentation_context())' in main
assert 'local function on_update()\n    railPresentation:clear()' in main
context = main.split('local function rail_presentation_context()')[1].split('local function render_rail_presentation')[0]
assert 'Personality.gameplay(m)' not in context
print('PASS runtime helper hash, main Lua5.3 compile, native hook ordering and frozen-frame source gates')
print('15 offline binding groups passed; NOT a native/rendered acceptance result')
