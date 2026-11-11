"""Generate a local-only native title rig from the approved Jimmie v7 package.

Never writes to the supplied model, live game, or saves. Generated artwork is
excluded from sharing; regenerate it from the owner's local approved input.
"""
from pathlib import Path
import argparse, hashlib, json, math, re
import numpy as np
from PIL import Image

ENGINE = Path(__file__).resolve().parents[1]

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def build(source, out):
    d = json.loads((source / 'jimmie_poses.json').read_text())
    profiles = {
        '5064f18107614ee3ef65224d20ffbffa84ae7cdb0bfbd100187a5ac64f000d4b':
            ('production-v7', 2295, 4260, range(910,936), 910, 1784,
             'f7fff84afb06d9f8b55a79b2cef902f9e838521a1706ace808fceef37973caa8'),
        'e686f2d0d5abd3db8fac8c859d7139a6c3f2f3baf6827530ddae53b853bfe9e5':
            ('approved-refined-grin', 3953, 7596, range(768,794), 2568, 5120,
             '73cd9f93e4e1e8fda8535671e3ae2765da6cb7da9ca5863d59706174d41414a6'),
    }
    profile, nv, nf, neck, hv, hf, atlas_sha = profiles[sha(source/'jimmie_poses.json')]
    assert sha(source/'jimmie_face.png') == atlas_sha
    assert len(d['verts']) == nv and len(d['faces']) == nf
    ids = [i for i,b in enumerate(d['bone_owners']) if b == 'hawk_head' and i not in neck]
    assert len(ids) == hv
    index = {v:i for i,v in enumerate(ids)}
    faces = [(i,[index[v] for v in f]) for i,f in enumerate(d['faces']) if all(v in index for v in f)]
    assert len(faces) == hf
    enum_text = (ENGINE/'src/goddard/dynlists/dynlists.h').read_text()
    enum = {n:int(v) for n,v in re.findall(r'(DYN\w+)\s*=\s*(\d+)',enum_text)}
    master = (ENGINE/'src/goddard/dynlists/dynlist_mario_master.c').read_text()
    face_text = (ENGINE/'src/goddard/dynlists/dynlist_mario_face.c').read_text()
    cage = np.array([[float(v) for v in m] for m in re.findall(r'\{\s*(-?\d+),\s*(-?\d+),\s*(-?\d+)\s*\}',face_text.split('mario_Face_VtxData[][3] = {')[1].split('};')[0])])
    joint_weights = {}
    shape = joint = None
    for line in master.splitlines():
        m=re.search(r'SetSkinShape\((\w+)\)',line)
        if m: shape=m[1]
        m=re.search(r'MakeAttachedJoint\((\w+)\)',line)
        if m: joint=enum[m[1]]
        m=re.search(r'SetSkinWeight\((\d+),\s*([\d.]+)\)',line)
        if m and shape=='DYNOBJ_MARIO_FACE_SHAPE':
            joint_weights.setdefault(joint,np.zeros(len(cage)))[int(m[1])]=float(m[2])/100
    drivers = sorted(set(joint_weights)|{6,15,106,122})
    driver_index = {j:i for i,j in enumerate(drivers)}
    points=np.array([[d['verts'][i][0]*10,(d['verts'][i][2]-135)*10+140,-d['verts'][i][1]*10] for i in ids])
    weights=[]
    for old,p in zip(ids,points):
        dist=np.linalg.norm(cage-p,axis=1)
        nearest=np.argsort(dist)[:4]
        blend=1/np.maximum(dist[nearest],1)**2; blend/=blend.sum()
        w={j:float(v[nearest]@blend) for j,v in joint_weights.items()}
        # The original model has separate nose and moustache components.
        # Semantic ownership avoids transferring cheek/cap motion to these.
        x,y,z=d['verts'][old]
        if z < 140 and y < -24 and d['vertex_regions'][old]=='hair':
            w={6 if x<0 else 15:1.0}
        elif y < -25.01 and d['vertex_regions'][old]=='skin':
            w={185:1.0}
        # Native eyelid rotation is retargeted inside the face atlas, not into
        # unrelated cheek/forehead vertices selected by Mario-space proximity.
        w.pop(206, None); w.pop(215, None)
        # The original seventh handle drives joint194. Nearest-Mario-cage
        # transfer barely reaches Jimmie's shorter chin. Give the actual front
        # chin a smooth localized response while preserving its rest geometry.
        if old < 354 and d['vertex_regions'][old]=='skin':
            u,v=d['uvs'][old]
            def smooth(a,b,x):
                t=max(0.,min(1.,(x-a)/(b-a)));return t*t*(3-2*t)
            front=smooth(0,18,-y)
            chin=front*(1-smooth(18,27,abs(u*64-32)))*smooth(50,58,v*64)
            if chin>0:
                w={j:value*(1-.8*chin) for j,value in w.items() if j!=194}
                w[194]=.8*chin

        w={j:v for j,v in sorted(w.items(),key=lambda q:-q[1])[:4] if v>0.001}
        total=sum(w.values())
        if total>1: w={j:v/total for j,v in w.items()}
        weights.append(w)
    tex_faces=set(d['tex_faces'])
    atlas=Image.open(source/'jimmie_face.png').convert('RGBA')
    rgba=np.array(atlas)
    # Separate sclera/lid and pupil surfaces retain the approved source pixels.
    # Their source atlas is unchanged. Only the title's derived atlas is cleared.
    clean=rgba.copy()
    extra=[]
    verts=[]
    def add(p,c,uv,w):
        ws=[(driver_index[j],v) for j,v in w.items()]
        ws += [(0,0)]*(4-len(ws))
        verts.append((list(p),list(c),list(uv),ws))
        return len(verts)-1
    for old,p,w in zip(ids,points,weights): add(p,d['colors'][old],d['uvs'][old],w)
    triangles=[(f,1 if old in tex_faces else 0) for old,f in faces]
    for quad,c,ws in extra:
        v=[add(p,c,[0,0],w) for p,w in zip(quad,ws)]
        triangles += [([v[0],v[2],v[1]],0),([v[0],v[3],v[2]],0)]
    # Three packed vertices per triangle avoids runtime cache/index rewriting.
    # Both frames own their vertices/display lists (no deferred-render aliasing).
    packed=[]; ordered=[]
    for texture in (0,1):
        for f,t in triangles:
            if t==texture:
                ordered.append((len(packed),texture))
                packed.extend(f)
    out.mkdir(parents=True,exist_ok=True)
    lines=['/* Generated local artwork; see tools/build_jimmie_head.py. */',
           f'#define JH_VERTEX_COUNT {len(verts)}',f'#define JH_PACKED_COUNT {len(packed)}',
           f'#define JH_SOURCE_VERTEX_COUNT {hv}',
           f'#define JH_TRIANGLE_COUNT {len(triangles)}',f'#define JH_SOLID_TRIANGLES {sum(t==0 for _,t in triangles)}',
           f'#define JH_DRIVER_COUNT {len(drivers)}',
           'static const int sJhDriverIds[JH_DRIVER_COUNT] = {'+','.join(map(str,drivers))+'};',
           'static const struct JhBindVertex sJhBind[JH_VERTEX_COUNT] = {']
    for p,c,uv,ws in verts:
        lines.append('{{'+','.join(f'{v:.6f}f' for v in p)+'},{'+','.join(str(int(v)) for v in c)+'},{'+','.join(str(round(v*2048)) for v in uv)+'},{'+','.join(str(j) for j,w in ws)+'},{'+','.join(f'{w:.7f}f' for j,w in ws)+'}},')
    lines+=['};','static const unsigned short sJhPacked[JH_PACKED_COUNT] = {',','.join(map(str,packed)),'};',
            'static const unsigned char sJhTexture[] = {']
    for row in clean:
        lines.append(','.join(str(int(v)) for pixel in row for v in pixel)+',')
    lines+=['};']
    eye_base=rgba.copy(); pupil=np.zeros((64,64),dtype=np.uint8)
    for cx in (21,43):
        for yy in range(28,35):
            for xx in range(cx-4,cx+4):
                pupil[yy,xx]=round(max(0.,min(1.,(225-int(rgba[yy,xx,2]))/200.))*255)
                if pupil[yy,xx]:
                    eye_base[yy,xx]=[248,242,225,255]
    lines+=['static const unsigned char sJhEyeBase[] = {']
    for row in eye_base:
        lines.append(','.join(str(int(v)) for pixel in row for v in pixel)+',')
    lines+=['};', 'static const unsigned char sJhPupilAlpha[] = {']
    for row in pupil: lines.append(','.join(str(int(v)) for v in row)+',')
    lines+=['};']
    (out/'jimmie_head_data.inc.h').write_text('\n'.join(lines)+'\n')
    report={'source_sha256':{p.name:sha(p) for p in [source/'jimmie_poses.json',source/'jimmie_face.png']},
            'engine_source_sha256':{p.name:sha(p) for p in [ENGINE/'src/goddard/dynlists/dynlist_mario_master.c',ENGINE/'src/goddard/dynlists/dynlist_mario_face.c']},
            'source_profile':profile,'source_vertices':hv,'source_triangles':hf,'rig_vertices':len(verts),'rig_triangles':len(triangles),'drivers':drivers,
            'rig_sha256':sha(out/'jimmie_head_data.inc.h'),'status':'candidate; native visual review required'}
    (out/'jimmie_head_manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True)
    p.add_argument('--out',type=Path,default=ENGINE/'src/goddard/generated')
    a=p.parse_args();build(a.source.resolve(),a.out.resolve())
