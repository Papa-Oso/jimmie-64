"""New words in his voice, and the checks that keep them honest.

The writer is given three things and nothing else:
  the scene      only what the game witnessed and what he audibly said;
  the move       what this line is for (from the winning rule);
  real lines     things he actually said while doing the same move elsewhere.
Evidence that real examples beat trait descriptions: agents conditioned on a person's own
words reproduce that person far better than agents given a profile (Park et al., 2024).
With retrieval off the same prompt is sent without the real lines; that is the condition
that tests whether a fine-tuned model has learned him.
"""
from __future__ import annotations

import json
import random
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .corpus import PACE_TALK, tokens, line_features

DATA = Path(__file__).with_name("data")

IDENTITY = (
    "You write what Jimmie says out loud. Jimmie (floppyjimmie) is a real streamer and skateboarder. "
    "Right now he is skating alongside Mario inside Super Mario 64. Mario is the player and never talks. "
    "Jimmie is loud, loose, cocky and funny, and warmer than he lets on.\n"
    "How he actually talks (measured across 109 hours of his streams):\n"
    "- Short. Half of what he says is five words or fewer.\n"
    "- He swears inside ordinary sentences, not only in outbursts: fuck, fucking, shit, holy shit, god damn.\n"
    "- He hangs a name on the end: son, dude, buddy, man, sweetie, ladies, boys.\n"
    "- He repeats himself (Okay. Okay. / Come on, come on.) and restarts sentences halfway.\n"
    "- His everyday reactions: Oh my god. / Holy shit! / Come on. / Let's go. / There we go. / It's fine. / "
    "Not a big deal. / Are you kidding me? / What the hell is going on? / That's what I'm talking about. / "
    "Hit the road, dude. / We'll take it. / Don't need it.\n"
    "- He announces things like a host, asks questions to nobody, and treats absurd things with total seriousness.\n"
    "Hard rules:\n"
    "- Only things listed in SCENE happened. Never add events, counts, places or outcomes.\n"
    "- Mario does the jumping, the stars, the dying. Jimmie does the skateboarding. Never swap them.\n"
    "- No advice, directions, tips, technique names, times, pace or records. He is company, not a coach.\n"
    "- Never explain a joke. Never mention being in a game mod, an AI, chat, subs or donations.\n"
    "- Spoken words only: no stage directions, no emoji, no quotation marks.\n"
)

ASK = ("Write {n} different things he might say right now, one per line, each at most {max_words} words. "
       "Short is better. Vary how they start. Do not number them. "
       "Every line must make sense for THE MOMENT by itself; borrow his rhythm, not a whole REAL LINE that is about something else. "
       "If saying nothing is the better call, make one of the lines a single dash.")

COACHING = re.compile(
    r"\b(you (should|need to|have to|gotta|got to|wanna|want to|might want)|try (to|the|going|using|a)\b|"
    r"go (left|right|up|down|around|back|through|for the)|take the|use the|(jump|climb|swim|run) (on|onto|to|over|up|across)\b|"
    r"next (star|up|one is)|head (to|for|over)|don'?t forget|remember to|make sure (to|you)|the trick is|you can just)\b", re.I)
JARGON = re.compile(
    r"\b(blj|backwards? long ?jump|cannonless|lakitu skip|mips clip|clip (through|into)|frame[- ]perfect|sub-?pixel|"
    r"any ?%|(16|70|120)[- ]star|tas\b|rta\b|speed ?run(ner|ning)?s?|strats?|setup|cycle|rng|hitbox|wall ?kick)\b", re.I)
META = re.compile(r"\b(as an ai|language model|chat\b|subs?\b|subscri|donat|follow(er|ing)?s?\b|twitch|stream(er|ing)?\b|viewers?|mod\b|npc)\b", re.I)
PACE_MORE = re.compile(r"\b\d{1,2}:\d\d\b|\bseconds? (ahead|behind)\b|\b(ahead|behind) (of )?(pace|schedule)\b|\brecord\b", re.I)
FORMAT = re.compile(r"[*_#\[\](){}<>\"“”]|[^\x00-\x7F’…—]")
# Mario's deeds claimed by Jimmie, and Jimmie's skating pinned on Mario.
WRONG_ACTOR = re.compile(
    r"\b(i|we) (just )?(got|grabbed|collected|found) (the|that|a|another) (star|key)\b|\bi (just )?died\b|"
    r"\b(you|mario) (just )?(landed|bailed|ollied|kickflipped|ate shit)\b|\byour (board|kickflip|ollie|trick|skating)\b|"
    r"\bnice (kickflip|ollie|trick)\b", re.I)
