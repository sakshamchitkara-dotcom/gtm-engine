"""Drives gtm.cli.main() the way a user does, on the sample CSV."""
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from gtm import cli
from gtm.store import Store
from tests.test_gtm import SAMPLE


class CLITest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = f"{self.tmp.name}/t.db"
        self.gtm("run", str(SAMPLE), "--start", "2026-09-28", "--asof", "2026-09-25T18:00:00")

    def tearDown(self):
        self.tmp.cleanup()

    def gtm(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            cli.main(["--db", self.db, *argv])
        return out.getvalue()

    def test_run_is_idempotent(self):
        out = self.gtm("run", str(SAMPLE), "--start", "2026-09-28")
        self.assertTrue(out.startswith("rows=12 kept=10 invalid=1 dupes=1+"), out)
        self.assertEqual(len(self.gtm("leads", "--limit", "50").splitlines()), 10)

    def test_reports(self):
        self.assertIn("Leads: 10", self.gtm("report"))
        self.assertIn("win rate", self.gtm("cohorts", "--by", "source"))
        self.assertIn("TOTAL", self.gtm("forecast"))
        self.assertIn("missing", self.gtm("accounts"))
        self.assertIn("challenger vs control", self.gtm("experiment"))
        self.assertTrue(self.gtm("today", "--date", "2026-09-28").strip())

    def test_stage_reply_and_suppress(self):
        self.assertEqual(self.gtm("stage", "priya@northwind.io", "meeting").strip(), "priya@northwind.io -> meeting")
        with self.assertRaises(SystemExit) as e:
            self.gtm("stage", "ghost@nowhere.io", "won")
        self.assertIn("no lead", str(e.exception))
        self.assertIn("unsubscribe", self.gtm("reply", "sara@tinyapps.dev", "please remove me"))
        self.assertIn("sara@tinyapps.dev", self.gtm("suppress", "--list"))
        self.gtm("suppress", "spam.io")
        self.assertIn("spam.io", self.gtm("suppress"))

    def test_today_hides_sent_touches_and_closed_leads(self):
        before = self.gtm("today", "--date", "2026-12-31")
        self.assertIn("priya@northwind.io", before)
        self.gtm("stage", "priya@northwind.io", "meeting")
        store = Store(self.db)
        other = next(l.split()[2] for l in before.splitlines() if "priya" not in l and " email " in l)
        store.record_send(other, 1, "x", "2026-09-28")
        store.db.close()
        after = self.gtm("today", "--date", "2026-12-31")
        self.assertNotIn("priya@northwind.io", after)
        self.assertEqual(sum(other in l for l in after.splitlines()), sum(other in l for l in before.splitlines()) - 1)

    def test_missing_files_exit_cleanly(self):
        for argv in (["run", "nope.csv"], ["signals", "nope.csv"], ["outcomes", "nope.csv"],
                     ["sla", "--team", "nope.json"], ["run", str(SAMPLE), "--config", "nope.json"]):
            with self.assertRaises(SystemExit) as e:
                self.gtm(*argv)
            self.assertEqual(str(e.exception), f"{argv[0]}: no such file: nope." + argv[-1].split(".")[-1])

    def test_run_map_errors_exit_cleanly(self):
        self.noemail = Path(self.tmp.name, "noemail.csv")
        self.noemail.write_text("Contact,Company\nana@co.io,Co\n")
        for m, msg in (("email", "run: expected HEADER=FIELD"), ("x=mail", "run: unknown field 'mail'"),
                       ("Nope=email", "run: --map columns not in"), ("Company=title", "run: no email column")):
            with self.assertRaises(SystemExit) as e:
                self.gtm("run", str(self.noemail if m.startswith("Company") else SAMPLE), "--map", m)
            self.assertTrue(str(e.exception).startswith(msg), e.exception)

    def test_outcomes_bulk_stage(self):
        p = Path(self.tmp.name, "o.csv")
        p.write_text("email,stage\nPriya@Northwind.io,won\nghost@x.io,lost\nsara@tinyapps.dev,maybe\n")
        self.assertEqual(self.gtm("outcomes", str(p)).strip(), "updated=1 unknown_lead=1 bad_stage=1")
        store = Store(self.db)
        self.assertEqual(store.lead("priya@northwind.io")["stage"], "won")
        store.db.close()

    def test_verify_and_export(self):
        out = self.gtm("verify", "a@gmial.com", "info@acme.io", "bad")
        self.assertEqual([l.split()[0] for l in out.splitlines()], ["invalid", "risky", "invalid"])
        hub = self.gtm("export", "--format", "hubspot").splitlines()
        self.assertTrue(hub[0].startswith("Email,First Name"))
        self.assertEqual(len(hub), 11)
        self.assertEqual(len(self.gtm("export", "--tier", "A").splitlines()) - 1,
                         len(self.gtm("leads", "--tier", "A").splitlines()))

    def test_outbox_dry_run_and_digest(self):
        out_dir = Path(self.tmp.name, "outbox")
        out = self.gtm("outbox", "--date", "2026-09-28", "--dry-run", "--out", str(out_dir))
        self.assertIn("dry run", out)
        self.assertTrue(list(out_dir.rglob("*.eml")))
        paths = self.gtm("digest", "--date", "2026-09-28", "--out", f"{self.tmp.name}/dg").split()
        self.assertTrue(paths and all(Path(p).exists() for p in paths))
        owner = Path(paths[0]).stem
        self.assertIn(f"# Daily digest: {owner}", self.gtm("digest", "--date", "2026-09-28", "--rep", owner))
