"""
scoring/rules.py — Part 5A: rule-based scoring, scorable-now criteria only.

--------------------------------------------------------------------------
SCOPE: this file now covers all five configured score criteria across
Parts 5A/5B/5C — `price_vs_reserve` + `location_match` (5A),
`possession_status` + `land_classification` (5B), and `plot_size_fit`
(5C). `config.SCORE_WEIGHTS` itself is still all `None` (owner hasn't set
real weights yet), so each part's `partial_score_5x` stays an explicitly-
labeled partial average of that part's own criteria, not presented as
the finished weighted score — see Part 7 for where those get combined.

--------------------------------------------------------------------------
price_vs_reserve — RELATIVE, not against a hard ceiling (owner decision,
2026-08-09; config.BUDGET_CEILING = None): there is no separately-scraped
"market value" field to discount reserve_price against, so "how good a
discount to the reserve price it is" is read the only way the scraped
data supports — a listing's reserve_price relative to the reserve prices
of the *other* listings in the same scoring batch. A cheaper reserve
price than most of the batch scores higher; a pricier one scores lower.
This is a percentile rank (0-100, ties averaged), not a raw price and not
a comparison to any fixed number. Recomputed fresh per batch — a listing
scored yesterday's batch will not carry the same number today, by design.

Listings with reserve_price = None can't be percentile-ranked at all;
scored as None here and flagged, never guessed/defaulted. A batch with
only one priced listing has no peers to rank against either — scored
neutral (50) and flagged, not treated as "cheapest" or "priciest".

reserve_price = 0 is treated the same way as None -- excluded from the
peer group, scored None, flagged -- NOT scored as "cheapest possible"
(discovered on a real run, 2026-08-09: scraper/ibbi.py's own
_parse_reserve_price() docstring already notes IBBI's site uses a
literal "0" as a placeholder for "no reserve price fixed / as-per-terms"
on some listings, not a genuine free/near-free asset. Percentile-ranking
that as the cheapest listing in the batch would hand it a perfect
price_vs_reserve score and put it at the top of the report for the
wrong reason. This is a scoring-layer decision, not a scraper bug --
the scraper is correctly capturing what the page actually says.)

--------------------------------------------------------------------------
location_match — BONUS, not a filter (owner decision, 2026-08-09;
config.PREFERRED_REGIONS = ["Delhi", "Rajpura", "Madhya Pradesh"]):
every listing gets scored, including listings outside the preferred
regions and listings whose location isn't known yet (Part 3C's details-
PDF parse hasn't run / found nothing). Both of those cases get the same
neutral baseline (config.LOCATION_MATCH_NEUTRAL) — never a penalty.
Matching a preferred region (case-insensitive substring) adds
config.LOCATION_MATCH_BONUS on top. Nothing is ever excluded from the
batch for its location.
--------------------------------------------------------------------------
"""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Optional

import sys
sys.path.insert(0, ".")
import config


def _as_dict(record) -> dict:
    return asdict(record) if not isinstance(record, dict) else record


# ---------------------------------------------------------------------------
# price_vs_reserve
# ---------------------------------------------------------------------------

def compute_price_vs_reserve_scores(records: list) -> list[dict]:
    """
    Percentile-rank reserve_price across the batch. Returns a list, same
    order/length as `records`, of:
      {"score": float 0-100, "flags": [...]}   -- cheaper reserve = higher score
      {"score": None, "flags": ["missing reserve_price..."]}   -- can't rank
      {"score": None, "flags": ["...literal 0..."]}   -- placeholder, not a real price
      {"score": 50.0, "flags": ["only one priced listing..."]} -- no peers
    Score of None must never be silently treated as 0 downstream -- it
    means "not scored", not "worst score".
    """
    recs = [_as_dict(r) for r in records]
    priced = [
        (i, r["reserve_price"]) for i, r in enumerate(recs)
        if r.get("reserve_price") is not None and r.get("reserve_price") > 0
    ]
    prices = [p for _, p in priced]
    n = len(prices)

    results = [None] * len(recs)

    for i, r in enumerate(recs):
        price = r.get("reserve_price")
        if price is None:
            results[i] = {
                "score": None,
                "flags": ["price_vs_reserve not scored: reserve_price missing for this listing"],
            }
            continue
        if price == 0:
            results[i] = {
                "score": None,
                "flags": [
                    "price_vs_reserve not scored: reserve_price is literal "
                    "0 on IBBI's site, which is a known placeholder for "
                    "'no reserve price fixed / as-per-terms', not a real "
                    "price -- treated as unknown, not as the cheapest listing"
                ],
            }
            continue
        if n == 1:
            results[i] = {
                "score": 50.0,
                "flags": [
                    "price_vs_reserve scored neutral (50): this is the only "
                    "listing in the batch with a reserve_price, nothing to "
                    "rank it against"
                ],
            }
            continue
        less = sum(1 for p in prices if p < price)
        equal = sum(1 for p in prices if p == price)
        # Average-rank percentile of THIS price among all priced listings,
        # 0.0 = cheapest, 1.0 = priciest. Ties share the same percentile.
        percentile_of_price = (less + 0.5 * (equal - 1)) / (n - 1)
        score = round((1 - percentile_of_price) * 100, 1)
        results[i] = {"score": score, "flags": []}

    return results


