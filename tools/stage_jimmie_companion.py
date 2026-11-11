"""Freeze the installed companion into a PRIVATE preview; never edit live runtime.

Re-running updates only staged program/assets, preserving private saves/settings.
The current installed movement source must match the reviewed baseline.
"""
from pathlib import Path
import csv, hashlib, json, shutil, subprocess

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT.parent / 'jimmie-64'
STAGE = ROOT / 'build/integrated-preview'
MAIN_SHA = '0db53aff763652fb290e8d8c2cff92b543bbb595482523cedc98bfb7a921d51a'

def engine_file(p):
    return (p.suffix in ('.lua', '.luac') or
        len(p.parts) == 2 and ((p.parts[0] == 'actors' and p.suffix in ('.bin', '.col')) or
        (p.parts[0] == 'sound' and p.suffix in ('.m64', '.mp3', '.aiff', '.ogg')) or
        (p.parts[0] == 'data' and p.suffix == '.bhv') or
        (p.parts[0] == 'textures' and p.suffix == '.tex') or
        (p.parts[0] == 'levels' and p.suffix == '.lvl')))

def main():
    active = subprocess.check_output(['tasklist', '/FI', 'IMAGENAME eq sm64coopdx.exe', '/FO', 'CSV', '/NH'], text=True, timeout=10)
    if any(r and r[0].lower() == 'sm64coopdx.exe' for r in csv.reader(active.splitlines())):
        raise SystemExit('A game is running; staging was not changed')
    source = LIVE/'coopdx/sm64coopdx/mods/jimmie'
    assert hashlib.sha256((source/'main.lua').read_bytes()).hexdigest() == MAIN_SHA, 'Review changed installed main before refreshing this profile'
    game = STAGE/'coopdx/sm64coopdx'
    mod = game/'mods/jimmie'
    shutil.copytree(source, mod, dirs_exist_ok=True)
    ai = STAGE/'ai'; ai.mkdir(parents=True, exist_ok=True)
    director = (LIVE/'ai/director.py').read_text(encoding='utf-8')
    # Root, telemetry, relay, caches and save destinations stay in the private tree.
    # Only the existing immutable local model is read outside it.
    old = 'model_path = self.root / "models" / "Qwen3-1.7B"'
    assert director.count(old) == 1
    director = director.replace(old, 'model_path = Path(' + repr(str(LIVE/'models/Qwen3-1.7B')) + ')')
    director = director.replace('"--windowed", "--skip-intro", "--console"', '"--windowed", "--skip-update-check", "--no-discord", "--console"')
    old = 'args += ["--enable-mod", "jimmie_text", "--enable-mod", "jimmie_start_concept"]'
    assert director.count(old) == 1
    director = director.replace(old, 'pass  # Native title; original dialogue retained in this timing profile.')
    (ai/'director.py').write_text(director, encoding='utf-8')
    for name in ('persona.txt', 'host_persona.txt', 'route_engine_profile.json', 'skate_trace_analysis.py'):
        shutil.copyfile(LIVE/'ai'/name, ai/name)
    for p in (ROOT/'build/us_pc').glob('*.dll'): shutil.copyfile(p, game/p.name)
    for name in ('baserom.us.z64', 'sm64coopdx.exe'):
        shutil.copyfile(ROOT/'build/us_pc'/name, game/name)
    shutil.copytree(ROOT/'build/us_pc/jimmie-title', game/'jimmie-title', dirs_exist_ok=True)
    save = STAGE/'coopdx/save'; save.mkdir(parents=True, exist_ok=True)
    config = save/'sm64config.txt'
    if not config.exists():
        config.write_text('fullscreen false\namount_of_players 1\nbubble_death false\nskip_intro false\npause_anywhere false\ncoop_mod_dev_mode true\nbackground_gamepad true\n')
    entries = []
    dynamic = {'director_relay.lua': 1, 'route_launch_profile.lua': 2}
    for p in sorted(mod.rglob('*')):
        rel = p.relative_to(mod)
        if p.is_file() and engine_file(rel):
            data = p.read_bytes()
            entries.append(dict(path=rel.as_posix(), md5=hashlib.md5(data).hexdigest(),
                sha256=hashlib.sha256(data).hexdigest(), dynamic=dynamic.get(rel.as_posix(), 0)))
    out = ROOT/'src/pc/generated'; out.mkdir(exist_ok=True)
    header = '/* Frozen installed companion. MD5 matches engine cache identity, not an anti-cheat boundary. */\nstatic const struct JimmieProfileFile sProfileFiles[] = {\n'
    for e in entries:
        values = ','.join('0x'+e['md5'][i:i+2] for i in range(0,32,2))
        header += '    {' + json.dumps(e['path']) + ', {' + values + '}, ' + str(e['dynamic']) + '},\n'
    header += '};\n'
    (out/'jimmie_companion_profile.inc.h').write_text(header)
    manifest = dict(source=str(source), source_main_sha256=MAIN_SHA, files=entries,
        staged_director_sha256=hashlib.sha256((ai/'director.py').read_bytes()).hexdigest(),
        limits='Personal practice profile, not leaderboard certification. Dynamic files must be data-only literals. Native title/engine source and model acceptance remain separate.')
    (STAGE/'source-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(dict(stage=str(STAGE), files=len(entries), lua_files=sum(e['path'].endswith('.lua') for e in entries))))

if __name__ == '__main__': main()
