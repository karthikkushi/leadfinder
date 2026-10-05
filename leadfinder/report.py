"""The morning email: today's best leads to call, with one-tap Call / WhatsApp / Map buttons and a CSV file."""
import csv
import datetime
import html
import io
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import quote_plus

import certifi

from .classify import host_of
from .config import CATEGORY_LABELS, COUNTRIES
from .db import DB

log = logging.getLogger("leadfinder")
ROOT = Path(__file__).resolve().parent.parent
STATUS = {
    "none": "No website",
    "social_only": "No website - only a social media page",
    "directory_only": "No website - only directory listings (Justdial etc.)",
    "dead": "Website not working",
    "weak": "Website needs work",
}


def _status_line(lead: dict) -> str:
    text = STATUS.get(lead["website_status"], lead["website_status"])
    if lead["website_status"] == "social_only" and lead.get("socials"):
        sites = sorted({host_of(s).split(".")[0].capitalize() for s in lead["socials"] if host_of(s)})
        text = f"No website - only {', '.join(sites[:3])}"
    if lead.get("issues"):
        text += ": " + "; ".join(lead["issues"][:4])
    return text


def _links(lead: dict) -> dict:
    digits = (lead.get("phone_intl") or "").lstrip("+")
    maps = ("https://www.google.com/maps/search/?api=1&query="
            + quote_plus(f"{lead['name']} {lead.get('locality') or ''} {lead['city']}"))
    return {"call": f"tel:{lead.get('phone_intl')}", "whatsapp": f"https://wa.me/{digits}", "maps": maps}


def _card(lead: dict) -> str:
    e = html.escape
    links = _links(lead)
    area = lead.get("locality")
    same = area and area.lower().replace("mysore", "mysuru").replace("bangalore", "bengaluru") == lead["city"].lower()
    place = lead["city"] if not area or same else f"{area}, {lead['city']}"
    colour = "#b42318" if lead["priority"] == 1 else "#b54708"
    website = (f' &nbsp;<a href="{e(lead["website"])}" style="color:#475467">website</a>'
               if lead.get("website") else "")
    btn = ("display:inline-block;padding:7px 12px;margin:6px 6px 0 0;border-radius:8px;text-decoration:none;"
           "font-size:13px;font-weight:600;")
    return f"""
<tr><td style="padding:12px 14px;border-bottom:1px solid #eaecf0">
  <div style="font-size:15px;font-weight:700;color:#101828">{e(lead['name'])}</div>
  <div style="font-size:13px;color:#475467;margin-top:2px">{e(CATEGORY_LABELS.get(lead['category'], lead['category']))}
    &middot; {e(place)}</div>
  <div style="font-size:13px;color:{colour};margin-top:4px">{e(_status_line(lead))}</div>
  <div style="font-size:14px;color:#101828;margin-top:4px">{e(lead.get('phone') or '')}{website}</div>
  <a href="{e(links['call'])}" style="{btn}background:#1570ef;color:#fff">Call</a>
  <a href="{e(links['whatsapp'])}" style="{btn}background:#12b76a;color:#fff">WhatsApp</a>
  <a href="{e(links['maps'])}" style="{btn}background:#f2f4f7;color:#344054">Map</a>
</td></tr>"""


def _section(title: str, note: str, leads: list[dict]) -> str:
    if not leads:
        return ""
    rows = "".join(_card(l) for l in leads)
    return f"""
<h2 style="font-size:17px;color:#101828;margin:26px 0 4px">{html.escape(title)} ({len(leads)})</h2>
<div style="font-size:13px;color:#667085;margin-bottom:8px">{html.escape(note)}</div>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"
       style="border:1px solid #eaecf0;border-radius:10px;border-collapse:separate">{rows}</table>"""


def _csv(leads: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Name", "Type", "Area", "City", "Country", "Phone", "Website status", "Website", "Social pages",
                "Address", "Call link", "WhatsApp link", "Map link"])
    for l in leads:
        links = _links(l)
        w.writerow([l["name"], CATEGORY_LABELS.get(l["category"], l["category"]), l.get("locality") or "", l["city"],
                    COUNTRIES.get(l["country"], (l["country"],))[0], l.get("phone") or "", _status_line(l),
                    l.get("website") or "", " ".join(l.get("socials") or []), l.get("address") or "",
                    links["call"], links["whatsapp"], links["maps"]])
    return buf.getvalue().encode("utf-8-sig")  # BOM so Excel opens it correctly


