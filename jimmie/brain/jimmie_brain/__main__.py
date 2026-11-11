"""Command line. Run `python -m jimmie_brain <command> -h`."""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

from . import corpus, eval as evaluation
from .bridge import Bridge
from .director import Director
from .facts import Fact, parse_line
from .voice import Bank, NullTTS, QwenCloneTTS, Renderer
from .writer import ChatLLM, ScriptedLLM, Writer


def _index(args):
    if not getattr(args, "turns", None) or not Path(args.turns).is_file():
        return None, []
    turns = corpus.load_turns(Path(args.turns))
    return corpus.Index(turns, splits=("train",), min_speaker=args.min_speaker), turns


def _writer(args, index):
    llm = ScriptedLLM() if args.llm == "scripted" else ChatLLM(args.llm, args.model)
    return Writer(llm, index=index, retrieval=not args.no_retrieval, rng=random.Random(args.seed))


def cmd_corpus(a):
    splits = corpus.load_splits(a.splits)
    turns = corpus.build_turns(Path(a.transcripts), splits, Path(a.speakers) if a.speakers else None)
    corpus.save_turns(turns, Path(a.out))
    index = corpus.Index(turns, splits=("train",))
    verified = sum(t.speaker is not None for t in turns)
    summary = {"turns": len(turns), "usable_train": len(index.turns), "speaker_checked": verified,
               "by_split": {s: sum(t.split == s for t in turns) for s in sorted({t.split for t in turns})},
               "fingerprint_train": corpus.fingerprint([t.text for t in index.turns])}
    print(json.dumps(summary, indent=1))
    if not verified:
        print("NOTE: no speaker scores yet. Retrieval works; training export stays empty until tools/speaker_pass.py has run.",
              file=sys.stderr)


def cmd_export(a):
    turns = corpus.load_turns(Path(a.turns))
    rows = list(corpus.training_rows(turns, min_speaker=a.min_speaker, require_verified=not a.allow_unverified))
    with Path(a.out).open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"rows": len(rows), "vods": len({r["vod"] for r in rows}), "out": a.out}))


def cmd_shadow(a):
    """Replay a recorded game log: what would he have said, and when? Nothing is played."""
    index, _ = _index(a)
    d = Director(writer=_writer(a, index), rng=random.Random(a.seed))
    said = 0

    def say(entry, at, label):
        nonlocal said
        line = d.lines[entry["line"]]
        said += 1
        print(f"{at / 1000:9.1f}s {label:<38} JIMMIE [{entry['rule']}/{line.source}]: {line.text}")
        # Stand in for the game: confirm the line was heard, as the link's "played" report would.
        d.observe(Fact("played", "jimmie", ms=at + entry.get("delay", 0), mode=d.memory.mode, scope=d.memory.scope,
                       level=d.memory.level, data={"line": line.id, "rule": entry["rule"], "intent": entry["intent"]}))

    def think():
        while d.write_one():
            pass
        if d.ambient:
            say(d.ambient, d.memory.now, "(dead air)")

    clock = 0.0
    for raw in Path(a.log).read_text(encoding="utf-8", errors="replace").splitlines():
        fact = parse_line(raw)
        if not fact or fact.kind in ("played", "hello"):
            continue
        while clock and clock + 2000 < fact.ms:        # the bridge ticks every two seconds; so does the replay
            clock += 2000
            d.tick(clock)
            think()
        clock = max(clock, fact.ms)
        entry = d.plan.get(fact.key)                   # what the game would already be holding for this event
        d.observe(fact)
        if entry and entry["scope"] == fact.scope:
            say(entry, fact.ms, fact.key)
        elif a.verbose:
            print(f"{fact.ms / 1000:9.1f}s {fact.key:<38} (quiet)")
        think()
    print(f"-- {said} lines", file=sys.stderr)


def cmd_scenes(a):
    bad = [r for r in evaluation.rule_check() if not r["ok"]]
    for r in evaluation.rule_check():
        print(("ok  " if r["ok"] else "BAD ") + f"{r['scene']:<24} {str(r['rule']):<20} {r['intent']}")
    if a.out:
        index, turns = _index(a)
        rows = evaluation.generate(_writer(a, index), a.label, seed=a.seed)
        Path(a.out).write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
        held = [t.text for t in turns if t.split == "test" and corpus.usable(t)]
        train = [t.text for t in turns if t.split == "train"]
        print(json.dumps(evaluation.report(rows, held, train), indent=1, default=dict))
    return 1 if bad else 0


def cmd_packet(a):
    runs = {}
    for path in a.runs:
        rows = json.loads(Path(path).read_text(encoding="utf-8"))
        runs[rows[0]["label"]] = rows
    evaluation.packet(runs, Path(a.out), seed=a.seed)
    print(f"ballot.html and the sealed key are in {a.out}")


