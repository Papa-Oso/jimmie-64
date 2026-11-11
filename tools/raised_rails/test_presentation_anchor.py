"""Offline Lua + exact-source evidence checks. No game, native launch, or runtime edits.
Run with an existing Python containing lupa; emits results to stdout only.
"""
from pathlib import Path
import hashlib
import math
import re
import struct
from lupa.lua53 import LuaRuntime

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
EXPECTED = {
    'mods/jimmie/actors/jimmie_orig_board/model.inc.c': '9e104ed61001620ebaa6701f5e120b5f0a4e41034061928d77f13d9bc7f914a6',
    'mods/jimmie/original_clip_bank.lua': '168bca45f901d539b99e44cfb105cd600b4644966e635438c7784a007727a684',
    'src/engine/math_util.c': '674634d8ac43fd7bdf2f5332c919aa16b43df7c7fc1d1a6d10787fd4d387df86',
    'include/trig_tables.inc.c': 'e1e73e0df08c58796d1decb040850b9f5c9997fe78e4f2976a43ace07d51db3b',
}
sources = {}
for relative, expected in EXPECTED.items():
    data = (ROOT / relative).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert digest == expected, (relative, 'source changed; reverify anchors/angles', digest)
    sources[relative] = data.decode('utf-8')
    print('SOURCE', relative, digest)
mesh = sources['mods/jimmie/actors/jimmie_orig_board/model.inc.c']
for suffix, x in [('007', -57), ('015', 57)]:
    name = 'jimmie_orig_board_board_shade_vtx_' + suffix
    block = re.search(r'static const Vtx ' + name + r'\[\] = \{(.*?)\n\};', mesh, re.S).group(1)
    vertices = [tuple(map(int, v)) for v in re.findall(r'\{ \{\s*(-?\d+),\s*(-?\d+),\s*(-?\d+)\s*\}', block)]
    assert vertices[2] == (x, -17, 17) and vertices[5] == (x, -17, -17)
    draw = re.search(r'gsSPVertex\(' + name + r', 32, 0\),(.*?)(?:gsSPVertex|gsSPEndDisplayList)', mesh, re.S).group(1)
    assert 'gsSP1Triangle(4, 5, 2, 0)' in draw
    assert 'gsSP1Triangle(5, 0, 2, 0)' in draw
    midpoint = tuple((a+b)/2 for a, b in zip(vertices[2], vertices[5]))
    assert midpoint == (x, -17, 0)
    # Anchor is the shared triangle EDGE MIDPOINT, not a literal mesh vertex.
    assert (x, -17, 0) not in vertices
    assert tuple(round((p+t)*.62, 6) for p,t in zip(midpoint, (0,22,-5))) == (round(x*.62, 6), 3.1, -3.1)
bank = sources['mods/jimmie/original_clip_bank.lua']
for name, expected in [
    ('jimmie_original_v1_board_balance042', [0,22,65531,0,0,0]),
    ('jimmie_stock_v1_board_reverse_balance042', [0,22,65531,32768,0,32768]),
]:
    record = re.search(r'register_animation\("'+name+r'",5,0,0,0,10,\{([^}]+)\},\{([^}]+)\}', bank)
    assert record and list(map(int, record[1].split(','))) == expected
    assert list(map(int, record[2].split(','))) == [1,0,1,1,1,2,1,3,1,4,1,5]
assert 'obj_scale(obj, 0.62)' in (ROOT/'mods/jimmie/main.lua').read_text()
assert 'obj.oGraphYOffset = 0' in (ROOT/'mods/jimmie/main.lua').read_text()
assert 'gSineTable[(u16) (sm64Angle) >> 4]' in sources['src/engine/math_util.c']
trig = sources['include/trig_tables.inc.c']
values = [float(x) for x in re.findall(r'(-?\d+\.\d+(?:e[-+]?\d+)?)f', trig, re.I)]
assert len(values) == 5120, len(values)
f32 = lambda x: struct.unpack('<f', struct.pack('<f', x))[0]
max_trig_error = max(abs(f32(x)-math.sin(i*2*math.pi/4096)) for i,x in enumerate(values))
assert max_trig_error < 1e-7, max_trig_error
print('PASS mesh edge midpoint, flat/reverse clip, scale and native trig evidence; max table error', max_trig_error)