NUMBER_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen".split())}
STAR_COUNT = re.compile(r"\b(\d+|" + "|".join(NUMBER_WORDS) + r")(st|nd|rd|th)? (more )?stars?\b", re.I)
ORDINAL = re.compile(r"\b(first|second|third|fourth|fifth|\d+(st|nd|rd|th)) (star|time|death|try|attempt)\b", re.I)


def normal(text: str) -> str:
    return " ".join(tokens(text))


class Veto:
    def __init__(self, path: Path = DATA / "veto.json"):
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        self.texts = [normal(t) for t in raw.get("texts", [])]
        self.patterns = [re.compile(p, re.I) for p in raw.get("patterns", [])]
        self.files = {f.lower() for f in raw.get("files", [])}

    def text(self, line: str) -> bool:
        n = normal(line)
        return any(t and t in n for t in self.texts) or any(p.search(line) for p in self.patterns)

    def file(self, name: str | None) -> bool:
        return bool(name) and str(name).replace("\\", "/").rsplit("/", 1)[-1].lower() in self.files


@dataclass
class Scene:
    """Everything the writer may know. Built from Memory; nothing here is inferred."""
    mode: str = "free"
    place: str = ""
    story: list = field(default_factory=list)       # witnessed events, plain words
    moment: str = ""                                 # the rule's direction
    intent: str = ""
    last_said: str = ""
    last_said_s: float = 0.0
    stars: int | None = None
    actor: str = "mario"
    facts: dict = field(default_factory=dict)        # presumed context values, for the record


def build_messages(scene: Scene, exemplars: list[str], n: int = 5, max_words: int = 10) -> tuple[str, str]:
    lines = ["SCENE"]
    lines.append("- Mode: " + ("a 16-star speedrun attempt; Mario is busy" if scene.mode == "16" else "free exploration; no hurry"))
    if scene.place:
        lines.append(f"- Place: {scene.place}")
    for event in scene.story:
        lines.append(f"- {event}")
    if scene.last_said:
        lines.append(f"- The last thing Jimmie said out loud, {round(scene.last_said_s)}s ago: {scene.last_said}")
    lines.append("")
    lines.append("THE MOMENT")
    lines.append(scene.moment or "React as he would.")
    if exemplars:
        lines.append("")
        lines.append("REAL LINES (things he actually said in other situations; copy the rhythm and attitude, not the topics)")
        lines.extend(f"- {e}" for e in exemplars)
    lines.append("")
    lines.append(ASK.format(n=n, max_words=max_words))
    return IDENTITY, "\n".join(lines)


def clean(raw: str) -> list[str]:
    """Model output -> candidate lines. Strips numbering and wrappers; keeps a lone dash as 'quiet'."""
    out = []
    for line in raw.replace("\r", "").split("\n"):
        line = line.strip()
        line = re.sub(r"^(\d+[.)]|[-*•])\s+", "", line)
        line = line.strip().strip('"“”').strip()
        line = re.sub(r"^(jimmie|jimmy)\s*:\s*", "", line, flags=re.I)
        if line:
            out.append(line)
    return out


def lint(line: str, scene: Scene, veto: Veto, max_words: int = 10, recent: list[str] = ()) -> list[str]:
    """Reasons this line may not be spoken. Empty means it passed."""
    reasons = []
    words = tokens(line)
    if not words:
        return ["empty"]
    if len(words) > max_words:
        reasons.append("too_long")
    if FORMAT.search(line):
        reasons.append("format")
    if veto.text(line):
        reasons.append("owner_veto")
    if PACE_TALK.search(line) or PACE_MORE.search(line):
        reasons.append("pace")
    if COACHING.search(line):
        reasons.append("coaching")
    if JARGON.search(line):
        reasons.append("jargon")
    if META.search(line):
        reasons.append("meta")
    if WRONG_ACTOR.search(line):
        reasons.append("wrong_actor")
    for m in STAR_COUNT.finditer(line):
        raw = m.group(1).lower()
        value = int(raw) if raw.isdigit() else NUMBER_WORDS[raw]
        if scene.stars is None or value != scene.stars:
            reasons.append("invented_count")
            break
    if ORDINAL.search(line) and "invented_count" not in reasons:
        # "second time" is only safe when the scene itself counts; presumed facts carry those numbers.
        if not any(isinstance(v, int) and v >= 2 for v in scene.facts.values()):
            reasons.append("invented_count")
    n = normal(line)
    if any(n == normal(r) for r in recent):
        reasons.append("repeat")
    return reasons


