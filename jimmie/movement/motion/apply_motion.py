"""Apply Jimmie's accepted movement changes to a game's mods/jimmie folder. Standard library only.

  python apply_motion.py --mod <mods/jimmie folder>            apply every change not already there
  python apply_motion.py --mod <folder> --backup <folder>      first copy the files it will change
  python apply_motion.py --mod <folder> --skip coast,dust      leave some out (for before/after tests)
  python apply_motion.py --mod <folder> --include-pending       also apply changes still waiting for approval
  python apply_motion.py --list                                names and one-line descriptions

brain/tools/build_game.py calls this after its own edits, so a rebuild keeps the changes.
Safe to run twice: a change whose marker text is already in the mod is skipped.
Every replacement must match exactly once; otherwise nothing is written and it says which one failed.
A change may instead replace whole files (the model files in actors/); those are copied after the text edits succeed.
The changes themselves are in changes.py (and the ollie's in ../ollie-candidate/apply_windup.py).
"""
from pathlib import Path
import argparse, shutil, sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / 'ollie-candidate'))
import changes  # noqa: E402


def load(mod, cache, name):
    if name not in cache:
        raw = (mod / name).read_bytes()
        cache[name] = [raw.decode('utf-8').replace('\r\n', '\n'), b'\r\n' in raw, False]
    return cache[name]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mod', type=Path); ap.add_argument('--backup', type=Path)
    ap.add_argument('--skip', default=''); ap.add_argument('--list', action='store_true')
    ap.add_argument('--include-pending', action='store_true')
    a = ap.parse_args()
    if a.list:
        for c in changes.CHANGES: print(f"{c['name']:12} {'PENDING ' if c.get('pending') else ''}{c['what']}")
        return 0
    mod = a.mod.resolve(); skip = {s for s in a.skip.split(',') if s}
    assert (mod / 'main.lua').is_file(), f'not a jimmie mod folder: {mod}'
    cache, done, had, copies = {}, [], [], []
    for c in changes.CHANGES:
        if c.get('files'):
            # A change that replaces whole files (model files). It is "already there" when every file matches byte for byte.
            same = all((mod / rel).is_file() and (mod / rel).read_bytes() == Path(src).read_bytes() for rel, src in c['files'].items())
            if same: had.append(c['name']); continue
            if c['name'] in skip or (c.get('pending') and not a.include_pending): continue
            copies += list(c['files'].items()); done.append(c['name']); continue
        file, text = c['marker']
        if text in load(mod, cache, file)[0]: had.append(c['name']); continue
        if c['name'] in skip or (c.get('pending') and not a.include_pending): continue
        for name, edits in c['edits'].items():
            entry = load(mod, cache, name)
            for old, new in edits:
                if entry[0].count(old) != 1:
                    raise SystemExit(f"{c['name']}: {name}: expected exactly one match, found {entry[0].count(old)}, for:\n{old}\nNothing was written.")
                entry[0] = entry[0].replace(old, new); entry[2] = True
        assert text in load(mod, cache, file)[0], f"{c['name']}: marker missing after its own edits"
        done.append(c['name'])
    changed = [n for n, e in cache.items() if e[2]]
    if a.backup and changed:
        a.backup.mkdir(parents=True, exist_ok=True)
        for n in changed: shutil.copy2(mod / n, a.backup / n)
    for n in changed:
        text, crlf, _ = cache[n]
        (mod / n).write_bytes((text.replace('\n', '\r\n') if crlf else text).encode('utf-8'))
    for rel, src in copies:
        dest = mod / rel
        if a.backup and dest.is_file():
            (a.backup / rel).parent.mkdir(parents=True, exist_ok=True); shutil.copy2(dest, a.backup / rel)
        dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dest)
    print('motion changes applied:', ', '.join(done) or 'none', '| already there:', ', '.join(had) or 'none',
          '| files written:', ', '.join(changed + [rel for rel, _ in copies]) or 'none')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
