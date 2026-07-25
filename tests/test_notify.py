import json
import tempfile
import threading
import unittest
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer

from gtm import notify, pipeline
from gtm.store import Store
from tests.test_gtm import SAMPLE


class Hook(BaseHTTPRequestHandler):
    got = []

    def do_POST(self):
        Hook.got.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


class NotifyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(f"{self.tmp.name}/t.db")
        pipeline.run(SAMPLE, self.store, start=date(2026, 9, 28))
        self.tier_a = [r["email"] for r in self.store.leads("A") if not r["blocked"]]

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def test_dry_run_records_nothing(self):
        body, sent = notify.run(self.store)
        self.assertFalse(sent)
        self.assertTrue(all(e in body["text"] for e in self.tier_a))
        self.assertEqual(notify.pending(self.store)[0]["tier"], "A")  # still pending

    def test_send_posts_once(self):
        srv = HTTPServer(("127.0.0.1", 0), Hook)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{srv.server_port}/hook"
            self.assertTrue(notify.run(self.store, url)[1])
            self.assertEqual(notify.run(self.store, url), (None, False))  # already announced
        finally:
            srv.shutdown()
            srv.server_close()
        self.assertEqual(len(Hook.got), 1)
        self.assertEqual(self.store.notified(), set(self.tier_a))

    def test_lead_data_cannot_ping_or_link(self):
        text = notify.payload([{"email": "x@y.io", "first_name": "<!channel>", "title": "<http://evil|click>",
                                "company": "A&B", "domain": "y.io", "score": 90, "owner": "sam@acme.io"}])["text"]
        self.assertNotIn("<", text)
        self.assertIn("&lt;!channel&gt;", text)
        self.assertIn("A&amp;B", text)
