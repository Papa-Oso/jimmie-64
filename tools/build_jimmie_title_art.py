"""Convert frozen approved title artwork to native RGBA16 tiles; source untouched."""
from pathlib import Path
from PIL import Image
import hashlib, json, shutil
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT.parent/'jimmie-64/docs/start-screen-20261107/backdrop.png'
EXPECTED='4d2bba92df616680567aec3c553f75ca57bb8ff4f362f29346ca3fc9974f1975'
def main():
    sha=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    assert sha==EXPECTED,'Staged art changed; review before regeneration'
    image=Image.open(SOURCE).convert('RGB');assert image.size==(512,256)
    lines=['/* Generated from frozen staged title artwork; see manifest. */']
    draws=[]
    for ty in range(8):
        for tx in range(16):
            index=ty*16+tx;data=[]
            for r,g,b in image.crop((tx*32,ty*32,tx*32+32,ty*32+32)).get_flattened_data():
                value=((r>>3)<<11)|((g>>3)<<6)|((b>>3)<<1)|1
                data.extend((value>>8,value&255))
            lines.append(f'ALIGNED8 static const u8 sTitleTile{index}[] = {{')
            lines += [','.join(f'0x{x:02x}' for x in data[n:n+32])+',' for n in range(0,len(data),32)]
            lines.append('};')
            left=-96+tx*32;top=248-ty*32
            lines.append(f'static const Vtx sTitleQuad{index}[] = {{')
            for x,y,s,t in [(left,top,0,0),(left,top-32,0,1024),(left+32,top-32,1024,1024),(left+32,top,1024,0)]:
                lines.append('{{{%d,%d,0},0,{%d,%d},{255,255,255,255}}},'%(x,y,s,t))
            lines.append('};')
            draws += [f'gsDPLoadTextureBlock(sTitleTile{index}, G_IM_FMT_RGBA, G_IM_SIZ_16b, 32, 32, 0, G_TX_CLAMP, G_TX_CLAMP, 5, 5, G_TX_NOLOD, G_TX_NOLOD),',
                      f'gsSPVertex(sTitleQuad{index},4,0),','gsSP2Triangles(0,1,2,0,0,2,3,0),']
    lines += ['static const Gfx sJimmieTitleBackdrop[] = {',
        'gsSPDisplayList(dl_proj_mtx_fullscreen),','gsDPSetCycleType(G_CYC_1CYCLE),',
        'gsSPClearGeometryMode(G_LIGHTING | G_ZBUFFER | G_CULL_BACK),',
        'gsDPSetCombineMode(G_CC_DECALRGB,G_CC_DECALRGB),',
        'gsDPSetRenderMode(G_RM_AA_OPA_SURF,G_RM_AA_OPA_SURF2),',
        'gsDPSetTextureFilter(G_TF_POINT),','gsSPTexture(0xffff,0xffff,0,G_TX_RENDERTILE,G_ON),',
        *draws,'gsDPPipeSync(),','gsSPTexture(0xffff,0xffff,0,G_TX_RENDERTILE,G_OFF),',
        'gsSPSetGeometryMode(G_LIGHTING | G_ZBUFFER | G_CULL_BACK),',
        'gsDPSetTextureFilter(G_TF_BILERP),','gsDPSetCombineMode(G_CC_SHADE,G_CC_SHADE),',
        'gsDPSetRenderMode(G_RM_AA_ZB_OPA_SURF,G_RM_AA_ZB_OPA_SURF2),','gsSPEndDisplayList(),','};']
    out=ROOT/'src/menu/generated';out.mkdir(exist_ok=True)
    header=out/'jimmie_title_art.inc.h';header.write_text('\n'.join(lines)+'\n')
    greetings=json.loads((SOURCE.parent/'greeting_manifest.json').read_text())
    expected=['615d531863f1ec063ab1a5b72f2698a659bc9336f683bd9b9ca13f1f7b42d8eb','ec08ee24b1cb057080058702df06368d41bcc27db9676ec63d7f6046e7de6846','c2dff5a3ebdaeae90fee01f7a6a208880db0805f866c69bd884e69a221061933']
    assert len(greetings)==3
    audio=ROOT/'build/us_pc/jimmie-title';audio.mkdir(parents=True,exist_ok=True)
    for i,item in enumerate(greetings):
        assert item['file']==f'title_good_morning_{i+1:02}.ogg'
        source=SOURCE.parent/'sound'/item['file']
        assert hashlib.sha256(source.read_bytes()).hexdigest()==item['sha256']==expected[i]
        shutil.copyfile(source,audio/item['file'])
    (out/'jimmie_title_art_manifest.json').write_text(json.dumps(dict(source=str(SOURCE),source_sha256=sha,header_sha256=hashlib.sha256(header.read_bytes()).hexdigest(),tiles=128,format='RGBA16 big-endian bytes',safe_frame=[96,8,320,240],greetings=greetings),indent=2)+'\n')
    print(out)
if __name__=='__main__':main()