def build(data: dict, app_url: str | None) -> tuple[str, str]:
    leads = data["leads"]
    no_site = [l for l in leads if l["priority"] == 1]
    improve = [l for l in leads if l["priority"] == 2]
    cities = sorted({l["city"] for l in leads})
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    subject = f"{len(leads)} shops to call today" + (f" - {', '.join(cities[:3])}" if cities else "") + \
              f" ({today:%a %d %b})"
    t = data["totals"]
    jobs = "".join(f"<li>{html.escape(j['city'])}: {html.escape(j.get('message') or j['status'])}</li>"
                   for j in data["jobs"])
    callbacks = "".join(
        f"<li><b>{html.escape(c['name'])}</b> - <a href=\"tel:{html.escape(c['phone_intl'] or '')}\">"
        f"{html.escape(c['phone'] or '')}</a> ({html.escape(c['city'])})"
        f"{' - ' + html.escape(c['notes']) if c.get('notes') else ''}</li>" for c in data["callbacks"])
    app = (f'<p style="margin:18px 0"><a href="{html.escape(app_url)}" style="display:inline-block;padding:10px 16px;'
           f'border-radius:8px;background:#101828;color:#fff;text-decoration:none;font-weight:600">'
           f'Open the calling app to record results</a></p>') if app_url else ""
    body = f"""<!doctype html><html><body style="margin:0;background:#f9fafb">
<div style="max-width:640px;margin:0 auto;padding:20px 16px;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif">
<h1 style="font-size:21px;color:#101828;margin:0 0 6px">Good morning! {len(leads)} shops to call today</h1>
<div style="font-size:14px;color:#475467">This morning the agents found <b>{data['new_found']}</b> new shops and
checked <b>{data['checked']}</b> websites. Waiting in the database: <b>{t['no_website']}</b> shops with no website,
<b>{t['improve_website']}</b> whose website needs work.</div>
{app}
{f'<h2 style="font-size:17px;color:#101828;margin:22px 0 6px">Callbacks due</h2><ul style="font-size:14px;color:#344054">{callbacks}</ul>' if callbacks else ''}
{_section("No website - call these first", "Pitch: a simple website with Call and WhatsApp buttons, photos and a map.", no_site)}
{_section("Website needs work", "Pitch: a modern, fast, phone-friendly redesign. Mention the problems listed.", improve)}
{f'<h3 style="font-size:14px;color:#344054;margin:24px 0 4px">Today\'s searches</h3><ul style="font-size:13px;color:#667085">{jobs}</ul>' if jobs else ''}
<p style="font-size:12px;color:#98a2b3;margin-top:24px">The same list is attached as a spreadsheet (CSV).
Business data: Overture Maps Foundation and &copy; OpenStreetMap contributors.</p>
</div></body></html>"""
    return subject, body


def send_morning_email(since_hours: float = 4, dry_run: bool = False):
    db = DB()
    since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=since_hours)).isoformat()
    limit = int(os.environ.get("REPORT_LEADS", "60"))
    data = db.report(since, limit, mark=False)
    subject, body = build(data, os.environ.get("APP_URL"))
    attachment = _csv(data["leads"])
    out = ROOT / "logs"
    out.mkdir(exist_ok=True)
    (out / "morning_email.html").write_text(body, encoding="utf-8")
    (out / "morning_leads.csv").write_bytes(attachment)

    user, password = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_APP_PASSWORD")
    to = [a.strip() for a in os.environ.get("REPORT_TO", "").split(",") if a.strip()]
    if dry_run or not (user and password and to):
        if not dry_run:
            log.warning("Email not set up yet (GMAIL_USER / GMAIL_APP_PASSWORD / REPORT_TO); saved logs/morning_email.html")
        log.info("Email preview: %s (%d leads)", subject, len(data["leads"]))
        return

    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, f"Lead Finder <{user}>", ", ".join(to)
    msg.set_content(f"{subject}\n\nOpen this email in Gmail to see the list, or open the attached spreadsheet.")
    msg.add_alternative(body, subtype="html")
    msg.add_attachment(attachment, maintype="text", subtype="csv",
                       filename=f"leads-{datetime.date.today():%Y-%m-%d}.csv")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(cafile=certifi.where())) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)
    db.call("worker_mark_emailed", p_ids=[l["id"] for l in data["leads"]])
    log.info("Sent '%s' to %s", subject, ", ".join(to))
