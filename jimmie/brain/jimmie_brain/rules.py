"""When a moment deserves a line, and which social move it is.

This is the dynamic-dialog pattern Valve described for Left 4 Dead: every rule is a list of
criteria over the current facts; the rule that matches with the MOST criteria wins, so a
specific rule ("third death in a row on this visit") beats a general one ("Mario died").
Two additions matter for Jimmie:
  * the winner then rolls its own chance. Losing the roll means quiet. It never falls through
    to a vaguer rule, so silence is something the table chooses on purpose;
  * rules are data. Tuning his timing is editing JSON, not writing another Lua module.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT = Path(__file__).with_name("data") / "rules.json"
OPS = {
    "gte": lambda a, b: a >= b, "lte": lambda a, b: a <= b, "gt": lambda a, b: a > b, "lt": lambda a, b: a < b,
    "ne": lambda a, b: a != b, "in": lambda a, b: a in b, "nin": lambda a, b: a not in b,
}


def _blank(expected):
    if isinstance(expected, bool):
        return False
    if isinstance(expected, (int, float)):
        return 0
    if isinstance(expected, (list, tuple)):
        return _blank(expected[0]) if expected else ""
    return ""


def holds(criterion, actual_or_missing, present: bool) -> bool:
    if isinstance(criterion, dict):
        for op, expected in criterion.items():
            actual = actual_or_missing if present else _blank(expected)
            try:
                if not OPS[op](actual, expected):
                    return False
            except TypeError:
                return False
        return True
    actual = actual_or_missing if present else _blank(criterion)
    return actual == criterion


@dataclass
class Rule:
    id: str
    on: tuple                      # fact kinds
    intent: str
    when: dict = field(default_factory=dict)
    lane: str = "instant"          # instant: planned ahead and played by the game; ambient: generated when it fires
    chance: float = 1.0
    cooldown_s: float = 0.0
    bank: tuple = ()               # recorded takes that fit
    bits: tuple = ()               # lore bits; fixed forms only, never rewritten
    write: bool = False            # may the writer improvise here
    bank_share: float = 0.5        # when both exist, how often to use the recording
    staple_share: float = 0.5      # of the rest, how often one of his everyday lines instead of a written one
    presume: tuple = ()            # context keys a written line's wording depends on
    delay_ms: int = 0              # deliberate timing: a beat of silence before a deadpan
    payoff: bool = False           # answers an audible claim; ignores the talk gap
    precision_ok: bool = False     # allowed while Mario is lining something up
    direction: str = ""            # the move, in plain words, for the writer
    max_words: int = 10
    weight: float = 1.0

    @property
    def quiet(self) -> bool:
        return self.intent == "quiet"

    def specificity(self) -> int:
        return len(self.when)


@dataclass
class Decision:
    rule: Rule | None
    speak: bool
    reason: str

    @property
    def intent(self) -> str:
        return self.rule.intent if self.rule and self.speak else "quiet"


class RuleBook:
    def __init__(self, rules: list[Rule], gaps: dict | None = None):
        self.rules = rules
        self.gaps = gaps or {"16": 6.0, "free": 3.5}
        self.by_kind: dict[str, list[Rule]] = {}
        for rule in rules:
            for kind in rule.on:
                self.by_kind.setdefault(kind, []).append(rule)
        ids = [r.id for r in rules]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate rule id")

    @classmethod
    def load(cls, path: Path = DEFAULT) -> "RuleBook":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        rules = []
        for row in raw["rules"]:
            row = dict(row)
            on = row.pop("on")
            row.pop("note", None)
            for key in ("bank", "bits", "presume"):
                if key in row:
                    row[key] = tuple(row[key])
            rules.append(Rule(on=tuple([on] if isinstance(on, str) else on), **row))
        return cls(rules, raw.get("gaps"))

    def match(self, ctx: dict) -> list[Rule]:
        """Every rule whose criteria all hold, most specific first."""
        found = [r for r in self.by_kind.get(ctx.get("fact", ""), ())
                 if all(holds(c, ctx.get(k), k in ctx) for k, c in r.when.items())]
        return sorted(found, key=lambda r: (-r.specificity(), -r.weight, r.id))

    def decide(self, ctx: dict, last_heard: dict[str, float], now_ms: float, rng: random.Random) -> Decision:
        """last_heard: rule id -> game ms when a line from that rule last actually played."""
        found = self.match(ctx)
        if not found:
            return Decision(None, False, "no_rule")
        top = found[0].specificity()
        tied = [r for r in found if r.specificity() == top]
        rule = tied[0] if len(tied) == 1 else rng.choices(tied, [r.weight for r in tied])[0]
        if rule.quiet:
            return Decision(rule, False, "rule_is_quiet")
        if ctx.get("precision") and not rule.precision_ok:
            return Decision(rule, False, "precision")
        if not rule.payoff and ctx.get("since_spoke_s", 1e9) < self.gaps.get(str(ctx.get("mode")), 3.5):
            return Decision(rule, False, "just_spoke")
        heard = last_heard.get(rule.id)
        if rule.cooldown_s and heard is not None and now_ms - heard < rule.cooldown_s * 1000:
            return Decision(rule, False, "cooldown")
        if rng.random() >= rule.chance:
            return Decision(rule, False, "chance")
        return Decision(rule, True, "speak")
