"""Guarded private native title music/chatter smoke. Default is a read-only plan.
Adapted from tools/run_jimmie_head_smoke.py; only --execute launches a game.
"""
from pathlib import Path
import argparse, csv, ctypes, datetime, hashlib, importlib.util, json, os
import shutil, subprocess, time
from ctypes import wintypes

BUILD = Path(__file__).resolve().parents[1]
STAGE = BUILD.parent
PROJECT = STAGE.parents[1]
ACCEPTED = PROJECT / "docs/title-face-repair-20261107/native-build"
BINARY = BUILD / "build/us_pc/sm64coopdx.exe"
BUNDLE = STAGE / "private-title-assets/jimmie-title"
ASSETS = {
    "rainbow_road.ogg": "b9e418704301365f3ce5776f679cfbc5c874e21241d726e69fae3325d512f5f4",
    "title_good_morning_01.ogg": "615d531863f1ec063ab1a5b72f2698a659bc9336f683bd9b9ca13f1f7b42d8eb",
    "title_good_morning_02.ogg": "ec08ee24b1cb057080058702df06368d41bcc27db9676ec63d7f6046e7de6846",
    "title_good_morning_03.ogg": "c2dff5a3ebdaeae90fee01f7a6a208880db0805f866c69bd884e69a221061933",
    "title_whats_happening.ogg": "228db49f79d8e5d3dfecdd3f4f0ce2fddac0154ce55648905f52f10e34baa67d",
    "title_pink_bitch_insurance.ogg": "4298bf9baaf1de1853bff85d54490db11d2cb0e5f2f45fd4a96282bdeff5b303",
}
CONFIG = """master_volume 0
music_volume 0
sfx_volume 0
env_volume 0
mute_focus_loss false
fullscreen false
amount_of_players 1
bubble_death false
skip_intro false
pause_anywhere false
"""
def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def protected():
    files = [PROJECT / "native-launch-manifest.json",
             PROJECT / "coopdx/sm64coopdx/sm64coopdx.exe",
             PROJECT / "launch_jimmie.cmd", PROJECT / "start_jimmie.cmd"]
    files += sorted((PROJECT / "coopdx/save").rglob("*"))
    return {str(p.relative_to(PROJECT)): sha(p) for p in files if p.is_file()}

def copy_verified(src, dst, manifest):
    if src.is_symlink():
        raise RuntimeError(f"Refusing symlink input: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    expected = sha(src)
    shutil.copy2(src, dst)
    if sha(dst) != expected:
        raise RuntimeError(f"Copy mismatch: {src}")
    manifest[str(dst)] = {"source": str(src), "sha256": expected}

def copy_tree(src, dst, manifest):
    if not src.is_dir():
        return
    for p in sorted(src.rglob("*")):
        if p.is_file():
            copy_verified(p, dst / p.relative_to(src), manifest)

def source_head_check():
    paths = list((ACCEPTED / "src/goddard").rglob("*"))
    paths += [ACCEPTED / "src/pc/gfx/gfx_pc.c"]
    result = {}
    for old in paths:
        if old.is_file():
            rel = old.relative_to(ACCEPTED)
            candidate = BUILD / rel
            if not candidate.is_file() or sha(old) != sha(candidate):
                raise RuntimeError(f"Accepted native-head source changed: {rel}")
            result[str(rel)] = sha(candidate)
    return result

def own_window_close(pid):
    """Post WM_CLOSE only to top-level windows proven to belong to this child."""
    user = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowThreadProcessId.restype = wintypes.DWORD
    user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user.PostMessageW.restype = wintypes.BOOL
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user.EnumWindows.restype = wintypes.BOOL
    targets = []
    @callback_type
    def visit(hwnd, unused):
        actual = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(actual))
        if actual.value == pid:
            targets.append(int(hwnd))
        return True
    if not user.EnumWindows(visit, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    sent = []
    for hwnd in targets:
        actual = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(actual))
        if actual.value == pid and user.PostMessageW(hwnd, 0x0010, 0, 0):
            sent.append(hwnd)
    return sent

