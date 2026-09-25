import tempfile
import unittest
from datetime import date

from gtm import pipeline, replies
from gtm.store import Store
from tests.test_gtm import SAMPLE


class RepliesTest(unittest.TestCase):
    def test_classify(self):
        cases = {
            "Sounds good, what times work Thursday?": "interested",
            "Can you send me more info?": "interested",
            "Not interested, thanks.": "negative",
            "We already use Outreach for this.": "negative",
            "Not right now - circle back next quarter?": "not_now",
            "I'm out of the office until Oct 2 with limited access to email.": "ooo",
            "I'm not the right person, reach out to dana@northwind.io": "referral",
            "Please unsubscribe me from this list": "unsubscribe",
            "Stop emailing me.": "unsubscribe",
            "Who is this?": "other",
        }
        for text, label in cases.items():
            self.assertEqual(replies.classify(text), label, text)

    def test_apply_updates_store(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(f"{d}/t.db")
            pipeline.run(SAMPLE, store, start=date(2026, 9, 1))
            stage = lambda e: store.lead(e)["stage"]
            pending = lambda e: [t for t in store.touches_due("2026-12-31") if t["email"] == e]

            self.assertEqual(replies.apply(store, "ana@shopwave.co", "I'm OOO this week")[0], "ooo")
            self.assertTrue(pending("ana@shopwave.co"))
            self.assertEqual(stage("ana@shopwave.co"), "new")

            label, note = replies.apply(store, "priya@northwind.io", "Talk to my colleague: dana@northwind.io")
            self.assertEqual((label, note), ("referral", "referred to dana@northwind.io"))
            self.assertEqual(stage("priya@northwind.io"), "replied")
            self.assertFalse(pending("priya@northwind.io"))

            store.set_stage("tom.b@ledgerly.com", "meeting")
            replies.apply(store, "tom.b@ledgerly.com", "sounds great")
            self.assertEqual(stage("tom.b@ledgerly.com"), "meeting")  # never moves backwards

            replies.apply(store, "lucas@quantpay.com", "unsubscribe")
            self.assertIn("lucas@quantpay.com", store.suppressed())
            self.assertEqual(stage("lucas@quantpay.com"), "lost")
