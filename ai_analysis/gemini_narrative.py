"""
ai_analysis/gemini_narrative.py — Part 6A: per-listing AI narrative write-up
via the Google Gemini free-tier API (`config.GEMINI_MODEL`).

--------------------------------------------------------------------------
SCOPE (per PROJECT_STATUS.md Section 2, background-check depth item 1):
this module ONLY reasons over fields already scraped for a listing
(corporate debtor, asset description, price, dates, location, etc.) --
it does not look anything up externally. That's deliberate, not a
limitation to fix here: MCA company lookup (6B) and the unofficial
web-search news pass (6C) are separate, later parts. The prompt below
explicitly tells the model not to invent outside facts, so the narrative
stays honest about what it does and doesn't actually know.

This is SEPARATE FROM AND IN ADDITION TO scoring/rules.py's deterministic
score -- never a replacement for it (master decision, 2026-08-09).

--------------------------------------------------------------------------
FAILURE HANDLING (same "never silently drop, always flag" pattern used
throughout scraper/ and scoring/): a failed narrative call for one
listing -- missing key, network error, rate limit, a blocked/empty
response, malformed JSON back from the model -- never raises out of
generate_narrative()/generate_narratives_for_batch(). It comes back as
narrative=None plus a human-readable flag, same shape a caller already
knows how to handle from every other part of this pipeline. One bad
listing never blocks the rest of the batch.

--------------------------------------------------------------------------
RATE LIMITING: config.GEMINI_REQUEST_DELAY_SECONDS is applied between
calls in generate_narratives_for_batch() (not on a single ad-hoc call),
same pattern as the scrapers' REQUEST_DELAY_SECONDS. One retry (after
config.GEMINI_RETRY_BACKOFF_SECONDS) is attempted on HTTP 429/5xx only --
anything else (bad key, malformed request, blocked content) fails fast
since retrying won't help.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from typing import Optional

import requests

import sys
sys.path.insert(0, ".")
import config


REQUIRED_NARRATIVE_KEYS = ["summary", "price_read", "risk_notes", "data_gaps"]


class GeminiAPIError(Exception):
    """Raised for any HTTP-level or transport failure calling Gemini.
    Callers inside this module catch it and turn it into a flag; it should
    never escape generate_narrative()/generate_narratives_for_batch()."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def _as_dict(record) -> dict:
    return asdict(record) if not isinstance(record, dict) else record


def _build_prompt(record) -> str:
    """Builds a prompt containing ONLY the fields already scraped for this
    listing. Explicitly instructs the model not to assume/invent anything
    beyond them -- this is the "reason over what we already have, free,
    unlimited" tier from PROJECT_STATUS.md, not a research pass."""
    r = _as_dict(record)

    fields = {
        "corporate_debtor (the entity whose asset is being sold)": r.get("corporate_debtor"),
        "notice_type": r.get("notice_type"),
        "insolvency_professional (ip_name)": r.get("ip_name"),
        "auction_date": str(r.get("auction_date")) if r.get("auction_date") else None,
        "emd_due_date": str(r.get("emd_due_date")) if r.get("emd_due_date") else None,
        "reserve_price_inr": r.get("reserve_price"),
        "emd_amount_inr": r.get("emd_amount"),
        "nature_of_assets (free text from the notice)": r.get("nature_of_assets"),
        "plot_area_mentions (raw size strings found, unit not yet unified)": r.get("plot_area_mentions"),
        "location": r.get("location"),
        "possession_status": r.get("possession_status"),
        "land_classification": r.get("land_classification"),
        "auction_platform": r.get("auction_platform"),
        "issues_the_scraper_itself_flagged": r.get("flags"),
    }
    fields_json = json.dumps(fields, indent=2, default=str)

    return f"""You are helping a buyer read ONE structured auction/insolvency
listing scraped from IBBI (India's Insolvency and Bankruptcy Board). You are
given ONLY the JSON fields below -- nothing else. Do not use any outside
knowledge about this specific company, location, or asset, and do not guess
at a fair market price. If a field is null or missing, say so plainly instead
of filling the gap. If nothing here lets you judge whether the price is fair,
say that directly rather than offering a soft guess.

LISTING DATA:
{fields_json}

Respond with ONLY a JSON object (no markdown fences, no commentary) with
exactly these four keys:
- "summary": 2-4 plain-English sentences on what's being sold and the
  process (notice type, key dates), based strictly on the data above.
- "price_read": one or two sentences on the reserve price. Only comment on
  whether it seems notable relative to what's described IF the data
  actually supports that; otherwise say plainly that no independent
  valuation or comparable data is available here.
- "risk_notes": a JSON array of short strings (buyer-relevant risk points
  visible in this data, e.g. unclear possession status, ambiguous plot
  size, an EMD deadline that's very soon). Empty array if none stand out.
- "data_gaps": a JSON array of short strings naming which fields relevant
  to a buying decision are null/missing for this listing. Empty array if
  none.
"""


