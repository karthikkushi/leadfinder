"""Sort links and phone numbers: own website, social page, directory listing, website builder."""
import re
from urllib.parse import urlparse

import phonenumbers
import tldextract
from rapidfuzz import fuzz

from .config import (BUILDER_SUFFIXES, CATEGORY_WEIGHT, DEAD_SUFFIXES, DIRECTORY_NAMES, FOR_SALE_NAMES, GENERIC_WORDS,
                     SOCIAL_DOMAINS)

_extract = tldextract.TLDExtract(suffix_list_urls=())  # bundled list, no network
CHAIN_URL = re.compile(r"utm_source=overture|store-?locator|/stores?/|/locations?/|store-details|storelocator|"
                       r"/branch(es)?/|/outlets?/|near-?me\.", re.I)


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if not url or " " in url:
        return None
    if not re.match(r"^[a-z][a-z0-9+.-]*://", url, re.I):
        url = "http://" + url
    return url


def host_of(url: str | None) -> str:
    url = normalize_url(url)
    if not url:
        return ""
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def site_key(url: str | None) -> str:
    """The part of the address that identifies one site: the registered domain, or the full host on builders."""
    host = host_of(url)
    if any(_ends_with(host, s) for s in BUILDER_SUFFIXES):
        return host
    parts = _extract(host)
    return f"{parts.domain}.{parts.suffix}" if parts.suffix else host


def path_depth(url: str | None) -> int:
    url = normalize_url(url)
    return len([p for p in urlparse(url).path.split("/") if p]) if url else 0


def _ends_with(host: str, suffix: str) -> bool:
    return host == suffix or host.endswith("." + suffix)


def link_kind(url: str | None) -> str:
    """'social', 'directory', 'dead', 'builder', 'own' or '' for an unusable link."""
    host = host_of(url)
    if not host or "." not in host:
        return ""
    if any(_ends_with(host, s) for s in DEAD_SUFFIXES):
        return "dead"
    if any(_ends_with(host, s) for s in BUILDER_SUFFIXES):
        return "builder"
    parts = _extract(host)
    registered = f"{parts.domain}.{parts.suffix}" if parts.suffix else parts.domain
    if registered in SOCIAL_DOMAINS or host in SOCIAL_DOMAINS:
        return "social"
    if parts.domain in FOR_SALE_NAMES:
        return "dead"
    if parts.domain in DIRECTORY_NAMES:
        return "directory"
    return "own"


def name_key(name: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def distinct_key(name: str | None) -> str:
    """The name without words every shop uses ('Sri', 'Dental', 'Clinic', ...)."""
    words = [w for w in re.findall(r"[a-z0-9]+", (name or "").lower()) if w not in GENERIC_WORDS]
    return "".join(words)


def resemblance(name: str, url: str | None) -> int:
    """0-100: how much the web address looks like the business name."""
    host = host_of(url)
    if not host:
        return 0
    parts = _extract(host)
    if link_kind(url) == "builder" and parts.subdomain:
        label = name_key(parts.subdomain.split(".")[-1])
    else:
        label = name_key(parts.domain)
    if len(label) < 3:
        return 0
    full, key = name_key(name), distinct_key(name)
    scores = [fuzz.ratio(full, label)]
    if len(key) >= 4:
        scores.append(fuzz.partial_ratio(key, label) if len(label) >= 5 else 0)
    if link_kind(url) == "builder" and path_depth(url):
        scores.append(fuzz.partial_ratio(key or full, name_key(urlparse(normalize_url(url)).path)))
    return int(max(scores))


def is_chain_url(url: str | None) -> bool:
    return bool(url and CHAIN_URL.search(url))


def is_listing_page(url: str | None, name: str) -> bool:
    """A page deep inside a site that isn't named after the shop is a directory listing, not its website."""
    return path_depth(url) >= 2 and resemblance(name, url) < 50 and link_kind(url) != "builder"


def format_phone(raw: str | None, country: str) -> tuple[str | None, str | None]:
    """Returns (display number, E.164 number) or (None, None) if it isn't a real phone number."""
    if not raw:
        return None, None
    raw = re.split(r"[;,/]", raw)[0].strip()
    try:
        num = phonenumbers.parse(raw, country)
    except phonenumbers.NumberParseException:
        return None, None
    if not phonenumbers.is_possible_number(num):
        return None, None
    return (phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.INTERNATIONAL),
            phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164))


def initial_status(websites: list[str], socials: list[str], name: str) -> tuple[str, str | None]:
    """Website status from the listing alone: (status, own website url to audit)."""
    kinds = {}
    for w in websites:
        k = link_kind(w)
        if k in ("own", "builder") and is_listing_page(w, name):
            k = "directory"
        kinds.setdefault(k, normalize_url(w))
    if "own" in kinds or "builder" in kinds:
        return "unknown", kinds.get("own") or kinds.get("builder")
    if "dead" in kinds:
        return "dead", kinds["dead"]
    if "directory" in kinds:
        return "directory_only", None
    if "social" in kinds or socials:
        return "social_only", None
    return "none", None


BASE_SCORE = {"none": 90, "social_only": 88, "directory_only": 86, "dead": 84}
PRIORITY = {"none": 1, "social_only": 1, "directory_only": 1, "dead": 1, "weak": 2, "unknown": 2, "good": 3}


def score(status: str, category: str, issues: list[str] | None = None, confidence: float | None = None,
          has_email: bool = False, verified: bool = False) -> tuple[int, int]:
    """(priority, score). Priority 1 = no real website, 2 = website that needs work, 3 = good website (skip)."""
    priority = PRIORITY.get(status, 2)
    if priority == 3:
        return 3, 0
    if priority == 1:
        base = BASE_SCORE.get(status, 85) + (5 if verified else 0)
    else:
        base = 40 + min(35, 6 * len(issues or []))
    extra = CATEGORY_WEIGHT.get(category, 4) + round(4 * (confidence or 0.5)) + (2 if has_email else 0)
    return priority, base + extra
