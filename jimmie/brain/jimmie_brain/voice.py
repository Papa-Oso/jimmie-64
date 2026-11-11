"""Turning a line into sound. Order of preference: his real recording, a take already rendered,
then the cloned voice. The clone uses the Qwen3-TTS model and owner-confirmed reference the
project already has; it is imported lazily so everything else runs without a GPU."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

from .writer import normal

DATA = Path(__file__).with_name("data")
SPOKEN_FORMS = {"[chuckles]": "Heh heh heh.", "[laughs]": "Ha ha ha ha."}


@dataclass
class Take:
    tag: str
    text: str
    file: str | None          # name inside the mod's sound folder, when it ships with the game
    origin: str = ""
    bit: str = ""


class Bank:
    def __init__(self, path: Path = DATA / "bank.json"):
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        self.takes = {tag: Take(tag, r["text"], r.get("file"), r.get("origin", "")) for tag, r in raw["takes"].items()}
        self.bits: dict[str, list[Take]] = {}
        for bit, row in raw["bits"].items():
            self.bits[bit] = [Take(f"bit_{bit}_{i}", f["text"], f.get("file"), "bit", bit) for i, f in enumerate(row["forms"])]
        self.by_text = {normal(t.text): t for t in self.takes.values() if t.file}

    def recording_for(self, text: str) -> Take | None:
        """If he has really said exactly this and we have the audio, use the audio."""
        return self.by_text.get(normal(text))


class NullTTS:
    """Writes a short silent WAV. For tests and text-only shadow runs."""
    name = "null"

    def render(self, text: str, out: Path) -> float:
        seconds = max(0.4, 0.33 * len(text.split()))
        with wave.open(str(out), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
            w.writeframes(b"\0\0" * int(16000 * seconds))
        return seconds


class QwenCloneTTS:
    """The project's existing voice clone. Loads once, stays warm."""
    name = "qwen3-tts-1.7b-clone"

    def __init__(self, model_dir: Path, reference_json: Path, device: str | None = None, seed: int = 643301):
        import torch  # noqa: lazily, so the rest of the brain needs no GPU stack
        from qwen_tts import Qwen3TTSModel
        ref = json.loads(Path(reference_json).read_text(encoding="utf-8-sig"))
        audio = Path(ref["audio"])
        if not audio.is_file():  # the pack moved; the WAV sits beside its manifest
            audio = Path(reference_json).with_name(Path(ref["audio"].replace("\\", "/")).name)
        self.torch, self.seed = torch, seed
        device = device or ("cuda:0" if torch.cuda.is_available() else "cpu")
        self.model = Qwen3TTSModel.from_pretrained(str(model_dir), device_map=device, dtype=torch.bfloat16,
                                                   attn_implementation="sdpa")
        self.prompt = self.model.create_voice_clone_prompt(ref_audio=str(audio), ref_text=ref["text"])

    def render(self, text: str, out: Path) -> float:
        self.torch.manual_seed(self.seed + int(hashlib.sha256(text.encode()).hexdigest()[:6], 16))
        waves, rate = self.model.generate_voice_clone(text=text, language="English", voice_clone_prompt=self.prompt,
                                                      max_new_tokens=160, do_sample=True, temperature=0.78, top_p=0.9,
                                                      repetition_penalty=1.05)
        return self._finish(waves[0], rate, out)

    def render_many(self, texts: list[str], outs: list[Path]) -> list[float | None]:
        """Several lines in one pass, which is several times faster than one at a time. None = that take failed."""
        self.torch.manual_seed(self.seed + int(hashlib.sha256("\n".join(texts).encode()).hexdigest()[:6], 16))
        prompt = self.prompt * len(texts) if len(self.prompt) == 1 else self.prompt
        waves, rate = self.model.generate_voice_clone(text=list(texts), language=["English"] * len(texts),
                                                      voice_clone_prompt=prompt, max_new_tokens=160, do_sample=True,
                                                      temperature=0.78, top_p=0.9, repetition_penalty=1.05)
        done = []
        for wave_, out in zip(waves, outs):
            try:
                done.append(self._finish(wave_, rate, out))
            except ValueError:
                done.append(None)
        return done

    def _finish(self, wave_, rate: int, out: Path) -> float:
        import numpy as np
        import soundfile as sf
        audio = np.asarray(wave_, dtype=np.float32).reshape(-1)
        peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
        if peak > 0:
            audio = audio * (0.89 / peak)       # one consistent level, so a quiet take is not lost under the music
        loud = np.flatnonzero(np.abs(audio) >= max(0.003, 0.02 * float(np.max(np.abs(audio)))))
        if not len(loud):
            raise ValueError("render produced silence")
        lo = max(0, int(loud[0]) - round(0.035 * rate))
        hi = min(len(audio), int(loud[-1]) + round(0.08 * rate) + 1)
        sf.write(str(out), audio[lo:hi], rate, subtype="PCM_16")
        return (hi - lo) / rate


class Renderer:
    """text -> .ogg on disk, cached by voice + text. ModFS accepts ogg and mp3, not wav."""

    def __init__(self, tts, cache: Path, ffmpeg: str | Path | None = "ffmpeg"):
        self.tts, self.cache, self.ffmpeg = tts, Path(cache), ffmpeg
        self.cache.mkdir(parents=True, exist_ok=True)

    def path_for(self, text: str) -> Path:
        key = hashlib.sha256((self.tts.name + "\n" + text).encode("utf-8")).hexdigest()[:24]
        return self.cache / f"{key}.ogg"

    def ensure(self, text: str) -> tuple[Path, float]:
        spoken = SPOKEN_FORMS.get(text.strip().lower(), text)
        target = self.path_for(spoken)
        meta = target.with_suffix(".json")
        if target.is_file() and meta.is_file():
            return target, json.loads(meta.read_text())["seconds"]
        wav = target.with_suffix(".wav")
        seconds = self.tts.render(spoken, wav)
        self.encode(wav, target)
        meta.write_text(json.dumps({"text": spoken, "seconds": round(seconds, 3), "voice": self.tts.name}))
        return target, seconds

    def encode(self, wav: Path, target: Path) -> None:
        if self.ffmpeg and shutil.which(str(self.ffmpeg)) or (self.ffmpeg and Path(str(self.ffmpeg)).is_file()):
            subprocess.run([str(self.ffmpeg), "-nostdin", "-v", "error", "-y", "-i", str(wav), "-map_metadata", "-1",
                            "-c:a", "libvorbis", "-q:a", "5", str(target)], check=True)
            wav.unlink(missing_ok=True)
        else:  # no encoder available (tests): keep the bytes so the pipeline still flows
            wav.replace(target)
