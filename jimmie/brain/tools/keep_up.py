"""Keep Jimmie up with the stream, unattended.

    python tools/keep_up.py            do everything
    python tools/keep_up.py --dry      show what it would add from streams already transcribed; change nothing
    python tools/keep_up.py --no-fetch skip looking for new streams (use what is already transcribed)

One run:
  1. asks the transcriber (../../twitch-vod-transcribe) for streams it has not done and transcribes them;
  2. rebuilds work/turns.jsonl from all transcripts;
  3. takes sentences from streams this routine has not mined before, drops anything that names a
     person, talks to chat, is about the stream itself, or breaks an owner veto;
  4. has the local writer model, acting as an editor, keep only lines that make sense said out loud
     beside Mario with no other context, and pick up to --add of them;
  5. adds those to data/real_lines.json marked "auto" with the date, at half the usual weight;
  6. voices them, runs the tests, and puts real_lines.json back if a test fails;
  7. appends what it did to docs/KEEPUP_LOG.md.

It refuses to start while the game is open, because transcribing and voicing use the graphics card.
Lines it adds are his words; nobody has read them. Remove any you dislike from real_lines.json, or
add the wording to data/veto.json so it never comes back.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import play  # noqa: E402
from jimmie_brain.writer import ChatLLM, Veto  # noqa: E402

REPOS = HERE.parent.parent
TRANSCRIBER = REPOS / "twitch-vod-transcribe"
REAL = HERE / "jimmie_brain/data/real_lines.json"
STATE = HERE / "work/keepup_state.json"
LOG = HERE / "docs/KEEPUP_LOG.md"
PORT = 8774

# Not about the stream, chat, other people, records or anything crude enough to need a person's eye.
BAD = re.compile(r"\b(chat|stream\w*|sub|subs|follow\w*|donat\w*|bits|raid|mod|mods|discord|twitch|youtube|clip|clips|guys|"
                 r"viewer\w*|gift\w*|prime|emote\w*|tts|song|playlist|ad|ads|dono|thank|thanks|welcome|y'all|live|video|"
                 r"videos|run|runs|pb|record|split|splits|timer|pace|speedrun\w*|tonight|tomorrow|today|yesterday|he|she|"
                 r"his|her|him|he's|she's|said|says|retard\w*|fag\w*|nig\w*|rape\w*|kill|cancer|gay|dick\w*|cock|pussy|"
                 r"cum|porn\w*|jerk\w*|sperm|pubes?|pubic|panties|trann\w*|jew\w*|muslim\w*|black people|white people)\b", re.I)
HIS = re.compile(r"fuck|shit|goddamn|god damn|\bson\b|\bdude\b|\bbro\b|\bman\b|\bbuddy\b", re.I)
OPENERS = set("I I'm I've I'd I'll It It's That That's This There There's They We We're We've You You're Your What "
              "What's Why Who How Where When Yeah Yes No Nah Oh Okay Dude Hey Holy God Fuck Fucking Shit Man Bro Buddy "
              "Listen Look Let's Let Just Like Maybe Probably Good My The A An If Not Nothing Some One Kind Honestly "
              "Alright Well Here Now Still Sometimes Every Everybody Everything Never Always Really Too All Any Another "
              "Damn Even Goddamn Hold Imagine Kinda Might Need Only Our Right Same Should Something Tell These Those Wait "
              "Was Were Would Wow Whoa Somebody Someone Actually Absolutely Pretty Could People Nobody Anything Anybody "
              "Mario".split())

EDITOR = ("You are editing lines for a video-game character. Each line below is something a streamer really said. "
          "The character says lines like these out loud, to nobody in particular, while skateboarding around a Super "
          "Mario 64 level next to Mario. KEEP a line only if all of this is true: it is a complete thought; it makes "
          "sense with no other context; it does not point at something the listener cannot see (\"that guy\", \"this "
          "thing right here\", \"it\" with nothing it refers to); it is not addressed to an audience or a named person; "
          "it is not about a different game's events; it is funny, odd or characterful rather than filler. "
          "Answer with one line per input, in order, exactly: the number, a space, then KEEP or DROP.")


def game_open() -> bool:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq sm64coopdx.exe"], capture_output=True, text=True).stdout
    return "sm64coopdx.exe" in out


def candidates(turns: Path, skip_vods: set, have: set, veto: Veto) -> tuple[list[str], set]:
    found, vods = [], set()
    with turns.open(encoding="utf-8") as f:
        for raw in f:
            row = json.loads(raw)
            vods.add(row["vod"])
            if row["vod"] in skip_vods or row["flags"]:
                continue
            text = row["text"].strip()
            words = text.split()
            if not 6 <= len(words) <= 28 or BAD.search(text) or not HIS.search(text) or text.lower() in have:
                continue
            if not re.search(r"[.!?]$", text) or re.search(r"\d", text) or veto.text(text):
                continue
            if any(w[0].isupper() and not w.startswith("I") for w in words[1:]) or re.sub(r"[^A-Za-z']", "", words[0]) not in OPENERS:
                continue                       # a capitalised word is probably a name
            if text.lower().count("like") > 2:
                continue
            have.add(text.lower())
            found.append(text)
    return found, vods


def edit(lines: list[str], cfg: dict) -> list[str]:
    """The writer model as editor: which of these stand on their own."""
    proc = subprocess.Popen([cfg["llama_server"], "-m", cfg["model"], "-c", "4096", "-ngl", "99", "--port", str(PORT),
                             "--host", "127.0.0.1", "-rea", "off"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline and proc.poll() is None and not play.llm_up(PORT):
            time.sleep(0.5)
        if not play.llm_up(PORT):
            raise SystemExit("the editor model did not start")
        llm, kept = ChatLLM(f"http://127.0.0.1:{PORT}", timeout=120), []
        for start in range(0, len(lines), 12):
            batch = lines[start:start + 12]
            user = "\n".join(f"{i + 1} {t}" for i, t in enumerate(batch))
            try:
                raw = llm.complete(EDITOR, user, temperature=0.0, max_tokens=120)
            except Exception:
                continue
            for n, verdict in re.findall(r"(\d+)\s+(KEEP|DROP)", raw):
                if verdict == "KEEP" and 1 <= int(n) <= len(batch):
                    kept.append(batch[int(n) - 1])
        return kept
    finally:
        proc.kill()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry", action="store_true")
    p.add_argument("--no-fetch", action="store_true")
    p.add_argument("--add", type=int, default=30, help="most lines to add in one run")
    p.add_argument("--consider", type=int, default=360, help="most candidates to show the editor in one run")
    p.add_argument("--remine", action="store_true", help="also look again at streams already mined")
    a = p.parse_args()
    if game_open():
        raise SystemExit("The game is open. Close it first; this uses the graphics card.")
    cfg = play.settings()
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.is_file() else {"mined": [], "runs": []}
    turns = HERE / "work/turns.jsonl"
    if not STATE.is_file() and turns.is_file():        # first run: the streams already in hand were mined by hand
        with turns.open(encoding="utf-8") as f:
            state["mined"] = sorted({json.loads(r)["vod"] for r in f})

    if not (a.dry or a.no_fetch):
        print("Looking for new streams and transcribing them...", flush=True)
        subprocess.run(["cmd", "/c", "start_pipeline.cmd", "--refresh"], cwd=TRANSCRIBER, check=False)
        print("Rebuilding the line source...", flush=True)
        subprocess.run([str(play.PYTHON), "-B", "-m", "jimmie_brain", "corpus", str(TRANSCRIBER / "transcripts"),
                        str(turns), "--splits", str(HERE.parent / "ai/personality_vod_splits.json")], cwd=HERE, check=True)

    doc = json.loads(REAL.read_text(encoding="utf-8"))
    have = {l["text"].lower() for l in doc["lines"]}
    found, vods = candidates(turns, set() if a.remine else set(state["mined"]), have, Veto())
    new_vods = sorted(vods - set(state["mined"]))
    random.Random(len(state["runs"]) + 1).shuffle(found)
    shown = found[:a.consider]
    print(f"{len(new_vods)} new stream(s), {len(found)} candidate lines, showing the editor {len(shown)}", flush=True)
    kept = edit(shown, cfg) if shown else []
    picked = kept[:a.add]
    print(f"editor kept {len(kept)}; adding {len(picked)}", flush=True)
    for line in picked:
        print("  +", line)
    if a.dry or not picked:
        if not a.dry:
            state["mined"] = sorted(set(state["mined"]) | vods)
            STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")
        return 0

    backup = HERE / "work/real_lines.before_keepup.json"
    shutil.copy2(REAL, backup)
    stamp = date.today().isoformat()
    doc["lines"] += [{"text": t, "rules": ["wander", "idle_ramble"], "auto": stamp, "weight": 3} for t in picked]
    out = ("{\n " + json.dumps("about") + ": " + json.dumps(doc["about"]) + ",\n \"weight\": " + json.dumps(doc["weight"])
           + ",\n \"lines\": [\n  " + ",\n  ".join(json.dumps(l, ensure_ascii=False) for l in doc["lines"]) + "\n ]\n}\n")
    REAL.write_bytes(out.encode("utf-8"))

    print("Voicing the new lines...", flush=True)
    subprocess.run([str(play.PYTHON), "-B", "bake_all.py", "--voice-only", "--batch", "1"], cwd=HERE, check=False)
    tests = subprocess.run([str(play.PYTHON), "-B", "-m", "unittest", "discover", "-s", "tests"], cwd=HERE,
                           capture_output=True, text=True)
    ok = tests.returncode == 0
    if not ok:
        shutil.copy2(backup, REAL)
        print("Tests failed; real_lines.json was put back.", tests.stderr[-600:], flush=True)
    state["mined"] = sorted(set(state["mined"]) | vods)
    state["runs"].append({"date": stamp, "new_streams": new_vods, "candidates": len(found), "kept": len(kept),
                          "added": len(picked) if ok else 0, "tests_passed": ok})
    STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")
    with LOG.open("a", encoding="utf-8", newline="\n") as f:
        if LOG.stat().st_size == 0:
            f.write("# What the keep-up routine added\n\nWritten by `tools/keep_up.py`. Nobody has read these lines; "
                    "remove any from `real_lines.json` (they are marked \"auto\").\n")
        f.write(f"\n## {stamp}\n\n{len(new_vods)} new stream(s), {len(found)} candidates, editor kept {len(kept)}, "
                f"{'added ' + str(len(picked)) if ok else 'added none: tests failed'}.\n\n")
        f.writelines(f"- {t}\n" for t in (picked if ok else []))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
