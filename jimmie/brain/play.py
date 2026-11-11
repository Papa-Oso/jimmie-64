"""Start Jimmie 64 with the brain: the model server, the brain process and the game, together.

    python play.py                 play, from the pool of lines written and voiced ahead (bake.cmd makes it)
    python play.py --live          play with the writer and the voice running live instead (needs the GPU to itself)
    python play.py --smoke 60      automated: boot straight into the castle grounds, no sound device,
                                   run for N seconds, then print what the game and the brain reported
    python play.py --no-brain      the build alone (it then behaves like its parent)

Everything it writes stays in this folder: profile/ (its own save), sessions/, work/.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import mmap
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent           # the jimmie-64 folder this brain lives in
REPOS = PROJECT.parent          # its neighbours: .tmp-ai-models, twitch-vod-transcribe
GAME = HERE / "build/game"
PROFILE = HERE / "profile"
if os.environ.get("JIMMIE_PLAY_PROFILE"):          # timing tests keep their own save and settings
    PROFILE = Path(os.environ["JIMMIE_PLAY_PROFILE"])
ROM = PROJECT / "main/user/save/baserom.us.z64"
CONFIG = PROJECT / "main/user/save/sm64config.txt"
PYTHON = PROJECT / ".venv/Scripts/python.exe"
SETTINGS = HERE / "settings.json"
CAPTURE = REPOS / ".tmp-ai-models/native-star-stage-r1/process_audio.exe"   # records one process's audio output
DEFAULTS = {
    "llama_server": str(REPOS / ".tmp-ai-models/llama-b12211/llama-server.exe"),
    "model": str(REPOS / ".tmp-ai-models/gemma-4-12b/gemma-4-12b-it-qat-q4_0.gguf"),
    "llm_port": 8771, "llm_context": 4096, "llm_gpu_layers": 99,
    "voice": "qwen",
    "voice_model": str(PROJECT / "models/Qwen3-TTS-12Hz-1.7B-Base"),
    "voice_reference": str(PROJECT / "voice_tests/ref_short.json"),
    "ffmpeg": str(REPOS / "twitch-vod-transcribe/tools/ffmpeg.exe"),
    "turns": str(HERE / "work/turns.jsonl"),
    "listener": str(PROJECT / "models/hub/models--openai--whisper-large-v3-turbo/snapshots/41f01f3fe87f28c78e2fbf8b568835947dd65ed9"),
}


def settings() -> dict:
    out = dict(DEFAULTS)
    if SETTINGS.is_file():
        out.update(json.loads(SETTINGS.read_text(encoding="utf-8")))
    return out


# settings.json may say where things are when this folder sits somewhere else (for example inside
# the game's own source tree): "game" (the folder holding sm64coopdx.exe), "rom", "config", "python".
_where = settings()
GAME = (HERE / _where["game"]).resolve() if _where.get("game") else GAME
ROM = (HERE / _where["rom"]).resolve() if _where.get("rom") else ROM
CONFIG = (HERE / _where["config"]).resolve() if _where.get("config") else CONFIG
PYTHON = (HERE / _where["python"]).resolve() if _where.get("python") else PYTHON
if not PYTHON.is_file():
    PYTHON = Path(sys.executable)


class Channel:
    """The shared-memory page the engine checks to enable the route companion. Nothing answers on it here."""

    def __init__(self):
        self.name = uuid.uuid4().hex
        self.mapping = mmap.mmap(-1, 4096, tagname="Local\\Jimmie64RouteV1_" + self.name, access=mmap.ACCESS_WRITE)

    def close(self):
        self.mapping.close()


SAVE = "save"            # the folder inside profile/ that holds the save, settings and ROM


def new_run() -> None:
    """A fresh attempt: an empty save in its own folder, so the normal save is never touched.

    The run folder keeps its own best time and run records; the ROM and settings are copied from
    the normal folder the first time. Only the run folder's save file is removed."""
    global SAVE
    normal, run = PROFILE / "save", PROFILE / "run"
    run.mkdir(parents=True, exist_ok=True)
    for name in ("baserom.us.z64", "sm64config.txt"):
        if not (run / name).exists() and (normal / name).is_file():
            shutil.copy2(normal / name, run / name)
    for name in ("sm64_save_file.bin", "sm64_save_file.bin.bak"):
        (run / name).unlink(missing_ok=True)
    SAVE = "run"


