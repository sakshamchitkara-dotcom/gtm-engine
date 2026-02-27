"""CRM import CSVs. Column names match HubSpot's and Salesforce's lead import templates."""
import csv

HUBSPOT_STATUS = {"new": "NEW", "contacted": "ATTEMPTED_TO_CONTACT", "replied": "CONNECTED",
                  "meeting": "IN_PROGRESS", "opportunity": "OPEN_DEAL", "won": "OPEN_DEAL",
                  "lost": "UNQUALIFIED"}
HUBSPOT_LIFECYCLE = {"meeting": "salesqualifiedlead", "opportunity": "opportunity", "won": "customer"}
SF_STATUS = {"new": "Open - Not Contacted", "contacted": "Working - Contacted", "replied": "Working - Contacted",
             "meeting": "Working - Contacted", "opportunity": "Closed - Converted", "won": "Closed - Converted",
             "lost": "Closed - Not Converted"}
SF_RATING = {"A": "Hot", "B": "Warm", "C": "Cold", "D": "Cold"}

# (CRM column, function of lead record)
MAPPINGS = {
    "basic": [(k, lambda r, k=k: r[k]) for k in ("email", "score", "tier", "owner", "stage")],
    "hubspot": [
        ("Email", lambda r: r["email"]),
        ("First Name", lambda r: r.get("first_name", "")),
        ("Last Name", lambda r: r.get("last_name", "")),
        ("Job Title", lambda r: r.get("title", "")),
        ("Company Name", lambda r: r.get("company", "")),
        ("Number of Employees", lambda r: r.get("employees") or ""),
        ("Industry", lambda r: r.get("industry", "")),
        ("Country/Region", lambda r: r.get("country", "")),
        ("Lead Status", lambda r: HUBSPOT_STATUS[r["stage"]]),
        ("Lifecycle Stage", lambda r: HUBSPOT_LIFECYCLE.get(r["stage"], "lead")),
        ("Contact owner", lambda r: "" if r["owner"] in ("nurture", "unassigned") else r["owner"]),
        ("Original Source Drill-Down 1", lambda r: r.get("source", "")),
        ("GTM Score", lambda r: r["score"]),
        ("GTM Tier", lambda r: r["tier"]),
    ],
    "salesforce": [
        ("Email", lambda r: r["email"]),
        ("FirstName", lambda r: r.get("first_name", "")),
        ("LastName", lambda r: r.get("last_name") or "[not provided]"),  # required field
        ("Title", lambda r: r.get("title", "")),
        ("Company", lambda r: r.get("company") or "[not provided]"),     # required field
        ("NumberOfEmployees", lambda r: r.get("employees") or ""),
        ("Industry", lambda r: r.get("industry", "")),
        ("Country", lambda r: r.get("country", "")),
        ("LeadSource", lambda r: r.get("source", "")),
        ("Status", lambda r: SF_STATUS[r["stage"]]),
        ("Rating", lambda r: SF_RATING.get(r["tier"], "Cold")),
        ("Owner_Email__c", lambda r: "" if r["owner"] in ("nurture", "unassigned") else r["owner"]),
        ("GTM_Score__c", lambda r: r["score"]),
    ],
}


def _safe(v):
    """Neutralize spreadsheet formula injection (=, +, -, @ at the start of a cell)."""
    return "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v


def export(rows, fmt, out):
    cols = MAPPINGS[fmt]
    w = csv.writer(out)
    w.writerow([c for c, _ in cols])
    for r in rows:
        w.writerow([_safe(f(r)) for _, f in cols])
