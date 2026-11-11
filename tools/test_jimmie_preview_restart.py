"""Exercise the real preview launcher from a fresh PowerShell and unrelated cwd.
Only private preview config is temporarily muted/restored. WM_CLOSE targets the
verified child game; cleanup targets only this launch's captured child identities.
"""
from pathlib import Path
import argparse,datetime,hashlib,json,os,subprocess,time
import psutil
ROOT=Path(__file__).resolve().parents[1]
PREVIEW=ROOT/'build/integrated-preview'
DIRECTOR=PREVIEW/'ai/director.py'
GAME=PREVIEW/'coopdx/sm64coopdx/sm64coopdx.exe'
SAVE=PREVIEW/'coopdx/save'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None

def owned_python():
    result=[]
    for proc in psutil.process_iter(['pid','name','cmdline','create_time']):
        try:
            if proc.info['name'].lower() in ('python.exe','pythonw.exe') and str(DIRECTOR).lower() in ' '.join(proc.info['cmdline']).lower():result.append(proc)
        except (psutil.Error,TypeError):pass
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cycles',type=int,default=2);parser.add_argument('--hold',type=int,default=8);args=parser.parse_args()
    if not 1<=args.cycles<=2 or not 5<=args.hold<=12:parser.error('bounded cycles 1..2; hold 5..12')
    if any(p.info['name'].lower()=='sm64coopdx.exe' for p in psutil.process_iter(['name'])) or owned_python():parser.error('An existing game/preview director is active; no changes made')
    out=ROOT/'build/restart-tests'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True)
    config=SAVE/'sm64config.txt';original=config.read_bytes();before={str(p.relative_to(PREVIEW)):sha(p) for p in (SAVE/'jimmie_16star_pb.txt',SAVE/'sm64_save_file.bin',GAME)}
    config.write_text(original.decode('utf-8')+'\nmaster_volume 0\n',encoding='utf-8')
    env=dict(os.environ,SDL_AUDIODRIVER='dummy',JIMMIE_HEAD_TEST_START='1',JIMMIE_SDL_CONTROLLER_TEST='1')
    cycles=[]
    try:
        for cycle in range(args.cycles):
            start=time.time();status={};game=None;identities=[]
            command=['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(ROOT/'play_jimmie_integrated.ps1')]
            launched=subprocess.run(command,cwd=out,env=env,capture_output=True,text=True,timeout=25)
            deadline=time.monotonic()+12
            while time.monotonic()<deadline:
                path=SAVE/'jimmie_director_status.json'
                if path.exists() and path.stat().st_mtime>=start:
                    try:status=json.loads(path.read_text())
                    except (ValueError,OSError):continue
                    if status.get('running') and status.get('game_pid'):
                        candidate=psutil.Process(status['game_pid'])
                        if Path(candidate.exe()).resolve()==GAME.resolve():game=candidate;break
                time.sleep(.2)
            if game:
                deadline=time.monotonic()+args.hold
                while time.monotonic()<deadline and game.is_running():time.sleep(.2)
                procs=owned_python()
                identities=[(p.pid,p.create_time()) for p in procs]
                child_env=game.environ()
                cleared=all(k not in child_env for k in ('JIMMIE_HEAD_TEST_START','JIMMIE_HEAD_TEST_INTERACTION','JIMMIE_SDL_CONTROLLER_TEST','JIMMIE_HEAD_FRAMES','JIMMIE_HEAD_TRACE'))
                path=str(GAME).replace("'","''")
                close=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',f"$p=Get-Process -Id {game.pid}; if ($p.Path -ne '{path}') {{ throw 'wrong owned game' }}; $p.CloseMainWindow()"],capture_output=True,text=True,timeout=10)
                deadline=time.monotonic()+12
                while time.monotonic()<deadline:
                    status=json.loads((SAVE/'jimmie_director_status.json').read_text())
                    if not status.get('running'):break
                    time.sleep(.2)
                time.sleep(.5)
                remaining=[]
                for pid,created in identities:
                    try:
                        p=psutil.Process(pid)
                        if p.create_time()==created and p.is_running():remaining.append(pid)
                    except psutil.Error:pass
                checks=dict(launcher_exit_zero=launched.returncode==0,owned_game_launched=True,diagnostic_flags_cleared=cleared,
                    clean_game_exit=status.get('game_exit_code')==0,supervisor_stopped=status.get('running') is False,no_orphan_worker=not remaining)
                cycles.append(dict(cycle=cycle+1,checks=checks,status=status,remaining_owned_pids=remaining,close_output=close.stdout+close.stderr,launcher_output=launched.stdout+launched.stderr))
                # Preserve the failure evidence, then stop only identities captured
                # from this launch so the test never leaves an orphan behind.
                for pid,created in identities:
                    try:
                        p=psutil.Process(pid)
                        if p.create_time()==created and p.is_running():p.kill();p.wait(timeout=10)
                    except psutil.NoSuchProcess:pass
                if game.is_running():game.kill();game.wait(timeout=10)
            else:
                cycles.append(dict(cycle=cycle+1,checks=dict(owned_game_launched=False),status=status,launcher_output=launched.stdout+launched.stderr));break
            print(json.dumps(cycles[-1]),flush=True)
    finally:config.write_bytes(original)
    after={str(p.relative_to(PREVIEW)):sha(p) for p in (SAVE/'jimmie_16star_pb.txt',SAVE/'sm64_save_file.bin',GAME)}
    report=dict(passed=len(cycles)==args.cycles and all(all(c['checks'].values()) for c in cycles) and before==after,cycles=cycles,
      before=before,after=after,private_config_restored=config.read_bytes()==original,
      sources={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'play_jimmie_integrated.ps1',DIRECTOR,ROOT/'tools/test_jimmie_preview_restart.py')},
      limits='Fresh shell/process restart, not a machine reboot. Muted title-only launch; no listening, physical-controller or full-run timing claim. Only verified child windows closed.')
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(passed=report['passed'],report=str(out/'report.json'))),flush=True)
    return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
