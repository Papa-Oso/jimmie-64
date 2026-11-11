"""Runs the game-side link under Lupa with a mocked engine. Skipped where Lupa is not installed
(the project venv has it). This is the only automated check of the Lua file: it was written
without a Lua interpreter available, so run this before anything else touches the game."""
import random
import unittest
from pathlib import Path

try:
    from lupa import LuaRuntime
except ImportError:  # pragma: no cover
    LuaRuntime = None

from jimmie_brain.bridge import plan_text
from jimmie_brain.director import Director
from jimmie_brain.facts import parse_line
from jimmie_brain.rules import Rule, RuleBook

LINK = Path(__file__).resolve().parents[1] / "lua" / "jimmie_brain_link.lua"

HARNESS = """
function(source, py)
    ACT_FLAG_AIR, ACT_FLAG_INTANGIBLE = 0x800, 0x1000
    ACT_FLAG_SWIMMING, INTERACT_STAR_OR_KEY = 0x2000, 0x1000
    LEVEL_BOWSER_1, LEVEL_BOWSER_2, LEVEL_BOWSER_3 = 30, 33, 34
    gNetworkPlayers = {[0] = {currLevelNum = 9}}
    MOD_FS_URI_FORMAT = "modfs:/%s/%s"
    gMarioStates = {[0] = {vel = {x = 9, y = 0, z = 0}, pos = {y = 0}, action = 0, health = 0x880}}
    function get_global_timer() return py.frame() end
    function mod_fs_exists(box) return py.exists(box) end
    function mod_fs_reload(box) return box end
    function mod_fs_get_file(fs, name) return py.open(fs, name) end
    function mod_fs_file_read_line(f) return py.readline(f) end
    local function json(t)
        local parts = {}
        for k, v in pairs(t) do
            local value = type(v) == "string" and string.format("%q", v) or tostring(v)
            parts[#parts + 1] = string.format("%q:%s", k, value)
        end
        return "{" .. table.concat(parts, ",") .. "}"
    end
    return load(source, "link")().new({
        json = json,
        clock = function() return py.clock() end,
        print = function(line) py.emit(line) end,
        busy = function() return py.busy() end,
        veto = {["roast_01.ogg"] = true},
        load = function(name) return py.load(name) end,
        context = function() return py.context() end,
        speak = function(sample, seconds, detail) return py.speak(sample, seconds, detail) end,
    })
end
"""


class Engine:
    """Everything the link asks of the game, held in Python."""

    def __init__(self, lua):
        self.lua, self.now, self.out, self.spoken, self.boxes, self.loaded = lua, 1000.0, [], [], {}, []
        self.ctx = {"epoch": 1, "slot": 1, "generation": 1, "visit": 1, "mode": "free", "level": 9, "nearby": True}
        self.voice_busy = False

    def clock(self): return self.now
    def frame(self): return int(self.now / 33)
    def emit(self, line): self.out.append(line)
    def busy(self): return self.voice_busy
    def exists(self, box): return box in self.boxes
    def context(self): return self.lua.table_from(self.ctx) if self.ctx else None
    def open(self, box, name): return iter(self.boxes[box].splitlines()) if name == "plan.txt" else None
    def readline(self, f): return next(f, None)

    def load(self, name):
        self.loaded.append(name)
        return name

    def speak(self, sample, seconds, detail):
        if not detail.valid():
            return False
        self.spoken.append((sample, detail.text))
        detail.onPlay()
        return True


@unittest.skipIf(LuaRuntime is None, "Lupa not installed")
class LinkTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.game = Engine(self.lua)
        self.link = self.lua.eval(HARNESS)(LINK.read_text(encoding="utf-8"), self.game)
        self.link.update()
        self.session = self.link.session()
        self.director = Director(rng=random.Random(0))
        self.director.rulebook = RuleBook([
            Rule("pay", ("trick_bailed",), "own_it", when={"f.condition": "called_bail"}, bank=("star_hype",), payoff=True),
            Rule("slow", ("death",), "deadpan", bank=("castle_door",), delay_ms=900)])

    def facts(self):
        found = [parse_line(line) for line in self.game.out]
        self.game.out.clear()
        return [f for f in found if f]

    def pump(self, ms=300):
        """Brain reads what the game printed, publishes its plan, the game polls it."""
        kinds = []
        for f in self.facts():
            kinds.append(f.kind)
            self.director.observe(f)
        self.game.boxes["jbplan_" + self.session] = plan_text(self.director.document(), lambda line: None)
        self.game.now += ms
        self.link.update()
        return kinds

    def test_hello_then_arrival_then_a_planned_payoff(self):
        self.assertEqual(self.pump(), ["hello", "arrival"])
        self.assertIn("catchphrase_01.ogg", self.game.loaded)             # loaded before it is needed
        self.assertFalse(self.link.fact("trick_bailed", "jimmie"))         # no condition: nothing was planned for that
        said = self.link.fact("trick_bailed", "jimmie", self.lua.table_from({"condition": "called_bail"}))
        self.assertTrue(said)
        self.assertEqual(self.game.spoken, [("catchphrase_01.ogg", "Holy shit!")])
        self.assertIn("played", self.pump())
        self.assertEqual(self.director.memory.spoken[-1].text, "Holy shit!")

    def test_a_delay_is_kept_and_a_warp_cancels_the_plan(self):
        self.pump()
        self.assertTrue(self.link.fact("death", "mario"))
        self.assertEqual(self.game.spoken, [])                             # the pause is part of the line
        self.game.now += 950
        self.link.update()
        self.assertEqual(self.game.spoken, [("catchphrase_03.ogg", "What's happening, guys?")])
        self.game.out.clear()
        self.director.last_heard.clear()
        self.game.boxes["jbplan_" + self.session] = "JB1|manual|2\nL|900|||1.0|Old.\nP|death:mario|900|0|1/1/1/1|deadpan|slow\n"
        self.game.now += 300
        self.link.update()
        self.game.ctx = dict(self.game.ctx, visit=2)                       # the scene changed under the plan
        self.assertFalse(self.link.fact("death", "mario"))
        self.assertEqual(len(self.game.spoken), 1)

    def test_a_malformed_plan_changes_nothing(self):
        self.pump()
        self.game.boxes["jbplan_" + self.session] = "JB1|bad|2\nL|5||x.ogg|1.0|Hi.\nGARBAGE\n"
        self.game.now += 300
        self.link.update()
        self.assertTrue(self.link.fact("death", "mario"))                  # the earlier plan is still in force

    def test_what_the_player_types_reaches_the_brain_as_plain_text(self):
        self.game.out.clear()
        me, other = self.lua.table_from({"playerIndex": 0}), self.lua.table_from({"playerIndex": 1})
        self.link.chat(me, '\\#ff0000\\hey "Jimmie"  ')
        self.link.chat(me, "/j16 16")                                      # a command is not talk
        self.link.chat(other, "someone else")
        facts = [f for f in map(parse_line, self.game.out) if f]
        self.assertEqual([(f.kind, f.actor, f.data["text"]) for f in facts], [("chat", "mario", "hey  Jimmie")])

    def test_a_landing_reports_the_trick_by_name(self):
        self.game.out.clear()
        self.link.skate(self.lua.table_from({"fact": "trick_completed", "kind": "trick", "condition": "clean_landing",
                                             "trick": "kickflip to nose manual", "line": 3}))
        facts = [f for f in map(parse_line, self.game.out) if f and f.kind == "trick_completed"]
        self.assertEqual((facts[0].data["trick"], facts[0].data["row"]), ("kickflip to nose manual", 3))


if __name__ == "__main__":
    unittest.main()
