"""Research agent: builds a fact sheet for one hot lead from public sources only.

Every fact carries its source, link, time and confidence. "Not found" is kept apart from "doesn't exist":
anything we couldn't check is None (unknown), never False.

- Website: opens the home page like a phone does and grades five areas (mobile, Google, contact & booking,
  trust, tech), each check with its evidence.
- Instagram / Facebook / ratings: read from public search-result snippets (what any search engine shows);
  each profile must pass an identity check (name + city/area, or the link the map listing itself gives).
- Rivals: the nearest same-type shops with their own website, and what their websites offer.
"""
import datetime
import logging
import re
import time
from urllib.parse import urljoin, urlparse

from rapidfuzz import fuzz
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from .classify import distinct_key, host_of, is_chain_url, link_kind, name_key, normalize_url, resemblance
from .config import CATEGORY_LABELS, SEARCH_REGION
from .verify import CITY_NAMES, PARKED, UNDER_CONSTRUCTION, Searcher, _digits, _get

log = logging.getLogger(__name__)

BOOKING_HOSTS = ("practo.com", "calendly.com", "fresha.com", "setmore.com", "zohobookings", "bookings.zoho",
                 "simplybook", "booksy.com", "acuityscheduling", "vagaro.com", "appointy", "picktime", "lybrate.com",
                 "docpulse", "squareup.com/appointments", "youcanbook.me", "tidycal.com", "eazydiner", "dineout")
ORDER_HOSTS = ("zomato.com", "swiggy.com", "magicpin.in", "dunzo", "ubereats", "doordash", "grubhub")
BOOKING_WORDS = ("book appointment", "book an appointment", "book now", "schedule appointment", "book a visit",
                 "book online", "request appointment", "request an appointment", "book a table", "reserve a table",
                 "book your", "book consultation", "book a consultation", "appointment form")
ORDER_WORDS = ("order online", "order now", "add to cart", "buy now", "shop now")
REVIEW_WORDS = ("testimonial", "what our patients say", "what our clients say", "what our customers say",
                "reviews", "happy patients", "happy clients", "happy customers", "google reviews")
TEAM_WORDS = ("about us", "our team", "our doctors", "meet the doctor", "meet our", "our story", "who we are")
CMS_HINTS = (("wp-content", "WordPress"), ("wix.com", "Wix"), ("squarespace", "Squarespace"), ("shopify", "Shopify"),
             ("wsimg.com", "GoDaddy builder"), ("blogger.com", "Blogger"), ("webflow", "Webflow"),
             ("elementor", "Elementor"), ("weebly", "Weebly"), ("zyrosite", "Hostinger builder"), ("_next/", "Next.js"))
RESPONSIVE_HINTS = ("@media", "bootstrap", "tailwind", "elementor", "wix.com", "squarespace", "shopify", "webflow",
                    "foundation.min", "bulma", "w3.css", "flex-wrap")
GROUP_WEIGHTS = {"mobile": 25, "contact": 25, "google": 20, "trust": 15, "tech": 15}
GROUP_LABELS = {"mobile": "Phone screens", "contact": "Contact & booking", "google": "Found on Google",
                "trust": "Trust", "tech": "Speed & safety"}


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _check(checks: list, group: str, key: str, ok: bool | None, good: str, bad: str, evidence: str = ""):
    checks.append({"group": group, "key": key, "ok": ok, "text": good if ok else bad, "evidence": evidence})


