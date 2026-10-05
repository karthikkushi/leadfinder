"""Merger agent: the same shop found by several sources becomes one lead."""
import math
from collections import defaultdict

from rapidfuzz import fuzz

from .classify import initial_status, score

CELL = 0.002  # ~200 m grid for nearby lookups


def _cell(lat, lon):
    return (math.floor(lat / CELL), math.floor(lon / CELL))


def _metres(a, b) -> float:
    dlat = (a["lat"] - b["lat"]) * 111_000
    dlon = (a["lon"] - b["lon"]) * 111_000 * math.cos(math.radians(a["lat"]))
    return math.hypot(dlat, dlon)


def _same(a, b) -> bool:
    if a["phone_intl"] and a["phone_intl"] == b["phone_intl"]:
        return True
    if a["lat"] is None or b["lat"] is None or _metres(a, b) > 150:
        return False
    return fuzz.token_set_ratio(a["name"].lower(), b["name"].lower()) >= 88


def _absorb(main: dict, extra: dict):
    main["sources"] = sorted(set(main["sources"]) | set(extra["sources"]))
    for f in ("phone", "phone_intl", "email", "locality", "address"):
        if not main.get(f) and extra.get(f):
            main[f] = extra[f]
    main["socials"] = sorted(set(main["socials"]) | set(extra["socials"]))[:8]
    # If any source knows a real website, the shop has one.
    if extra.get("website") and main["website_status"] in ("none", "social_only", "directory_only", "dead"):
        websites = [extra["website"]]
        status, own = initial_status(websites, main["socials"], main["name"])
        main["website"], main["website_status"] = own, status
    main["priority"], main["score"] = score(main["website_status"], main["category"],
                                            confidence=main.get("_confidence"), has_email=bool(main.get("email")))


def merge(primary: list[dict], others: list[dict]) -> list[dict]:
    grid = defaultdict(list)
    by_phone = {}
    for lead in primary:
        if lead["lat"] is not None:
            grid[_cell(lead["lat"], lead["lon"])].append(lead)
        if lead["phone_intl"]:
            by_phone.setdefault(lead["phone_intl"], lead)

    merged = list(primary)
    for o in others:
        match = by_phone.get(o["phone_intl"]) if o["phone_intl"] else None
        if match is None and o["lat"] is not None:
            cx, cy = _cell(o["lat"], o["lon"])
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for cand in grid.get((cx + dx, cy + dy), []):
                        if _same(cand, o):
                            match = cand
                            break
        if match:
            _absorb(match, o)
        elif o["phone_intl"]:
            merged.append(o)
            if o["lat"] is not None:
                grid[_cell(o["lat"], o["lon"])].append(o)
            by_phone[o["phone_intl"]] = o

    # One lead per phone number: keep the one with the most information.
    best = {}
    for lead in merged:
        key = lead["phone_intl"]
        cur = best.get(key)
        rank = (bool(lead["website"]), len(lead["sources"]), bool(lead["address"]), len(lead["name"]))
        if cur is None or rank > cur[0]:
            if cur is not None:
                _absorb(lead, cur[1])
            best[key] = (rank, lead)
        else:
            _absorb(cur[1], lead)
    return [lead for _rank, lead in best.values()]
