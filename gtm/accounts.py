"""Roll leads up into accounts by domain: account score + buying-committee coverage."""
from collections import defaultdict

# who needs to be in the room for a typical RevOps tooling deal
COMMITTEE = {
    "economic_buyer": {"c_level", "vp"},
    "champion": {"director", "manager"},
    "user": {"ic"},
}
OPEN = {"new", "contacted", "replied", "meeting", "opportunity"}


def role_of(seniority):
    return next((r for r, levels in COMMITTEE.items() if seniority in levels), None)


def rollup(rows):
    """rows: merged lead records (Store.leads()). Free-email leads have no account."""
    by_domain = defaultdict(list)
    for r in rows:
        if not r.get("is_free_email") and r.get("domain"):
            by_domain[r["domain"]].append(r)
    out = []
    for domain, people in by_domain.items():
        roles = {role_of(p.get("seniority")) for p in people} - {None}
        coverage = len(roles) / len(COMMITTEE)
        top = max(p["score"] for p in people)
        # best contact carries the account; each extra committee role adds 5, intent adds up to 10
        intent = min(10, sum(p.get("intent", 0) for p in people) // 3)
        out.append({
            "domain": domain,
            "company": next((p["company"] for p in people if p.get("company")), domain),
            "leads": len(people),
            "score": min(100, top + 5 * max(0, len(roles) - 1) + intent),
            "coverage": round(coverage, 2),
            "missing": sorted(set(COMMITTEE) - roles),
            "owner": max(people, key=lambda p: p["score"])["owner"],
            "open": sum(1 for p in people if p["stage"] in OPEN),
        })
    return sorted(out, key=lambda a: (-a["score"], a["domain"]))


def render(accounts, limit=20):
    lines = [f"{'score':>5}  {'cov':>4}  {'leads':>5}  {'domain':<24} {'owner':<18} missing"]
    for a in accounts[:limit]:
        lines.append(f"{a['score']:>5}  {a['coverage']:>4.0%}  {a['leads']:>5}  {a['domain']:<24} "
                     f"{a['owner']:<18} {', '.join(a['missing']) or '-'}")
    return "\n".join(lines)
