"""Deterministic A/B tests on the opener subject line + a two-proportion z-test.

Assignment is a hash of (experiment, email), so it is stable across re-runs and
machines with nothing stored.
"""
import hashlib
import math

EXPERIMENT = "opener-subject-v1"
ARMS = ("control", "challenger")
# tier -> subject per arm; control matches the cadence's original subject
SUBJECTS = {
    "A": ("$company + pipeline visibility", "$first_name, question about $company's lead routing"),
    "B": ("idea for $company", "$company's speed-to-lead"),
}
REPLIED = {"replied", "meeting", "opportunity", "won"}


def arm(email, experiment=EXPERIMENT):
    h = int(hashlib.sha256(f"{experiment}:{email.lower()}".encode()).hexdigest(), 16)
    return ARMS[h % len(ARMS)]


def subject(lead):
    """Opener subject template for this lead, or None if its tier isn't in the test."""
    pair = SUBJECTS.get(lead.tier)
    return pair[ARMS.index(arm(lead.email))] if pair else None


def z_test(s1, n1, s2, n2):
    """Two-sided two-proportion z-test. Returns (z, p_value)."""
    if not (n1 and n2):
        return 0.0, 1.0
    pooled = (s1 + s2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0:
        return 0.0, 1.0
    z = (s1 / n1 - s2 / n2) / se
    return z, math.erfc(abs(z) / math.sqrt(2))


def results(rows):
    """Exposed = contacted (stage moved past new) in a tested tier; success = replied or later."""
    counts = {a: [0, 0] for a in ARMS}  # arm -> [successes, exposed]
    for r in rows:
        if r["tier"] in SUBJECTS and r["stage"] != "new":
            c = counts[arm(r["email"])]
            c[1] += 1
            c[0] += r["stage"] in REPLIED
    (s1, n1), (s2, n2) = counts["control"], counts["challenger"]
    z, p = z_test(s2, n2, s1, n1)
    return {"experiment": EXPERIMENT, "arms": counts, "z": round(z, 3), "p": round(p, 4)}


def render(res):
    lines = [f"experiment {res['experiment']}", f"{'arm':<12}{'sent':>6}{'replied':>9}{'rate':>8}"]
    for a, (s, n) in res["arms"].items():
        lines.append(f"{a:<12}{n:>6}{s:>9}{(s / n if n else 0):>8.1%}")
    verdict = "significant at 95%" if res["p"] < 0.05 else "not significant"
    lines.append(f"challenger vs control: z={res['z']} p={res['p']} ({verdict})")
    return "\n".join(lines)
