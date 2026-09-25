import tempfile
import unittest
from datetime import date, datetime

from gtm import intent, pipeline
from gtm.models import Lead
from gtm.store import Store
from tests.test_gtm import SAMPLE


class IntentTest(unittest.TestCase):
    def test_decay_and_cap(self):
        now = datetime(2026, 9, 25)
        sigs = [("a@x.io", "pricing_page", "2026-09-25T00:00:00"),
                ("a@x.io", "demo_page", "2026-09-18T00:00:00"),   # one half-life old -> 10
                ("x.io", "g2_visit", "2026-09-11"),               # two half-lives, account-level -> 2.5
                ("b@x.io", "demo_page", "2026-09-30")]            # future clamps to age 0
        pts = intent.points(sigs, now)
        self.assertAlmostEqual(pts["a@x.io"], 25)
        self.assertAlmostEqual(pts["x.io"], 2.5)
        self.assertEqual(intent.for_lead(Lead(email="a@x.io"), pts), 28)
        self.assertEqual(intent.for_lead(Lead(email="b@x.io"), pts), 22)
        self.assertEqual(intent.for_lead(Lead(email="z@y.io"), pts), 0)
        pts["a@x.io"] = 99
        self.assertEqual(intent.for_lead(Lead(email="a@x.io"), pts), intent.CAP)

    def test_clean_rejects_junk(self):
        self.assertEqual(intent.clean(" A@X.io ", "Docs", "2026-09-01T10:00:00Z"),
                         ("a@x.io", "docs", "2026-09-01T10:00:00"))
        for bad in [("", "docs", "2026-09-01"), ("a@x.io", "hack", "2026-09-01"), ("a@x.io", "docs", "nope")]:
            with self.assertRaises(ValueError):
                intent.clean(*bad)

    def test_intent_lifts_score(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(f"{d}/t.db")
            pipeline.run(SAMPLE, store, start=date(2026, 9, 1))
            before = {r["email"]: r["score"] for r in store.leads()}["ana@shopwave.co"]
            store.add_signals([("ana@shopwave.co", "demo_page", "2026-09-25T00:00:00")])
            pipeline.run(SAMPLE, store, start=date(2026, 9, 1), asof=datetime(2026, 9, 25))
            after = {r["email"]: r["score"] for r in store.leads()}["ana@shopwave.co"]
            self.assertEqual(after - before, 20)
