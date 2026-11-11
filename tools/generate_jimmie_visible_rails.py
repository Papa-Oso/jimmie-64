"""Private static-alpha appearance candidates, NOT proven grindable rails.
No ROM, textures or complete meshes are exported. Unsupported areas fail closed.
No arguments regenerate the private metadata; --plan and --check never write.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import re
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT.parent / 'jimmie-64/docs/follow-tricks-20261107/installation/native-build'
ROM = NATIVE / 'build/us_pc/baserom.us.z64'


def sha(path):
 return hashlib.sha256(path.read_bytes()).hexdigest()


def clean(text):
 return re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)


def source_us(text):
 # Explicit private input configuration; no speculative preprocessor evaluation.
 flags = {'VERSION_US':True, 'VERSION_JP':False, 'VERSION_EU':False,
          'VERSION_SH':False, 'ENHANCE_LEVEL_TEXTURES':True}
 active, stack, output = True, [], []
 for line in clean(text).splitlines():
  if line.lstrip().startswith('#'):
   directive = line.lstrip()[1:].strip().split()
   if not directive:
    continue
   op = directive[0]
   if op in ('ifdef', 'ifndef'):
    if len(directive) != 2 or directive[1] not in flags:
     raise ValueError('unsupported preprocessor condition ' + line.strip())
    condition = flags[directive[1]]
    if op == 'ifndef': condition = not condition
    stack.append((active, condition, False));active = active and condition
   elif op == 'else':
    if not stack or stack[-1][2]: raise ValueError('invalid preprocessor else')
    parent, condition, _ = stack[-1]
    stack[-1] = (parent, condition, True);active = parent and not condition
   elif op == 'endif':
    if not stack: raise ValueError('unmatched preprocessor endif')
    active = stack.pop()[0]
   elif op != 'include':
    raise ValueError('unsupported preprocessor directive ' + line.strip())
  elif active:
   output.append(line)
 if stack: raise ValueError('unclosed preprocessor condition')
 return '\n'.join(output)


def definitions(text):
 return [(m.group(2), m.group(1)) for m in re.finditer(
  r'\bDEFINE_LEVEL\(\s*"[^"]*"\s*,\s*(LEVEL_\w+)\s*,\s*\w+\s*,\s*(\w+)\s*,', clean(text))]


def area_roots(script):
 result = {}
 for area, name in re.findall(r'\bAREA\(\s*(\d+)\s*,\s*(\w+)\s*\)', clean(script)):
  area = int(area)
  if area in result and result[area] != name:
   raise ValueError('ambiguous area mapping ' + str(area))
  result[area] = name
 return result


# Only structural/static geo commands supported. Runtime-rendered objects and
# ASM-produced geometry are deliberately outside the exported candidate set.
GEO_SAFE = set('NODE_START NODE_SCREEN_AREA OPEN_NODE CLOSE_NODE ZBUFFER NODE_ORTHO BACKGROUND BACKGROUND_COLOR CAMERA_FRUSTUM CAMERA_FRUSTUM_WITH_FUNC CAMERA RENDER_OBJ ASM SWITCH_CASE CULLING_RADIUS RENDER_RANGE NOP'.split())


def alpha_roots(geo, root):
 layouts = dict(re.findall(r'(?:static\s+)?const GeoLayout (\w+)\[\]\s*=\s*\{(.*?)\};', clean(geo), re.S))
 roots = []
 def walk(name, stack):
  if name in stack or len(stack) > 32:
   raise ValueError('geo recursion')
  if name not in layouts:
   raise ValueError('unresolved geo layout ' + name)
  for m in re.finditer(r'\bGEO_(\w+)\s*\((.*?)\)', layouts[name], re.S):
   op, args = m.group(1), [x.strip() for x in m.group(2).split(',')]
   if op == 'DISPLAY_LIST':
    if len(args) != 2 or not re.fullmatch(r'\w+', args[1]):
     raise ValueError('unsupported geo display list')
    if args[0] == 'LAYER_ALPHA' and args[1] not in roots:
     roots.append(args[1])
   elif op == 'BRANCH':
    if len(args) != 2 or args[0] not in ('0', '1'):
     raise ValueError('unsupported geo branch')
    walk(args[1], stack + [name])
    if args[0] == '0':
     return
   elif op in ('RETURN', 'END'):
    return
   elif op not in GEO_SAFE:
    raise ValueError('unsupported geo command GEO_' + op)
 walk(root, [])
 return roots


# Explicit allowlist: never silently ignore a new geometry-affecting operation.
DL_STATE = set(('gsDPLoadBlock gsDPLoadSync gsDPLoadTextureBlock gsDPPipeSync '
 'gsDPSetCombineMode gsDPSetCycleType gsDPSetDepthSource gsDPSetEnvColor '
 'gsDPSetFogColor gsDPSetRenderMode gsDPSetTextureFilter gsDPSetTextureImage '
 'gsDPSetTextureLOD gsDPSetTexturePersp gsDPSetTile gsDPSetTileSize gsDPTileSync '
 'gsSPClearGeometryMode gsSPFogFactor gsSPFogPosition gsSPGeometryMode '
 'gsSPLight gsSPSetGeometryMode gsSPTexture').split())


def display_triangles(roots, lists, vertices):
 triangles = []
 def walk(name, slots, stack):
  if name in stack or len(stack) > 16:
   raise ValueError('display-list recursion')
  if name not in lists:
   raise ValueError('unresolved alpha list ' + name)
  for m in re.finditer(r'\b(gs\w+)\s*\((.*?)\)', clean(lists[name]), re.S):
   op, args = m.group(1), [x.strip() for x in m.group(2).split(',')]
   if op == 'gsSPEndDisplayList':
    return
   if op in ('gsSPDisplayList', 'gsSPBranchList'):
    walk(args[0], slots, stack + [name])
    if op == 'gsSPBranchList':
     return
   elif op == 'gsSPVertex':
    if len(args) != 3 or args[0] not in vertices:
     raise ValueError('unresolved vertex expression ' + args[0])
    count, base = int(args[1], 0), int(args[2], 0)
    if count <= 0 or base < 0 or base + count > 16 or count > len(vertices[args[0]]):
     raise ValueError('out-of-range vertex load')
    for i in range(count):
     slots[base+i] = vertices[args[0]][i]
   elif op in ('gsSP1Triangle', 'gsSP2Triangles'):
    ids = [int(x, 0) for x in args]
    if len(ids) != (8 if op == 'gsSP2Triangles' else 4):
     raise ValueError('malformed triangle')
    for start in ((0, 4) if op == 'gsSP2Triangles' else (0,)):
     if any(i < 0 or i >= 16 or i not in slots for i in ids[start:start+3]):
      raise ValueError('out-of-range or unloaded triangle vertex')
     triangles.append(tuple(slots[i] for i in ids[start:start+3]))
   elif op not in DL_STATE:
    raise ValueError('unsupported display-list command ' + op)
 for root in roots:
  walk(root, {}, [])
 return triangles


def extract(level, area=1):
 folder = ROOT / 'levels' / level / 'areas' / str(area)
 geo_path = folder / 'geo.inc.c'
 script_path = ROOT / 'levels' / level / 'script.c'
 sources = {p:p.read_text() for p in sorted(folder.glob('*/model.inc.c'))}
 evidence = {p.relative_to(ROOT).as_posix():sha(p) for p in [geo_path, script_path, *sources]}
 receipt = dict(area=area, source_sha256=evidence, alpha_roots=[], segments=0,
  warnings=[], raw_segment_sha256={}, status='excluded', scope='static alpha appearance candidates only')
 vertices, lists, raws = {}, {}, {}
 try:
  mapped = area_roots(source_us(script_path.read_text()))
  if area not in mapped:
   raise ValueError('area has no script mapping')
  receipt['geo_root'] = mapped[area]
  roots = alpha_roots(source_us(geo_path.read_text()), mapped[area])
  receipt['alpha_roots'] = roots
  if not roots:
   receipt['status'] = 'no-alpha-roots'
   return [], receipt
  for p, text in sources.items():
   text = source_us(text)
   for m in re.finditer(r'ROM_ASSET_LOAD_VTX\((\w+),\s*(0x[0-9a-fA-F]+),\s*[^,]+,\s*(0x[0-9a-fA-F]+),\s*(\d+)\)', text):
    name, rom, off, size = m.group(1), int(m.group(2),16), int(m.group(3),16), int(m.group(4))
    if rom not in raws:
     raws[rom] = subprocess.check_output([str(NATIVE/'tools/mio0.exe'), '-d', '-o', hex(rom), str(ROM), '-'])
    raw = raws[rom]
    if size <= 0 or off + size > len(raw) or size % 16:
     raise ValueError('out-of-range ROM vertex load ' + name)
    decoded = [struct.unpack_from('>hhh',raw,k) for k in range(off,off+size,16)]
    if name in vertices and vertices[name] != decoded:
     raise ValueError('conflicting vertex symbol ' + name)
    vertices[name] = decoded
   for name, body in re.findall(r'(?:static\s+)?const Gfx (\w+)\[\]\s*=\s*\{(.*?)\};', text, re.S):
    if name in lists:
     raise ValueError('duplicate display list ' + name)
    lists[name] = body
  triangles = display_triangles(roots, lists, vertices)
 except (ValueError, KeyError, IndexError) as exc:
  receipt['warnings'] = [str(exc)]
  return [], receipt
 receipt['raw_segment_sha256'] = {hex(k):hashlib.sha256(v).hexdigest() for k,v in raws.items()}
 edges={}
 for tri in triangles:
  a,b,c=tri;ab=[b[i]-a[i] for i in range(3)];ac=[c[i]-a[i] for i in range(3)]
  n=[ab[1]*ac[2]-ab[2]*ac[1],ab[2]*ac[0]-ab[0]*ac[2],ab[0]*ac[1]-ab[1]*ac[0]]
  mag=math.sqrt(sum(x*x for x in n))
  if mag<1 or abs(n[1])/mag>.03:continue
  for i in range(3):
   a,b,c=tri[i],tri[(i+1)%3],tri[(i+2)%3];key=tuple(sorted((a,b)))
   edges.setdefault(key,[]).append(c)
 segments=[]
 for (a,b),thirds in edges.items():
  if len(thirds)!=1:continue
  dx,dz=b[0]-a[0],b[2]-a[2];length=math.hypot(dx,dz)
  if length<72 or abs(b[1]-a[1])/length>.8:continue
  c=thirds[0];t=max(0,min(1,((c[0]-a[0])*dx+(c[2]-a[2])*dz)/(length*length)))
  if a[1]+(b[1]-a[1])*t-c[1]<40:continue
  segments.append(list(a+b))
 if len(segments) > 512:
  receipt['warnings'] = ['exceeds runtime 512-segment area limit']
  return [], receipt
 receipt.update(segments=len(segments), status='candidates' if segments else 'no-top-segments')
 return segments, receipt


def generate():
 maps, areas = [], {}
 definitions_path = ROOT / 'levels/level_defines.h'
 for name, constant in definitions(definitions_path.read_text()):
  for geo in sorted((ROOT/'levels'/name/'areas').glob('*/geo.inc.c')):
   if not geo.parent.name.isdigit():
    continue
   area = int(geo.parent.name)
   segments, receipt = extract(name, area)
   receipt['level'] = constant
   areas[name + '/' + str(area)] = receipt
   if segments:
    maps.append((constant, area, segments))
 # Keep the original map blocks first for an easy baseline review.
 priority = {('LEVEL_CASTLE',1):0, ('LEVEL_BOB',1):1}
 maps.sort(key=lambda row:priority.get((row[0],row[1]),2))
 lines = ['-- Private static-alpha appearance candidates; NOT proven grindable.',
  '-- Live collision, entry, exit and presentation checks remain mandatory.',
  '-- Unsupported/scaled/dynamic geometry is excluded. Private derived geometry.', 'return {maps={']
 for level, area, segments in maps:
  lines.append(" {level='"+level+"',area="+str(area)+',segments={')
  lines.extend('  {'+','.join(str(v) for v in seg)+'},' for seg in segments)
  lines.append(' }},')
 lines.extend(['}}',''])
 content = '\n'.join(lines)
 receipt = dict(schema=2, input_configuration='VERSION_US; ENHANCE_LEVEL_TEXTURES=1 (Makefile default; no build overrides)', scope='Candidate appearance descriptors, not proven grindable or exhaustive coverage',
  excluded_geometry=['dynamic/object meshes', 'non-alpha layers', 'ASM-generated geometry', 'unsupported geo transforms or references'],
  source_sha256={'Makefile':sha(ROOT/'Makefile'), 'levels/level_defines.h':sha(definitions_path),
   'tools/generate_jimmie_visible_rails.py':sha(Path(__file__))},
  rom_sha256=sha(ROM), extractor_sha256=sha(NATIVE/'tools/mio0.exe'), areas=areas,
  generated_sha256=hashlib.sha256(content.encode()).hexdigest())
 return content, receipt


def main():
 parser = argparse.ArgumentParser(description=__doc__)
 mode = parser.add_mutually_exclusive_group()
 mode.add_argument('--plan', action='store_true', help='compute coverage without writing')
 mode.add_argument('--check', action='store_true', help='check metadata is current without writing')
 args = parser.parse_args()
 content, receipt = generate()
 target = ROOT/'mods/jimmie/skate_visible_rails.lua'
 summary = dict(areas=len(receipt['areas']), candidate_areas=sum(r['status']=='candidates' for r in receipt['areas'].values()),
  segments=sum(r['segments'] for r in receipt['areas'].values()),
  excluded={k:r['warnings'] for k,r in receipt['areas'].items() if r['status']=='excluded'})
 if args.check:
  current = target.exists() and target.read_bytes() == content.encode()
  summary['current'] = current
  print(json.dumps(summary, indent=2))
  return 0 if current else 1
 if not args.plan:
  target.write_text(content, encoding='utf-8', newline='\n')
  out=ROOT/'build/raised-rails';out.mkdir(parents=True,exist_ok=True)
  (out/'visible-generation.json').write_text(json.dumps(receipt,indent=2)+'\n', encoding='utf-8', newline='\n')
 print(json.dumps(summary, indent=2))
 return 0


if __name__ == '__main__':
 raise SystemExit(main())
