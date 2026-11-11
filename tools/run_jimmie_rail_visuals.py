"""Isolated real OpenGL rail frames; no camera, pose or movement forcing.
The existing guarded map runner remains unchanged. Nothing is installed.
"""
from pathlib import Path
import argparse, datetime, hashlib, importlib.util, json, os, re, shutil, subprocess, time
ROOT=Path(__file__).resolve().parents[1]
PERSONAL=ROOT.parent/'jimmie-64'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def _png_from_ppm(path):
    """Lossless format conversion of our bounded RGB framebuffer, no dependencies."""
    import struct, zlib
    data=path.read_bytes()
    header=re.match(rb'P6\n([0-9]+) ([0-9]+)\n255\n',data)
    if not header:raise ValueError('Unexpected framebuffer PPM header')
    width,height=map(int,header.groups())
    if not (1<=width<=640 and 1<=height<=480):raise ValueError('Framebuffer exceeds capture bounds')
    pixels=data[header.end():]
    if len(pixels)!=width*height*3:raise ValueError('Incomplete framebuffer pixels')
    def chunk(tag,body):
        return struct.pack('>I',len(body))+tag+body+struct.pack('>I',zlib.crc32(tag+body)&0xffffffff)
    rows=b''.join(b'\0'+pixels[y*width*3:(y+1)*width*3] for y in range(height))
    png=(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))
         +chunk(b'IDAT',zlib.compress(rows,6))+chunk(b'IEND',b''))
    output=path.with_suffix('.png');output.write_bytes(png)
    return {'png':output.name,'png_sha256':sha(output),'ppm_sha256':sha(path),
            'width':width,'height':height,'sampled_color_values':len(set(pixels[::97]))}

