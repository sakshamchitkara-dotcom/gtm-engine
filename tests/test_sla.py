import tempfile
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

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

    def test_business_hours_skip_nights_weekends_and_dst(self):
        bh, ny = {"start": 9, "end": 18, "days": [0, 1, 2, 3, 4]}, ZoneInfo("America/New_York")
        # Fri 17:00 EDT -> Mon 10:00 EST across the Nov 1 DST change: 1h Friday + 1h Monday
        self.assertAlmostEqual(sla.business_hours(datetime(2026, 10, 30, 21), datetime(2026, 11, 2, 15), ny, bh), 2)
        # created and touched overnight: zero working hours elapsed
        self.assertEqual(sla.business_hours(datetime(2026, 9, 29, 23), datetime(2026, 9, 30, 12), ny, bh), 0)

    def test_holidays_are_skipped_per_zone(self):
        ny = ZoneInfo("America/New_York")
        # Wed 16:00 -> Fri 10:00 EST with Thanksgiving off: 2h Wed + 1h Fri
        bh = {"start": 9, "end": 18, "holidays": ["2026-11-26"]}
        a, b = datetime(2026, 11, 25, 21), datetime(2026, 11, 27, 15)
        self.assertAlmostEqual(sla.business_hours(a, b, ny, bh, {datetime(2026, 11, 26).date()}), 3)
        # dict form: rep email beats zone beats default
        team = {"business_hours": {**bh, "holidays": {"default": ["2026-11-26"], "Europe/Berlin": [],
                                                      "kai@acme.io": ["2026-11-25", "2026-11-26"]}},
                "timezones": {"default": "America/New_York", "lena@acme.io": "Europe/Berlin",
                              "kai@acme.io": "America/New_York"}}
        clock = sla._clock(team)
        self.assertAlmostEqual(clock("sam@acme.io", a, b), 3)
        self.assertAlmostEqual(clock("kai@acme.io", a, b), 1)
        self.assertAlmostEqual(clock("lena@acme.io", a, b), 9 + 7)  # Wed 22:00 -> Fri 16:00 Berlin, no holiday
        self.assertAlmostEqual(sla._clock({"business_hours": bh, "timezones": {"default": "America/New_York"}})("x", a, b), 3)

    def test_report_uses_each_reps_zone(self):
        team = {"sla_hours": {"A": 4}, "business_hours": {"start": 9, "end": 18},
                "timezones": {"default": "America/New_York", "lena@acme.io": "Europe/Berlin"}}
        with tempfile.TemporaryDirectory() as d:
            store = Store(f"{d}/t.db")
            store.upsert_leads([Lead(email="ny@x.io", tier="A", owner="sam@acme.io"),
                                Lead(email="de@y.io", tier="A", owner="lena@acme.io")])
            with store.db:  # both imported Tue 14:00 UTC = 10:00 New York, 16:00 Berlin
                store.db.execute("UPDATE events SET at='2026-09-29 14:00:00'")
            rep = sla.report(store, team, datetime(2026, 9, 29, 19))  # 15:00 NY, 21:00 Berlin
            store.db.close()
        self.assertEqual({b["email"]: b["age_h"] for b in rep["breaches"]}, {"ny@x.io": 5.0})
        self.assertIn("business hours 9-18h", sla.render(rep))

    def test_backfill_estimates_created_for_old_leads(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(f"{d}/t.db")
            with store.db:  # two 0.2-era leads: no created event; one was contacted before its row was updated
                store.db.executemany("INSERT INTO leads (email, data, score, tier, owner, stage, updated_at) "
                                     "VALUES (?, '{}', 90, 'A', 'sam@acme.io', ?, '2026-09-20 12:00:00')",
                                     [("a@x.io", "contacted"), ("b@x.io", "new")])
                store.db.execute("INSERT INTO events (email, kind, at) VALUES ('a@x.io','contacted','2026-09-18 10:00:00')")
            store.upsert_leads([Lead(email="c@x.io", tier="A", owner="sam@acme.io")])  # already tracked
            self.assertEqual(sla.report(store, {"sla_hours": {"A": 4}})["untracked"], 2)
            self.assertEqual(store.backfill_created(), 2)
            self.assertEqual(store.backfill_created(), 0)  # idempotent
            created = store.first_event(("created",))
            store.db.close()
        self.assertEqual((created["a@x.io"], created["b@x.io"]), ("2026-09-18 10:00:00", "2026-09-20 12:00:00"))


if __name__ == "__main__":
    unittest.main()
