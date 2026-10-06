"""Feature agent: measures the signals that say how good a lead is, from the map data around each shop.

- rivals_nearby / rivals_with_site: same-type shops within 1 km, and how many of them have a website
- brands_nearby: chain/brand outlets within 1 km (a busy, well-off commercial area)
- confidence: how sure the map data is that the shop exists and still trades
- phone_type: mobile (usually the owner, WhatsApp works), landline, toll-free (a big company)
- branches: how many places in the city share the shop's name (2-3 = a growing local business)
- has_instagram: the owner already uses social media for business

The score itself is computed in the database (private.score_lead), so every update re-scores the lead.
"""
import functools
import logging
import math
from collections import Counter, defaultdict

import phonenumbers

from . import geo
from .classify import host_of, link_kind, name_key
from .config import CATEGORY_KEYS
from .db import DB
from .sources import overture

log = logging.getLogger("leadfinder")
RADIUS_M = 1000
CELL = 0.01  # degrees, ~1.1 km grid for neighbour lookups
PHONE_TYPES = {
    phonenumbers.PhoneNumberType.MOBILE: "mobile",
    phonenumbers.PhoneNumberType.FIXED_LINE: "fixed",
    phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "fixed_or_mobile",
    phonenumbers.PhoneNumberType.TOLL_FREE: "toll_free",
}


@functools.lru_cache(maxsize=200_000)
def _host_kind(host: str) -> str:
    return link_kind("http://" + host)


def _has_site(websites) -> bool:
    return any(_host_kind(host_of(w)) in ("own", "builder") for w in websites or [] if host_of(w))


def phone_type(e164: str | None, country: str) -> str | None:
    if not e164:
        return None
    try:
        return PHONE_TYPES.get(phonenumbers.number_type(phonenumbers.parse(e164, country)), "other")
    except phonenumbers.NumberParseException:
        return None


def _cell(lat, lon):
    return math.floor(lat / CELL), math.floor(lon / CELL)


def _near(grid, lat, lon):
    cx, cy = _cell(lat, lon)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            yield from grid.get((cx + dx, cy + dy), ())


def _metres(lat1, lon1, lat2, lon2) -> float:
    return math.hypot((lat2 - lat1) * 111_000, (lon2 - lon1) * 111_000 * math.cos(math.radians(lat1)))


def compute_city(db: DB, country: str, city: str) -> int:
    bbox = geo.city_bbox(city, country)
    table = overture._load_area(bbox)
    rows = overture._connection().execute(
        f"SELECT id, name, tprimary, hier, confidence, websites, brand, lat, lon, name_key FROM {table}").fetchall()
    wanted = set(CATEGORY_KEYS)
    by_type = defaultdict(list)   # cell -> (lat, lon, category, has_site, id)
    brands = defaultdict(list)    # cell -> (lat, lon)
    confidence, names = {}, Counter()
    for pid, name, tprimary, hier, conf, websites, brand, lat, lon, nkey in rows:
        confidence[f"ov:{pid}"] = conf
        names[nkey] += 1
        if brand:
            brands[_cell(lat, lon)].append((lat, lon))
        category = overture.categorise(name, hier, tprimary, wanted)
        if category:
            by_type[_cell(lat, lon)].append((lat, lon, category, _has_site(websites), f"ov:{pid}"))
    log.info("%s: %d places around the city measured", city, len(rows))

    done, after = 0, None
    while True:
        leads = db.call("worker_city_leads", p_country=country, p_city=city, p_after=after, p_limit=5000) or []
        if not leads:
            break
        after = leads[-1]["id"]
        out = []
        for l in leads:
            lat, lon = l.get("lat"), l.get("lon")
            rivals = with_site = brands_near = 0
            if lat is not None and lon is not None:
                for plat, plon, cat, has_site, pid in _near(by_type, lat, lon):
                    if cat == l["category"] and pid != l["source_key"] and _metres(lat, lon, plat, plon) <= RADIUS_M:
                        rivals += 1
                        with_site += has_site
                brands_near = sum(1 for blat, blon in _near(brands, lat, lon)
                                  if _metres(lat, lon, blat, blon) <= RADIUS_M)
            out.append({
                "id": l["id"], "confidence": confidence.get(l["source_key"]),
                "phone_type": phone_type(l.get("phone_intl"), country),
                "rivals_nearby": rivals, "rivals_with_site": with_site, "brands_nearby": brands_near,
                "has_instagram": any("instagram.com" in (s or "") for s in l.get("socials") or []),
                "branches": names.get(name_key(l["name"]), 1),
            })
        for i in range(0, len(out), 1000):
            db.call("worker_save_features", p_rows=out[i:i + 1000])
        done += len(out)
        log.info("%s: scored %d leads", city, done)
    return done


def compute_missing(db: DB, only_missing: bool = True) -> int:
    total = 0
    for place in db.call("worker_places") or []:
        if only_missing and not place["missing"]:
            continue
        total += compute_city(db, place["country"], place["city"])
    return total