def inspect_trace(run, fallback, clean_exit, forced, unchanged, head):
    trace = run / "rig.jsonl"
    rows = []
    malformed = []
    if trace.exists():
        for n, line in enumerate(trace.read_text().splitlines(), 1):
            try: rows.append(json.loads(line))
            except json.JSONDecodeError: malformed.append(n)
    names = [row.get("event") for row in rows]
    frames = [row for row in rows if row.get("event") == "frame"]
    event_counts = {name: names.count(name) for name in sorted(set(names)) if isinstance(name, str)}
    errs = (run / "stderr.log").read_text(errors="replace")
    checks = {
        "clean_exit_zero": clean_exit,
        "not_forced": not forced,
        "protected_files_unchanged": unchanged,
        "accepted_head_source_unchanged": bool(head),
        "trace_complete": bool(rows) and not malformed,
        "all_native_head_drivers_bound": bool(frames) and all(r.get("bound") == 15 for r in frames),
        "greeting_started": names.count("title_greeting_started") == 1,
        "no_native_crash_report": "Exception occurred" not in errs,
    }
    if fallback:
        checks.update(missing_track_fallback=names.count("title_music_load_failed") == 1,
                      no_custom_music_started="title_music_started" not in names)
    else:
        checks.update(one_music_start=names.count("title_music_started") == 1,
                      two_chatter_starts=names.count("title_chatter_started") == 2,
                      no_chatter_failure=not any(n in names for n in ("title_chatter_load_failed", "title_chatter_play_failed")),
                      synthetic_start_observed="test_start_pressed" in names,
                      handed_to_menu="title_handed_to_menu" in names,
                      music_stop_observed=names.count("title_music_stopped") == 1)
        if "title_handed_to_menu" in names:
            tail = names[names.index("title_handed_to_menu") + 1:]
            checks["no_title_sound_restart_after_handoff"] = not any(n in tail for n in
                ("title_greeting_started", "title_chatter_started", "title_music_started"))
        interactions = [r for r in rows if r.get("event") == "interaction"]
        passed_handles = 0
        for target in range(7):
            phases = {r["phase"]: r for r in interactions if r.get("target") == target}
            if set(phases) != {13, 15, 21, 69}: continue
            drag, hold_start, hold, release = [phases[x] for x in (13, 15, 21, 69)]
            axes = ("dx", "dy", "dz")
            if (bool(drag["picked"]) and sum(abs(drag[k]) for k in axes) > 1
                and max(abs(hold_start[k] - hold[k]) for k in axes) < .05
                and max(abs(release[k]) for k in axes) < .05):
                passed_handles += 1
        checks["seven_native_handles_passed"] = passed_handles == 7
    return {"checks": checks, "passed": all(checks.values()), "event_counts": event_counts,
            "malformed_trace_lines": malformed, "trace": rows}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--expect-sha256")
    parser.add_argument("--missing-track", action="store_true")
    parser.add_argument("--seconds", type=int)
    parser.add_argument("--no-capture", action="store_true")
    args = parser.parse_args()
    seconds = args.seconds if args.seconds is not None else (8 if args.missing_track else 49)
    if args.missing_track:
        if not 6 <= seconds <= 12: parser.error("Fallback is only a 6..12-second startup check.")
    elif not 47 <= seconds <= 60:
        parser.error("Combined interaction/Start check must be 47..60 seconds.")
    if not args.execute:
        print(json.dumps({"mode":"plan_only_no_writes_or_launch","candidate":str(BINARY),
            "assets":str(BUNDLE),"seconds":seconds,"missing_track":args.missing_track,
            "private_config":CONFIG,"full_engine_audio":"muted; not claimed device-less",
            "hooks":"Existing JIMMIE_HEAD_TEST_INTERACTION + START at frame1250; fallback uses neither",
            "required_before_execution":"Explicit final expected executable SHA256 and coordinator approval"},indent=2))
        return 0
    if os.name != "nt": parser.error("This runner is Windows-only.")
    if not args.expect_sha256 or len(args.expect_sha256) != 64:
        parser.error("--execute requires the final --expect-sha256.")
    if not BINARY.is_file() or sha(BINARY) != args.expect_sha256.lower():
        raise RuntimeError("Candidate missing or does not match the explicitly supplied executable hash.")
    spec = importlib.util.spec_from_file_location("title_smoke_launch_guard", PROJECT / "ai/launch_jimmie.py")
    guards = importlib.util.module_from_spec(spec);spec.loader.exec_module(guards)
    with guards.LaunchLock():
        if guards.running_game_pids():
            raise RuntimeError("Game active; nothing started. Never terminate another game.")
        head = source_head_check()
        before = protected()
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        run = BUILD / "build/title-audio-smoke" / stamp
        run.mkdir(parents=True, exist_ok=False)
        runtime = run / "runtime";runtime.mkdir()
        save = run / "save";save.mkdir()
        appdata = run / "appdata";appdata.mkdir()
        localappdata = run / "localappdata";localappdata.mkdir()
        frames = run / "frames";frames.mkdir()
        copied = {}
        copy_verified(BINARY, runtime / BINARY.name, copied)
        rom = BINARY.parent / "baserom.us.z64"
        if not rom.is_file(): raise RuntimeError("Candidate's existing local US ROM is required; no download or live fallback.")
        copy_verified(rom, runtime / rom.name, copied)
        for name in ("sm64coopdx.exe.dd64",):
            source = BINARY.parent / name
            if source.is_file(): copy_verified(source, runtime / name, copied)
        for dll in sorted(BINARY.parent.glob("*.dll")):
            copy_verified(dll, runtime / dll.name, copied)
        for directory in ("dynos", "lang", "palettes", "res"):
            copy_tree(BINARY.parent / directory, runtime / directory, copied)
        for name, expected in ASSETS.items():
            src = BUNDLE / name
            if sha(src) != expected: raise RuntimeError(f"Native title asset hash changed: {name}")
            if args.missing_track and name == "rainbow_road.ogg": continue
            copy_verified(src, runtime / "jimmie-title" / name, copied)
        # These settings are authored for the private test. No user save/config is copied.
        (run / "private-config-template.txt").write_text(CONFIG)
        copy_verified(run / "private-config-template.txt", save / "sm64config.txt", copied)
        (run / "copy-manifest.json").write_text(json.dumps(copied, indent=2) + "\n")
        (run / "protected-before.json").write_text(json.dumps(before, indent=2) + "\n")
        env = {k:v for k,v in os.environ.items() if not k.startswith("JIMMIE_")}
        env.update(APPDATA=str(appdata), LOCALAPPDATA=str(localappdata),
                   SDL_VIDEO_WINDOW_POS="-20000,-20000", SDL_JOYSTICK_RAWINPUT="0",
                   SDL_AUDIODRIVER="dummy", JIMMIE_NATIVE_HEAD="1", JIMMIE_HEAD_TRACE=str(run / "rig.jsonl"))
        if not args.missing_track:
            env.update(JIMMIE_HEAD_TEST_START="1", JIMMIE_HEAD_TEST_INTERACTION="1")
        if not args.no_capture: env["JIMMIE_HEAD_FRAMES"] = str(frames)
        command = [str(runtime / BINARY.name), "--console", "--hide-loading-screen",
                   "--windowed", "--width", "960", "--height", "720", "--backend", "opengl",
                   "--skip-update-check", "--no-discord", "--disable-mods", "--savepath", str(save)]
        # Recheck immediately before launch, while the production mutex is still held.
        if guards.running_game_pids(): raise RuntimeError("Game appeared during staging; no launch.")
        if sha(BINARY) != args.expect_sha256.lower():
            raise RuntimeError("Build changed during staging; no launch.")
        forced = False; closed_windows = []; child = None; close_error = None
        start = time.monotonic()
        try:
            with (run / "stdout.log").open("w") as out, (run / "stderr.log").open("w") as err:
                child = subprocess.Popen(command, cwd=runtime, env=env, stdout=out, stderr=err,
                                         creationflags=subprocess.CREATE_NO_WINDOW)
                print(json.dumps({"pid":child.pid,"run":str(run)}),flush=True)
                try: child.wait(timeout=seconds)
                except subprocess.TimeoutExpired:
                    try: closed_windows = own_window_close(child.pid)
                    except Exception as exc: close_error = str(exc)
                    try: child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        forced = True;child.terminate();child.wait(timeout=10)
        finally:
            if child is not None and child.poll() is None:
                forced = True;child.terminate();child.wait(timeout=10)
        code = child.returncode if child else None
        after = protected()
        unchanged = before == after
        (run / "protected-after.json").write_text(json.dumps(after, indent=2) + "\n")
        report = inspect_trace(run, args.missing_track, code == 0, forced, unchanged, head)
        captures = []
        if not args.no_capture:
            from PIL import Image
            for ppm in sorted(frames.glob("*.ppm")):
                with Image.open(ppm) as image: image.save(ppm.with_suffix(".png"))
            captures = [str(p.relative_to(run)) for p in sorted(frames.glob("*.png"))]
        report.update(executable_sha256=args.expect_sha256.lower(), run=str(run), args=command,
                      seconds=time.monotonic()-start, requested_seconds=seconds,
                      missing_track=args.missing_track, exit_code=code, forced_termination=forced,
                      wm_close_windows=closed_windows, close_error=close_error,
                      accepted_head_source_hashes=head, framebuffer_files=captures,
                      limits="Muted private native launch; miniaudio may open its normal device. No audible/listening approval. Existing synthetic handle and Start inputs are not a physical controller. No user save/config is copied or used as runtime input. Short run does not reach the music loop endpoint; looping has separate decoder evidence. Trace reports playback starts, not acoustic output.",
                      original_runner="title-face-repair-20261107/native-build/tools/run_jimmie_head_smoke.py")
        (run / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({k:v for k,v in report.items() if k not in ("trace","accepted_head_source_hashes","args")},indent=2))
        return 0 if report["passed"] else 1

if __name__ == "__main__":
    raise SystemExit(main())

