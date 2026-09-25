import tempfile
import unittest
from datetime import date
from pathlib import Path

from gtm import digest, pipeline
from gtm.store import Store
from tests.test_gtm import SAMPLE


class DigestTest(unittest.TestCase):
    def test_digest_sections(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(f"{d}/t.db")
            pipeline.run(SAMPLE, store, start=date(2026, 9, 1))
            owner = store.lead("priya@northwind.io")["owner"]
            store.set_stage("priya@northwind.io", "replied")
            md = digest.render(store, owner, "2026-09-02")
            self.assertIn(f"# Daily digest: {owner} (2026-09-02)", md)
            self.assertIn("| priya@northwind.io | Northwind | 100 |", md)
            self.assertIn("## Touches due", md)
            paths = digest.write_all(store, "2026-09-02", Path(d) / "digests")
            self.assertIn(f"{owner}.md", {p.name for p in paths})
            self.assertNotIn("nurture.md", {p.name for p in paths})

    def test_cell_escapes_pipes(self):
        self.assertEqual(digest._cell("a|b\nc"), "a\\|b c")
