"""Real stream speech: parsing, tagging, retrieval, fingerprint and training export.

The transcripts are Whisper cues of roughly 40 seconds that mix Jimmie with
donation text-to-speech, guests and game audio. Nothing here pretends otherwise:
every turn carries a speaker score (None until the speaker pass has run) and
flags, and every consumer chooses what it is willing to trust.
"""
from __future__ import annotations

import json
import math
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path

CUE_TIME = re.compile(r"(\d+):(\d\d):(\d\d)[,.](\d{3}) --> (\d+):(\d\d):(\d\d)[,.](\d{3})")
VOD_ID = re.compile(r"\[(\d{6,})\]")
WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

PROFANITY = {
    "fuck": ("fuck", "fucking", "fucked", "fucker", "fuckers", "motherfucker", "motherfucking", "fucks", "fuckin"),
    "shit": ("shit", "shits", "shitty", "bullshit", "shitballs"),
    "hell": ("hell",), "ass": ("ass", "asses", "asshole", "dumbass"),
    "damn": ("damn", "goddamn", "dammit", "goddammit"), "bitch": ("bitch", "bitches", "bitching"),
    "piss": ("piss", "pissed", "pissing"), "dick": ("dick", "dicks", "dickhead"), "cock": ("cock", "cocks"),
}
PROFANE_WORDS = {w for forms in PROFANITY.values() for w in forms}
ADDRESS = ("dude", "guys", "son", "buddy", "man", "bro", "boys", "ladies", "baby")
# People talking TO him (donation TTS, guests) say his name. He rarely does.
NAMES_HIM = re.compile(r"\b(jimm(y|ie)|jim jam|jimbo|floppy ?jimm(y|ie))\b", re.I)
PACE_TALK = re.compile(r"\b(pb|personal best|world record|wr|splits?|timer|pace|sum of best|gold)\b", re.I)
STREAM_ADMIN = re.compile(
    r"\b(thank you (so much|guys)|thanks for the|resub|subs?\b|gifted|bits\b|raid|follow(ers?)?\b|prediction|"
    r"good morning|good night|tts\b|chat\b|mods?\b|stream(ing|er)?\b|emotes?)\b", re.I)

# Social moves a line can perform. Lexical tags are leads for retrieval, not labels of truth.
INTENT_LEXICON = {
    "celebrate": r"\b(let'?s (fucking )?go|fuck yes|fuck yeah|holy shit|yes+!|there it is|we did it|nailed|got it|beautiful|that'?s what i'?m talking about|hell yeah|oh my god)\b",
    "own_it": r"\b(i fucked up|my bad|i'?m (so |fucking )?(bad|stupid|dumb|an idiot)|that was (so )?bad|i suck|i blew it|i choked|fuck me)\b",
    "save_face": r"\b(meant to do that|on purpose|not terrible|not (that )?bad|i'?m fine|it'?s fine|whatever|doesn'?t matter|i don'?t care|who cares)\b",
    "boast": r"\b(watch this|easy|too easy|told you|i told you|i'?m (so |fucking )?good|check this|here we go|i got this|no problem|nothing to it|like a glove)\b",
    "disbelief": r"\b(unbelievable|unreal|no way|are you (fucking )?kidding|what the (fuck|hell)|what is (this|happening)|how|why would|you'?ve got to be|come on)\b",
    "needle": r"\b(you (fucking )?(idiot|pussy|suck)|what are you doing|what the fuck (are you|is wrong)|nice one|good job|really\?|seriously|where are you going|the fuck is wrong with you)\b",
    "relief": r"\b(thank (god|fuck|christ)|finally|oh thank|phew|okay,? okay|there we go|about (fucking )?time)\b",
    "greet": r"\b(what'?s (up|happening|going on)|good morning|hello|hey|welcome|how are (you|we)|look who)\b",
    "ramble": r"\b(you know what|i was thinking|let me (tell|explain)|the thing is|i mean|you ever|one time|back in|remember when|speaking of)\b",
    "nerves": r"\b(please|don'?t (fuck|choke|die)|oh no|oh god|oh fuck|i can'?t (watch|look)|here it comes|careful|shit shit)\b",
}
INTENT_RX = {k: re.compile(v, re.I) for k, v in INTENT_LEXICON.items()}
STOP = set("the a an and or but of to in on at for with is are was were be been it its it's this that i you he she we they "
           "me my your our their so just not no do does did have has had will would can could if then than as from by "
           "about up out what when where who how all there here s t don".split())


def tokens(text: str) -> list[str]:
    return WORD.findall(text.lower())


@dataclass
class Turn:
    id: str                 # vod/cue/sentence
    vod: str
    split: str              # train | development | test | unassigned
    start: float
    end: float
    text: str
    prev: str = ""          # preceding sentences in the same stretch of talk
    game: str = ""          # hint from the stream title
    speaker: float | None = None   # 0..1 after the speaker pass; None = unverified
    flags: list[str] = field(default_factory=list)
    intents: list[str] = field(default_factory=list)

    @property
    def words(self) -> int:
        return len(tokens(self.text))


