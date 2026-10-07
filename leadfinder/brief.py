"""Sales-brief agent: turns a research fact sheet into a one-screen call brief for Shreya.

Quality comes from three things, not from a bigger model alone:
1. The model only sees numbered facts and must cite them; numbers it writes must exist in the facts.
2. Worked examples of the tone we want (plain Indian English, short, no sales jargon).
3. A second pass that reviews the brief against the facts; problems go back for one rewrite.
"""
import json
import logging
import re

from . import llm

log = logging.getLogger(__name__)

# What to sell, by shop type: (no website, weak website). Evidence decides the add-ons in the prompt.
OFFERS = {
    "dentist": ("Website with treatments, doctor profile and WhatsApp appointment booking",
                "Website redesign with treatment pages and WhatsApp appointment booking"),
    "dermatologist": ("Website with treatments, before/after gallery and WhatsApp consultation booking",
                      "Website redesign with treatment pages, results gallery and consultation booking"),
    "physio": ("Website with conditions treated and WhatsApp appointment booking", "Website redesign with booking"),
    "eye_clinic": ("Website with services, frames gallery and eye-test booking", "Website redesign with eye-test booking"),
    "vet": ("Website with services, timings and WhatsApp appointment booking", "Website redesign with booking"),
    "clinic": ("Website with doctors, timings and WhatsApp appointment booking", "Website redesign with booking"),
    "salon_beauty": ("Website with services, price list, bridal packages gallery and WhatsApp booking",
                     "Website redesign with packages, gallery and WhatsApp booking"),
    "gym_fitness": ("Website with plans, trainer profiles and free-trial enquiry", "Website redesign with plans and trial enquiry"),
    "restaurant_cafe": ("Menu website with photos, location and WhatsApp/phone orders", "Website redesign with menu and ordering"),
    "bakery_sweets": ("Website with cakes/sweets catalogue and WhatsApp orders", "Website redesign with catalogue and WhatsApp orders"),
    "tuition": ("Website with courses, results, timings and admission enquiry form", "Website redesign with courses and admission enquiry"),
    "clothing": ("Catalogue website with WhatsApp enquiry on every product", "Website redesign as a catalogue with WhatsApp enquiry"),
    "jewellery": ("Catalogue website with collections and WhatsApp enquiry", "Website redesign with collections and WhatsApp enquiry"),
    "furniture_home": ("Catalogue website with WhatsApp enquiry", "Website redesign as a catalogue with WhatsApp enquiry"),
    "pet_shop": ("Website with products, services and WhatsApp orders", "Website redesign with WhatsApp orders"),
    "events_photo": ("Portfolio website with packages and enquiry form", "Portfolio redesign with packages and enquiry"),
    "home_services": ("Website with services, areas covered and quote request", "Website redesign with quote request"),
}
DEFAULT_OFFER = ("Simple website with photos, timings, location and Call/WhatsApp buttons",
                 "Website redesign that works on phones with Call/WhatsApp buttons")

SYSTEM = """You write call briefs for Shreya, who cold-calls small local businesses in India to sell websites made by a small web studio. She calls on her phone between other work, so the brief must be readable in 30 seconds.

HARD RULES
- Use ONLY the numbered facts. Never invent ratings, follower counts, distances, years, prices, names or problems. If a fact is marked "possible match", say "I think I saw..." or leave it out.
- Every claim in "why_call" must cite fact ids like [F3].
- Any number you write must appear in the facts.
- Talk like a friendly, respectful person from Bengaluru/Mysuru on a phone call: short sentences, simple English, no jargon. Never use: "digital presence", "leverage", "elevate", "seamless", "cutting-edge", "solutions", "synergy", "revolutionize", "I hope you are doing well", "online footprint", "boost your business".
- Never insult their current website or business. Never quote our internal website scores to the owner.
- Only call an Instagram "active" or "strong" if it is confirmed and has at least 1000 followers or 100 posts.
- Never say they lack something that the facts list under "Website already has" or in the website menu. Point at what customers miss, not at what the owner did wrong.
- Compliment something real first when a fact allows it (good rating, active Instagram).
- Use {me} for the caller's name and {company} for the studio name. Never write a price.
- A local business with 2-3 branches is a good lead, not a chain.
- If the facts show a national chain/franchise outlet (store-locator website, brand account with huge followings), set call to "no" and explain: the head office controls their website.
- The WhatsApp message must be under 70 words, start with "Hi" and the shop name, give one specific observation, and end with a yes/no question. No links.

OUTPUT JSON with exactly these keys:
{
 "call": "yes" | "maybe" | "no",
 "headline": "one line: why this shop is worth a call today",
 "why_call": ["3-4 short bullets with [F#] citations"],
 "sell": {"main": "what to offer", "add_on": "one optional add-on or empty", "why_it_fits": "one sentence, cite [F#]"},
 "opening": "what Shreya says in the first 15 seconds (ask for the owner, who she is, one specific reason for calling, ask for 30 seconds)",
 "questions": ["2 short discovery questions that make the owner talk about how customers find and contact them"],
 "pitch": "3-4 sentences linking their situation to the offer, ending by offering a free sample made for their shop",
 "objections": [{"they_say": "...", "you_say": "..."}, {"they_say": "...", "you_say": "..."}],
 "dont_say": ["2 things to avoid with this specific shop"],
 "sample": "what the free sample website should show for this shop (one sentence)",
 "whatsapp": "the message to send after the call",
 "follow_up": "when and how to follow up if they don't decide today"
}"""

