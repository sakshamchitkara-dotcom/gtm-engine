"""Assign leads to reps: territory first, then round-robin within the pool.

Tier A enterprise goes to the AE pool; everything else to SDRs. Team and
per-rep capacity live in config/team.json. A rep at capacity is skipped;
when a whole pool is full the lead is parked as "unassigned".
"""
import json
from pathlib import Path

TEAM_FILE = Path(__file__).resolve().parent.parent / "config" / "team.json"
ROLES = ("ae", "sdr")

REGIONS = {
    "NA": {"US", "CA", "MX"},
    "EMEA": {"GB", "DE", "FR", "NL", "ES", "IT", "SE", "IE", "AE", "ZA"},
    "APAC": {"IN", "AU", "SG", "JP", "NZ"},
}


def load_team(path=None):
    with open(path or TEAM_FILE) as f:
        return json.load(f)


def cap_for(team, rep, key="capacity"):
    caps = team.get(key, {})
    return caps.get(rep, caps.get("default"))


def region_of(country):
    return next((r for r, cs in REGIONS.items() if country in cs), "NA")


class Router:
    def __init__(self, team=None):
        self.team = team or load_team()
        self._pools = {(role, reg): list(reps) for role in ROLES
                       for reg, reps in self.team.get(role, {}).items()}
        self._next = dict.fromkeys(self._pools, 0)
        self.load = {}

    def _pick(self, key):
        pool = self._pools.get(key) or []
        for _ in range(len(pool)):
            rep = pool[self._next[key] % len(pool)]
            self._next[key] += 1
            cap = cap_for(self.team, rep)
            if cap is None or self.load.get(rep, 0) < cap:
                self.load[rep] = self.load.get(rep, 0) + 1
                return rep
        return "unassigned"

    def assign(self, lead):
        if lead.tier == "D":
            lead.owner = "nurture"
            return lead
        role = "ae" if lead.tier == "A" and lead.size_band in ("upper_mid", "enterprise") else "sdr"
        lead.owner = self._pick((role, region_of(lead.country)))
        return lead