def parse_srt(path: Path):
    """Yield (index, start_s, end_s, text) for each cue."""
    block: list[str] = []
    for raw in Path(path).read_text(encoding="utf-8-sig", errors="replace").splitlines() + [""]:
        line = raw.strip()
        if line:
            block.append(line)
            continue
        if len(block) >= 3 and (m := CUE_TIME.fullmatch(block[1])):
            g = [int(x) for x in m.groups()]
            start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
            end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
            index = int(block[0]) if block[0].isdigit() else -1
            yield index, start, end, " ".join(block[2:])
        block = []


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in SENTENCE_END.split(text) if p.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def tag_turn(turn: Turn) -> None:
    text, n = turn.text, turn.words
    if NAMES_HIM.search(text):
        turn.flags.append("names_him")
    if STREAM_ADMIN.search(text):
        turn.flags.append("stream_admin")
    if PACE_TALK.search(text):
        turn.flags.append("pace_talk")
    if n > 30 and not re.search(r"[.!?,]", text):
        turn.flags.append("unpunctuated")
    if n == 0:
        turn.flags.append("empty")
    turn.intents = [k for k, rx in INTENT_RX.items() if rx.search(text)]


def game_hint(title: str) -> str:
    t = title.lower()
    for key, name in (("mario", "sm64"), ("earthworm", "ewj3d"), ("horror", "horror"), ("marble", "marbles")):
        if key in t:
            return name
    return ""


def load_splits(path: Path | None) -> dict[str, str]:
    if not path or not Path(path).is_file():
        return {}
    return {vod: row.get("split", "unassigned") for vod, row in json.loads(Path(path).read_bytes())["sessions"].items()}


def load_speaker_scores(folder: Path | None, vod: str):
    """Optional sidecar from tools/speaker_pass.py: [[start_s, end_s, score], ...] sorted by start."""
    if not folder:
        return None
    p = Path(folder) / f"{vod}.json"
    return json.loads(p.read_bytes())["intervals"] if p.is_file() else None


def _score(intervals, start, end):
    if not intervals:
        return None
    total = weight = 0.0
    for a, b, s in intervals:
        if b <= start:
            continue
        if a >= end:
            break
        overlap = min(b, end) - max(a, start)
        total += overlap * s
        weight += overlap
    return round(total / weight, 3) if weight > 0 else None


def build_turns(transcripts: Path, splits: dict[str, str] | None = None, speakers: Path | None = None,
                context_sentences: int = 3) -> list[Turn]:
    """Sentence-level turns with interpolated times and the talk that led into them."""
    splits = splits or {}
    turns: list[Turn] = []
    for srt in sorted(Path(transcripts).glob("*.srt")):
        m = VOD_ID.search(srt.name)
        if not m:
            continue
        vod = m.group(1)
        hint = game_hint(srt.stem)
        intervals = load_speaker_scores(speakers, vod)
        recent: list[tuple[float, str]] = []
        for index, start, end, text in parse_srt(srt):
            sentences = split_sentences(text)
            total = sum(len(s) for s in sentences) or 1
            at = start
            for i, sentence in enumerate(sentences, 1):
                span = (end - start) * len(sentence) / total
                # Talk older than 25 s is a different moment.
                prev = " ".join(t for when, t in recent[-context_sentences:] if at - when <= 25)
                turn = Turn(id=f"vod/{vod}/{index}/{i}", vod=vod, split=splits.get(vod, "unassigned"),
                            start=round(at, 2), end=round(at + span, 2), text=sentence, prev=prev, game=hint,
                            speaker=_score(intervals, at, at + span))
                tag_turn(turn)
                turns.append(turn)
                recent.append((at, sentence))
                at += span
    return turns


def save_turns(turns: list[Turn], path: Path) -> None:
    with Path(path).open("w", encoding="utf-8", newline="\n") as f:
        for t in turns:
            f.write(json.dumps(asdict(t), ensure_ascii=False) + "\n")


def load_turns(path: Path) -> list[Turn]:
    with Path(path).open(encoding="utf-8") as f:
        return [Turn(**json.loads(line)) for line in f if line.strip()]


def usable(turn: Turn, min_speaker: float = 0.5, max_words: int = 22, min_words: int = 1) -> bool:
    """A turn we are willing to show the writer as 'this is how he talks'."""
    if any(f in turn.flags for f in ("names_him", "unpunctuated", "empty", "pace_talk")):
        return False
    if turn.speaker is not None and turn.speaker < min_speaker:
        return False
    return min_words <= turn.words <= max_words


