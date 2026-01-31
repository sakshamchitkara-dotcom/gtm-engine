import argparse
import csv
import sys
from datetime import date

from . import analytics, pipeline
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

    ex = sub.add_parser("export", help="CRM-ready CSV to stdout")
    ex.add_argument("--tier")

    a = p.parse_args(argv)
    store = Store(a.db)

    if a.cmd == "run":
        leads, stats = pipeline.run(a.csv, store, a.config, a.start)
        print(f"rows={stats['rows']} kept={stats['kept']} invalid={stats['invalid']} "
              f"dupes={stats['duplicates']}+{stats['person_dupes']} undeliverable={stats['undeliverable']} touches={stats['touches']}")
    elif a.cmd == "leads":
        for row in store.leads(a.tier)[: a.limit]:
            print(f"{row['score']:>3} {row['tier']}  {row['email']:<32} {row['owner']}")
    elif a.cmd == "today":
        for x in store.touches_due(a.date):
            print(f"{x['date']} {x['channel']:<8} {x['email']:<32} {x['subject']}")
    elif a.cmd == "stage":
        store.set_stage(a.email, a.stage)
        print(f"{a.email} -> {a.stage}")
    elif a.cmd == "verify":
        for e in a.emails:
            status, why = verify(e)
            print(f"{status:<8} {e}  {why}".rstrip())
    elif a.cmd == "report":
        print(analytics.render(store.leads()))
    elif a.cmd == "export":
        w = csv.writer(sys.stdout)
        w.writerow(["email", "score", "tier", "owner", "stage"])
        for row in store.leads(a.tier):
            w.writerow([row["email"], row["score"], row["tier"], row["owner"], row["stage"]])


if __name__ == "__main__":
    main()
