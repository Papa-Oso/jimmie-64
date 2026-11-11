"""After building the game, put Jimmie's extra files beside it and check everything is in place.

    python jimmie/setup_jimmie.py          from the top of the repository, after `make`

Copies the title-screen voice clips next to the built game and reports what is ready. It does not
download anything and does not need or touch a ROM: the game asks for yours the first time it runs.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

TOP = Path(__file__).resolve().parents[1]
GAME = TOP / "build/us_pc"


def main() -> int:
    exe = GAME / "sm64coopdx.exe"
    if not exe.is_file():
        print(f"The game is not built yet: {exe} is missing. Build it first (see JIMMIE.md).")
        return 1
    title = GAME / "jimmie-title"
    title.mkdir(exist_ok=True)
    clips = sorted((TOP / "jimmie/title").glob("*.ogg"))
    for clip in clips:
        shutil.copy2(clip, title / clip.name)
    mod = GAME / "mods/jimmie"
    checks = {
        "game program": exe.is_file(),
        "Jimmie mod": (mod / "main.lua").is_file() and (mod / "jimmie_brain_link.lua").is_file(),
        "his recorded clips": len(list((mod / "sound").glob("*.ogg"))) > 0,
        "title voice clips": len(clips) > 0,
        "voiced line pool": (TOP / "jimmie/brain/work/pool/voice.json").is_file(),
    }
    for name, ok in checks.items():
        print(("ready    " if ok else "MISSING  ") + name)
    if all(checks.values()):
        print("\nStart it with:  python jimmie/brain/play.py")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