# ---------------------------------------------------------------------------
# location_match
# ---------------------------------------------------------------------------

def score_location_match(location: Optional[str]) -> dict:
    """
    Score one listing's location field against config.PREFERRED_REGIONS.
    Never excludes anything -- a non-match or unknown location both get
    the same neutral baseline, only a match adds the bonus on top.
    """
    if not location or not str(location).strip():
        return {
            "score": config.LOCATION_MATCH_NEUTRAL,
            "matched_region": None,
            "flags": [
                "location_match scored neutral: location not yet known "
                "(details PDF not parsed, or field genuinely blank) -- "
                "not a penalty"
            ],
        }

    loc_lower = str(location).lower()
    for region in config.PREFERRED_REGIONS:
        if region.lower() in loc_lower:
            return {
                "score": config.LOCATION_MATCH_NEUTRAL + config.LOCATION_MATCH_BONUS,
                "matched_region": region,
                "flags": [],
            }

    return {
        "score": config.LOCATION_MATCH_NEUTRAL,
        "matched_region": None,
        "flags": [],
    }


# ---------------------------------------------------------------------------
# Batch entry point
# ---------------------------------------------------------------------------

def score_batch_5a(records: list) -> list[dict]:
    """
    Score a batch of scraped records (IBBIRecord or dict) on the two 5A
    criteria. Returns one result dict per input record, same order:

      {
        "listing_key_fields": {...identity fields, for cross-reference...},
        "price_vs_reserve": {"score": float|None, "flags": [...]},
        "location_match": {"score": float, "matched_region": str|None, "flags": [...]},
        "partial_score_5a": float|None,   -- see note below
        "flags": [...],   -- union of both criteria's flags
      }

    `partial_score_5a` is a plain average of whichever of the two 5A
    component scores are actually available for that listing -- it is
    NOT the final weighted score from config.SCORE_WEIGHTS. Those weights
    are still all None (owner hasn't set them, and 3 of 5 criteria --
    possession_status, land_classification, plot_size_fit -- aren't
    scored until 5B/5C exist). Treating a 2-of-5 average as "the score"
    would overstate what's actually been evaluated, so it's kept
    explicitly labeled "partial" rather than presented as a finished
    ranking. Once 5B/5C land and the owner sets real SCORE_WEIGHTS, this
    should be replaced by the proper weighted sum across all five.
    """
    recs = [_as_dict(r) for r in records]
    price_scores = compute_price_vs_reserve_scores(recs)

    results = []
    for rec, price_result in zip(recs, price_scores):
        loc_result = score_location_match(rec.get("location"))

        components = []
        if price_result["score"] is not None:
            components.append(price_result["score"])
        if loc_result["score"] is not None:
            components.append(loc_result["score"])
        partial_score = round(sum(components) / len(components), 1) if components else None

        results.append({
            "listing_key_fields": {
                "corporate_debtor": rec.get("corporate_debtor"),
                "ip_name": rec.get("ip_name"),
                "notice_type": rec.get("notice_type"),
                "nature_of_assets": rec.get("nature_of_assets"),
            },
            "price_vs_reserve": price_result,
            "location_match": loc_result,
            "partial_score_5a": partial_score,
            "flags": price_result["flags"] + loc_result["flags"],
        })

    return results


# ---------------------------------------------------------------------------
# Part 5B — possession_status + land_classification
#
# Both fields come from scraper.ibbi.enrich_record_with_notice() (notice_pdf
# parsing). Same "never guess, never penalize unknown" philosophy as 5A.
# ---------------------------------------------------------------------------

