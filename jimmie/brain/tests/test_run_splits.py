"""Splits on the run clock, and the text-box variants used from the second attempt on."""
import re
import unittest
from pathlib import Path

try:
    from lupa import LuaRuntime
except ImportError:  # pragma: no cover
    LuaRuntime = None

LUA = Path(__file__).resolve().parents[1] / "lua"
ALLOWED = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 !%'(),-./:<>?[]^|")


def rows(name):
    """{id: [text, ...]} from a Lua data file, without running it."""
    src = (LUA / name).read_text(encoding="utf-8")
    return src


class Variants(unittest.TestCase):
    def test_every_variant_fills_the_same_lines_as_the_box_it_replaces(self):
        base = {int(i): (int(per), body.count("\\n") + 1) for i, per, body in
                re.findall(r'\{(\d+), (\d+), -?\d+, -?\d+, "((?:[^"\\]|\\.)*)"\}', rows("jimmie_dialogs.lua"))}
        src = rows("jimmie_dialog_variants.lua")
        found = 0
        for ident, block in re.findall(r"\[(\d+)\] = \{(.*?)\n  \},", src, re.S):
            per, lines = base[int(ident)]
            for body in re.findall(r'"((?:[^"\\]|\\.)*)"', block):
                found += 1
                parts = body.split("\\n")
                self.assertEqual(-(-len(parts) // per), -(-lines // per), body)      # same number of boxes
                for line in parts:
                    self.assertLessEqual(len(line), 26, line)
                    self.assertFalse(set(line) - ALLOWED, line)
        self.assertGreaterEqual(found, 3)

    def test_no_owner_vetoed_wording(self):
        self.assertNotIn("know this map", rows("jimmie_dialog_variants.lua").lower())


@unittest.skipIf(LuaRuntime is None, "Lupa not installed")
class Splits(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.mod = self.lua.execute((LUA / "jimmie_run_splits.lua").read_text(encoding="utf-8"))
        self.store = {}
        self.s = self.mod.new(lambda key: self.store.get(key), lambda key, v: self.store.__setitem__(key, v))

    def test_first_time_at_a_star_has_nothing_to_compare(self):
        self.assertIsNone(self.s.star(1, 150000))
        self.assertEqual(self.store["reach_1"], 150000)

    def test_later_attempts_compare_with_the_fastest_reach(self):
        self.s.star(1, 150000)
        self.assertEqual(self.s.star(1, 152500), 2500)       # behind
        self.assertEqual(self.store["reach_1"], 150000)      # a slower time does not replace it
        self.assertEqual(self.s.star(1, 149000), -1000)      # ahead
        self.assertEqual(self.store["reach_1"], 149000)

    def test_a_finished_best_run_becomes_the_reference(self):
        self.s.star(1, 140000)                               # a fast first star in a run that was never finished
        times = {n: 150000 * n for n in range(1, 17)}
        self.s.finish(True, lambda n: times[n])
        self.assertEqual(self.store["pb_16"], 2400000)
        self.assertEqual(self.s.star(1, 151000), 1000)       # against the finished run, not the abandoned one

    def test_a_finish_that_is_not_the_best_changes_nothing(self):
        self.s.finish(False, lambda n: 1000 * n)
        self.assertNotIn("pb_1", self.store)

    def test_bad_input_is_ignored(self):
        self.assertIsNone(self.s.star(0, 1000))
        self.assertIsNone(self.s.star(17, 1000))
        self.assertIsNone(self.s.star(3, 0))
        self.assertEqual(self.store, {})

    def test_the_difference_reads_like_a_split(self):
        self.assertEqual(self.mod.delta(-2100), "-0:02.1")
        self.assertEqual(self.mod.delta(74000), "+1:14.0")
        self.assertEqual(self.mod.delta(0), "+0:00.0")
        self.assertEqual(self.mod.delta(None), "")


if __name__ == "__main__":
    unittest.main()
