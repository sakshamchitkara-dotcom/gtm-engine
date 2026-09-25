"""Slack alert for new tier-A leads, via an incoming webhook. Dry run (print) unless --send.

Env: SLACK_WEBHOOK_URL. Each lead is announced once (notified table); dry runs record nothing.
"""
import json
from urllib.request import Request, urlopen


def _esc(v):
    """Slack mrkdwn: lead data is untrusted, so no <!channel>, <url|spoofed links> or formatting tricks."""
    return str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def pending(store, limit=20):
    done = store.notified()
    return [r for r in store.leads("A") if not r.get("blocked") and r["stage"] == "new"
            and r["email"] not in done][:limit]


def payload(leads):
    lines = [f"*{len(leads)} new tier-A lead{'s' * (len(leads) != 1)}*"]
    for r in leads:
        who = " ".join(filter(None, [r.get("first_name"), r.get("last_name")])) or r["email"]
        lines.append(f"- *{_esc(who)}*, {_esc(r.get('title') or '?')} at {_esc(r.get('company') or r['domain'])}"
                     f" - score {r['score']}, intent {r.get('intent', 0)}, owner {_esc(r['owner'])}"
                     f" ({_esc(r['email'])})")
    return {"text": "\n".join(lines)}


def post(url, body, timeout=10):
    req = Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=timeout) as r:  # non-2xx raises HTTPError
        return r.status


def run(store, url=None, limit=20):
    """Returns (payload or None, sent). Sends and records only when url is given."""
    leads = pending(store, limit)
    if not leads:
        return None, False
    body = payload(leads)
    if url:
        post(url, body)
        store.mark_notified([r["email"] for r in leads])
    return body, bool(url)
