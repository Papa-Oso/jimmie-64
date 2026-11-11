"""Write and voice Jimmie's lines before play, so nothing heavy runs during it.

The 12B writer and the voice clone do not fit on a 12 GB card together, and a reaction has to
start within half a second. So the work is done ahead:

    python -m jimmie_brain.bake write --llm http://127.0.0.1:8771 --turns work/turns.jsonl
    python -m jimmie_brain.bake voice --voice-model ... --voice-reference ... --ffmpeg ...
    python -m jimmie_brain.bake report --turns work/turns.jsonl

write   for every rule that allows new words, and every place for the rules that are about a
        place, ask the model for candidates, keep the ones that pass every check.  -> work/pool/lines.jsonl
judge   the model, as an editor, strikes lines that do not fit their moment; lines lifted whole from
        a stream and the excess of lines ending on "son/dude/buddy" are trimmed to his real rate.
voice   record every line, staple, bit and unrecorded take in the cloned voice, then have a
        speech recogniser listen to each one; a take that does not say its words is redone or
        dropped.                                                               -> work/pool/voice.json
report  how the written lines compare with his real held-out speech.

Run `write` again any time for more lines: it adds to the pool and never repeats what is in it.
"""
from __future__ import annotations

import argparse
import difflib
import json
import random
import re
import time
from pathlib import Path

from . import corpus
from .facts import LEVEL_NAMES
from .rules import RuleBook
from .voice import Bank, QwenCloneTTS, Renderer, SPOKEN_FORMS
from .writer import ChatLLM, Scene, Veto, Writer, build_messages, clean, lint, normal

DATA = Path(__file__).with_name("data")
POOL = Path("work/pool")

# Rules whose lines are about where they are: written once per place, plus a few that fit anywhere.
PLACE_RULES = {"arrive_new", "arrive_again", "idle_ramble", "wander"}
PLACES = [16, 6, 26, 9, 24, 12, 5, 4, 7, 22, 8, 23, 10, 11, 36, 13, 14, 15, 17, 19, 21, 27]
PLACE_NOTES = {
    16: "outside Peach's castle: grass, a moat, a bridge, a waterfall", 6: "inside Peach's castle: checkered floor, paintings, big staircase",
    26: "the castle courtyard: a fountain and Boos", 9: "Bob-omb Battlefield: grassy hills, a mountain, Bob-ombs, a Chain Chomp",
    24: "Whomp's Fortress: a floating stone fortress with Whomps and Thwomps", 12: "Jolly Roger Bay: a foggy cove with a sunken ship and an eel",
    5: "Cool, Cool Mountain: snow, a long ice slide, penguins", 4: "Big Boo's Haunt: a haunted mansion full of Boos",
    7: "Hazy Maze Cave: a dark cave with toxic fog and an underground lake", 22: "Lethal Lava Land: platforms over a sea of lava, a volcano",
    8: "Shifting Sand Land: desert, quicksand, a pyramid", 23: "Dire, Dire Docks: deep water, a submarine dock",
    10: "Snowman's Land: snow, a giant snowman, freezing water", 11: "Wet-Dry World: a flooded town where the water level changes",
    36: "Tall, Tall Mountain: a huge mountain with mushrooms and a monkey", 13: "Tiny-Huge Island: an island where everything is giant or tiny",
    14: "Tick Tock Clock: the inside of a giant clock", 15: "Rainbow Ride: carpets flying through the sky",
    17: "Bowser in the Dark World: Bowser's first obstacle course", 19: "Bowser in the Fire Sea: Bowser's lava course",
    21: "Bowser in the Sky: the last course before the final fight", 27: "the Princess's Secret Slide: a long indoor slide",
}
# What had just happened, in the same plain words Memory.story() uses, for each rule.
EVENT = {"star": "Mario collected a star (just now)", "death": "Mario died (just now)", "hurt": "Mario got hurt (just now)",
         "fall": "Mario fell a long way (just now)", "key": "Mario got a Bowser key (just now)",
         "grand_star": "Mario beat Bowser for good (just now)", "trick_bailed": "Jimmie bailed a skate trick (just now)",
         "trick_completed": "Jimmie landed a skate trick (just now)", "arrival": "they arrived in a new area (just now)"}
