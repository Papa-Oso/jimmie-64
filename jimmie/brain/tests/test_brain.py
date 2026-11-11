import json
import random
import tempfile
import unittest
import zipfile
from pathlib import Path

from jimmie_brain import corpus, eval as evaluation
from jimmie_brain.bridge import Bridge, Publisher, plan_text
from jimmie_brain.director import Director
from jimmie_brain.facts import Fact, parse_line
from jimmie_brain.memory import Memory
from jimmie_brain.rules import Rule, RuleBook, holds
from jimmie_brain.voice import Bank, NullTTS, Renderer
from jimmie_brain.writer import Scene, ScriptedLLM, Veto, Writer, clean, lint, normal

SRT = """1
00:00:10,000 --> 00:00:20,000
Holy shit, dude. Watch this shit. Fuck. I fucked up there. Hey Jimmy, put my marbles in your mouth.

2
00:00:21,000 --> 00:00:30,000
We got a PB tonight, son. Let's fucking go! What are you doing, dude?

"""


def fact(kind, actor="mario", ms=1000.0, mode="free", scope="1/1/1/1", level=9, **data):
    return Fact(kind, actor, ms=ms, mode=mode, scope=scope, level=level, data=data)


class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        root = Path(self.dir.name)
        (root / "2026-01-01 - Mario Night [123456789].srt").write_text(SRT, encoding="utf-8")
        self.root = root
        self.turns = corpus.build_turns(root, {"123456789": "train"})

    def tearDown(self):
        self.dir.cleanup()

    def test_sentences_get_times_inside_their_cue(self):
        self.assertEqual(len(self.turns), 8)
        first = [t for t in self.turns if t.id.startswith("vod/123456789/1/")]
        self.assertTrue(all(10 <= t.start <= t.end <= 20.01 for t in first))
        self.assertEqual(self.turns[2].prev, "Holy shit, dude. Watch this shit.")
        self.assertEqual(self.turns[0].game, "sm64")

    def test_someone_addressing_him_and_pace_talk_are_not_examples(self):
        index = corpus.Index(self.turns)
        texts = [t.text for t in index.turns]
        self.assertNotIn("Hey Jimmy, put my marbles in your mouth.", texts)
        self.assertNotIn("We got a PB tonight, son.", texts)
        self.assertIn("Fuck.", texts)

    def test_exemplars_follow_the_social_move(self):
        index = corpus.Index(self.turns)
        got = [t.text for t in index.exemplars("own_it", 4, random.Random(1))]
        self.assertEqual(got, ["I fucked up there."])

    def test_speaker_sidecar_gates_examples_and_training(self):
        self.assertEqual(list(corpus.training_rows(self.turns)), [])       # unverified speech never trains
        speakers = self.root / "spk"
        speakers.mkdir()
        (speakers / "123456789.json").write_text(json.dumps({"intervals": [[10, 14, 0.9], [14, 20, 0.1], [21, 30, 0.9]]}))
        turns = corpus.build_turns(self.root, {"123456789": "train"}, speakers)
        self.assertEqual(turns[0].speaker, 0.9)
        kept = [t.text for t in corpus.Index(turns).turns]
        self.assertIn("Holy shit, dude.", kept)
        self.assertNotIn("I fucked up there.", kept)                       # that stretch was someone else
        rows = list(corpus.training_rows(turns))
        self.assertTrue(rows and all(r["vod"] == "123456789" for r in rows))
        self.assertEqual(list(corpus.training_rows(turns, splits=("test",))), [])

    def test_fingerprint_and_drift(self):
        real = corpus.fingerprint(["Fuck yeah, son.", "What the fuck?", "Okay.", "Let's go, dude."])
        prim = corpus.fingerprint(["That was a truly wonderful jump, Mario.", "I believe we should proceed carefully now."])
        self.assertGreater(corpus.drift(real, prim)["distance"], corpus.drift(real, real)["distance"])
        self.assertEqual(corpus.drift(real, real)["distance"], 0)


