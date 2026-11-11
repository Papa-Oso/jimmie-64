"""Focused actual-source native timer and bridge tests; no game launch/live writes."""
from pathlib import Path
import datetime, hashlib, json, os, subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
STAGE=ROOT.parent/'jimmie-64/docs/automatic-run-clock-20261107'
def main():
    out=ROOT/'build/pb-tests'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(parents=True);cc=ROOT.parent/'jimmie-native-head-toolchain/msys64/mingw64/bin/gcc.exe'
    env=dict(os.environ,PATH=str(cc.parent)+os.pathsep+os.environ.get('PATH',''),TEMP=str(out),TMP=str(out),TMPDIR=str(out))
    for key in ('JIMMIE_HEAD_TRACE','JIMMIE_HEAD_TEST_START','JIMMIE_HEAD_TEST_INTERACTION','JIMMIE_SDL_CONTROLLER_TEST'):env.pop(key,None)
    flags=['-std=gnu11','-O2','-Iinclude','-Isrc','-Isrc/pc','-I.','-Ilib/lua/include','-DVERSION_US','-D_LANGUAGE_C','-DNON_MATCHING','-DAVOID_UB','-DF3DEX_GBI_2','-DF3DEX_GBI_2E','-DJIMMIE_NATIVE_HEAD']
    steps=[
        [sys.executable,'-B','tools/pin_jimmie_text_profile.py','--check'],
        [str(cc),*flags,'-Wall','-Wextra','-Werror','src/pc/jimmie_run_clock.c','tools/test_jimmie_run_clock_core.c','-o',str(out/'core.exe')],
        [str(out/'core.exe'),str(out)],
        [str(cc),*flags,'-Djrc_monotonic_us=jrc_platform_monotonic_us','-c','src/pc/jimmie_run_clock.c','-o',str(out/'core.o')],
        [str(cc),*flags,'-Wall','-Wextra','-Werror','tools/test_jimmie_run_bridge.c',str(out/'core.o'),'-o',str(out/'bridge.exe')],
        [str(out/'bridge.exe'),str(out)],
    ]
    results=[]
    for command in steps:
        run=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=45)
        results.append(dict(command=command,exit=run.returncode,output=run.stdout+run.stderr))
        print(run.stdout+run.stderr,flush=True)
        if run.returncode:break
    sources=[ROOT/p for p in ['src/pc/jimmie_run_bridge.c','src/pc/jimmie_companion_profile.c','src/pc/generated/jimmie_companion_profile.inc.h','src/pc/generated/jimmie_text_profile.inc.h','src/pc/jimmie_run_clock.c','src/pc/jimmie_run_clock.h','tools/test_jimmie_run_bridge.c','tools/pin_jimmie_text_profile.py']]
    sources.append(STAGE/'test_run_clock.c')
    report=dict(passed=len(results)==len(steps) and all(r['exit']==0 for r in results),steps=results,
      sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
      limits='Bridge uses actual engine types/source with fixture state and clock; core exercises actual QPC and Windows persistence. No full played run or GPU presentation timing.')
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(out/'report.json')
    return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
