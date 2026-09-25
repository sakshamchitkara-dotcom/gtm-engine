import tempfile
import unittest
from datetime import date
from email import message_from_bytes
from pathlib import Path
from unittest import mock

from gtm import outbox, pipeline
from gtm.store import Store
from tests.test_gtm import SAMPLE


class FakeSMTP:
    def __init__(self):
        self.msgs = []

    def send_message(self, msg):
        self.msgs.append(msg)


class OutboxTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(f"{self.tmp.name}/t.db")
        pipeline.run(SAMPLE, self.store, start=date(2026, 9, 1))
        self.team = {"daily_send_cap": {"default": 100}}

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def test_dry_run_writes_eml_and_leaves_db_alone(self):
        out = Path(self.tmp.name) / "out"
        stats = outbox.send_due(self.store, "2026-09-01", self.team, out_dir=out)
        files = sorted(out.rglob("*.eml"))
        self.assertEqual(stats["sent"], len(files))
        self.assertGreater(len(files), 0)
        msg = message_from_bytes(files[0].read_bytes())
        self.assertIn("mailto:", msg["List-Unsubscribe"])
        self.assertEqual(self.store.sent_keys(), set())
        self.assertTrue(all(r["stage"] == "new" for r in self.store.leads()))

    def test_send_records_caps_and_skips(self):
        self.store.suppress("northwind.io")
        smtp = FakeSMTP()
        env = {"GTM_BASE_URL": "https://gtm.example.com", "GTM_UNSUB_SECRET": "s3cret"}
        with mock.patch.dict("os.environ", env):
            stats = outbox.send_due(self.store, "2026-09-01", {"daily_send_cap": {"default": 1}}, transport=smtp)
        owners = [m["From"] for m in smtp.msgs]
        self.assertEqual(len(owners), len(set(owners)))  # cap 1 per rep
        self.assertEqual(stats["skipped_contact"], 1)     # northwind suppressed
        self.assertGreater(stats["capped"], 0)
        m = smtp.msgs[0]
        self.assertEqual(m["List-Unsubscribe-Post"], "List-Unsubscribe=One-Click")
        self.assertIn("https://gtm.example.com/unsubscribe?email=", m["List-Unsubscribe"])
        self.assertEqual(self.store.lead(m["To"])["stage"], "contacted")
        again = outbox.send_due(self.store, "2026-09-01", self.team, transport=FakeSMTP())
        self.assertEqual(again["skipped_sent"], stats["sent"])

    def test_refused_recipient_does_not_stop_the_run(self):
        class Refusing(FakeSMTP):
            def send_message(self, msg):
                if msg["To"] == "priya@northwind.io":
                    raise outbox.smtplib.SMTPRecipientsRefused({msg["To"]: (550, b"no such user")})
                super().send_message(msg)
        smtp = Refusing()
        stats = outbox.send_due(self.store, "2026-09-01", self.team, transport=smtp)
        self.assertEqual(stats["refused"], 1)
        self.assertEqual(stats["sent"], len(smtp.msgs))
        self.assertNotIn(("priya@northwind.io", 1), self.store.sent_keys())

    def test_missing_smtp_config_is_a_clean_error(self):
        with mock.patch.dict("os.environ", {}, clear=True), self.assertRaisesRegex(RuntimeError, "SMTP_HOST"):
            outbox.send_due(self.store, "2026-09-01", self.team)
        self.assertEqual(self.store.sent_keys(), set())

    def test_safe_filename(self):
        self.assertEqual(outbox._safe("../../a/b@x.io-1.eml"), ".._.._a_b@x.io-1.eml")

    def test_token_is_per_email(self):
        self.assertNotEqual(outbox.unsub_token("a@x.io", "k"), outbox.unsub_token("b@x.io", "k"))
        self.assertEqual(outbox.unsub_token("A@x.io", "k"), outbox.unsub_token("a@x.io", "k"))
