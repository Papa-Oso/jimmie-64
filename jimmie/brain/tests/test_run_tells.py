"""The three tells that decide whether a new file is a 16-star run. Runs the Lua under Lupa."""
import unittest
from pathlib import Path

try:
    from lupa import LuaRuntime
except ImportError:  # pragma: no cover
    LuaRuntime = None

SOURCE = Path(__file__).resolve().parents[1] / "lua" / "jimmie_run_tells.lua"
GROUNDS, CASTLE, BOB, WF, JRB = 16, 6, 9, 24, 12


@unittest.skipIf(LuaRuntime is None, "Lupa not installed")
class RunTells(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.mod = self.lua.execute(SOURCE.read_text(encoding="utf-8"))
        self.t = self.mod.new()
        self.t.begin()

    def walk(self, steps):
        """steps: (seconds, level, stars, still) in order."""
        for t, level, stars, still in steps:
            self.t.observe(t, level, stars, still)

    def verdict(self):
        return self.t.verdict()[0]

    def test_a_real_start_is_a_run_and_keeps_the_clock(self):
        self.walk([(5, GROUNDS, 0, False), (18, CASTLE, 0, False), (40, BOB, 0, False)])
        self.t.star(150, BOB, 1)
        self.assertEqual(self.verdict(), "run")
        self.assertTrue(self.t.shows())

    def test_the_clock_shows_from_the_start_while_it_is_still_watching(self):
        self.walk([(2, GROUNDS, 0, False)])
        self.assertEqual(self.verdict(), "watching")
        self.assertTrue(self.t.shows())

    def test_one_hit_is_enough_even_when_the_other_two_are_missed(self):
        self.walk([(60, GROUNDS, 0, False), (70, CASTLE, 0, False), (130, BOB, 0, False)])   # late door, late course
        self.t.star(200, BOB, 1)                                                              # star in time
        self.assertEqual((self.verdict(), self.t.tells().star), ("run", "hit"))

    def test_missing_all_three_stops_the_clock(self):
        self.walk([(60, GROUNDS, 0, False), (70, CASTLE, 0, False), (130, BOB, 0, False), (250, BOB, 0, False)])
        self.assertEqual(self.verdict(), "not")
        self.assertFalse(self.t.shows())
        self.assertEqual(self.t.verdict()[1], "missed all three tells")

    def test_one_bad_miss_stops_it_alone(self):
        self.walk([(10, CASTLE, 0, False), (50, JRB, 0, False)])               # quick door, but the wrong first course
        self.assertEqual(self.t.verdict()[1], "first course is not on the route")
        t = self.mod.new(); t.begin()
        for s in range(0, 200, 5):
            t.observe(s, GROUNDS, 0, False)                                    # wandering the grounds
        self.assertEqual(t.verdict()[1], "never went into the castle")
        t = self.mod.new(); t.begin()
        t.observe(10, CASTLE, 0, False)
        for s in range(12, 90, 2):
            t.observe(s, CASTLE, 0, True)                                      # put the controller down
        self.assertEqual(t.verdict()[1], "stood still too long")

    def test_once_it_is_a_run_nothing_later_takes_the_clock_away(self):
        self.walk([(18, CASTLE, 0, False), (40, BOB, 0, False)])
        self.t.star(120, BOB, 1)
        for s in range(130, 400, 10):
            self.t.observe(s, JRB, 1, True)
        self.assertEqual(self.verdict(), "run")

    def test_the_clock_text(self):
        self.assertEqual(self.mod.clock(1149570), "19:09.57")
        self.assertEqual(self.mod.clock(61234), "01:01.23")


if __name__ == "__main__":
    unittest.main()
