"""Assign leads to reps: territory first, then round-robin within the pool.

Tier A enterprise goes to the AE pool; everything else to SDRs.
"""
from itertools import cycle

DEFAULT_TEAM = {
    "ae": {"NA": ["maya@acme.io", "jordan@acme.io"], "EMEA": ["lena@acme.io"], "APAC": ["arjun@acme.io"]},
    "sdr": {"NA": ["sam@acme.io", "riley@acme.io", "alex@acme.io"], "EMEA": ["noah@acme.io", "ella@acme.io"],
            "APAC": ["kai@acme.io"]},
}

REGIONS = {
    "NA": {"US", "CA", "MX"},
    "EMEA": {"GB", "DE", "FR", "NL", "ES", "IT", "SE", "IE", "AE", "ZA"},
    "APAC": {"IN", "AU", "SG", "JP", "NZ"},
}


def region_of(country):
    return next((r for r, cs in REGIONS.items() if country in cs), "NA")


class Router:
    def __init__(self, team=None):
        team = team or DEFAULT_TEAM
        self._pools = {(role, reg): cycle(reps) for role, regs in team.items() for reg, reps in regs.items()}

    def assign(self, lead):
        if lead.tier == "D":
            lead.owner = "nurture"
            return lead
        role = "ae" if lead.tier == "A" and lead.size_band in ("upper_mid", "enterprise") else "sdr"
        lead.owner = next(self._pools[(role, region_of(lead.country))])
        return lead
