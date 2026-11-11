"""Write, edit, voice and score a fresh batch of Jimmie's lines. Run it with the game closed.

    python bake_all.py            add a batch to the pool (about an hour on a 12 GB card)
    python bake_all.py --seed 7   a different batch; each run adds lines, none are repeated

The writer model and the voice do not fit on the GPU together, so they take turns: the model
writes and edits, is shut down, then the voice records and a speech recogniser checks each take.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import play

HERE = Path(__file__).resolve().parent


def run(args: list[str]) -> None:
    env = dict(os.environ, TORCHINDUCTOR_CACHE_DIR=str(HERE / "work/torch-cache"), PYTHONIOENCODING="utf-8")
    code = subprocess.run([str(play.PYTHON), "-B", "-m", "jimmie_brain.bake", *args], cwd=HERE, env=env).returncode
    if code:
        raise SystemExit(f"bake step failed: {args[0]}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--rounds", type=int, default=4)
    p.add_argument("--voice-only", action="store_true", help="skip writing; voice whatever is not voiced yet")
    p.add_argument("--batch", type=int, default=4, help="lines voiced at once; use 1 for long lines")
    a = p.parse_args()
    cfg = play.settings()
    (HERE / "work/pool").mkdir(parents=True, exist_ok=True)
    if not a.voice_only:
        print("Starting the writer model...", flush=True)
        llm = play.start_llm(cfg, HERE / "work/pool")
        url = f"http://127.0.0.1:{cfg['llm_port']}"
        try:
            run(["write", "--llm", url, "--turns", cfg["turns"], "--seed", str(a.seed), "--rounds", str(a.rounds)])
            run(["judge", "--llm", url, "--seed", str(a.seed)])
        finally:
            if llm and llm.poll() is None:
                llm.terminate()
                llm.wait(timeout=20)
    listener = cfg.get("listener")
    run(["voice", "--voice-model", cfg["voice_model"], "--voice-reference", cfg["voice_reference"], "--ffmpeg", cfg["ffmpeg"],
         "--batch", str(a.batch), *(["--listener", listener] if listener else [])])
    run(["report", "--turns", cfg["turns"]])
    return 0


if __name__ == "__main__":
    sys.exit(main())
