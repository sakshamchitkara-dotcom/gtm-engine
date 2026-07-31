import tempfile
import unittest
from datetime import datetime

from gtm import sla
from gtm.models import Lead
from gtm.store import Store


class SLATest(unittest.TestCase):
    def test_time_to_first_touch_and_breaches(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(f"{d}/t.db")
            mk = lambda e, tier, owner="sam@acme.io": Lead(email=e, tier=tier, owner=owner, domain="x.io")
            store.upsert_leads([mk("fast@x.io", "A"), mk("slow@x.io", "A"), mk("open@x.io", "A"),
                                mk("fresh@x.io", "B"), mk("d@x.io", "D", "nurture")])
            store.upsert_leads([mk("fast@x.io", "A")])  # re-import doesn't restart the clock
            with store.db:
                store.db.execute("UPDATE events SET at='2026-09-25 09:00:00' WHERE kind='created'")
                store.db.executemany("INSERT INTO events (email, kind, at) VALUES (?,?,?)", [
                    ("fast@x.io", "contacted", "2026-09-25 10:00:00"),
                    ("slow@x.io", "contacted", "2026-09-25 19:00:00"),
                    ("slow@x.io", "replied", "2026-09-26 09:00:00")])  # only the first touch counts
            # untouched leads still in 'new' breach once past SLA; touched ones never do
            store.db.execute("UPDATE leads SET stage='contacted' WHERE email IN ('fast@x.io','slow@x.io')")
            store.db.commit()
            store.db.execute("INSERT INTO leads (email, data, score, tier, owner, stage) "
                             "VALUES ('old@x.io', '{}', 90, 'A', 'sam@acme.io', 'new')")
            rep = sla.report(store, {"sla_hours": {"A": 4, "B": 24}}, datetime(2026, 9, 25, 20, 0))
            store.db.close()
        (o,) = rep["owners"]
        self.assertEqual((o["leads"], o["touched"], o["within"], o["median_h"]), (4, 2, 1, 5.5))
        self.assertEqual([b["email"] for b in rep["breaches"]], ["open@x.io"])  # fresh B is 11h < 24h
        self.assertEqual(rep["untracked"], 1)
        self.assertIn("open@x.io", sla.render(rep))


if __name__ == "__main__":
    unittest.main()
