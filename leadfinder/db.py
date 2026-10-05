"""Talks to the Supabase database through its locked-down functions (the worker access code is checked there)."""
import os
import time

import httpx


class DB:
    def __init__(self):
        self.url = os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1/rpc/"
        self.code = os.environ["WORKER_CODE"]
        self.http = httpx.Client(timeout=60, headers={"apikey": os.environ["SUPABASE_KEY"],
                                                      "Content-Type": "application/json"})

    def call(self, fn: str, **args):
        for attempt in range(4):
            try:
                r = self.http.post(self.url + fn, json={"p_code": self.code, **args})
                if r.status_code >= 500 or r.status_code == 429:
                    raise httpx.HTTPStatusError(r.text, request=r.request, response=r)
                if r.status_code >= 400:
                    raise RuntimeError(f"{fn}: {r.text[:300]}")
                return r.json() if r.content else None
            except (httpx.TransportError, httpx.HTTPStatusError):
                if attempt == 3:
                    raise
                time.sleep(5 * (attempt + 1))

    def claim_job(self):
        return self.call("worker_claim_job")

    def finish_job(self, job_id: int, status: str, found: int, added: int, message: str):
        return self.call("worker_finish_job", p_id=job_id, p_status=status, p_found=found, p_added=added,
                         p_message=message)

    def upsert_leads(self, rows: list[dict]) -> dict:
        totals = {"inserted": 0, "updated": 0}
        clean = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
        for i in range(0, len(clean), 400):
            res = self.call("worker_upsert_leads", p_rows=clean[i:i + 400])
            totals["inserted"] += res["inserted"]
            totals["updated"] += res["updated"]
        return totals

    def next_checks(self, limit: int, priority: int, country: str | None = None) -> list[dict]:
        return self.call("worker_next_checks", p_limit=limit, p_priority=priority, p_country=country) or []

    def save_checks(self, rows: list[dict]):
        if rows:
            return self.call("worker_save_checks", p_rows=rows)

    def plan(self, targets: list[tuple[str, str]], days: int = 30, backlog: int = 1500) -> dict:
        return self.call("worker_plan", p_targets=[{"country": c, "city": t} for c, t in targets], p_days=days,
                         p_backlog=backlog)

    def report(self, since: str, limit: int, mark: bool = True, countries: list[str] | None = None) -> dict:
        return self.call("worker_report", p_since=since, p_limit=limit, p_mark=mark, p_countries=countries)
