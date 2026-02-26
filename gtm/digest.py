"""Per-rep daily markdown digest: what to do today and where the pipeline stands."""
from pathlib import Path

from . import forecast

HOT_INTENT = 10


def _cell(v):
    return str(v).replace("|", "\\|").replace("\n", " ")


def _table(header, rows):
    if not rows:
        return "_none_\n"
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def render(store, rep, day, leads=None):
    leads = [r for r in (leads if leads is not None else store.leads()) if r["owner"] == rep]
    by_email = {r["email"]: r for r in leads}
    sent = store.sent_keys()
    # unsent emails carry over; call/LinkedIn tasks aren't tracked, so only show today's
    due = [t for t in store.touches_due(day) if t["email"] in by_email and (t["email"], t["step"]) not in sent
           and (t["channel"] == "email" or t["date"] == day)]
    overdue = sum(1 for t in due if t["date"] < day)
    replied = [r for r in leads if r["stage"] == "replied"]
    hot = sorted((r for r in leads if r.get("intent", 0) >= HOT_INTENT and r["stage"] in forecast.OPEN),
                 key=lambda r: -r["intent"])
    fresh = [r for r in leads if r["stage"] == "new" and r["tier"] in ("A", "B")][:10]
    f = next((o for o in forecast.forecast(leads) if o["owner"] == rep), {"open_acv": 0, "weighted": 0})

    md = [f"# Daily digest: {rep} ({day})", "",
          f"{len(leads)} leads - {len(due)} touches due ({overdue} overdue) - "
          f"open ACV ${f['open_acv']:,} - weighted ${f['weighted']:,}", "",
          "## Touches due", "",
          _table(["date", "channel", "lead", "company", "subject / note"],
                 [(t["date"], t["channel"] + (" (outbox)" if t["channel"] == "email" else ""), t["email"],
                   by_email[t["email"]].get("company", ""), t["subject"] or t["body"]) for t in due]),
          "## Replies waiting on you", "",
          _table(["lead", "company", "score"], [(r["email"], r.get("company", ""), r["score"]) for r in replied]),
          "## Hot intent", "",
          _table(["lead", "company", "intent", "stage"],
                 [(r["email"], r.get("company", ""), r["intent"], r["stage"]) for r in hot]),
          "## Top untouched A/B leads", "",
          _table(["score", "tier", "lead", "title", "company"],
                 [(r["score"], r["tier"], r["email"], r.get("title", ""), r.get("company", "")) for r in fresh])]
    return "\n".join(md)


def write_all(store, day, out_dir):
    """One file per rep that owns leads. Returns the paths written."""
    leads = store.leads()
    reps = sorted({r["owner"] for r in leads} - {"nurture", "unassigned"})
    paths = []
    for rep in reps:
        path = Path(out_dir) / day / f"{rep}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(store, rep, day, leads))
        paths.append(path)
    return paths