def setup_profile() -> None:
    for name in ("save", "temp", "appdata", "localappdata"):
        (PROFILE / name).mkdir(parents=True, exist_ok=True)
    # With no ROM to copy, the game shows its own first-run screen and asks the player for theirs.
    if not (PROFILE / SAVE / "baserom.us.z64").exists() and ROM.is_file():
        shutil.copy2(ROM, PROFILE / SAVE / "baserom.us.z64")
    if not (PROFILE / SAVE / "sm64config.txt").exists() and CONFIG.is_file():
        shutil.copy2(CONFIG, PROFILE / SAVE / "sm64config.txt")


def llm_up(port: int) -> bool:
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{port}/health", timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False


def start_llm(cfg: dict, session: Path):
    if llm_up(cfg["llm_port"]):
        return None
    args = [cfg["llama_server"], "-m", cfg["model"], "-c", str(cfg["llm_context"]), "-ngl", str(cfg["llm_gpu_layers"]),
            "--port", str(cfg["llm_port"]), "--host", "127.0.0.1", "-rea", "off"]
    log = (session / "llm.log").open("wb")
    proc = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline and proc.poll() is None and not llm_up(cfg["llm_port"]):
        time.sleep(0.5)
    if not llm_up(cfg["llm_port"]):
        proc.kill()
        raise SystemExit("the model server did not start; see " + str(session / "llm.log"))
    return proc


