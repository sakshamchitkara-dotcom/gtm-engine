import unittest

from gtm import analytics


class CohortTest(unittest.TestCase):
    ROWS = [{"email": "a@x.io", "source": "webinar", "stage": "won", "updated_at": "2026-09-20 00:00:00"},
            {"email": "b@x.io", "source": "webinar", "stage": "lost", "updated_at": "2026-09-20 00:00:00"},
            {"email": "c@x.io", "source": "list", "stage": "new", "updated_at": "2026-09-20 00:00:00"},
            {"email": "d@x.io", "source": "", "stage": "contacted", "updated_at": "2026-09-02 00:00:00"}]
    CREATED = {"a@x.io": "2026-08-03 10:00:00", "b@x.io": "2026-09-01 10:00:00", "c@x.io": "2026-09-01 10:00:00"}

    def test_groups_by_import_month_and_source(self):
        rows = analytics.cohorts(self.ROWS, self.CREATED, {"b@x.io": "meeting"})
        got = {c["cohort"]: c for c in rows}
        self.assertEqual(list(got), ["2026-08 / webinar", "2026-09 / (none)", "2026-09 / list", "2026-09 / webinar"])
        self.assertEqual(got["2026-09 / webinar"], {"cohort": "2026-09 / webinar", "leads": 1, "contacted": 1,
                                                    "meeting": 1, "won": 0, "lost": 1})  # lost after a meeting
        self.assertEqual(got["2026-09 / (none)"]["contacted"], 1)  # no created event: falls back to updated_at
        self.assertEqual(got["2026-09 / list"]["contacted"], 0)

    def test_by_source_and_render(self):
        rows = analytics.cohorts(self.ROWS, self.CREATED, by="source")
        self.assertEqual([(c["cohort"], c["leads"], c["won"], c["lost"]) for c in rows],
                         [("(none)", 1, 0, 0), ("list", 1, 0, 0), ("webinar", 2, 1, 1)])
        out = analytics.render_cohorts(rows)
        self.assertRegex(out.splitlines()[-1], r"^webinar\s+2\s+100%\s+50%\s+1\s+1\s+50%$")
        self.assertIn("-", out.splitlines()[1])  # no closed leads: win rate "-" not a ZeroDivisionError
        self.assertEqual([c["cohort"] for c in analytics.cohorts(self.ROWS, self.CREATED, by="month")],
                         ["2026-08", "2026-09"])


if __name__ == "__main__":
    unittest.main()