PRELUDE = {
    "star_after_trouble": ["Mario fell and lost progress (1m ago)"],
    "star_after_deaths": ["Mario died (3m ago)", "Mario died (1m ago)"],
    "death_again": ["Mario died (1m ago)"], "death_streak": ["Mario died (2m ago)", "Mario died (1m ago)"],
    "death_tilted": ["Mario died (4m ago)", "Mario died (2m ago)", "Mario died (1m ago)"],
    "bail_streak": ["Jimmie bailed a skate trick (40s ago)", "Jimmie bailed a skate trick (15s ago)"],
    "land_streak": ["Jimmie landed a skate trick (30s ago)", "Jimmie landed a skate trick (12s ago)"],
    "land_after_fall": ["Jimmie bailed a skate trick (15s ago)"],
}
SAID_BEFORE = {"bail_called": "Watch this shit.", "land_called": "Watch this shit.", "land_left": "Here we go."}


def jobs(book: RuleBook):
    for rule in book.rules:
        if not rule.write or rule.quiet:
            continue
        mode = rule.when.get("mode") if isinstance(rule.when.get("mode"), str) else None
        levels = [None] + (PLACES if rule.id in PLACE_RULES else [])
        fixed = rule.when.get("level")
        if isinstance(fixed, int):
            levels = [fixed]
        for level in levels:
            yield rule, mode, level


def scene_for(rule, mode, level) -> Scene:
    story = list(PRELUDE.get(rule.id, []))
    if rule.on[0] in EVENT:
        story.append(EVENT[rule.on[0]])
    place = ""
    if level is not None:
        place = LEVEL_NAMES.get(level, "")
        if level in PLACE_NOTES:
            place += f" ({PLACE_NOTES[level]})"
    said = SAID_BEFORE.get(rule.id, "")
    return Scene(mode=mode or "free", place=place, story=story, moment=rule.direction, intent=rule.intent,
                 last_said=said, last_said_s=3.0 if said else 0.0, stars=None)


