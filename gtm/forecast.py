"""Weighted pipeline: stage win-probability x expected ACV (by company size band), per owner."""
from collections import defaultdict

STAGE_PROB = {"new": 0.02, "contacted": 0.04, "replied": 0.10, "meeting": 0.20,
              "opportunity": 0.40, "won": 1.0, "lost": 0.0}
ACV = {"micro": 3_000, "small": 8_000, "mid": 20_000, "upper_mid": 45_000,
       "enterprise": 120_000, "unknown": 5_000}
OPEN = {"new", "contacted", "replied", "meeting", "opportunity"}


def forecast(rows):
    """Returns list of per-owner dicts sorted by weighted pipeline, plus a TOTAL row."""
    by = defaultdict(lambda: {"leads": 0, "open_acv": 0, "weighted": 0.0, "won": 0})
    for r in rows:
        acv = ACV.get(r.get("size_band") or "unknown", ACV["unknown"])
        for key in (r["owner"], "TOTAL"):
            o = by[key]
            o["leads"] += 1
            if r["stage"] in OPEN:
                o["open_acv"] += acv
                o["weighted"] += acv * STAGE_PROB[r["stage"]]
            elif r["stage"] == "won":
                o["won"] += acv
    out = [{"owner": k, **v, "weighted": round(v["weighted"])} for k, v in by.items()]
    return sorted(out, key=lambda o: (o["owner"] == "TOTAL", -o["weighted"]))


def render(rows):
    lines = [f"{'owner':<18}{'leads':>6}{'open ACV':>12}{'weighted':>11}{'won':>10}"]
    for o in forecast(rows):
        lines.append(f"{o['owner']:<18}{o['leads']:>6}{o['open_acv']:>12,}{o['weighted']:>11,}{o['won']:>10,}")
    return "\n".join(lines)
