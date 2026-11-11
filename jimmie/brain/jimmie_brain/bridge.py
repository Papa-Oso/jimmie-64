"""The running game <-> the director.

In:  the game's stdout.log, which the companion already prints facts to.
Out: ModFS boxes in the player's save/sav folder, the channel the project already uses to hand
     prepared choices to Lua. One small plan box, plus one box per new voiced line. The engine's
     audio_sample_load accepts ModFS URIs, so a freshly voiced line needs no engine change.

Plan file (plan.txt), pipe-separated, one header then exactly <rows> rows:
    JB1|<seq>|<rows>
    L|<line id>|<box>|<mod sound file>|<seconds>|<text>      line to have loaded (box or file, not both)
    P|<event key>|<line id>|<delay ms>|<scope>|<intent>|<rule>   if this happens, say that
    N|<line id>|<expires game ms>|<scope>|<intent>|<rule>|<delay ms>   say this as soon as there is room
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZIP_STORED, ZipFile

from .director import Director
from .facts import Fact, parse_line

SESSION = re.compile(r"\d{6,20}")


def flat(text: str) -> str:
    return re.sub(r"[|\r\n]+", " ", text).strip()


def plan_text(doc: dict, box_for, beat: int = 0) -> str:
    rows = []
    for line in doc["lines"]:
        box = "" if line.file else (box_for(line) or "")
        if not line.file and not box:
            continue                       # nothing the game could play
        rows.append(f"L|{line.id}|{box}|{line.file or ''}|{line.seconds:.2f}|{flat(line.text)}")
    playable = {int(r.split("|")[1]) for r in rows}
    for key, e in sorted(doc["plan"].items()):
        if e["line"] in playable:
            rows.append(f"P|{key}|{e['line']}|{e['delay']}|{e['scope']}|{e['intent']}|{e['rule']}")
    a = doc["ambient"]
    if a and a["line"] in playable:
        rows.append(f"N|{a['line']}|{a['expires']:.0f}|{a['scope']}|{a['intent']}|{a['rule']}|{a['delay']}")
    return "\n".join([f"JB1|{doc['seq']}|{len(rows)}|{beat}", *rows]) + "\n"


def write_box(path: Path, files: dict[str, bytes], text_files=()) -> None:
    """A ModFS archive, written whole then moved into place so the game never reads half of one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, suffix=".pending", delete=False) as f:
        temp = Path(f.name)
    try:
        with ZipFile(temp, "w", ZIP_STORED) as bundle:
            for name, data in files.items():
                bundle.writestr(name, data)
            bundle.writestr("properties.json", json.dumps({"isPublic": True, "files": {
                name: {"isText": name in text_files, "isPublic": True, "compressionLevel": 0} for name in files}}))
        # On Windows the move fails while the game has the old box open; it holds it for a few ms.
        for attempt in range(40):
            try:
                os.replace(temp, path)
                break
            except PermissionError:
                if attempt == 39:
                    raise
                time.sleep(0.005)
    finally:
        temp.unlink(missing_ok=True)


class Publisher:
    def __init__(self, sav: Path, session: str):
        if not SESSION.fullmatch(session):
            raise ValueError("bad session id")
        self.sav, self.session = Path(sav), session
        self.boxes: dict[int, str] = {}
        self.created: list[Path] = []
        self.last_seq = None

    def box_for(self, line) -> str | None:
        if line.id in self.boxes:
            return self.boxes[line.id]
        if not line.audio or not Path(line.audio).is_file():
            return None
        name = f"jbline_{self.session}_{line.id}"
        target = self.sav / f"{name}.modfs"
        write_box(target, {"line.ogg": Path(line.audio).read_bytes()})
        self.created.append(target)
        self.boxes[line.id] = name
        return name

    def publish(self, doc: dict, beat: int = 0) -> bool:
        """beat changes every couple of seconds so the game can tell the brain is alive."""
        if (doc["seq"], beat) == self.last_seq:
            return False
        target = self.sav / f"jbplan_{self.session}.modfs"
        try:
            write_box(target, {"plan.txt": plan_text(doc, self.box_for, beat).encode("utf-8")}, text_files=("plan.txt",))
        except PermissionError:
            return False                   # the game is reading it; the next step publishes
        if target not in self.created:
            self.created.append(target)
        self.last_seq = (doc["seq"], beat)
        return True

    def cleanup(self) -> None:
        for path in self.created:
            path.unlink(missing_ok=True)


class Tail:
    """Follow a growing log file by bytes; yields complete lines only."""

    def __init__(self, path: Path):
        self.path, self.position, self.partial = Path(path), 0, b""

    def read(self) -> list[str]:
        if not self.path.is_file():
            return []
        with self.path.open("rb") as f:
            f.seek(self.position)
            chunk = f.read(1 << 18)
            self.position = f.tell()
        if not chunk:
            return []
        whole = (self.partial + chunk).split(b"\n")
        self.partial = whole.pop()[-8192:]
        return [b.decode("utf-8", "replace") for b in whole]


class Bridge:
    def __init__(self, director: Director, log: Path, sav: Path, journal: Path | None = None, tick_s: float = 2.0):
        self.director, self.tail, self.sav = director, Tail(log), Path(sav)
        self.publisher: Publisher | None = None
        self.journal, self.tick_s = journal, tick_s
        self.stop = threading.Event()
        self.clock = (0.0, time.monotonic())      # (game ms at last fact, wall time then)
        if self.sav.is_dir():                     # boxes left behind by a run that was killed
            for stale in list(self.sav.glob("jbplan_*.modfs")) + list(self.sav.glob("jbline_*.modfs")):
                stale.unlink(missing_ok=True)
        self.journaled = 0

    def game_now(self) -> float:
        game, wall = self.clock
        return game + (time.monotonic() - wall) * 1000.0 if game else 0.0

    def handle(self, fact: Fact) -> None:
        if self.publisher and fact.source != "jb":
            return      # the link is installed and reports everything itself; older prefixes would double-count
        if fact.ms:
            self.clock = (fact.ms, time.monotonic())
        if fact.kind == "hello" and SESSION.fullmatch(str(fact.data.get("session", ""))):
            if self.publisher:
                self.publisher.cleanup()
            self.publisher = Publisher(self.sav, str(fact.data["session"]))
        self.director.observe(fact)

    def step(self) -> None:
        for raw in self.tail.read():
            fact = parse_line(raw)
            if fact:
                self.handle(fact)
        if self.publisher:
            self.publisher.publish(self.director.document(), int(time.monotonic() // 2))
        if self.journal and len(self.director.log) > self.journaled:
            with self.journal.open("a", encoding="utf-8") as f:
                for row in self.director.log[self.journaled:]:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            self.journaled = len(self.director.log)

    def _write_loop(self) -> None:
        while not self.stop.is_set():
            if self.director.write_one() is None:
                self.stop.wait(0.15)

    def run(self) -> None:
        writer = threading.Thread(target=self._write_loop, name="Jimmie thinks ahead", daemon=True)
        writer.start()
        next_tick = time.monotonic() + self.tick_s
        try:
            while not self.stop.wait(0.03):
                self.step()
                if time.monotonic() >= next_tick:
                    next_tick += self.tick_s
                    if (now := self.game_now()):
                        self.director.tick(now)
        finally:
            self.stop.set()
            writer.join(timeout=15)
            if self.publisher:
                self.publisher.cleanup()
