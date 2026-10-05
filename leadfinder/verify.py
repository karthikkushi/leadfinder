"""Website checker agent.

- Shops listed without a website: searches the web for their own site (a missing website field in a map
  listing doesn't mean the shop has no site). The LLM only decides the unclear matches.
- Shops with a website: opens it like a phone browser would and lists what's wrong with it.
"""
import datetime
import logging
import re
import threading
import time

import httpx
from ddgs import DDGS
from rapidfuzz import fuzz
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from . import llm
from .classify import distinct_key, host_of, is_listing_page, link_kind, name_key, normalize_url, resemblance, score
from .config import CATEGORY_LABELS, SEARCH_REGION

log = logging.getLogger(__name__)
UA = ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/128.0.0.0 Mobile Safari/537.36")
PARKED = ("domain is for sale", "buy this domain", "this domain may be for sale", "domain parking", "sedoparking",
          "hugedomains.com", "afternic", "this domain has expired", "domain has expired", "account suspended",
          "website is suspended", "renew your domain", "parked domain")
UNDER_CONSTRUCTION = ("under construction", "coming soon", "launching soon", "site is under maintenance")
STRONG = ("Not mobile-friendly", "No HTTPS", "Security certificate", "Looks outdated", "Under construction",
          "Very little content", "Free website-builder")
BLOCKED_CODES = {401, 403, 406, 429, 503}


def _get(url: str, verify: bool = True, timeout: float = 15) -> httpx.Response:
    return httpx.get(url, follow_redirects=True, timeout=timeout, verify=verify,
                     headers={"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9"})


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def _mentions(text: str, name: str) -> bool:
    flat = name_key(text)
    key = distinct_key(name)
    return (len(key) >= 4 and key in flat) or name_key(name) in flat


