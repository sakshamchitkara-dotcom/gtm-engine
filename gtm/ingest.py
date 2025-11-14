"""Load raw leads from CSV, normalize fields, drop junk and duplicates."""
import csv
import re

from .models import Lead

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)

# common header spellings from different tools (Apollo, HubSpot, Clay exports...)
ALIASES = {
    "email": ["email", "email address", "work email", "e-mail"],
    "first_name": ["first_name", "first name", "firstname"],
    "last_name": ["last_name", "last name", "lastname"],
    "title": ["title", "job title", "jobtitle"],
    "company": ["company", "company name", "organization", "account"],
    "employees": ["employees", "# employees", "company size", "headcount"],
    "industry": ["industry"],
    "country": ["country", "hq country"],
    "source": ["source", "lead source"],
}


def _pick(row, field):
    lowered = {k.strip().lower(): v for k, v in row.items() if k}
    for alias in ALIASES[field]:
        if alias in lowered and lowered[alias] is not None:
            return lowered[alias].strip()
    return ""


def _to_int(value):
    digits = re.sub(r"[^\d]", "", value.split("-")[0])  # "51-200" -> 51
    return int(digits) if digits else 0


def normalize(row):
    email = _pick(row, "email").lower()
    if not EMAIL_RE.match(email):
        return None
    return Lead(
        email=email,
        first_name=_pick(row, "first_name").title(),
        last_name=_pick(row, "last_name").title(),
        title=_pick(row, "title"),
        company=_pick(row, "company"),
        employees=_to_int(_pick(row, "employees")),
        industry=_pick(row, "industry").lower(),
        country=_pick(row, "country").upper(),
        source=_pick(row, "source").lower(),
    )


def load_csv(path):
    """Returns (leads, stats). Duplicate emails keep the first occurrence."""
    leads, seen = [], set()
    stats = {"rows": 0, "invalid": 0, "duplicates": 0}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            stats["rows"] += 1
            lead = normalize(row)
            if lead is None:
                stats["invalid"] += 1
            elif lead.email in seen:
                stats["duplicates"] += 1
            else:
                seen.add(lead.email)
                leads.append(lead)
    stats["kept"] = len(leads)
    return leads, stats
