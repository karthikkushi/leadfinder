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
    elif args.cmd == "sent-today":
        from .db import DB
        countries = [c.strip().upper() for c in os.environ.get("REPORT_COUNTRIES", "IN").split(",") if c.strip()]
        print(DB().call("worker_sent_today", p_countries=countries or None))
    elif args.cmd == "audit":
        from .verify import audit
        print(json.dumps(audit(args.url), indent=2))


if __name__ == "__main__":
    main()
