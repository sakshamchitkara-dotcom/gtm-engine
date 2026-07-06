#!/usr/bin/env python3
"""Seeded fake GTM data: ~500 messy leads + intent signals, for demos and CI smoke runs.

    python3 scripts/gen_leads.py --out data/generated --seed 7 --n 500 --asof 2026-09-25

Also writes outcomes.csv: closed won/lost for ~40% of leads, drawn from a hidden
model (OUTCOME_WEIGHTS) that deliberately disagrees with config/icp.json in places,
so `gtm calibrate` has something real to find.

The mess is deliberate: duplicate rows, the same person under two emails, company
name variants (Inc/LLC/typos), typo/disposable/role/invalid emails, and EU leads
from purchased lists (GDPR-blocked).
"""
import argparse
import csv
import math
import random
from datetime import date, datetime, time, timedelta
from pathlib import Path

FIRST = "ana ben chen dana eli farah gus hana ivan jade kofi lena mo nia omar priya quinn raj sara tom uma vik wen yara zoe".split()
LAST = "shah baker lima chen moreau ng ali roy patel kim novak silva okafor weber rossi tanaka singh berg costa diaz".split()
PRE = "north ledger shop medi quant tiny cloud bright stack data flow pipe signal core peak orbit loop grid".split()
POST = "wind ly wave base pay apps cart path forge hub stream line works labs ops ware scale".split()
TLD = [".io", ".com", ".co", ".ai", ".dev"]
INDUSTRIES = ["SaaS"] * 4 + ["Fintech"] * 2 + ["Software"] * 2 + ["Ecommerce", "Healthcare", "Education", "Retail"]
COUNTRIES = ["US"] * 8 + ["CA", "GB", "GB", "DE", "DE", "FR", "NL", "ES", "IN", "AU", "SG", "JP", "BR"]
SOURCES = ["demo_request", "webinar", "webinar", "content", "content", "list", "list", "list"]
TITLES = ["VP of Revenue Operations", "Head of Sales", "Chief Revenue Officer", "Director of Sales",
          "RevOps Lead", "Growth Marketing Manager", "Sales Operations Manager", "CEO", "Founder",
          "Account Executive", "SDR", "Marketing Coordinator", "Software Engineer", "Director of Marketing",
          "VP Growth", "Head of RevOps", "CTO", "Data Analyst"]
SUFFIX_VARIANTS = ["", "", "", " Inc", ", Inc.", " LLC", " Ltd", " GmbH"]
SIGNALS = {"pricing_page": 3, "demo_page": 1, "docs": 3, "email_click": 4, "email_open": 5,
           "g2_visit": 1, "blog": 3, "case_study": 1, "webinar_attended": 1}
# hidden truth for outcomes: log-odds of winning a closed deal
OUTCOME_WEIGHTS = {"base": -1.6, "fintech": 1.4, "healthcare": 1.0, "demo_request": 1.2, "webinar": 0.5,
                   "exec": 0.9, "mid_market": 0.7, "enterprise": -0.6, "free_email": -1.5}
EXEC_WORDS = ("vp", "chief", "head", "ceo", "cro", "cto", "founder")
HEADER = ["Email", "First Name", "Last Name", "Job Title", "Company Name", "# Employees",
          "Industry", "Country", "Lead Source"]


def companies(rng, n):
    n = min(n, len(PRE) * len(POST))  # only this many unique names exist; asking for more never ends
    seen, out = set(), []
    while len(out) < n:
        a, b = rng.choice(PRE), rng.choice(POST)
        if a + b in seen:
            continue
        seen.add(a + b)
        out.append({"name": (a + b).title(), "domain": a + b + rng.choice(TLD),
                    "employees": rng.choice([rng.randint(2, 10), rng.randint(11, 50), rng.randint(51, 200),
                                             rng.randint(201, 1000), rng.randint(1001, 20000)]),
                    "industry": rng.choice(INDUSTRIES), "country": rng.choice(COUNTRIES)})
    return out


def company_label(rng, name):
    if rng.random() < 0.05:  # a typo'd variant, e.g. "Nortwind"
        i = rng.randrange(1, len(name) - 1)
        name = name[:i] + name[i + 1:]
    return name + rng.choice(SUFFIX_VARIANTS)


