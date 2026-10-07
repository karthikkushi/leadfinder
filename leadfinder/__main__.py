"""python -m leadfinder worker [--minutes 20] [--wait]
python -m leadfinder queue Bengaluru --country IN [--category dentist]
python -m leadfinder audit https://example.com"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    (ROOT / "logs").mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(ROOT / "logs" / "worker.log", encoding="utf-8")])
    for noisy in ("httpx", "httpcore", "primp", "ddgs"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    p = argparse.ArgumentParser(prog="leadfinder")
    sub = p.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("worker", help="run the agents")
    w.add_argument("--minutes", type=float, default=20)
    w.add_argument("--wait", action="store_true", help="keep waiting for new jobs instead of stopping")
    w.add_argument("--plan", action="store_true", help="queue the next target city when the queue runs dry")
    e = sub.add_parser("email", help="send the morning lead email")
    e.add_argument("--since-hours", type=float, default=4)
    e.add_argument("--dry-run", action="store_true", help="write the email to logs/ without sending or marking")
    q = sub.add_parser("queue", help="add a search job")
    q.add_argument("city")
    q.add_argument("--country", default="IN")
    q.add_argument("--category", default="all")
    f = sub.add_parser("features", help="measure lead signals and re-score (all cities missing them)")
    f.add_argument("--city")
    f.add_argument("--country", default="IN")
    f.add_argument("--all", action="store_true", help="re-measure every city, not only new leads")
    sub.add_parser("recheck", help="re-check every shop marked 'no website' with the current rules")
    sub.add_parser("briefs", help="research today's hot leads and write their sales briefs")
    sub.add_parser("sent-today", help="print how many leads were emailed since midnight India time")
    a = sub.add_parser("audit", help="grade one website")
    a.add_argument("url")
    args = p.parse_args()

    if args.cmd == "worker":
        from .worker import run
        run(args.minutes, args.wait, args.plan)
    elif args.cmd == "email":
        from .report import send_morning_email
        send_morning_email(args.since_hours, args.dry_run)
    elif args.cmd == "queue":
        import httpx
        r = httpx.post(os.environ["SUPABASE_URL"] + "/rest/v1/rpc/app_queue_job",
                       headers={"apikey": os.environ["SUPABASE_KEY"]},
                       json={"p_code": os.environ["ADMIN_CODE"], "p_country": args.country, "p_city": args.city,
                             "p_category": args.category})
        print(r.text)
    elif args.cmd == "features":
        from .db import DB
        from .features import compute_city, compute_missing
        db = DB()
        n = compute_city(db, args.country, args.city) if args.city else compute_missing(db, not args.all)
        print(f"scored {n} leads")
    elif args.cmd == "recheck":
        from .db import DB
        from .verify import Searcher, check
        db, searcher = DB(), Searcher()
        leads = db.call("worker_no_website_checked", p_limit=2000) or []
        fixed, kept, retry = 0, 0, []
        for i, lead in enumerate(leads, 1):
            r = check(lead, searcher)
            if r is None:
                retry.append(lead["id"])
                continue
            db.save_checks([r])
            if r["priority"] != 1:
                fixed += 1
                logging.info("Found a website for %s: %s (%s)", lead["name"], r["website"], r["website_status"])
            else:
                kept += 1
            if i % 20 == 0:
                logging.info("Re-checked %d of %d", i, len(leads))
        if retry:
            db.call("worker_reset_checks", p_ids=retry)
        print(f"re-checked {len(leads)}: {fixed} actually have a website, {kept} confirmed no website, "
              f"{len(retry)} sent back to the queue (search unavailable)")
    elif args.cmd == "briefs":
        from .brief import write_brief
        from .db import DB
        from .research import research
        from .verify import Searcher
        db, searcher, tried = DB(), Searcher(), set()
        countries = [c.strip().upper() for c in os.environ.get("REPORT_COUNTRIES", "IN").split(",") if c.strip()]
        while True:  # a skipped chain outlet gets replaced by a new pick, which needs a brief too
            leads = [l for l in db.call("worker_research_leads", p_countries=countries or ["IN"]) or [] if l["id"] not in tried]
            if not leads:
                break
            for lead in leads:
                tried.add(lead["id"])
                try:
                    facts = research(db, lead, searcher)
                    b = write_brief(facts)
                except Exception:
                    logging.exception("Brief for %s failed", lead["name"])
                    continue
                if not b["ok"]:  # AI unavailable: the app falls back to the standard script
                    logging.warning("No brief for %s: %s", lead["name"], b.get("error"))
                    continue
                db.call("worker_save_brief", p_id=lead["id"], p_research=facts,
                        p_brief=b["brief"] | {"facts": b["facts"], "unresolved": b["unresolved"]})
                logging.info("Brief for %s: call %s (%d rounds)", lead["name"], b["brief"].get("call"), b["rounds"])
    elif args.cmd == "sent-today":
        from .db import DB
        countries = [c.strip().upper() for c in os.environ.get("REPORT_COUNTRIES", "IN").split(",") if c.strip()]
        print(DB().call("worker_sent_today", p_countries=countries or None))
    elif args.cmd == "audit":
        from .verify import audit
        print(json.dumps(audit(args.url), indent=2))


if __name__ == "__main__":
    main()
