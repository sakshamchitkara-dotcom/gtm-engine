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


def parse_mapping(pairs):
    """["Contact Email=email", ...] -> {"contact email": "email"}; raises ValueError."""
    mapping = {}
    for pair in pairs or ():
        header, sep, field = pair.rpartition("=")
        field = field.strip().lower()
        if not sep or not header.strip():
            raise ValueError(f"expected HEADER=FIELD, got {pair!r}")
        if field not in ALIASES:
            raise ValueError(f"unknown field {field!r} in {pair!r}; fields: {', '.join(ALIASES)}")
        mapping[header.strip().lower()] = field
    return mapping


def _remap(row, mapping):
    """Mapped columns replace whatever the aliases would have picked for their field."""
    targets = set(mapping.values())
    out = {k: v for k, v in row.items() if k and not any(k.strip().lower() in ALIASES[t] for t in targets)}
    for k, v in row.items():
        if k and k.strip().lower() in mapping:
            out[mapping[k.strip().lower()]] = v
    return out


def load_csv(path, mapping=None):
    """Returns (leads, stats). Duplicate emails keep the first occurrence.
    mapping: {csv header (lowercase): lead field} for columns the aliases don't know."""
    leads, seen = [], set()
    stats = {"rows": 0, "invalid": 0, "duplicates": 0}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = {h.strip().lower() for h in reader.fieldnames or () if h}
        if missing := sorted(set(mapping or ()) - headers):
            raise ValueError(f"--map columns not in {path}: {', '.join(missing)}")
        if "email" not in (mapping or {}).values() and not headers & set(ALIASES["email"]):
            raise ValueError(f"no email column in {path} (headers: {', '.join(reader.fieldnames or [])});"
                             " name it with --map 'HEADER=email'")
        for row in reader:
            if mapping:
                row = _remap(row, mapping)
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