# ---------------------------------------------------------------- website
def deep_audit(url: str, lead: dict | None = None) -> dict:
    """Grades a website. Returns {"ok": False, "reason"} when it can't be opened."""
    url = normalize_url(url)
    t0 = time.monotonic()
    resp, cert_ok = None, True
    for attempt in (url, url.replace("http://", "https://", 1) if url.startswith("http://") else None):
        if not attempt:
            continue
        try:
            resp = _get(attempt, timeout=20)
            break
        except Exception as e:
            if "CERTIFICATE" in str(e).upper():
                try:
                    resp, cert_ok = _get(attempt, verify=False, timeout=20), False
                    break
                except Exception:
                    pass
    seconds = round(time.monotonic() - t0, 1)
    out = {"source": "website", "url": url, "retrieved_at": now(), "confidence": "high"}
    if resp is None:
        return {**out, "ok": False, "reason": "Website did not open"}
    if resp.status_code in (401, 403, 406, 429, 503):
        return {**out, "ok": False, "reason": f"Website blocked our check ({resp.status_code})"}
    if resp.status_code >= 400:
        return {**out, "ok": False, "reason": f"Website shows an error ({resp.status_code})"}
    final = str(resp.url)
    html = resp.text[:3_000_000]
    low = html.lower()
    if any(p in low for p in PARKED) and len(low) < 60_000:
        return {**out, "ok": False, "reason": "Domain parked or expired", "url": final}

    tree = HTMLParser(html)
    node = tree.css_first("title")
    title = node.text(strip=True) if node else ""
    desc_node = tree.css_first('meta[name="description"]')
    description = (desc_node.attributes.get("content") or "").strip() if desc_node else ""
    h1s = [h.text(strip=True) for h in tree.css("h1") if h.text(strip=True)]
    links = [(a.attributes.get("href") or "").strip() for a in tree.css("a")]
    low_links = [l.lower() for l in links]
    imgs = tree.css("img")
    schema = " ".join(s.text() for s in tree.css('script[type="application/ld+json"]')).lower()
    nav = []
    for a in tree.css("nav a, header a, .menu a"):
        t = a.text(strip=True)
        if t and 2 < len(t) < 30 and t.lower() not in (x.lower() for x in nav):
            nav.append(t)
    for n in tree.css("script, style, noscript, svg"):
        n.decompose()
    text = tree.body.text(separator=" ") if tree.body else ""
    words = len(text.split())
    tlow = " ".join(text.lower().split())
    internal = {l.split("#")[0].rstrip("/") for l in links
                if l and not l.startswith(("#", "tel:", "mailto:", "javascript:"))
                and (host_of(urljoin(final, l)) == host_of(final))}
    years = [int(y) for y in re.findall(r"(?:©|&copy;|copyright)\s*(?:\d{4}\s*[-–]\s*)?((?:19|20)\d{2})", low)]
    this_year = datetime.date.today().year
    cms = next((name for hint, name in CMS_HINTS if hint in low), None)
    https = final.startswith("https://") and cert_ok

    wa = any(("wa.me" in l or "api.whatsapp.com" in l or l.startswith("whatsapp:")) for l in low_links)
    tel = any(l.startswith("tel:") for l in low_links)
    form = any(f.css_first("input[type=email], input[type=tel], textarea") for f in tree.css("form"))
    booking_link = next((l for l in low_links if any(h in l for h in BOOKING_HOSTS)), None)
    order_link = next((l for l in low_links if any(h in l for h in ORDER_HOSTS)), None)
    booking_words = next((w for w in BOOKING_WORDS if w in tlow), None)
    order_words = next((w for w in ORDER_WORDS if w in tlow), None)
    maps = "google.com/maps" in low or "maps.google" in low or "goo.gl/maps" in low or "maps.app.goo.gl" in low
    phone8 = _digits((lead or {}).get("phone_intl"))[-8:]
    phone_on_page = bool(phone8) and phone8 in _digits(text)
    city = (lead or {}).get("city", "")
    city_on_page = any(c in tlow for c in CITY_NAMES.get(city.lower(), (city.lower(),))) if city else None
    reviews = next((w for w in REVIEW_WORDS if w in tlow), None)
    team = next((w for w in TEAM_WORDS if w in tlow), None)
    prices = bool(re.search(r"(₹|rs\.?\s?\d|inr\s?\d|\$\s?\d|price list|pricing|packages?)", tlow))
    socials = sorted({l for l in links if link_kind(l) == "social"})[:6]
    responsive = any(h in low for h in RESPONSIVE_HINTS)
    viewport = bool(re.search(r"<meta[^>]+name=[\"']?viewport", low))
    weight_mb = round(len(resp.content) / 1e6, 1)

    sitemap = robots = None
    try:
        parts = urlparse(final)
        base = f"{parts.scheme}://{parts.netloc}"
        robots_r = _get(base + "/robots.txt", timeout=8)
        robots = robots_r.status_code == 200 and "user-agent" in robots_r.text.lower()
        sm = _get(base + "/sitemap.xml", timeout=8)
        head = sm.text[:5000].lower()
        sitemap = sm.status_code == 200 and ("<urlset" in head or "<sitemapindex" in head)
    except Exception:
        pass

    c: list = []
    _check(c, "mobile", "viewport", viewport, "Set up for phone screens", "Not set up for phone screens (no mobile layout)")
    _check(c, "mobile", "responsive", responsive or None, "Layout adapts to screen size",
           "No sign the layout adapts to phones")
    _check(c, "mobile", "tap_to_call", tel, "Tap-to-call button", "No tap-to-call button")
    _check(c, "mobile", "weight", weight_mb < 3, f"Light page ({weight_mb} MB)", f"Heavy page ({weight_mb} MB) - slow on mobile data")
    _check(c, "google", "title", bool(title) and title.lower() not in ("home", "index", "untitled"),
           f"Page title: \"{title[:60]}\"", "No proper page title (Google shows a blank or 'Home')", title[:80])
    _check(c, "google", "description", bool(description), "Has a Google description",
           "No description for Google results", description[:120])
    _check(c, "google", "h1", len(h1s) >= 1, "Main heading present", "No main heading on the page", (h1s or [""])[0][:80])
    _check(c, "google", "schema", "localbusiness" in schema or any(t in schema for t in (
        "dentist", "medicalclinic", "physician", "beautysalon", "restaurant", "store", "organization")),
           "Business details marked up for Google", "Business details not marked up for Google (no LocalBusiness data)")
    _check(c, "google", "sitemap", sitemap, "Has a sitemap for Google", "No sitemap for Google")
    _check(c, "google", "city_named", city_on_page, f"Mentions {city}", f"Doesn't mention {city} (hurts local search)")
    _check(c, "contact", "whatsapp", wa, "WhatsApp button", "No WhatsApp button")
    _check(c, "contact", "phone_shown", phone_on_page or tel, "Phone number on the page", "Phone number not on the page")
    _check(c, "contact", "form", form, "Enquiry form", "No enquiry form")
    booking_ok = bool(booking_link or booking_words or order_link or order_words)
    _check(c, "contact", "booking", booking_ok,
           "Online booking/ordering: " + (host_of(booking_link or order_link) if (booking_link or order_link)
                                          else (booking_words or order_words or "")),
           "No online booking or ordering")
    _check(c, "contact", "map", maps, "Google Map / directions", "No map or directions")
    _check(c, "trust", "reviews", bool(reviews), "Shows reviews/testimonials", "No reviews or testimonials shown")
    _check(c, "trust", "gallery", len(imgs) >= 8, f"{len(imgs)} photos", f"Only {len(imgs)} photos")
    _check(c, "trust", "about", bool(team), "About / team section", "No about or team section")
    _check(c, "trust", "fresh", (max(years) >= this_year - 1) if years else None,
           f"Recently updated (© {max(years) if years else ''})", f"Looks old (© {max(years) if years else ''})")
    _check(c, "trust", "content", words >= 250, f"Enough information ({words} words)", f"Very little information ({words} words)")
    _check(c, "tech", "https", https, "Secure (https)", "Not secure - browsers show a warning" if not cert_ok
           else "No https - browsers mark it 'Not secure'")
    _check(c, "tech", "speed", seconds <= 4, f"Opened in {seconds}s", f"Slow to open ({seconds}s)")
    _check(c, "tech", "live", not (any(p in tlow for p in UNDER_CONSTRUCTION) and words < 400),
           "Finished site", "Shows 'coming soon' / under construction")
    _check(c, "tech", "own_address", link_kind(final) == "own", "Own web address",
           f"Free builder address ({host_of(final)})")

    scores = {}
    for g in GROUP_WEIGHTS:
        known = [x for x in c if x["group"] == g and x["ok"] is not None]
        scores[g] = round(100 * sum(1 for x in known if x["ok"]) / len(known)) if known else None
    have = {g: s for g, s in scores.items() if s is not None}
    overall = round(sum(s * GROUP_WEIGHTS[g] for g, s in have.items()) / sum(GROUP_WEIGHTS[g] for g in have)) if have else None
    return {**out, "ok": True, "url": final, "score": overall, "scores": scores, "checks": c,
            "title": title[:120], "description": description[:200], "h1": (h1s or [None])[0],
            "menu": nav[:12], "pages_linked": len(internal), "cms": cms, "seconds": seconds, "weight_mb": weight_mb,
            "has_whatsapp": wa, "has_booking": booking_ok, "booking_via": host_of(booking_link or order_link) or booking_words or order_words,
            "has_form": form, "has_reviews": bool(reviews), "copyright": max(years) if years else None,
            "socials": socials, "robots": robots}


