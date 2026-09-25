import json
import socket
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from gtm import pipeline, web
from gtm.outbox import unsub_token
from gtm.store import Store
from tests.test_gtm import SAMPLE


class WebTest(unittest.TestCase):
    TOKEN = "t0ken"

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.store = Store(f"{cls.tmp.name}/t.db")
        pipeline.run(SAMPLE, cls.store, start=date(2026, 9, 1))
        cls.srv = web.make_server(cls.store, port=0, env={"GTM_API_TOKEN": cls.TOKEN, "GTM_UNSUB_SECRET": "k"})
        cls.base = f"http://127.0.0.1:{cls.srv.server_port}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.store.db.close()
        cls.tmp.cleanup()

    def call(self, path, body=None, token=TOKEN, raw=None, ctype="application/json"):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = Request(self.base + path, data=data, method="POST" if data is not None else "GET")
        if data is not None:
            req.add_header("Content-Type", ctype)
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urlopen(req) as r:
                return r.status, r.read().decode()
        except HTTPError as e:
            return e.code, e.read().decode()

    def test_auth(self):
        self.assertEqual(self.call("/api/leads", token=None)[0], 401)
        self.assertEqual(self.call("/api/leads", token="wrong")[0], 401)
        self.assertEqual(self.call("/api/nope")[0], 404)

    def test_dashboard_is_public_but_data_is_not(self):
        status, html = self.call("/", token=None)
        self.assertEqual(status, 200)
        self.assertIn('<script src="/app.js">', html)
        self.assertIn("Authorization", self.call("/app.js", token=None)[1])

    def test_gets(self):
        status, body = self.call("/api/leads?tier=A&limit=2")
        rows = json.loads(body)
        self.assertEqual((status, len(rows), rows[0]["tier"]), (200, 2, "A"))
        self.assertNotIn("data", rows[0])
        self.assertEqual(json.loads(self.call("/api/report")[1])["total"], len(self.store.leads()))
        self.assertEqual(json.loads(self.call("/api/forecast")[1])[-1]["owner"], "TOTAL")
        self.assertEqual(self.call("/api/leads?limit=abc")[0], 400)

    def test_post_leads_validates_then_runs_pipeline(self):
        self.assertEqual(self.call("/api/leads", raw=b"{nope")[0], 400)
        self.assertEqual(self.call("/api/leads", {"email": "a@b.io"}, ctype="text/plain")[0], 415)
        status, body = self.call("/api/leads", [{"email": "x@ok.io"}, {"email": "bad"}, {"email": "y@ok.io", "admin": 1}])
        self.assertEqual(status, 400)
        self.assertEqual([e["index"] for e in json.loads(body)["error"]], [1, 2])
        status, body = self.call("/api/leads", {"email": "new.vp@web-co.io", "title": "VP Sales", "employees": 300,
                                                "industry": "SaaS", "country": "US", "source": "demo_request"})
        out = json.loads(body)
        self.assertEqual((status, out["leads"][0]["tier"]), (201, "A"))
        self.assertIsNotNone(self.store.lead("new.vp@web-co.io"))

    def test_body_limits(self):
        with socket.create_connection(("127.0.0.1", self.srv.server_port)) as s:  # no body needed for a 413
            s.sendall(f"POST /api/signals HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer {self.TOKEN}\r\n"
                      f"Content-Length: {web.MAX_BODY + 1}\r\n\r\n".encode())
            self.assertIn(b" 413 ", s.recv(200))
        self.assertEqual(self.call("/api/leads", [{"email": f"{i}@x.io"} for i in range(web.MAX_ITEMS + 1)])[0], 400)
        self.assertEqual(self.call("/api/leads", [])[0], 400)
        self.assertEqual(self.call("/api/leads", {"email": "a@b.io", "title": "x" * 201})[0], 400)
        self.assertEqual(len(json.loads(self.call("/api/leads?limit=5000")[1])), len(self.store.leads()[:1000]))

    def test_round_robin_advances_across_requests(self):
        owners = set()
        for i in range(3):
            body = {"email": f"rr{i}@rr{i}-co.io", "title": "Manager", "employees": 60,
                    "industry": "saas", "country": "US", "source": "webinar"}
            owners.add(json.loads(self.call("/api/leads", body)[1])["leads"][0]["owner"])
        self.assertEqual(len(owners), 3)

    def test_signals_and_reply_webhook(self):
        status, body = self.call("/api/signals", [{"email": "ana@shopwave.co", "signal": "pricing_page",
                                                   "at": "2026-09-20T10:00:00Z"}])
        self.assertEqual((status, json.loads(body)["inserted"]), (201, 1))
        self.assertEqual(self.call("/api/signals", [{"email": "ana@shopwave.co", "signal": "x", "at": "1"}])[0], 400)
        status, body = self.call("/api/replies", {"email": "sara@tinyapps.dev", "text": "Sounds good, send a calendar link"})
        self.assertEqual(json.loads(body)["label"], "interested")
        self.assertEqual(self.store.lead("sara@tinyapps.dev")["stage"], "replied")
        self.assertEqual(self.call("/api/replies", {"email": "sara@tinyapps.dev"})[0], 400)

    def test_one_click_unsubscribe(self):
        e = "mo@cloudcart.com"
        self.assertEqual(self.call(f"/unsubscribe?email={e}&token=forged", token=None)[0], 403)
        path = f"/unsubscribe?email={e}&token={unsub_token(e, 'k')}"
        self.assertEqual(self.call(path, token=None)[0], 200)            # GET only shows a form
        self.assertNotIn(e, self.store.suppressed())
        status, _ = self.call(path, raw=b"List-Unsubscribe=One-Click", token=None,
                              ctype="application/x-www-form-urlencoded")
        self.assertEqual(status, 200)
        self.assertIn(e, self.store.suppressed())

    def test_slow_client_does_not_block_others(self):
        # a client that promises a body and never sends it used to wedge the single-threaded server
        with socket.create_connection(("127.0.0.1", self.srv.server_port)) as slow:
            slow.sendall(b"POST /api/signals HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\n"
                         b"Authorization: Bearer t0ken\r\nContent-Length: 100\r\n\r\n")
            req = Request(self.base + "/api/report", headers={"Authorization": f"Bearer {self.TOKEN}"})
            with urlopen(req, timeout=3) as r:
                self.assertEqual(r.status, 200)

    def test_concurrent_posts_are_serialized(self):
        def post(i):
            body = {"email": f"cc{i}@cc{i}-co.io", "title": "Manager", "employees": 60,
                    "industry": "saas", "country": "US", "source": "webinar"}
            return self.call("/api/leads", body)[0]
        with ThreadPoolExecutor(8) as pool:
            self.assertEqual(set(pool.map(post, range(24))), {201})
        self.assertEqual(sum(1 for r in self.store.leads() if r["email"].startswith("cc")), 24)
