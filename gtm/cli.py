import argparse
import csv
import sys
from datetime import date, datetime

from . import accounts, analytics, compliance, digest, experiments, forecast, intent, outbox, pipeline, replies
from .routing import load_team
from .store import STAGES, Store
from .verify import verify


def main(argv=None):
    p = argparse.ArgumentParser(prog="gtm", description="GTM engineering pipeline")
    p.add_argument("--db", default="gtm.db")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="ingest, enrich, score, route and sequence a CSV")
    r.add_argument("csv")
    r.add_argument("--config")
    r.add_argument("--start", type=date.fromisoformat, help="cadence start date (YYYY-MM-DD)")
    r.add_argument("--asof", type=datetime.fromisoformat, help="intent decay reference time (default now)")

    ls = sub.add_parser("leads", help="list scored leads")
    ls.add_argument("--tier")
    ls.add_argument("--limit", type=int, default=20)

    t = sub.add_parser("today", help="touches due on/before a date")
    t.add_argument("--date", default=date.today().isoformat())

    st = sub.add_parser("stage", help="move a lead through the funnel")
    st.add_argument("email")
    st.add_argument("stage", choices=STAGES)

    sub.add_parser("report", help="funnel + distribution report")

    v = sub.add_parser("verify", help="check email deliverability (valid/risky/invalid)")
    v.add_argument("emails", nargs="+")

    ac = sub.add_parser("accounts", help="leads rolled up by company domain")
    ac.add_argument("--limit", type=int, default=20)

    ex = sub.add_parser("export", help="CRM-ready CSV to stdout")
    ex.add_argument("--tier")

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
    ob.add_argument("--team", help="team config (default config/team.json)")

    sub.add_parser("forecast", help="weighted pipeline per owner (stage prob x ACV)")

    dg = sub.add_parser("digest", help="per-rep markdown daily digest")
    dg.add_argument("--date", default=date.today().isoformat())
    dg.add_argument("--rep", help="print one rep's digest instead of writing all")
    dg.add_argument("--out", default="digests")

    a = p.parse_args(argv)
    store = Store(a.db)

    if a.cmd == "run":
        leads, stats = pipeline.run(a.csv, store, a.config, a.start, a.asof)
        print(f"rows={stats['rows']} kept={stats['kept']} invalid={stats['invalid']} "
              f"dupes={stats['duplicates']}+{stats['person_dupes']} undeliverable={stats['undeliverable']} "
              f"blocked={stats['blocked']} touches={stats['touches']}")
    elif a.cmd == "leads":
        for row in store.leads(a.tier)[: a.limit]:
            print(f"{row['score']:>3} {row['tier']}  {row['email']:<32} {row['owner']}")
    elif a.cmd == "today":
        for x in store.touches_due(a.date):
            print(f"{x['date']} {x['channel']:<8} {x['email']:<32} {x['subject']}")
    elif a.cmd == "stage":
        store.set_stage(a.email, a.stage)
        print(f"{a.email} -> {a.stage}")
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
        stats = outbox.send_due(store, a.date, load_team(a.team), a.out if a.dry_run else None)
        print(" ".join(f"{k}={v}" for k, v in stats.items()) + (f"  (dry run -> {a.out}/{a.date}/)" if a.dry_run else ""))
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
        print(analytics.render(store.leads()))
    elif a.cmd == "accounts":
        print(accounts.render(accounts.rollup(store.leads()), a.limit))
    elif a.cmd == "export":
        w = csv.writer(sys.stdout)
        w.writerow(["email", "score", "tier", "owner", "stage"])
        for row in store.leads(a.tier):
            w.writerow([row["email"], row["score"], row["tier"], row["owner"], row["stage"]])


if __name__ == "__main__":
    main()