# ---------------------------------------------------------------- search snippets
NUM = r"([\d][\d.,]*\s?[KkMm]?)"
IG_RE = re.compile(NUM + r"\s+Followers?,\s+" + NUM + r"\s+Following,\s+" + NUM + r"\s+Posts?\s+-\s+(.*?)\s*\(@([\w.]+)\)", re.I)
FB_RE = re.compile(NUM + r"\s+likes?\s*[·•]\s*" + NUM + r"\s+talking about this(?:\s*[·•]\s*" + NUM + r"\s+were here)?", re.I)
FB_FOLLOW_RE = re.compile(NUM + r"\s+followers", re.I)
RATING_RES = [re.compile(r"(?:average rating of|rated|rating of|rating:)\s*([0-5](?:\.\d)?)", re.I),
              re.compile(r"\b([0-5]\.\d)\s*(?:/\s*5|out of 5|stars?|★)", re.I),
              re.compile(r"★\s*([0-5]\.\d)")]
COUNT_RE = re.compile(r"([\d][\d,]*)\s+(?:verified\s+)?(?:user\s+)?(?:patient\s+)?(?:reviews|ratings|feedbacks?|patient stories)", re.I)
DOCTORS_RE = re.compile(r"(\d+)\s+Doctors?\s+in", re.I)
RATING_SITES = ("justdial.com", "practo.com", "google.com", "sulekha.com", "zomato.com", "magicpin.in", "lybrate.com",
                "tripadvisor", "yelp.com", "clinicspots.com", "credihealth.com", "swiggy.com", "nobroker.in",
                "urbancompany.com", "trustpilot.com")


