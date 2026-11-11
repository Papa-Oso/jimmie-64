"""The run-clock block of lua/install_brain.lua, driven through two attempts with a stand-in game.

The automated game start cannot collect stars or reset, so this runs the real Lua with stubs for
the engine calls it makes: mode follows the verdict without a chat message, a split is shown with
its difference, the second attempt swaps the introduction text and tells the brain.
"""
import unittest
from pathlib import Path

try:
    from lupa import LuaRuntime
except ImportError:  # pragma: no cover
    LuaRuntime = None

LUA = Path(__file__).resolve().parents[1] / "lua"

STUBS = r"""
EVENTS, CHAT, MODES, FACTS, TEXTS, DRAWN, STORE, HOOKS = {}, {}, {}, {}, {}, {}, {}, {}
STATE = { phase = 0, ms = 0, best = 0, stars = 0, splits = {} }
TIMER = 0
Personality = { json = function(row) local parts = {} for k, v in pairs(row) do parts[#parts + 1] = k .. "=" .. tostring(v) end table.sort(parts) return table.concat(parts, " ") end }
print = function(s) EVENTS[#EVENTS + 1] = s end
function jimmie_run_state() return STATE.phase, STATE.ms, STATE.best, STATE.stars, "" end
function jimmie_run_split(n) return STATE.splits[n] or 0 end
function djui_chat_message_create(s) CHAT[#CHAT + 1] = s end
JIMMIE_ROUTE16 = { command = function(name) MODES[#MODES + 1] = name; djui_chat_message_create("Jimmie: " .. name) return true end }
JIMMIE_BRAIN = { fact = function(kind, actor, extra) FACTS[#FACTS + 1] = kind .. ":" .. tostring(extra.n) end }
gMarioStates = { [0] = { vel = { x = 9, y = 0, z = 9 } } }
gNetworkPlayers = { [0] = { currLevelNum = 16 } }
function get_global_timer() return TIMER end
function smlua_text_utils_dialog_replace(id, a, per, left, width, text) TEXTS[#TEXTS + 1] = { id = id, per = per, text = text } end
function mod_storage_load_number(key) return STORE[key] or 0 end
function mod_storage_save_number(key, v) STORE[key] = v end
HOOK_UPDATE, HOOK_ON_HUD_RENDER, RESOLUTION_N64, FONT_NORMAL = 1, 2, 0, 0
function hook_event(kind, fn) HOOKS[kind] = fn end
function djui_hud_set_resolution() end
function djui_hud_set_font() end
function djui_hud_get_screen_width() return 320 end
function djui_hud_measure_text(s) return #s * 6 end
function djui_hud_set_color(r, g, b, a) COLOR = r .. "," .. g .. "," .. b end
function djui_hud_print_text(s, x, y, scale) DRAWN[#DRAWN + 1] = { text = s, color = COLOR } end
function djui_hud_reset_color() end
"""


@unittest.skipIf(LuaRuntime is None, "Lupa not installed")
class RunHudWiring(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(STUBS)
        mods = self.lua.eval("{}")
        for name in ("jimmie_run_tells", "jimmie_run_splits", "jimmie_dialogs", "jimmie_dialog_variants"):
            mods[name] = self.lua.execute((LUA / f"{name}.lua").read_text(encoding="utf-8"))
        self.lua.globals().MODS = mods
        self.lua.execute("function require(name) return MODS[name] end")
        src = (LUA / "install_brain.lua").read_text(encoding="utf-8")
        block = src[src.index('if type(jimmie_run_state) == "function" then'):]
        # Errors must surface in the test instead of being swallowed by the hooks' pcall.
        block = block.replace("pcall(run_update)", "run_update()").replace("pcall(run_hud)", "run_hud()")
        self.lua.execute(block)
        self.g = self.lua.globals()

    def tick(self, ms, level=16, stars=0, phase=1):
        s = self.g.STATE
        s.phase, s.ms, s.stars = phase, ms, stars
        self.g.gNetworkPlayers[0].currLevelNum = level
        self.g.TIMER = self.g.TIMER + 10
        self.g.HOOKS[1]()
        self.g.DRAWN = self.lua.eval("{}")
        self.g.HOOKS[2]()
        return [(d.text, d.color) for d in self.g.DRAWN.values()]

    def attempt(self, star_ms):
        """A real start: grounds, castle, Bob-omb Battlefield, first star at star_ms."""
        self.tick(0, phase=0)
        self.tick(1000)
        self.tick(18000, level=6)
        self.tick(40000, level=9)
        self.g.STATE.splits[1] = star_ms
        return self.tick(star_ms + 100, level=9, stars=1)

    def test_two_attempts(self):
        drawn = self.attempt(150000)
        self.assertEqual(list(self.g.MODES.values()), ["16"])              # followed the verdict by itself
        self.assertEqual(list(self.g.CHAT.values()), [])                    # and said nothing in chat
        self.assertEqual(self.g.STORE["reach_1"], 150000)
        self.assertTrue(any(t.startswith("STAR 1  02:30.00") and "+" not in t and "-0" not in t for t, _ in drawn), drawn)
        self.assertEqual(list(self.g.FACTS.values()), [])                   # first attempt: nothing to notice
        self.assertEqual(len(self.g.TEXTS), 1)
        first = self.g.TEXTS[1].text
        self.assertIn("I'm", first)                                         # the introduction itself

        drawn = self.attempt(147900)                                        # reset, 2.1 s faster to the first star
        self.assertEqual(list(self.g.FACTS.values()), ["attempt:2"])
        second = self.g.TEXTS[2]
        self.assertEqual(second.id, 34)
        self.assertNotEqual(second.text, first)
        self.assertEqual(second.text.count("\n"), first.count("\n"))        # same lines, so the same boxes
        split = [(t, c) for t, c in drawn if t.startswith("STAR 1")]
        self.assertEqual(split[-1], ("STAR 1  02:27.90  -0:02.1", "110,230,120"))   # ahead, in green
        self.assertEqual(self.g.STORE["reach_1"], 147900)
        self.assertEqual(list(self.g.CHAT.values()), [])

    def test_behind_is_red_and_a_non_run_records_nothing(self):
        self.attempt(150000)
        drawn = self.attempt(151000)
        self.assertEqual([c for t, c in drawn if t.startswith("STAR 1")][-1], "240,110,100")
        # An attempt that is plainly not a run: wanders, wrong course first. Its star is not a split reference.
        self.tick(0, phase=0)
        self.tick(1000)
        self.tick(200000)                                                   # still outside after 150 s: a bad miss
        self.assertEqual(list(self.g.MODES.values())[-1], "free")
        self.g.STATE.splits[1] = 100000
        self.tick(400000, level=12, stars=1)
        self.assertEqual(self.g.STORE["reach_1"], 150000)


if __name__ == "__main__":
    unittest.main()
