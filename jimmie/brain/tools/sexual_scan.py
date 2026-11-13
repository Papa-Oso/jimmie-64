"""List every sentence in the transcripts on hand that is sexual, so the line pickers know what to avoid.

    python tools/sexual_scan.py            scan work/turns.jsonl (streams) and the transcriber's clip transcripts

Writes work/sexual_hits.json: one entry per distinct sentence with where it was said and which
words matched. This is a word match, not a judgement: tools that pick lines treat a match as
"needs a person or a careful reader", and work/adult-catalogue/SEXUAL_LINES.md is the reviewed list made from it.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
TRANSCRIBER = HERE.parent.parent / "twitch-vod-transcribe"

# Body parts, acts, and porn terms. Deliberately broad; plain swearing ("fuck", "shit", "ass", "bitch") is not sexual.
WORDS = (r"sex\w*|porn\w*|dick\w*|cock\w*|penis\w*|boner\w*|erect\w*|balls|ballsack\w*|nutsack\w*|testicl\w*|scrotum|"
         r"puss(?:y|ies)|vagina\w*|clit\w*|cunt\w*|tit|tits|titt\w*|boob\w*|nipple\w*|breast\w*|"
         r"cum|cums|cumm\w*|jizz\w*|semen|sperm\w*|ejaculat\w*|orgasm\w*|climax\w*|horny|aroused|arousal|"
         r"jerk(?:ing|ed|s)? (?:off|it|him|me)|jack(?:ing|ed|s)? (?:off|it)|masturbat\w*|fap\w*|strok(?:e|ing) (?:it|my|his)|"
         r"blow ?job\w*|blowj\w*|hand ?job\w*|rim ?job\w*|suck(?:ing|ed|s)? (?:my|his|a|on (?:my|his|a)|it off)|deep ?throat\w*|"
         r"fuck(?:ing|ed|s)? (?:her|him)|get(?:ting)? laid|bang(?:ing|ed)? (?:her|him|your|my)|"
         r"anal|butthole\w*|asshole lick\w*|butt ?plug\w*|dildo\w*|vibrator\w*|fleshlight\w*|lube|condom\w*|"
         r"nude\w*|naked|strip(?:per|pers|ping)|hooker\w*|prostitut\w*|whore\w*|slut\w*|escort\w*|onlyfans|only fans|"
         r"fetish\w*|kink\w*|bdsm|bondage|foot (?:pics|fetish)|feet pics|thong\w*|panties|lingerie|"
         r"rape\w*|raping|molest\w*|pedo\w*|grope\w*|groping|incest\w*|"
         r"hentai|milf\w*|gilf\w*|threesome\w*|orgy|orgies|gangbang\w*|creampie\w*|squirt\w*|"
         r"pubes?|pubic|taint|gooch|queef\w*|moan(?:ing|ed|s)?|thrust\w*|hump(?:ing|ed|s)?|"
         r"sugar (?:daddy|baby)|twink\w*|trann\w*|lesbian\w*|make out|making out|french kiss\w*|"
         r"sext\w*|nudes|dick pic\w*|wet dream\w*|virgin\w*|bust(?:ing|ed)? a nut|nut(?:ted|ting)|nutted|coom\w*|goon(?:ing|ed)?")
RX = re.compile(r"\b(?:" + WORDS + r")\b", re.I)
SENT = re.compile(r"(?<=[.!?])\s+")


def main() -> int:
    hits: dict[str, dict] = {}
    words = Counter()

    def take(text: str, where: str) -> None:
        text = " ".join(text.split())
        found = sorted({m.group(0).lower() for m in RX.finditer(text)})
        if not found or len(text) < 8:
            return
        key = text.lower()
        row = hits.setdefault(key, {"text": text, "words": found, "where": []})
        if len(row["where"]) < 3:
            row["where"].append(where)
        row["count"] = row.get("count", 0) + 1
        words.update(found)

    n = 0
    with (HERE / "work/turns.jsonl").open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            n += 1
            take(r["text"], f"stream {r['vod']} at {int(r['start']) // 3600}:{int(r['start']) % 3600 // 60:02d}:{int(r['start']) % 60:02d}")
    clips = 0
    for p in sorted((TRANSCRIBER / "transcripts/clips").glob("*.txt")):
        body = p.read_text(encoding="utf-8", errors="replace")
        body = body.split("\n\n", 1)[1] if "\n\n" in body else body          # skip the header block
        clips += 1
        for s in SENT.split(body):
            take(s, f"clip {p.stem[:60]}")
    out = sorted(hits.values(), key=lambda r: r["text"].lower())
    (HERE / "work/sexual_hits.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{n} stream sentences, {clips} clips read; {len(out)} distinct sentences matched")
    print(", ".join(f"{w} {c}" for w, c in words.most_common(60)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
