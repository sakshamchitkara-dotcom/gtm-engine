"""Funnel + distribution reports off the lead table."""
from collections import Counter

from .store import STAGES

# a lead in "meeting" has also passed "contacted" and "replied"
_REACHED = {s: STAGES[1:i + 1] for i, s in enumerate(STAGES)}
_REACHED["lost"] = ["contacted"]  # lost with no recorded history: it was at least contacted


def _reached(r, peaks):
    return _REACHED[peaks.get(r["email"], "lost") if r["stage"] == "lost" else r["stage"]]


def funnel(rows, peaks=None):
    """peaks: {email: furthest open stage} from Store.peak_stages(), so a lead lost after a
    meeting still counts toward contacted/replied/meeting."""
    reached = Counter()
    for r in rows:
        reached["new"] += 1
        reached.update(_reached(r, peaks or {}))
    out, prev = [], None
    for s in ["new", "contacted", "replied", "meeting", "opportunity", "won"]:
        n = reached[s]
        conv = f"{n / prev:.0%}" if prev else "-"
        out.append((s, n, conv))
        prev = n or None
    return out


def summary(rows):
    return {
        "total": len(rows),
        "by_tier": dict(sorted(Counter(r["tier"] for r in rows).items())),
        "by_owner": dict(Counter(r["owner"] for r in rows).most_common()),
        "avg_score": round(sum(r["score"] for r in rows) / len(rows), 1) if rows else 0,
    }


def render(rows, peaks=None):
    s = summary(rows)
    lines = [f"Leads: {s['total']}   avg score: {s['avg_score']}", "", "Tier mix:"]
    lines += [f"  {t}: {n}" for t, n in s["by_tier"].items()]
    lines += ["", "Owner load:"] + [f"  {o:<18} {n}" for o, n in s["by_owner"].items()]
    lines += ["", f"{'stage':<12}{'count':>6}{'conv':>8}"]
    lines += [f"{st:<12}{n:>6}{c:>8}" for st, n, c in funnel(rows, peaks)]
    return "\n".join(lines)



def cohorts(rows, created, peaks=None, by="both"):
    """Leads grouped by import month (their "created" event, else the row's updated_at),
    source, or both: how many reached contacted and meeting, and won vs lost."""
    groups = {}
    for r in rows:
        month = (created.get(r["email"]) or r.get("updated_at") or "?")[:7]
        source = r.get("source") or "(none)"
        key = {"source": (source,), "month": (month,)}.get(by, (month, source))
        g = groups.setdefault(key, Counter())
        g["leads"] += 1
        g["lost"] += r["stage"] == "lost"
        g.update(_reached(r, peaks or {}))
    return [{"cohort": " / ".join(k), **{c: g[c] for c in ("leads", "contacted", "meeting", "won", "lost")}}
            for k, g in sorted(groups.items())]


def render_cohorts(rows):
    pct = lambda n, d: f"{n / d:.0%}" if d else "-"
    width = max([len(c["cohort"]) for c in rows] + [6]) + 2
    lines = [f"{'cohort':<{width}}{'leads':>6}{'contacted':>10}{'meeting':>9}{'won':>5}{'lost':>5}{'win rate':>9}"]
    lines += [f"{c['cohort']:<{width}}{c['leads']:>6}{pct(c['contacted'], c['leads']):>10}"
              f"{pct(c['meeting'], c['leads']):>9}{c['won']:>5}{c['lost']:>5}{pct(c['won'], c['won'] + c['lost']):>9}"
              for c in rows]
    return "\n".join(lines)