def audit(url: str, name: str | None = None, phone_intl: str | None = None) -> dict:
    """Opens a website and grades it: dead, weak (with issues), good, or not really the shop's site."""
    url = normalize_url(url)
    if link_kind(url) == "dead":
        reason = ("Old Google business.site page - Google shut these down" if "business.site" in url
                  else "Domain is up for sale")
        return {"status": "dead", "issues": [reason], "website": url}
    issues, resp, t0 = [], None, time.monotonic()
    for attempt in (url, url.replace("http://", "https://", 1) if url.startswith("http://") else None):
        if not attempt:
            continue
        try:
            resp = _get(attempt)
            break
        except httpx.ConnectError as e:
            if "CERTIFICATE" in str(e).upper():
                try:
                    resp = _get(attempt, verify=False)
                    issues.append("Security certificate broken - browsers warn visitors")
                    break
                except Exception:
                    pass
        except Exception:
            pass
    if resp is None:  # one slower retry before calling a site dead - a wrong "your site is down" call is bad
        time.sleep(3)
        try:
            resp = _get(url, timeout=30)
        except Exception:
            pass
    elapsed = time.monotonic() - t0
    if resp is None:
        return {"status": "dead", "issues": ["Website not opening"], "website": url}
    if resp.status_code in BLOCKED_CODES:
        return {"status": "good", "issues": [], "website": str(resp.url)}  # bot wall: don't guess
    if resp.status_code >= 400:
        return {"status": "dead", "issues": [f"Website shows an error ({resp.status_code})"], "website": url}

    final = str(resp.url)
    kind = link_kind(final)
    if kind in ("social", "directory", "dead"):
        status = {"social": "social_only", "directory": "directory_only", "dead": "dead"}[kind]
        return {"status": status, "issues": [f"Website link only goes to {host_of(final)}"], "website": None,
                "socials": [final] if kind != "dead" else []}

    html = resp.text[:3_000_000]
    low = html.lower()
    if any(p in low for p in PARKED) and len(low) < 60_000:
        return {"status": "dead", "issues": ["Domain parked or expired"], "website": url}

    tree = HTMLParser(html)
    title = (tree.css_first("title").text(strip=True) if tree.css_first("title") else "")
    links = [a.attributes.get("href") or "" for a in tree.css("a")]
    emails = sorted({l[7:].split("?")[0] for l in links if l.lower().startswith("mailto:") and "@" in l})
    socials = sorted({l for l in links if link_kind(l) == "social"})[:6]
    for node in tree.css("script, style, noscript, svg"):
        node.decompose()
    text = tree.body.text(separator=" ") if tree.body else ""
    words = len(text.split())

    # Is this really the shop's own site? Listing pages show the shop's name and phone too, so they're only
    # accepted when the address looks like the shop's name or the page is a home page about the shop.
    if name and resemblance(name, final) < 50:
        about_shop = _mentions(title + " " + text[:20000], name) or (
            phone_intl and _digits(phone_intl)[-8:] in _digits(text))
        if is_listing_page(final, name) or not about_shop:
            return {"status": "directory_only", "issues": [f"Listed website ({host_of(final)}) isn't the shop's own"],
                    "website": None}

    if not re.search(r"<meta[^>]+name=[\"']?viewport", low):
        issues.append("Not mobile-friendly (no mobile layout)")
    if final.startswith("http://"):
        issues.append("No HTTPS - browsers show 'Not secure'")
    years = [int(y) for y in re.findall(r"(?:©|&copy;|copyright)\s*(?:\d{4}\s*[-–]\s*)?((?:19|20)\d{2})", low)]
    this_year = datetime.date.today().year
    if years and max(years) <= this_year - 3:
        issues.append(f"Looks outdated (© {max(years)})")
    if any(p in low for p in UNDER_CONSTRUCTION) and words < 400:
        issues.append("Under construction / 'coming soon' page")
    if words < 80 and low.count("<script") < 6:
        issues.append("Very little content")
    if link_kind(final) == "builder":
        issues.append(f"Free website-builder address ({host_of(final)})")
    if elapsed > 6:
        issues.append(f"Slow to load ({elapsed:.0f}s)")
    if not any(l.lower().startswith(("tel:", "https://wa.me", "https://api.whatsapp", "whatsapp:")) for l in links):
        issues.append("No tap-to-call or WhatsApp button")
    if not title:
        issues.append("No page title (hurts Google ranking)")
    if len(resp.content) > 5_000_000:
        issues.append(f"Heavy page ({len(resp.content) / 1e6:.0f} MB)")

    weak = any(i.startswith(STRONG) for i in issues) or len(issues) >= 2
    return {"status": "weak" if weak else "good", "issues": issues, "website": final,
            "email": emails[0] if emails else None, "socials": socials}


class Searcher:
    """Free web search through ddgs, rotating DuckDuckGo, Yahoo and Bing so no single engine gets hammered.
    One search at a time; backs off when every engine fails."""
    ENGINES = ["duckduckgo", "yahoo", "bing"]

    def __init__(self):
        self.failures = 0
        self.disabled_until = 0.0
        self.turn = 0
        self.lock = threading.Lock()

    def search(self, query: str, region: str) -> list[dict] | None:
        with self.lock:
            if time.monotonic() < self.disabled_until:
                return None
            errors, empty = [], 0
            self.turn += 1
            for i in range(len(self.ENGINES)):
                engine = self.ENGINES[(self.turn + i) % len(self.ENGINES)]
                try:
                    results = DDGS(timeout=15).text(query, region=region, max_results=8, backend=engine) or []
                except Exception as e:
                    if "no results" in str(e).lower():
                        results = []
                    else:
                        errors.append(f"{engine}: {str(e)[:60]}")
                        continue
                if not results:  # an engine sometimes answers empty when it's throttling: ask another one
                    empty += 1
                    continue
                self.failures = 0
                time.sleep(0.7)
                return results
            if empty:
                self.failures = 0
                return []
            self.failures += 1
            wait = min(300, 30 * self.failures)
            log.info("Web search unavailable (%s); pausing searches %ss", "; ".join(errors), wait)
            self.disabled_until = time.monotonic() + wait
            return None


