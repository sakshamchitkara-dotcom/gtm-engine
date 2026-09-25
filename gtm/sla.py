"""Speed-to-lead: hours from a lead's first import to its first touch, against per-tier SLAs.

A lead's clock starts at its "created" event (written by Store.upsert_leads on first import)
and stops at its first stage event past "new" (outbox sends and `gtm stage` both write one).
SLA hours per tier come from team.json "sla_hours"; tiers without one (D) are not tracked.
ponytail: wall-clock hours, no business hours or rep time zones.
"""
from datetime import datetime, timezone
from statistics import median

DEFAULT_SLA = {"A": 4, "B": 24, "C": 72}
TOUCH = ("contacted", "replied", "meeting", "opportunity", "won")


def _ts(s):
    return datetime.fromisoformat(s).replace(tzinfo=None)


def report(store, team, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo:  # event times are naive UTC (SQLite CURRENT_TIMESTAMP)
        now = now.astimezone(timezone.utc).replace(tzinfo=None)
    sla = team.get("sla_hours", DEFAULT_SLA)
    created, touched = store.first_event(("created",)), store.first_event(TOUCH)
    owners, breaches, untracked = {}, [], 0
    for r in store.leads():
        if r["tier"] not in sla or r["owner"] in ("nurture", "unassigned") or r.get("blocked"):
            continue
        if r["email"] not in created:
            untracked += 1  # imported before SLA tracking existed
            continue
        start, limit = _ts(created[r["email"]]), sla[r["tier"]]
        o = owners.setdefault(r["owner"], {"owner": r["owner"], "leads": 0, "touched": 0, "hours": [],
                                           "within": 0, "open_breached": 0})
        o["leads"] += 1
        if r["email"] in touched:
            h = (_ts(touched[r["email"]]) - start).total_seconds() / 3600
            o["touched"] += 1
            o["hours"].append(h)
            o["within"] += h <= limit
        elif r["stage"] == "new" and (now - start).total_seconds() / 3600 > limit:
            o["open_breached"] += 1
            breaches.append({"email": r["email"], "owner": r["owner"], "tier": r["tier"],
                             "age_h": round((now - start).total_seconds() / 3600, 1), "sla_h": limit})
    rows = []
    for o in sorted(owners.values(), key=lambda o: (-o["open_breached"], o["owner"])):
        hours = o.pop("hours")
        o["median_h"] = round(median(hours), 1) if hours else None
        o["within_pct"] = round(100 * o["within"] / o["touched"]) if o["touched"] else None
        rows.append(o)
    return {"sla_hours": sla, "owners": rows, "breaches": sorted(breaches, key=lambda b: -b["age_h"]),
            "untracked": untracked}


def render(rep, limit=10):
    lines = ["SLA hours: " + ", ".join(f"{t}={h}" for t, h in rep["sla_hours"].items()), "",
             f"{'owner':<18}{'leads':>6}{'touched':>8}{'median h':>9}{'in SLA':>7}{'breached':>9}"]
    for o in rep["owners"]:
        med = "-" if o["median_h"] is None else f"{o['median_h']:.1f}"
        pct = "-" if o["within_pct"] is None else f"{o['within_pct']}%"
        lines.append(f"{o['owner']:<18}{o['leads']:>6}{o['touched']:>8}{med:>9}{pct:>7}{o['open_breached']:>9}")
    if rep["breaches"]:
        lines += ["", f"untouched past SLA (oldest {min(limit, len(rep['breaches']))} of {len(rep['breaches'])}):"]
        lines += [f"  {b['age_h']:>6}h > {b['sla_h']}h  {b['tier']}  {b['email']:<32} {b['owner']}"
                  for b in rep["breaches"][:limit]]
    if rep["untracked"]:
        lines.append(f"\n{rep['untracked']} leads predate SLA tracking (no created event) and are skipped")
    return "\n".join(lines)