def to_int(s: str | None) -> int | None:
    if not s:
        return None
    s = s.strip().replace(",", "").replace(" ", "")
    mult = 1000 if s[-1:] in "Kk" else 1_000_000 if s[-1:] in "Mm" else 1
    try:
        return int(float(s.rstrip("KkMm")) * mult)
    except ValueError:
        return None


def _is_same_shop(lead: dict, text: str, handle: str = "") -> int:
    """0-100: how sure we are that a snippet/profile is this shop."""
    key = distinct_key(lead["name"]) or name_key(lead["name"])
    flat = name_key(text + " " + handle)
    if len(key) < 4:
        return 0
    name_hit = key in flat or fuzz.partial_ratio(key, name_key(handle)) >= 88 if handle else key in flat
    if not name_hit:
        return 0
    sure = 60
    phone8 = _digits(lead.get("phone_intl"))[-8:]
    if phone8 and phone8 in _digits(text):
        sure = 95
    cities = CITY_NAMES.get(lead["city"].lower(), (lead["city"].lower(),))
    area = (lead.get("locality") or "").lower()
    if any(name_key(c) in flat for c in cities) or (area and area != lead["city"].lower() and name_key(area) in flat):
        sure = max(sure, 80)
    return sure


def social_and_ratings(lead: dict, searcher: Searcher) -> dict:
    region = SEARCH_REGION.get(lead["country"], "wt-wt")
    city = lead["city"]
    known = [s for s in lead.get("socials") or [] if link_kind(s) == "social"]
    known_ig = next((re.search(r"instagram\.com/([\w.]+)", s).group(1) for s in known
                     if re.search(r"instagram\.com/(?!p/|reel/|explore/)([\w.]+)", s)), None)
    queries = [f"{lead['name']} {city} instagram", f"{lead['name']} {city} reviews rating"]
    if known_ig:
        queries[0] = f"instagram.com/{known_ig}"
    results, searched = [], []
    for q in queries:
        r = searcher.search(q, region)
        searched.append({"query": q, "ok": r is not None, "results": len(r or [])})
        results += r or []

    out = {"instagram": None, "facebook": None, "ratings": [], "other_profiles": [], "snippets": [],
           "searches": searched, "retrieved_at": now()}
    ig_candidates = []
    for r in results:
        href, body, title = r.get("href", ""), r.get("body", ""), r.get("title", "")
        blob = f"{title} {body}"
        if "instagram.com" in href:
            m = IG_RE.search(blob)
            if not m:
                continue
            handle = m.group(5)
            sure = 95 if known_ig and handle.lower() == known_ig.lower() else _is_same_shop(lead, blob, handle)
            ig_candidates.append({"handle": handle, "name": m.group(4).strip()[:80], "followers": to_int(m.group(1)),
                                  "following": to_int(m.group(2)), "posts": to_int(m.group(3)),
                                  "bio": body.split(":", 1)[-1].strip()[:200], "url": f"https://www.instagram.com/{handle}/",
                                  "match": sure, "source": "search snippet"})
        elif "facebook.com" in href and not out["facebook"]:
            m = FB_RE.search(blob)
            fm = FB_FOLLOW_RE.search(blob)
            in_listing = any(href.rstrip("/").split("/")[-1] in s for s in known if "facebook.com" in s)
            sure = 95 if in_listing else _is_same_shop(lead, blob)
            if (m or fm) and sure >= 60:
                out["facebook"] = {"url": href, "likes": to_int(m.group(1)) if m else None,
                                   "talking": to_int(m.group(2)) if m else None,
                                   "checkins": to_int(m.group(3)) if m and m.group(3) else None,
                                   "followers": to_int(fm.group(1)) if fm else None,
                                   "match": sure, "source": "search snippet", "text": body[:200]}
        host = host_of(href)
        if any(s in host or s in href for s in RATING_SITES):
            sure = _is_same_shop(lead, blob)
            if sure < 60:
                continue
            rating = next((float(m.group(1)) for rx in RATING_RES if (m := rx.search(blob))), None)
            count = COUNT_RE.search(blob)
            doctors = DOCTORS_RE.search(blob)
            entry = {"site": host.split(".")[-2] if host.count(".") else host, "url": href,
                     "rating": rating if rating and 1 <= rating <= 5 else None,
                     "count": to_int(count.group(1)) if count else None,
                     "doctors": int(doctors.group(1)) if doctors else None, "match": sure,
                     "source": "search snippet", "text": body[:240]}
            if entry["rating"] or entry["count"] or entry["doctors"]:
                out["ratings"].append(entry)
            elif len(body) > 80:
                out["snippets"].append({"site": entry["site"], "text": body[:240], "url": href})
    ig_candidates.sort(key=lambda x: (x["match"], x["followers"] or 0), reverse=True)
    if ig_candidates and ig_candidates[0]["match"] >= 60:
        out["instagram"] = ig_candidates[0]
        out["other_profiles"] = [f"@{x['handle']}" for x in ig_candidates[1:4]]
    # one entry per site (the best-matching one)
    best = {}
    for e in out["ratings"]:
        if e["site"] not in best or e["match"] > best[e["site"]]["match"]:
            best[e["site"]] = e
    out["ratings"] = list(best.values())
    return out


