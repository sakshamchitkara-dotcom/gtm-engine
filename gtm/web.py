"""stdlib JSON API + HTML dashboard (GET /) over the store.

GET  /api/leads?tier=&owner=&limit=   GET /api/report   GET /api/forecast   GET /api/accounts
POST /api/leads    {lead} or [{lead}, ...]      -> runs the pipeline on them
POST /api/signals  {signal} or [{email, signal, at}, ...]
POST /api/replies  {"email", "text"}            -> reply webhook (classify + update)
GET|POST /unsubscribe?email=&token=             -> one-click unsubscribe (RFC 8058)

If GTM_API_TOKEN is set, every /api/* call needs "Authorization: Bearer <token>".

ponytail: single-threaded HTTPServer sharing one SQLite connection. Fine for a
team dashboard; put a real WSGI server in front if you expose it to traffic.
"""
import hmac
import json
import os
import re
import sys
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import accounts, analytics, compliance, forecast, intent, pipeline, replies
from .ingest import normalize
from .outbox import unsub_token
from .store import Store

STATIC = Path(__file__).resolve().parent / "static"
MAX_BODY = 1_000_000
MAX_ITEMS = 1000
LEAD_FIELDS = {"email", "first_name", "last_name", "title", "company", "employees", "industry", "country", "source"}
EMAIL_RE = re.compile(r"^[^@\s/\\]+@[^@\s/\\]+\.[a-z]{2,}$", re.I)


class BadRequest(Exception):
    def __init__(self, detail, status=HTTPStatus.BAD_REQUEST):
        super().__init__(detail)
        self.detail, self.status = detail, status


def _items(body):
    items = body if isinstance(body, list) else [body]
    if not items or len(items) > MAX_ITEMS or not all(isinstance(i, dict) for i in items):
        raise BadRequest(f"expected an object or a list of 1-{MAX_ITEMS} objects")
    return items


def parse_leads(body):
    leads, errors = [], []
    for n, item in enumerate(_items(body)):
        unknown = set(item) - LEAD_FIELDS
        bad = [k for k, v in item.items() if not isinstance(v, (str, int)) or isinstance(v, bool) or len(str(v)) > 200]
        lead = None if unknown or bad else normalize({k: str(v) for k, v in item.items()})
        if lead is None:
            errors.append({"index": n, "error": f"unknown fields {sorted(unknown)}" if unknown
                           else f"bad values {sorted(bad)}" if bad else "invalid email"})
        else:
            leads.append(lead)
    if errors:
        raise BadRequest(errors)
    return leads


def parse_signals(body):
    out, errors = [], []
    for n, item in enumerate(_items(body)):
        try:
            if not all(isinstance(item.get(k), str) for k in ("email", "signal", "at")):
                raise ValueError("email, signal and at must be strings")
            out.append(intent.clean(item["email"], item["signal"], item["at"]))
        except ValueError as e:
            errors.append({"index": n, "error": str(e)})
    if errors:
        raise BadRequest(errors)
    return out


def parse_reply(body):
    if not isinstance(body, dict):
        raise BadRequest("expected an object")
    email, text = body.get("email"), body.get("text")
    if not isinstance(email, str) or not EMAIL_RE.match(email.strip()):
        raise BadRequest("email is required")
    if not isinstance(text, str) or not text.strip() or len(text) > 20_000:
        raise BadRequest("text is required (max 20000 chars)")
    return email.strip().lower(), text