def score_possession_status(possession_status: Optional[str]) -> dict:
    """Score one listing's possession_status. physical/symbolic/unknown all
    map to config.POSSESSION_STATUS_SCORES -- unknown (None, i.e. not found
    or notice PDF unavailable/unparseable) is a neutral score, never a
    penalty, same treatment as location_match's unknown-location path."""
    key = possession_status if possession_status in ("physical", "symbolic") else "unknown"
    score = config.POSSESSION_STATUS_SCORES[key]
    flags = []
    if key == "unknown":
        flags.append(
            "possession_status scored neutral: not found in the notice PDF "
            "(or the notice PDF wasn't available/parseable) -- not a penalty"
        )
    return {"score": score, "possession_status": possession_status, "flags": flags}


def score_land_classification(land_classification: Optional[str]) -> dict:
    """Score one listing's land_classification against
    config.PREFERRED_LAND_CLASSIFICATIONS. Same bonus-not-filter pattern as
    score_location_match: unknown classification and non-preferred
    classification both get the same neutral baseline; a preferred-list
    match adds the bonus. With PREFERRED_LAND_CLASSIFICATIONS empty (the
    default until the owner sets a preference), every classification --
    including unknown -- scores the same neutral baseline."""
    if not land_classification:
        return {
            "score": config.LAND_CLASSIFICATION_NEUTRAL,
            "matched_classification": None,
            "flags": [
                "land_classification scored neutral: not found in the "
                "searched text -- not a penalty"
            ],
        }

    for preferred in config.PREFERRED_LAND_CLASSIFICATIONS:
        if preferred.lower() == land_classification.lower():
            return {
                "score": config.LAND_CLASSIFICATION_NEUTRAL + config.LAND_CLASSIFICATION_BONUS,
                "matched_classification": preferred,
                "flags": [],
            }

    return {
        "score": config.LAND_CLASSIFICATION_NEUTRAL,
        "matched_classification": None,
        "flags": [],
    }


def score_batch_5b(records: list) -> list[dict]:
    """Score a batch of scraped+notice-enriched records on the two 5B
    criteria. Returns one result dict per input record, same order:

      {
        "listing_key_fields": {...same identity fields as score_batch_5a...},
        "possession_status": {"score": float, "possession_status": str|None, "flags": [...]},
        "land_classification": {"score": float, "matched_classification": str|None, "flags": [...]},
        "partial_score_5b": float,   -- see note below
        "flags": [...],
      }

    `partial_score_5b` is a plain average of these two 5B scores only --
    like 5A's partial_score_5a, it is NOT the final weighted score from
    config.SCORE_WEIGHTS (still all None; plot_size_fit/5C is still
    outstanding, and 5A + 5B haven't been combined into one ranking yet --
    that's Part 7's job once 5C exists and real weights are set). Unlike
    5A's partial score, both 5B components always return a number (unknown
    is scored neutral, never None), so this average is never itself None.
    """
    recs = [_as_dict(r) for r in records]

    results = []
    for rec in recs:
        possession_result = score_possession_status(rec.get("possession_status"))
        classification_result = score_land_classification(rec.get("land_classification"))

        partial_score = round(
            (possession_result["score"] + classification_result["score"]) / 2, 1
        )

        results.append({
            "listing_key_fields": {
                "corporate_debtor": rec.get("corporate_debtor"),
                "ip_name": rec.get("ip_name"),
                "notice_type": rec.get("notice_type"),
                "nature_of_assets": rec.get("nature_of_assets"),
            },
            "possession_status": possession_result,
            "land_classification": classification_result,
            "partial_score_5b": partial_score,
            "flags": possession_result["flags"] + classification_result["flags"],
        })

    return results


# ---------------------------------------------------------------------------
# Part 5C — plot_size_fit
#
# Input is scraper.ibbi's `plot_area_mentions` (Part 3C): a list of RAW
# strings like ["7,450 sq. ft", "2 acres"], deliberately left unconverted/
# unpicked at extraction time because a listing can have several area
# figures (land vs building) and guessing which one is "the" plot size
# would be silent misinformation. Turning that into ONE clean number (or
# correctly flagging why it can't be) is 5C's job, done here rather than
# in scraper/ibbi.py since it's scoring-layer judgment, not extraction.
#
# Owner decision (2026-08-09): no minimum plot size right now
# (config.MIN_PLOT_SIZE_SQFT = None) -- same "bonus not filter, never
# penalize missing/undecided data" pattern as every other criterion here.
# ---------------------------------------------------------------------------