def cmd_write(a) -> int:
    book = RuleBook.load()
    veto = Veto()
    turns = corpus.load_turns(Path(a.turns))
    index = corpus.Index(turns, splits=("train",))
    known = {normal(t.text) for t in turns if t.split == "train"}
    writer = Writer(ChatLLM(a.llm, a.model, timeout=90), index=index, veto=veto, rng=random.Random(a.seed), candidates=a.candidates)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    have: dict[str, set] = {}
    if out.is_file():
        for raw in out.read_text(encoding="utf-8").splitlines():
            row = json.loads(raw)
            have.setdefault(row["rule"], set()).add(normal(row["text"]))
    staples = {normal(t) for rows in json.loads((DATA / "staples.json").read_text(encoding="utf-8")).values()
               if isinstance(rows, list) for t, _ in rows}
    todo = list(jobs(book))
    added = rejected = calls = 0
    reasons: dict[str, int] = {}
    started = time.monotonic()
    with out.open("a", encoding="utf-8", newline="\n") as f:
        for n, (rule, mode, level) in enumerate(todo, 1):
            scene = scene_for(rule, mode, level)
            rounds = a.rounds if level is None else max(1, a.rounds // 2)
            seen = have.setdefault(rule.id, set())
            kept = 0
            for r in range(rounds):
                system, user = build_messages(scene, writer.exemplars(scene), a.candidates, rule.max_words)
                try:
                    raw = writer.llm.complete(system, user, temperature=1.0, max_tokens=40 + 22 * a.candidates,
                                              seed=a.seed * 1000 + n * 10 + r)
                except Exception as error:      # a stalled server should not lose the lines already written
                    print(f"  ! {rule.id}: {error}", flush=True)
                    continue
                calls += 1
                for line in clean(raw):
                    if line in ("-", "—", "..."):
                        continue
                    why = lint(line, scene, veto, rule.max_words)
                    key = normal(line)
                    if not why and (key in seen or key in staples):
                        why = ["repeat"]
                    if why:
                        rejected += 1
                        for w in why:
                            reasons[w] = reasons.get(w, 0) + 1
                        continue
                    seen.add(key)
                    f.write(json.dumps({"text": line, "rule": rule.id, "intent": rule.intent, "mode": mode, "level": level,
                                        "copied": key in known}, ensure_ascii=False) + "\n")
                    added += 1
                    kept += 1
            f.flush()
            print(f"[{n}/{len(todo)}] {rule.id}{'' if level is None else ' @' + LEVEL_NAMES.get(level, str(level))}: +{kept}", flush=True)
    print(json.dumps({"added": added, "rejected": rejected, "why": reasons, "calls": calls,
                      "minutes": round((time.monotonic() - started) / 60, 1), "out": str(out)}, indent=1))
    return 0


JUDGE = ("You are a script editor checking lines for Jimmie, a loud, sweary streamer skating beside Mario in Super Mario 64. "
         "You are strict and brief.")
JUDGE_ASK = ("Which of the numbered lines do NOT fit THE MOMENT? A line fails if its emotion is wrong for what just happened "
             "(cheering a death, mourning a win), if it is about something that did not happen, if it gets wrong who did what "
             "(Mario jumps, collects stars and dies; Jimmie skates), or if it makes no sense said out loud right now. "
             "Swearing, rudeness and repetition are fine. Reply with only the failing numbers separated by commas, or the word none.")
ADDRESS_END = re.compile(r"\b(son|dude|buddy|man|bro|boys|ladies|sweetie|baby|guys|mario|spanky|fucker)[.!?]*$", re.I)


STRIP_TAG = re.compile(r",?\s+(son|dude|buddy|man|bro|boys|ladies|sweetie|baby|guys|spanky|fucker)([.!?]*)$", re.I)


def cmd_judge(a) -> int:
    """Second pass: the model, as an editor, strikes lines that do not fit their moment; then the pool is
    trimmed toward how often he really ends a line on a name, and long lines lifted whole from a stream go."""
    book = {r.id: r for r in RuleBook.load().rules}
    path = Path(a.out)
    rows = [json.loads(r) for r in path.read_text(encoding="utf-8").splitlines()]
    todo = [r for r in rows if "fit" not in r]
    llm = ChatLLM(a.llm, a.model, timeout=90)
    groups: dict[tuple, list[dict]] = {}
    for r in todo:
        groups.setdefault((r["rule"], r["mode"], r["level"]), []).append(r)
    calls = 0
    for (rule_id, mode, level), group in groups.items():
        rule = book.get(rule_id)
        if not rule:
            continue
        scene = scene_for(rule, mode, level)
        head = ["SCENE"] + ([f"- Place: {scene.place}"] if scene.place else []) + [f"- {e}" for e in scene.story]
        if scene.last_said:
            head.append(f"- The last thing Jimmie said out loud: {scene.last_said}")
        head += ["", "THE MOMENT", scene.moment, ""]
        for at in range(0, len(group), 12):
            chunk = group[at:at + 12]
            user = "\n".join(head + [f"{i + 1}. {r['text']}" for i, r in enumerate(chunk)] + ["", JUDGE_ASK])
            try:
                reply = llm.complete(JUDGE, user, temperature=0.0, max_tokens=40)
            except Exception as error:
                print(f"  ! {rule_id}: {error}", flush=True)
                continue
            calls += 1
            bad = {int(n) for n in re.findall(r"\d+", reply)}
            for i, r in enumerate(chunk):
                r["fit"] = (i + 1) not in bad
    known_long = lambda r: r["copied"] and len(normal(r["text"]).split()) >= 5
    rng = random.Random(a.seed)
    kept, struck = [], {"unfit": 0, "lifted": 0, "name_tag": 0, "name_tag_removed": 0}
    staple_texts = {normal(t) for group in json.loads((DATA / "staples.json").read_text(encoding="utf-8")).values()
                    if isinstance(group, list) for t, _ in group}
    by_rule: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("fit") is False:
            struck["unfit"] += 1
        elif known_long(r):
            struck["lifted"] += 1
        else:
            by_rule.setdefault(r["rule"], []).append(r)
    for rule_id, group in by_rule.items():
        tagged = [r for r in group if ADDRESS_END.search(r["text"].strip())]
        plain = [r for r in group if not ADDRESS_END.search(r["text"].strip())]
        # The model hangs "son" or "dude" on nearly every line; he does it on about one in ten.
        # Keep his rate and drop the tag, not the line, from the rest.
        rng.shuffle(tagged)
        seen = {normal(r["text"]) for r in plain}
        keep_tag = max(2, round(a.name_rate * len(group)))
        for i, r in enumerate(tagged):
            if i < keep_tag:
                seen.add(normal(r["text"]))
                plain.append(r)
                continue
            bare = STRIP_TAG.sub(lambda m: m.group(2) or ".", r["text"].strip())
            if len(normal(bare).split()) >= 2 and normal(bare) not in seen and normal(bare) not in staple_texts:
                seen.add(normal(bare))
                plain.append(dict(r, text=bare, untagged=True))
                struck["name_tag_removed"] += 1
            else:
                struck["name_tag"] += 1
        kept.extend(plain)
    path.with_name("lines-all.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept), encoding="utf-8")
    print(json.dumps({"before": len(rows), "kept": len(kept), "struck": struck, "judge_calls": calls}, indent=1))
    return 0


OVERUSED = ("i mean", "holy shit", "god damn", "goddamn", "oh my god")
PLACE_INTENT = {"wander": "ramble", "idle_ramble": "ramble", "arrive_new": "greet", "arrive_again": "callback"}


def real_rows() -> list[dict]:
    """His own stream lines (data/real_lines.json) as pool rows: one per rule and place they fit."""
    doc = json.loads((DATA / "real_lines.json").read_text(encoding="utf-8"))
    intents = {r.id: r.intent for r in RuleBook.load().rules}
    rows = []
    for line in doc["lines"]:
        for rule in line["rules"]:
            for level in line.get("levels") or [None]:
                rows.append({"text": line["text"], "rule": rule, "intent": intents[rule], "mode": None, "level": level,
                             "weight": float(line.get("weight", doc.get("weight", 1.0))), "real": True})
    return rows


def answer_rows() -> list[dict]:
    """Answers written ahead of time to things players type at him (data/answers.json) as pool rows."""
    path = DATA / "answers.json"
    if not path.is_file():
        return []
    return [{"text": text, "rule": "chat_answer", "intent": "reply", "mode": None, "level": None, "weight": 1.0,
             "answer": entry["id"]}
            for entry in json.loads(path.read_text(encoding="utf-8"))["answers"] for text in entry["say"]]


def trick_rows() -> list[dict]:
    """Lines that name a trick he just landed (data/tricks.json) as pool rows."""
    path = DATA / "tricks.json"
    if not path.is_file():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not doc.get("chance"):                   # switched off: nothing to voice or load
        return []
    return [{"text": text, "rule": "trick_name", "intent": "boast", "mode": None, "level": None, "weight": 1.0,
             "tag": "trick:" + name}
            for name, texts in doc["say"].items() for text in texts]


def soften_repeats(lines: list[dict]) -> list[dict]:
    """The writer opens a third of its lines the same few ways. Those stay, but come up far less often."""
    for row in lines:
        opener = " ".join(re.sub(r"[^a-z' ]", "", row["text"].lower()).split()[:3])
        if opener.startswith(OVERUSED) and row["rule"] in PLACE_INTENT:
            row["weight"] = 0.04
    return lines


def pool_texts(lines: Path) -> list[str]:
    """Everything the clone has to say: written lines, staples, and takes or bits with no recording."""
    texts: list[str] = []
    bank = json.loads((DATA / "bank.json").read_text(encoding="utf-8"))
    for take in bank["takes"].values():
        if not take.get("file") and not take["text"].startswith("("):
            texts.append(take["text"])
    for bit in bank["bits"].values():
        texts.extend(f["text"] for f in bit["forms"] if not f.get("file") and not f["text"].startswith("("))
    for rows in json.loads((DATA / "staples.json").read_text(encoding="utf-8")).values():
        if isinstance(rows, list):
            texts.extend(t for t, _ in rows)
    if lines.is_file():
        texts.extend(json.loads(raw)["text"] for raw in lines.read_text(encoding="utf-8").splitlines())
    texts.extend(row["text"] for row in real_rows() + answer_rows() + trick_rows())
    out, seen = [], set()
    for t in texts:
        if normal(t) not in seen:
            seen.add(normal(t))
            out.append(t)
    return out


class Listener:
    """A speech recogniser that checks a take says its words. It has never seen the script."""

    def __init__(self, model_dir: str):
        import torch
        from transformers import pipeline
        self.asr = pipeline("automatic-speech-recognition", model=model_dir, torch_dtype=torch.float16,
                            device="cuda:0" if torch.cuda.is_available() else "cpu")

    def hears(self, path: Path) -> str:
        import librosa
        audio, _ = librosa.load(str(path), sr=16000, mono=True)
        return self.asr({"raw": audio, "sampling_rate": 16000}, generate_kwargs={"language": "en", "task": "transcribe"})["text"].strip()


SAME_WORDS = (("goddamn", "god damn"), ("gonna", "going to"), ("gotta", "got to"), ("wanna", "want to"), ("alright", "all right"),
              ("fuckin'", "fucking"), ("fuckin", "fucking"), ("skatable", "skateable"), ("shitballs", "shit balls"),
              ("ok", "okay"), ("'cause", "because"), ("yup", "yep"))


def spelled(text: str) -> str:
    """One spelling for words a recogniser writes differently from the script; the sound is the same."""
    text = " " + normal(text.replace(chr(8217), "'")) + " "
    for a, b in SAME_WORDS:
        text = text.replace(f" {a} ", f" {b} ")
    return text.strip()


def agreement(wanted: str, heard: str) -> float:
    a, b = spelled(wanted).split(), spelled(heard).split()
    return difflib.SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def cmd_voice(a) -> int:
    pool = Path(a.pool)
    index_path = pool / "voice.json"
    voiced = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else {}
    texts = [t for t in pool_texts(pool / "lines.jsonl") if normal(t) not in voiced]
    if a.limit:
        texts = texts[:a.limit]
    print(f"{len(texts)} lines to voice, {len(voiced)} already done", flush=True)
    if not texts:
        return 0
    tts = QwenCloneTTS(Path(a.voice_model), Path(a.voice_reference))
    renderer = Renderer(tts, pool / "audio", a.ffmpeg)
    listener = Listener(a.listener) if a.listener else None
    base_seed, started, retried, done = tts.seed, time.monotonic(), 0, 0
    why: dict[str, str] = {}
    todo = list(texts)
    for attempt in range(a.tries):
        tts.seed = base_seed + attempt * 7919
        again = []
        # Lines of similar length together, so a batch does not wait on its longest member.
        todo.sort(key=lambda t: len(t))
        for at in range(0, len(todo), a.batch):
            batch = todo[at:at + a.batch]
            spoken = [SPOKEN_FORMS.get(t.strip().lower(), t) for t in batch]
            targets = [renderer.path_for(sp).with_name(renderer.path_for(sp).stem + f"-t{attempt}.ogg") for sp in spoken]
            try:
                lengths = tts.render_many(spoken, [t.with_suffix(".wav") for t in targets])
            except Exception as error:
                for t in batch:
                    why[t] = str(error)[:200]
                again.extend(batch)
                continue
            for text, sp, target, seconds in zip(batch, spoken, targets, lengths):
                if seconds is None:
                    why[text] = "silence"
                    again.append(text)
                    continue
                renderer.encode(target.with_suffix(".wav"), target)
                heard = listener.hears(target) if listener else sp
                score = agreement(sp, heard)
                # A take far longer than its words is the model rambling or trailing off into noise.
                sane = seconds <= 0.9 + 0.62 * len(sp.split())
                if score >= a.agree and sane:
                    voiced[normal(text)] = {"file": target.relative_to(pool).as_posix(), "seconds": round(seconds, 3), "heard": heard,
                                            "agreement": round(score, 2), "tries": attempt + 1, "text": text}
                    done += 1
                else:
                    target.unlink(missing_ok=True)
                    why[text] = f"heard {heard!r} ({score:.2f}, {seconds:.1f}s)"
                    again.append(text)
                    retried += 1
            index_path.write_text(json.dumps(voiced, indent=1, ensure_ascii=False), encoding="utf-8")
            rate = (time.monotonic() - started) / max(1, done + len(again))
            print(f"pass {attempt + 1}: {min(at + a.batch, len(todo))}/{len(todo)}  {rate:.1f}s per line, {len(again)} to redo", flush=True)
        todo = again
        if not todo:
            break
    failed = [{"text": t, "error": why.get(t, "")} for t in todo]
    index_path.write_text(json.dumps(voiced, indent=1, ensure_ascii=False), encoding="utf-8")
    (pool / "voice-dropped.json").write_text(json.dumps(failed, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"voiced_total": len(voiced), "new": len(texts) - len(failed), "dropped": len(failed), "retries": retried,
                      "minutes": round((time.monotonic() - started) / 60, 1)}, indent=1))
    return 0


def cmd_report(a) -> int:
    from .eval import authorship_auc, copy_rate
    pool = Path(a.pool)
    rows = [json.loads(r) for r in (pool / "lines.jsonl").read_text(encoding="utf-8").splitlines()]
    turns = corpus.load_turns(Path(a.turns))
    rng = random.Random(0)
    held = [t.text for t in turns if t.split == "test" and corpus.usable(t)]
    dev = [t.text for t in turns if t.split == "development" and corpus.usable(t)]
    train = [t.text for t in turns if t.split == "train"]
    written = [r["text"] for r in rows]
    n = min(len(written), len(held), 1500)
    sample = lambda xs: rng.sample(xs, min(n, len(xs)))
    voiced = json.loads((pool / "voice.json").read_text(encoding="utf-8")) if (pool / "voice.json").is_file() else {}
    report = {
        "written_lines": len(written), "rules": len({r["rule"] for r in rows}),
        "places_with_lines": len({r["level"] for r in rows if r["level"] is not None}),
        "voiced": len(voiced),
        "voice_first_try": round(sum(v["tries"] == 1 for v in voiced.values()) / len(voiced), 3) if voiced else None,
        "voice_mean_agreement": round(sum(v["agreement"] for v in voiced.values()) / len(voiced), 3) if voiced else None,
        "copy_rate": copy_rate(written, train),
        "authorship_auc_written_vs_real": authorship_auc(sample(held), sample(written)),
        "authorship_auc_floor_real_vs_real": authorship_auc(sample(held), sample(dev)),
        "fingerprint_written": corpus.fingerprint(written), "fingerprint_real": corpus.fingerprint(held),
    }
    report["drift"] = corpus.drift(report["fingerprint_real"], report["fingerprint_written"])
    (pool / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="jimmie_brain.bake", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(required=True)
    s = sub.add_parser("write"); s.set_defaults(fn=cmd_write)
    s.add_argument("--llm", required=True); s.add_argument("--model", default="local"); s.add_argument("--turns", required=True)
    s.add_argument("--out", default=str(POOL / "lines.jsonl")); s.add_argument("--rounds", type=int, default=4)
    s.add_argument("--candidates", type=int, default=8); s.add_argument("--seed", type=int, default=1)
    s = sub.add_parser("judge"); s.set_defaults(fn=cmd_judge)
    s.add_argument("--llm", required=True); s.add_argument("--model", default="local")
    s.add_argument("--out", default=str(POOL / "lines.jsonl")); s.add_argument("--seed", type=int, default=1)
    s.add_argument("--name-rate", type=float, default=0.2, help="largest share of a rule's lines that may end on a name")
    s = sub.add_parser("voice"); s.set_defaults(fn=cmd_voice)
    s.add_argument("--pool", default=str(POOL)); s.add_argument("--voice-model", required=True)
    s.add_argument("--voice-reference", required=True); s.add_argument("--ffmpeg", default="ffmpeg")
    s.add_argument("--listener", help="folder of a Whisper model; omit to skip the listening check")
    s.add_argument("--agree", type=float, default=0.8); s.add_argument("--tries", type=int, default=3)
    s.add_argument("--limit", type=int, default=0)
    s.add_argument("--batch", type=int, default=4)
    s = sub.add_parser("report"); s.set_defaults(fn=cmd_report)
    s.add_argument("--pool", default=str(POOL)); s.add_argument("--turns", required=True)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
