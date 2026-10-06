"""Coordinator: takes search jobs from the database queue, runs the finder agents, then keeps the website
checker busy. Everything is saved as it goes, so a stopped run just carries on next time."""
import itertools
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor

from . import features, geo, verify
from .config import CATEGORY_KEYS, DAILY_TARGETS
from .db import DB
from .merge import merge
from .sources import osm, overture

log = logging.getLogger("leadfinder")


def find_leads(db: DB, job: dict) -> tuple[int, int, str]:
    city, country, category = job["city"], job["country"], job["category"]
    categories = CATEGORY_KEYS if category == "all" else [category]
    log.info("Job %s: %s, %s - %s", job["id"], city, country, category)
    bbox = geo.city_bbox(city, country)
    found = overture.fetch(bbox, categories, country, city)
    extra = []
    if country != "IN":  # in India OpenStreetMap adds very few phone numbers; abroad it's strong
        try:
            extra = osm.fetch(bbox, categories, country, city)
        except Exception as e:
            log.warning("OpenStreetMap step failed: %s", e)
    leads = merge(found, extra)
    res = db.upsert_leads(leads)
    features.compute_city(db, country, city)  # score the new shops right away
    p1 = sum(1 for l in leads if l["priority"] == 1)
    msg = (f"{len(leads)} shops with a phone number: {p1} without a real website, "
           f"{len(leads) - p1} with a website to check. {res['inserted']} new.")
    log.info(msg)
    return len(leads), res["inserted"], msg


def _safe_check(lead, searcher):
    try:
        return verify.check(lead, searcher)
    except Exception as e:
        log.warning("Check failed for %s: %s", lead.get("name"), e)
        return None


# Which country each round of checks works on, e.g. "IN,IN,US" = two rounds India, one round USA.
CHECK_MIX = itertools.cycle([c.strip().upper() for c in os.environ.get("CHECK_MIX", "IN,IN,US").split(",") if c.strip()])


def check_some(db: DB, searcher: verify.Searcher, deadline: float) -> int:
    country = next(CHECK_MIX)
    no_site = db.next_checks(12, 1, country)    # needs web searches: done one by one
    has_site = db.next_checks(32, 2, country)   # just opens the website: done in parallel
    if not no_site and not has_site:  # nothing left for that country: take any
        no_site, has_site = db.next_checks(12, 1), db.next_checks(32, 2)
    if not no_site and not has_site:
        return 0
    results = []
    with ThreadPoolExecutor(8) as pool:
        futures = [pool.submit(_safe_check, lead, searcher) for lead in has_site]
        for lead in no_site:
            if time.monotonic() > deadline:
                break
            r = _safe_check(lead, searcher)
            if r:
                results.append(r)
        results += [r for f in futures if (r := f.result())]
    db.save_checks(results)
    p1 = sum(1 for r in results if r["priority"] == 1)
    p2 = sum(1 for r in results if r["priority"] == 2)
    log.info("Checked %d leads: %d no website, %d website needs work, %d good website (skipped)",
             len(results), p1, p2, len(results) - p1 - p2)
    return len(results)


def run(minutes: float, wait: bool = False, plan: bool = False):
    db = DB()
    searcher = verify.Searcher()
    deadline = time.monotonic() + minutes * 60
    log.info("Agents started for up to %.0f minutes%s", minutes, " (waiting for new jobs when idle)" if wait else "")
    learned = db.call("worker_refresh_learning")
    rescored = 0
    for _ in range(100):  # re-score shops whose type's learned adjustment changed, a batch at a time
        n = db.call("worker_rescore_some", p_limit=1500) or 0
        rescored += n
        if not n:
            break
    log.info("Learning from calls: %s shop types updated, %d shops re-scored", learned.get("categories"), rescored)
    try:
        features.compute_missing(db)  # any shops that haven't been scored yet
    except Exception:
        log.exception("Scoring step failed; continuing with checks")
    while time.monotonic() < deadline - 45:
        if plan:
            planned = db.plan(DAILY_TARGETS)
            if planned.get("queued"):
                log.info("Planner queued %s, %s", planned["city"], planned["country"])
        job = db.claim_job()
        if job:
            try:
                found, added, msg = find_leads(db, job)
                db.finish_job(job["id"], "done", found, added, msg)
            except Exception as e:
                log.exception("Job %s failed", job["id"])
                db.finish_job(job["id"], "failed", 0, 0, f"{type(e).__name__}: {e}")
            continue
        if check_some(db, searcher, deadline - 30):
            continue
        if not wait:
            log.info("Nothing left to do")
            break
        time.sleep(60)
    db.call("worker_refresh_summary")  # the app's counters
    log.info("Agents stopped")