def find_own_site(lead: dict, results: list[dict]) -> tuple[str | None, list[str], bool]:
    """(own website url or None, social pages found, unsure)."""
    key = distinct_key(lead["name"]) or name_key(lead["name"])
    phone8 = _digits(lead.get("phone_intl"))[-8:]
    socials, maybe = [], []
    for r in results:
        href, title, body = r.get("href", ""), r.get("title", ""), r.get("body", "")
        kind = link_kind(href)
        if kind == "social":
            if len(key) >= 4 and fuzz.partial_ratio(key, name_key(title)) >= 85:
                socials.append(href)
            continue
        if kind not in ("own", "builder") or is_listing_page(href, lead["name"]):
            continue
        looks = resemblance(lead["name"], href)
        phone_hit = bool(phone8) and phone8 in _digits(title + " " + body)
        if looks >= 85 and (phone_hit or fuzz.ratio(name_key(lead["name"]), name_key(host_of(href).split(".")[0])) >= 85):
            return href, socials, False
        if looks >= 60 or (phone_hit and looks >= 30):
            maybe.append(r)

    for r in maybe[:2]:  # open the page: does it show this shop's phone number?
        try:
            page = _get(r["href"])
            if phone8 and phone8 in _digits(page.text[:2_000_000]) and resemblance(lead["name"], r["href"]) >= 60:
                return r["href"], socials, False
        except Exception:
            pass
    if maybe:
        answer = llm.ask_json(
            "You check whether a web page is the official website of one specific local business. "
            "A different business with a similar name, a directory, a listing site, a marketplace or a chain's "
            "head-office site is NOT its website. Reply as JSON: {\"url\": <matching url or null>, \"sure\": <true|false>}",
            f"Business: {lead['name']}\nType: {CATEGORY_LABELS.get(lead['category'], lead['category'])}\n"
            f"Area: {lead.get('locality') or ''}, {lead['city']}\nAddress: {lead.get('address') or 'unknown'}\n"
            f"Phone: {lead.get('phone') or 'unknown'}\n\nCandidates:\n"
            + "\n".join(f"- {r['href']} | {r.get('title', '')} | {r.get('body', '')[:200]}" for r in maybe[:5]))
        if answer is None:
            return None, socials, True
        if answer.get("url") and answer.get("sure"):
            return answer["url"], socials, False
    return None, socials, False


def check(lead: dict, searcher: Searcher) -> dict | None:
    """Result row for worker_save_checks, or None to retry later (search unavailable)."""
    status, website, issues, verified = lead["website_status"], lead.get("website"), [], True
    socials, email = [], None
    if status == "unknown" and website:
        a = audit(website, lead["name"], lead.get("phone_intl"))
        status, issues = a["status"], a["issues"]
        website, email, socials = a.get("website"), a.get("email"), a.get("socials") or []
    if status in ("none", "social_only", "directory_only", "dead"):
        query = f"{lead['name']} {lead.get('locality') or ''} {lead['city']}".strip()
        results = searcher.search(query, SEARCH_REGION.get(lead["country"], "wt-wt"))
        if results is None:
            return None
        own, found_socials, unsure = find_own_site(lead, results)
        socials += found_socials
        if own:
            a = audit(own, lead["name"], lead.get("phone_intl"))
            if a["status"] in ("weak", "good"):
                status, issues, website = a["status"], a["issues"], a.get("website") or own
                email = email or a.get("email")
            socials += a.get("socials") or []
        elif found_socials and status == "none":
            status = "social_only"
        verified = not unsure
    priority, sc = score(status, lead["category"], issues, has_email=bool(lead.get("email") or email),
                         verified=verified)
    return {"id": lead["id"], "website": website if status != "directory_only" else None,
            "socials": sorted(set(socials))[:6], "email": email, "website_status": status, "issues": issues[:8],
            "priority": priority, "score": sc, "verified": verified}
