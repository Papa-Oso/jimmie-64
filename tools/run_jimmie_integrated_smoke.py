"""Bounded private rendered companion/SDL/AI launch. Refuses existing games.
No desktop capture or OS input; terminates only the game it started, then lets
its supervisor close its own worker. The complete run tree is retained.
"""
from pathlib import Path
import argparse, csv, datetime, hashlib, importlib.util, json, os, shutil, subprocess, time
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('--seconds',type=int,default=25)
    p.add_argument('--controller',action='store_true');p.add_argument('--ai',action='store_true')
    a=p.parse_args()
    if not 15<=a.seconds<=90:p.error('seconds must be 15..90')
    running=subprocess.check_output(['tasklist','/FI','IMAGENAME eq sm64coopdx.exe','/FO','CSV','/NH'],text=True,timeout=10)
    if any(r and r[0].lower()=='sm64coopdx.exe' for r in csv.reader(running.splitlines())):p.error('A game is running; no test started')
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run=ROOT/'build/integrated-tests'/stamp;run.mkdir(parents=True)
    source=ROOT/'build/integrated-preview'
    shutil.copytree(source/'ai',run/'ai')
    game=run/'coopdx/sm64coopdx';shutil.copytree(source/'coopdx/sm64coopdx',game)
    save=run/'coopdx/save';save.mkdir();(save/'sm64config.txt').write_text('master_volume 0\nfullscreen false\namount_of_players 1\nbubble_death false\nskip_intro false\npause_anywhere false\ncoop_mod_dev_mode true\nbackground_gamepad true\n')
    frames=run/'frames';frames.mkdir()
    env=dict(os.environ,APPDATA=str(run/'.appdata'),LOCALAPPDATA=str(run/'.localappdata'),
        SDL_JOYSTICK_RAWINPUT='0',SDL_AUDIODRIVER='dummy',JIMMIE_NATIVE_HEAD='1',
        JIMMIE_HEAD_TRACE=str(run/'rig.jsonl'),JIMMIE_HEAD_FRAMES=str(frames))
    for key in ('JIMMIE_HEAD_TEST_START','JIMMIE_HEAD_TEST_INTERACTION','JIMMIE_SDL_CONTROLLER_TEST'):env.pop(key,None)
    if a.controller:env['JIMMIE_SDL_CONTROLLER_TEST']='1'
    # Fresh route proof and empty mailbox before either launch path.
    spec=importlib.util.spec_from_file_location('private_director',run/'ai/director.py')
    director=importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name]=director;spec.loader.exec_module(director)
    director.RelayWriter(game/'mods/jimmie/director_relay.lua').prepare()
    route=director.prepare_route_profile(run)
    assert route['launch_allowed']
    binary=game/'sm64coopdx.exe'
    if a.ai:
        args=[sys.executable,'-B',str(run/'ai/director.py'),'--supervise','--profile','launch']
    else:
        args=[str(binary),'--console','--hide-loading-screen','--windowed','--width','960','--height','720',
              '--backend','opengl','--skip-update-check','--no-discord','--server','58324','--playercount','1',
              '--savepath',str(save),'--enable-mod','jimmie']
    started=time.monotonic();owned_game=None;status={};game_exit=None
    with (run/'stdout.log').open('w') as out,(run/'stderr.log').open('w') as err:
        child=subprocess.Popen(args,cwd=game,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
        print(json.dumps(dict(run=str(run),pid=child.pid,controller=a.controller,ai=a.ai)),flush=True)
        try:
            while child.poll() is None and time.monotonic()-started<a.seconds:
                if a.ai and (save/'jimmie_director_status.json').exists():
                    status=json.loads((save/'jimmie_director_status.json').read_text())
                    owned_game=status.get('game_pid',owned_game)
                time.sleep(.2)
        finally:
            if child.poll() is None:
                if a.ai and owned_game:
                    # PID came only from this fresh supervisor's private status.
                    subprocess.run(['taskkill','/PID',str(owned_game),'/F'],capture_output=True,timeout=10)
                    try:child.wait(timeout=15)
                    except subprocess.TimeoutExpired:child.terminate();child.wait(timeout=10)
                else:child.terminate();child.wait(timeout=10)
            game_exit=child.returncode
    if a.ai and (save/'jimmie_director_status.json').exists():status=json.loads((save/'jimmie_director_status.json').read_text())
    trace=run/'rig.jsonl';rows=[json.loads(s) for s in trace.read_text().splitlines()] if trace.exists() else []
    text=(run/'stdout.log').read_text(errors='replace')+(run/'stderr.log').read_text(errors='replace')
    native=[r for r in rows if r['event']=='frame'];pads={}
    for r in rows:
        if r['event']=='sdl_pad':pads.setdefault(r['frame'],r)
    checks=dict(no_crash='Exception occurred' not in text,no_lua_error='LUA ERROR' not in text,
        bound=bool(native) and all(r['bound']==15 for r in native),greeting=any(r['event']=='title_greeting_started' for r in rows),
        no_pb_write=not(save/'jimmie_16star_pb.txt').exists())
    if a.controller:
        checks.update(axis_right=pads.get(301,{}).get('x',0)>0,axis_left=pads.get(321,{}).get('x',0)<0,
            a_and_r=pads.get(343,{}).get('buttons',0)&0x8010==0x8010,
            r_after_a_release=pads.get(349,{}).get('buttons',0)&0x8010==0x10,
            start=pads.get(600,{}).get('buttons',0)&0x1000==0x1000,
            handoff=any(r['event']=='title_handed_to_host' for r in rows),
            permanent_models=any(r['event']=='permanent_models_loaded' for r in rows),
            synthetic_cannot_record=any(r['event']=='pb_file_selected' and r['phase']==3 for r in rows))
    else:
        checks['companion_run_eligible']=any(r['event']=='pb_running' and r['phase']==1 for r in rows)
        checks['not_invalidated']=not any(r['event']=='pb_invalidated' for r in rows)
    if a.controller:
        gp=[r for r in rows if r['event']=='goddard_pad']
        checks['goddard_stick']=any(r['x']>0 for r in gp) and any(r['x']<0 for r in gp)
        checks['goddard_a_r']=any(r['buttons']&0x8010==0x8010 for r in gp)
    if a.ai:
        checks['lua_error_count_zero']=status.get('lua_errors')==0
        checks['passive_log_available']=not status.get('skate_trace_error')
        checks['supervisor_stopped']=status.get('running') is False
        checks['model_ready']=status.get('backend')=='qwen-local'
    gameplay=[]
    for path in save.glob('jimmie_skate*.jsonl'):
        for line in path.read_text().splitlines():
            batch=json.loads(line)
            for record in batch.get('records',[]):
                if record.get('companion',{}).get('present') and record.get('mario',{}).get('action',0) and not record.get('paused'):gameplay.append(record)
    if a.ai and a.controller:checks['unpaused_gameplay_with_companion']=bool(gameplay)
    from PIL import Image
    for ppm in frames.glob('*.ppm'):Image.open(ppm).save(ppm.with_suffix('.png'))
    report=dict(passed=all(checks.values()),checks=checks,run=str(run),seconds=a.seconds,executable_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
        director_sha256=hashlib.sha256((run/'ai/director.py').read_bytes()).hexdigest(),route=route,status=status,exit_code=game_exit,
        gameplay_samples_with_companion=len(gameplay),events=[r for r in rows if r['event']!='frame'],frames=[str(f.relative_to(run)) for f in frames.glob('*.png')],
        limits='Private virtual SDL controller, not physical-device acceptance. Muted playback, no listening claim. Bounded process termination. No complete run or finish-frame retiming.')
    (run/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(passed=report['passed'],checks=checks,report=str(run/'report.json'),status=status),indent=2),flush=True)
    return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
