"""ingest -> enrich -> score -> route -> sequence, end to end."""
from . import compliance
from .dedupe import dedupe
from .enrich import enrich
from .ingest import load_csv
from .routing import Router
from .scoring import load_config, score
from . import sequences
from .verify import verify


def run(csv_path, store, config_path=None, start=None):
    cfg = load_config(config_path)
    router = Router()
    leads, stats = load_csv(csv_path)
    leads, stats["person_dupes"] = dedupe(leads)
    kept = []
    for lead in leads:
        lead.email_status, _ = verify(lead.email)
        if lead.email_status != "invalid":
            kept.append(lead)
    stats["undeliverable"] = len(leads) - len(kept)
    leads, touches = kept, []
    suppressed = store.suppressed()
    for lead in leads:
        router.assign(score(enrich(lead), cfg))
        lead.blocked = compliance.check(lead, suppressed)
        if lead.blocked:
            store.clear_touches(lead.email)
        else:
            touches += sequences.build(lead, start)
    stats["blocked"] = sum(1 for l in leads if l.blocked)
    store.upsert_leads(leads)
    store.save_touches(touches)
    stats["touches"] = len(touches)
    return leads, stats