# ---------------------------------------------------------------- rivals
def rivals(db, lead: dict, audit_top: int = 3) -> list[dict]:
    out = []
    for r in db.call("worker_rivals", p_id=lead["id"], p_limit=20) or []:
        url = normalize_url(r.get("website"))
        if not url or link_kind(url) not in ("own", "builder") or is_chain_url(url):
            continue
        if resemblance(lead["name"], r["name"]) >= 80:  # another branch of the same shop
            continue
        if any(host_of(url) == host_of(x["website"]) for x in out):
            continue
        out.append({"name": r["name"], "metres": r["metres"], "website": url, "status": r["website_status"]})
        if len(out) >= 6:
            break
    for r in out[:audit_top]:
        a = deep_audit(r["website"])
        if a.get("ok"):
            r.update({"score": a["score"], "has_whatsapp": a["has_whatsapp"], "has_booking": a["has_booking"],
                      "booking_via": a["booking_via"], "mobile_ready": a["scores"].get("mobile"),
                      "has_reviews": a["has_reviews"]})
        else:
            r["opened"] = False
    return out


# ---------------------------------------------------------------- chain / franchise
CHAIN_HOST_RE = re.compile(r"^(stores?|locations?|branches|outlets?|clinics?)\.", re.I)


def chain_signals(lead: dict) -> list[str]:
    sig = []
    for url in filter(None, [lead.get("website"), lead.get("listing_website")]):
        if is_chain_url(url) or CHAIN_HOST_RE.match(host_of(url)) or "onelink.me" in url:
            sig.append(f"Website is a brand store-locator / app link ({host_of(url)})")
    if (lead.get("branches") or 1) >= 4:
        sig.append(f"{lead['branches']} places in the city share this name")
    return sig


def research(db, lead: dict, searcher: Searcher) -> dict:
    t0 = time.monotonic()
    site = None
    if lead.get("website") and lead.get("website_status") in ("weak", "good", "dead"):
        site = deep_audit(lead["website"], lead)
    social = social_and_ratings(lead, searcher)
    rv = rivals(db, lead)
    return {
        "lead": {k: lead.get(k) for k in ("id", "name", "category", "city", "locality", "address", "phone_type",
                                          "website", "website_status", "issues", "rivals_nearby", "rivals_with_site",
                                          "branches", "brands_nearby", "tier", "lead_score", "reasons", "socials")}
                | {"type": CATEGORY_LABELS.get(lead["category"], lead["category"])},
        "website": site,
        "social": social,
        "rivals": rv,
        "chain_signals": chain_signals(lead),
        "researched_at": now(),
        "seconds": round(time.monotonic() - t0),
    }
