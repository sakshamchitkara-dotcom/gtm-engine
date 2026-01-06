"""ingest -> enrich -> score -> route -> sequence, end to end."""
from .enrich import enrich
from .ingest import load_csv
from .routing import Router
from .scoring import load_config, score
from . import sequences


def run(csv_path, store, config_path=None, start=None):
    cfg = load_config(config_path)
    router = Router()
    leads, stats = load_csv(csv_path)
    touches = []
    for lead in leads:
        router.assign(score(enrich(lead), cfg))
        touches += sequences.build(lead, start)
    store.upsert_leads(leads)
    store.save_touches(touches)
    stats["touches"] = len(touches)
    return leads, stats
