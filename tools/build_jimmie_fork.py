"""Build only this private fork with the existing sibling Windows toolchain."""
from pathlib import Path
import argparse, datetime, hashlib, json, os, subprocess, time
ROOT = Path(__file__).resolve().parents[1]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--jobs', type=int, default=4)
    a = p.parse_args()
    if not 1 <= a.jobs <= 8: raise SystemExit('jobs must be 1..8')
    if ROOT.name != 'jimmie64-playable-grinds-20261108':
        raise SystemExit('This initial local builder is restricted to the separate fork stage')
    for name in ('build/us_pc/lang', 'build/us_pc/mods', 'build/us_pc/sm64coopdx.app'):
        target = ROOT / name
        if not target.resolve().is_relative_to(ROOT): raise SystemExit('Build target escapes stage: ' + name)
        if any(parent.is_symlink() for parent in [target, *target.parents] if parent.is_relative_to(ROOT)):
            raise SystemExit('Refuse symlinked build target: ' + name)
    personal = ROOT.parent / 'jimmie-64'
    manifest = json.loads((ROOT / 'docs/jimmie/native-baseline-manifest.json').read_text())
    before = {e['path']: sha(personal / e['path']) for e in manifest['protected_personal_files']}
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = ROOT / 'build/jimmie-builds' / stamp
    (out / 'temp').mkdir(parents=True)
    shell = ROOT.parent / 'jimmie-native-head-toolchain/msys64/usr/bin/bash.exe'
    if not shell.is_file(): raise SystemExit('Existing compiler shell missing')
    command = [str(shell), '-lc', 'export PATH=/mingw64/bin:/usr/bin:$PATH; make -j' + str(a.jobs) + ' JIMMIE_NATIVE_HEAD=1 DISCORD_SDK=0 COOPNET=0 UPDATER=0']
    env = dict(os.environ, MSYSTEM='MINGW64', CHERE_INVOKING='1')
    for key in list(env):
        if key.startswith('JIMMIE_'): env.pop(key)
    for key in ('TMP', 'TEMP', 'TMPDIR'): env[key] = str(out / 'temp')
    print(json.dumps({'build_output': str(out), 'command': command}), flush=True)
    start = time.monotonic()
    with (out / 'build.log').open('wb') as log:
        run = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS, timeout=1800)
    after = {e['path']: sha(personal / e['path']) for e in manifest['protected_personal_files']}
    exe = ROOT / 'build/us_pc/sm64coopdx.exe'
    report = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'command': command,
        'cwd': str(ROOT), 'exit_code': run.returncode, 'seconds': time.monotonic() - start,
        'passed': run.returncode == 0 and before == after, 'protected_unchanged': before == after,
        'before': before, 'after': after, 'no_game_launched': True, 'not_installed': True,
        'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'source_status': subprocess.check_output(['git', 'status', '--short'], cwd=ROOT, text=True).splitlines(),
        'runner_sha256': sha(Path(__file__)), 'executable_sha256': sha(exe) if exe.is_file() else None,
        'limits': 'Build result only; does not prove runtime, ROM-first setup, audio, visual or release acceptance.'}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2), flush=True)
    if run.returncode:
        print('\n'.join((out / 'build.log').read_text(errors='replace').splitlines()[-70:]), flush=True)
    return 0 if report['passed'] else 1

if __name__ == '__main__': raise SystemExit(main())
