"""Calibrate icp.json against closed won/lost history with a small logistic regression.

Features are exactly what score() pays points for: one-hot per icp.json key (anything
else is the zero-point baseline), the best title keyword, free/risky email. Coefficients
are log-odds of winning; suggested points rescale them so the largest one matches the
largest current weight. Then "base" (an intercept score() adds) keeps the average score
where it was, and tier cutoffs move so every tier keeps its current headcount: reps get
the same volume, ordered by what actually wins.

ponytail: batch gradient descent on sparse dicts, in-sample AUC only. Fine up to tens of
thousands of closed leads; hold out a slice before trusting small gains.
"""
import copy
import json
import math

CATS = {"industries": "industry", "size_bands": "size_band", "seniority": "seniority",
        "countries": "country", "sources": "source"}
CLOSED = {"won": 1, "lost": 0}


def features(r, cfg):
    f = {}
    for cat, attr in CATS.items():
        if r.get(attr) in cfg[cat]:
            f[f"{cat}:{r[attr]}"] = 1.0
    title = (r.get("title") or "").lower()
    hits = [k for k in cfg["title_keywords"] if k in title]
    if hits:  # score() only counts the best keyword
        f["title_keywords:" + max(hits, key=cfg["title_keywords"].get)] = 1.0
    if r.get("is_free_email"):
        f["penalties:free_email"] = 1.0
    if r.get("email_status") == "risky":
        f["penalties:risky_email"] = 1.0
    return f


def fit(X, y, l2=1.0, iters=3000, lr=0.5):
    """L2-regularized logistic regression. X: list of {feature: value}. Returns (weights, bias)."""
    names = sorted({k for x in X for k in x})
    w, b, n = dict.fromkeys(names, 0.0), 0.0, len(X)
    for _ in range(iters):
        gw, gb = dict.fromkeys(names, 0.0), 0.0
        for x, t in zip(X, y):
            z = b + sum(w[k] * v for k, v in x.items())
            err = 1 / (1 + math.exp(-max(-35.0, min(35.0, z)))) - t
            gb += err
            for k, v in x.items():
                gw[k] += err * v
        b -= lr * gb / n
        for k in names:
            w[k] -= lr * (gw[k] + l2 * w[k]) / n
    return w, b


def auc(scores, y):
    """Probability a random won lead outscores a random lost one (ties count half)."""
    pos = [s for s, t in zip(scores, y) if t]
    neg = [s for s, t in zip(scores, y) if not t]
    if not pos or not neg:
        return None
    wins = sum((p > q) + 0.5 * (p == q) for p in pos for q in neg)
    return wins / (len(pos) * len(neg))


def calibrate(rows, cfg, min_support=5):
    closed = [r for r in rows if r["stage"] in CLOSED]
    y = [CLOSED[r["stage"]] for r in closed]
    X = [features(r, cfg) for r in closed]
    if len(set(y)) < 2:
        raise ValueError(f"need both won and lost leads to calibrate (have {len(closed)} closed)")
    w, b = fit(X, y)
    support = {k: sum(k in x for x in X) for k in w}
    won = {k: sum(t for x, t in zip(X, y) if k in x) for k in w}
    current = {f"{c}:{k}": v for c in list(CATS) + ["title_keywords", "penalties"] for k, v in cfg[c].items()}
    fitted = [k for k in w if support[k] >= min_support]
    scale = (max(abs(current[k]) for k in fitted) / max(abs(w[k]) for k in fitted)
             if fitted and any(w[k] for k in fitted) else 0)
    table = sorted(({"feature": k, "n": support[k], "won": won[k], "coef": round(w[k], 3),
                     "current": current.get(k, 0),
                     "suggested": round(w[k] * scale) if k in fitted else current.get(k, 0)}
                    for k in w), key=lambda t: -t["coef"])
    new_cfg = copy.deepcopy(cfg)
    for t in table:
        cat, key = t["feature"].split(":", 1)
        new_cfg[cat][key] = t["suggested"]
    _rebase(rows, cfg, new_cfg)
    tiers = {}
    for r, t in zip(closed, y):
        tiers.setdefault(r["tier"], [0, 0])
        tiers[r["tier"]][0] += t
        tiers[r["tier"]][1] += 1
    model = [b + sum(w[k] * v for k, v in x.items()) for x in X]
    return {"closed": len(closed), "won": sum(y), "tiers": dict(sorted(tiers.items())),
            "auc_current": auc([r["score"] for r in closed], y), "auc_model": auc(model, y),
            "min_support": min_support, "table": table, "config": new_cfg}


def _points(r, cfg):
    return sum(cfg[c][k] for c, k in (f.split(":", 1) for f in features(r, cfg))) + r.get("intent", 0)


def _rebase(rows, cfg, new_cfg):
    """Set base so the mean score is unchanged, then pick cutoffs that keep each tier's headcount."""
    if not rows:
        return
    raw = [_points(r, new_cfg) for r in rows]
    new_cfg["base"] = round(sum(r["score"] for r in rows) / len(rows) - sum(raw) / len(raw))
    new = sorted((max(0, min(100, p + new_cfg["base"])) for p in raw), reverse=True)
    above = 0
    for t in sorted(cfg["tiers"], key=lambda t: -cfg["tiers"][t]):
        above += sum(r["tier"] == t for r in rows)
        new_cfg["tiers"][t] = new[above - 1] if above else 101


def render(res):
    lines = [f"closed leads: {res['closed']}  won: {res['won']} ({res['won'] / res['closed']:.0%})",
             f"AUC current score: {res['auc_current']:.3f}   calibrated model: {res['auc_model']:.3f}"
             "  (in-sample)", "", "win rate by current tier:"]
    lines += [f"  {t}: {w}/{n} = {w / n:.0%}" for t, (w, n) in res["tiers"].items()]
    lines += ["", f"{'feature':<32}{'n':>5}{'won':>5}{'coef':>8}{'now':>6}{'new':>6}"]
    c = res["config"]
    tail = [f"", f"base {c['base']:+d}; tier cutoffs " + ", ".join(f"{t}>={v}" for t, v in c["tiers"].items())]
    for t in res["table"]:
        flag = "" if t["n"] >= res["min_support"] else "  (too few, kept)"
        lines.append(f"{t['feature']:<32}{t['n']:>5}{t['won']:>5}{t['coef']:>8.2f}{t['current']:>6}"
                     f"{t['suggested']:>6}{flag}")
    return "\n".join(lines + tail)


def write(res, path):
    with open(path, "w") as f:
        json.dump(res["config"], f, indent=2)
        f.write("\n")
