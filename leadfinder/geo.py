"""Turn a city name into a map box using OpenStreetMap's free Nominatim service."""
import functools

import httpx

from .config import COUNTRIES

UA = {"User-Agent": "leadfinder/1.0 (small-business lead research tool)"}
MAX_SPAN = 0.9  # degrees (~100 km); bigger boxes (whole states/emirates) are trimmed around the centre


@functools.cache
def city_bbox(city: str, country: str) -> tuple[float, float, float, float]:
    """(south, west, north, east) for a city."""
    country_name = COUNTRIES.get(country, (country, []))[0]
    r = httpx.get("https://nominatim.openstreetmap.org/search",
                  params={"q": f"{city}, {country_name}", "format": "json", "limit": 1,
                          "countrycodes": country.lower(), "featureType": "settlement"},
                  headers=UA, timeout=30)
    r.raise_for_status()
    hits = r.json()
    if not hits:
        r = httpx.get("https://nominatim.openstreetmap.org/search",
                      params={"q": f"{city}, {country_name}", "format": "json", "limit": 1,
                              "countrycodes": country.lower()}, headers=UA, timeout=30)
        hits = r.json()
    if not hits:
        raise ValueError(f"Couldn't find '{city}' in {country_name} on the map")
    s, n, w, e = map(float, hits[0]["boundingbox"])
    lat, lon = float(hits[0]["lat"]), float(hits[0]["lon"])
    if n - s > MAX_SPAN:
        s, n = lat - MAX_SPAN / 2, lat + MAX_SPAN / 2
    if e - w > MAX_SPAN:
        w, e = lon - MAX_SPAN / 2, lon + MAX_SPAN / 2
    return s, w, n, e
