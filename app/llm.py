"""Groq LLM client (OpenAI-compatible endpoint) with JSON output, retries and model fallback."""
from __future__ import annotations

import json
import os
import re
import time

import httpx

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class LLMError(RuntimeError):
    pass


def _extract_json(text: str) -> dict:
    # Some models wrap JSON in ```json fences or add <think> blocks (qwen3). Strip them.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise LLMError("Model did not return JSON")
    return json.loads(m.group(0))


def chat_json(system: str, user: str, temperature: float = 0.3) -> dict:
    """Ask the model for a JSON object. Tries the primary model, then the fallback model."""
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise LLMError("GROQ_API_KEY not set")
    models = [os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
              os.getenv("GROQ_FALLBACK_MODEL", "qwen/qwen3-32b")]
    last_err: Exception | None = None
    for model in models:
        for attempt in range(2):
            try:
                r = httpx.post(
                    GROQ_URL,
                    headers={"Authorization": f"Bearer {key}"},
                    json={
                        "model": model,
                        "temperature": temperature,
                        "response_format": {"type": "json_object"},
                        "messages": [{"role": "system", "content": system},
                                     {"role": "user", "content": user}],
                    },
                    timeout=60,
                )
                if r.status_code == 429:  # rate limited on free tier -> back off
                    time.sleep(2 * (attempt + 1))
                    continue
                r.raise_for_status()
                return _extract_json(r.json()["choices"][0]["message"]["content"])
            except (httpx.HTTPError, KeyError, json.JSONDecodeError, LLMError) as e:
                last_err = e
                time.sleep(1)
    raise LLMError(f"All LLM attempts failed: {last_err}")