lua = LuaRuntime(unpack_returned_tuples=True)
lua.globals().M = lua.execute((HERE/'presentation_anchor.lua').read_text())
count = lua.execute(r'''
local n = 0
local function group(name,f) f(); n=n+1; print('PASS '..name) end
local function near(a,b,e) assert(math.abs(a-b)<=(e or 1e-8), tostring(a)..' ~= '..tostring(b)) end
local function cp(t) if type(t)~='table' then return t end local q={} for k,v in pairs(t) do q[k]=cp(v) end return q end
local function same(a,b) for k,v in pairs(a)do if type(v)=='table' then same(v,b[k]) else assert(v==b[k],k)end end end
local function vec(x,y,z)return {x=x,y=y,z=z}end
local function args(a,b,root,reverse)
 local dx,dy,dz=b.x-a.x,b.y-a.y,b.z-a.z
 local h=math.atan(dx,dz);local r=math.atan(dy,math.sqrt(dx*dx+dz*dz))
 return {root=root,rail={a=a,b=b,verified=true},heading=h,incline=r,
  native={yaw=(math.floor(h*32768/math.pi)-16384)%65536,pitch=0,roll=math.floor(r*32768/math.pi)},
  clip=reverse and 'jimmie_stock_v1_board_reverse_balance042' or 'jimmie_original_v1_board_balance042',blend=1}
end
local function castle()
 return args(vec(-818,614,-429),vec(-622,614,-429),vec(-720,603.756,-429))
end
local function accepted(a)local r=M.compute(a);assert(r.ok,r.reason);return r end
local function rejected(a,reason)local r=M.compute(a);assert(not r.ok and r.reason==reason,r.reason..' ~= '..reason)end
local function check_contacts(a,r)
 local u={};local dx,dy,dz=a.rail.b.x-a.rail.a.x,a.rail.b.y-a.rail.a.y,a.rail.b.z-a.rail.a.z
 local length=math.sqrt(dx*dx+dy*dy+dz*dz);u.x,u.y,u.z=dx/length,dy/length,dz/length
 for _,p in ipairs({r.truckA,r.truckB}) do
  local x,y,z=p.x-a.rail.a.x,p.y-a.rail.a.y,p.z-a.rail.a.z
  local d=x*u.x+y*u.y+z*u.z;assert(d>=0 and d<=length)
  local e=math.sqrt((x-d*u.x)^2+(y-d*u.y)^2+(z-d*u.z)^2)
  assert(e<=r.contactTolerance+1e-8);near(e,r.maxTruckResidual,1e-8)
 end
 near(r.truckCenter.x,r.contactCenter.x);near(r.truckCenter.y,r.contactCenter.y);near(r.truckCenter.z,r.contactCenter.z)
end
group('Castle exact flat contact / truck rather than deck',function()
 local a=castle();local r=accepted(a);near(r.delta.x,0);near(r.delta.y,7.144);near(r.delta.z,3.1)
 near(r.root.y,610.9);assert(r.centerContact and r.exactTruckContact);check_contacts(a,r)
end)
group('BoB diagonal quantized yaw / both travel directions',function()
 for _,reverse in ipairs({false,true})do
  local a,b=vec(-1521,891,2034),vec(1288,891,3820)
  if reverse then a,b=b,a end
  local q=args(a,b,vec((a.x+b.x)/2,901,(a.z+b.z)/2),reverse)
  -- Actual collision crest direction differs from the visible alpha line.
  q.heading=math.atan(reverse and -2812 or 2812,reverse and -1789 or 1789)
  q.native.yaw=(math.floor(q.heading*32768/math.pi)-16384)%65536
  local r=accepted(q);near(r.delta.y,-13.1);near(r.root.y,887.9)
  assert(not r.exactTruckContact and r.maxTruckResidual>.001);check_contacts(q,r)
 end
end)
group('inclined rail both directions / reverse clip invariant',function()
 local a,b=vec(-220,600,100),vec(220,820,410)
 for _,back in ipairs({false,true})do
  local q=args(back and b or a,back and a or b,vec(0,704,255),false)
  local r=accepted(q);check_contacts(q,r)
  q.clip='jimmie_stock_v1_board_reverse_balance042';local s=accepted(q)
  same(r.delta,s.delta);same(r.truckCenter,s.truckCenter)
 end
end)
group('finite endpoints, minimum 35.34 inset plus safety, never clamp',function()
 local q=castle();q.root.x=q.rail.a.x+37.34;accepted(q)
 q.root.x=q.root.x-.001;rejected(q,'outside-contact-interior')
 q=castle();q.root.x=q.rail.b.x-37.34;accepted(q)
 q.root.x=q.root.x+.001;rejected(q,'outside-contact-interior')
 q=castle();q.root.x=1000;rejected(q,'outside-contact-interior')
 q=castle();q.rail.b.x=q.rail.a.x+74;rejected(q,'segment-too-short')
 q=castle();q.safetyMargin=6.66;near(accepted(q).inset,42)
 q.root.x=q.rail.a.x+41.999;rejected(q,'outside-contact-interior')
end)
group('offset caps reject instead of clamp, including blend zero',function()
 local q=castle();q.root.y=578.900000001;near(accepted(q).fullDelta.y,32)
 q.root.y=578.89;rejected(q,'offset-out-of-bounds');q.blend=0;rejected(q,'offset-out-of-bounds')
 q=castle();q.root.z=-457.899999999;near(accepted(q).fullDelta.z,32)
 q.root.z=-457.91;rejected(q,'offset-out-of-bounds')
 q=castle();q.root.y=642.899999999;near(accepted(q).fullDelta.y,-32)
end)
group('smooth entry/exit and no partial-contact claim',function()
 near(M.blend(0,1),0);near(M.blend(1,0),0);near(M.blend(1,1),1);near(M.blend(.5,1),.5)
 near(M.blend(.25,.75),.15625);assert(M.blend(-1,1)==nil);assert(M.blend(0/0,1)==nil)
 local q=castle();local full=accepted(q)
 for _,b in ipairs({0,.25,.5,.75,1})do
  q.blend=b;local r=accepted(q);near(r.delta.y,full.delta.y*b)
  assert(r.centerContact==(b==1));assert(r.exactTruckContact==(b==1))
  near(r.maxTruckResidual,math.sqrt(full.delta.y^2+full.delta.z^2)*(1-b),1e-8)
  near(r.fullBlendTruckResidual,0)
 end
 q.blend=1.001;rejected(q,'invalid-blend')
end)
group('native s16 low-four-bit quantization and signed aliases',function()
 local q=castle();q.native.yaw=15;local a=accepted(q);q.native.yaw=0;local b=accepted(q);same(a.delta,b.delta)
 q.native.yaw=-1;local c=accepted(q);q.native.yaw=65535;local d=accepted(q);same(c.delta,d.delta)
 assert(c.maxTruckResidual>0 and c.maxTruckResidual<=.12)
 q.native.yaw=65536;rejected(q,'invalid-native-angles')
 q=castle();q.native.yaw=.5;rejected(q,'invalid-native-angles')
end)
group('wrong clips, direction, bank, slope and stale native pose reject',function()
 local q=castle();q.clip='jimmie_original_v1_board_balance043';rejected(q,'unsupported-clip')
 q=castle();q.heading=0;rejected(q,'travel-misaligned')
 q=castle();q.native.yaw=16384;rejected(q,'native-misaligned')
 q=castle();q.native.roll=1000;rejected(q,'native-misaligned')
 q=castle();q.native.pitch=1;rejected(q,'unsupported-bank')
 q=castle();q.incline=math.pi/2;rejected(q,'invalid-travel')
 q=castle();q.rail.b=vec(q.rail.a.x,800,q.rail.a.z);rejected(q,'incompatible-slope')
end)
group('nonfinite, degenerate, unverified and malformed geometry reject',function()
 assert(not M.compute(nil).ok)
 local q=castle();q.root.x=0/0;rejected(q,'invalid-root')
 q=castle();q.rail.b.z=math.huge;rejected(q,'invalid-segment')
 q=castle();q.rail.b=cp(q.rail.a);rejected(q,'degenerate-segment')
 q=castle();q.rail.verified=false;rejected(q,'unverified-rail')
 q=castle();q.safetyMargin=-.1;rejected(q,'invalid-margin')
 q=castle();q.blend=math.huge;rejected(q,'invalid-blend')
 q=castle();q.root.x=32769;rejected(q,'invalid-root')
end)
group('immutable inputs, repeated frames and equal unaliased trio',function()
 local q=castle();local before=cp(q);local r=accepted(q)
 for i=1,100 do local next=accepted(q);same(r.delta,next.delta);same(before,q)end
 local parts=M.paired(r);same(parts.body,parts.board);same(parts.body,parts.brace)
 parts.body.x=99;near(parts.board.x,0);near(parts.brace.x,0);near(r.delta.x,0)
 assert(M.paired({ok=false})==nil)
end)
return n
''')
print(f'PASS {count} focused Lua groups + source-evidence checks. No engine/render/controller acceptance claimed.')
print('HELPER_SHA256', hashlib.sha256((HERE/'presentation_anchor.lua').read_bytes()).hexdigest())
