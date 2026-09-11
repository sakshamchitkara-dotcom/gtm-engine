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
| Score | `gtm/scoring.py` | ICP fit 0–100 + A/B/C/D tier, weights in `gtm/config/icp.json`, explainable `reasons` |
| Route | `gtm/routing.py` | territory + round-robin, account-sticky, per-rep capacity from `gtm/config/team.json` |
| Comply | `gtm/compliance.py` | suppression list (emails + domains), unsubscribes, GDPR: EU/UK leads need an inbound source |
| Sequence | `gtm/sequences.py` | per-tier multi-touch cadences (email/LinkedIn/call), weekend-aware |
| Experiment | `gtm/experiments.py` | hashed A/B opener subjects, two-proportion z-test |
| Send | `gtm/outbox.py` | SMTP or `--dry-run` .eml files, per-rep daily caps, `List-Unsubscribe` (+ RFC 8058 one-click) |
| Replies | `gtm/replies.py` | rule-based: interested / not_now / ooo / referral / negative / unsubscribe → stage + suppression |
| Store | `gtm/store.py` | SQLite, idempotent upserts, funnel stage events, sends, signals, suppression |
| Report | `gtm/analytics.py`, `accounts.py`, `forecast.py`, `digest.py` | funnel, account rollup + committee coverage, weighted pipeline, per-rep daily digest |
| Calibrate | `gtm/calibrate.py` | logistic regression on won/lost → suggested `icp.json` weights, same tier sizes |
| Alert | `gtm/notify.py` | Slack incoming-webhook alert for new tier-A leads, dry run by default |
| SLA | `gtm/sla.py` | time from import to first touch vs per-tier targets in business hours per rep time zone, breach list |
| Export | `gtm/crm.py` | HubSpot / Salesforce import CSVs |
| Web | `gtm/web.py` | JSON API + dashboard on `http.server`, optional bearer token |

## Quickstart

```bash
pip install -e .                      # or use `python3 -m gtm` everywhere below
python3 scripts/gen_leads.py --asof 2026-09-25        # 500 messy leads + signals + outcomes -> data/generated/
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
sent=307 skipped_sent=0 skipped_contact=0 capped=73 refused=0  (dry run -> outbox/2026-09-28/)
```

`dupes=18+12` is exact-email duplicates + the same person under a second address;
`blocked` is suppressed or GDPR-without-consent leads (scored and routed, never emailed);
`capped` touches stay due and go out on the next day's run.

### Closed-loop: outcomes, calibration, alerts, SLA

`gen_leads.py` also writes `outcomes.csv`: won/lost for ~40% of leads, drawn from a hidden
model that disagrees with `icp.json` on purpose. Real output, continuing the run above:

```
$ gtm notify --limit 2                     # dry run: prints the Slack payload, records nothing
{
  "text": "*2 new tier-A leads*\n- *Tom Rossi*, Sales Operations Manager at Cloudware Inc - score 100, intent 16, owner maya@acme.io (tom.rossi@cloudware.com)\n- ..."
}
-- dry run: nothing sent or recorded (use --send)

$ gtm outcomes data/generated/outcomes.csv
updated=168 unknown_lead=10 bad_stage=0

$ gtm calibrate --write icp.calibrated.json
closed leads: 168  won: 63 (38%)
AUC current score: 0.564   calibrated model: 0.870  (in-sample)

win rate by current tier:
  A: 18/47 = 38%
  B: 32/70 = 46%
  C: 11/44 = 25%
  D: 2/7 = 29%

feature                             n  won    coef   now   new
industries:fintech                 21   17    1.61    20    29
...
industries:software                29    4   -1.13    20   -20
penalties:free_email               12    0   -1.66   -30   -30

base +67; tier cutoffs A>=79, B>=53, C>=30

$ gtm forecast
owner              leads    open ACV   weighted       won
maya@acme.io          34   1,290,000     25,800    90,000
...
TOTAL                443  10,461,000    209,220 2,504,000

$ gtm cohorts --by source
cohort         leads contacted  meeting  won lost win rate
content          117       36%      11%   13   29      31%
demo_request      52       46%      29%   15    9      62%
list             171       36%      13%   23   39      37%
webinar          103       39%      12%   12   28      30%

$ gtm sla --now "$(date -u -v+30H +%Y-%m-%dT%H:%M:%S)"   # imported Fri 10:17 UTC; as if 30h later
SLA hours: A=4, B=24, C=72  (business hours 9-18h, rep time zones)

owner              leads touched median h in SLA breached
maya@acme.io          34       2      0.0   100%       15
jordan@acme.io        27       4      0.0   100%       10
...
untouched past SLA (oldest 10 of 51):
     9.0h > 4h  A  ivan.diaz@northlabs.com          jordan@acme.io
...
```