# Conversion factors to sq ft (standard Indian real-estate approximations).
# Order matters in _normalize_area_to_sqft below: check the more specific
# units (acre/hectare/gunta/cent) before falling back to the ft/m checks,
# since e.g. "cent" would otherwise false-match a bare "m" substring check.
_SQFT_PER_ACRE = 43560.0
_SQFT_PER_HECTARE = 107639.0
_SQFT_PER_GUNTA = 1089.0     # 1 gunta = 121 sq yards, standard India measure
_SQFT_PER_CENT = 435.6       # 1 cent = 40.46 sq m, common in Kerala/Tamil Nadu
_SQFT_PER_SQM = 10.7639


def _normalize_area_to_sqft(mention: str) -> Optional[float]:
    """Parse one raw area-mention string (e.g. '7,450 sq. ft', '2 Acres')
    into a plain sq-ft float. Returns None if the number or unit can't be
    confidently read -- never guessed."""
    m = re.match(r"\s*([\d,]+\.?\d*)\s*(.+?)\s*$", mention)
    if not m:
        return None
    num_str, unit_raw = m.groups()
    try:
        num = float(num_str.replace(",", ""))
    except ValueError:
        return None

    unit = unit_raw.lower().replace(".", "").strip()
    if unit.startswith("acre"):
        return num * _SQFT_PER_ACRE
    if unit.startswith("hectare"):
        return num * _SQFT_PER_HECTARE
    if unit.startswith("gunta"):
        return num * _SQFT_PER_GUNTA
    if unit.startswith("cent"):
        return num * _SQFT_PER_CENT
    if "ft" in unit or "feet" in unit:
        return num
    if "m" in unit:   # sq mtrs / meters / metres / m, checked last on
        return num * _SQFT_PER_SQM   # purpose so it can't shadow the above
    return None


def _parse_plot_size_sqft(area_mentions: list) -> tuple[Optional[float], list[str]]:
    """Turn scraper.ibbi's raw `plot_area_mentions` list into ONE clean
    sq-ft number, or (None, flags) when that isn't safely possible.
    Returns (plot_size_sqft, flags)."""
    if not area_mentions:
        return None, [
            "plot_size_fit not scored: no area figure found for this "
            "listing (see plot_area_mentions / Part 3C flags)"
        ]

    converted, unparsed = [], []
    for mention in area_mentions:
        val = _normalize_area_to_sqft(mention)
        (converted if val is not None else unparsed).append(val if val is not None else mention)

    flags = []
    if unparsed:
        flags.append(
            f"plot_size_fit: could not parse unit for {unparsed!r} -- "
            f"ignored, not guessed"
        )
    if not converted:
        flags.append(
            "plot_size_fit not scored: no area mention could be converted "
            "to a clean number"
        )
        return None, flags

    distinct = sorted(set(round(v, 1) for v in converted))
    # Treat mentions that converge to (near enough) the same figure as one
    # value -- e.g. the same area repeated elsewhere in the notice, or
    # rounding noise -- rather than flagging every duplicate as ambiguous.
    if len(distinct) == 1 or (max(distinct) - min(distinct)) / max(distinct) < 0.01:
        return round(sum(converted) / len(converted), 1), flags

    flags.append(
        f"plot_size_fit not scored: multiple different area figures found "
        f"({area_mentions!r}) -- likely separate land/building figures; "
        f"picking one would be a guess, not a fix"
    )
    return None, flags


def score_plot_size_fit(plot_size_sqft: Optional[float]) -> dict:
    """Score one listing's resolved plot_size_sqft against
    config.MIN_PLOT_SIZE_SQFT. With MIN_PLOT_SIZE_SQFT = None (the
    default until the owner sets a real minimum), every listing scores
    the same neutral baseline regardless of size -- informational only,
    not yet a real filter. Below-minimum listings (once a minimum
    exists) stay at the neutral baseline too, never penalized -- same
    bonus-not-filter pattern as location_match / land_classification."""
    if plot_size_sqft is None:
        return {"score": config.PLOT_SIZE_NEUTRAL, "plot_size_sqft": None, "flags": []}

    if config.MIN_PLOT_SIZE_SQFT is None:
        return {
            "score": config.PLOT_SIZE_NEUTRAL,
            "plot_size_sqft": plot_size_sqft,
            "flags": [
                "plot_size_fit scored neutral: no minimum plot size set "
                "yet (config.MIN_PLOT_SIZE_SQFT is None) -- size shown "
                "for reference only"
            ],
        }

    if plot_size_sqft >= config.MIN_PLOT_SIZE_SQFT:
        return {
            "score": config.PLOT_SIZE_NEUTRAL + config.PLOT_SIZE_BONUS,
            "plot_size_sqft": plot_size_sqft,
            "flags": [],
        }

    return {"score": config.PLOT_SIZE_NEUTRAL, "plot_size_sqft": plot_size_sqft, "flags": []}


