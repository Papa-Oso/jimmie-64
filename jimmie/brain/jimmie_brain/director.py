"""Decides ahead of time what Jimmie would say to whatever happens next.

The speed problem: a reaction must start within 500 ms of the event, and writing plus voicing
a new line takes longer than that. The answer is the same one a quick person uses: have the
comeback ready. After every fact the director asks, for each thing that could happen next,
"which rule would win, and would he speak?" and hands the game a small plan:

    star:mario                   -> line 41 (written, already voiced and loaded)
    trick_bailed:jimmie:called_bail -> line 7 (his real "Fuck.")
    death:mario                  -> (nothing: stay quiet)

The game executes the plan locally the instant the event fires, with no round trip.
New words are written in the background for the moments that are likely soon, so an
improvised line is as fast as a recording. Slow moments (dead air, arrivals) are answered
reactively through the same plan as an "ambient" line with an expiry.
"""
from __future__ import annotations

import random
import threading
from dataclasses import dataclass, field

from .facts import Fact, LEVEL_NAMES
from .memory import Memory
from .rules import Rule, RuleBook
from .voice import Bank, Take
from .writer import Scene, Veto, Writer

# Events the game must be able to answer instantly. (kind, actor, data)
INSTANT = [
    ("star", "mario", {}), ("death", "mario", {}), ("hurt", "mario", {}), ("fall", "mario", {}),
    ("key", "mario", {}), ("grand_star", "mario", {}),
    ("water_enter", "mario", {}), ("water_enter", "jimmie", {}),
    ("precision_jump", "mario", {}), ("mario_voice", "mario", {"cue": "mamma_mia"}),
    ("trick_approach", "jimmie", {"toward": True}),
    ("trick_bailed", "jimmie", {"condition": "called_bail"}), ("trick_bailed", "jimmie", {"condition": "plain_bail"}),
    ("trick_completed", "jimmie", {"condition": "called_land"}), ("trick_completed", "jimmie", {"condition": "left_land"}),
    ("trick_completed", "jimmie", {"condition": "clean_landing"}),
    ("trick_completed", "jimmie", {"condition": "landing_after_getup"}),
]
INSTANT_KINDS = {k for k, _, _ in INSTANT}
CONTROL_KINDS = {"played", "dropped", "hello", "mode", "hitch", "missed"}


@dataclass
class Line:
    id: int
    text: str
    intent: str
    rule: str
    source: str                  # recorded | written
    bit: str = ""
    file: str | None = None      # ships inside the mod already
    audio: str | None = None     # path to a rendered ogg that must be sent to the game
    seconds: float = 1.5
    requires: dict = field(default_factory=dict)
    scope: str | None = None     # written about this visit: dies with it
    mode: str | None = None
    used: bool = False
    tag: str = ""
    pooled: bool = False         # written and voiced before play; reusable, least-used first
    uses: int = 0
    weight: float = 1.0
    real: bool = False           # his own words from a stream, spoken by the clone
    topics: tuple = ()           # what it is about (data/topics.json)
    level: int | None = None     # written about one place


@dataclass
class Want:
    rule: Rule
    scene: Scene
    requires: dict
    scope: str | None
    mode: str


