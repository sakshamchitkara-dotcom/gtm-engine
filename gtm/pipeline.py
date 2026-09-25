"""dedupe -> verify -> enrich -> score (+intent) -> route -> comply -> sequence -> store."""
from . import compliance, intent, sequences
from .dedupe import dedupe
from .enrich import enrich
from .ingest import load_csv
from .routing import Router
from .scoring import load_config, score
from .verify import verify


def process(leads, store, cfg=None, start=None, asof=None, team=None, router=None):
    """Runs already-normalized Lead objects through the pipeline. Returns (kept leads, stats).

    Pass a long-lived router to keep round-robin/capacity state across calls (the web API does).
    """
    cfg = cfg or load_config()
    router = router or Router(team)
    stats = {}
    leads, stats["person_dupes"] = dedupe(leads)
    kept = []
    for lead in leads:
        lead.email_status, _ = verify(lead.email)
        if lead.email_status != "invalid":
            kept.append(lead)
    stats["undeliverable"] = len(leads) - len(kept)
    leads, touches = kept, []
    suppressed = store.suppressed()
    pts = intent.points(store.signals(), asof)
    for lead in leads:
        lead.intent = intent.for_lead(enrich(lead), pts)
        score(lead, cfg)
    router.seed(store.leads())
    # best lead first: the first routed lead at a domain claims the account for its pool
    for lead in sorted(leads, key=lambda l: -l.score):
        router.assign(lead)
    for lead in leads:
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


def run(csv_path, store, config_path=None, start=None, asof=None, team=None, mapping=None):
    leads, stats = load_csv(csv_path, mapping)
    leads, more = process(leads, store, load_config(config_path), start, asof, team)
    return leads, {**stats, **more}