EXAMPLE_FACTS = """[F1] Shop: Sri Ganesh Physiotherapy Centre, physiotherapists in Jayanagar, Bengaluru
[F2] Phone: mobile number (likely the owner, WhatsApp works)
[F3] Website: none found (searched Google-style results and tried 6 web addresses)
[F4] Justdial: rated 4.7 (search result)
[F5] Instagram @sriganeshphysio: 860 followers, 120 posts (search result, matched by name and city)
[F6] 5 of 7 similar shops within 1 km have websites
[F7] Rival: Align Physio, 400 m away, website score 84/100, has online booking, has WhatsApp button"""

EXAMPLE_BRIEF = {
    "call": "yes",
    "headline": "Well-rated physio with an active Instagram but no website, while nearby rivals take bookings online",
    "why_call": ["No website of their own [F3]", "Customers rate them 4.7 on Justdial [F4]",
                 "Posts regularly on Instagram, so the owner cares about getting customers online [F5]",
                 "Align Physio 400 m away takes bookings online [F7]"],
    "sell": {"main": "Website with conditions treated and WhatsApp appointment booking",
             "add_on": "Show their Instagram posts on the website",
             "why_it_fits": "They already get attention on Instagram [F5]; a website turns Google searches into bookings too [F7]."},
    "opening": "Hello, am I speaking with the owner of Sri Ganesh Physiotherapy? I'm {me} from {company}. I saw your clinic has really good reviews on Justdial, and I had one small idea for getting you more patients from Google. Do you have 30 seconds?",
    "questions": ["How do most new patients find you now: Google, Instagram, or word of mouth?",
                  "When someone wants an appointment, do they call you or message on WhatsApp?"],
    "pitch": "When people in Jayanagar search for a physio on Google, the clinics with websites show up first, and some even let patients book online. You already have great reviews and an active Instagram, so you're only missing the page that brings those Google searches to you. We make simple websites with your treatments, timings, location and a WhatsApp booking button. I can make a free sample for your clinic first, so you see it before deciding anything.",
    "objections": [
        {"they_say": "We already have Instagram.", "you_say": "Instagram is great for people who already follow you. A website is what new patients find when they search on Google, and it can show your Instagram posts too."},
        {"they_say": "We get enough patients by word of mouth.", "you_say": "That's the best kind! Even then, most people Google a clinic before they visit, so a website helps them choose you. The sample is free, so you can just have a look."}],
    "dont_say": ["Don't call it a problem that they have no website; frame it as an easy next step", "Don't mention rivals by name unless they ask"],
    "sample": "One-page site: treatments for back pain, sports injuries and post-surgery rehab, photos from their Instagram, timings, Jayanagar map and a WhatsApp 'Book appointment' button.",
    "whatsapp": "Hi Sri Ganesh Physiotherapy, this is {me} from {company}. Thanks for your time on the call. Your Justdial reviews are excellent, but patients searching Google can't find a website for you yet. Shall I make a free sample website for your clinic so you can see how it would look?",
    "follow_up": "If no reply, send one friendly WhatsApp after 2 days; call again after 5 days in the evening. Stop after that.",
}

