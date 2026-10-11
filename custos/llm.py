"""Minimal provider-agnostic chat call. LLM_PROVIDER = ollama | openai | anthropic."""
import json
import os
import re

import httpx

PROVIDER = os.getenv("LLM_PROVIDER", "ollama")
MODEL = os.getenv("LLM_MODEL") or {
    "ollama": "qwen2.5-coder:7b",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-5-5",
}[PROVIDER]


def chat(system: str, user: str, model: str | None = None, temperature: float = 0.0) -> str:
    model = model or MODEL
    if PROVIDER == "anthropic":
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
            json={"model": model, "max_tokens": 1500, "temperature": temperature, "system": system,
                  "messages": [{"role": "user", "content": user}]},
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["content"][0]["text"]
    base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1") if PROVIDER == "openai" \
        else os.getenv("OLLAMA_URL", "http://localhost:11434") + "/v1"
    headers = {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY', 'ollama')}"}
    r = httpx.post(
        f"{base}/chat/completions", headers=headers, timeout=180,
        json={"model": model, "temperature": temperature,
              "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def extract_json(text: str):
    """Pull the first JSON object/array out of a model reply (handles ``` fences)."""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start = min([i for i in (text.find("["), text.find("{")) if i != -1], default=-1)
    if start == -1:
        raise ValueError("no JSON in reply")
    return json.JSONDecoder().raw_decode(text[start:])[0]