def _collect_visual_evidence(run,log):
    records=[];traces=[];events=[]
    for line in log.splitlines():
        for marker,target in (('[jimmie-visual] frame ',records),
                              ('[raised-rails] trace ',traces),
                              ('[raised-rails] event ',events)):
            if marker in line:
                try:target.append(json.loads(line.split(marker,1)[1]))
                except json.JSONDecodeError:pass
                break
    if len(records)>360:raise ValueError('Capture exceeded bounded frame count')
    captured=[];errors=[]
    for record in records:
        name=record.get('file','')
        if not re.fullmatch(r'game-[0-9]+-l[0-9]+-a[0-9]+-f[0-9]+\.ppm',name):
            errors.append('Unexpected capture filename');continue
        path=run/'frames'/name
        try:converted=_png_from_ppm(path)
        except (OSError,ValueError) as exc:
            errors.append(name+': '+str(exc));continue
        nearby=[t for t in traces if t.get('level')==record['level'] and t.get('area')==record['area']]
        nearest=min(nearby,key=lambda t:abs(t['frame']-record['frame']),default=None)
        exact=nearest is not None and nearest['frame']==record['frame']
        linked=nearest if nearest and abs(nearest['frame']-record['frame'])<=3 else None
        entry=dict(record,**converted)
        entry['native_trace']=linked
        entry['exact_native_tick']=exact
        body=nearest.get('body') if exact else None
        board=nearest.get('board') if exact else None
        pair=bool(body and board and not body.get('unavailable') and not board.get('unavailable'))
        entry['observed_pair_present_at_exact_tick']=pair
        entry['grind_at_exact_tick']=bool(exact and pair and nearest.get('grind'))
        # The route harness retains its last final/gap while the pair is absent
        # during respawn. Never turn that stale diagnostic into close-pass proof.
        actor=body.get('object') if pair else None
        mario=nearest.get('mario') if pair else None
        gap=((actor['x']-mario['x'])**2+(actor['z']-mario['z'])**2)**0.5 if actor and mario else None
        entry['observed_pair_horizontal_gap']=gap
        entry['near_mario_at_exact_tick']=bool(gap is not None and gap<140)
        captured.append(entry)
    grind=[r for r in captured if r['grind_at_exact_tick']]
    close=[r for r in captured if r['near_mario_at_exact_tick']]
    selected=[]
    for group in (grind,close):
        if group:
            for index in sorted({0,len(group)//2,len(group)-1}):
                if group[index]['png'] not in selected:selected.append(group[index]['png'])
    if not selected and captured:selected=[captured[len(captured)//2]['png']]
    summary={'capture_count':len(captured),'exact_grind_frames':len(grind),
             'exact_near_mario_frames':len(close),'review_pngs':selected,'errors':errors,
             'nonuniform_frames':sum(r['sampled_color_values']>8 for r in captured),
             'frame_interval_game_ticks':3,'frame_cap':360,'resolution_cap':[640,480],
             'limits':'Real hidden OpenGL framebuffer with the ordinary gameplay camera. Synthetic native input after one placement. Pixel export may affect timing. Logs and screenshots prove only the observed run, not reliability, human-controller or audible acceptance.',
             'frames':captured}
    (run/'visual-frames.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seconds',type=int,default=55)
    p.add_argument('--expected-engine-sha256',required=True)
    p.add_argument('--expected-visible-sha256',required=True)
    p.add_argument('--preflight-only',action='store_true')
    p.add_argument('--diagnostics',action='store_true',help='Observe existing clearance checks; no extra native probes')
    p.add_argument('--case',choices=['grounds-route','grounds-roomy','bob-route'],default='grounds-route')
    a=p.parse_args()
    if not 15<=a.seconds<=180:raise SystemExit('Test duration must be 15..180 seconds')
    exe=ROOT/'build/us_pc/sm64coopdx.exe'
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
    harnesses=[ROOT/'tools/jimmie_harnesses'/('map_rails.lua' if a.case=='map-rails' else 'raised_rails_roomy.lua')]
    with guard.LaunchLock():
        if guard.running_game_pids():raise SystemExit('REFUSED: existing game; nothing launched')
        if a.preflight_only:
            print(json.dumps({'preflight':True,'existing_game':False,'engine_sha256':sha(exe),'visible_sha256':a.expected_visible_sha256,'protected_files':len(before)}));return 0
        stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        run=ROOT/'build/map-rails/visuals'/(stamp+'-'+a.case)
        game=run/'game';save=run/'save';temp=run/'temp';frames=run/'frames'
        for path in (game,save,temp,frames):path.mkdir(parents=True)
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
        for harness in harnesses:
            body=harness.read_text(encoding='utf-8-sig').replace('__MAIN_SHA__',sha(mod_source/'main.lua')).replace('__CONTROLLER_SHA__',sha(mod_source/'original_motion_controller.lua'))
            if a.case in ('grounds-route','grounds-roomy'):
                # Reuse the reviewed native-input/normal-outcome harness without
                # changing its source. Only scene route and sloping route-floor
                # validation differ; all live rail authority remains untouched.
                start=body.index('local qa=')
                end=body.index('local function emit',start)
                body=body[:start]+"""local qa={tick=0,index=1,sceneTick=0,results={},episodes={},done=false,cases={
 {name='grounds_side_fence',level=LEVEL_CASTLE_GROUNDS,area=1,
  start={-3635.736,408.454,-339.439},player={-3203.4,438.9,-256.4},
  stick=48,frames=600,waypoints={{-2850,-188.5},{-3750,-361.4}}}
}}
"""+body[end:]
                old="local h,s=find_floor(x,y+24,z)\n  local okay=s~=nil and numeric(h) and math.abs(h-y)<=24"
                new="local route=string.sub(label,1,6)=='route-'\n  local h,s=find_floor(x,y+(route and 180 or 24),z)\n  local okay=s~=nil and numeric(h) and math.abs(h-y)<=(route and 180 or 24)"
                if body.count(old)!=1:raise SystemExit('Roomy floor-validation contract changed')
                body=body.replace(old,new).replace("fixtureVariant='roomy'","fixtureVariant='grounds-native-slope'")
                if a.case=='grounds-roomy':
                    body=body.replace("name='grounds_side_fence'", "name='grounds_roomy_fence'")
                    body=body.replace('player={-3203.4,438.9,-256.4}', 'player={-3320.556693,434.814393,-59.912074}')
                    body=body.replace('waypoints={{-2850,-188.5},{-3750,-361.4}}', 'waypoints={{-2534.930114,91.054410},{-4007.979949,-192.007748}}')
                    body=body.replace("fixtureVariant='grounds-native-slope'", "fixtureVariant='grounds-roomy-native-slope'")
            if a.case=='bob-route':
                start=body.index('local qa=');end=body.index('local function emit',start)
                body=body[:start]+"""local qa={tick=0,index=1,sceneTick=0,results={},episodes={},done=false,cases={
 {name='bob_lower_fence',level=9,area=1,start={-72.057727,768,2861.002140},
  player={-527.66828524,768,2571.14179536},stick=48,frames=600,
  waypoints={{-915.780983,2324.223724},{181.0592498,3022.0356648}}}
}}
"""+body[end:]
            if a.diagnostics and a.case in ('grounds-route','grounds-roomy'):
                body+='\n'+(ROOT/'tools/jimmie_harnesses/map_rails_diagnostics.lua').read_text(encoding='utf-8-sig')
            main+='\n;(function()\n'+body+'\nend)()\n'
        if harnesses:(mod/'main.lua').write_text(main,encoding='utf-8')
        # These five existing title recordings stay private. Captured title music is
        # deliberately not introduced as a dependency in this fork test.
        title=game/'jimmie-title';title.mkdir()
        title_sources={}
        for name in ('title_good_morning_01.ogg','title_good_morning_02.ogg','title_good_morning_03.ogg','title_pink_bitch_insurance.ogg','title_whats_happening.ogg'):
            src=PERSONAL/'coopdx/sm64coopdx/jimmie-title'/name
            title_sources[name]=sha(src);shutil.copyfile(src,title/name)
        (save/'sm64config.txt').write_text('master_volume 0\nfullscreen false\nwindow_w 640\nwindow_h 480\namount_of_players 1\nbubble_death false\ncoop_mod_dev_mode false\nbackground_gamepad false\ndisable_gamepads true\ndebug_error true\ndebug_info true\n',encoding='utf-8')
        env=os.environ.copy()
        for k in list(env):
            if k.startswith('JIMMIE_'):env.pop(k)
        env.update(APPDATA=str(run/'appdata'),LOCALAPPDATA=str(run/'localappdata'),TEMP=str(temp),TMP=str(temp),
            SDL_JOYSTICK_RAWINPUT='0',SDL_AUDIODRIVER='dummy',JIMMIE_NATIVE_HEAD='1',
            JIMMIE_HEAD_TEST_START='1',JIMMIE_HEAD_TRACE=str(run/'native-trace.jsonl'),JIMMIE_GAME_FRAMES=str(frames))
        args=[str(game/'sm64coopdx.exe'),'--console','--hide-loading-screen','--windowed','--width','640','--height','480','--backend','opengl','--server','58460',
            '--playercount','1','--skip-intro','--skip-update-check','--no-discord','--disable-mods','--enable-mod','jimmie','--savepath',str(save)]
        inputs={'engine_sha256':sha(exe),'args':args,'before':before,'package_files':package,
            'native_map_transitions':a.case=='map-rails','native_controller_route':a.case in ('grounds-route','grounds-roomy','bob-route'),'seeded_rail':False,'outcome_overrides':False,'harnesses':{str(h):sha(h) for h in harnesses},'guard_sha256':sha(guard_path),
            'clearance_diagnostic_sha256':sha(ROOT/'tools/jimmie_harnesses/map_rails_diagnostics.lua') if a.diagnostics else None,'copied_visible_sha256':sha(mod/'skate_visible_rails.lua'),'running_main_sha256':sha(mod/'main.lua'),'title_recordings':title_sources,'title_music_omitted':True,'runner_sha256':sha(Path(__file__)),'rendered_capture':True,'hidden_window':True,'capture_sources':{name:sha(ROOT/name) for name in ('src/pc/gfx/gfx_opengl.c','src/pc/gfx/gfx_sdl.c')}}
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
                    if ('[map-rails] COMPLETE ' if a.case=='map-rails' else '[raised-rails] COMPLETE ') in log:
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
            marker='[map-rails] case-end ' if a.case=='map-rails' else '[raised-rails] case-end '
            if marker in line:
                try:cases.append(json.loads(line.split(marker,1)[1]))
                except json.JSONDecodeError:pass
        by_case={c['case']:c for c in cases}
        checks={'personal_unchanged':before==after,'five_original_actors':len(list((mod/'actors').glob('*.bin')))==5}
        if a.case=='map-rails':
            checks['map_routes_complete']='[map-rails] COMPLETE ' in text
            for key in ('grounds_first','castle_first','castle_basement','castle_upper','grounds_return'):
                checks[key]=by_case.get(key,{}).get('passed') is True
            checks['new_grounds_metadata']=by_case.get('grounds_first',{}).get('visibleSegments',0)>0
            checks['grounds_return_consistent']=all(by_case.get('grounds_first',{}).get(k)==by_case.get('grounds_return',{}).get(k) for k in ('segmentCount','visibleSegments','matchedLoadedSegments'))
        else:
            c=by_case.get('bob_lower_fence' if a.case=='bob-route' else 'grounds_roomy_fence' if a.case=='grounds-roomy' else 'grounds_side_fence',{})
            checks['route_complete']='[raised-rails] COMPLETE ' in text
            checks['native_movement']=c.get('nativeMovement') is True
            checks['moving_grind']=c.get('hadMovingGrind') is True
            checks['completed_journey']=c.get('completedJourneys',0)>0
        lua_errors=[line for line in text.splitlines() if any(x in line.lower() for x in ('lua error','script error','[lua]','stack traceback','segmentation fault'))]
        checks['no_lua_errors']=not lua_errors
        checks['metadata_identity_preserved']=sha(mod_source/'skate_visible_rails.lua')==sha(mod/'skate_visible_rails.lua')==a.expected_visible_sha256
        heap_errors=[line for line in text.splitlines() if 'heap.c:' in line and ('alloc' in line.lower() or 'pool' in line.lower()) and ('error' in line.lower() or 'failed' in line.lower())]
        checks['no_heap_allocation_errors']=not heap_errors
        trace=(run/'native-trace.jsonl').read_text(errors='replace') if (run/'native-trace.jsonl').exists() else ''
        visual=_collect_visual_evidence(run,text)
        checks['framebuffer_captured']=visual['capture_count']>0 and not visual['errors']
        checks['nonuniform_framebuffer']=visual['nonuniform_frames']>0
        checks['rendered_grind_linked']=visual['exact_grind_frames']>0
        report={'visual_evidence':{k:v for k,v in visual.items() if k!='frames'},'passed':all(checks.values()),'checks':checks,'engine_sha256':sha(exe),'case':a.case,'cases':cases,
            'exit_code':child.returncode,'stop_reason':reason,'owned_termination_requested':terminated,'kill_requested':killed,
            'elapsed_seconds':time.monotonic()-start,'lua_errors':lua_errors,
            'heap_allocation_errors':heap_errors,
            'heap_warning_lines':[line for line in text.splitlines() if 'alloc_bank_or_seq' in line or 'heap' in line.lower() and 'warn' in line.lower()],
            'all_error_lines':[line for line in text.splitlines() if any(x in line.lower() for x in ('error','failed to','failed:'))],
            'actor_caches':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in (mod/'actors').glob('*.bin')},
            'native_title_started':'test_start_pressed' in trace,'title_music_omitted':True,
            'before':before,'after':after,'limits':visual['limits']}
        (run/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({'report':str(run/'report.json'),'passed':report['passed'],'checks':checks,
            'cases':cases,'exit_code':child.returncode,'stop_reason':reason,'errors':report['all_error_lines'][-12:]},indent=2),flush=True)
        return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
