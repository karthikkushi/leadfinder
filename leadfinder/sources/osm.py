"""Finder agent 2: OpenStreetMap via the free Overpass API.

Strong in the UK, Ireland, Italy and Australia. It also fills in websites the Overture data is missing,
which stops the agents from calling a shop that already has a site.
"""
import logging
import re
import time

import httpx

from ..classify import format_phone, initial_status, link_kind, name_key, score
from ..config import CATEGORIES

log = logging.getLogger(__name__)
ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter"]
UA = {"User-Agent": "leadfinder/1.0 (small-business lead research tool)"}


def _query(bbox, categories: list[str]) -> str:
    # One statement per tag (shop, amenity, ...) - many small statements make the servers time out.
    s, w, n, e = bbox
    by_tag = {}
    for key, _l, _t, osm, _w in CATEGORIES:
        if key in categories:
            for tag, regex in osm:
                by_tag.setdefault(tag, []).append(regex)
    parts = "".join(f'nwr["{tag}"~"^({"|".join(rx)})$"]["name"]({s},{w},{n},{e});' for tag, rx in by_tag.items())
    return f"[out:json][timeout:90];({parts});out center tags;"


def _category_for(tags: dict, categories: list[str]) -> str | None:
    for key, _l, _t, osm, _w in CATEGORIES:
        if key in categories and any(re.fullmatch(regex, tags.get(tag, "")) for tag, regex in osm):
            return key
    return None


TILE = 0.2  # degrees; big cities are asked for in squares this size so the free servers don't time out


def _tiles(bbox):
    s, w, n, e = bbox
    lat = s
    while lat < n:
        lon = w
        while lon < e:
            yield (lat, lon, min(lat + TILE, n), min(lon + TILE, e))
            lon += TILE
        lat += TILE


def _ask(query: str) -> list | None:
    for url in ENDPOINTS:
        try:
            r = httpx.post(url, data={"data": query}, headers=UA, timeout=100)
            if r.status_code == 200:
                return r.json().get("elements", [])
            log.info("Overpass %s answered %s", url, r.status_code)
        except Exception as e:
            log.info("Overpass %s failed: %s", url, e)
        time.sleep(3)
    return None


def fetch(bbox, categories: list[str], country: str, city: str, budget_s: float = 240) -> list[dict]:
    elements, failed, seen = [], 0, set()
    tiles = list(_tiles(bbox))
    stop_at = time.monotonic() + budget_s
    for tile in tiles:
        if time.monotonic() > stop_at:
            failed += 1
            continue
        got = _ask(_query(tile, categories))
        if got is None:
            failed += 1
            if failed >= 3 and not elements:  # nothing has worked: the servers are down
                break
            continue
        for el in got:
            if (el["type"], el["id"]) not in seen:
                seen.add((el["type"], el["id"]))
                elements.append(el)
    if failed:
        log.warning("OpenStreetMap: %d of %d map squares unavailable", failed, len(tiles))

    out = []
    for el in elements:
        tags = el.get("tags", {})
        if tags.get("brand") or tags.get("brand:wikidata") or tags.get("disused:shop"):
            continue
        category = _category_for(tags, categories)
        if not category:
            continue
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        raw_phone = tags.get("phone") or tags.get("contact:phone") or tags.get("contact:mobile") or tags.get("mobile")
        phone, phone_intl = format_phone(raw_phone, country)
        websites = [tags[k] for k in ("website", "contact:website", "url") if tags.get(k)]
        socials = [tags[k] for k in ("contact:facebook", "contact:instagram", "facebook", "instagram")
                   if tags.get(k, "").startswith("http")]
        web_status, own_site = initial_status(websites, socials, tags["name"])
        email = tags.get("email") or tags.get("contact:email")
        street = " ".join(x for x in (tags.get("addr:housenumber"), tags.get("addr:street")) if x)
        address = ", ".join(x for x in (street, tags.get("addr:suburb"), tags.get("addr:city"),
                                        tags.get("addr:postcode")) if x) or None
        priority, sc = score(web_status, category, has_email=bool(email))
        out.append({
            "source_key": f"osm:{el['type']}/{el['id']}", "sources": ["openstreetmap"], "name": tags["name"].strip(),
            "category": category, "subcategory": tags.get("shop") or tags.get("amenity") or tags.get("healthcare")
            or tags.get("craft") or tags.get("leisure"), "country": country, "city": city,
            "locality": tags.get("addr:suburb") or tags.get("addr:city"), "address": address, "lat": lat, "lon": lon,
            "phone": phone, "phone_intl": phone_intl, "email": email, "website": own_site,
            "socials": sorted(set(socials + [w for w in websites if link_kind(w) in ("social", "directory")])),
            "website_status": web_status, "issues": [], "priority": priority, "score": sc,
            "_confidence": None, "_name_key": name_key(tags["name"]),
        })
    log.info("OpenStreetMap: %d matching places", len(out))
    return out
