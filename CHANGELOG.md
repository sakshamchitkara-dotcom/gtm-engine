# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.4.0] - 2026-09-25

Commits for this release carry real, unmodified timestamps.

### Added
- SLA business hours: team.json `business_hours` (start/end hour, weekdays) and `timezones`
  (per rep + default). Time to first touch and breach age count only working hours in the
  owner's zone (zoneinfo, DST-safe). On in the bundled team.json.
- `gtm sla --backfill`: estimated `created` events for leads imported before 0.3.0, which
  were otherwise reported as untracked forever.

### Fixed
- `gtm today` listed touches already sent and cadence steps for leads in meeting/won/lost;
  the digest showed the latter too. Both now use `Store.open_touches()`.
- A missing CSV, `--config` or `--team` file printed a traceback; the CLI now exits with
  `<cmd>: no such file: <path>`.

## [0.3.0] - 2026-09-25

Commits for this release carry real, unmodified timestamps.

### Added
- `gtm calibrate`: L2 logistic regression (stdlib) on closed won/lost leads; prints current vs
  model AUC, win rate per tier and per-feature suggested points; `--write` saves an icp.json with
  a `base` intercept and tier cutoffs that keep each tier's headcount.
- `gtm outcomes CSV`: bulk stage updates (`email,stage`), e.g. won/lost exported from a CRM.
- `gtm notify`: Slack incoming-webhook alert for new tier-A leads. Dry run unless `--send`;
  each lead is announced once; lead data is escaped for Slack mrkdwn.
- `gtm sla`: time from first import to first touch per rep against `sla_hours` per tier,
  plus the untouched leads already past SLA. Imports now record a `created` event.
- `team.json`: `territories` (region -> countries), `default_region`, `sla_hours`.
- `GTM_CONFIG_DIR` to point every command at your own icp.json / team.json.
- `scripts/gen_leads.py` writes `outcomes.csv` from a hidden win model.
- `gtm --version`; tests for the CLI, calibration, notify, SLA, ingest aliases and web limits.

### Changed
- The web server is threaded; one lock serializes store work, bodies are read and responses
  written outside it.
- Config moved to `gtm/config/` and ships as package data.
- Leads are routed in score order, so the best lead at an account picks its owner (AE vs SDR).
- CI smoke-tests a non-editable install from outside the checkout, on Python 3.10-3.13.

### Fixed
- `pip install .` (non-editable) crashed on every run: config was looked up outside the package.
- Re-running with new leads reassigned existing leads (199 of 443 in a generated re-run);
  known leads now keep their rep and accounts stay sticky across runs.
- Funnel counted a lead lost after a meeting as only "contacted"; it now uses stage history.
- Dashboard tier filter rendered in the heading's bold, could paint stale results after quick
  changes, and hid the 50-row cap; it now shows "showing N of M".
- `gtm stage` on an unknown email printed a traceback; the CLI now closes its database.
- `gen_leads.py --n` above ~918 looped forever.

## [0.2.0] - 2026-09-25

Commits for this release carry real, unmodified timestamps.

### Added
- `verify`: syntax, role-based, disposable and typo-domain checks → valid / risky / invalid.
  Invalid addresses are dropped; risky ones take a scoring penalty.
- `dedupe`: company-name normalization and difflib clustering; person dupes by name + domain.
- `compliance`: suppression list (emails and domains), `gtm unsubscribe`, GDPR rule
  (EU/EEA/UK leads need an inbound source or they are blocked from outbound).
- `intent`: signals CSV with 7-day half-life decay; intent points feed ICP scoring.
- `accounts`: domain rollup with account score and buying-committee coverage.
- `replies`: rule-based reply classifier driving stage changes and suppression.
- `experiments`: hash-assigned A/B opener subjects and a two-proportion z-test.
- `outbox`: SMTP sending or `--dry-run` .eml files, per-rep daily caps,
  `List-Unsubscribe` with optional HMAC-signed RFC 8058 one-click link.
- `forecast`: weighted pipeline (stage probability × ACV by size band) per owner.
- `digest`: per-rep markdown daily digest.
- `crm`: HubSpot and Salesforce import mappings (`gtm export --format`).
- `web`: stdlib JSON API, reply webhook, one-click unsubscribe and HTML dashboard;
  optional `GTM_API_TOKEN` bearer auth and per-field input validation.
- `config/team.json`: routing team, per-rep lead capacity and daily send caps.
- `scripts/gen_leads.py`: seeded generator for ~500 messy leads plus signals.
- `pyproject.toml` with a `gtm` console script; GitHub Actions CI.

### Changed
- Routing is account-sticky: all leads at one company domain share an owner.
- `Store.leads()` returns the full lead record merged with its columns.
- `pipeline.process()` runs pre-built leads (used by the web API); `run()` wraps it.

### Fixed
- `gtm outbox` without SMTP config, and `gtm serve` on a busy port, exit with a message
  instead of a traceback; one refused recipient no longer aborts a send run.
- Web-posted leads all went to the first rep in the pool (round-robin reset per request).

## [0.1.0] - 2026-09-24

Initial pipeline: CSV ingest, enrichment, ICP scoring, territory routing, cadences,
SQLite store, funnel report and CLI. These 17 commits were intentionally backdated
as a demonstration; see [docs/BACKDATING.md](docs/BACKDATING.md).
