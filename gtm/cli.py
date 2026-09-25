import argparse
import csv
import json
import os
import sys
from urllib.error import URLError
from datetime import date, datetime

from . import (accounts, analytics, calibrate, compliance, crm, digest, experiments, forecast, intent, notify,
               outbox, pipeline, replies, sla)
from . import __version__
from .routing import load_team
from .scoring import load_config
from .store import STAGES, Store
from .verify import verify


def main(argv=None):
    p = argparse.ArgumentParser(prog="gtm", description="GTM engineering pipeline")
    p.add_argument("--db", default="gtm.db")
    p.add_argument("--version", action="version", version=f"gtm-engine {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="ingest, enrich, score, route and sequence a CSV")
    r.add_argument("csv")
    r.add_argument("--config")
    r.add_argument("--start", type=date.fromisoformat, help="cadence start date (YYYY-MM-DD)")
    r.add_argument("--asof", type=datetime.fromisoformat, help="intent decay reference time (default now)")

    ls = sub.add_parser("leads", help="list scored leads")
    ls.add_argument("--tier")
    ls.add_argument("--limit", type=int, default=20)

    t = sub.add_parser("today", help="unsent touches due on/before a date, for leads still new/contacted")
    t.add_argument("--date", default=date.today().isoformat())

    st = sub.add_parser("stage", help="move a lead through the funnel")
    st.add_argument("email")
    st.add_argument("stage", choices=STAGES)

    oc = sub.add_parser("outcomes", help="bulk stage updates from a CSV (email,stage), e.g. CRM won/lost")
    oc.add_argument("csv")

    cb = sub.add_parser("calibrate", help="fit icp.json weights to closed won/lost history")
    cb.add_argument("--config", help="icp config to start from (default bundled)")
    cb.add_argument("--min-support", type=int, default=5, help="closed leads a feature needs to be refit")
    cb.add_argument("--write", metavar="PATH", help="write the calibrated icp.json here")

    sub.add_parser("report", help="funnel + distribution report")

    v = sub.add_parser("verify", help="check email deliverability (valid/risky/invalid)")
    v.add_argument("emails", nargs="+")

    ac = sub.add_parser("accounts", help="leads rolled up by company domain")
    ac.add_argument("--limit", type=int, default=20)

    ex = sub.add_parser("export", help="CRM-ready CSV to stdout")
    ex.add_argument("--tier")
    ex.add_argument("--format", choices=sorted(crm.MAPPINGS), default="basic")

    sg = sub.add_parser("signals", help="load intent signals CSV (email,signal,at)")
    sg.add_argument("csv")

    su = sub.add_parser("suppress", help="add emails or domains to the do-not-contact list")
    su.add_argument("values", nargs="*")
    su.add_argument("--reason", default="manual")
    su.add_argument("--list", action="store_true", help="print the suppression list")

    un = sub.add_parser("unsubscribe", help="suppress an email, cancel its touches, mark it lost")
    un.add_argument("email")

    rp = sub.add_parser("reply", help="classify an inbound reply and update the lead")
    rp.add_argument("email")
    rp.add_argument("text", help="reply body, or - to read stdin")

    sub.add_parser("experiment", help="A/B subject-line results with a z-test")

    ob = sub.add_parser("outbox", help="send due email touches (SMTP_* env) or write .eml files")
    ob.add_argument("--date", default=date.today().isoformat())
    ob.add_argument("--dry-run", action="store_true", help="write .eml files instead of sending")
    ob.add_argument("--out", default="outbox", help="dry-run output directory")
    ob.add_argument("--team", help="team config (default gtm/config/team.json or $GTM_CONFIG_DIR)")

    nt = sub.add_parser("notify", help="Slack alert for new tier-A leads (prints only, unless --send)")
    nt.add_argument("--send", action="store_true", help="post to $SLACK_WEBHOOK_URL and mark leads notified")
    nt.add_argument("--limit", type=int, default=20)

    sl = sub.add_parser("sla", help="time to first touch vs per-tier SLA (team.json sla_hours)")
    sl.add_argument("--now", type=datetime.fromisoformat, help="evaluate as of this time (UTC; default now)")
    sl.add_argument("--team", help="team config (default gtm/config/team.json or $GTM_CONFIG_DIR)")
    sl.add_argument("--backfill", action="store_true",
                    help="estimate a start time for leads imported before 0.3.0 so they are tracked")

    sub.add_parser("forecast", help="weighted pipeline per owner (stage prob x ACV)")

    dg = sub.add_parser("digest", help="per-rep markdown daily digest")
    dg.add_argument("--date", default=date.today().isoformat())
    dg.add_argument("--rep", help="print one rep's digest instead of writing all")
    dg.add_argument("--out", default="digests")

    sv = sub.add_parser("serve", help="JSON API + dashboard (GTM_API_TOKEN enables auth)")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)

    a = p.parse_args(argv)
    if a.cmd == "serve":
        from . import web
        return web.serve(a.db, a.host, a.port)
    store = Store(a.db)
    try:
        if a.cmd == "run":
            leads, stats = pipeline.run(a.csv, store, a.config, a.start, a.asof)
            print(f"rows={stats['rows']} kept={stats['kept']} invalid={stats['invalid']} "
                  f"dupes={stats['duplicates']}+{stats['person_dupes']} undeliverable={stats['undeliverable']} "
                  f"blocked={stats['blocked']} touches={stats['touches']}")
        elif a.cmd == "leads":
            for row in store.leads(a.tier)[: a.limit]:
                print(f"{row['score']:>3} {row['tier']}  {row['email']:<32} {row['owner']}")
        elif a.cmd == "today":
            for x in store.open_touches(a.date):
                print(f"{x['date']} {x['channel']:<8} {x['email']:<32} {x['subject']}")
        elif a.cmd == "stage":
            try:
                store.set_stage(a.email, a.stage)
            except KeyError:
                sys.exit(f"stage: no lead {a.email!r} (import it with `gtm run` first)")
            print(f"{a.email} -> {a.stage}")
        elif a.cmd == "outcomes":
            n = dict.fromkeys(("updated", "unknown_lead", "bad_stage"), 0)
            with open(a.csv, newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    stage = (row.get("stage") or "").strip().lower()
                    if stage not in STAGES:
                        n["bad_stage"] += 1
                        continue
                    try:
                        store.set_stage((row.get("email") or "").strip(), stage)
                        n["updated"] += 1
                    except KeyError:
                        n["unknown_lead"] += 1
            print(" ".join(f"{k}={v}" for k, v in n.items()))
        elif a.cmd == "calibrate":
            try:
                res = calibrate.calibrate(store.leads(), load_config(a.config), a.min_support)
            except ValueError as e:
                sys.exit(f"calibrate: {e}")
            print(calibrate.render(res))
            if a.write:
                calibrate.write(res, a.write)
                print(f"\nwrote {a.write}; apply with: gtm run CSV --config {a.write}")
        elif a.cmd == "signals":
            rows, skipped = intent.load_csv(a.csv)
            print(f"signals loaded={store.add_signals(rows)} skipped={skipped} (re-run `gtm run` to rescore)")
        elif a.cmd == "suppress":
            for val in a.values:
                store.suppress(val, a.reason)
            if a.list or not a.values:
                print("\n".join(sorted(store.suppressed())))
        elif a.cmd == "unsubscribe":
            compliance.unsubscribe(store, a.email)
            print(f"{a.email} unsubscribed")
        elif a.cmd == "reply":
            label, note = replies.apply(store, a.email, sys.stdin.read() if a.text == "-" else a.text)
            print(f"{a.email}: {label} -> {note}")
        elif a.cmd == "experiment":
            print(experiments.render(experiments.results(store.leads())))
        elif a.cmd == "outbox":
            try:
                stats = outbox.send_due(store, a.date, load_team(a.team), a.out if a.dry_run else None)
            except (RuntimeError, OSError) as e:  # missing config, SMTP down/auth failed
                sys.exit(f"outbox: {e}")
            print(" ".join(f"{k}={v}" for k, v in stats.items()) + (f"  (dry run -> {a.out}/{a.date}/)" if a.dry_run else ""))
        elif a.cmd == "notify":
            url = os.environ.get("SLACK_WEBHOOK_URL") if a.send else None
            if a.send and not url:
                sys.exit("notify: SLACK_WEBHOOK_URL not set (drop --send for a dry run)")
            try:
                body, sent = notify.run(store, url, a.limit)
            except (URLError, OSError) as e:
                sys.exit(f"notify: webhook failed: {e}")
            if body is None:
                print("notify: no new tier-A leads")
            else:
                print(body["text"] if sent else json.dumps(body, indent=2))
                print("-- sent to Slack" if sent else "-- dry run: nothing sent or recorded (use --send)")
        elif a.cmd == "sla":
            if a.backfill:
                print(f"backfilled created events for {store.backfill_created()} leads (estimated)\n")
            print(sla.render(sla.report(store, load_team(a.team), a.now)))
        elif a.cmd == "forecast":
            print(forecast.render(store.leads()))
        elif a.cmd == "digest":
            if a.rep:
                print(digest.render(store, a.rep, a.date))
            else:
                for path in digest.write_all(store, a.date, a.out):
                    print(path)
        elif a.cmd == "verify":
            for e in a.emails:
                status, why = verify(e)
                print(f"{status:<8} {e}  {why}".rstrip())
        elif a.cmd == "report":
            print(analytics.render(store.leads(), store.peak_stages()))
        elif a.cmd == "accounts":
            print(accounts.render(accounts.rollup(store.leads()), a.limit))
        elif a.cmd == "export":
            crm.export(store.leads(a.tier), a.format, sys.stdout)
    except FileNotFoundError as e:  # a CSV or --config/--team path that doesn't exist
        sys.exit(f"{a.cmd}: no such file: {e.filename}")
    finally:
        store.db.close()


if __name__ == "__main__":
    main()