def score_batch_5c(records: list) -> list[dict]:
    """Score a batch of scraped+details-enriched records (IBBIRecord or
    dict) on plot_size_fit. Returns one result dict per input record,
    same order:

      {
        "listing_key_fields": {...same identity fields as 5a/5b...},
        "plot_size_fit": {"score": float, "plot_size_sqft": float|None, "flags": [...]},
        "partial_score_5c": float,   -- always a number, never None,
                                         same as 5B (unknown -> neutral)
        "flags": [...],
      }
    """
    recs = [_as_dict(r) for r in records]

    results = []
    for rec in recs:
        plot_size_sqft, parse_flags = _parse_plot_size_sqft(rec.get("plot_area_mentions") or [])
        size_result = score_plot_size_fit(plot_size_sqft)
        all_flags = parse_flags + size_result["flags"]

        results.append({
            "listing_key_fields": {
                "corporate_debtor": rec.get("corporate_debtor"),
                "ip_name": rec.get("ip_name"),
                "notice_type": rec.get("notice_type"),
                "nature_of_assets": rec.get("nature_of_assets"),
            },
            "plot_size_fit": {**size_result, "flags": all_flags},
            "partial_score_5c": size_result["score"],
            "flags": all_flags,
        })

    return results


if __name__ == "__main__":
    # Offline smoke test: synthetic records only, no network. Exercises
    # the percentile math (cheap/mid/expensive/tied/missing-price) and the
    # location bonus/neutral/unknown paths before this touches real data.
    synthetic = [
        {"corporate_debtor": "A", "ip_name": "x", "notice_type": "Sale Notice",
         "nature_of_assets": "Land", "reserve_price": 1000000, "location": "Delhi NCR"},
        {"corporate_debtor": "B", "ip_name": "x", "notice_type": "Sale Notice",
         "nature_of_assets": "Land", "reserve_price": 5000000, "location": "Mumbai, Maharashtra"},
        {"corporate_debtor": "C", "ip_name": "x", "notice_type": "Sale Notice",
         "nature_of_assets": "Land", "reserve_price": 3000000, "location": "Rajpura, Punjab"},
        {"corporate_debtor": "D", "ip_name": "x", "notice_type": "Sale Notice",
         "nature_of_assets": "Land", "reserve_price": 3000000, "location": None},
        {"corporate_debtor": "E", "ip_name": "x", "notice_type": "Sale Notice",
         "nature_of_assets": "Land", "reserve_price": None, "location": "Indore, Madhya Pradesh"},
        {"corporate_debtor": "F", "ip_name": "x", "notice_type": "Sale Notice",
         "nature_of_assets": "Land", "reserve_price": 0, "location": "Bhopal, Madhya Pradesh"},
    ]

    results = score_batch_5a(synthetic)
    for rec, res in zip(synthetic, results):
        print(
            f"{rec['corporate_debtor']:>3} | reserve={rec['reserve_price']!s:>9} "
            f"| loc={rec['location']!s:<25} "
            f"| price_score={res['price_vs_reserve']['score']!s:>6} "
            f"| loc_score={res['location_match']['score']!s:>5} "
            f"(matched={res['location_match']['matched_region']}) "
            f"| partial_5a={res['partial_score_5a']!s:>6} "
            f"| flags={res['flags']}"
        )

    # Cheapest priced listing (A, 1,000,000) should score highest on price.
    assert results[0]["price_vs_reserve"]["score"] == 100.0
    # Most expensive priced listing (B, 5,000,000) should score lowest.
    assert results[1]["price_vs_reserve"]["score"] == 0.0
    # C and D are tied on price -> equal (mid) percentile score.
    assert results[2]["price_vs_reserve"]["score"] == results[3]["price_vs_reserve"]["score"]
    # E has no reserve_price -> not scored, flagged, not defaulted to 0.
    assert results[4]["price_vs_reserve"]["score"] is None
    assert "reserve_price missing" in results[4]["price_vs_reserve"]["flags"][0]
    # E's partial score falls back to location_match alone.
    assert results[4]["partial_score_5a"] == results[4]["location_match"]["score"]
    # F has reserve_price = 0 (IBBI's "no reserve fixed" placeholder) --
    # must NOT be scored 100 as "cheapest". Excluded like a missing price.
    assert results[5]["price_vs_reserve"]["score"] is None
    assert "literal 0" in results[5]["price_vs_reserve"]["flags"][0]
    # F must also NOT have pulled the price floor down to include 0 in the
    # peer group -- C/D (3,000,000, mid of A/B's 1M-5M range) should still
    # land at 50.0, not be skewed by F's 0 being counted as a real price.
    assert results[2]["price_vs_reserve"]["score"] == 50.0

    # Preferred-region bonus: Delhi, Rajpura, Madhya Pradesh all match.
    assert results[0]["location_match"]["matched_region"] == "Delhi"
    assert results[2]["location_match"]["matched_region"] == "Rajpura"
    assert results[4]["location_match"]["matched_region"] == "Madhya Pradesh"
    assert results[0]["location_match"]["score"] == config.LOCATION_MATCH_NEUTRAL + config.LOCATION_MATCH_BONUS
    # Non-preferred region (Mumbai): neutral, no bonus, not excluded/penalized.
    assert results[1]["location_match"]["matched_region"] is None
    assert results[1]["location_match"]["score"] == config.LOCATION_MATCH_NEUTRAL
    # Unknown location (D, None): same neutral baseline as a genuine non-match.
    assert results[3]["location_match"]["score"] == config.LOCATION_MATCH_NEUTRAL
    assert "not yet known" in results[3]["location_match"]["flags"][0]

    print("\nAll offline smoke-test assertions passed (synthetic data only -- "
          "still needs a real run against scraper.ibbi + storage.db output, "
          "see test_part5a.py, before this can be marked confirmed).")

    # -----------------------------------------------------------------
    # Part 5B offline smoke test (possession_status + land_classification)
    # -----------------------------------------------------------------
    synthetic_5b = [
        {"corporate_debtor": "P", "ip_name": "x", "notice_type": "Sale Notice",
         "nature_of_assets": "Land", "possession_status": "physical", "land_classification": "industrial"},
        {"corporate_debtor": "Q", "ip_name": "x", "notice_type": "Sale Notice",
         "nature_of_assets": "Land", "possession_status": "symbolic", "land_classification": "agricultural"},
        {"corporate_debtor": "R", "ip_name": "x", "notice_type": "Sale Notice",
         "nature_of_assets": "Land", "possession_status": None, "land_classification": None},
    ]
    results_5b = score_batch_5b(synthetic_5b)
    for rec, res in zip(synthetic_5b, results_5b):
        print(
            f"{rec['corporate_debtor']:>3} | possession={rec['possession_status']!s:<10} "
            f"| poss_score={res['possession_status']['score']!s:>5} "
            f"| classification={rec['land_classification']!s:<12} "
            f"| class_score={res['land_classification']['score']!s:>5} "
            f"| partial_5b={res['partial_score_5b']!s:>6} | flags={res['flags']}"
        )

    # Physical possession scores higher than symbolic (Claude-picked
    # defaults, config.POSSESSION_STATUS_SCORES).
    assert results_5b[0]["possession_status"]["score"] == config.POSSESSION_STATUS_SCORES["physical"]
    assert results_5b[1]["possession_status"]["score"] == config.POSSESSION_STATUS_SCORES["symbolic"]
    assert results_5b[0]["possession_status"]["score"] > results_5b[1]["possession_status"]["score"]
    # Unknown possession (R) -> neutral, never None, never penalized to 0.
    assert results_5b[2]["possession_status"]["score"] == config.POSSESSION_STATUS_SCORES["unknown"]
    assert "not found" in results_5b[2]["possession_status"]["flags"][0]
    # land_classification: with PREFERRED_LAND_CLASSIFICATIONS empty by
    # default, every classification (including unknown) scores the same
    # neutral baseline -- no bonus fires yet.
    assert results_5b[0]["land_classification"]["score"] == config.LAND_CLASSIFICATION_NEUTRAL
    assert results_5b[0]["land_classification"]["matched_classification"] is None
    assert results_5b[2]["land_classification"]["score"] == config.LAND_CLASSIFICATION_NEUTRAL
    # partial_score_5b is always a real number (never None) since both
    # components always score something.
    assert all(r["partial_score_5b"] is not None for r in results_5b)

    print("\nAll Part 5B offline smoke-test assertions passed (synthetic "
          "data only -- still needs a real run against scraper.ibbi's new "
          "enrich_record_with_notice(), see test_part5b.py, before this "
          "can be marked confirmed).")

    # -----------------------------------------------------------------
    # Part 5C offline smoke test (plot_size_fit)
    # -----------------------------------------------------------------
    synthetic_5c = [
        {"corporate_debtor": "X", "ip_name": "x", "notice_type": "Sale Notice",
         "nature_of_assets": "Land", "plot_area_mentions": ["7,450 sq. ft"]},
        {"corporate_debtor": "Y", "ip_name": "x", "notice_type": "Sale Notice",
         "nature_of_assets": "Land", "plot_area_mentions": ["2 acres"]},
        {"corporate_debtor": "Z", "ip_name": "x", "notice_type": "Sale Notice",
         "nature_of_assets": "Land", "plot_area_mentions": []},
        {"corporate_debtor": "W", "ip_name": "x", "notice_type": "Sale Notice",
         "nature_of_assets": "Land", "plot_area_mentions": ["7,450 sq. ft", "14,200 sq. ft"]},
        {"corporate_debtor": "V", "ip_name": "x", "notice_type": "Sale Notice",
         "nature_of_assets": "Land", "plot_area_mentions": ["500 sq. mtrs", "500 sq. mtrs"]},
    ]
    results_5c = score_batch_5c(synthetic_5c)
    for rec, res in zip(synthetic_5c, results_5c):
        print(
            f"{rec['corporate_debtor']:>3} | mentions={rec['plot_area_mentions']!s:<35} "
            f"| plot_size_sqft={res['plot_size_fit']['plot_size_sqft']!s:>10} "
            f"| score={res['plot_size_fit']['score']!s:>5} "
            f"| flags={res['flags']}"
        )

    # X: single clean sq-ft mention -> converts cleanly, no unit math needed.
    assert results_5c[0]["plot_size_fit"]["plot_size_sqft"] == 7450.0
    # Y: acres correctly converted to sq ft (2 * 43,560).
    assert results_5c[1]["plot_size_fit"]["plot_size_sqft"] == 87120.0
    # Both X and Y score neutral (MIN_PLOT_SIZE_SQFT is None -- informational
    # only, not a real filter yet), not penalized or favored either way.
    assert results_5c[0]["plot_size_fit"]["score"] == config.PLOT_SIZE_NEUTRAL
    assert results_5c[1]["plot_size_fit"]["score"] == config.PLOT_SIZE_NEUTRAL
    assert "no minimum plot size set yet" in results_5c[0]["flags"][0]
    # Z: no area mentions at all -> None, flagged, never guessed/defaulted.
    assert results_5c[2]["plot_size_fit"]["plot_size_sqft"] is None
    assert "no area figure found" in results_5c[2]["flags"][0]
    # W: two genuinely DIFFERENT figures (land vs building) -> ambiguous,
    # correctly refuses to guess which one is "the" plot size.
    assert results_5c[3]["plot_size_fit"]["plot_size_sqft"] is None
    assert "multiple different area figures" in results_5c[3]["flags"][0]
    # V: same figure mentioned twice (sq mtrs) -> NOT flagged as ambiguous,
    # correctly collapses to one converted value (500 * 10.7639).
    assert results_5c[4]["plot_size_fit"]["plot_size_sqft"] == round(500 * 10.7639, 1)
    assert not any("multiple different" in f for f in results_5c[4]["flags"])
    # partial_score_5c is always a real number (never None), same pattern
    # as partial_score_5b.
    assert all(r["partial_score_5c"] is not None for r in results_5c)

    print("\nAll Part 5C offline smoke-test assertions passed (synthetic "
          "data only -- still needs a real run against real "
          "plot_area_mentions from scraper.ibbi's Part 3C enrichment, see "
          "test_part5c.py, before this can be marked confirmed).")
