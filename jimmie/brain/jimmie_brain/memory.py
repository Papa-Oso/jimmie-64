"""What Jimmie knows right now: what happened, what he said aloud, and how the session feels.

Two rules keep him honest:
  * a line is remembered only when the game confirms it started playing;
  * anything tied to a visit dies when the scope changes (warp, reset, new file).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

from .corpus import tokens
from .facts import Fact, LEVEL_NAMES


@dataclass
class Spoken:
    ms: float
    line_id: str
    text: str
    intent: str
    bit: str = ""
    scope: str = ""


@dataclass
class Memory:
    now: float = 0.0
    mode: str = "free"
    scope: str = ""
    level: int = 0
    session: dict = field(default_factory=lambda: {"stars": 0, "deaths": 0, "bails": 0, "lands": 0, "visits": 0})
    visit: dict = field(default_factory=dict)          # counters for this scope only
    streak: dict = field(default_factory=lambda: {"bails": 0, "lands": 0, "deaths": 0})
    last_fact: dict = field(default_factory=dict)      # kind -> ms
    recent: list = field(default_factory=list)         # last facts, newest last
    spoken: list = field(default_factory=list)         # Spoken, newest last
    bits: dict = field(default_factory=dict)           # bit -> {"n": uses, "ms": last}
    claim: dict | None = None                          # an audible boast awaiting its outcome
    levels_seen: dict = field(default_factory=dict)    # level -> visits
    tilt: float = 0.0                                  # 0..100, how badly it is going
    hype: float = 0.0                                  # 0..100, how well
    last_decay: float = 0.0
    stars: int = 0
    precision_until: float = 0.0
    idle_since: float = 0.0
    watching: bool = False
    entered: float = 0.0

    # ------------------------------------------------------------ updates
    def _decay(self, now: float) -> None:
        if self.last_decay and now > self.last_decay:
            # Half-life of about 90 seconds: moods fade unless the game keeps feeding them.
            factor = 0.5 ** ((now - self.last_decay) / 90000.0)
            self.tilt *= factor
            self.hype *= factor
        self.last_decay = max(self.last_decay, now)

    def _enter_scope(self, fact: Fact) -> None:
        self.scope = fact.scope
        self.entered = self.now
        self.visit = {}
        self.claim = None
        self.streak["deaths"] = 0
        self.precision_until = 0.0
        if fact.level:
            self.level = fact.level
            self.levels_seen[fact.level] = self.levels_seen.get(fact.level, 0) + 1
        self.session["visits"] += 1

    def observe(self, fact: Fact) -> None:
        self.now = max(self.now, fact.ms)
        self._decay(self.now)
        if fact.mode in ("16", "free"):
            self.mode = fact.mode
        if fact.scope and fact.scope != self.scope:
            self._enter_scope(fact)
        elif fact.level and fact.level != self.level:
            self.level = fact.level
        bump = lambda table, key: table.__setitem__(key, table.get(key, 0) + 1)
        k, who = fact.kind, fact.actor
        if isinstance(fact.data.get("n"), int):
            self.stars = fact.data["n"]            # the game's own count, as of just before this fact
        if k == "star":
            bump(self.session, "stars"); bump(self.visit, "stars")
            self.stars = int(fact.data.get("stars") or self.stars + 1)
            self.hype = min(100, self.hype + 30)
            self.tilt *= 0.5
            self.streak["deaths"] = 0
        elif k == "death" and who == "mario":
            bump(self.session, "deaths"); bump(self.visit, "deaths"); bump(self.streak, "deaths")
            self.tilt = min(100, self.tilt + 25)
            self.hype *= 0.5
        elif k in ("setback", "hurt", "fall") and who == "mario":
            bump(self.visit, "setbacks")
            self.tilt = min(100, self.tilt + 8)
        elif k == "trick_bailed":
            bump(self.session, "bails"); bump(self.visit, "bails"); bump(self.streak, "bails")
            self.streak["lands"] = 0
        elif k == "trick_completed":
            bump(self.session, "lands"); bump(self.visit, "lands"); bump(self.streak, "lands")
            self.streak["bails"] = 0
        elif k in ("precision_setup", "precision_attempt"):
            self.precision_until = self.now + 6000
        elif k == "idle":
            self.idle_since = self.idle_since or self.now - float(fact.data.get("s", 0)) * 1000
        elif k == "watch":
            self.watching = bool(fact.data.get("on"))
        if k not in ("idle", "watch", "tick"):
            self.idle_since = 0.0
        if k in ("trick_bailed", "trick_completed"):
            self.claim = None
        self.last_fact[fact.key] = self.now
        self.last_fact[k] = self.now
        self.recent.append({"kind": k, "actor": who, "ms": self.now, "scope": fact.scope, **fact.data})
        del self.recent[:-24]

    def heard(self, line_id: str, text: str, intent: str, bit: str = "", ms: float | None = None) -> None:
        """The game confirmed this line started. Only now does it exist for callbacks and repetition."""
        at = self.now if ms is None else ms
        self.now = max(self.now, at)
        self.spoken.append(Spoken(at, line_id, text, intent, bit, self.scope))
        del self.spoken[:-40]
        if bit:
            row = self.bits.setdefault(bit, {"n": 0, "ms": 0.0})
            row["n"] += 1
            row["ms"] = at
        if intent == "boast_call":
            self.claim = {"ms": at, "text": text, "scope": self.scope}

    # ------------------------------------------------------------- queries
    def peek(self, fact: Fact) -> "Memory":
        """Memory as it would be if this fact happened next. Used to plan before the event."""
        other = copy.deepcopy(self)
        other.observe(fact)
        return other

    def since(self, key: str) -> float:
        at = self.last_fact.get(key)
        return (self.now - at) / 1000.0 if at else 1e9

    def context(self, fact: Fact | None = None) -> dict:
        """Flat facts for rule matching. Every value is something the game witnessed or he audibly said."""
        last = self.spoken[-1] if self.spoken else None
        claim_live = bool(self.claim and self.claim["scope"] == self.scope and self.now - self.claim["ms"] < 12000)
        ctx = {
            "mode": self.mode, "level": self.level, "level_name": LEVEL_NAMES.get(self.level, ""),
            "stars": self.stars, "stars_session": self.session["stars"], "stars_visit": self.visit.get("stars", 0),
            "deaths_session": self.session["deaths"], "deaths_visit": self.visit.get("deaths", 0),
            "deaths_streak": self.streak["deaths"], "setbacks_visit": self.visit.get("setbacks", 0),
            "bails_streak": self.streak["bails"], "lands_streak": self.streak["lands"],
            "bails_visit": self.visit.get("bails", 0), "lands_visit": self.visit.get("lands", 0),
            "level_visits": self.levels_seen.get(self.level, 0),
            "tilt": round(self.tilt), "hype": round(self.hype),
            "called": claim_live,
            "since_spoke_s": round((self.now - last.ms) / 1000.0, 1) if last else 1e9,
            "last_intent": last.intent if last else "", "last_bit": last.bit if last else "",
            "last_said": " ".join(tokens(last.text)) if last else "",
            "lines_visit": sum(1 for s in self.spoken if s.scope == self.scope),
            "precision": self.now < self.precision_until,
            "idle_s": round((self.now - self.idle_since) / 1000.0, 1) if self.idle_since else 0.0,
            "watching": self.watching,
            "visit_s": round((self.now - self.entered) / 1000.0, 1) if self.entered else 0.0,
        }
        for bit, row in self.bits.items():
            ctx[f"bit_n.{bit}"] = row["n"]
            ctx[f"bit_since_s.{bit}"] = round((self.now - row["ms"]) / 1000.0, 1)
        if fact is not None:
            ctx.update(fact=fact.kind, actor=fact.actor, key=fact.key)
            for name, value in fact.data.items():
                if isinstance(value, (str, int, float, bool)):
                    ctx[f"f.{name}"] = value
        return ctx

    def story(self, limit: int = 6) -> list[str]:
        """Recent witnessed events in plain words for the writer. No interpretation, no intent."""
        names = {"star": "{a} collected a star", "death": "{a} died", "setback": "{a} fell and lost progress",
                 "hurt": "{a} got hurt", "fall": "{a} fell a long way", "key": "{a} got a Bowser key",
                 "trick_bailed": "Jimmie bailed a skate trick", "trick_completed": "Jimmie landed a skate trick",
                 "water_enter": "{a} went into the water", "arrival": "they arrived in a new area",
                 "precision_setup": "{a} lined up a difficult jump", "grand_star": "{a} beat Bowser for good"}
        out = []
        for row in self.recent:
            if row["scope"] != self.scope or row["kind"] not in names:
                continue
            ago = round((self.now - row["ms"]) / 1000.0)
            if row["kind"] == "arrival" and ago > 15:
                continue
            out.append(names[row["kind"]].format(a=row["actor"].capitalize()) + (f" ({ago}s ago)" if ago > 2 else " (just now)"))
        return out[-limit:]