def email_for(rng, first, last, domain):
    r = rng.random()
    if r < 0.02:
        return f"{first}.{last}@{domain}".replace("@", " at ")               # invalid syntax
    if r < 0.04:
        return f"{first}.{last}@" + rng.choice(["gmial.com", "gamil.com", "hotmial.com", "yaho.com"])
    if r < 0.05:
        return f"{first}{last}@" + rng.choice(["mailinator.com", "yopmail.com"])
    if r < 0.08:
        return rng.choice(["info", "sales", "hello", "contact"]) + "@" + domain
    if r < 0.15:
        return f"{first}.{last}{rng.randint(1, 99)}@" + rng.choice(["gmail.com", "outlook.com", "yahoo.com"])
    return rng.choice([f"{first}.{last}", f"{first}", f"{first[0]}{last}"]) + "@" + domain


def generate(n=500, seed=7, asof=None):
    rng = random.Random(seed)
    asof = asof or date.today()
    accts = companies(rng, max(10, n // 3))
    rows = []
    while len(rows) < n:
        c = rng.choice(accts)
        first, last = rng.choice(FIRST), rng.choice(LAST)
        row = [email_for(rng, first, last, c["domain"]), first, last, rng.choice(TITLES),
               company_label(rng, c["name"]), c["employees"], c["industry"], c["country"], rng.choice(SOURCES)]
        rows.append(row)
        roll = rng.random()
        if roll < 0.03:
            rows.append(list(row))                                          # exact duplicate row
        elif roll < 0.06 and "@" + c["domain"] in row[0]:
            rows.append([f"{first[0]}.{last}@{c['domain']}"] + row[1:])      # same person, second address
    rows = rows[:n]

    signals, start = [], datetime.combine(asof, time(18))
    for row in rows:
        if "@" not in row[0] or rng.random() > 0.4:
            continue
        for _ in range(rng.randint(1, 5)):
            kind = rng.choices(list(SIGNALS), weights=list(SIGNALS.values()))[0]
            target = row[0].split("@")[1] if kind == "g2_visit" else row[0]
            at = start - timedelta(days=rng.uniform(0, 30))
            signals.append([target, kind, at.isoformat(timespec="seconds")])
    return rows, signals


def outcomes(rows, seed=7, closed=0.4):
    """[(email, 'won'|'lost')] for a random ~40% of rows with a usable email."""
    rng, w, out, seen = random.Random(seed + 1), OUTCOME_WEIGHTS, [], set()
    for email, _, _, title, _, employees, industry, _, source in rows:
        if "@" not in email or " " in email or email in seen or rng.random() > closed:
            continue
        seen.add(email)
        t = title.lower()
        logit = (w["base"] + w.get(industry.lower(), 0) + w.get(source, 0)
                 + w["exec"] * any(k in t.split() or k in t for k in EXEC_WORDS)
                 + w["mid_market"] * (51 <= employees <= 1000) + w["enterprise"] * (employees > 1000)
                 + w["free_email"] * any(d in email for d in ("gmail.", "outlook.", "yahoo.")))
        out.append((email, "won" if rng.random() < 1 / (1 + math.exp(-logit)) else "lost"))
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", default="data/generated")
    p.add_argument("--n", type=int, default=500)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--asof", type=date.fromisoformat, help="signals fall in the 30 days before this date (default today)")
    a = p.parse_args()
    rows, signals = generate(a.n, a.seed, a.asof)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "leads.csv", "w", newline="") as f:
        csv.writer(f).writerows([HEADER] + rows)
    with open(out / "signals.csv", "w", newline="") as f:
        csv.writer(f).writerows([["email", "signal", "at"]] + signals)
    closed = outcomes(rows, a.seed)
    with open(out / "outcomes.csv", "w", newline="") as f:
        csv.writer(f).writerows([["email", "stage"]] + closed)
    won = sum(s == "won" for _, s in closed)
    print(f"wrote {len(rows)} leads, {len(signals)} signals and {len(closed)} outcomes ({won} won) to {out}/")


if __name__ == "__main__":
    main()
