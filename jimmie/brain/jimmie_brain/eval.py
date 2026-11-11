"""Evidence that does not depend on anyone's opinion of their own work.

  rule_check      every matched scene picks the rule (and the silence) it should
  generate        the same scenes through any writer configuration
  authorship_auc  can a simple classifier tell his real held-out lines from generated ones?
                  0.5 means it cannot. A machine version of "a stranger sorted all 24 correctly".
  copy_rate       how much of the output is lifted verbatim from the training streams
  packet/score    a blind ballot for people who know him, and the pre-registered pass mark
"""
from __future__ import annotations

import hashlib
import html
import json
import math
import random
from collections import Counter
from pathlib import Path

from .corpus import fingerprint, drift, tokens
from .director import Director
from .facts import Fact
from .rules import RuleBook
from .writer import Writer, normal, lint, Veto

DATA = Path(__file__).with_name("data")


def load_scenes(path: Path = DATA / "scenes.json") -> list[dict]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [{**raw["defaults"], **s} for s in raw["scenes"]]


def stage(scene: dict, rulebook: RuleBook | None = None):
    """Replay a scene's facts through real memory. Returns (director, final fact, winning rule or None)."""
    d = Director(rulebook=rulebook or RuleBook.load(), rng=random.Random(0))
    now = 1_000_000.0

    def fact(row):
        return Fact(row["kind"], row.get("actor", "mario"), ms=now, mode=scene["mode"],
                    scope=row.get("scope", scene["scope"]), level=scene["level"], data=dict(row.get("data", {})))

    d.memory.observe(Fact("arrival", "mario", ms=now, mode=scene["mode"], scope=scene["scope"],
                          level=scene.get("start_level", scene["level"])))
    for row in scene["facts"]:
        now += row.get("dt", 1000)
        if "said" in row:
            d.memory.heard("scripted", row["said"], row.get("intent", ""), ms=now)
        else:
            d.memory.observe(fact(row))
    now += scene["final"].get("dt", 1000)
    final = fact(scene["final"])
    after = d.memory.peek(final)
    ctx = after.context(final)
    found = d.rulebook.match(ctx)
    rule = found[0] if found else None
    return d, final, rule, after, ctx


def rule_check(scenes: list[dict] | None = None) -> list[dict]:
    """Each scene's winning rule and whether it agrees with the scene's expectation."""
    rows = []
    for scene in scenes or load_scenes():
        d, final, rule, after, ctx = stage(scene)
        speaks = bool(rule and not rule.quiet and not (ctx.get("precision") and not rule.precision_ok))
        rows.append({"scene": scene["id"], "rule": rule.id if rule else None, "intent": rule.intent if rule else "quiet",
                     "speaks": speaks, "expected": scene["expect"], "ok": speaks == (scene["expect"] == "speak")})
    return rows


def generate(writer: Writer | None, label: str, scenes: list[dict] | None = None, seed: int = 0) -> list[dict]:
    """One row per scene: what this configuration would have him say (or '' for quiet)."""
    rows = []
    for i, scene in enumerate(scenes or load_scenes()):
        d, final, rule, after, ctx = stage(scene)
        row = {"scene": scene["id"], "family": scene["family"], "note": scene["note"], "label": label,
               "rule": rule.id if rule else None, "text": "", "source": "quiet", "rejected": []}
        if rule and not rule.quiet and not (ctx.get("precision") and not rule.precision_ok):
            line = None
            if rule.bits or (rule.bank and not rule.write):
                line = d._pick(rule, ctx, after)
            if line:
                row.update(text=line.text, source="recorded")
            elif rule.write and writer:
                writer.rng = random.Random(seed * 1000 + i)
                draft = writer.write(d._scene(rule, after, ctx), max_words=rule.max_words, seed=seed * 1000 + i)
                if draft:
                    row.update(text=draft.text, source="written" if draft.text else "quiet", rejected=draft.rejected)
        rows.append(row)
    return rows


# ------------------------------------------------------------ objective metrics

def _features(text: str) -> list[str]:
    words = tokens(text)
    grams = words + [a + "_" + b for a, b in zip(words, words[1:])]
    return grams + [f"len{min(len(words), 12)}", "q" if text.rstrip().endswith("?") else "nq"]


def authorship_auc(real: list[str], generated: list[str], folds: int = 5, seed: int = 0) -> float:
    """Cross-validated naive Bayes: probability a random generated line scores 'more generated' than a real one."""
    data = [(t, 0) for t in real] + [(t, 1) for t in generated]
    if min(len(real), len(generated)) < folds:
        return float("nan")
    rng = random.Random(seed)
    rng.shuffle(data)
    scored = []
    for k in range(folds):
        train = [d for i, d in enumerate(data) if i % folds != k]
        test = [d for i, d in enumerate(data) if i % folds == k]
        counts = (Counter(), Counter())
        docs = [0, 0]
        for text, y in train:
            counts[y].update(_features(text))
            docs[y] += 1
        vocab = len(set(counts[0]) | set(counts[1])) + 1
        totals = [sum(c.values()) for c in counts]
        for text, y in test:
            llr = math.log((docs[1] + 1) / (docs[0] + 1))
            for f in _features(text):
                llr += math.log((counts[1][f] + 1) / (totals[1] + vocab)) - math.log((counts[0][f] + 1) / (totals[0] + vocab))
            scored.append((llr, y))
    pos = [s for s, y in scored if y == 1]
    neg = [s for s, y in scored if y == 0]
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return round(wins / (len(pos) * len(neg)), 3)


