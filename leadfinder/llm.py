"""Free LLM (Groq free tier) for the judgement calls the rules can't make. Optional: without a key the
agents skip these calls and leave such leads marked "not verified"."""
import json
import logging
import os

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
