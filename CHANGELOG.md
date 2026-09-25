# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
