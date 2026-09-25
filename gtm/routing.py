"""Assign leads to reps: territory first, then round-robin within the pool.

Tier A enterprise goes to the AE pool; everything else to SDRs. Team and
per-rep capacity live in gtm/config/team.json ($GTM_CONFIG_DIR overrides). A rep at capacity is skipped;
when a whole pool is full the lead is parked as "unassigned".

Accounts are sticky: once a company domain has an owner in this run, every
other routable lead at that domain goes to the same rep (even past cap).
The first lead routed decides, so pipeline.process routes in score order: the
tier-A exec, not whichever contact came first in the CSV, picks AE vs SDR.
"""
import json

from . import config_path

ROLES = ("ae", "sdr")

# used when team.json has no "territories"; "default_region" catches unlisted countries
REGIONS = {
    "NA": {"US", "CA", "MX"},
    "EMEA": {"GB", "DE", "FR", "NL", "ES", "IT", "SE", "IE", "AE", "ZA"},
    "APAC": {"IN", "AU", "SG", "JP", "NZ"},
}


def load_team(path=None):
    with open(path or config_path("team.json")) as f:
        return json.load(f)


def cap_for(team, rep, key="capacity"):
    caps = team.get(key, {})
    return caps.get(rep, caps.get("default"))


def region_of(country, territories=None, default="NA"):
    return next((r for r, cs in (territories or REGIONS).items() if country in cs), default)


class Router:
    def __init__(self, team=None):
        self.team = team or load_team()
        self._pools = {(role, reg): list(reps) for role in ROLES
                       for reg, reps in self.team.get(role, {}).items()}
        self._next = dict.fromkeys(self._pools, 0)
        self.load = {}
        self.accounts = {}  # domain -> owner
        self.known = {}     # email -> owner from earlier runs

    def seed(self, rows):
        """Owners already in the store (Store.leads(), best first): a lead keeps its rep across
        re-runs and its account stays with that rep, as long as the rep is still on the team."""
        reps = {rep for pool in self._pools.values() for rep in pool}
        for r in rows:
            if r["owner"] in reps:
                self.known[r["email"]] = r["owner"]
                if not r.get("is_free_email") and r.get("domain"):
                    self.accounts.setdefault(r["domain"], r["owner"])

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
        domain = "" if lead.is_free_email else lead.domain
        if lead.email in self.known or domain in self.accounts:
            lead.owner = self.known.get(lead.email) or self.accounts[domain]
            self.load[lead.owner] = self.load.get(lead.owner, 0) + 1
            return lead
        role = "ae" if lead.tier == "A" and lead.size_band in ("upper_mid", "enterprise") else "sdr"
        lead.owner = self._pick((role, region_of(lead.country, self.team.get("territories"),
                                                      self.team.get("default_region", "NA"))))
        if domain and lead.owner != "unassigned":
            self.accounts[domain] = lead.owner
        return lead
