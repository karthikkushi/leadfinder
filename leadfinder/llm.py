"""Free LLM (Groq free tier) for the judgement calls the rules can't make. Optional: without a key the
agents skip these calls and leave such leads marked "not verified"."""
import json
import logging
import os
import re
import time

import httpx

log = logging.getLogger(__name__)
MODELS = ["openai/gpt-oss-20b", "llama-3.1-8b-instant"]
_disabled = False


def ask_json(system: str, user: str) -> dict | None:
    global _disabled
    key = os.environ.get("GROQ_API_KEY")
    if not key or _disabled:
        return None
    for model in MODELS:
        body = {"model": model, "temperature": 0, "max_tokens": 600,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = "low"
        try:
            r = httpx.post("https://api.groq.com/openai/v1/chat/completions", json=body, timeout=45,
                           headers={"Authorization": f"Bearer {key}"})
            if r.status_code == 401:
                _disabled = True
                log.warning("Groq key rejected; continuing without the LLM")
                return None
            if r.status_code == 429:
                log.info("Groq %s rate limited, trying next model", model)
                continue
            r.raise_for_status()
            return json.loads(r.json()["choices"][0]["message"]["content"])
        except Exception as e:
            log.info("LLM call on %s failed: %s", model, e)
    return None


def _wait_seconds(value: str | None) -> float:
    """Groq's reset headers look like '7.66s', '1m26.4s' or '690ms'."""
    if not value:
        return 10.0
    total = 0.0
    for num, unit in re.findall(r"([\d.]+)(ms|s|m|h)", value):
        total += float(num) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[unit]
    return min(max(total, 1.0), 120.0)


def write_json(system: str, user: str, model: str = "openai/gpt-oss-120b", effort: str = "medium",
               max_tokens: int = 3000, temperature: float = 0.4) -> tuple[dict | None, dict]:
    """One careful call to the big free model. Waits out the per-minute limit instead of failing.
    Returns (answer or None, usage)."""
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None, {}
    body = {"model": model, "temperature": temperature, "max_tokens": max_tokens, "reasoning_effort": effort,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    for attempt in range(6):
        try:
            r = httpx.post("https://api.groq.com/openai/v1/chat/completions", json=body, timeout=120,
                           headers={"Authorization": f"Bearer {key}"})
        except httpx.TransportError as e:
            log.info("Groq connection problem (%s), retrying", e)
            time.sleep(10)
            continue
        if r.status_code == 429:
            wait = _wait_seconds(r.headers.get("retry-after") and r.headers["retry-after"] + "s"
                                 or r.headers.get("x-ratelimit-reset-tokens"))
            if "per day" in r.text.lower() or "tpd" in r.text.lower() or "rpd" in r.text.lower():
                log.warning("Groq daily limit reached for %s", model)
                return None, {}
            log.info("Groq per-minute limit, waiting %.0fs", wait)
            time.sleep(wait + 1)
            continue
        if r.status_code >= 500:
            time.sleep(10)
            continue
        if r.status_code >= 400:
            log.warning("Groq error %s: %s", r.status_code, r.text[:300])
            return None, {}
        data = r.json()
        try:
            answer = json.loads(data["choices"][0]["message"]["content"])
            if isinstance(answer, dict):
                return answer, data.get("usage", {})
            log.info("Groq answer was not a JSON object, asking again")
        except (json.JSONDecodeError, KeyError, TypeError):
            log.info("Groq answer was not valid JSON, asking again")
            continue
    return None, {}
