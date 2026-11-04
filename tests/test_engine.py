"""Run with:  python3 -m unittest discover tests"""
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

from tools import learner  # noqa: E402
from tools.chat_parser import parse_file  # noqa: E402
from tools.intents import detect_intent, extract_times, extract_topic  # noqa: E402
from tools.profile_store import Profile  # noqa: E402
from tools.reply_engine import generate_reply  # noqa: E402
from tools.chat_parser import Message  # noqa: E402
from tools.intents import family  # noqa: E402
from tools.screenshot_parser import bubbles_from_page, clean_ocr, is_junk, stitch  # noqa: E402

SAMPLE = ROOT / "examples" / "sample_chat.txt"


class IntentTests(unittest.TestCase):
    def test_intents(self):
        cases = {
            "when is the deadline for the report?": "q_when",
            "what time is the meeting tomorrow?": "q_when",
            "where can I find the brand guidelines?": "q_where",
            "who should I ask about the invoice?": "q_who",
            "why did they push the launch?": "q_why",
            "how did the client meeting go?": "q_status",
            "how are you?": "checkin",
            "can I leave early on friday?": "permission",
            "can you review my slides?": "request",
            "what do you think about the new logo?": "opinion",
            "sorry running late": "apology",
            "I got the certification!": "news",
            "the dashboard is finished": "done",
            "did you send it?": "yesno",
            "thanks so much!": "thanks",
            "are you free for lunch?": "schedule",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(detect_intent(text), expected)

    def test_everyday_texts_are_not_general(self):
        cases = {
            "ok sounds good": "ack", "k": "ack", "haha nice": "ack", "lol": "laugh", "lmaooo": "laugh", "😂😂": "laugh",
            "goodnight": "goodbye", "ttyl": "goodbye", "i'll call you tomorrow": "goodbye",
            "omw": "whereabouts", "i'll be there at 6": "whereabouts", "just got home": "arrived", "just landed": "arrived",
            "happy birthday!": "wishes", "good luck today": "wishes", "nice work today": "praise", "proud of you": "praise",
            "look at this": "share", "did you see the news": "share", "no way": "react", "wait what": "react",
            "my boss is so annoying": "vent", "traffic is insane": "vent", "i'm so tired": "mood", "i need coffee": "mood",
            "in a meeting": "away", "brb": "away", "lmk when you're free": "request", "send me the file": "request",
            "let's get dinner": "schedule", "wanna watch a movie": "schedule", "running 10 min late": "apology",
            "did u finish the reading": "yesno", "i made pasta tonight": "update", "the weather is so nice today": "update",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(detect_intent(text, "personal"), expected)
        # flirting only exists where it makes sense
        self.assertEqual(detect_intent("wanna grab drinks friday?", "personal"), "schedule")
        self.assertEqual(detect_intent("wanna grab drinks friday?", "talking_stage"), "flirt")

    def test_topic(self):
        self.assertEqual(extract_topic("can you review the q2 budget sheet"), "q2 budget sheet")
        self.assertEqual(extract_topic("what do you think about the new logo?"), "logo")
        self.assertIsNone(extract_topic("are you free?"))

    def test_times(self):
        self.assertEqual(extract_times("let's do after 3 tomorrow"), ["after 3", "tomorrow"])
        self.assertEqual(extract_times("I need 10 minutes"), [])


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        import tools.profile_store as store
        cls._old = store.PROFILES_DIR
        store.PROFILES_DIR = Path(cls.tmp.name)
        cls.profile = learner.create_profile(SAMPLE, "Dana", me="Alex", relationship="boss")

    @classmethod
    def tearDownClass(cls):
        import tools.profile_store as store
        store.PROFILES_DIR = cls._old
        cls.tmp.cleanup()

    def reply(self, text, seed=1):
        return generate_reply(self.profile, [], text, seed=seed)

    def test_parses_sample(self):
        self.assertGreater(len(parse_file(SAMPLE)), 100)

    def test_every_reply_explains_itself(self):
        for text in ["when is it due?", "where's the deck?", "hey", "ok"]:
            out = self.reply(text)
            self.assertTrue(out["replies"])
            self.assertTrue(out["explanation"])

    def test_when_question_gets_a_time(self):
        out = self.reply("when is the budget sheet due?")
        self.assertEqual(out["why"]["intent"], "q_when")
        self.assertTrue(extract_times(" ".join(out["replies"])), out)

    def test_where_question_is_not_permission(self):
        self.assertEqual(self.reply("where can I find the onboarding doc?")["why"]["intent"], "q_where")

    def test_reuses_real_reply_for_same_situation(self):
        out = self.reply("can I leave a bit early on friday? dentist")
        self.assertEqual(out["why"]["strategy"], "reused")

    def test_mentioned_time_is_respected(self):
        out = self.reply("can we meet at 3?")
        text = " ".join(out["replies"])
        self.assertNotIn("after 2", text)
        self.assertIn("3", text)

    def test_uses_their_shorthand(self):
        # Dana writes "u", lowercase, no apostrophes: composed text should too.
        for seed in range(5):
            for bubble in self.reply("why is the meeting cancelled?", seed=seed)["replies"]:
                self.assertEqual(bubble, bubble.lower())
                self.assertNotIn("'", bubble)

    def test_correction_wins_next_time(self):
        profile = Profile("dana", Path(self.tmp.name))
        learner.correct(profile, "can I get a raise?", ["hmm"], ["lets talk at ur review"])
        out = generate_reply(profile, [], "can I get a raise?", seed=1)
        self.assertEqual(out["replies"], ["lets talk at ur review"])
        self.assertIn("you taught", out["explanation"])


class UndoResetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        import tools.profile_store as store
        self._old, store.PROFILES_DIR = store.PROFILES_DIR, Path(self.tmp.name)
        self.p = learner.create_profile(SAMPLE, "Dana", me="Alex", relationship="boss")

    def tearDown(self):
        import tools.profile_store as store
        store.PROFILES_DIR = self._old
        self.tmp.cleanup()

    def test_undo_each_change(self):
        learner.correct(self.p, "can I get a raise?", ["hmm"], ["lets talk at ur review"])
        learner.approve(self.p, "hey", ["morning"])
        learner.add_note(self.p, "calls everyone chief")
        self.assertEqual(len(self.p.snapshots()), 3)
        self.assertIn("note", learner.undo(self.p)["label"])
        self.assertEqual(self.p.meta.get("notes"), "")
        learner.undo(self.p)
        self.assertEqual(self.p.approved(), [])
        self.assertEqual(len(self.p.corrections()), 1)
        learner.undo(self.p)
        self.assertEqual(self.p.corrections(), [])
        self.assertIsNone(learner.undo(self.p))

    def test_reset_keeps_learning_and_is_undoable(self):
        examples = len(self.p.examples())
        learner.correct(self.p, "can I get a raise?", ["hmm"], ["lets talk at ur review"])
        learner.add_note(self.p, "never texts on weekends")
        cleared = learner.reset_feedback(self.p)
        self.assertEqual(cleared, {"corrections": 1, "approved": 0, "notes": 1})
        self.assertEqual(self.p.corrections(), [])
        self.assertEqual(len(self.p.examples()), examples)
        self.assertNotIn("weekends", self.p.persona)
        learner.undo(self.p)
        self.assertEqual(len(self.p.corrections()), 1)
        self.assertIn("weekends", self.p.meta["notes"])

    def test_reset_to_start_undoes_learning(self):
        before = len(self.p.messages())
        with tempfile.TemporaryDirectory() as tmp:
            newer = Path(tmp) / "newer.txt"
            newer.write_text("Alex: are you free friday?\nDana: ya after 2\n", encoding="utf-8")
            added, version = learner.learn(self.p, newer)
        self.assertEqual((added, version), (2, 2))
        learner.correct(self.p, "hey", ["k"], ["morning"])
        self.assertTrue(learner.reset_to_start(self.p))
        self.assertEqual(len(self.p.messages()), before)
        self.assertEqual(self.p.meta["version"], 1)
        self.assertEqual(self.p.corrections(), [])
        self.assertEqual(self.p.snapshots(), [])


class SampleTests(unittest.TestCase):
    """Every sample person parses to its listed size, in its own format, and can reply."""

    def test_samples(self):
        import json
        manifest = json.loads((ROOT / "examples" / "samples" / "samples.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(manifest), 9)
        self.assertGreaterEqual(len({m["relationship"] for m in manifest}), 9)
        with tempfile.TemporaryDirectory() as tmp:
            import tools.profile_store as store
            old, store.PROFILES_DIR = store.PROFILES_DIR, Path(tmp)
            try:
                for m in manifest:
                    with self.subTest(sample=m["id"]):
                        msgs = parse_file(ROOT / m["file"])
                        self.assertEqual(len(msgs), m["messages"])
                        self.assertEqual({x.sender for x in msgs}, {m["target"], m["me"]})
                        p = learner.create_profile(ROOT / m["file"], m["target"], m["name"], m["me"], m["relationship"])
                        out = generate_reply(p, [], "hey how are you?", seed=1)
                        self.assertTrue(out["replies"] and out["explanation"])
            finally:
                store.PROFILES_DIR = old

    def test_generator_is_stable(self):
        """Re-running tools/make_samples.py must reproduce the committed files exactly."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("make_samples", ROOT / "tools" / "make_samples.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for person in mod.PEOPLE:
            body, ext = mod.write(person, mod.play(person))
            self.assertEqual(body, (ROOT / "examples" / "samples" / f"{person['id']}{ext}").read_text(encoding="utf-8"), person["id"])


class FeatureTests(unittest.TestCase):
    def features(self, sid):
        import json
        from tools.features import compute_features
        m = {e["id"]: e for e in json.loads((ROOT / "examples" / "samples" / "samples.json").read_text(encoding="utf-8"))}[sid]
        return compute_features(parse_file(ROOT / m["file"]), m["target"], m["me"], m["relationship"])

    def test_styles_are_told_apart(self):
        jordan, marcus, keisha, taylor = (self.features(s) for s in ("jordan", "marcus", "keisha", "taylor"))
        self.assertGreater(marcus["them"]["formality"], jordan["them"]["formality"] + 50)
        self.assertGreater(keisha["them"]["avg_words"], 4 * jordan["them"]["avg_words"])
        self.assertEqual(jordan["them"]["laugh_style"], "💀")
        self.assertGreater(taylor["them"]["endings_pct"]["."], 80)
        self.assertEqual(sum(jordan["them"]["hours"]), jordan["them"]["messages"])
        self.assertAlmostEqual(sum(jordan["them"]["length_bins"].values()), 100, delta=0.5)

    def test_no_timestamps_means_no_timing(self):
        s = self.features("taylor")["shared"]
        self.assertFalse(s["has_timestamps"])
        self.assertIsNone(s["them_reply_median_s"])
        self.assertIsNone(s["they_start_pct"])

    def test_shared_numbers_add_up(self):
        f = self.features("mom")
        s = f["shared"]
        self.assertEqual(s["messages"], f["them"]["messages"] + f["you"]["messages"])
        self.assertLessEqual(s["active_days"], s["days_span"])
        self.assertIsNotNone(s["them_reply_median_s"])

    def test_csv_row(self):
        from tools.features import flat_row
        row = flat_row("Mom", self.features("mom"))
        for col in ("name", "messages", "them_avg_words", "you_avg_words", "them_endings_pct_.", "them_hours"):
            self.assertIn(col, row)


class RelationshipTests(unittest.TestCase):
    def test_families(self):
        self.assertEqual(family("talking-stage"), "talking_stage")
        self.assertEqual(family("ex"), "ex")
        self.assertEqual(family("boss"), "work")
        self.assertEqual(family("best friend"), "personal")

    def test_romantic_intents_only_outside_work(self):
        self.assertEqual(detect_intent("what are we?", "talking_stage"), "closure")
        self.assertEqual(detect_intent("I miss you", "ex"), "affection")
        self.assertEqual(detect_intent("why did you leave?", "ex"), "closure")
        self.assertEqual(detect_intent("why did you leave early?", "work"), "q_why")

    def test_reference_fills_thin_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            chat = Path(tmp) / "chat.txt"
            chat.write_text("Me: hey\nSam: heyy\nMe: how was work\nSam: long lol\n", encoding="utf-8")
            import tools.profile_store as store
            old, store.PROFILES_DIR = store.PROFILES_DIR, Path(tmp) / "profiles"
            try:
                p = learner.create_profile(chat, "Sam", me="Me", relationship="talking stage")
                out = generate_reply(p, [], "what are we?", seed=1)
                self.assertEqual(out["why"]["strategy"], "reference")
                self.assertIn("reference", out["explanation"])
                off = learner.create_profile(chat, "Sam", name="Sam2", me="Me", relationship="talking stage",
                                             use_reference=False)
                self.assertNotEqual(generate_reply(off, [], "what are we?", seed=1)["why"]["strategy"], "reference")
            finally:
                store.PROFILES_DIR = old


def line(text, x0, x1, y0, h=0.02):
    return {"text": text, "x0": x0, "x1": x1, "y0": y0, "y1": y0 + h}


class ScreenshotTests(unittest.TestCase):
    def test_sides_and_chrome(self):
        page = {"lines": [
            line("9:41", 0.08, 0.15, 0.02),                 # status bar
            line("sam.k", 0.2, 0.3, 0.06),                  # header
            line("Today 8:02 PM", 0.36, 0.55, 0.15),        # centred divider
            line("hey how was your day", 0.55, 0.92, 0.20), # right = me
            line("hiii it was good!!", 0.16, 0.62, 0.25),   # left = them
            line("pretty chill, kinda tired", 0.40, 0.92, 0.32),
            line("honestly", 0.40, 0.60, 0.348),            # wrapped line of the same bubble
            line("Seen", 0.82, 0.92, 0.40),
            line("Message...", 0.1, 0.27, 0.93),            # typing bar
        ]}
        self.assertEqual(bubbles_from_page(page), [
            {"side": "right", "text": "hey how was your day"},
            {"side": "left", "text": "hiii it was good!!"},
            {"side": "right", "text": "pretty chill, kinda tired honestly"},
        ])

    def test_junk_and_cleanup(self):
        for junk in ["Seen", "Active now", "Today 8:02 PM", "Mon 9:12 AM", "Liked a message", "Message..."]:
            self.assertTrue(is_junk(junk), junk)
        for keep in ["k", "ok", "sent it!", "lol", "see you at 9"]:
            self.assertFalse(is_junk(keep), keep)
        self.assertEqual(clean_ocr("work was a lot and | need sleep ®"), "work was a lot and I need sleep")

    def test_stitch_overlap_with_ocr_noise(self):
        a = [Message("Me", "hey"), Message("Them", "omg yes"), Message("Them", "7?"), Message("Me", "ya")]
        again = [Message("Them", "omg yes"), Message("Them", "77?"), Message("Me", "ya")]
        self.assertEqual(len(stitch(a, again)), 4)                                  # already have it
        self.assertEqual(len(stitch(a, again[2:] + [Message("Them", "night")])), 5)  # overlap + 1 new


if __name__ == "__main__":
    unittest.main()
