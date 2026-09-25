"""Send due email touches over SMTP, or write .eml files with --dry-run.

Env: SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD, SMTP_STARTTLS (1).
Unsubscribe: GTM_UNSUB_MAILTO (mailto target) and, for RFC 8058 one-click,
GTM_BASE_URL + GTM_UNSUB_SECRET (the web server's POST /unsubscribe).
"""
import hashlib
import hmac
import os
import re
import smtplib
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from urllib.parse import urlencode

from . import compliance
from .routing import cap_for
from .store import SENDABLE_STAGES



def _safe(name):
    """Emails may legally contain '/'; never let one become a path segment."""
    return re.sub(r"[^\w@.+-]", "_", name)


def unsub_token(email, secret):
    return hmac.new(secret.encode(), email.lower().encode(), hashlib.sha256).hexdigest()[:32]


def unsub_url(email, env=os.environ):
    base, secret = env.get("GTM_BASE_URL"), env.get("GTM_UNSUB_SECRET")
    if not (base and secret):
        return None
    return f"{base.rstrip('/')}/unsubscribe?" + urlencode({"email": email, "token": unsub_token(email, secret)})


def build_message(touch, owner, env=os.environ):
    email = touch["email"]
    mailto = env.get("GTM_UNSUB_MAILTO", "unsubscribe@acme.io")
    url = unsub_url(email, env)
    msg = EmailMessage()
    msg["From"] = owner
    msg["To"] = email
    msg["Subject"] = touch["subject"]
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=owner.rsplit("@", 1)[-1])
    links = [f"<mailto:{mailto}?subject=unsubscribe%20{email}>"] + ([f"<{url}>"] if url else [])
    msg["List-Unsubscribe"] = ", ".join(links)
    if url:
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    footer = f"\n\n--\nNot relevant? Reply \"unsubscribe\"{' or visit ' + url if url else ''} and I won't email again."
    msg.set_content(touch["body"] + footer)
    return msg


class SMTPTransport:
    def __init__(self, env=os.environ):
        self.env, self.conn = env, None

    def send_message(self, msg):
        if self.conn is None:
            e = self.env
            if not e.get("SMTP_HOST"):
                raise RuntimeError("SMTP_HOST not set (use --dry-run to write .eml files instead)")
            self.conn = smtplib.SMTP(e["SMTP_HOST"], int(e.get("SMTP_PORT", 587)), timeout=30)
            if e.get("SMTP_STARTTLS", "1") != "0":
                self.conn.starttls()
            if e.get("SMTP_USER"):
                self.conn.login(e["SMTP_USER"], e.get("SMTP_PASSWORD", ""))
        self.conn.send_message(msg)

    def close(self):
        if self.conn:
            self.conn.quit()


def send_due(store, on_date, team, out_dir=None, transport=None):
    """Sends (or with out_dir, writes) every due email touch that passes the checks.

    Dry runs touch nothing in the database. Returns counts per outcome.
    """
    dry = out_dir is not None
    suppressed, sent = store.suppressed(), store.sent_keys()
    stats = {"sent": 0, "skipped_sent": 0, "skipped_contact": 0, "capped": 0, "refused": 0}
    used = {}
    transport = None if dry else (transport or SMTPTransport())
    try:
        for t in store.touches_due(on_date):
            if t["channel"] != "email":
                continue
            if (t["email"], t["step"]) in sent:
                stats["skipped_sent"] += 1
                continue
            lead = store.lead(t["email"])
            if (not lead or lead.get("blocked") or lead["stage"] not in SENDABLE_STAGES
                    or compliance.is_suppressed(t["email"], suppressed)):
                stats["skipped_contact"] += 1
                continue
            owner = lead["owner"]
            if owner not in used:
                used[owner] = store.sends_on(on_date, owner)
            cap = cap_for(team, owner, "daily_send_cap")
            if cap is not None and used[owner] >= cap:
                stats["capped"] += 1  # stays due; goes out on the next run
                continue
            msg = build_message(t, owner)
            if dry:
                path = Path(out_dir) / on_date / _safe(owner) / _safe(f"{t['email']}-{t['step']}.eml")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(bytes(msg))
            else:
                try:
                    transport.send_message(msg)
                except smtplib.SMTPRecipientsRefused:
                    stats["refused"] += 1  # bad address: skip it, keep the run going
                    continue
                store.record_send(t["email"], t["step"], owner, on_date)
                if lead["stage"] == "new":
                    store.set_stage(t["email"], "contacted")
                    lead["stage"] = "contacted"
            used[owner] += 1
            stats["sent"] += 1
    finally:
        if hasattr(transport, "close"):
            transport.close()
    return stats