CHECKER = """You review a sales call brief against its facts before it reaches a caller. Be strict but fair.
Report a problem only if one of these is true:
1. A claim, number, name, rating, distance or year is not supported by the facts (or a "possible match" fact is stated as certain).
2. It sounds robotic, salesy or uses jargon a shop owner wouldn't use.
3. It insults the business or its website.
4. The WhatsApp message is over 70 words, has a link, or doesn't end with a question.
5. The call decision is clearly wrong (e.g. a national chain outlet marked "yes"). A local business with 2-3 branches is NOT a chain and should be called.
6. It says the shop lacks something the facts say it already has (check "Website already has" and the menu), or quotes an internal score to the owner, or mentions an UNCONFIRMED profile.
Reply as JSON: {"ok": true|false, "problems": ["short, specific fix instructions"]}"""


def offer_for(category: str, has_weak_site: bool) -> str:
    return OFFERS.get(category, DEFAULT_OFFER)[1 if has_weak_site else 0]


def fact_sheet(f: dict) -> list[str]:
    """Numbered, plain facts. Only things we verified, each with where it came from."""
    l, facts = f["lead"], []
    add = facts.append
    area = l.get("locality") if l.get("locality") and l["locality"] != l["city"] else ""
    add(f"Shop: {l['name']}, {l['type'].lower()} in {area + ', ' if area else ''}{l['city']}")
    if l.get("address"):
        add(f"Address: {l['address']}")
    add({"mobile": "Phone: mobile number (likely the owner, WhatsApp works)",
         "fixed": "Phone: landline (may reach staff, not the owner)"}.get(l.get("phone_type"), "Phone: type unknown"))
    w = f.get("website")
    status = l.get("website_status")
    if status in ("none", "social_only", "directory_only"):
        add("Website: none found (checked search results and tried likely web addresses)"
            + (" - they only have social media pages" if status == "social_only" else ""))
    elif w and not w.get("ok"):
        add(f"Website {l.get('website')}: {w.get('reason')} (checked today)")
    elif w:
        groups = ", ".join(f"{k} {v}/100" for k, v in w["scores"].items() if v is not None)
        add(f"Website {w['url']}: our internal score {w['score']}/100 ({groups}) - for Shreya only, never quote scores to the owner")
        bad = [c["text"] for c in w["checks"] if c["ok"] is False]
        good = [c["text"] for c in w["checks"] if c["ok"]]
        if bad:
            add("Website problems found: " + "; ".join(bad[:8]))
        if good:
            add("Website already has: " + "; ".join(good))
        if w.get("menu"):
            add("Website menu: " + ", ".join(w["menu"][:10]))
    s = f.get("social") or {}
    ig = s.get("instagram")
    if ig:
        sure = "matched by name and city" if ig["match"] >= 80 else "UNCONFIRMED: may be a different shop, do not mention it on the call"
        add(f"Instagram @{ig['handle']}: {ig['followers']} followers, {ig['posts']} posts (search result, {sure})"
            + (f"; bio: {ig['bio'][:120]}" if ig.get("bio") else ""))
    fb = s.get("facebook")
    if fb:
        parts = [f"{fb[k]} {label}" for k, label in (("likes", "likes"), ("followers", "followers"), ("checkins", "check-ins")) if fb.get(k)]
        add(f"Facebook page: {', '.join(parts)} (search result)")
    for r in s.get("ratings") or []:
        bits = [f"rated {r['rating']}" if r.get("rating") else "", f"{r['count']} reviews" if r.get("count") else "",
                f"{r['doctors']} doctors listed" if r.get("doctors") else ""]
        add(f"{r['site'].title()}: {', '.join(b for b in bits if b)} (search result)")
    if l.get("rivals_nearby"):
        add(f"{l['rivals_with_site']} of {l['rivals_nearby']} similar shops within 1 km have websites")
    for r in (f.get("rivals") or [])[:3]:
        if r.get("score") is not None:
            extras = [x for x, ok in (("has online booking", r.get("has_booking")), ("has WhatsApp button", r.get("has_whatsapp"))) if ok]
            add(f"Rival: {r['name']}, {r['metres']} m away, website score {r['score']}/100" + (", " + ", ".join(extras) if extras else ""))
    if (l.get("branches") or 1) > 1:
        add(f"{l['branches']} places in the city share this name: a growing local business with branches (a good sign, not a chain)")
    for c in dict.fromkeys(f.get("chain_signals") or []):
        add(f"Chain signal: {c}")
    return [f"[F{i}] {x}" for i, x in enumerate(facts, 1)]


