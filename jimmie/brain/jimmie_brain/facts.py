"""Game events, normalised. The game is the only authority on what happened and who did it."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

# Log prefixes the existing builds already print, plus the brain link's own.
PREFIXES = ("[jb] ", "[j16] ", "[jimmie-social] ", "[jimmie-skate-memory] ", "[jimmie-v2] ")

LEVEL_NAMES = {
    4: "Big Boo's Haunt", 5: "Cool, Cool Mountain", 6: "the castle", 7: "Hazy Maze Cave", 8: "Shifting Sand Land",
    9: "Bob-omb Battlefield", 10: "Snowman's Land", 11: "Wet-Dry World", 12: "Jolly Roger Bay", 13: "Tiny-Huge Island",
    14: "Tick Tock Clock", 15: "Rainbow Ride", 16: "the castle grounds", 17: "Bowser in the Dark World",
    18: "Vanish Cap", 19: "Bowser in the Fire Sea", 20: "the Secret Aquarium", 21: "Bowser in the Sky",
    22: "Lethal Lava Land", 23: "Dire, Dire Docks", 24: "Whomp's Fortress", 26: "the castle courtyard",
    27: "the Princess's Secret Slide", 28: "Metal Cap", 29: "Wing Cap", 30: "the first Bowser fight",
    31: "the rainbow bonus", 33: "the second Bowser fight", 34: "the final Bowser fight", 36: "Tall, Tall Mountain",
}


@dataclass
class Fact:
    kind: str                       # star, death, trick_bailed, arrival, ...
    actor: str = "mario"            # mario | jimmie | game
    ms: float = 0.0                 # game monotonic clock
    frame: int = 0
    mode: str = "free"              # "16" | "free"
    scope: str = ""                 # epoch/slot/generation/visit: anything remembered dies when this changes
    level: int = 0
    data: dict = field(default_factory=dict)
    source: str = "jb"              # which log prefix reported it

    @property
    def key(self) -> str:
        """What the game looks up at event time. Must be computable in Lua from the event alone."""
        condition = self.data.get("condition")
        return f"{self.kind}:{self.actor}" + (f":{condition}" if condition else "")


def _scope(row: dict) -> str:
    if isinstance(row.get("scope"), str):
        return row["scope"]
    parts = [row.get(k) for k in ("epoch", "slot", "generation", "visit")]
    return "/".join(str(p) for p in parts) if any(p is not None for p in parts) else ""


def _level(row: dict) -> int:
    if isinstance(row.get("level"), int):
        return row["level"]
    scene = row.get("scene")
    if isinstance(scene, str) and scene.split("/")[0].isdigit():
        return int(scene.split("/")[0])
    return 0


J16_KINDS = {"course_star": "star", "secret_star": "star", "key": "key", "mario_death": "death",
             "segment_entered": "arrival", "fell_below_setup": "setback", "wall_setup": "precision_setup",
             "possible_wall_attempt": "precision_attempt", "final_grand_star": "grand_star", "mode": "mode"}


def parse_line(line: str) -> Fact | None:
    """One stdout line -> Fact, or None. Unknown or malformed lines are ignored, never guessed at."""
    for prefix in PREFIXES:
        at = line.find(prefix)
        if at >= 0:
            break
    else:
        return None
    try:
        row = json.loads(line[at + len(prefix):])
    except ValueError:
        return None
    if not isinstance(row, dict):
        return None
    ms = row.get("ms") or row.get("qpc_ms") or row.get("observed_qpc_ms") or 0.0
    base = dict(source=prefix.strip("[] "), ms=float(ms), frame=int(row.get("frame") or row.get("f") or 0),
                mode=str(row.get("mode") or "free"), scope=_scope(row), level=_level(row))
    if prefix == "[jb] ":
        kind = row.get("k")
        if not isinstance(kind, str):
            return None
        skip = {"k", "a", "ms", "f", "frame", "mode", "scope", "level"}
        return Fact(kind=kind, actor=str(row.get("a") or "game"), data={k: v for k, v in row.items() if k not in skip}, **base)
    if prefix == "[j16] ":
        kind = J16_KINDS.get(row.get("kind"))
        if not kind:
            return None
        data = {k: row[k] for k in ("objective", "mission", "stars", "id", "selection", "reason", "course", "act") if k in row}
        if row.get("kind") == "secret_star":
            data["secret"] = True
        return Fact(kind=kind, actor=str(row.get("actor") or "mario"), data=data, **base)
    if prefix == "[jimmie-social] ":
        kind = row.get("kind")
        if kind == "outcome" and row.get("fact") in ("trick_bailed", "trick_completed"):
            data = {"heard": bool(row.get("heard")), "left": bool(row.get("left"))}
            if row.get("condition"):
                data["condition"] = row["condition"]
            return Fact(kind=row["fact"], actor="jimmie", data=data, **base)
        if kind == "approach":
            return Fact(kind="trick_approach", actor="jimmie", data={"toward": bool(row.get("toward"))}, **base)
        if kind == "played":
            return Fact(kind="played", actor="jimmie", data={"tag": row.get("tag"), "legacy": True}, **base)
        if kind == "wall_jump":
            return Fact(kind="precision_jump", actor="mario", data={}, **base)
        return None
    if prefix == "[jimmie-skate-memory] ":
        if row.get("fact") in ("trick_completed", "trick_bailed", "getup_completed"):
            data = {"condition": row["condition"]} if row.get("condition") else {}
            return Fact(kind=row["fact"], actor="jimmie", data=data, **base)
        return None
    if prefix == "[jimmie-v2] " and row.get("type") == "event":
        return Fact(kind=str(row.get("kind")), actor=str(row.get("actor") or "mario"),
                    data={"subject": row.get("subject")}, **base)
    return None