def start_brain(cfg: dict, session: Path, llm: str | None, voice: str):
    env = dict(os.environ, TORCHINDUCTOR_CACHE_DIR=str(HERE / "work/torch-cache"), PYTHONIOENCODING="utf-8")
    args = [str(PYTHON), "-B", "-m", "jimmie_brain", "run", str(session / "stdout.log"), str(PROFILE / SAVE / "sav"),
            "--journal", str(session / "brain.jsonl")]
    if llm is None:
        args += ["--pool", str(HERE / "work/pool")]
    else:
        args += ["--turns", cfg["turns"], "--llm", llm, "--voice", voice, "--voice-model", cfg["voice_model"],
                 "--voice-reference", cfg["voice_reference"], "--ffmpeg", cfg["ffmpeg"],
                 "--cache", str(HERE / "work/voice-cache")]
    log = (session / "brain.log").open("wb")
    return subprocess.Popen(args, cwd=HERE, env=env, stdout=log, stderr=subprocess.STDOUT,
                            creationflags=subprocess.CREATE_NO_WINDOW)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--smoke", type=int, metavar="SECONDS")
    p.add_argument("--no-brain", action="store_true")
    p.add_argument("--live", action="store_true", help="write and voice lines during play instead of using the pool")
    p.add_argument("--sound", action="store_true", help="with --smoke: play through the real sound device")
    p.add_argument("--capture", action="store_true",
                   help="record the game's own audio output (up to 125 s) so tools/measure_latency.py can time each line")
    p.add_argument("--llm", help="'scripted' for stand-in lines, or a server URL; default starts the local model")
    p.add_argument("--voice", choices=("qwen", "null"))
    p.add_argument("--new-run", action="store_true",
                   help="start a 16-star attempt on an empty save kept apart from your normal save")
    p.add_argument("--run-test", action="store_true",
                   help="with --smoke: let the automated start be timed as a run (uses a separate test record)")
    a = p.parse_args()
    cfg = settings()
    if not (GAME / "sm64coopdx.exe").is_file():
        raise SystemExit(f"The game was not found in {GAME}. Build it first (see the setup notes).")
    if subprocess.run(["tasklist", "/FI", "IMAGENAME eq sm64coopdx.exe"], capture_output=True, text=True).stdout.count("sm64coopdx.exe"):
        raise SystemExit("A game is already open. Close it first.")
    if a.new_run:
        new_run()
    setup_profile()
    session = HERE / "sessions" / datetime.now().strftime("%Y%m%d-%H%M%S")
    session.mkdir(parents=True)
    (session / "stdout.log").write_bytes(b"")
    channel = Channel()
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("JIMMIE_", "SDL_"))}
    env.update(APPDATA=str(PROFILE / "appdata"), LOCALAPPDATA=str(PROFILE / "localappdata"), TEMP=str(PROFILE / "temp"),
               TMP=str(PROFILE / "temp"), JIMMIE_NATIVE_HEAD="1", SDL_JOYSTICK_RAWINPUT="0",
               JIMMIE_ROUTE_CHANNEL=channel.name, JIMMIE_HEAD_TRACE=str(session / "native.jsonl"))
    args = [str(GAME / "sm64coopdx.exe"), "--server", "58468", "--playercount", "1", "--windowed", "--skip-update-check",
            "--no-discord", "--disable-mods", "--enable-mod", "jimmie", "--console", "--savepath", str(PROFILE / SAVE)]
    for extra in os.environ.get("JIMMIE_PLAY_EXTRA_MODS", "").split(","):   # timing tests add the input-tape mod
        if extra:
            args += ["--enable-mod", extra]
    if a.smoke:
        env.update(JIMMIE_HEAD_TEST_START="1")
        if a.run_test:
            env.update(JIMMIE_RUN_TEST="1")
        if not a.sound:
            env["SDL_AUDIODRIVER"] = "dummy"
        args += ["--backend", "opengl", "--skip-intro", "--hide-loading-screen"]
    llm_proc = brain = None
    try:
        if not a.no_brain:
            llm = a.llm
            if not (a.live or llm):
                if not (HERE / "work/pool/voice.json").is_file():
                    raise SystemExit("No lines have been written and voiced yet. Run bake.cmd first (about an hour, once).")
            elif not llm:
                print("Starting the model...", flush=True)
                llm_proc = start_llm(cfg, session)
                llm = f"http://127.0.0.1:{cfg['llm_port']}"
            print("Starting Jimmie's brain...", flush=True)
            brain = start_brain(cfg, session, llm, a.voice or cfg["voice"])
            deadline = time.monotonic() + 240
            while time.monotonic() < deadline and brain.poll() is None:
                if b"[jimmie-brain] ready" in (session / "brain.log").read_bytes():
                    break
                time.sleep(0.5)
            if brain.poll() is not None:
                raise SystemExit("the brain stopped while starting; see " + str(session / "brain.log"))
        print("Starting the game. Session folder:", session, flush=True)
        with (session / "stdout.log").open("ab") as out, (session / "stderr.log").open("wb") as err:
            game = subprocess.Popen(args, cwd=GAME, env=env, stdout=out, stderr=err)
            capture = None
            if a.capture:
                capture = subprocess.Popen([str(CAPTURE), str(game.pid)], cwd=session, stdout=(session / "capture.log").open("wb"),
                                           stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                if a.smoke:
                    try:
                        game.wait(timeout=a.smoke)
                    except subprocess.TimeoutExpired:
                        pass
                else:
                    game.wait()
            finally:
                if capture:
                    (session / "stop-loopback").touch()
                    try:
                        capture.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        capture.kill()
                if game.poll() is None:
                    game.terminate()
                    try:
                        game.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        game.kill()
    finally:
        for proc in (brain, llm_proc):
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        channel.close()
    if a.smoke:
        log = (session / "stdout.log").read_text(encoding="utf-8", errors="replace").splitlines()
        jb = [l for l in log if "[jb]" in l]
        print(json.dumps({"session": str(session), "log_lines": len(log), "jb_lines": len(jb),
                          "lua_errors": [l for l in log if "error" in l.lower()][:10]}, indent=1))
        for l in jb[:60]:
            print(l[:220])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