def copy_rate(lines: list[str], train_texts: list[str], min_words: int = 4) -> float:
    known = {normal(t) for t in train_texts}
    long = [l for l in lines if len(tokens(l)) >= min_words]
    return round(sum(normal(l) in known for l in long) / len(long), 3) if long else 0.0


def report(rows: list[dict], real_heldout: list[str], train_texts: list[str]) -> dict:
    texts = [r["text"] for r in rows if r["source"] == "written" and r["text"]]
    veto = Veto()
    return {
        "label": rows[0]["label"] if rows else "",
        "scenes": len(rows), "written": len(texts),
        "quiet": sum(r["source"] == "quiet" for r in rows),
        "rejected_candidates": Counter(reason for r in rows for _, reasons in r["rejected"] for reason in reasons),
        "owner_veto_hits": sum(veto.text(t) for t in texts),
        "copy_rate": copy_rate(texts, train_texts),
        "authorship_auc": authorship_auc(real_heldout, texts) if texts else None,
        "drift": drift(fingerprint(real_heldout), fingerprint(texts)) if texts and real_heldout else None,
    }


# ------------------------------------------------------------ blind listening

def packet(runs: dict[str, list[dict]], out: Path, seed: int = 0) -> None:
    """A self-contained ballot page. Labels are hidden; the key is written separately."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    labels = sorted(runs)
    scenes = [r["scene"] for r in runs[labels[0]]]
    key, cards = {}, []
    for i, scene_id in enumerate(scenes):
        options = [(label, next(r for r in runs[label] if r["scene"] == scene_id)) for label in labels]
        rng.shuffle(options)
        note = options[0][1]["note"]
        key[scene_id] = [label for label, _ in options]
        choices = "".join(
            f'<label><input type="radio" name="s{i}" value="{n}"> <b>{chr(65 + n)}</b> '
            f'{html.escape(row["text"]) if row["text"] else "<i>(he says nothing)</i>"}</label>'
            for n, (_, row) in enumerate(options))
        extra = "".join(f'<label><input type="radio" name="s{i}" value="{v}"> {t}</label>'
                        for v, t in (("both", "Both sound like him"), ("neither", "Neither"), ("unsure", "Not sure")))
        cards.append(f'<section data-scene="{html.escape(scene_id)}"><h3>{i + 1}. {html.escape(note)}</h3>{choices}{extra}'
                     f'<label class="fit"><input type="checkbox" name="f{i}"> The one I picked also fits this moment</label></section>')
    page = f"""<!doctype html><meta charset="utf-8"><title>Which one is Jimmie?</title>
<style>body{{font:16px/1.5 system-ui;max-width:46rem;margin:2rem auto;padding:0 1rem;background:#fff;color:#111}}
section{{border-top:1px solid #ccc;padding:1rem 0}}label{{display:block;margin:.35rem 0}}h3{{font-size:1rem}}
.fit{{color:#555}}button{{font:inherit;padding:.5rem 1rem}}</style>
<h1>Which one is Jimmie?</h1>
<p>For each moment, pick the line that sounds most like something he would actually say there.
Go with your gut. There are no trick questions and saying nothing is a real option.</p>
<form id="f">{''.join(cards)}<p><button type="button" onclick="save()">Save my answers</button></p></form>
<script>function save(){{const out={{}};document.querySelectorAll('section').forEach((s,i)=>{{
const c=document.querySelector('input[name=s'+i+']:checked');
out[s.dataset.scene]={{pick:c?c.value:null,fits:document.querySelector('input[name=f'+i+']').checked}}}});
const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(out,null,1)],{{type:'application/json'}}));
a.download='ballot.json';a.click()}}</script>"""
    (out / "ballot.html").write_text(page, encoding="utf-8")
    (out / "KEY-do-not-open-before-voting.json").write_text(json.dumps(
        {"order": key, "sha256": hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()}, indent=1), encoding="utf-8")


def score(ballot: dict, key: dict, candidate: str, pass_mark: float = 2 / 3) -> dict:
    """Pre-registered: win = 1, 'both' = 1/2, 'neither'/'unsure'/loss = 0, over ALL scenes; pass at two thirds."""
    order = key["order"]
    points, tally = 0.0, Counter()
    for scene, labels in order.items():
        pick = (ballot.get(scene) or {}).get("pick")
        if pick is None:
            tally["blank"] += 1
        elif pick in ("both", "neither", "unsure"):
            tally[pick] += 1
            points += 0.5 if pick == "both" else 0.0
        else:
            won = labels[int(pick)] == candidate
            tally["candidate" if won else "other"] += 1
            points += 1.0 if won else 0.0
    share = points / len(order) if order else 0.0
    return {"candidate": candidate, "share": round(share, 3), "passed": share >= pass_mark, "tally": dict(tally),
            "fits": sum(1 for s in order if (ballot.get(s) or {}).get("fits"))}
