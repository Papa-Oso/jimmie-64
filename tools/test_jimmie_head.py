"""Compile native adapter and verbatim upstream interaction functions in isolation.

The camera projection, audio and display-list submission are explicit stubs in
the C harness. This is not a rendered game test or an input-device test.
"""
import argparse, hashlib, json, os, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def function(source,name):
    start=source.index('void '+name+'(');brace=source.index('{',start);depth=1;end=brace+1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[start:end]
def main():
    p=argparse.ArgumentParser();p.add_argument('--cc',type=Path,required=True);p.add_argument('--out',type=Path,default=ROOT/'build/head-tests');a=p.parse_args()
    a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=True)
    joints=(ROOT/'src/goddard/joints.c').read_text()
    selected=['grabbable_joint_update_func','eye_joint_update_func']
    pre='\n'.join('#include "goddard/'+s+'.h"' for s in ['gd_types','gd_macros','gd_main','gd_math','dynlist_proc','draw_objects','objects','sfx','jimmie_head'])
    sliced=a.out/'native_interactions.c';sliced.write_text(pre+'\n'+'\n'.join(function(joints,n) for n in selected)+'\n')
    flags=['-std=gnu11','-O2','-Iinclude','-Isrc','-I.','-DVERSION_US','-D_LANGUAGE_C','-DNON_MATCHING','-DAVOID_UB','-DF3DEX_GBI_2','-DF3DEX_GBI_2E','-DJIMMIE_NATIVE_HEAD']
    exe=a.out/'native-head-tests.exe'
    env=dict(os.environ);env['PATH']=str(a.cc.resolve().parent)+os.pathsep+env.get('PATH','')
    temp=a.out/'tmp';temp.mkdir(exist_ok=True)
    env.update(TEMP=str(temp),TMP=str(temp),TMPDIR=str(temp))
    command=[str(a.cc.resolve()),*flags,'tools/test_jimmie_head_native.c',str(sliced),'src/goddard/gd_math.c','-lm','-o',str(exe)]
    build=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True)
    (a.out/'compile.log').write_text(build.stdout+build.stderr)
    report={'command':command,'compile_exit':build.returncode,'sources':{s:hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in ['src/goddard/joints.c','src/goddard/gd_math.c','src/goddard/jimmie_head.c','src/goddard/generated/jimmie_head_data.inc.h','tools/test_jimmie_head_native.c']},'native_functions':selected,'limits':'camera projection/audio/render submission stubbed; no visual, controller, startup or GPU evidence'}
    if build.returncode==0:
        run=subprocess.run([str(exe)],env=env,capture_output=True,text=True,timeout=40)
        report.update(run_exit=run.returncode,output=run.stdout+run.stderr)
    (a.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return build.returncode or report.get('run_exit',1)
if __name__=='__main__': raise SystemExit(main())