def cmd_score(a):
    ballot = json.loads(Path(a.ballot).read_text(encoding="utf-8"))
    key = json.loads(Path(a.key).read_text(encoding="utf-8"))
    print(json.dumps(evaluation.score(ballot, key, a.candidate), indent=1))


def cmd_run(a):
    if a.pool:
        # Lines written and voiced ahead of play: nothing heavy runs while the game does.
        pool = Path(a.pool)
        lines = [json.loads(r) for r in (pool / "lines.jsonl").read_text(encoding="utf-8").splitlines()]
        voiced = json.loads((pool / "voice.json").read_text(encoding="utf-8"))
        for take in voiced.values():           # stored relative to the pool, so the folder can be moved
            take["file"] = str((pool / take["file"]).resolve())
        staples = json.loads((Path(__file__).with_name("data") / "staples.json").read_text(encoding="utf-8"))
        from .bake import answer_rows, real_rows, soften_repeats, trick_rows
        lines = soften_repeats(lines) + real_rows() + answer_rows() + trick_rows()
        d = Director(bank=Bank(), rng=random.Random())
        print("[jimmie-brain] pool " + json.dumps(d.load_pool(lines, staples, voiced)), flush=True)
    else:
        index, _ = _index(a)
        tts = NullTTS() if a.voice == "null" else QwenCloneTTS(Path(a.voice_model), Path(a.voice_reference))
        renderer = Renderer(tts, Path(a.cache), a.ffmpeg)
        d = Director(writer=_writer(a, index), bank=Bank(), renderer=renderer, rng=random.Random())
    print("[jimmie-brain] ready", flush=True)
    Bridge(d, Path(a.log), Path(a.sav), journal=Path(a.journal) if a.journal else None).run()


def main(argv=None):
    p = argparse.ArgumentParser(prog="jimmie_brain", description=__doc__)
    sub = p.add_subparsers(required=True)

    def common(s):
        s.add_argument("--turns", help="turns.jsonl from the corpus command")
        s.add_argument("--min-speaker", type=float, default=0.5)
        s.add_argument("--llm", default="scripted", help="'scripted' or the base URL of a local OpenAI-compatible server")
        s.add_argument("--model", default="local")
        s.add_argument("--no-retrieval", action="store_true", help="transcript search off: tests what the model itself knows")
        s.add_argument("--seed", type=int, default=0)

    s = sub.add_parser("corpus", help="transcripts -> turns.jsonl"); s.set_defaults(fn=cmd_corpus)
    s.add_argument("transcripts"); s.add_argument("out"); s.add_argument("--splits"); s.add_argument("--speakers")
    s = sub.add_parser("export", help="turns.jsonl -> context/response rows for adapter training"); s.set_defaults(fn=cmd_export)
    s.add_argument("turns"); s.add_argument("out"); s.add_argument("--min-speaker", type=float, default=0.7)
    s.add_argument("--allow-unverified", action="store_true")
    s = sub.add_parser("shadow", help="replay a game log; print what he would say"); s.set_defaults(fn=cmd_shadow)
    s.add_argument("log"); s.add_argument("-v", "--verbose", action="store_true"); common(s)
    s = sub.add_parser("scenes", help="check the rule table on matched scenes; optionally write lines"); s.set_defaults(fn=cmd_scenes)
    s.add_argument("--out"); s.add_argument("--label", default="candidate"); common(s)
    s = sub.add_parser("packet", help="blind ballot from two or more scene runs"); s.set_defaults(fn=cmd_packet)
    s.add_argument("out"); s.add_argument("runs", nargs="+"); s.add_argument("--seed", type=int, default=0)
    s = sub.add_parser("score", help="score a returned ballot"); s.set_defaults(fn=cmd_score)
    s.add_argument("ballot"); s.add_argument("key"); s.add_argument("candidate")
    s = sub.add_parser("run", help="live: follow the game log and feed the game its plan"); s.set_defaults(fn=cmd_run)
    s.add_argument("log"); s.add_argument("sav"); common(s)
    s.add_argument("--voice", choices=("null", "qwen"), default="qwen")
    s.add_argument("--voice-model"); s.add_argument("--voice-reference"); s.add_argument("--cache", default="voice-cache")
    s.add_argument("--ffmpeg", default="ffmpeg"); s.add_argument("--journal")
    s.add_argument("--pool", help="folder from `python -m jimmie_brain.bake`: play from lines written and voiced ahead")
    a = p.parse_args(argv)
    return a.fn(a) or 0


if __name__ == "__main__":
    raise SystemExit(main())
