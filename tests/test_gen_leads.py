import csv
import importlib.util
import tempfile
import unittest
from datetime import date
from pathlib import Path

from gtm import pipeline
from gtm.store import Store

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("gen_leads", ROOT / "scripts" / "gen_leads.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)


class GenLeadsTest(unittest.TestCase):
    def test_seeded_and_messy(self):
        a = gen.generate(500, seed=3, asof=date(2026, 9, 25))
        self.assertEqual(a, gen.generate(500, seed=3, asof=date(2026, 9, 25)))
        rows, signals = a
        self.assertEqual(len(rows), 500)
        self.assertGreater(len(signals), 100)

    def test_outcomes_follow_hidden_model(self):
        rows, _ = gen.generate(800, seed=3, asof=date(2026, 9, 25))
        closed = gen.outcomes(rows, seed=3)
        self.assertEqual(closed, gen.outcomes(rows, seed=3))
        self.assertTrue(0.3 < len(closed) / len(rows) < 0.5)
        industry = {r[0]: r[6] for r in rows}
        rate = lambda ind: (lambda xs: sum(xs) / len(xs))([s == "won" for e, s in closed if industry[e] == ind])
        self.assertGreater(rate("Fintech"), rate("Retail") + 0.15)

    def test_pipeline_handles_generated_data(self):
        rows, _ = gen.generate(500, seed=3, asof=date(2026, 9, 25))
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "leads.csv"
            with open(path, "w", newline="") as f:
                csv.writer(f).writerows([gen.HEADER] + rows)
            _, stats = pipeline.run(path, Store(f"{d}/t.db"), start=date(2026, 9, 28))
        for key in ("invalid", "duplicates", "person_dupes", "undeliverable", "blocked"):
            self.assertGreater(stats[key], 0, key)
