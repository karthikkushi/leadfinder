"""Finder agent 1: Overture Maps places (free open data from Meta, Microsoft, Foursquare and others).

Reads only the part of the worldwide file that covers the city box, straight from the public S3 bucket.
"""
import functools
import logging
import re

import duckdb
import httpx

from ..classify import format_phone, initial_status, is_chain_url, link_kind, score, site_key
from ..config import CATEGORIES, NAME_HINTS

log = logging.getLogger(__name__)
FALLBACK_RELEASE = "2026-09-23.1"


@functools.cache
def latest_release() -> str:
    try:
        return httpx.get("https://stac.overturemaps.org/catalog.json", timeout=20).json()["latest"]
    except Exception as e:  # catalogue down: use the last release we know
        log.warning("Overture catalogue unavailable (%s), using %s", e, FALLBACK_RELEASE)
        return FALLBACK_RELEASE


# Places whose own category is this vague get their category from their name when it says more.
BROAD = {"shopping", "fashion_and_apparel_store", "specialty_store", "health_care", "outpatient_care_facility",
         "personal_or_beauty_service", "food_and_beverage_store", "hardware_home_and_garden_store", "home_service",
         "professional_service", "lifestyle_services", "services_and_business", "retail"}

_con = None
_loaded: dict[tuple, str] = {}  # city box -> temp table, so several categories for one city load it once


def _connection():
    global _con
    if _con is None:
        _con = duckdb.connect()
        _con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
    return _con


def _load_area(bbox) -> str:
    if bbox in _loaded:
        return _loaded[bbox]
    s, w, n, e = bbox
    table = f"area_{len(_loaded)}"
    path = f"s3://overturemaps-us-west-2/release/{latest_release()}/theme=places/type=place/*"
    con = _connection()
    con.execute(f"""
        CREATE TEMP TABLE {table} AS
        SELECT id, names.primary AS name, taxonomy.primary AS tprimary, taxonomy.hierarchy AS hier,
               confidence, websites, socials, phones, emails, addresses[1] AS addr, operating_status,
               brand.names.primary AS brand, bbox.xmin AS lon, bbox.ymin AS lat,
               lower(regexp_replace(names.primary, '[^A-Za-z0-9]+', '', 'g')) AS name_key
          FROM read_parquet('{path}')
         WHERE bbox.xmin BETWEEN {w} AND {e} AND bbox.ymin BETWEEN {s} AND {n}
           AND names.primary IS NOT NULL""")
    _loaded[bbox] = table
    return table


def _category_for(hier: list[str] | None, tprimary: str | None, wanted: set[str]) -> str | None:
    # Most specific level first, so a jewellery shop (fashion_and_apparel_store > jewelry_store) is jewellery.
    for level in reversed(hier or ([tprimary] if tprimary else [])):
        for key, _label, tokens, _osm, _w in CATEGORIES:
            if key in wanted and level in tokens:
                return key
    if tprimary == "shopping" and "general_shop" in wanted:
        return "general_shop"
    return None


def _name_hint(name: str) -> str | None:
    low = name.lower()
    return next((cat for rx, cat in NAME_HINTS if re.search(rx, low)), None)


def fetch(bbox, categories: list[str], country: str, city: str) -> list[dict]:
    """Callable, independent (non-chain) businesses in the box for the given categories."""
    table = _load_area(bbox)
    con = _connection()
    wanted = set(categories)
    tokens = sorted({t for c in CATEGORIES if c[0] in wanted for t in c[2] if not t.startswith("=")})
    exact = ["shopping"]  # generic shops are always read; their names decide the category

    # Chain detection: the same name many times in the city, or one website shared by many places.
    name_counts = dict(con.execute(f"SELECT name_key, count(*) FROM {table} GROUP BY 1").fetchall())
    host_stats = {}
    for w, places, names in con.execute(f"""
            SELECT w, count(*), count(DISTINCT name_key) FROM (SELECT name_key, unnest(websites) AS w FROM {table})
             GROUP BY 1""").fetchall():
        h = site_key(w)
        p0, n0 = host_stats.get(h, (0, 0))
        host_stats[h] = (p0 + places, n0 + names)

    rows = con.execute(f"""
        SELECT id, name, tprimary, hier, confidence, websites, socials, phones, emails, addr, operating_status,
               brand, lon, lat, name_key
          FROM {table}
         WHERE list_has_any(hier, ?::VARCHAR[]) OR tprimary IN (SELECT unnest(?::VARCHAR[]))""",
                       [tokens, exact]).fetchall()

    out, skipped_chain = [], 0
    for (pid, name, tprimary, hier, conf, websites, socials, phones, emails, addr, status, brand, lon, lat,
         nkey) in rows:
        if status in ("permanently_closed", "temporarily_closed"):
            continue
        addr = addr or {}
        if addr.get("country") and addr["country"].upper() != country:
            continue
        category = _category_for(hier, tprimary, wanted)
        if category in (None, "general_shop") or tprimary in BROAD:
            hinted = _name_hint(name)
            if hinted in wanted:
                category = hinted
        if not category:
            continue
        websites = [w for w in (websites or []) if w]
        socials = [s for s in (socials or []) if s]
        own_hosts = [site_key(w) for w in websites if link_kind(w) == "own"]
        chain_site = any(host_stats.get(h, (0, 0))[0] >= 6 or host_stats.get(h, (0, 0))[1] >= 3 for h in own_hosts)
        if (brand or chain_site or any(is_chain_url(w) for w in websites)
                or (name_counts.get(nkey, 0) >= 4 and own_hosts)):
            skipped_chain += 1
            continue
        phone, phone_intl = None, None
        for p in phones or []:
            phone, phone_intl = format_phone(p, country)
            if phone_intl:
                break
        if not phone_intl:
            continue  # nobody to call
        web_status, own_site = initial_status(websites, socials, name)
        email = (emails or [None])[0]
        priority, sc = score(web_status, category, confidence=conf, has_email=bool(email))
        out.append({
            "source_key": f"ov:{pid}", "sources": ["overture"], "name": name.strip(), "category": category,
            "subcategory": tprimary, "country": country, "city": city, "locality": addr.get("locality"),
            "address": addr.get("freeform"), "lat": lat, "lon": lon, "phone": phone, "phone_intl": phone_intl,
            "email": email, "website": own_site,
            "socials": sorted(set(socials + [w for w in websites if link_kind(w) in ("social", "directory")]))[:6],
            "website_status": web_status, "issues": [], "priority": priority, "score": sc,
            "_confidence": conf, "_name_key": nkey,
        })
    log.info("Overture: %d matching places, %d chains skipped, %d callable leads", len(rows), skipped_chain, len(out))
    return out
