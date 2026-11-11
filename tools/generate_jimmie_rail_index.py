"""Generate private Castle numeric rail hints from actual local collision.
No full collision mesh is exported. Every runtime hint requires fresh native proof.
Uses the existing private offline Castle triangle adapter; no installs or launch.
"""
from pathlib import Path
import sys,math,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
ADAPTER=ROOT.parent/'jimmie-64/docs/skating-playtest-fix-20261107/castle-geometry'
sys.path.insert(0,str(ADAPTER))
import test_actual_collision_lua as model

def main():
 h=model.Harness(ROOT/'mods/jimmie');hints=[];sources=[]
 weights=[(1/3,1/3,1/3),(.8,.1,.1),(.1,.8,.1),(.1,.1,.8)]
 for t in model.geo.TRIANGLES:
  n=t['normal'];v=t['vertices']
  if n[1]<.65:continue
  lengths=[math.hypot(v[(i+1)%3][0]-v[i][0],v[(i+1)%3][2]-v[i][2]) for i in range(3)]
  longest=max(lengths)
  if longest<96:continue
  area=abs((v[1][0]-v[0][0])*(v[2][2]-v[0][2])-(v[1][2]-v[0][2])*(v[2][0]-v[0][0]))/2
  if not 12<=2*area/longest<=96:continue
  if math.hypot(n[0],n[2])>.05:dx,dz=n[0],n[2]
  else:
   i=lengths.index(longest);dx,dz=v[(i+1)%3][0]-v[i][0],v[(i+1)%3][2]-v[i][2]
  length=math.hypot(dx,dz);dx,dz=dx/length,dz/length
  for weights0 in weights:
   pos=[sum(v[i][k]*weights0[i] for i in range(3)) for k in range(3)]
   feature,receipt=h.run('featureAt',h.pt(pos),dx,dz)
   if feature is None or feature.feature!='two-sided-rail':continue
   if any(math.dist(pos,old[:3])<24 and abs(dx*old[3]+dz*old[4])>.95 for old in hints):continue
   hints.append(pos+[dx,dz]);sources.append(t['index'])
 lines=['-- Generated private geometry hints, not collision clearance or forced plans.',
        '-- Source collision SHA256: '+model.geo.META['collision_sha256'],
        "return {level='LEVEL_CASTLE',area=1,collisionSha256='"+model.geo.META['collision_sha256']+"',hints={"]
 lines += [' {'+','.join(format(x,'.12g') for x in hint)+'},' for hint in hints]
 lines += ['}}','']
 target=ROOT/'mods/jimmie/skate_rail_index.lua';target.write_text('\n'.join(lines),encoding='utf-8',newline='\n')
 report=dict(count=len(hints),collision_sha256=model.geo.META['collision_sha256'],source_triangles=sources,index_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),limits='Private numeric candidate points and tangent hints only. Offline classifier is not native clearance. Runtime checks current level/area, exact floor height, static dry support, width, rail segments, entry, exit and players.')
 out=ROOT/'build/natural-rails';out.mkdir(parents=True,exist_ok=True);(out/'index-generation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
