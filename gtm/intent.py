"""Buying-intent signals with exponential time decay -> intent points for scoring.

Signals CSV: email,signal,at  (email may be a bare domain for account-level signals
like a G2 visit). A signal is worth WEIGHTS[signal] today and half that after
HALF_LIFE_DAYS.
"""
import csv
from datetime import datetime, timezone

WEIGHTS = {
    "demo_page": 20, "pricing_page": 15, "g2_visit": 10, "webinar_attended": 8,
    "case_study": 6, "docs": 5, "email_click": 5, "email_open": 1, "blog": 2,
}
HALF_LIFE_DAYS = 7
CAP = 30


def parse_at(value):
    """ISO date or datetime -> naive UTC datetime."""
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if dt.tzinfo:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def clean(target, signal, at):
    """Validate one signal. Returns (target, signal, iso_at) or raises ValueError."""
    target, signal = (target or "").strip().lower(), (signal or "").strip().lower()
    if not target or " " in target or "." not in target:
        raise ValueError(f"bad email/domain: {target!r}")
    if signal not in WEIGHTS:
        raise ValueError(f"unknown signal: {signal!r}")
    return target, signal, parse_at(at).isoformat(timespec="seconds")


def load_csv(path):
    """Returns (signals, n_skipped)."""
    out, skipped = [], 0
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                out.append(clean(row.get("email"), row.get("signal"), row.get("at") or ""))
            except ValueError:
                skipped += 1
    return out, skipped


def points(signals, asof=None):
    """{email_or_domain: decayed points} from (target, signal, iso_at) rows."""
    asof = parse_at(asof.isoformat()) if asof else datetime.now(timezone.utc).replace(tzinfo=None)
    pts = {}
    for target, signal, at in signals:
        age = max(0.0, (asof - parse_at(at)).total_seconds() / 86400)
        pts[target] = pts.get(target, 0) + WEIGHTS[signal] * 0.5 ** (age / HALF_LIFE_DAYS)
    return pts


def for_lead(lead, pts):
    domain = lead.email.rsplit("@", 1)[-1]
    return min(CAP, round(pts.get(lead.email, 0) + pts.get(domain, 0)))
