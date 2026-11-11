"""How long from a game event to the first audible sample of Jimmie's line.

    python play.py --smoke 115 --sound --capture
    python tools/measure_latency.py sessions/<that session> [more sessions...]

The game prints the event and the "played" confirmation with its own clock; the capture
program records the game's audio output with the same clock on every packet. For each line
that played, this finds where that exact recording begins in the captured sound (by matching
the waveform, so music and other effects do not confuse it) and reports event -> sound.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
SOUNDS = HERE / "build/game/mods/jimmie/sound"
RATE = 44100


def load_clip(name: str) -> np.ndarray | None:
    import librosa
    path = Path(name)
    if not path.is_absolute():
        path = SOUNDS / name
    if not path.is_file():
        return None
    audio, _ = librosa.load(str(path), sr=RATE, mono=True)
    return audio.astype(np.float32)


def capture(session: Path):
    pcm = np.fromfile(session / "windows.pcm", dtype="<i2").reshape(-1, 2).astype(np.float32).mean(axis=1) / 32768.0
    with (session / "windows-packets.csv").open() as f:
        packets = [(int(r["offset"]), int(r["qpc_100ns"]) / 10000.0) for r in csv.DictReader(f)]
    offsets = np.array([p[0] for p in packets], dtype=np.float64)
    times = np.array([p[1] for p in packets], dtype=np.float64)
    return pcm, offsets, times


def onset_ms(pcm, offsets, times, clip, around_ms: float) -> tuple[float, float] | None:
    """Clock time at which `clip` starts in the capture, searching from 150 ms before to 1500 ms after."""
    at = int(np.interp(around_ms, times, offsets))
    lo, hi = max(0, at - int(0.15 * RATE)), min(len(pcm), at + int(1.5 * RATE))
    head = clip[: int(0.45 * RATE)]
    window = pcm[lo: hi + len(head)]
    if len(window) <= len(head) or not np.any(head):
        return None
    corr = np.correlate(window, head, mode="valid")
    energy = np.sqrt(np.convolve(window ** 2, np.ones(len(head), dtype=np.float32), mode="valid")) * np.linalg.norm(head) + 1e-9
    score = corr / energy
    best = int(np.argmax(score))
    return float(np.interp(lo + best, offsets, times)), float(score[best])


def main(argv) -> int:
    rows = []
    for folder in argv:
        session = Path(folder)
        pcm, offsets, times = capture(session)
        heard = {}
        for raw in (session / "brain.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(raw)
            if row.get("event") == "heard":
                heard[row["line"]] = row
        facts = []
        for raw in (session / "stdout.log").read_text(encoding="utf-8", errors="replace").splitlines():
            at = raw.find("[jb] {")
            if at >= 0:
                try:
                    facts.append(json.loads(raw[at + 5:]))
                except ValueError:
                    pass
        for i, fact in enumerate(facts):
            if fact.get("k") != "played" or fact.get("line") not in heard:
                continue
            line = heard[fact["line"]]
            clip = load_clip(line.get("sound") or "")
            if clip is None:
                continue
            # The event that caused it: the fact printed on the same frame, if there is one (planned reactions).
            cause = next((f for f in reversed(facts[:i]) if f.get("f") == fact.get("f") and f.get("k") not in ("played", "idle")), None)
            found = onset_ms(pcm, offsets, times, clip, fact["ms"])
            if not found:
                continue
            start, score = found
            rows.append({"session": session.name, "rule": fact.get("rule"), "text": line["text"], "source": line.get("source"),
                         "kind": "reaction" if cause else "ambient", "event": cause["k"] if cause else None,
                         "event_to_sound_ms": round(start - (cause or fact)["ms"], 1), "match": round(score, 2)})
    good = [r for r in rows if r["match"] >= 0.5]
    for r in rows:
        print(f"{r['event_to_sound_ms']:8.1f} ms  match {r['match']:.2f}  {r['kind']:<8} {str(r['rule']):<18} {r['text']}")
    def stats(xs):
        xs = sorted(xs)
        return {"n": len(xs), "p50": float(np.percentile(xs, 50)), "p95": float(np.percentile(xs, 95)), "worst": xs[-1]} if xs else {"n": 0}
    summary = {"lines_played": len(rows), "confidently_located": len(good),
               "reactions": stats([r["event_to_sound_ms"] for r in good if r["kind"] == "reaction"]),
               "all": stats([r["event_to_sound_ms"] for r in good]),
               "over_500ms": [r for r in good if r["event_to_sound_ms"] > 500]}
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
