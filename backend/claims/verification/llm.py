"""Optional Google Gemini helper. Every caller has a rule-based fallback, so the
system works fully offline when GEMINI_API_KEY is empty."""
import json
import logging

import requests
from django.conf import settings

log = logging.getLogger(__name__)


def enabled():
    return bool(settings.CLAIMS["GEMINI_API_KEY"])


def _call(prompt, json_mode):
    if not enabled():
        return None
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.CLAIMS['GEMINI_MODEL']}:generateContent?key={settings.CLAIMS['GEMINI_API_KEY']}"
    )
    config = {"temperature": 0.1}
    if json_mode:
        config["responseMimeType"] = "application/json"
    try:
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": config}, timeout=40)
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as exc:
        log.warning("Gemini call failed: %s", exc)
        return None


def ask_json(prompt):
    text = _call(prompt, json_mode=True)
    if not text:
        return None
    try:
        cleaned = text.strip().removeprefix("```json").removesuffix("```").strip()
        return json.loads(cleaned)
    except (ValueError, TypeError):
        return None


def ask_text(prompt):
    return _call(prompt, json_mode=False)
