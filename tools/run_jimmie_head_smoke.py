"""Bounded isolated native-engine startup trace; never uses the live save path."""
from pathlib import Path
import argparse, csv, datetime, hashlib, json, os, subprocess
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--seconds',type=int,default=30);p.add_argument('--render',action='store_true');p.add_argument('--capture',action='store_true');p.add_argument('--start',action='store_true');p.add_argument('--interaction',action='store_true');p.add_argument('--fallback',action='store_true');p.add_argument('--width',type=int,default=800);p.add_argument('--height',type=int,default=600);p.add_argument('--host',action='store_true');p.add_argument('--pb-record',type=Path);a=p.parse_args()
    if not (320<=a.width<=2560 and 240<=a.height<=1440): p.error('unsupported test window size')
    if a.host and (a.start or a.interaction): p.error('host eligibility smoke takes no synthetic input')
    if not 1<=a.seconds<=60: p.error('seconds must be 1..60')
    if a.capture and not a.render: p.error('--capture requires --render')
    running=subprocess.check_output(['tasklist','/FI','IMAGENAME eq sm64coopdx.exe','/FO','CSV','/NH'],text=True,timeout=10)
    if any(row and row[0].lower()=='sm64coopdx.exe' for row in csv.reader(running.splitlines())):
        p.error('A game is already running; this test will not interrupt it.')
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    run=ROOT/'build/head-smoke'/stamp;run.mkdir(parents=True)
    save=run/'save';save.mkdir();(save/'sm64config.txt').write_text('master_volume 0\nfullscreen false\namount_of_players 1\nbubble_death false\nskip_intro false\npause_anywhere false\n')
    if a.pb_record:
        import shutil
        shutil.copyfile(a.pb_record,save/'jimmie_16star_pb.txt')
    binary=ROOT/'build/us_pc/sm64coopdx.exe'
    args=[str(binary),'--console','--hide-loading-screen','--windowed','--width',str(a.width),'--height',str(a.height),'--skip-update-check','--no-discord','--disable-mods','--savepath',str(save)]
    if a.host: args += ['--server','58324','--playercount','1']
    if not a.render: args.append('--headless')
    env=dict(os.environ,SDL_VIDEO_WINDOW_POS='-20000,-20000',APPDATA=str(run/'appdata'),LOCALAPPDATA=str(run/'localappdata'),SDL_JOYSTICK_RAWINPUT='0',SDL_AUDIODRIVER='dummy',JIMMIE_NATIVE_HEAD='0' if a.fallback else '1',JIMMIE_HEAD_TRACE=str(run/'rig.jsonl'))
    for key in ('JIMMIE_HEAD_FRAMES','JIMMIE_HEAD_TEST_START','JIMMIE_HEAD_TEST_INTERACTION'): env.pop(key,None)
    if a.capture:
        args += ['--backend','opengl']
        frames=run/'frames';frames.mkdir();env['JIMMIE_HEAD_FRAMES']=str(frames)
    if a.start: env['JIMMIE_HEAD_TEST_START']='1'
    if getattr(a,'interaction',False): env['JIMMIE_HEAD_TEST_INTERACTION']='1'
    with (run/'stdout.log').open('w') as out,(run/'stderr.log').open('w') as err:
        child=subprocess.Popen(args,cwd=binary.parent,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
        print(json.dumps({'pid':child.pid,'run':str(run)}),flush=True)
        timed_out=False
        try: code=child.wait(timeout=a.seconds)
        except subprocess.TimeoutExpired:
            timed_out=True;child.terminate();code=child.wait(timeout=10)
    trace=run/'rig.jsonl';rows=[json.loads(s) for s in trace.read_text().splitlines()] if trace.exists() else []
    frames=[r for r in rows if r['event']=='frame']
    interactions=[r for r in rows if r['event']=='interaction']
    interaction_checks=[]
    for target in range(7):
        phases={r['phase']:r for r in interactions if r['target']==target}
        if set(phases)!={13,15,21,69}: interaction_checks.append(False);continue
        drag,hold_start,hold,release=[phases[p] for p in (13,15,21,69)]
        axes=('dx','dy','dz')
        interaction_checks.append(bool(drag['picked']) and sum(abs(drag[k]) for k in axes)>1
            and max(abs(hold_start[k]-hold[k]) for k in axes)<.05
            and max(abs(release[k]) for k in axes)<.05)
    report={'executable_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'args':args,'seconds':a.seconds,'bounded_termination':timed_out,'exit_code':code,'rendered_window':a.render,'fallback':a.fallback,'trace':rows,'all_drivers_bound':bool(frames) and all(f['bound']==15 for f in frames),'limits':'No screenshot, listening or controller acceptance. Termination is deliberate, not clean exit.'}
    report.update(start_requested=a.start,start_handed_to_menu=any(r['event']=='title_handed_to_menu' for r in rows),
        interaction_requested=a.interaction,interaction_handles_passed=sum(interaction_checks),
        native_crash_report='Exception occurred' in (run/'stderr.log').read_text())
    if len(frames)>1 and 'wall_time' in frames[-1]:
        elapsed=frames[-1]['wall_time']-frames[0]['wall_time']
        report['native_head_updates_per_second']=(frames[-1]['sample']-frames[0]['sample'])/elapsed
    if a.capture:
        from PIL import Image
        for ppm in (run/'frames').glob('*.ppm'): Image.open(ppm).save(ppm.with_suffix('.png'))
        report['rendered_frame_artifacts']=[str(f.relative_to(run)) for f in (run/'frames').glob('*.png')]
    report['limits']='Application framebuffer exports when requested; synthetic test inputs, not a physical controller; no listening approval or isolated GPU timing. Process termination is deliberate.'
    report.update(pb_events=[r for r in rows if r['event'].startswith('pb_')],greeting_started=any(r['event']=='title_greeting_started' for r in rows),window_size=[a.width,a.height],pb_record_exists=(save/'jimmie_16star_pb.txt').exists(),host_requested=a.host)
    report['passed']=timed_out and report['all_drivers_bound'] and not report['native_crash_report'] and (not a.start or report['start_handed_to_menu']) and (not a.interaction or all(interaction_checks))
    if a.host:
        report['passed'] = timed_out and not report['native_crash_report'] and any(r['event']=='pb_running' and r['phase']==1 and r['elapsed_us']>=5000000 for r in rows) and not any(r['event']=='pb_invalidated' for r in rows) and not report['pb_record_exists']
    (run/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('args','trace')},indent=2))
    return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())

