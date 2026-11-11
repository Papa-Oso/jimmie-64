"""Private map-wide numeric rail-candidate audit, not native play acceptance.
Reads local static geometry; writes summary/counts and bounded example coordinates,
never ROM/full mesh, installed game, saves, or settings. Uses existing Lua detector.
The offline adapter supplies no live water/dynamic obstacles: results are hints.
"""
from pathlib import Path
import argparse, hashlib, json, math, re, struct, subprocess, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import generate_jimmie_visible_rails as visible
import test_jimmie_surface_rails as surface
from lupa import LuaRuntime
SHA = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def collision(level, area):
    path = ROOT/'levels'/level/'areas'/str(area)/'collision.inc.c'
    text = path.read_text()
    m = re.search(r'ROM_ASSET_LOAD_COLLISION\([^,]+,\s*(0x[0-9a-fA-F]+),\s*[^,]+,\s*(0x[0-9a-fA-F]+),\s*(\d+)\)', text)
    if not m:
        raise ValueError('unsupported collision source')
    rom, off, size = int(m[1],16),int(m[2],16),int(m[3])
    raw = subprocess.check_output([str(visible.NATIVE/'tools/mio0.exe'),'-d','-o',hex(rom),str(visible.ROM),'-'])
    data=raw[off:off+size]
    if len(data)!=size or len(data)%2: raise ValueError('truncated collision')
    words=struct.unpack('>'+str(len(data)//2)+'h',data)
    if words[0]!=0x40: raise ValueError('unsupported collision prefix')
    count=words[1]; vertices=[words[i:i+3] for i in range(2,2+count*3,3)]
    i=2+count*3;tris=[]
    while words[i]!=0x41:
        kind,count=words[i:i+2];i+=2
        stride=4 if kind in (4,14,36,37,39,44,45) else 3
        for _ in range(count):
            ids=words[i:i+3]; i+=stride
            if len(ids)!=3 or any(k<0 or k>=len(vertices) for k in ids):raise ValueError('invalid collision vertex')
            vs=[vertices[k] for k in ids];a,b,c=vs
            ab=[b[k]-a[k] for k in range(3)];ac=[c[k]-a[k] for k in range(3)]
            n=[ab[1]*ac[2]-ab[2]*ac[1],ab[2]*ac[0]-ab[0]*ac[2],ab[0]*ac[1]-ab[1]*ac[0]]
            length=math.sqrt(sum(x*x for x in n))
            if length==0:continue
            n=[x/length for x in n]
            tris.append(dict(index=len(tris),type=kind,vertices=vs,normal=n,origin=-sum(n[k]*a[k] for k in range(3))))
    return tris,dict(source=path.relative_to(ROOT).as_posix(),source_sha256=SHA(path),collision_sha256=hashlib.sha256(data).hexdigest(),triangles=len(tris))


def audit():
    mod=ROOT/'mods/jimmie';lua=LuaRuntime(unpack_returned_tuples=True)
    current=lua.execute((mod/'skate_visible_rails.lua').read_text())
    definitions=(ROOT/'levels/level_defines.h').read_text()
    lookup={m[1]:m[2] for m in re.finditer(r'DEFINE_LEVEL\("[^\"]*",\s*(LEVEL_\w+),\s*\w+,\s*(\w+)\s*,',definitions)}
    maps=[]
    for mapping in current.maps.values():
        level=lookup[mapping.level];area=mapping.area
        row=dict(level=level,constant=mapping.level,area=area,visible_segments=len(mapping.segments))
        try:
            tris,meta=collision(level,area);row.update(meta);surface.install_geometry(tris)
            h=surface.harness(100)
            h.lua.globals().g[mapping.level]=100
            h.lua.globals().g.gNetworkPlayers[0].currAreaIndex=area
            count=0;examples=[]
            for s in h.world.surfaceRails.segments.values():
                p={k:(s.a[k]+s.b[k])*.5 for k in ('x','y','z')}
                q=h.lua.table_from(p)
                match=h.world.surfaceRails.visible(h.world.surfaceRails,q,s.dx,s.dz,True)
                if match:
                    count+=1
                    if len(examples)<3:
                        feature,diagnostic=h.run('featureAt',q,s.dx,s.dz)
                        examples.append(dict(point=p,direction=[s.dx,s.dz],seed=s.seed,visual_top=match.point.y,feature=feature.feature if feature else None,last_probe_reason=diagnostic['lastReject']))
            row.update(captured_static_segments=len(h.world.surfaceRails.segments),visually_matched_static_hints=count,examples=examples)
        except Exception as e:row['error']=str(e)
        maps.append(row)
        print(json.dumps({k:row[k] for k in ('level','area','visible_segments','visually_matched_static_hints','error') if k in row}),flush=True)
    return dict(schema=1,maps=maps,source_sha256={n:SHA(mod/n) for n in ('skate_surface_rails.lua','skate_visible_rails.lua','skate_probes.lua')},tool_sha256=SHA(Path(__file__)),fixture_sha256={str(Path(p).resolve()):SHA(Path(p)) for p in (surface.__file__,surface.base.__file__,surface.MODEL.__file__,surface.MODEL.geo.__file__)},limits='Private actual static map triangles through an approximate offline adapter. Counts are discovery/appearance hints, not demonstrated grinds. No native water/gas/dynamic-object state, gameplay, renderer, controller or performance proof. No installation or publication.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'build/map-rails/collision-audit.json')
    args=parser.parse_args()
    if not args.out.resolve().is_relative_to(ROOT/'build/map-rails'):raise SystemExit('Output must remain under build/map-rails')
    report=audit();args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(report=str(args.out),maps=len(report['maps']),errors=sum('error' in r for r in report['maps']))))
    return 0 if not any('error' in r for r in report['maps']) else 1

if __name__=='__main__':raise SystemExit(main())
