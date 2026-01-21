# gtm-engine

A small, dependency-free GTM (go-to-market) engineering system in Python:
**ingest → enrich → score → route → sequence → track → report**.

> **Heads up:** this repo also demonstrates commit backdating. All commit dates
> (Sept 1–24, 2026) were set manually. See [docs/BACKDATING.md](docs/BACKDATING.md).

## What it does

| Stage | Module | Notes |
|---|---|---|
| Ingest | `gtm/ingest.py` | CSV from Apollo/HubSpot/Clay-style exports, header aliasing, email validation, dedupe |
| Enrich | `gtm/enrich.py` | domain, free-email flag, seniority from title, company size band |
| Score | `gtm/scoring.py` | ICP fit 0–100 + A/B/C/D tier, weights in `config/icp.json`, explainable `reasons` |
| Route | `gtm/routing.py` | territory (NA/EMEA/APAC) + round-robin; tier-A enterprise → AEs, D → nurture |
| Sequence | `gtm/sequences.py` | per-tier multi-touch cadences (email/LinkedIn/call), weekend-aware |
| Store | `gtm/store.py` | SQLite, idempotent upserts, funnel stage events |
| Report | `gtm/analytics.py` | tier mix, rep load, stage funnel with conversion |

## Quickstart

```bash
python3 -m gtm run data/sample_leads.csv --start 2026-09-01
python3 -m gtm leads --tier A
python3 -m gtm today --date 2026-09-02
python3 -m gtm stage priya@northwind.io meeting
python3 -m gtm report
python3 -m gtm export --tier A > crm_import.csv
```

```
rows=12 kept=10 invalid=1 dupes=1 touches=30
100 A  priya@northwind.io               maya@acme.io
 94 A  tom.b@ledgerly.com               noah@acme.io
 ...
```

## Tests

```bash
python3 -m unittest -v
```

Python 3.10+, stdlib only.