class RuleTests(unittest.TestCase):
    def book(self):
        return RuleBook([
            Rule("general", ("death",), "needle", chance=1.0),
            Rule("specific", ("death",), "deadpan", when={"deaths_streak": {"gte": 3}}, chance=0.0),
            Rule("hush", ("precision_setup",), "quiet"),
            Rule("cool", ("star",), "celebrate", cooldown_s=30),
            Rule("pay", ("trick_bailed",), "own_it", payoff=True),
        ])

    def test_criteria(self):
        self.assertTrue(holds({"gte": 2, "lte": 5}, 3, True))
        self.assertFalse(holds({"gte": 2}, None, False))        # a missing number is zero
        self.assertFalse(holds(True, None, False))
        self.assertTrue(holds({"in": ["a", "b"]}, "a", True))

    def test_most_specific_wins_and_a_lost_roll_is_silence_not_fallthrough(self):
        b, rng = self.book(), random.Random(0)
        self.assertEqual(b.decide({"fact": "death", "deaths_streak": 1}, {}, 0, rng).rule.id, "general")
        d = b.decide({"fact": "death", "deaths_streak": 3}, {}, 0, rng)
        self.assertEqual((d.rule.id, d.speak, d.reason), ("specific", False, "chance"))

    def test_gap_cooldown_precision_and_payoff(self):
        b, rng = self.book(), random.Random(0)
        self.assertEqual(b.decide({"fact": "star", "mode": "free", "since_spoke_s": 1}, {}, 0, rng).reason, "just_spoke")
        self.assertEqual(b.decide({"fact": "star", "mode": "free"}, {"cool": 5000}, 20000, rng).reason, "cooldown")
        self.assertTrue(b.decide({"fact": "star", "mode": "free"}, {"cool": 5000}, 40000, rng).speak)
        self.assertEqual(b.decide({"fact": "star", "precision": True}, {}, 0, rng).reason, "precision")
        self.assertTrue(b.decide({"fact": "trick_bailed", "mode": "free", "since_spoke_s": 1}, {}, 0, rng).speak)
        self.assertFalse(b.decide({"fact": "precision_setup"}, {}, 0, rng).speak)

    def test_shipped_table_loads_and_every_matched_scene_behaves(self):
        self.assertGreater(len(RuleBook.load().rules), 30)
        bad = [r for r in evaluation.rule_check() if not r["ok"]]
        self.assertEqual(bad, [])


class MemoryTests(unittest.TestCase):
    def test_a_line_exists_only_once_heard_and_a_claim_dies_with_the_visit(self):
        m = Memory()
        m.observe(fact("arrival"))
        self.assertEqual(m.context()["lines_visit"], 0)
        m.heard("1", "Watch this shit.", "boast_call", ms=2000)
        self.assertTrue(m.context()["called"])
        m.observe(fact("arrival", ms=3000, scope="1/1/1/2"))
        self.assertFalse(m.context()["called"])
        self.assertEqual(m.context()["lines_visit"], 0)

    def test_counters_are_per_visit_and_mood_decays(self):
        m = Memory()
        for i in range(3):
            m.observe(fact("death", ms=1000 + i * 1000))
        c = m.context()
        self.assertEqual((c["deaths_visit"], c["deaths_streak"]), (3, 3))
        self.assertGreaterEqual(c["tilt"], 70)
        m.observe(fact("arrival", ms=400000, scope="1/1/1/2"))
        c = m.context()
        self.assertEqual((c["deaths_visit"], c["deaths_session"]), (0, 3))
        self.assertLess(c["tilt"], 10)

    def test_peek_does_not_change_the_present(self):
        m = Memory()
        m.observe(fact("arrival"))
        after = m.peek(fact("star", ms=2000, stars=1))
        self.assertEqual((m.session["stars"], after.session["stars"]), (0, 1))

    def test_skating_belongs_to_jimmie(self):
        m = Memory()
        m.observe(fact("trick_bailed", "jimmie"))
        self.assertEqual(m.story(), ["Jimmie bailed a skate trick (just now)"])
        self.assertEqual(m.context()["deaths_visit"], 0)


