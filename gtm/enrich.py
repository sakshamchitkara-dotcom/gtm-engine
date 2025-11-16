"""Cheap, offline enrichment: domain, seniority, company size band.

ponytail: rule-based. Swap in a Clearbit/Apollo lookup inside enrich() if you
need firmographics you don't already have in the CSV.
"""

FREE_EMAIL = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com",
    "aol.com", "proton.me", "protonmail.com", "live.com", "gmx.com",
}

# checked in order, first match wins
SENIORITY = [
    ("c_level", ["chief", "ceo", "cto", "cro", "cmo", "coo", "cfo", "founder", "co-founder", "owner"]),
    ("vp", ["vp", "vice president", "head of"]),
    ("director", ["director"]),
    ("manager", ["manager", "lead"]),
]

SIZE_BANDS = [(1, 10, "micro"), (11, 50, "small"), (51, 200, "mid"),
              (201, 1000, "upper_mid"), (1001, 10**9, "enterprise")]


def seniority_of(title):
    words = title.lower().replace(",", " ").replace("/", " ")
    tokens = set(words.split())
    for level, keys in SENIORITY:
        for k in keys:
            if (" " in k and k in words) or k in tokens:
                return level
    return "ic" if title else "unknown"


def size_band(employees):
    for lo, hi, name in SIZE_BANDS:
        if lo <= employees <= hi:
            return name
    return "unknown"


def enrich(lead):
    lead.domain = lead.email.split("@", 1)[1]
    lead.is_free_email = lead.domain in FREE_EMAIL
    lead.seniority = seniority_of(lead.title)
    lead.size_band = size_band(lead.employees)
    if not lead.company and not lead.is_free_email:
        lead.company = lead.domain.split(".")[0].title()
    return lead