def _extract_text(response_json: dict) -> str:
    try:
        candidates = response_json.get("candidates") or []
        if not candidates:
            feedback = response_json.get("promptFeedback")
            raise GeminiAPIError(f"Gemini returned no candidates (possibly blocked): {feedback}")
        parts = candidates[0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError, TypeError) as e:
        raise GeminiAPIError(f"unexpected Gemini response shape: {response_json}") from e


def _parse_json_response(text: str) -> dict:
    cleaned = text.strip()
    # Defensive: response_mime_type=application/json should prevent markdown
    # fences, but strip them if the model adds any anyway.
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    return json.loads(cleaned)  # raises json.JSONDecodeError on failure


def call_gemini_raw(
    prompt: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    timeout: Optional[int] = None,
) -> dict:
    """Low-level single call. Returns the raw parsed response body.
    Raises GeminiAPIError on any missing-key/network/HTTP-level failure --
    callers decide whether/how to flag it (generate_narrative() does)."""
    api_key = api_key or config.GEMINI_API_KEY
    if not api_key:
        raise GeminiAPIError(
            "GEMINI_API_KEY not set. Get a free key at "
            "https://aistudio.google.com/apikey and put it in a local .env "
            "file (GEMINI_API_KEY=...) or export it in your shell -- never "
            "commit it."
        )
    model = model or config.GEMINI_MODEL
    url = config.GEMINI_API_ENDPOINT.format(model=model)
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "response_mime_type": "application/json",
        },
    }
    try:
        resp = requests.post(
            url,
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
            json=body,
            timeout=timeout or config.GEMINI_REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as e:
        raise GeminiAPIError(f"network error calling Gemini: {e}") from e

    if resp.status_code != 200:
        raise GeminiAPIError(
            f"Gemini API returned HTTP {resp.status_code}: {resp.text[:300]}",
            status_code=resp.status_code,
        )
    return resp.json()


def generate_narrative(
    record,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:
    """
    Generates the AI narrative for ONE listing. Never raises.

    Returns:
      {"narrative": {"summary": ..., "price_read": ..., "risk_notes": [...],
                      "data_gaps": [...]},
       "flags": []}
    on success, or:
      {"narrative": None, "flags": ["AI narrative call failed: <reason>"]}
    on any failure (missing key, network, rate limit, blocked/empty
    response, malformed JSON back from the model).
    """
    prompt = _build_prompt(record)
    last_err: Optional[Exception] = None

    for attempt in range(2):  # one retry, 429/5xx only
        try:
            raw = call_gemini_raw(prompt, api_key=api_key, model=model)
            text = _extract_text(raw)
            parsed = _parse_json_response(text)
            missing = [k for k in REQUIRED_NARRATIVE_KEYS if k not in parsed]
            if missing:
                return {
                    "narrative": parsed,
                    "flags": [f"AI response missing expected key(s): {missing}"],
                }
            return {"narrative": parsed, "flags": []}
        except GeminiAPIError as e:
            last_err = e
            if e.status_code in (429, 500, 502, 503) and attempt == 0:
                time.sleep(config.GEMINI_RETRY_BACKOFF_SECONDS)
                continue
            break
        except json.JSONDecodeError as e:
            # Malformed JSON back from the model (e.g. an unescaped
            # character inside a text field) is usually a one-off
            # generation slip, not a systematic problem -- retrying once
            # is worth it, same as a 429/5xx. Confirmed as a real,
            # non-rare failure mode on 2026-08-09's first live run
            # (1/5 listings), not just a hypothetical.
            last_err = e
            if attempt == 0:
                continue
            break

    return {"narrative": None, "flags": [f"AI narrative call failed: {last_err}"]}


def generate_narratives_for_batch(
    records: list,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    delay_seconds: Optional[float] = None,
) -> list[dict]:
    """Runs generate_narrative() across a batch, same order/length as
    `records`, pausing config.GEMINI_REQUEST_DELAY_SECONDS between calls
    to stay under the free tier's per-minute rate limit. One bad listing
    (see generate_narrative()'s failure handling) never stops the batch."""
    delay = config.GEMINI_REQUEST_DELAY_SECONDS if delay_seconds is None else delay_seconds
    results = []
    for i, record in enumerate(records):
        results.append(generate_narrative(record, api_key=api_key, model=model))
        if i < len(records) - 1:
            time.sleep(delay)
    return results