class Index:
    """BM25 over usable turns of chosen splits, with intent buckets for social-move retrieval."""

    def __init__(self, turns: list[Turn], splits=("train",), k1: float = 1.4, b: float = 0.6, **filters):
        self.turns = [t for t in turns if t.split in splits and usable(t, **filters)]
        self.k1, self.b = k1, b
        self.docs = [[w for w in tokens(t.text) if w not in STOP] for t in self.turns]
        self.lengths = [len(d) or 1 for d in self.docs]
        self.avg = sum(self.lengths) / max(1, len(self.lengths))
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for i, doc in enumerate(self.docs):
            for word, count in Counter(doc).items():
                self.postings[word].append((i, count))
        n = len(self.docs)
        self.idf = {w: math.log(1 + (n - len(p) + 0.5) / (len(p) + 0.5)) for w, p in self.postings.items()}
        self.by_intent: dict[str, list[int]] = defaultdict(list)
        for i, t in enumerate(self.turns):
            for intent in t.intents:
                self.by_intent[intent].append(i)

    def search(self, query: str, k: int = 8, among: set[int] | None = None) -> list[tuple[float, Turn]]:
        scores: dict[int, float] = defaultdict(float)
        for word in {w for w in tokens(query) if w not in STOP}:
            idf = self.idf.get(word)
            if not idf:
                continue
            for i, count in self.postings[word]:
                if among is not None and i not in among:
                    continue
                norm = count + self.k1 * (1 - self.b + self.b * self.lengths[i] / self.avg)
                scores[i] += idf * count * (self.k1 + 1) / norm
        best = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
        return [(s, self.turns[i]) for i, s in best]

    def exemplars(self, intent: str, k: int = 8, rng: random.Random | None = None, query: str = "",
                  prefer_game: str = "sm64") -> list[Turn]:
        """Real turns that perform this social move: some matched to the scene words, the rest a varied sample."""
        rng = rng or random.Random(0)
        pool = self.by_intent.get(intent) or list(range(len(self.turns)))
        chosen: list[int] = []
        seen: set[str] = set()

        def take(i):
            key = " ".join(tokens(self.turns[i].text))
            if key and key not in seen:
                seen.add(key)
                chosen.append(i)

        if query:
            where = {id(t): i for i, t in enumerate(self.turns)}
            for _, t in self.search(query, k=max(2, k // 3), among=set(pool)):
                take(where[id(t)])
        # Half from streams of this game when there are any, the rest from everywhere.
        in_game = [i for i in pool if self.turns[i].game == prefer_game]
        for i in rng.sample(in_game, min(len(in_game), k)):
            if len(chosen) >= max(len(chosen), k // 2 + (1 if query else 0)) and len(chosen) >= k // 2:
                break
            take(i)
        for i in rng.sample(pool, min(len(pool), k * 4)):
            if len(chosen) >= k:
                break
            take(i)
        return [self.turns[i] for i in chosen[:k]]


# ---------------------------------------------------------------- fingerprint

def line_features(text: str) -> dict[str, float]:
    words = tokens(text)
    n = len(words) or 1
    counts = Counter(words)
    last = words[-1] if words else ""
    return {
        "words": float(len(words)),
        "profane": sum(1 for w in words if w in PROFANE_WORDS) / n,
        "fuck": sum(1 for w in words if w in PROFANITY["fuck"]) / n,
        "has_profanity": float(any(w in PROFANE_WORDS for w in words)),
        "has_address": float(any(w in ADDRESS for w in words)),
        "suffix_address": float(last in ADDRESS),
        "suffix_son": float(last == "son"),
        "question": float(text.rstrip().endswith("?")),
        "exclaim": float(text.rstrip().endswith("!")),
        "repeat": float(any(c >= 2 for w, c in counts.items() if w not in STOP and len(w) > 2)),
        "short": float(len(words) <= 3),
    }


def fingerprint(lines: list[str]) -> dict[str, float]:
    """Mean of per-line features plus length quartiles. Compare two of these to detect drift."""
    lines = [l for l in lines if l and tokens(l)]
    if not lines:
        return {}
    rows = [line_features(l) for l in lines]
    out = {k: round(sum(r[k] for r in rows) / len(rows), 4) for k in rows[0]}
    lengths = sorted(r["words"] for r in rows)
    out["words_p25"], out["words_p50"], out["words_p75"] = (lengths[int(q * (len(lengths) - 1))] for q in (.25, .5, .75))
    out["n"] = len(lines)
    return out


DRIFT_KEYS = ("has_profanity", "fuck", "has_address", "suffix_son", "question", "exclaim", "repeat", "short")


def drift(reference: dict[str, float], candidate: dict[str, float]) -> dict[str, float]:
    """Per-feature difference (candidate - reference) and one summary number. Zero is identical."""
    diffs = {k: round(candidate.get(k, 0) - reference.get(k, 0), 4) for k in DRIFT_KEYS}
    ref_len = max(1.0, reference.get("words_p50", 1))
    diffs["words_p50_ratio"] = round(candidate.get("words_p50", 0) / ref_len, 3)
    diffs["distance"] = round(math.sqrt(sum(diffs[k] ** 2 for k in DRIFT_KEYS)), 4)
    return diffs


# ------------------------------------------------------------ training export

def training_rows(turns: list[Turn], splits=("train",), min_speaker: float = 0.7, require_verified: bool = True):
    """Context -> his actual next turn. With require_verified, unverified speech yields zero rows on purpose."""
    for t in turns:
        if t.split not in splits or not usable(t, min_speaker=min_speaker, max_words=40):
            continue
        if require_verified and t.speaker is None:
            continue
        if "stream_admin" in t.flags:
            continue
        yield {"id": t.id, "vod": t.vod, "context": t.prev, "game": t.game, "response": t.text}
