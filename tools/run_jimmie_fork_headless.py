"""Run a bounded windowless fork test in a fresh private game/save directory."""
from pathlib import Path
import argparse, datetime, hashlib, importlib.util, json, os, re, shutil, subprocess, time
ROOT=Path(__file__).resolve().parents[1]
PERSONAL=ROOT.parent/'jimmie-64'
TERRAIN=PERSONAL/'docs/original-skate-motion-20261107/stock-integration/terrain-review'
VOICE=ROOT/'tools/jimmie_harnesses/voice.lua'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seconds',type=int,default=90)
    p.add_argument('--expected-engine-sha256',required=True)
    p.add_argument('--case',choices=['terrain-voice','outcomes','plain','timing-status','rail-physics','moving-rails','raised-rails','raised-rails-roomy','falls-getup'],default='terrain-voice')
    a=p.parse_args()
    if not 15<=a.seconds<=180:raise SystemExit('Test duration must be 15..180 seconds')
    exe=ROOT/'build/us_pc/sm64coopdx.exe'
    if sha(exe)!=a.expected_engine_sha256:raise SystemExit('Build identity changed')
    mod_source=ROOT/'mods/jimmie'
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
    harnesses={'plain':[], 'falls-getup':[ROOT/'tools/jimmie_harnesses/falls_getup.lua'], 'outcomes':[ROOT/'tools/jimmie_harnesses/outcomes.template.lua'], 'terrain-voice':[TERRAIN/'native_terrain_harness.lua',VOICE], 'timing-status':[ROOT/'tools/jimmie_harnesses/timing_status.lua'], 'rail-physics':[ROOT/'tools/jimmie_harnesses/rail_physics.lua'], 'moving-rails':[ROOT/'tools/jimmie_harnesses/moving_rails.lua'], 'raised-rails':[ROOT/'tools/jimmie_harnesses/raised_rails.lua'], 'raised-rails-roomy':[ROOT/'tools/jimmie_harnesses/raised_rails_roomy.lua']}[a.case]
    with guard.LaunchLock():
        if guard.running_game_pids():raise SystemExit('REFUSED: existing game; nothing launched')
        stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        run=ROOT/'build/jimmie-runs'/(stamp+'-'+a.case)
        game=run/'game';save=run/'save';temp=run/'temp'
        for path in (game,save,temp):path.mkdir(parents=True)
        shutil.copyfile(exe,game/exe.name)
        for dll in (ROOT/'build/us_pc').glob('*.dll'):shutil.copyfile(dll,game/dll.name)
        shutil.copytree(ROOT/'build/us_pc/lang',game/'lang')
        rom=PERSONAL/'coopdx/sm64coopdx/baserom.us.z64'
        if hashlib.md5(rom.read_bytes()).hexdigest()!='20b854b239203baf6c961b850a4a51a2':raise SystemExit('Unsupported local ROM; no launch')
        shutil.copyfile(rom,game/'baserom.us.z64')
        db=PERSONAL/'coopdx/sm64coopdx/gamecontrollerdb.txt'
        if db.is_file():shutil.copyfile(db,game/db.name)
        mod=game/'mods/jimmie';shutil.copytree(mod_source,mod)
        main=(mod/'main.lua').read_text(encoding='utf-8-sig')
        if a.case=='terrain-voice':main+='\noriginalOutcomes=TrickOutcomes.new{random=function() return 1000 end}\n' # terrain fixture excludes the independently tested random crash outcome
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
            'forced_outcome_miss_in_terrain':a.case=='terrain-voice','controlled_rail_contact':a.case=='rail-physics','native_controller_routes':a.case in ('moving-rails','raised-rails','raised-rails-roomy'),'forced_outcome_miss_in_rail_physics':a.case=='rail-physics','harnesses':{str(h):sha(h) for h in harnesses},'guard_sha256':sha(guard_path),
            'title_recordings':title_sources,'title_music_omitted':True,'runner_sha256':sha(Path(__file__))}
        if a.case in ('raised-rails','raised-rails-roomy'):inputs['raised_rails_verifier_sha256']=sha(ROOT/'tools/verify_jimmie_raised_rails.py')
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
                    if a.case=='terrain-voice' and '[stock-terrain] COMPLETE ' in log and '[fork-spoken] COMPLETE ' in log:
                        reason='observation-complete';break
                    if a.case=='falls-getup' and '[fall-getup] COMPLETE ' in log:
                        reason='observation-complete';break
                    if a.case=='outcomes' and '[trick-outcomes] COMPLETE ' in log:
                        reason='observation-complete';break
                    if a.case=='timing-status' and '[personal-status] COMPLETE ' in log:
                        reason='observation-complete';break
                    if a.case=='rail-physics' and '[rail-physics] COMPLETE ' in log:
                        reason='observation-complete';break
                    if a.case=='moving-rails' and '[moving-rails] COMPLETE ' in log:
                        reason='observation-complete';break
                    if a.case in ('raised-rails','raised-rails-roomy') and '[raised-rails] COMPLETE ' in log:
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
            marker='[raised-rails] case-end ' if a.case in ('raised-rails','raised-rails-roomy') else '[moving-rails] case-end ' if a.case=='moving-rails' else '[rail-physics] case-end ' if a.case=='rail-physics' else '[stock-terrain] case-end '
            if marker in line:
                try:cases.append(json.loads(line.split(marker,1)[1]))
                except json.JSONDecodeError:pass
        by_case={c['case']:c for c in cases}
        checks={'personal_unchanged':before==after,'five_original_actors':len(list((mod/'actors').glob('*.bin')))==5}
        if a.case=='terrain-voice':
            for key in ('east_late','west_late'):
                c=by_case.get(key,{})
                checks[key+'_hop_grounded']=bool(c.get('hadHop') and c.get('final',{}).get('grounded'))
            c=by_case.get('close_native_rejoin',{})
            checks['close_rejoin']=bool(c.get('placed') and 0<c.get('rejoinAge',0)<=90)
            checks['voice_decode_and_qa_starts']='[fork-spoken] COMPLETE ' in text
            checks['terrain_windows_complete']='[stock-terrain] COMPLETE ' in text
        if a.case=='rail-physics':
            for key in ('downhill','downhill_cap','uphill_stall','uphill_momentum','flat_friction','flat_stall'):
                checks['physics_'+key]=by_case.get(key,{}).get('passed') is True
            checks['controlled_physics_complete']='[rail-physics] COMPLETE ' in text
        if a.case=='moving-rails':
            for key in ('east_parallel','west_parallel','center_stairs'):
                c=by_case.get(key,{})
                checks[key+'_native_movement']=c.get('nativeMovement') is True
                checks[key+'_moving_grind']=c.get('hadMovingGrind') is True
                checks[key+'_completed_journey']=c.get('completedJourneys',0)>0
            checks['moving_routes_complete']='[moving-rails] COMPLETE ' in text
        if a.case in ('raised-rails','raised-rails-roomy'):
            for key in (('castle_banister_roomy' if a.case=='raised-rails-roomy' else 'castle_banister'),'bob_lower_fence'):
                c=by_case.get(key,{})
                checks[key+'_native_movement']=c.get('nativeMovement') is True
                checks[key+'_moving_raised_grind']=c.get('hadMovingGrind') is True
                checks[key+'_completed_journey']=c.get('completedJourneys',0)>0
            checks['raised_routes_complete']='[raised-rails] COMPLETE ' in text
        if a.case=='plain':
            checks['native_profile_verified']='Jimmie PB profile verified:' in text
            checks['no_profile_rejection']='Jimmie PB profile:' not in text and 'Jimmie PB profile rejected:' not in text
        if a.case=='timing-status':
            checks['diagnostic_guard_and_scalar_snapshot']='[personal-status] COMPLETE ' in text
            checks['no_personal_pb_written']=not (save/'jimmie_16star_personal_v2.pb').exists()
        if a.case=='falls-getup':
            for marker in ('BEGIN','GETUP_COMMITTED','FALLBACK_RESPAWN','COMPLETE'):
                checks['falls_'+marker.lower()]='[fall-getup] '+marker+' ' in text
            checks['falls_proof_loss_injected']='[fall-getup] FAULT proofLossDuringGetup=true' in text and '[fall-getup] FALLBACK_RESPAWN paired=true braceSeconds=10 injected=true' in text
            for phase in ('fall','getup','idle'):
                for role in ('body','board'):
                    checks['falls_render_'+phase+'_'+role]=bool(re.search(r'\[fall-getup\] RENDER phase='+phase+r' role='+role+r' clip=\S+ frame=\d+ gfxDelta=(?:0\.0[0-1]\d*|0\.000000)',text))
            checks['falls_current_source_markers']=all(label+'='+package[name] in text for label,name in [('main','main.lua'),('crash','crash.lua'),('clips','crash_clips.lua'),('native','native_crash.lua'),('controller','original_motion_controller.lua')])
        if a.case=='outcomes':
            for marker in ('BOUNDARIES','ACTUAL_HIT','RECOVERED','COMPLETE'):
                checks['outcomes_'+marker.lower()]='[trick-outcomes] '+marker+' ' in text
        lua_errors=[line for line in text.splitlines() if any(x in line.lower() for x in ('lua error','script error','[lua]','stack traceback','segmentation fault'))]
        checks['no_lua_errors']=not lua_errors
        trace=(run/'native-trace.jsonl').read_text(errors='replace') if (run/'native-trace.jsonl').exists() else ''
        report={'passed':all(checks.values()),'checks':checks,'engine_sha256':sha(exe),'case':a.case,'cases':cases,
            'exit_code':child.returncode,'stop_reason':reason,'owned_termination_requested':terminated,'kill_requested':killed,
            'elapsed_seconds':time.monotonic()-start,'lua_errors':lua_errors,
            'heap_allocation_errors':[line for line in text.splitlines() if 'heap.c:' in line and ('alloc' in line.lower() or 'pool' in line.lower()) and ('error' in line.lower() or 'failed' in line.lower())],
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
