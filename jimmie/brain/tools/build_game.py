"""Make the brain build: a private copy of the current personality build with the brain link wired in.

    python tools/build_game.py

Reads the parent build, never writes to it. The result is build/game, replaced whole each time.
With no brain process running the copy behaves like its parent; while one runs, Jimmie's speech
comes from the brain only.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
PROJECT = HERE.parent           # the jimmie-64 folder this brain lives in
REPOS = PROJECT.parent          # its neighbours, such as .tmp-ai-models
PARENT = REPOS / ".tmp-ai-models/personality-owner-drops-candidate-20261109-r1/game"
MAIN_SOUNDS = PROJECT / "main/game/mods/jimmie/sound"
OUT = HERE / "build/game"
MOD = "mods/jimmie/"
MOTION = PROJECT / "docs/movement-review-20261109/motion/apply_motion.py"

EDITS = {
    # Jimmie's own skate outcomes reach the brain from the place that already witnesses them.
    "main.lua": [
        ('    print("[jimmie-skate-memory] "..Personality.json(fact))\n',
         '    print("[jimmie-skate-memory] "..Personality.json(fact))\n'
         '    if JIMMIE_BRAIN then JIMMIE_BRAIN.skate(fact) end\n'),
        ('    if bit then\n        VOICE.post(bit.event,{cats={bit.category}',
         '    if sound==29 and m.playerIndex==0 and JIMMIE_BRAIN and JIMMIE_BRAIN.live() then\n'
         '        JIMMIE_BRAIN.fact("mario_voice","mario",{cue="mamma_mia"})\n    end\n'
         '    if bit then\n        VOICE.post(bit.event,{cats={bit.category}'),
    ],
    # One mouth: while the brain is feeding plans the old canned barks stand down.
    "voice.lua": [
        ('local function submit(item, allowQueue)\n    if V.now == nil or V.play == nil then return false end\n',
         'local function submit(item, allowQueue)\n    if V.now == nil or V.play == nil then return false end\n'
         '    if JIMMIE_BRAIN and JIMMIE_BRAIN.live() then return false end\n'),
    ],
    "route_companion16.lua": [
        ('        log(kind,data)\n        append(history,',
         '        log(kind,data)\n        if JIMMIE_BRAIN then JIMMIE_BRAIN.route(kind) end\n        append(history,'),
    ],
    # The moment he commits to a spot is the moment he can call his shot.
    "skate_director.lua": [
        ('function D:enter(state, reason)\n',
         'function D:enter(state, reason)\n'
         '    if state == "setup" and self.state ~= "setup" and JIMMIE_BRAIN then pcall(JIMMIE_BRAIN.approach) end\n'),
    ],
}


def patched(raw: bytes, edits) -> bytes:
    newline = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8").replace("\r\n", "\n")
    for old, new in edits:
        if text.count(old) != 1:
            raise SystemExit(f"anchor not found exactly once: {old[:70]!r}")
        text = text.replace(old, new)
    return text.replace("\n", newline).encode("utf-8")


def main() -> int:
    if not PARENT.is_dir():
        raise SystemExit(f"parent build missing: {PARENT}")
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(PARENT, OUT)
    # The game program built from the fork (jimmie-64-fork) carries the side-part start-menu head and
    # the stock title music. Use it when it has been built; the parent's program is the fallback.
    fork_exe = REPOS / "jimmie-64-fork/build/us_pc/sm64coopdx.exe"
    if fork_exe.is_file():
        shutil.copy2(fork_exe, OUT / "sm64coopdx.exe")
    mod = OUT / MOD
    for name, edits in EDITS.items():
        (mod / name).write_bytes(patched((mod / name).read_bytes(), edits))
    install = (HERE / "lua/install_brain.lua").read_text(encoding="utf-8")
    main_lua = mod / "main.lua"
    main_lua.write_bytes(main_lua.read_bytes().rstrip() + b"\n\n;(function()\n" + install.encode("utf-8") + b"\nend)()\n")
    shutil.copy2(HERE / "lua/jimmie_brain_link.lua", mod / "jimmie_brain_link.lua")
    shutil.copy2(HERE / "lua/jimmie_run_tells.lua", mod / "jimmie_run_tells.lua")
    shutil.copy2(HERE / "lua/jimmie_dialogs.lua", mod / "jimmie_dialogs.lua")
    shutil.copy2(HERE / "lua/jimmie_run_splits.lua", mod / "jimmie_run_splits.lua")
    shutil.copy2(HERE / "lua/jimmie_dialog_variants.lua", mod / "jimmie_dialog_variants.lua")

    # The title screen plays the game's own title music. The parent build carries a recording of
    # music from another game; without the file the engine falls back to the normal sequence
    # (src/menu/jimmie_title_audio.c). Owner decision 2026-11-10; see docs/BUILD_ORIGIN_CHECK.md.
    (OUT / "jimmie-title/rainbow_road.ogg").unlink(missing_ok=True)

    # Jimmie's movement changes (wind-ups, ollie, rail hops). Owned by the movement review; each change
    # is listed in docs/movement-review-20261109/motion/changes.py. Stops the build if one no longer fits.
    subprocess.run([sys.executable, str(MOTION), "--mod", str(mod)], check=True)

    # Recordings the bank names: use the build's own, else the installed game's copy.
    bank = json.loads((HERE / "jimmie_brain/data/bank.json").read_text(encoding="utf-8"))
    veto = {f.lower() for f in json.loads((HERE / "jimmie_brain/data/veto.json").read_text(encoding="utf-8")).get("files", [])}
    wanted = [t.get("file") for t in bank["takes"].values()] + [f.get("file") for b in bank["bits"].values() for f in b["forms"]]
    missing = []
    for name in sorted({w for w in wanted if w}):
        if name.lower() in veto:
            raise SystemExit(f"bank names a vetoed file: {name}")
        if (mod / "sound" / name).is_file():
            continue
        if (MAIN_SOUNDS / name).is_file():
            shutil.copy2(MAIN_SOUNDS / name, mod / "sound" / name)
        else:
            missing.append(name)
    print(json.dumps({"built": str(OUT), "missing_bank_audio": missing}, indent=1))
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
