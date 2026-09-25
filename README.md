# gtm-engine

A small, dependency-free GTM (go-to-market) engineering system in Python:
**ingest → dedupe → verify → enrich → score → route → sequence → send → track → report**.

> **Heads up:** this repo also demonstrates commit backdating. All commit dates
> (Sept 1–24, 2026) were set manually. See [docs/BACKDATING.md](docs/BACKDATING.md).
> That applies to the first 17 commits (through `083c375`). Everything after it
> carries real, unmodified timestamps; see [CHANGELOG.md](CHANGELOG.md).

## What it does

| Stage | Module | Notes |
|---|---|---|
| Ingest | `gtm/ingest.py` | CSV from Apollo/HubSpot/Clay-style exports, header aliasing, exact-email dedupe |
| Dedupe | `gtm/dedupe.py` | company names normalized (Inc/LLC/Ltd/GmbH) + difflib clustering; same person under two emails |
| Verify | `gtm/verify.py` | syntax, role-based (`info@`, `sales@`), disposable and typo domains (`gmial.com`) → valid / risky / invalid |
| Enrich | `gtm/enrich.py` | domain, free-email flag, seniority from title, company size band |
| Intent | `gtm/intent.py` | signals (pricing_page, demo_page, g2_visit...) with a 7-day half-life → intent points |
| Score | `gtm/scoring.py` | ICP fit 0–100 + A/B/C/D tier, weights in `config/icp.json`, explainable `reasons` |
| Route | `gtm/routing.py` | territory + round-robin, account-sticky, per-rep capacity from `config/team.json` |
| Comply | `gtm/compliance.py` | suppression list (emails + domains), unsubscribes, GDPR: EU/UK leads need an inbound source |
| Sequence | `gtm/sequences.py` | per-tier multi-touch cadences (email/LinkedIn/call), weekend-aware |
| Experiment | `gtm/experiments.py` | hashed A/B opener subjects, two-proportion z-test |
| Send | `gtm/outbox.py` | SMTP or `--dry-run` .eml files, per-rep daily caps, `List-Unsubscribe` (+ RFC 8058 one-click) |
| Replies | `gtm/replies.py` | rule-based: interested / not_now / ooo / referral / negative / unsubscribe → stage + suppression |
| Store | `gtm/store.py` | SQLite, idempotent upserts, funnel stage events, sends, signals, suppression |
| Report | `gtm/analytics.py`, `accounts.py`, `forecast.py`, `digest.py` | funnel, account rollup + committee coverage, weighted pipeline, per-rep daily digest |
| Export | `gtm/crm.py` | HubSpot / Salesforce import CSVs |
| Web | `gtm/web.py` | JSON API + dashboard on `http.server`, optional bearer token |

## Quickstart

```bash
pip install -e .                      # or use `python3 -m gtm` everywhere below
python3 scripts/gen_leads.py --asof 2026-09-25        # 500 messy leads + signals -> data/generated/
gtm signals data/generated/signals.csv
gtm run data/generated/leads.csv --start 2026-09-28 --asof 2026-09-25T18:00:00
gtm report
gtm outbox --date 2026-09-28 --dry-run                # .eml files in outbox/2026-09-28/<rep>/
gtm reply <lead-email> "Sounds good, what times work?"
gtm forecast
gtm digest --date 2026-09-28                          # digests/2026-09-28/<rep>.md
gtm export --format hubspot > hubspot_import.csv
GTM_API_TOKEN=secret gtm serve --port 8000            # dashboard at http://127.0.0.1:8000/#token=secret
```

Real output from that run:

```
signals loaded=611 skipped=0 (re-run `gtm run` to rescore)
rows=500 kept=470 invalid=12 dupes=18+12 undeliverable=15 blocked=47 touches=1164
sent=267 skipped_sent=0 skipped_contact=0 capped=113 refused=0  (dry run -> outbox/2026-09-28/)
```

`dupes=18+12` is exact-email duplicates + the same person under a second address;
`blocked` is suppressed or GDPR-without-consent leads (scored and routed, never emailed);
`capped` touches stay due and go out on the next day's run.

After simulating some replies and stage moves (`gtm reply`, `gtm stage`):

```
$ gtm forecast
owner              leads    open ACV   weighted       won
jordan@acme.io        21   1,110,000     94,800         0
alex@acme.io          57   2,619,000     92,100         0
...
TOTAL                443  16,948,000    697,980    23,000

$ gtm experiment
experiment opener-subject-v1
arm           sent  replied    rate
control        111       14   12.6%
challenger      90        6    6.7%
challenger vs control: z=-1.4 p=0.1614 (not significant)
```

## Commands

| Command | Does |
|---|---|
| `run CSV [--start D] [--asof T]` | full pipeline; re-runs are idempotent and keep funnel stage |
| `leads`, `today`, `stage EMAIL STAGE`, `report` | list, due touches, move a lead, funnel report |
| `verify EMAIL...` | deliverability check without importing |
| `signals CSV` | load intent signals (`email,signal,at`; email may be a bare domain) |
| `suppress [VALUE...] [--list]`, `unsubscribe EMAIL` | do-not-contact list |
| `reply EMAIL TEXT` (`-` for stdin) | classify a reply and apply it |
| `outbox [--date D] [--dry-run]` | send due emails |
| `accounts`, `forecast`, `experiment`, `digest` | reports |
| `export [--tier] [--format basic\|hubspot\|salesforce]` | CRM CSV to stdout |
| `serve [--host] [--port]` | web API + dashboard |

## Configuration

- `config/icp.json`: scoring weights, tier cutoffs, penalties.
- `config/team.json`: AE/SDR pools per region, `capacity` (leads per run) and
  `daily_send_cap` per rep, each with a `default`.
- SMTP: `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_STARTTLS` (1).
- Unsubscribe: `GTM_UNSUB_MAILTO`; set `GTM_BASE_URL` + `GTM_UNSUB_SECRET` to add a signed
  one-click link served by `gtm serve` at `/unsubscribe`.
- Web: `GTM_API_TOKEN` requires `Authorization: Bearer <token>` on `/api/*`.

## Web API

```
GET  /api/leads?tier=A&owner=sam@acme.io&limit=50
GET  /api/report | /api/forecast | /api/accounts
POST /api/leads     {"email": "...", "title": "...", ...}  or a list (max 1000)
POST /api/signals   {"email": "...", "signal": "pricing_page", "at": "2026-09-25T09:00:00Z"}
POST /api/replies   {"email": "...", "text": "..."}          # reply webhook
```

Bodies must be `application/json`, at most 1 MB; unknown fields and bad values get a 400 listing each bad item.
The server is single-threaded `http.server`: fine for a team dashboard, put a real server in front for anything public.

## Tests

```bash
python3 -m unittest -v
```

CI (GitHub Actions) runs the tests on Python 3.10, 3.12 and 3.13 plus an end-to-end
smoke of the CLI and web server on generated data. Python 3.10+, stdlib only.
