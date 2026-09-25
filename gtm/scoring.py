"""ICP fit scoring. Weights live in config/icp.json so RevOps can tune without code."""
import json
from pathlib import Path

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "icp.json"


def load_config(path=None):
    with open(path or DEFAULT_CONFIG) as f:
        return json.load(f)


def score(lead, cfg):
    points, reasons = 0, []

    def add(n, why):
        nonlocal points
        if n:
            points += n
            reasons.append(f"{n:+d} {why}")

    add(cfg["industries"].get(lead.industry, 0), f"industry={lead.industry}")
    add(cfg["size_bands"].get(lead.size_band, 0), f"size={lead.size_band}")
    add(cfg["seniority"].get(lead.seniority, 0), f"seniority={lead.seniority}")
    add(cfg["countries"].get(lead.country, 0), f"country={lead.country}")
    add(cfg["sources"].get(lead.source, 0), f"source={lead.source}")
    title = lead.title.lower()
    # only the best keyword counts, so "Sales & Revenue Ops" doesn't stack
    kw = max((w for k, w in cfg["title_keywords"].items() if k in title), default=0)
    add(kw, "title keyword")
    if lead.is_free_email:
        add(cfg["penalties"]["free_email"], "free email domain")
    if lead.email_status == "risky":
        add(cfg["penalties"].get("risky_email", 0), "risky email")

    lead.score = max(0, min(100, points))
    lead.reasons = reasons
    lead.tier = next((t for t, cut in sorted(cfg["tiers"].items(), key=lambda x: -x[1])
                      if lead.score >= cut), "D")
    return lead