def score(line: str, recent: list[str], rng: random.Random) -> float:
    """Among lines that passed: short, not starting like the last few, with a little luck."""
    f = line_features(line)
    s = -abs(f["words"] - 4.5) * 0.35
    openers = {" ".join(tokens(r)[:2]) for r in recent[-5:]}
    if " ".join(tokens(line)[:2]) in openers:
        s -= 2.0
    return s + rng.random() * 1.5


class ChatLLM:
    """Any OpenAI-compatible local server (llama.cpp, as the project already runs)."""

    def __init__(self, base_url: str = "http://127.0.0.1:8080", model: str = "local", timeout: float = 12.0):
        self.base_url, self.model, self.timeout = base_url.rstrip("/"), model, timeout

    def complete(self, system: str, user: str, temperature: float = 0.9, max_tokens: int = 160, seed: int | None = None) -> str:
        body = {"model": self.model, "temperature": temperature, "top_p": 0.95, "max_tokens": max_tokens, "stream": False,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if seed is not None:
            body["seed"] = seed
        request = urllib.request.Request(self.base_url + "/v1/chat/completions", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
        # Local server only: never route through a system proxy.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=self.timeout) as response:
            return json.load(response)["choices"][0]["message"]["content"]


STAND_IN = """Holy shit, dude.|Okay. Okay.|What the fuck was that?|Unbelievable.|Oh my god, son.|There it is.|No way.
Are you fucking kidding me?|Fuck yeah, son.|I'm fine. I'm fine.|Unreal.|Come on, dude.|That's what I'm talking about.
Well, that happened.|Shit balls.|Easy. Easy.|What is happening?|Jesus Christ, buddy.|Alright, alright, alright.
Wow.|God damn, son.|Not terrible, though.|Let's fucking go.|Yeah, no, that tracks.|Oh, fuck me.|Beautiful.
I meant to do that.|You good, buddy?|Dude. Dude.|That was fucking clean.|Whatever, man.|Oh, come on, son!
Holy shit balls.|So that's how it is.|Fucking finally.|Look at this guy.|I can't. I can't.|Yep.|Nice. Real nice.
What a fucking day.""".replace("\n", "|").split("|")


class ScriptedLLM:
    """Stand-in for tests and dry runs. It is NOT Jimmie: it deals from a fixed deck so the plumbing can be exercised."""

    def __init__(self, table: dict[str, str] | None = None, default: str | None = None):
        self.table, self.default, self.calls = table or {}, default, []

    def complete(self, system, user, **kw):
        self.calls.append((system, user, kw))
        for key, text in self.table.items():
            if key in user:
                return text
        if self.default is not None:
            return self.default
        at = (len(self.calls) - 1) * 5
        return "\n".join(STAND_IN[(at + i) % len(STAND_IN)] for i in range(5))


@dataclass
class Draft:
    text: str
    rejected: list            # [(line, [reasons])]
    candidates: int
    quiet_offered: bool


class Writer:
    def __init__(self, llm, index=None, veto: Veto | None = None, retrieval: bool = True, rng: random.Random | None = None,
                 exemplar_count: int = 8, candidates: int = 5):
        self.llm, self.index, self.veto = llm, index, veto or Veto()
        self.retrieval, self.rng = retrieval, rng or random.Random()
        self.exemplar_count, self.candidates = exemplar_count, candidates

    def exemplars(self, scene: Scene) -> list[str]:
        if not (self.retrieval and self.index):
            return []
        corpus_intent = {"take_credit": "boast", "boast_call": "boast", "hype_nerves": "nerves", "fake_sympathy": "needle",
                         "deadpan": "disbelief", "sincere": "celebrate", "callback": "ramble", "laugh": "celebrate"}
        intent = corpus_intent.get(scene.intent, scene.intent)
        query = " ".join(scene.story[-2:]) + " " + scene.moment
        return [t.text for t in self.index.exemplars(intent, self.exemplar_count, self.rng, query=query)]

    def write(self, scene: Scene, max_words: int = 10, recent: list[str] = (), seed: int | None = None) -> Draft | None:
        """One line that passed every check, or None for quiet. Never raises on model trouble."""
        system, user = build_messages(scene, self.exemplars(scene), self.candidates, max_words)
        try:
            raw = self.llm.complete(system, user, seed=seed)
        except Exception:
            return None
        lines = clean(raw)
        quiet = any(l in ("-", "—", "...") for l in lines)
        passed, rejected = [], []
        for line in lines:
            if line in ("-", "—", "..."):
                continue
            reasons = lint(line, scene, self.veto, max_words, list(recent))
            (rejected.append((line, reasons)) if reasons else passed.append(line))
        if not passed:
            return Draft("", rejected, len(lines), quiet)
        best = max(passed, key=lambda l: score(l, list(recent), self.rng))
        return Draft(best, rejected, len(lines), quiet)
