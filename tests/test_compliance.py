import tempfile
import unittest
from datetime import date
from pathlib import Path

from gtm import compliance, pipeline
from gtm.models import Lead
from gtm.store import Store

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample_leads.csv"


class ComplianceTest(unittest.TestCase):
    def test_check(self):
        sup = {"bad@x.io", "blocked.com"}
        self.assertEqual(compliance.check(Lead(email="bad@x.io"), sup), "suppressed")
        self.assertEqual(compliance.check(Lead(email="a@blocked.com"), sup), "suppressed")
        self.assertEqual(compliance.check(Lead(email="a@ok.io", country="US", source="list"), sup), "")
        self.assertIn("gdpr", compliance.check(Lead(email="a@ok.de", country="DE", source="list"), sup))
        self.assertEqual(compliance.check(Lead(email="a@ok.de", country="DE", source="webinar"), sup), "")

    def test_suppression_blocks_touches_in_pipeline(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(f"{d}/t.db")
            store.suppress("ledgerly.com", "customer")
            _, stats = pipeline.run(SAMPLE, store, start=date(2026, 9, 1))
            self.assertEqual(stats["blocked"], 1)
            self.assertFalse([t for t in store.touches_due("2026-12-31") if t["email"] == "tom.b@ledgerly.com"])

    def test_unsubscribe(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(f"{d}/t.db")
            pipeline.run(SAMPLE, store, start=date(2026, 9, 1))
            compliance.unsubscribe(store, "Priya@Northwind.io")
            compliance.unsubscribe(store, "stranger@nowhere.io")  # unknown lead: no crash
            self.assertIn("priya@northwind.io", store.suppressed())
            self.assertFalse([t for t in store.touches_due("2026-12-31") if t["email"] == "priya@northwind.io"])
            stage = {r["email"]: r["stage"] for r in store.leads()}["priya@northwind.io"]
            self.assertEqual(stage, "lost")
