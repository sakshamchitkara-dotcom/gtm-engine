import tempfile
import unittest
from datetime import date
from pathlib import Path

from gtm import analytics, pipeline
from gtm.enrich import enrich, seniority_of, size_band
from gtm.ingest import load_csv
from gtm.models import Lead
from gtm.routing import REGIONS, Router, load_team
from gtm.scoring import load_config, score
from gtm.sequences import build
from gtm.store import Store

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample_leads.csv"


class GTMTest(unittest.TestCase):
    def test_ingest_drops_invalid_and_dupes(self):
        leads, stats = load_csv(SAMPLE)
        self.assertEqual(stats, {"rows": 12, "invalid": 1, "duplicates": 1, "kept": 10})
        self.assertEqual(leads[0].first_name, "Priya")

    def test_ingest_aliases_bom_and_ranges(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "hubspot.csv")
            p.write_text("\ufeffEmail Address,FirstName,Job Title,Organization,Company Size,HQ Country,Lead Source\n"
                         " Ana@Co.IO ,ana,VP Sales,Co,51-200,us,Demo_Request\n"
                         "ana@co.io,dup,,,,,\n", encoding="utf-8")
            leads, stats = load_csv(p)
        self.assertEqual(stats, {"rows": 2, "invalid": 0, "duplicates": 1, "kept": 1})
        a = leads[0]
        self.assertEqual((a.email, a.first_name, a.company, a.employees, a.country, a.source),
                         ("ana@co.io", "Ana", "Co", 51, "US", "demo_request"))

    def test_sequence_fills_blanks_and_dept(self):
        lead = Lead(email="x@co.io", title="Growth Marketing Manager", tier="B", owner="sam@acme.io")
        first = build(lead, date(2026, 9, 28))[0]
        self.assertIn("Hi there", first["body"])
        self.assertIn("growth teams at companies like your team", first["body"])
        self.assertNotIn("$", first["subject"] + first["body"])

    def test_enrichment_rules(self):
        self.assertEqual(seniority_of("VP of Revenue Operations"), "vp")
        self.assertEqual(seniority_of("Chief Revenue Officer"), "c_level")
        self.assertEqual(seniority_of("Software Engineer"), "ic")
        self.assertEqual(seniority_of("Head of Sales"), "vp")
        self.assertEqual(size_band(450), "upper_mid")
        self.assertTrue(enrich(Lead(email="x@gmail.com")).is_free_email)

    def test_scoring_orders_icp_above_junk(self):
        cfg = load_config()
        good = score(enrich(Lead(email="a@co.io", title="VP Revenue", employees=300,
                                 industry="saas", country="US", source="demo_request")), cfg)
        bad = score(enrich(Lead(email="b@gmail.com", title="Student", employees=1)), cfg)
        self.assertEqual(good.tier, "A")
        self.assertEqual(good.score, 100)  # clamped
        self.assertEqual((bad.score, bad.tier), (0, "D"))

    def test_routing_round_robin_and_nurture(self):
        r = Router()
        a = [r.assign(Lead(email=f"{i}@x.com", tier="B", country="US")).owner for i in range(4)]
        self.assertEqual(a, ["sam@acme.io", "riley@acme.io", "alex@acme.io", "sam@acme.io"])
        self.assertEqual(r.assign(Lead(email="d@x.com", tier="D")).owner, "nurture")
        ent = Lead(email="e@x.com", tier="A", size_band="enterprise", country="DE")
        self.assertEqual(r.assign(ent).owner, "lena@acme.io")

    def test_routing_keeps_accounts_together(self):
        r = Router()
        mk = lambda e, **kw: Lead(email=e, domain=e.split("@")[1], country="US", **kw)
        first = r.assign(mk("a@big.io", tier="B")).owner
        self.assertEqual(r.assign(mk("b@big.io", tier="A", size_band="enterprise")).owner, first)
        self.assertNotEqual(r.assign(mk("c@other.io", tier="B")).owner, first)
        free = [r.assign(mk(f"{i}@gmail.com", tier="B", is_free_email=True)).owner for i in range(3)]
        self.assertEqual(len(set(free)), 3)  # free-email domains are not accounts

    def test_territories_from_team_config(self):
        team = {"sdr": {"LATAM": ["br@x.io"], "ROW": ["row@x.io"]},
                "territories": {"LATAM": ["BR", "MX"]}, "default_region": "ROW"}
        r = Router(team)
        self.assertEqual(r.assign(Lead(email="a@x.com", tier="B", country="BR")).owner, "br@x.io")
        self.assertEqual(r.assign(Lead(email="b@y.com", tier="B", country="US")).owner, "row@x.io")
        # bundled team.json spells out the same territories the code falls back to
        self.assertEqual({k: set(v) for k, v in load_team()["territories"].items()}, REGIONS)

    def test_routing_respects_capacity(self):
        team = {"sdr": {"NA": ["a@x.io", "b@x.io"]}, "capacity": {"default": 2, "b@x.io": 1}}
        r = Router(team)
        owners = [r.assign(Lead(email=f"{i}@y.com", tier="B", country="US")).owner for i in range(4)]
        self.assertEqual(owners, ["a@x.io", "b@x.io", "a@x.io", "unassigned"])
        self.assertEqual(r.load, {"a@x.io": 2, "b@x.io": 1})
        self.assertEqual(build(Lead(email="u@y.com", tier="B", owner="unassigned")), [])

    def test_sequence_skips_weekends(self):
        lead = Lead(email="a@co.io", first_name="Ana", company="Co", tier="A", owner="sam@acme.io")
        touches = build(lead, date(2026, 9, 4))  # Friday
        self.assertEqual(len(touches), 5)
        self.assertEqual(touches[1]["date"], "2026-09-07")  # sat -> mon
        self.assertIn("Ana", touches[0]["body"])
        self.assertEqual(build(Lead(email="d@x.com", tier="D"), date(2026, 9, 4)), [])

    def test_pipeline_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(f"{d}/t.db")
            leads, stats = pipeline.run(SAMPLE, store, start=date(2026, 9, 1))
            rows = store.leads()
            self.assertEqual(len(rows), 10)
            self.assertEqual(rows[0]["tier"], "A")
            store.set_stage("priya@northwind.io", "meeting")
            f = dict((s, n) for s, n, _ in analytics.funnel(store.leads()))
            self.assertEqual((f["new"], f["contacted"], f["meeting"], f["won"]), (10, 1, 1, 0))
            with self.assertRaises(KeyError):
                store.set_stage("ghost@x.com", "won")
            # re-running is idempotent
            pipeline.run(SAMPLE, store, start=date(2026, 9, 1))
            self.assertEqual(len(store.leads()), 10)
            stages = {r["email"]: r["stage"] for r in store.leads()}
            self.assertEqual(stages["priya@northwind.io"], "meeting")  # upsert keeps funnel stage
            store.set_stage("priya@northwind.io", "lost")  # lost after the meeting
            f = dict((s, n) for s, n, _ in analytics.funnel(store.leads(), store.peak_stages()))
            self.assertEqual((f["contacted"], f["replied"], f["meeting"]), (1, 1, 1))

    def test_best_lead_decides_account_owner(self):
        with tempfile.TemporaryDirectory() as d:
            ic = Lead(email="ic@bigco.io", title="Analyst", employees=5000, industry="saas", country="US",
                      source="list")
            vp = Lead(email="vp@bigco.io", title="VP Revenue", employees=5000, industry="saas", country="US",
                      source="demo_request")
            leads, _ = pipeline.process([ic, vp], Store(f"{d}/t.db"))  # CSV order: IC first
            self.assertEqual(vp.tier, "A")
            self.assertNotEqual(ic.tier, "A")
            self.assertIn(vp.owner, ("maya@acme.io", "jordan@acme.io"))  # AE pool, not SDR
            self.assertEqual(ic.owner, vp.owner)

    def test_rerun_keeps_owners_when_new_leads_arrive(self):
        mk = lambda e: Lead(email=e, title="Manager", employees=60, industry="saas", country="US", source="webinar")
        with tempfile.TemporaryDirectory() as d:
            store = Store(f"{d}/t.db")
            pipeline.process([mk("a@one.io")], store)
            before = store.lead("a@one.io")["owner"]
            pipeline.process([mk("b@two.io"), mk("c@one.io"), mk("a@one.io")], store)  # new lead routed first
            self.assertEqual(store.lead("a@one.io")["owner"], before)
            self.assertEqual(store.lead("c@one.io")["owner"], before)  # account stays sticky across runs

    def test_config_dir_override(self):
        import json, os
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            Path(d, "team.json").write_text(json.dumps({"sdr": {"NA": ["only@x.io"]}}))
            with mock.patch.dict(os.environ, {"GTM_CONFIG_DIR": d}):
                self.assertEqual(load_team(), {"sdr": {"NA": ["only@x.io"]}})
        self.assertIn("maya@acme.io", load_team()["ae"]["NA"])  # bundled default


if __name__ == "__main__":
    unittest.main()
