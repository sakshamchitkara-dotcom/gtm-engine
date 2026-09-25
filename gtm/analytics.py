"""Funnel + distribution reports off the lead table."""
from collections import Counter

from .store import STAGES

# a lead in "meeting" has also passed "contacted" and "replied"
_REACHED = {s: STAGES[1:i + 1] for i, s in enumerate(STAGES)}
_REACHED["lost"] = ["contacted"]  # lost with no recorded history: it was at least contacted


def funnel(rows, peaks=None):
    """peaks: {email: furthest open stage} from Store.peak_stages(), so a lead lost after a
    meeting still counts toward contacted/replied/meeting."""
    peaks = peaks or {}
    reached = Counter()
    for r in rows:
        reached["new"] += 1
        stage = peaks.get(r["email"], "lost") if r["stage"] == "lost" else r["stage"]
        for s in _REACHED[stage]:
            reached[s] += 1
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