class Handler(BaseHTTPRequestHandler):
    store = None       # set by make_server
    api_token = None
    unsub_secret = None
    server_version = "gtm-engine"

    # --- plumbing -------------------------------------------------------
    def _send(self, status, payload, ctype="application/json"):
        data = payload if isinstance(payload, bytes) else (
            payload.encode() if isinstance(payload, str) else json.dumps(payload, default=str).encode())
        self.send_response(status)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        if ctype == "text/html":
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'")
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self):
        if not self.api_token:
            return True
        given = self.headers.get("Authorization", "")
        return hmac.compare_digest(given.encode(), f"Bearer {self.api_token}".encode())

    def _body(self, want_json=True):
        length = self.headers.get("Content-Length")
        if length is None or not length.isdigit():
            raise BadRequest("Content-Length required", HTTPStatus.LENGTH_REQUIRED)
        if int(length) > MAX_BODY:
            raise BadRequest("body too large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        raw = self.rfile.read(int(length))
        if not want_json:
            return raw
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            raise BadRequest("Content-Type must be application/json", HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
        try:
            return json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise BadRequest("invalid JSON")

    def _dispatch(self, method):
        url = urlparse(self.path)
        q = {k: v[-1] for k, v in parse_qs(url.query).items()}
        name = ROUTES.get((method, url.path))
        route = name and getattr(self, name)
        if not route:
            return self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
        if url.path.startswith("/api/") and not self._authorized():
            return self._send(HTTPStatus.UNAUTHORIZED, {"error": "missing or bad bearer token"})
        try:
            route(q)
        except BadRequest as e:
            self._send(e.status, {"error": e.detail})
        except Exception as e:  # never leak a traceback to the client
            print(f"error handling {method.upper()} {url.path}: {e!r}", file=sys.stderr)
            self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal error"})

    def do_GET(self):
        self._dispatch("get")

    def do_POST(self):
        self._dispatch("post")

    def log_message(self, fmt, *args):  # quieter default log, no query strings (tokens live there)
        sys.stderr.write(f"{self.command} {urlparse(self.path).path} {args[1] if len(args) > 1 else ''}\n")

    # --- routes ---------------------------------------------------------
    def get_index(self, q):
        self._send(HTTPStatus.OK, (STATIC / "index.html").read_bytes(), "text/html")

    def get_app_js(self, q):
        self._send(HTTPStatus.OK, (STATIC / "app.js").read_bytes(), "text/javascript")

    def get_api_leads(self, q):
        rows = self.store.leads(q.get("tier"))
        if q.get("owner"):
            rows = [r for r in rows if r["owner"] == q["owner"]]
        limit = q.get("limit", "100")
        if not limit.isdigit():
            raise BadRequest("limit must be a positive integer")
        self._send(HTTPStatus.OK, rows[: min(int(limit), 1000)])

    def get_api_report(self, q):
        rows = self.store.leads()
        funnel = [{"stage": s, "count": n, "conversion": c} for s, n, c in analytics.funnel(rows)]
        self._send(HTTPStatus.OK, {**analytics.summary(rows), "funnel": funnel})

    def get_api_forecast(self, q):
        self._send(HTTPStatus.OK, forecast.forecast(self.store.leads()))

    def get_api_accounts(self, q):
        self._send(HTTPStatus.OK, accounts.rollup(self.store.leads())[:100])

    def post_api_leads(self, q):
        leads, stats = pipeline.process(parse_leads(self._body()), self.store)
        self._send(HTTPStatus.CREATED, {"stats": stats, "leads": [
            {k: getattr(l, k) for k in ("email", "score", "tier", "owner", "email_status", "blocked")}
            for l in leads]})

    def post_api_signals(self, q):
        n = self.store.add_signals(parse_signals(self._body()))
        self._send(HTTPStatus.CREATED, {"inserted": n, "note": "scores pick up signals on the next pipeline run"})

    def post_api_replies(self, q):
        email, text = parse_reply(self._body())
        label, note = replies.apply(self.store, email, text)
        self._send(HTTPStatus.OK, {"email": email, "label": label, "action": note})

    def _check_unsub(self, q):
        email, token = q.get("email", ""), q.get("token", "")
        ok = self.unsub_secret and EMAIL_RE.match(email) and hmac.compare_digest(
            token.encode(), unsub_token(email, self.unsub_secret).encode())
        if not ok:
            raise BadRequest("invalid unsubscribe link", HTTPStatus.FORBIDDEN)
        return email

    def get_unsubscribe(self, q):
        # a GET must not unsubscribe (link scanners prefetch); show a one-button form instead
        email = self._check_unsub(q)
        self._send(HTTPStatus.OK, f"""<!doctype html><title>Unsubscribe</title>
<form method="post"><p>Stop emails to <b>{escape(email)}</b>?</p>
<input type="hidden" name="List-Unsubscribe" value="One-Click"><button>Unsubscribe</button></form>""",
                   "text/html")

    def post_unsubscribe(self, q):
        email = self._check_unsub(q)
        self._body(want_json=False)
        compliance.unsubscribe(self.store, email, "one-click")
        self._send(HTTPStatus.OK, f"<!doctype html><p>{escape(email)} is unsubscribed.</p>", "text/html")


ROUTES = {("get", "/"): "get_index", ("get", "/app.js"): "get_app_js"}
ROUTES.update({(m, path): f"{m}_{path.strip('/').replace('/', '_')}" for m, path in [
    ("get", "/api/leads"), ("get", "/api/report"), ("get", "/api/forecast"), ("get", "/api/accounts"),
    ("post", "/api/leads"), ("post", "/api/signals"), ("post", "/api/replies"),
    ("get", "/unsubscribe"), ("post", "/unsubscribe"),
]})


def make_server(store, host="127.0.0.1", port=8000, env=os.environ):
    handler = type("GTMHandler", (Handler,), {
        "store": store, "api_token": env.get("GTM_API_TOKEN") or None,
        "unsub_secret": env.get("GTM_UNSUB_SECRET") or None})
    return HTTPServer((host, port), handler)


def serve(db, host, port):
    srv = make_server(Store(db), host, port)
    auth = "bearer token required" if srv.RequestHandlerClass.api_token else "NO AUTH (set GTM_API_TOKEN)"
    print(f"gtm web on http://{host}:{srv.server_port}  [{auth}]", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
