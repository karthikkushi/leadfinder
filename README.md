# Lead Finder

**What:** AI agents that find local shops with no website or a weak one, grade their site, research the shop and write a short sales brief; a phone app shows the day's best leads to call.
**For:** web agencies and freelancers who sell websites to local businesses (built for my own agency, Kalvio Build).
**Run:** `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`, then `.venv/bin/python -m leadfinder audit https://example.com` grades any website. The full pipeline also needs a Supabase project (see "Not done yet").

Live app: <https://karthikkushi.github.io/leadfinder/> (access code required).

```
$ .venv/bin/python -m leadfinder audit http://example.com
{
  "status": "weak",
  "issues": [
    "No HTTPS - browsers show 'Not secure'",
    "Very little content",
    "No tap-to-call or WhatsApp button"
  ],
  ...
}
```

## How it works

1. **Find:** shops by city and business type from Overture Maps and OpenStreetMap, both free open data
   (`leadfinder/sources/`, categories and countries in `leadfinder/config.py`).
2. **Check:** find each shop's website and grade it: HTTPS, phone layout, content, call/WhatsApp buttons, map,
   booking (`verify.py`, `research.py`). Shops with a good site go to the bottom of the list (`classify.py`).
3. **Research and brief:** for hot leads, public facts (the website, Instagram/Facebook counts and ratings seen in
   search results) go to a free Groq model, which writes a call brief. Every number in the brief must appear in the
   facts, so it cannot invent ratings (`brief.py`).
4. **Deliver:** GitHub Actions runs the agents every morning and emails the top leads
   (`.github/workflows/morning.yml`); the caller works through them and logs follow-ups in the web app (`web/`,
   published to GitHub Pages).

Data lives in Supabase and is reached only through database functions that check an access code.

## Commands

```
python -m leadfinder audit <url>                       # grade one website
python -m leadfinder queue Bengaluru --country IN      # add a city to search
python -m leadfinder worker --minutes 20               # run the agents
python -m leadfinder briefs                            # research today's hot leads
python -m leadfinder email --dry-run                   # write the morning email to logs/
```

Settings go in `.env` (copy `.env.example`).

Checks: `.venv/bin/pip install pytest pyflakes`, then `.venv/bin/python -m pytest` and
`.venv/bin/python -m pyflakes leadfinder tests`.

## Not done yet

- The database setup is not in this repo: the tables and the 21 functions the agents call were made in the Supabase
  dashboard (only `supabase/follow_ups.sql` is here), so a new Supabase project can't be set up from the repo yet.
- The morning email covers India only (`REPORT_COUNTRIES=IN`); US shops are found and checked but not emailed.
- The `.command` files are macOS double-click helpers for my own setup.