class WriterTests(unittest.TestCase):
    def setUp(self):
        self.veto, self.scene = Veto(), Scene(stars=4)

    def reasons(self, line, **kw):
        return lint(line, kw.pop("scene", self.scene), self.veto, **kw)

    def test_lines_he_may_say(self):
        for ok in ("Fuck.", "Oh, fuck yeah, son.", "What the fuck was that, dude?", "Unbelievable.", "I'm fine. I'm fine.",
                   "Holy shit balls, son, finally."):
            self.assertEqual(self.reasons(ok), [], ok)

    def test_lines_he_may_not(self):
        cases = {
            "I know this map better than you.": "owner_veto",
            "Dude, I know that level better than you do.": "owner_veto",
            "That's a PB pace, son.": "pace",
            "We are ten seconds ahead.": "pace",
            "You should go left here, dude.": "coaching",
            "Try the BLJ, son.": "jargon",
            "Thanks for the sub, chat.": "meta",
            "I got the star, son.": "wrong_actor",
            "Nice kickflip, Mario.": "wrong_actor",
            "That's your seventh star!": "invented_count",
            "Second time you died there.": "invented_count",
            "*laughs* nice one": "format",
            "This is a very long sentence that keeps going and going well past any reasonable limit": "too_long",
        }
        for line, reason in cases.items():
            self.assertIn(reason, self.reasons(line), line)

    def test_counts_are_allowed_when_the_game_supplied_them(self):
        self.assertEqual(self.reasons("Four stars, son."), [])
        self.assertEqual(self.reasons("Second time, dude.", scene=Scene(facts={"deaths_visit": 2})), [])
        self.assertIn("repeat", self.reasons("Fuck.", recent=["fuck"]))

    def test_cleaning_model_output(self):
        self.assertEqual(clean('1. "Fuck."\n- Okay, okay.\nJimmie: Unreal.\n\n-'), ["Fuck.", "Okay, okay.", "Unreal.", "-"])

    def test_writer_drops_bad_candidates_and_survives_a_dead_model(self):
        llm = ScriptedLLM(default="You should go left, dude.\nI know this map better than you.\nFuck yeah, son.")
        draft = Writer(llm, rng=random.Random(0)).write(self.scene)
        self.assertEqual(draft.text, "Fuck yeah, son.")
        self.assertEqual(len(draft.rejected), 2)

        class Dead:
            def complete(self, *a, **k):
                raise OSError("down")
        self.assertIsNone(Writer(Dead()).write(self.scene))

    def test_retrieval_off_sends_no_real_lines(self):
        turns = corpus.build_turns(self._srt(), {"123456789": "train"})
        llm = ScriptedLLM()
        Writer(llm, index=corpus.Index(turns), retrieval=False).write(Scene(intent="own_it"))
        self.assertNotIn("REAL LINES", llm.calls[-1][1])
        Writer(llm, index=corpus.Index(turns), retrieval=True).write(Scene(intent="own_it"))
        self.assertIn("I fucked up there.", llm.calls[-1][1])

    def _srt(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        (Path(self._dir.name) / "x [123456789].srt").write_text(SRT, encoding="utf-8")
        return Path(self._dir.name)


class DirectorTests(unittest.TestCase):
    def director(self, text="Okay, that was sick, son.\nHoly shit, dude.", **kw):
        return Director(writer=Writer(ScriptedLLM(default=text), rng=random.Random(1)), rng=random.Random(2), **kw)

    def test_called_shot_is_planned_before_it_happens(self):
        d = self.director()
        d.observe(fact("arrival"))
        key = "trick_bailed:jimmie:called_bail"
        self.assertIn(key, d.plan)
        self.assertIn(d.lines[d.plan[key]["line"]].text, ("Fuck.", "I meant to do that.", "I fucking meant to do that."))
        self.assertNotIn("precision_jump:mario", d.plan)       # free exploration: leave the jump alone

    def test_the_owners_reference_exchange_is_kept_exactly(self):
        d = Director(rng=random.Random(0))
        d.observe(fact("arrival"))
        watch = d._recorded_line(d.bank.takes["watch_real"], d.rulebook.by_kind["trick_approach"][0])
        self.assertEqual(watch.text, "Watch this shit.")
        for _ in range(20):
            d.observe(fact("played", "jimmie", ms=d.memory.now + 5000, line=watch.id, intent="boast_call"))
            entry = d.plan["trick_bailed:jimmie:called_bail"]
            self.assertEqual((entry["rule"], d.lines[entry["line"]].text), ("bail_called_watch", "Fuck."))

    def test_written_lines_are_single_use_and_replaced(self):
        d = self.director()
        d.rulebook = RuleBook([Rule("g", ("grand_star",), "sincere", write=True, payoff=True)])
        d.observe(fact("arrival"))
        self.assertEqual(d.plan, {})                            # nothing ready yet: quiet, not a stall
        first = d.write_one()
        self.assertEqual(d.plan["grand_star:mario"]["line"], first.id)
        d.observe(fact("played", "jimmie", ms=2000, line=first.id))
        self.assertTrue(first.used)
        self.assertEqual(d.memory.spoken[-1].text, first.text)
        self.assertNotIn("grand_star:mario", d.plan)
        second = d.write_one()
        self.assertNotEqual(second.text, first.text)            # he does not write what he just said

    def test_lines_about_this_visit_die_with_it(self):
        d = self.director()
        d.rulebook = RuleBook([Rule("r", ("star",), "relief", when={"deaths_visit": {"gte": 1}}, write=True, presume=("deaths_visit",))])
        d.observe(fact("arrival"))
        d.observe(fact("death", ms=2000))
        line = d.write_one()
        self.assertEqual((line.scope, line.requires), ("1/1/1/1", {"deaths_visit": 1}))
        self.assertIn("star:mario", d.plan)
        d.observe(fact("arrival", ms=9000, scope="1/1/1/2"))
        self.assertNotIn("star:mario", d.plan)

    def test_vetoed_material_never_reaches_a_plan(self):
        d = self.director(text="I know this map better than you.")
        d.observe(fact("arrival"))
        for _ in range(12):
            d.write_one()
        self.assertFalse(any(d.veto.text(l.text) for l in d.lines.values()))
        bank = Bank()
        bank.takes["star_hype"].file = "roast_01.ogg"
        d2 = Director(bank=bank, rng=random.Random(0))
        d2.rulebook = RuleBook([Rule("s", ("star",), "celebrate", bank=("star_hype",))])
        d2.observe(fact("arrival"))
        self.assertEqual(d2.plan, {})

    def test_dead_air_gets_an_ambient_line_that_expires(self):
        d = self.director()
        d.rulebook = RuleBook([Rule("i", ("idle",), "bit", lane="ambient", bits=("carrier",))])
        d.observe(fact("arrival"))
        d.observe(fact("idle", ms=20000, s=10))
        self.assertEqual(d.lines[d.ambient["line"]].text, "Carrier.")
        d.tick(20000 + d.ambient_ttl_ms + 1)
        self.assertIsNone(d.ambient)

    def test_running_gags_rotate(self):
        d = self.director()
        d.rulebook = RuleBook([Rule("i", ("idle",), "bit", lane="ambient", bits=("carrier", "tor_tor_tor"))])
        d.observe(fact("arrival"))
        heard = []
        for i in range(4):
            d.observe(fact("idle", ms=20000 * (i + 1), s=10))
            line = d.lines[d.ambient["line"]]
            heard.append(line.text)
            d.observe(fact("played", "jimmie", ms=20000 * (i + 1) + 500, line=line.id))
        self.assertEqual(sorted(set(heard)), ["Carrier.", "Tor tor tor."])
        self.assertNotEqual(heard[0], heard[1])

    def test_a_recording_always_wins_and_the_clone_only_fills_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Director(renderer=Renderer(NullTTS(), Path(tmp), ffmpeg=None), rng=random.Random(0))
            d.observe(fact("arrival"))
            for line in d.lines.values():
                self.assertFalse(line.file and line.audio)       # a take with a recording is never also rendered
            rendered = [l for l in d.lines.values() if l.audio]
            self.assertTrue(all(Path(l.audio).is_file() for l in rendered))
            self.assertNotIn("Holy shit!", [l.text for l in rendered])   # ships as a recording

    def test_pool_lines_rotate_and_fit_the_place(self):
        d = Director(rng=random.Random(2))
        voiced = {t: {"file": "x.ogg", "seconds": 1.0} for t in
                  ["good morning whomp's fortress", "what a dump", "this place again", "hello", "we're in"]}
        d.rulebook = RuleBook([Rule("arrive", ("idle",), "greet", lane="ambient", write=True, staple_share=0.0)])
        counts = d.load_pool([{"text": "Good morning, Whomp's Fortress.", "rule": "arrive", "intent": "greet", "level": 24},
                              {"text": "What a dump.", "rule": "arrive", "intent": "greet", "level": None},
                              {"text": "This place again.", "rule": "arrive", "intent": "greet", "level": None},
                              {"text": "Never voiced.", "rule": "arrive", "intent": "greet", "level": None}],
                             {"greet": [["Hello.", 49], ["We're in.", 21]]}, voiced)
        self.assertEqual((counts["written"], counts["staple"], counts["skipped_no_audio"]), (3, 2, 1))
        heard = []
        for i in range(4):
            d.observe(fact("idle", ms=30000 * (i + 1), level=9, s=10))
            line = d.lines[d.ambient["line"]]
            heard.append(line.text)
            d.observe(fact("played", "jimmie", ms=30000 * (i + 1) + 500, line=line.id))
        self.assertNotIn("Good morning, Whomp's Fortress.", heard)      # that line belongs to another place
        self.assertEqual(set(heard), {"What a dump.", "This place again."})
        self.assertEqual(len(set(heard[:2])), 2)                         # least-used first: no repeat until both are used

    def test_his_real_lines_name_real_rules_and_places_and_respect_the_vetoes(self):
        import json
        from jimmie_brain.bake import PLACE_NOTES, real_rows
        from jimmie_brain.writer import Veto
        doc = json.loads((Path(__file__).parents[1] / "jimmie_brain/data/real_lines.json").read_text(encoding="utf-8"))
        writable = {r.id for r in RuleBook.load().rules if r.write}
        texts = [l["text"] for l in doc["lines"]]
        self.assertEqual(len(texts), len(set(texts)))
        veto = Veto()
        for line in doc["lines"]:
            self.assertTrue(line["rules"], line["text"])
            self.assertLessEqual(set(line["rules"]), writable, line["text"])
            self.assertLessEqual(set(line.get("levels") or []), set(PLACE_NOTES), line["text"])
            self.assertFalse(veto.text(line["text"]), line["text"])
        self.assertTrue(all(r["real"] and r["intent"] for r in real_rows()))

    def test_he_stays_on_the_subject_he_was_just_on(self):
        stay = 0
        for seed in range(40):
            d = Director(rng=random.Random(seed))
            texts = ["I need some coffee.", "We should get a pizza.", "Buddy, we're eating toast.",
                     "My car is busted.", "I lost my suspenders.", "That shirt was stupid.", "Look at this monitor."]
            voiced = {t.lower().rstrip(".").replace(",", ""): {"file": "x.ogg", "seconds": 1.0} for t in texts}
            d.rulebook = RuleBook([Rule("chat", ("idle",), "ramble", lane="ambient", write=True, staple_share=0.0)])
            d.load_pool([{"text": t, "rule": "chat", "intent": "ramble", "level": None, "real": True} for t in texts], {}, voiced)
            food = next(l for l in d.lines.values() if l.text == "I need some coffee.")
            self.assertEqual(food.topics, ("food",))
            d.observe(fact("played", "jimmie", ms=1000, line=food.id))
            d.observe(fact("idle", ms=20000, level=1, s=10))
            stay += "food" in d.lines[d.ambient["line"]].topics
        self.assertGreater(stay, 22)        # two of the six others are food; chance alone would give about 13 of 40

    def test_he_answers_what_the_player_types_in_chat(self):
        d = Director(rng=random.Random(3))
        texts = {"What's up, dude?": "chat_hello", "Dude, fuck you.": "chat_diss", "I have no idea.": "chat_question",
                 "Yeah, no kidding.": "chat_other", "We should get a pizza.": "wander", "My car is busted.": "wander"}
        voiced = {t.lower().rstrip(".?").replace(",", ""): {"file": "x.ogg", "seconds": 1.0} for t in texts}
        book = RuleBook.load()
        d.load_pool([{"text": t, "rule": r, "intent": next(x.intent for x in book.rules if x.id == r), "level": None,
                      "real": True} for t, r in texts.items()], {}, voiced)
        said = lambda: d.lines[d.ambient["line"]].text
        d.observe(fact("chat", ms=1000, text="hey jimmie"))
        self.assertEqual((said(), d.ambient["rule"]), ("What's up, dude?", "chat_hello"))
        d.observe(fact("played", "jimmie", ms=1500, line=d.ambient["line"], rule="chat_hello"))
        d.observe(fact("chat", ms=2000, text="you suck"))                  # answers even though he only just spoke
        self.assertEqual(said(), "Dude, fuck you.")
        about = 0
        for seed in range(40):                                             # a question about pizza mostly gets the pizza line
            d.rng = random.Random(seed)
            d.observe(fact("chat", ms=3000 + seed, text="do you like pizza?"))
            about += said() == "We should get a pizza."
            self.assertIn(said(), ("We should get a pizza.", "I have no idea."))
        self.assertGreater(about, 22)
        d.observe(fact("chat", ms=9000, text="carrier"))                   # naming a bit gets the bit
        self.assertEqual(d.lines[d.ambient["line"]].bit, "carrier")
        self.assertEqual(d.log[-2]["event"], "chat")

    def test_a_question_he_has_an_answer_ready_for_gets_that_answer(self):
        from jimmie_brain.bake import answer_rows
        rows = answer_rows()
        self.assertGreater(len(rows), 200)
        self.assertFalse([r["text"] for r in rows if Veto().text(r["text"])])
        d = Director(rng=random.Random(5))
        rows += [{"text": "Dude, fuck you.", "rule": "chat_diss", "intent": "reply", "level": None, "real": True},
                 {"text": "I have no idea.", "rule": "chat_question", "intent": "reply", "level": None, "real": True}]
        voiced = {normal(r["text"]): {"file": "x.ogg", "seconds": 1.0} for r in rows}
        d.load_pool(rows, {}, voiced)
        tag = lambda: d.lines[d.ambient["line"]].tag
        for ms, (typed, answer) in enumerate([("how old are u", "answer:age"), ("jimmie can you hear me", "answer:hear"),
                                              ("where's the star", "answer:help"), ("why do u skate", "answer:why_skate"),
                                              ("are you a robot lol", "answer:real"), ("ok", "answer:ok")]):
            d.observe(fact("chat", ms=1000 + ms * 9000, text=typed))
            self.assertEqual((typed, tag()), (typed, answer))
        d.observe(fact("chat", ms=90000, text="you suck"))                 # a dig is still a dig
        self.assertEqual(d.lines[d.ambient["line"]].text, "Dude, fuck you.")
        d.observe(fact("chat", ms=99000, text="have you ever been to florida"))   # nothing ready: the plain reply
        self.assertEqual(d.lines[d.ambient["line"]].text, "I have no idea.")

    def test_he_does_not_call_out_his_tricks(self):
        from jimmie_brain.bake import trick_rows
        self.assertEqual(trick_rows(), [])                                 # owner switched it off: nothing voiced or loaded
        for seed in range(20):
            d = Director(rng=random.Random(seed))
            d.rulebook = RuleBook([])
            d.observe(fact("trick_completed", "jimmie", ms=5000, condition="clean_landing", trick="kickflip"))
            self.assertIsNone(d.ambient)


class BridgeTests(unittest.TestCase):
    def test_log_lines_from_existing_builds_become_facts(self):
        f = parse_line('x [j16] {"kind":"course_star","actor":"mario","frame":9,"mode":"16","visit":3,"level":24,"stars":5,"id":"a"}')
        self.assertEqual((f.kind, f.mode, f.level, f.data["stars"]), ("star", "16", 24, 5))
        f = parse_line('[jimmie-social] {"kind":"outcome","fact":"trick_bailed","heard":"watch_real","condition":"called_bail","qpc_ms":5.5}')
        self.assertEqual((f.key, f.ms), ("trick_bailed:jimmie:called_bail", 5.5))
        f = parse_line('[jb] {"k":"played","a":"jimmie","ms":7,"line":12,"scope":"1/1/1/1"}')
        self.assertEqual((f.kind, f.data["line"], f.scope), ("played", 12, "1/1/1/1"))
        self.assertIsNone(parse_line("[jb] not json"))
        self.assertIsNone(parse_line("ordinary engine output"))

    def test_end_to_end_log_to_modfs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            log, sav = tmp / "stdout.log", tmp / "sav"
            d = Director(writer=Writer(ScriptedLLM(default="Okay, that was sick, son."), rng=random.Random(1)),
                         renderer=Renderer(NullTTS(), tmp / "cache", ffmpeg=None), rng=random.Random(3))
            d.rulebook = RuleBook([Rule("g", ("grand_star",), "sincere", write=True, payoff=True),
                                   Rule("c", ("trick_approach",), "boast_call", bank=("castle_door",))])
            b = Bridge(d, log, sav)
            log.write_text('[jb] {"k":"hello","session":"1234567890","ms":100}\n'
                           '[jb] {"k":"arrival","a":"mario","ms":200,"mode":"free","scope":"1/1/1/1","level":9}\n')
            b.step()
            d.write_one()
            b.step()
            with zipfile.ZipFile(sav / "jbplan_1234567890.modfs") as plan:
                rows = plan.read("plan.txt").decode().splitlines()
                properties = json.loads(plan.read("properties.json"))
            head = rows[0].split("|")
            self.assertEqual((head[0], int(head[2])), ("JB1", len(rows) - 1))
            self.assertTrue(properties["files"]["plan.txt"]["isText"])
            by = {r.split("|")[0]: r.split("|") for r in rows[1:]}
            self.assertIn("catchphrase_03.ogg", [r.split("|")[3] for r in rows[1:] if r.startswith("L|")])
            box = [r.split("|")[2] for r in rows[1:] if r.startswith("L|") and r.split("|")[2]][0]
            with zipfile.ZipFile(sav / f"{box}.modfs") as voiced:
                self.assertIn("line.ogg", voiced.namelist())
            self.assertEqual(by["P"][4], "1/1/1/1")
            with log.open("a") as f:
                f.write('[jb] {"k":"played","a":"jimmie","ms":900,"line":%s,"scope":"1/1/1/1"}\n' % by["P"][2])
            b.step()
            self.assertEqual(len(d.memory.spoken), 1)
            b.publisher.cleanup()
            self.assertEqual(list(sav.glob("*.modfs")), [])

    def test_plan_never_references_a_line_the_game_cannot_load(self):
        d = Director(rng=random.Random(0))
        d.observe(fact("arrival"))
        text = plan_text(d.document(), lambda line: None)
        loaded = {r.split("|")[1] for r in text.splitlines() if r.startswith("L|")}
        used = {r.split("|")[2] for r in text.splitlines() if r.startswith("P|")}
        self.assertTrue(used <= loaded)
        with self.assertRaises(ValueError):
            Publisher(Path("."), "../evil")


class EvalTests(unittest.TestCase):
    def test_classifier_separates_obvious_fakes_and_not_identical_sets(self):
        real = ["Fuck yeah, son.", "What the fuck?", "Okay, okay.", "Let's go, dude.", "Holy shit.", "Unbelievable.",
                "Come on, son!", "I fucked up.", "Oh my god.", "No way, dude."] * 3
        fake = ["What a marvelous achievement, Mario.", "I am delighted by your progress.", "That was a wonderful jump indeed.",
                "Truly splendid work, my friend.", "How delightful this adventure is."] * 6
        self.assertGreater(evaluation.authorship_auc(real, fake), 0.9)
        rng = random.Random(5)
        words = "fuck yeah son dude okay what the holy shit come on no way oh my god".split()
        same = [[" ".join(rng.choices(words, k=rng.randint(1, 5))) for _ in range(300)] for _ in range(2)]
        self.assertLess(abs(evaluation.authorship_auc(same[0], same[1]) - 0.5), 0.08)   # same source: a coin flip

    def test_generate_packet_and_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = evaluation.generate(Writer(ScriptedLLM(default="Fuck yeah, son."), rng=random.Random(0)), "adapter")
            b = evaluation.generate(Writer(ScriptedLLM(default="Wonderful."), rng=random.Random(0)), "stock")
            self.assertEqual([r["source"] for r in a if r["scene"] == "idle.run"], ["quiet"])
            self.assertEqual([r["text"] for r in a if r["scene"] == "precision.run_jump"][0] in
                             ("Carrier.", "Tor tor tor.", "Gub gub gub.", "Yeah, cum. Cum is good.", "Bitch."), True)
            evaluation.packet({"adapter": a, "stock": b}, Path(tmp))
            page = (Path(tmp) / "ballot.html").read_text()
            self.assertNotIn("adapter", page)
            key = json.loads((Path(tmp) / "KEY-do-not-open-before-voting.json").read_text())
            ballot = {s: {"pick": str(labels.index("adapter")), "fits": True} for s, labels in key["order"].items()}
            self.assertTrue(evaluation.score(ballot, key, "adapter")["passed"])
            unsure = {s: {"pick": "unsure"} for s in key["order"]}
            self.assertFalse(evaluation.score(unsure, key, "adapter")["passed"])

    def test_copy_rate(self):
        self.assertEqual(evaluation.copy_rate(["I fucked up on that one.", "Brand new sentence here, dude."],
                                              ["i fucked up on that one"]), 0.5)


if __name__ == "__main__":
    unittest.main()
