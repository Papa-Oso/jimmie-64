"""Score every second of every stream for "is this Jimmie's live voice?".

Why: the transcripts mix him with donation text-to-speech, guests, soundboard clips and game
audio. Until each turn has a speaker score, nothing can honestly be called a training example
of his speech (the previous training export correctly contained zero rows).

How: slide a 2-second window (1-second hop) over each VOD's audio, embed it with the speaker
encoder already in the project (ai/personality_speaker.py, the ECAPA encoder inside the local
Qwen3-TTS model), and take the cosine to the centroid of the owner-confirmed voice reference.

Writes <out>/<vod>.json: {"intervals": [[start_s, end_s, cosine], ...]} for jimmie_brain.corpus.

NOT RUN by its author (no access to the audio, torch or the GPU). Treat the first run as the test:
  1. run on ONE vod with --limit-s 600 and look at the histogram this prints;
  2. listen to ten windows just above and ten just below your chosen threshold;
  3. only then run the archive and pass that threshold as --min-speaker downstream.

Usage (project venv, from jimmie-64):
  .venv\\Scripts\\python.exe brain\\tools\\speaker_pass.py ^
      --corpus ..\\twitch-vod-transcribe --reference voice_tests\\ref_short.wav --out brain\\work\\speakers
"""
import argparse
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

RATE, WINDOW, HOP, BATCH = 24000, 2.0, 1.0, 64


def frames(ffmpeg, audio, limit_s=None):
    """Yield (start_s, float32 window) decoded on the fly; never holds a whole stream in memory."""
    command = [str(ffmpeg), "-nostdin", "-v", "error", "-i", str(audio), "-map", "0:a:0", "-ac", "1", "-ar", str(RATE),
               "-f", "s16le", "pipe:1"]
    if limit_s:
        command[4:4] = ["-t", str(limit_s)]
    proc = subprocess.Popen(command, stdout=subprocess.PIPE)
    size, hop = int(WINDOW * RATE), int(HOP * RATE)
    buffer, at = np.zeros(0, dtype=np.float32), 0
    try:
        while True:
            raw = proc.stdout.read(hop * 2 * 30)
            if not raw:
                break
            buffer = np.concatenate([buffer, np.frombuffer(raw[:len(raw) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0])
            while len(buffer) >= size:
                yield at / RATE, buffer[:size].copy()
                buffer = buffer[hop:]
                at += hop
    finally:
        proc.stdout.close()
        proc.wait()


def reference_centroid(extractor, path):
    with wave.open(str(path)) as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError("reference must be mono 16-bit PCM")
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
        rate = w.getframerate()
    from personality_speaker import mono_at_24k
    audio = mono_at_24k(pcm, rate)
    size, hop = int(WINDOW * RATE), int(HOP * RATE)
    windows = [audio[i:i + size] for i in range(0, len(audio) - size + 1, hop)]
    windows = [w for w in windows if float(np.sqrt(np.mean(w * w))) > 0.01]
    vectors = extractor.batch(windows)["ecapa"]
    centroid = vectors.mean(axis=0)
    centroid /= np.linalg.norm(centroid)
    spread = sorted(float(v @ centroid) for v in vectors)
    print(f"reference: {len(windows)} windows, cosine to own centroid min {spread[0]:.2f} median {spread[len(spread) // 2]:.2f}")
    return centroid


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--corpus", type=Path, required=True, help="twitch-vod-transcribe folder")
    p.add_argument("--reference", type=Path, required=True, help="owner-confirmed mono WAV of his live voice")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--ai", type=Path, default=Path("ai"), help="jimmie-64/ai, for personality_speaker.py")
    p.add_argument("--vods", nargs="*", help="only these VOD ids")
    p.add_argument("--limit-s", type=float)
    a = p.parse_args()
    sys.path.insert(0, str(a.ai.resolve()))
    from personality_speaker import Extractor
    extractor = Extractor()
    centroid = reference_centroid(extractor, a.reference)
    a.out.mkdir(parents=True, exist_ok=True)
    ffmpeg = a.corpus / "tools" / "ffmpeg.exe"
    for folder in sorted((a.corpus / "data").iterdir()):
        audio = folder / "audio.mp4"
        if not audio.is_file() or not folder.name.isdigit() or (a.vods and folder.name not in a.vods):
            continue
        target = a.out / f"{folder.name}.json"
        if target.is_file() and not a.limit_s:
            continue
        intervals, starts, batch = [], [], []

        def flush():
            if batch:
                scores = extractor.batch(batch)["ecapa"] @ centroid
                intervals.extend([round(s + (WINDOW - HOP) / 2, 2), round(s + (WINDOW + HOP) / 2, 2), round(float(c), 3)]
                                 for s, c in zip(starts, scores))
                starts.clear()
                batch.clear()

        for start, window in frames(ffmpeg, audio, a.limit_s):
            if float(np.sqrt(np.mean(window * window))) < 0.008:      # silence: nobody is speaking
                continue
            starts.append(start)
            batch.append(window)
            if len(batch) >= BATCH:
                flush()
        flush()
        scores = np.array([i[2] for i in intervals]) if intervals else np.zeros(1)
        histogram = np.histogram(scores, bins=10, range=(0, 1))[0].tolist()
        target.write_text(json.dumps({"vod": folder.name, "method": "ecapa-cosine", "window_s": WINDOW, "hop_s": HOP,
                                      "intervals": intervals}), encoding="utf-8")
        print(f"{folder.name}: {len(intervals)} voiced seconds; cosine histogram 0..1 in tenths: {histogram}", flush=True)


if __name__ == "__main__":
    main()
