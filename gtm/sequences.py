"""Multi-touch outbound cadences rendered per lead."""
from datetime import date, timedelta
from string import Template

# (day offset, channel, subject, body)
CADENCES = {
    "A": [
        (0, "email", "$company + pipeline visibility",
         "Hi $first_name,\n\nSaw $company is scaling its $dept team. Teams your size usually lose "
         "~20% of pipeline to slow lead routing. Worth 15 min to compare notes?\n\n- $owner_name"),
        (1, "linkedin", "", "Connect request: note referencing $company's growth"),
        (3, "call", "", "Call $first_name, reference email #1"),
        (5, "email", "re: $company + pipeline visibility",
         "$first_name - quick follow-up. Happy to send a 2-min Loom instead of a call.\n\n- $owner_name"),
        (10, "email", "closing the loop",
         "Hi $first_name, I'll assume timing is off. Mind if I check back next quarter?\n\n- $owner_name"),
    ],
    "B": [
        (0, "email", "idea for $company",
         "Hi $first_name,\n\nWe help $dept teams at companies like $company automate lead routing "
         "and scoring. Open to a short chat?\n\n- $owner_name"),
        (4, "email", "re: idea for $company", "Bumping this, $first_name. Useful or not a priority?\n\n- $owner_name"),
        (9, "linkedin", "", "Connect request"),
    ],
    "C": [
        (0, "email", "resources for $dept teams",
         "Hi $first_name, sharing our RevOps playbook in case it's useful for $company.\n\n- $owner_name"),
    ],
}


def _dept(title):
    t = title.lower()
    for key, dept in [("revops", "RevOps"), ("revenue", "revenue"), ("sales", "sales"),
                      ("growth", "growth"), ("marketing", "marketing")]:
        if key in t:
            return dept
    return "GTM"


def build(lead, start=None):
    """Returns list of touch dicts. Tier D / nurture leads get no outbound."""
    steps = CADENCES.get(lead.tier, [])
    if not steps or lead.owner in ("nurture", "unassigned"):
        return []
    start = start or date.today()
    ctx = {
        "first_name": lead.first_name or "there",
        "company": lead.company or "your team",
        "dept": _dept(lead.title),
        "owner_name": lead.owner.split("@")[0].title(),
    }
    touches = []
    for n, (offset, channel, subject, body) in enumerate(steps, 1):
        day = start + timedelta(days=offset)
        while day.weekday() >= 5:  # skip weekends
            day += timedelta(days=1)
        touches.append({
            "email": lead.email, "step": n, "date": day.isoformat(), "channel": channel,
            "subject": Template(subject).safe_substitute(ctx),
            "body": Template(body).safe_substitute(ctx),
        })
    return touches