class Director:
    def __init__(self, rulebook: RuleBook | None = None, writer: Writer | None = None, bank: Bank | None = None,
                 renderer=None, veto: Veto | None = None, rng: random.Random | None = None, ambient_ttl_ms: int = 7000,
                 ready_per_rule: int = 1):
        self.rulebook = rulebook or RuleBook.load()
        self.writer, self.bank, self.renderer = writer, bank or Bank(), renderer
        self.veto = veto or Veto()
        self.rng = rng or random.Random()
        self.memory = Memory()
        self.lock = threading.RLock()
        self.lines: dict[int, Line] = {}
        self.plan: dict[str, dict] = {}
        self.ambient: dict | None = None
        self.wants: list[Want] = []
        self.last_heard: dict[str, float] = {}
        self.ambient_ttl_ms, self.ready_per_rule = ambient_ttl_ms, ready_per_rule
        self.serial = 0
        self.seq = 0
        self.log: list[dict] = []          # decisions, for shadow runs and review
        self._recorded: dict[str, int] = {}
        self._sticky: dict[str, int] = {}  # event key -> line already loaded in the game for it
        self.voiced: dict[str, dict] = {}  # normalised text -> {"file", "seconds"} from the bake
        self.pool_size = 0

    # ------------------------------------------------------------ pool
    def load_pool(self, lines: list[dict], staples: dict, voiced: dict) -> dict:
        """Lines written and voiced ahead of play. Only lines that have audio are taken."""
        from .writer import normal
        self.voiced = voiced
        counts = {"written": 0, "staple": 0, "skipped_no_audio": 0, "vetoed": 0}
        for row in lines:
            take = voiced.get(normal(row["text"]))
            if self.veto.text(row["text"]):
                counts["vetoed"] += 1
            elif not take:
                counts["skipped_no_audio"] += 1
            else:
                self._new_line(text=row["text"], intent=row["intent"], rule=row["rule"], source="written", audio=take["file"],
                               seconds=take["seconds"], mode=row.get("mode"), level=row.get("level"), pooled=True,
                               weight=float(row.get("weight", 1.0)), real=bool(row.get("real")),
                               tag="answer:" + row["answer"] if row.get("answer") else str(row.get("tag") or ""))
                counts["written"] += 1
        for intent, rows in staples.items():
            if not isinstance(rows, list):
                continue
            for text, weight in rows:
                take = voiced.get(normal(text))
                real = self.bank.recording_for(text)
                if self.veto.text(text) or not (take or real):
                    counts["skipped_no_audio"] += 1
                    continue
                self._new_line(text=text, intent=intent, rule="", source="staple", file=real.file if real else None,
                               audio=None if real else take["file"], seconds=1.5 if real else take["seconds"],
                               pooled=True, weight=float(weight))
                counts["staple"] += 1
        self.pool_size = counts["written"] + counts["staple"]
        return counts

    # ------------------------------------------------------------ lines
    # ------------------------------------------------------------ topics
    def _topic_data(self) -> dict:
        if not hasattr(self, "_topic_doc"):
            import json, re
            from pathlib import Path
            doc = json.loads((Path(__file__).with_name("data") / "topics.json").read_text(encoding="utf-8"))
            doc["_match"] = {name: re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b", re.I)
                             for name, words in doc["topics"].items()}
            self._topic_doc, self._thread, self._cues = doc, None, {}
        return self._topic_doc

    def _topics_of(self, text: str) -> tuple:
        return tuple(name for name, rx in self._topic_data()["_match"].items() if rx.search(text))

    def _wanted_topics(self) -> set:
        """Topics the moment suggests: the thread he is on, what just happened, and where they are."""
        doc, now = self._topic_data(), self.memory.now
        wanted = set(doc["places"].get(str(self.memory.level), ()))
        if self._thread and self._thread[1] > now:
            wanted.add(self._thread[0])
        wanted.update(name for name, until in self._cues.items() if until > now)
        return wanted

    # ------------------------------------------------------------ chat
    def _chat_data(self) -> dict:
        if not hasattr(self, "_chat_doc"):
            import json
            from pathlib import Path
            self._chat_doc = json.loads((Path(__file__).with_name("data") / "chat.json").read_text(encoding="utf-8"))
            self._chat_doc["_ignore"] = set(self._chat_doc["ignore"])
        return self._chat_doc

    def _words(self, text: str) -> set:
        """The words of a sentence that say what it is about: longer ones, plurals folded together."""
        import re
        ignore = self._chat_data()["_ignore"]
        found = set()
        for word in re.findall(r"[a-z']+", text.lower()):
            if len(word) >= 3 and word not in ignore:
                found.add(word[:-1] if word.endswith("s") and len(word) > 3 else word)
        return found

    def _answer_data(self) -> dict:
        """The questions he has an answer ready for (data/answers.json), with how telling each word is."""
        if not hasattr(self, "_answer_doc"):
            import json, math
            from pathlib import Path
            path = Path(__file__).with_name("data") / "answers.json"
            doc = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"match": 1.0, "answers": []}
            asks = [(entry["id"], self._plain(ask)) for entry in doc["answers"] for ask in entry["ask"]]
            seen: dict = {}
            for _, words in asks:
                for word in words:
                    seen[word] = seen.get(word, 0) + 1
            # A word in few questions ("old", "skate") says a lot; one in most of them ("you", "do") says little.
            doc["_idf"] = {word: math.log((len(asks) + 1) / n) for word, n in seen.items()}
            doc["_rare"] = math.log(len(asks) + 1)
            doc["_asks"] = asks
            self._answer_doc = doc
        return self._answer_doc

    @staticmethod
    def _plain(text: str) -> frozenset:
        import re
        words = re.findall(r"[a-z0-9]+", text.lower().replace("'", ""))
        short = {"u": "you", "ur": "your", "r": "are", "y": "why", "whats": "what", "wheres": "where", "hows": "how"}
        words = [short.get(w, w) for w in words]
        return frozenset(w[:-1] if w.endswith("s") and len(w) > 3 else w for w in words)

    def _answer_for(self, text: str) -> tuple:
        """The prepared question closest to what was typed: (id, how close 0..1)."""
        doc, words = self._answer_data(), self._plain(text) - {"jimmie", "jimmy", "dude", "bro", "man", "hey", "yo", "so", "lol"}
        weigh = lambda ws: sum(doc["_idf"].get(w, doc["_rare"]) for w in ws)
        mine, best = weigh(words), ("", 0.0)
        for ident, ask in doc["_asks"]:
            both = weigh(words & ask)
            score = both / ((mine * weigh(ask)) ** 0.5) if both and mine else 0.0
            if score > best[1]:
                best = (ident, score)
        return best

    def _hear_chat(self, fact: Fact) -> None:
        """Work out how he takes a typed message: a greeting, a dig, a question, and what it is about."""
        import re
        doc, text = self._chat_data(), " ".join(str(fact.data.get("text") or "").lower().split())
        has = lambda phrase: re.search(r"(?<![a-z'])" + re.escape(phrase) + r"(?![a-z'])", text) is not None
        said = next((kind for kind, words in doc["said"].items() if any(has(w) for w in words)), None)
        asks = text.endswith("?") or any(text.startswith(w + " ") for w in doc["question_starts"])
        if asks and (said in (None, "praise") or (said == "hello" and len(text.split()) > 4)):
            said = "question"                   # "hey do you like pizza?" is a question; "what's up?" is a hello
        if said in ("hello", "praise", "laugh") and len(text.split()) > 5:
            said = None                         # a long message that happens to contain "nice" is about something else
        fact.data["said"] = said or "other"
        topics = self._topics_of(text)
        for name in topics:                     # what the player brought up stays in the air for a while
            self._cues[name] = (fact.ms or self.memory.now) + 45000
        answer, close = self._answer_for(text)
        plain = fact.data["said"] in ("question", "other", "hello", "bye")    # a dig or a compliment keeps its own reply
        if close >= (self._answer_data()["match"] if plain else 0.95)                 and any(l.tag == "answer:" + answer for l in self.lines.values()):
            fact.data["said"] = "question"       # he has an answer ready for exactly this
        else:
            answer = ""
        self._chat = {"said": fact.data["said"], "words": self._words(text), "topics": topics, "answer": answer,
                      "bit": next((bit for bit, words in doc["bits"].items() if any(has(w) for w in words)), "")}
        self.log.append({"ms": fact.ms or self.memory.now, "event": "chat", "text": text, "said": fact.data["said"],
                         "topics": list(topics), "bit": self._chat["bit"], "answer": answer, "close": round(close, 2)})

    def _reply(self, rule: Rule, ctx: dict) -> Line | None:
        """An answer to what was typed: the bit it named, a real line about the same thing, or a plain reply."""
        chat, mem = self._chat, self.memory
        for take in self.bank.bits.get(chat["bit"], ()):
            line = self._recorded_line(take, rule)
            if line and (line.file or line.audio) and line.text not in self._recent_texts(2):
                return line
        if chat["answer"]:                       # a question he has an answer ready for
            line = self._fresh([l for l in self.lines.values() if l.tag == "answer:" + chat["answer"]])
            if line:
                return line
        if chat["said"] in ("question", "other") and self.rng.random() < self._chat_data()["about_share"]:
            pool = [l for l in self.lines.values() if l.pooled and l.real and l.intent != "reply"
                    and l.level in (None, mem.level) and (l.mode is None or l.mode == mem.mode)]
            shared = {}
            for l in pool:
                n = len(chat["words"] & self._words(l.text))
                if n:
                    shared.setdefault(n, []).append(l)
            about = shared[max(shared)] if shared else [l for l in pool if set(chat["topics"]).intersection(l.topics)]
            line = self._fresh(about) if about else None
            if line:
                return line
        return self._pick(rule, ctx, mem)

    # ------------------------------------------------------------ tricks
    def _name_trick(self, trick: str) -> None:
        """He landed something and had nothing ready to say: sometimes he names it."""
        if not hasattr(self, "_trick_doc"):
            import json
            from pathlib import Path
            path = Path(__file__).with_name("data") / "tricks.json"
            self._trick_doc = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"chance": 0.0, "quiet_s": 8}
            self._trick_rule = Rule("trick_name", ("trick_completed",), "boast", lane="ambient")
        doc, mem = self._trick_doc, self.memory
        heard = self.last_heard.get("trick_name")
        last = mem.spoken[-1] if mem.spoken else None
        quiet = heard is not None and mem.now - heard < doc["quiet_s"] * 1000
        just_spoke = last is not None and mem.now - last.ms < self.rulebook.gaps.get(mem.mode, 3.5) * 1000
        if self.rng.random() >= doc["chance"] or self.ambient or mem.now < mem.precision_until or quiet or just_spoke:
            return
        parts = [p[:-4] if p.endswith(" out") else p for p in trick.split(" to ")]
        names = (["_combo"] if len(parts) > 1 and self.rng.random() < 0.5 else []) + parts
        for name in names + [p[6:] for p in parts if p.startswith("fakie ")]:
            line = self._fresh([l for l in self.lines.values() if l.tag == "trick:" + name])
            if line:
                self._set_ambient(line, self._trick_rule)
                self.log.append({"ms": mem.now, "event": "react", "fact": "trick_completed", "reason": "name_trick",
                                 "rule": "trick_name", "trick": trick})
                return

    def _new_line(self, **kw) -> Line:
        self.serial += 1
        line = Line(id=self.serial, **kw)
        line.topics = self._topics_of(line.text)
        self.lines[line.id] = line
        return line

    def _recorded_line(self, take: Take, rule: Rule) -> Line | None:
        """A recording, or a fixed form we voice once and keep. One Line per take, reused."""
        if self.veto.file(take.file) or self.veto.text(take.text):
            return None
        if take.tag in self._recorded:
            return self.lines[self._recorded[take.tag]]
        audio, seconds = None, 1.5
        if not take.file:
            if take.text.startswith("("):       # an original cut we do not have a file name for yet
                return None
            from .writer import normal
            baked = self.voiced.get(normal(take.text))
            if baked:                           # the clone says it until the real cut is wired into bank.json
                audio, seconds = baked["file"], baked["seconds"]
            elif self.renderer:
                path, seconds = self.renderer.ensure(take.text)
                audio = str(path)
        line = self._new_line(text=take.text, intent=rule.intent, rule="", source="recorded", bit=take.bit,
                              file=take.file, audio=audio, seconds=seconds, tag=take.tag)
        self._recorded[take.tag] = line.id
        return line

    def _recent_texts(self, n: int = 10) -> list[str]:
        return [s.text for s in self.memory.spoken[-n:]]

    def _written_ready(self, rule: Rule, ctx: dict, mem: Memory) -> list[Line]:
        return [l for l in self.lines.values()
                if l.source == "written" and l.rule == rule.id and not l.used
                and (l.scope is None or l.scope == mem.scope) and (l.mode is None or l.mode == mem.mode)
                and (l.level is None or l.level == mem.level)
                and all(ctx.get(k) == v for k, v in l.requires.items())]

    def _fresh(self, lines: list[Line], prefer_place: bool = False) -> Line | None:
        """From pooled lines: not something he just said, least-used first, his common ones more often."""
        said = [s.text for s in self.memory.spoken[-8:]]
        for window in (8, 3, 1):                # a small pool may repeat, but never back to back
            fresh = [l for l in lines if l.text not in said[-window:]]
            if fresh:
                break
        lines = fresh
        if not lines:
            return None
        if prefer_place:
            wanted = self._wanted_topics()          # a tangent that connects to the moment, most of the time
            on_topic = [l for l in lines if wanted.intersection(l.topics)]
            if on_topic and self.rng.random() < self._topic_data()["share"]:
                lines = on_topic
        if prefer_place:                        # mostly about where they are, then his own tangents, then anything
            roll, here = self.rng.random(), [l for l in lines if l.level is not None]
            real = [l for l in lines if l.real and l.level is None]
            if here and roll < 0.55:
                lines = here
            elif real and roll < 0.85:
                lines = real
        least = min(l.uses for l in lines)
        lines = [l for l in lines if l.uses == least]
        return self.rng.choices(lines, [l.weight ** 0.5 for l in lines])[0]

    def _pick(self, rule: Rule, ctx: dict, mem: Memory) -> Line | None:
        """A line for this rule in this (possibly hypothetical) context, or None."""
        if rule.bits:
            # Running gags rotate: the one he has gone longest without.
            order = sorted(rule.bits, key=lambda b: (mem.bits.get(b, {}).get("ms", -1.0), self.rng.random()))
            for bit in order:
                for take in self.bank.bits.get(bit, ()):
                    line = self._recorded_line(take, rule)
                    if line and (line.file or line.audio or not self.renderer):
                        return line
            return None
        last = self._recent_texts(1)
        takes = [t for tag in rule.bank if (t := self.bank.takes.get(tag))]
        recorded = [l for t in takes if (l := self._recorded_line(t, rule)) and (not last or l.text != last[0])]
        written = self._written_ready(rule, ctx, mem) if rule.write else []
        if self.pool_size:
            staples = [l for l in self.lines.values() if l.source == "staple" and l.intent == rule.intent] if rule.staple_share else []
            options = {"recorded": rule.bank_share if recorded else 0.0}
            rest = 1.0 - options["recorded"]
            options["staple"] = rest * rule.staple_share if staples else 0.0
            options["written"] = (rest - options["staple"]) if written else 0.0
            if not written and staples:
                options["staple"] = rest
            for _ in range(3):                  # a class that turns out empty hands its share to the others
                live = {k: v for k, v in options.items() if v > 0}
                if not live:
                    break
                kind = self.rng.choices(list(live), list(live.values()))[0]
                line = (self.rng.choice(recorded) if kind == "recorded"
                        else self._fresh(staples) if kind == "staple" else self._fresh(written, prefer_place=True))
                if line:
                    return line
                options[kind] = 0.0
            return None
        if written and recorded:
            return self.rng.choice(recorded) if self.rng.random() < rule.bank_share else written[0]
        if written:
            return written[0]
        if recorded:
            return self.rng.choice(recorded)
        return None

    def _scene(self, rule: Rule, mem: Memory, ctx: dict) -> Scene:
        last = mem.spoken[-1] if mem.spoken else None
        return Scene(mode=mem.mode, place=LEVEL_NAMES.get(mem.level, ""), story=mem.story(), moment=rule.direction,
                     intent=rule.intent, last_said=last.text if last else "",
                     last_said_s=(mem.now - last.ms) / 1000.0 if last else 0.0,
                     stars=mem.stars or None, actor=str(ctx.get("actor", "mario")),
                     facts={k: ctx.get(k) for k in rule.presume})

    def _want(self, rule: Rule, mem: Memory, ctx: dict) -> None:
        if not (rule.write and self.writer):
            return
        if len(self._written_ready(rule, ctx, mem)) >= self.ready_per_rule + (1 if rule.payoff else 0):
            return
        requires = {k: ctx.get(k) for k in rule.presume}
        if any(w.rule.id == rule.id and w.requires == requires for w in self.wants):
            return
        scene = self._scene(rule, mem, ctx)
        # A line written about what happened on this visit must not outlive it.
        scope = mem.scope if (scene.story or requires) else None
        self.wants.append(Want(rule, scene, requires, scope, mem.mode))

    # ------------------------------------------------------------ facts in
    def observe(self, fact: Fact) -> None:
        with self.lock:
            if fact.kind == "played":
                self._heard(fact)
                return
            if fact.kind in ("dropped", "hello", "hitch"):
                return
            self._topic_data()
            if fact.kind == "chat":
                self._hear_chat(fact)
            for name in self._topic_data()["events"].get(fact.kind, ()):   # what just happened suggests a topic
                self._cues[name] = (fact.ms or self.memory.now) + 30000
            if fact.kind == "missed":           # a line he was about to say never got out; say why in the journal
                self.log.append({"ms": fact.ms, "event": "missed", "rule": fact.data.get("rule"), "why": fact.data.get("why")})
                if self.ambient and self.ambient["line"] == fact.data.get("line"):
                    self.ambient = None
                    self.seq += 1
                return
            armed = fact.key in self.plan       # the game already had a line ready for exactly this
            self.memory.observe(fact)
            if fact.kind not in INSTANT_KINDS and fact.kind not in CONTROL_KINDS:
                self._react(fact)
            self.replan()
            if fact.kind == "trick_completed" and fact.data.get("trick") and not armed:
                self._name_trick(str(fact.data["trick"]))

    def _heard(self, fact: Fact) -> None:
        line = self.lines.get(int(fact.data.get("line") or 0))
        at = fact.ms or self.memory.now
        if not line:
            if fact.data.get("legacy") and fact.data.get("tag"):
                # A line the older Lua played on its own: still something he audibly said.
                take = self.bank.takes.get(str(fact.data["tag"]))
                self.memory.heard("legacy:" + str(fact.data["tag"]), take.text if take else "", "legacy", ms=at)
            return
        if line.topics:                         # stay on this thread for a little while
            self._thread = (line.topics[0], at + self._topic_data()["stay_s"] * 1000)
        if line.pooled:
            line.uses += 1
        elif line.source == "written":
            line.used = True
        rule_id = str(fact.data.get("rule") or line.rule)
        self.memory.heard(str(line.id), line.text, str(fact.data.get("intent") or line.intent), line.bit, ms=at)
        if rule_id:
            self.last_heard[rule_id] = at
        if self.ambient and self.ambient["line"] == line.id:
            self.ambient = None
        self.log.append({"ms": at, "event": "heard", "line": line.id, "text": line.text, "rule": rule_id,
                         "source": "real" if line.real else line.source, "topics": list(line.topics), "sound": line.audio or line.file})
        self.replan()

    def _react(self, fact: Fact) -> None:
        """Slow lane: something happened that the game could not have been pre-armed for."""
        ctx = self.memory.context(fact)
        decision = self.rulebook.decide(ctx, self.last_heard, self.memory.now, self.rng)
        if fact.kind != "tick" or decision.speak:
            self.log.append({"ms": self.memory.now, "event": "react", "fact": fact.key, "reason": decision.reason,
                             "rule": decision.rule.id if decision.rule else None})
        if not decision.speak:
            return
        rule = decision.rule
        line = self._reply(rule, ctx) if fact.kind == "chat" else self._pick(rule, ctx, self.memory)
        if line is None:
            self._want(rule, self.memory, ctx)   # the writer will deliver; see accept()
            return
        self._set_ambient(line, rule)
        if fact.kind == "chat":                  # he may be mid-sentence; the answer waits for him to finish
            self.ambient["expires"] += 6000

    def _set_ambient(self, line: Line, rule: Rule) -> None:
        self.ambient = {"line": line.id, "expires": self.memory.now + self.ambient_ttl_ms + rule.delay_ms,
                        "scope": self.memory.scope, "rule": rule.id, "intent": rule.intent, "delay": rule.delay_ms}
        self.seq += 1

    def tick(self, now_ms: float) -> None:
        """Called every couple of seconds by the bridge with the estimated game clock."""
        self.observe(Fact("tick", "game", ms=now_ms, mode=self.memory.mode, scope=self.memory.scope, level=self.memory.level))

    # ------------------------------------------------------------ planning
    def replan(self) -> None:
        with self.lock:
            mem = self.memory
            if self.ambient and (mem.now > self.ambient["expires"] or self.ambient["scope"] != mem.scope):
                self.ambient = None
                self.seq += 1
            self.wants = [w for w in self.wants if w.scope is None or w.scope == mem.scope]
            for dead in [i for i, l in self.lines.items() if l.source == "written" and l.scope not in (None, mem.scope)]:
                del self.lines[dead]      # written about a visit that is over
            plan: dict[str, dict] = {}
            for kind, actor, data in INSTANT:
                data = dict(data)
                if kind == "star":
                    data["stars"] = mem.stars + 1
                fact = Fact(kind, actor, ms=mem.now, mode=mem.mode, scope=mem.scope, level=mem.level, data=data)
                after = mem.peek(fact)
                ctx = after.context(fact)
                # The dice for each possible event are rolled once per plan; a rule that loses stays quiet.
                decision = self.rulebook.decide(ctx, self.last_heard, mem.now, self.rng)
                if decision.rule and decision.rule.write and not decision.rule.quiet:
                    self._want(decision.rule, after, ctx)
                if not decision.speak:
                    continue
                # Keep the line the game already has loaded for this event unless it stopped fitting,
                # so a tick does not make the game load seventeen new sounds every two seconds.
                kept = self.lines.get(self._sticky.get(fact.key, -1))
                if kept and kept.pooled and (kept.rule == decision.rule.id or (kept.source == "staple" and kept.intent == decision.rule.intent)) \
                        and kept.text not in {s.text for s in mem.spoken[-8:]} and (kept.level is None or kept.level == mem.level) \
                        and (kept.mode is None or kept.mode == mem.mode):
                    line = kept
                else:
                    line = self._pick(decision.rule, ctx, after)
                if line is None:
                    continue
                self._sticky[fact.key] = line.id
                plan[fact.key] = {"line": line.id, "delay": decision.rule.delay_ms, "scope": mem.scope,
                                  "rule": decision.rule.id, "intent": decision.rule.intent}
            if plan != self.plan:
                self.plan = plan
                self.seq += 1

    # ------------------------------------------------------------ writing
    def next_want(self) -> Want | None:
        with self.lock:
            # Payoffs first: an unanswered "watch this" is the worst silence.
            self.wants.sort(key=lambda w: (not w.rule.payoff, w.rule.lane != "ambient"))
            return self.wants.pop(0) if self.wants else None

    def accept(self, want: Want, text: str | None) -> Line | None:
        """A finished draft comes back from the writer (text None/empty = it chose quiet or failed)."""
        if not text:
            return None
        audio, seconds = None, max(0.5, 0.33 * len(text.split()))
        file = None
        real = self.bank.recording_for(text)
        if real:                                  # he wrote something we have him actually saying
            file = real.file
        elif self.renderer:
            path, seconds = self.renderer.ensure(text)
            audio = str(path)
        with self.lock:
            if want.scope is not None and want.scope != self.memory.scope:
                return None                       # the visit ended while he was thinking
            if self.veto.text(text):
                return None
            line = self._new_line(text=text, intent=want.rule.intent, rule=want.rule.id, source="written", file=file,
                                  audio=audio, seconds=seconds, requires=want.requires, scope=want.scope, mode=want.mode)
            self.log.append({"ms": self.memory.now, "event": "written", "line": line.id, "text": text, "rule": want.rule.id})
            if want.rule.lane == "ambient" or want.rule.id.startswith("arrive"):
                ctx = self.memory.context()
                if all(ctx.get(k) == v for k, v in want.requires.items()) and not ctx["precision"] and not self.ambient:
                    self._set_ambient(line, want.rule)
            self.replan()
            return line

    def write_one(self) -> Line | None:
        """Take the most urgent want, write it, keep the result. Safe to call from a worker thread."""
        want = self.next_want()
        if not want or not self.writer:
            return None
        with self.lock:   # do not write what he just said, or what is already waiting to be said
            avoid = self._recent_texts() + [l.text for l in self.lines.values() if l.source == "written" and not l.used]
        draft = self.writer.write(want.scene, max_words=want.rule.max_words, recent=avoid)
        if draft is not None and draft.rejected:
            with self.lock:
                self.log.append({"ms": self.memory.now, "event": "rejected", "rule": want.rule.id, "lines": draft.rejected})
        return self.accept(want, draft.text if draft else None)

    # ------------------------------------------------------------ plan out
    def document(self) -> dict:
        """Everything the game needs right now: the lines to have loaded and when to use them."""
        with self.lock:
            needed = {e["line"] for e in self.plan.values()}
            if self.ambient:
                needed.add(self.ambient["line"])
            return {"seq": self.seq,
                    "lines": [self.lines[i] for i in sorted(needed)],
                    "plan": dict(self.plan),
                    "ambient": dict(self.ambient) if self.ambient else None}
