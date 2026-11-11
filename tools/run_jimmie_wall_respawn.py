"""Isolated native wall-respawn regression; uses the existing guarded runner lifecycle."""
from pathlib import Path
import argparse, datetime, hashlib, importlib.util, json, os, re, shutil, subprocess, time
ROOT=Path(__file__).resolve().parents[1]
PERSONAL=ROOT.parent/'jimmie-64'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seconds',type=int,default=90)
    p.add_argument('--expected-engine-sha256',required=True)
    p.add_argument('--expected-visible-sha256',required=True)
    p.add_argument('--engine-root',type=Path,default=ROOT)
    p.add_argument('--preflight-only',action='store_true')
    p.add_argument('--case',choices=['wall-respawn'],default='wall-respawn')
    a=p.parse_args()
    if not 15<=a.seconds<=180:raise SystemExit('Test duration must be 15..180 seconds')
    exe=a.engine_root.resolve()/'build/us_pc/sm64coopdx.exe'
    if sha(exe)!=a.expected_engine_sha256:raise SystemExit('Build identity changed')
    mod_source=ROOT/'mods/jimmie'
    if sha(mod_source/'skate_visible_rails.lua')!=a.expected_visible_sha256:raise SystemExit('Visible metadata identity changed')
    package={f.relative_to(mod_source).as_posix():sha(f) for f in mod_source.rglob('*') if f.is_file()}
    manifest=json.loads((ROOT/'docs/jimmie/native-baseline-manifest.json').read_text())
    protected_paths=[e['path'] for e in manifest['protected_personal_files']]
    installed=PERSONAL/'main';installed_manifest=installed/'package-manifest.json'
    if installed_manifest.is_file():
        current=json.loads(installed_manifest.read_text())
        for name in current['runtime_files']:
            if not (installed/name).resolve().is_relative_to(installed.resolve()):raise SystemExit('Invalid installed manifest path')
            protected_paths.append('main/'+name)
        for name in ('package-manifest.json','Launch Jimmie 64.exe','user/save/sm64_save_file.bin','user/save/sm64config.txt','user/save/baserom.us.z64','user/save/jimmie_16star_personal_v2.pb'):
            if (installed/name).is_file():protected_paths.append('main/'+name)
    protected_paths=sorted(set(protected_paths))
    before={name:sha(PERSONAL/name) for name in protected_paths}
    guard_path=PERSONAL/'ai/launch_jimmie.py'
    spec=importlib.util.spec_from_file_location('fork_launch_guard',guard_path)
    guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
    harnesses=[ROOT/'tools/jimmie_harnesses/wall_respawn.lua']
    with guard.LaunchLock():
        if guard.running_game_pids():raise SystemExit('REFUSED: existing game; nothing launched')
        if a.preflight_only:
            print(json.dumps({'preflight':True,'existing_game':False,'engine_sha256':sha(exe),'visible_sha256':a.expected_visible_sha256,'protected_files':len(before)}));return 0
        stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        run=ROOT/'build/wall-respawn/native'/(stamp+'-'+a.case)
        game=run/'game';save=run/'save';temp=run/'temp'
        for path in (game,save,temp):path.mkdir(parents=True)
        shutil.copyfile(exe,game/exe.name)
        for dll in exe.parent.glob('*.dll'):shutil.copyfile(dll,game/dll.name)
        shutil.copytree(exe.parent/'lang',game/'lang')
        rom=PERSONAL/'coopdx/sm64coopdx/baserom.us.z64'
        if hashlib.md5(rom.read_bytes()).hexdigest()!='20b854b239203baf6c961b850a4a51a2':raise SystemExit('Unsupported local ROM; no launch')
        shutil.copyfile(rom,game/'baserom.us.z64')
        db=PERSONAL/'coopdx/sm64coopdx/gamecontrollerdb.txt'
        if db.is_file():shutil.copyfile(db,game/db.name)
        mod=game/'mods/jimmie';shutil.copytree(mod_source,mod)
        main=(mod/'main.lua').read_text(encoding='utf-8-sig')
        for harness in harnesses:
            body=harness.read_text(encoding='utf-8-sig').replace('__MAIN_SHA__',sha(mod_source/'main.lua')).replace('__CONTROLLER_SHA__',sha(mod_source/'original_motion_controller.lua'))
            main+='\n;(function()\n'+body+'\nend)()\n'
        if harnesses:(mod/'main.lua').write_text(main,encoding='utf-8')
        # These five existing title recordings stay private. Captured title music is
        # deliberately not introduced as a dependency in this fork test.
        title=game/'jimmie-title';title.mkdir()
        title_sources={}
        for name in ('title_good_morning_01.ogg','title_good_morning_02.ogg','title_good_morning_03.ogg','title_pink_bitch_insurance.ogg','title_whats_happening.ogg'):
            src=PERSONAL/'coopdx/sm64coopdx/jimmie-title'/name
            title_sources[name]=sha(src);shutil.copyfile(src,title/name)
        (save/'sm64config.txt').write_text('master_volume 0\nfullscreen false\nwindow_w 960\nwindow_h 720\namount_of_players 1\nbubble_death false\ncoop_mod_dev_mode false\nbackground_gamepad false\ndisable_gamepads true\ndebug_error true\ndebug_info true\n',encoding='utf-8')
        env=os.environ.copy()
        for k in list(env):
            if k.startswith('JIMMIE_'):env.pop(k)
        env.update(APPDATA=str(run/'appdata'),LOCALAPPDATA=str(run/'localappdata'),TEMP=str(temp),TMP=str(temp),
            SDL_JOYSTICK_RAWINPUT='0',SDL_AUDIODRIVER='dummy',JIMMIE_NATIVE_HEAD='1',
            JIMMIE_HEAD_TEST_START='1',JIMMIE_HEAD_TRACE=str(run/'native-trace.jsonl'))
        args=[str(game/'sm64coopdx.exe'),'--headless','--console','--hide-loading-screen','--server','58460',
            '--playercount','1','--skip-intro','--skip-update-check','--no-discord','--disable-mods','--enable-mod','jimmie','--savepath',str(save)]
        inputs={'engine_sha256':sha(exe),'args':args,'before':before,'package_files':package,
            'native_map_transitions':True,'native_controller_route':False,'seeded_rail':False,'outcome_overrides':False,'harnesses':{str(h):sha(h) for h in harnesses},'guard_sha256':sha(guard_path),
            'copied_visible_sha256':sha(mod/'skate_visible_rails.lua'),'running_main_sha256':sha(mod/'main.lua'),'title_recordings':title_sources,'title_music_omitted':True,'runner_sha256':sha(Path(__file__))}
        (run/'input.json').write_text(json.dumps(inputs,indent=2)+'\n')
        si=subprocess.STARTUPINFO();si.dwFlags|=subprocess.STARTF_USESHOWWINDOW;si.wShowWindow=0
        print(json.dumps({'run':str(run),'seconds':a.seconds,'case':a.case}),flush=True)
        start=time.monotonic();reason='process-exit';terminated=False;killed=False
        with (run/'stdout.log').open('w') as out,(run/'stderr.log').open('w') as err:
            child=subprocess.Popen(args,cwd=game,env=env,stdout=out,stderr=err,
                creationflags=subprocess.CREATE_NO_WINDOW,startupinfo=si)
            (run/'pid.json').write_text(json.dumps({'pid':child.pid,'exe':str(game/'sm64coopdx.exe')}))
            try:
                while child.poll() is None:
                    elapsed=time.monotonic()-start
                    log=(run/'stdout.log').read_text(errors='replace')
                    if '[LUA] Failed to call the callback' in log or '[LUA] Failed to load' in log:
                        reason='lua-failure';break
                    if ('[wall-respawn] COMPLETE ') in log:
                        reason='observation-complete';break
                    if elapsed>=a.seconds:reason='deadline';break
                    time.sleep(1)
            finally:
                if child.poll() is None:
                    terminated=True;child.terminate()
                    try:child.wait(timeout=10)
                    except subprocess.TimeoutExpired:killed=True;child.kill();child.wait(timeout=10)
        text=(run/'stdout.log').read_text(errors='replace')+(run/'stderr.log').read_text(errors='replace')
        after={name:sha(PERSONAL/name) for name in protected_paths}
        cases=[]
        for line in text.splitlines():
            marker='[wall-respawn] case-end '
            if marker in line:
                try:cases.append(json.loads(line.split(marker,1)[1]))
                except json.JSONDecodeError:pass
        by_case={c['case']:c for c in cases}
        checks={'personal_unchanged':before==after,'five_original_actors':len(list((mod/'actors').glob('*.bin')))==5}
        checks['suite_complete']='[wall-respawn] COMPLETE ' in text
        for key in ('grounds','bob_first','bob_star_exit','bob_second','bob_death_exit','bob_third','bob_star_exit_repeat','castle_basement','castle_upper','grounds_return'):
            checks[key]=by_case.get(key,{}).get('passed') is True
        for key in ('bob_star_exit','bob_death_exit','bob_star_exit_repeat'):
            checks[key+'_native_exit_action']=by_case.get(key,{}).get('transitionFrames',0)>0
        lua_errors=[line for line in text.splitlines() if any(x in line.lower() for x in ('lua error','script error','[lua]','stack traceback','segmentation fault'))]
        checks['no_lua_errors']=not lua_errors
        checks['metadata_identity_preserved']=sha(mod_source/'skate_visible_rails.lua')==sha(mod/'skate_visible_rails.lua')==a.expected_visible_sha256
        heap_errors=[line for line in text.splitlines() if 'heap.c:' in line and ('alloc' in line.lower() or 'pool' in line.lower()) and ('error' in line.lower() or 'failed' in line.lower())]
        checks['no_heap_allocation_errors']=not heap_errors
        trace=(run/'native-trace.jsonl').read_text(errors='replace') if (run/'native-trace.jsonl').exists() else ''
        report={'passed':all(checks.values()),'checks':checks,'engine_sha256':sha(exe),'case':a.case,'cases':cases,
            'exit_code':child.returncode,'stop_reason':reason,'owned_termination_requested':terminated,'kill_requested':killed,
            'elapsed_seconds':time.monotonic()-start,'lua_errors':lua_errors,
            'heap_allocation_errors':heap_errors,
            'heap_warning_lines':[line for line in text.splitlines() if 'alloc_bank_or_seq' in line or 'heap' in line.lower() and 'warn' in line.lower()],
            'all_error_lines':[line for line in text.splitlines() if any(x in line.lower() for x in ('error','failed to','failed:'))],
            'actor_caches':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in (mod/'actors').glob('*.bin')},
            'native_title_started':'test_start_pressed' in trace,'title_music_omitted':True,
            'before':before,'after':after,'limits':'Windowless dummy-renderer/audio fixture only. Harness and diagnostic Start invalidate PB. Original music omitted; source recordings private and uncleared. Not visual, natural-play, audible, multiplayer, full-run or clean-machine acceptance.'}
        (run/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({'report':str(run/'report.json'),'passed':report['passed'],'checks':checks,
            'cases':cases,'exit_code':child.returncode,'stop_reason':reason,'errors':report['all_error_lines'][-12:]},indent=2),flush=True)
        return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
