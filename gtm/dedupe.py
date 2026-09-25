"""Fuzzy dedupe: company name variants and the same person under two emails."""
import re
from collections import Counter
from difflib import SequenceMatcher

SUFFIXES = {"inc", "llc", "ltd", "limited", "gmbh", "corp", "corporation", "co", "plc", "sa",
            "sas", "bv", "ag", "pty", "pvt", "srl", "oy", "ab", "company", "the"}


def normalize_company(name):
    words = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower().replace("&", " and ")).split()
    return " ".join(w for w in words if w not in SUFFIXES)


def cluster_companies(names, threshold=0.88):
    """Returns {original name: canonical name}. Canonical = most frequent spelling, ties go to the first seen.

    ponytail: O(u^2) over unique normalized names; block by first letter if u gets into the 10k+ range.
    """
    counts = Counter(n for n in names if n)
    clusters = []  # [(normalized key, [originals])]
    for name in counts:
        key = normalize_company(name)
        for ckey, members in clusters:
            if key == ckey or (key and SequenceMatcher(None, key, ckey).ratio() >= threshold):
                members.append(name)
                break
        else:
            clusters.append((key, [name]))
    out = {}
    for _, members in clusters:
        canon = max(members, key=counts.get)  # ties -> first seen
        out.update(dict.fromkeys(members, canon))
    return out


def person_key(lead):
    first, last = (re.sub(r"[^a-z]", "", (n or "").lower()) for n in (lead.first_name, lead.last_name))
    if not (first and last):
        return None
    return first, last, lead.email.split("@", 1)[1]


def dedupe(leads):
    """Canonicalize company names and drop person dupes (same name + domain). Returns (kept, n_dropped)."""
    canon = cluster_companies(l.company for l in leads)
    kept, seen = [], set()
    for lead in leads:
        lead.company = canon.get(lead.company, lead.company)
        key = person_key(lead)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        kept.append(lead)
    return kept, len(leads) - len(kept)