30 wall-clock hours after a Friday-morning import is Saturday afternoon, but only Friday 9-18
counts: New York reps' untouched tier-A leads are 9.0 working hours old, while kai (Kolkata,
imported at 15:47 local) has no breaches yet.

The in-sample AUC flatters the model. Out of sample (a different-seed 900-lead file with
325 closed outcomes, scored once with each config) the calibrated weights moved AUC from
0.631 to 0.697 and tier-A win rate from 53% to 60%, with tier sizes held roughly constant.

## Commands

| Command | Does |
|---|---|
| `run CSV [--start D] [--asof T]` | full pipeline; re-runs are idempotent and keep funnel stage |
| `leads`, `today`, `stage EMAIL STAGE`, `report` | list, unsent due touches for leads still new/contacted, move a lead, funnel report |
| `outcomes CSV` | bulk stage updates (`email,stage`), e.g. closed won/lost exported from the CRM |
| `calibrate [--write PATH]` | fit icp.json weights to won/lost history (logistic regression), keep tier sizes |
| `verify EMAIL...` | deliverability check without importing |
| `signals CSV` | load intent signals (`email,signal,at`; email may be a bare domain) |
| `suppress [VALUE...] [--list]`, `unsubscribe EMAIL` | do-not-contact list |
| `reply EMAIL TEXT` (`-` for stdin) | classify a reply and apply it |
| `outbox [--date D] [--dry-run]` | send due emails |
| `accounts`, `forecast`, `experiment`, `digest` | reports |
| `cohorts [--by both\|month\|source]` | per import month and lead source: share contacted, share with a meeting, won, lost, win rate |
| `sla [--now T] [--backfill]` | time to first touch per rep vs per-tier SLA, plus untouched leads past SLA; `--backfill` estimates start times for leads imported before 0.3.0 |
| `notify [--send] [--limit N]` | Slack alert for new, contactable tier-A leads; prints the payload unless `--send` |
| `export [--tier] [--format basic\|hubspot\|salesforce]` | CRM CSV to stdout |
| `serve [--host] [--port]` | web API + dashboard |

## Configuration

- `gtm/config/icp.json`: scoring weights, tier cutoffs, penalties.
- `gtm/config/team.json`: AE/SDR pools per region, `capacity` (leads per run) and
  `daily_send_cap` per rep, each with a `default`.
  `territories` maps region -> country codes (pools are keyed by region); countries not listed
  go to `default_region`.
  `sla_hours` sets the time-to-first-touch target per tier (A 4h, B 24h, C 72h).
  `business_hours` (`start`/`end` hour, `days` with Monday=0) makes the SLA clock count only
  working hours, in each rep's zone from `timezones` (`default` + per-rep IANA names); remove it
  for a wall clock. Its `holidays` skips whole local days: a list of `YYYY-MM-DD` for everyone,
  or a dict keyed by rep email, then zone name, then `default`
  (`{"default": ["2026-11-26"], "Europe/Berlin": ["2026-10-03"]}`).
- `GTM_CONFIG_DIR`: a directory with your own `icp.json` / `team.json`; used by every command
  (the bundled files live inside the package, so this is how to customize a `pip install .`).
- SMTP: `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_STARTTLS` (1).
- Unsubscribe: `GTM_UNSUB_MAILTO`; set `GTM_BASE_URL` + `GTM_UNSUB_SECRET` to add a signed
  one-click link served by `gtm serve` at `/unsubscribe`.
- Slack: `SLACK_WEBHOOK_URL` (incoming webhook) for `gtm notify --send`.
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
The server is a threaded `http.server`; store access is serialized by one lock (bodies are read and
responses written outside it). Fine for a team dashboard; put a real server in front for anything public.

## Known limits

- `gtm calibrate` reports in-sample AUC only; with a few hundred closed deals, hold some out
  before trusting small gains. It only reweights keys already in `icp.json`.
- SLA holidays are dates you list in team.json; nothing ships a country calendar. `gtm sla --backfill` start times for pre-0.3.0
  leads are estimates (first stage event, else the row's last update).
- Reply classification is regex rules; email verification never probes SMTP/MX.
- The web API serializes all store work behind one lock.

## Tests

```bash
python3 -m unittest -v
```

CI (GitHub Actions) runs the tests on Python 3.10-3.13 plus an end-to-end
smoke of a non-editable install (CLI and web server) on generated data. Python 3.10+, stdlib only.