BANNED = ("digital presence", "leverage", "elevate", "seamless", "cutting-edge", "cutting edge", "synergy",
          "revolutioniz", "hope you are doing well", "online footprint", "boost your business", "solutions")


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def rule_problems(brief: dict, facts_text: str) -> list[str]:
    """Checks that don't need a model: invented numbers, banned words, message length."""
    problems = []
    body = json.dumps({k: v for k, v in brief.items() if k != "why_call"}, ensure_ascii=False) + " " + " ".join(brief.get("why_call", []))
    body = re.sub(r"\[F\d+\]", "", body)
    allowed = _numbers(facts_text) | {"1", "2", "3", "4", "5", "7", "10", "15", "30", "24"}
    invented = sorted(_numbers(body) - allowed)
    if invented:
        problems.append(f"These numbers are not in the facts: {', '.join(invented)}. Remove them or use only fact numbers.")
    low = body.lower()
    for w in BANNED:
        if w in low:
            problems.append(f"Don't use the phrase '{w}'.")
    wa = brief.get("whatsapp", "")
    if len(wa.split()) > 75:
        problems.append(f"WhatsApp message is {len(wa.split())} words; keep it under 70.")
    if "http" in wa or "www." in wa:
        problems.append("No links in the WhatsApp message.")
    needed = ("call", "headline", "why_call") if brief.get("call") == "no" else (
        "call", "headline", "why_call", "sell", "opening", "questions", "pitch", "objections", "whatsapp")
    for key in needed:
        if not brief.get(key):
            problems.append(f"Missing '{key}'.")
    return problems


def write_brief(f: dict) -> dict:
    facts = fact_sheet(f)
    l = f["lead"]
    if any("store-locator" in c for c in f.get("chain_signals") or []):  # head office runs their website: no AI needed
        return {"ok": True, "rounds": 0, "usage": [], "facts": facts, "unresolved": [], "brief": {
            "call": "no", "headline": "National chain outlet: head office controls its website",
            "why_call": [c for c in dict.fromkeys(f["chain_signals"])]}}
    weak = l.get("website_status") in ("weak", "good") and (f.get("website") or {}).get("ok")
    facts_text = "\n".join(facts)
    user = (f"EXAMPLE FACTS\n{EXAMPLE_FACTS}\n\nEXAMPLE BRIEF\n{json.dumps(EXAMPLE_BRIEF, ensure_ascii=False)}\n\n"
            f"NOW WRITE THE BRIEF FOR THIS SHOP\nSuggested main offer for this shop type: {offer_for(l['category'], weak)}\n"
            f"FACTS\n{facts_text}")
    usage, brief, problems = [], None, []
    for round_ in range(3):
        prompt = user if not problems else (user + "\n\nYOUR PREVIOUS BRIEF\n" + json.dumps(brief, ensure_ascii=False)
                                            + "\n\nFIX THESE PROBLEMS AND RETURN THE FULL BRIEF\n- " + "\n- ".join(problems))
        brief, u = llm.write_json(SYSTEM, prompt, effort="medium", max_tokens=3500)
        usage.append(u)
        if not brief:
            return {"ok": False, "error": "AI unavailable", "facts": facts, "usage": usage}
        problems = rule_problems(brief, facts_text)
        if not problems:
            review, u = llm.write_json(CHECKER, f"FACTS\n{facts_text}\n\nBRIEF\n{json.dumps(brief, ensure_ascii=False)}",
                                       effort="medium", max_tokens=1200, temperature=0)
            usage.append(u)
            problems = [] if not review or review.get("ok") else review.get("problems") or []
        if not problems:
            break
        log.info("Brief for %s needs fixes: %s", l["name"], problems)
    return {"ok": True, "brief": brief, "facts": facts, "unresolved": problems, "rounds": round_ + 1, "usage": usage}
