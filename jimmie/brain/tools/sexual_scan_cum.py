"""Second pass for one word the speech recogniser usually spells differently: "cum" heard as "come".

    python tools/sexual_scan_cum.py

Writes work/sexual_hits_cum.json in the same shape as sexual_hits.json: sentences where come / came /
coming is used in a way that may be sexual, and that the first scan did not already match.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "tools"))
import sexual_scan  # noqa: E402

COME = r"(?:come|comes|came|coming|comin|cummin|cumming|cummed)"
RX = re.compile(
    r"\b(?:"
    + COME + r" (?:on|in|inside|all over|into|onto|down|up) (?:my|your|his|her|their|the|a|me|you|him|it)\b"
    r"|" + COME + r" (?:in|on|all over) (?:my|your|his|her) (?:pants|face|mouth|hand|hands|ass|butt|chest|hair|shorts|jeans|bed|sock|socks)"
    r"|(?:make|made|makes|making) (?:me|you|him|her|them|it) " + COME + r"\b"
    r"|(?:gonna|going to|about to|wanna|want to|tryna|trying to|just|almost|already|never|can't|couldn't|didn't) " + COME + r"\b(?! (?:back|here|over|out|up|down|on\b|in\b|to|through|with|from|around|by|home|along|for|at|off|across|into|after|before|and|get|see|say|play|watch|check|hang))"
    r"|" + COME + r" (?:so hard|hard|twice|too fast|too quick|quick|early|buckets|a lot|everywhere)"
    r"|(?:load|loads|shot a|shoot a|shooting a|blow a|blew a|bust a|busted a)\b[^.?!]{0,20}\b(?:load|loads|rope|ropes)"
    r"|pre ?come|precum|come ?shot|cum ?shot|come stain\w*|cum stain\w*|come sock\w*|come rag\w*|come dumpster\w*|come guzzl\w*|"
    r"(?:my|his|your|the|some|that|this|of|with|in|covered in|full of|drink|drinking|eat|eating|swallow\w*|taste\w*|tasting) come\b(?! (?:on|back|here|true|up|over|and|to|from|in|out|down))"
    r")", re.I)


def main() -> int:
    hits: dict[str, dict] = {}

    def take(text: str, where: str) -> None:
        text = " ".join(text.split())
        if sexual_scan.RX.search(text):          # the first scan already has it
            return
        found = sorted({m.group(0).lower() for m in RX.finditer(text)})
        if not found or len(text) < 8:
            return
        row = hits.setdefault(text.lower(), {"text": text, "words": found, "where": []})
        if len(row["where"]) < 3:
            row["where"].append(where)
        row["count"] = row.get("count", 0) + 1

    with (HERE / "work/turns.jsonl").open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            take(r["text"], f"stream {r['vod']} at {int(r['start']) // 3600}:{int(r['start']) % 3600 // 60:02d}:{int(r['start']) % 60:02d}")
    for p in sorted((sexual_scan.TRANSCRIBER / "transcripts/clips").glob("*.txt")):
        body = p.read_text(encoding="utf-8", errors="replace")
        body = body.split("\n\n", 1)[1] if "\n\n" in body else body
        for s in sexual_scan.SENT.split(body):
            take(s, f"clip {p.stem[:60]}")
    out = sorted(hits.values(), key=lambda r: r["text"].lower())
    (HERE / "work/sexual_hits_cum.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(out)} more sentences where come/came/coming may mean cum")
    for r in out[:12]:
        print("  ", r["text"][:120])
    return 0


if __name__ == "__main__":
    sys.exit(main())
