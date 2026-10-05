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


def fetch(bbox, categories: list[str], country: str, city: str) -> list[dict]:
    query = _query(bbox, categories)
    data = None
    for url in ENDPOINTS:
        try:
            r = httpx.post(url, data={"data": query}, headers=UA, timeout=110)
            if r.status_code == 200:
                data = r.json()
                break
            log.warning("Overpass %s answered %s", url, r.status_code)
        except Exception as e:
            log.warning("Overpass %s failed: %s", url, e)
        time.sleep(3)
    if data is None:
        log.warning("OpenStreetMap unavailable right now, continuing with Overture only")
        return []

    out = []
    for el in data.get("elements", []):
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
