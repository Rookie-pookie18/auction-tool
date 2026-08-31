"""
pipeline.py — Part 7A: the pipeline orchestrator.

--------------------------------------------------------------------------
FILENAME/LOCATION DECISION (flagged per Section 0 rule 1, not guessed):
repo root, alongside the existing test_part*.py scripts -- NOT inside
scraper/, storage/, scoring/, or ai_analysis/, because this is the one
piece of code that imports and chains ALL of them together (Part 3C/5B's
scraper-level PDF enrichment, Part 4 storage, Part 5 scoring, Part 6
ai_analysis) and doesn't belong to any single existing package. Named
`pipeline.py` rather than `orchestrator.py` so Part 8B's cron step has an
obvious single import: `from pipeline import run_pipeline`. This becomes
that single entry point once 8B exists, per the 2026-08-10 Part 7
architecture decision's own stated plan (see PROJECT_STATUS.md).
--------------------------------------------------------------------------
WHAT THIS RUNS, EVERY CALL (see PROJECT_STATUS.md decision log, "Part 7
architecture decisions" and "Part 7A enrichment-trigger refinement"):

  1. Scrape the FULL current active listing set (scraper.ibbi.scrape_all_
     pages) -- not an incremental diff. Full scrape every run is what lets
     "top-scored" / "closing soon" be computed over every currently-active
     listing, not just today's new/changed ones.
  2. Run Part 3C (enrich_all_with_details) and Part 5B (enrich_all_with_
     notice) PDF enrichment -- but, as of 2026-08-13, ONLY for listings
     that are new, changed, or were never successfully parsed before
     (storage.db.classify_pending decides this, read-only, before any
     fetch happens). Originally this ran unconditionally on every single
     record every run; against the real site's ~484 pages / ~9,700
     listings that was 16+ hours of pure fetch-delay, confirmed the hard
     way when a real run hit GitHub Actions' 4-hour job cap without
     finishing (see .github/workflows/daily_report.yml history). For
     listings that DON'T get re-fetched this run, their already-parsed
     fields (cin/location/emd_amount/auction_platform/plot_area_mentions/
     possession_status/land_classification) are pulled back from the DB
     instead, so scoring below still has them for the full active set --
     not just today's fetches. Same "reuse unless something's actually
     different" philosophy Part 6's needs_reenrichment() already used for
     Gemini/MCA/DuckDuckGo, just applied one layer earlier, to the
     scraper-level PDF fetches that were the actual runtime problem.
  3. storage.db.store_records() -- new/changed/unchanged/collision
     detection, unchanged from Part 4.
  4. Score the full batch fresh in-memory: scoring.rules.score_batch_5a/
     5b/5c. Never persisted (see storage/db.py's own docstring on why --
     price_vs_reserve is an intentionally-ephemeral, batch-relative
     percentile).
  5. For each listing, storage.db.needs_reenrichment() decides whether to
     re-run Part 6's three modules (Gemini narrative, MCA lookup, news
     search) or reuse the existing `enrichment` row. Re-enrichment runs
     go through the existing batch helpers (generate_narratives_for_
     batch/enrich_batch_with_mca/enrich_batch_with_news) so their pacing
     (GEMINI_REQUEST_DELAY_SECONDS/NEWS_SEARCH_REQUEST_DELAY_SECONDS) and
     retry logic apply exactly as already built and confirmed in Parts
     6A/6B/6C -- this file does not reimplement that pacing, it just
     restricts which listings get sent through it.
  6. Assemble ONE dataset per listing: raw scraped fields + this run's
     fresh score + enrichment (fresh-or-reused, each field still carrying
     its own module's honesty/"unverified" flags exactly as written) +
     this run's new/changed/unchanged/collision status. This assembled
     list is the function's return value -- what Part 7B (PDF layout)
     will consume next.

COLLISION HANDLING (a real gap found while wiring this, not previously
decided anywhere -- flagged here rather than guessed past silently):
a "collision" status means listing_key already belongs to a DIFFERENT
existing listing (near-duplicate hash, see storage/db.py's module
docstring) -- the incoming record was written to the `collisions` table,
NOT to `listings`, and nothing about it was merged or overwritten.
Running that listing_key through needs_reenrichment()/upsert_enrichment()
would silently write this incoming, unrelated record's AI narrative into
the enrichment row that actually belongs to the other, already-stored
listing sharing that key -- corrupting a real listing's enrichment data.
So: collisions are assembled into this run's output (still visible, still
flagged, still fully scored) but SKIP Part 6 enrichment entirely this
run -- `enrichment` in their dataset is None with a flag explaining why,
never a guess at whose enrichment row to touch. Resolve the collision
first (see storage/db.py's collision-resolution note), then it will
enrich normally on a later run once it has its own real listing_key.
--------------------------------------------------------------------------
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, is_dataclass
from datetime import date, timedelta
from typing import Optional

sys.path.insert(0, ".")

import config
from scraper.ibbi import scrape_all_pages, enrich_all_with_details, enrich_all_with_notice
from storage.db import (
    get_connection, store_records, needs_reenrichment, get_enrichment,
    upsert_enrichment, classify_pending,
)
from scoring.rules import score_batch_5a, score_batch_5b, score_batch_5c
from ai_analysis.gemini_narrative import generate_narratives_for_batch
from ai_analysis.mca_lookup import enrich_batch_with_mca
from ai_analysis.news_search import enrich_batch_with_news


def _rec_to_raw_dict(rec) -> dict:
    """Same asdict-or-passthrough pattern every other module here uses
    (storage/db.py, scoring/rules.py, ai_analysis/*.py's own _as_dict)."""
    return asdict(rec) if is_dataclass(rec) else dict(rec)


def run_pipeline(
    max_pages: Optional[int] = None,
    db_path: Optional[str] = None,
    run_details_enrichment: bool = True,
    run_notice_enrichment: bool = True,
) -> dict:
    """
    Runs one full pipeline pass: scrape -> store -> score -> enrich.
    Returns:
      {
        "assembled": [ {...one dict per listing, see module docstring...} ],
        "scrape_problems": [...],           -- from scraper.ibbi.scrape_all_pages
        "store_summary": {"new": N, "unchanged": N, "changed": N, "collision": N},
        "enrichment_summary": {"reenriched": N, "reused": N, "skipped_collision": N},
      }

    max_pages: forwarded to scrape_all_pages -- None = the site's full
        current listing set; pass a small int for a smoke/confirmation run.
    db_path: forwarded to storage.db.get_connection -- None = config.DB_PATH
        (the real DB). Tests should pass a throwaway path so a smoke run
        never touches the owner's real data.
    run_details_enrichment / run_notice_enrichment: default True (the real
        every-run behavior). Only exposed as False for a fast offline
        wiring test that shouldn't attempt real PDF fetches -- never turn
        these off for a real run, since scoring 5a/5b/5c and Part 6's
        prompts all depend on the fields these two populate.
    """
    conn = get_connection(db_path)

    # Connection is closed in `finally` below so a real run never leaks
    # an open SQLite handle -- harmless on Linux (files can be removed
    # while open) but on Windows an open handle blocks deleting/renaming
    # the DB file, which is exactly what tripped up test_part8a.py's own
    # throwaway-DB cleanup on a real Windows run (2026-08-11) -- fixed at
    # the source here rather than papered over in that test.
    try:

        # --- 1. Scrape the full current active set ---
        # cutoff_date added 2026-08-13, alongside the PDF-fetch gating fix
        # above -- see config.SCRAPE_WINDOW_DAYS and scraper.ibbi.
        # scrape_all_pages()'s own docstring for the full reasoning and
        # the stated tradeoff. None (config default disabled) restores
        # the old "walk every one of the ~484 pages" behavior.
        cutoff_date = (
            date.today() - timedelta(days=config.SCRAPE_WINDOW_DAYS)
            if config.SCRAPE_WINDOW_DAYS is not None else None
        )
        records, scrape_problems = scrape_all_pages(max_pages=max_pages, cutoff_date=cutoff_date)

        # --- 2. Scraper-level PDF enrichment (Parts 3C/5B) -- gated as of
        # 2026-08-13 (see module docstring). Read-only preview first (no
        # writes yet -- the real write happens in step 3, after enrichment,
        # once cin/location/etc. are final for this run) decides, per
        # listing, whether a PDF fetch is actually worth doing: only if the
        # listing is new, changed, or was never successfully parsed before.
        # Everyone else reuses their already-stored fields untouched.
        preview_by_index: dict[int, dict] = {}
        need_details_idx: list[int] = []
        need_notice_idx: list[int] = []
        for i, rec in enumerate(records):
            preview = classify_pending(conn, rec)
            preview_by_index[i] = preview
            status = preview["status"]
            existing = preview["existing"]
            details_already_parsed = bool(existing and existing.get("details_pdf_parsed"))
            notice_already_parsed = bool(existing and existing.get("notice_pdf_parsed"))
            # "new"/"changed"/"collision" always (re-)fetch -- something is
            # different about this listing, its PDFs might be too. An
            # "unchanged" listing only (re-)fetches if it was never
            # successfully parsed before (worth retrying, e.g. yesterday's
            # PDF was temporarily unreachable or scanned/unreadable).
            if status in ("new", "changed", "collision") or not details_already_parsed:
                need_details_idx.append(i)
            if status in ("new", "changed", "collision") or not notice_already_parsed:
                need_notice_idx.append(i)

        if run_details_enrichment:
            enrich_all_with_details([records[i] for i in need_details_idx])
        if run_notice_enrichment:
            enrich_all_with_notice([records[i] for i in need_notice_idx])

        # For every listing that did NOT get a fresh fetch above, pull its
        # already-parsed fields back from the DB. Scoring below (step 4)
        # runs over the FULL currently-active set, not just today's
        # fetches, so it needs these fields populated on every record,
        # fetched-this-run or not.
        need_details_set = set(need_details_idx)
        need_notice_set = set(need_notice_idx)
        for i, rec in enumerate(records):
            existing = preview_by_index[i]["existing"]
            if existing is None:
                continue  # brand new listing -- nothing to reuse, always in both fetch sets above
            if i not in need_details_set:
                rec.cin = existing.get("cin")
                rec.emd_amount = existing.get("emd_amount")
                rec.location = existing.get("location")
                rec.state = existing.get("state")
                rec.auction_platform = existing.get("auction_platform")
                rec.auction_platform_url = existing.get("auction_platform_url")
                rec.plot_area_mentions = json.loads(existing.get("plot_area_mentions") or "[]")
                rec.details_pdf_parsed = bool(existing.get("details_pdf_parsed"))
                rec.flags.append(
                    "Part 3C (details PDF) reused from the DB, not re-fetched "
                    "this run -- listing unchanged and already parsed."
                )
            if i not in need_notice_set:
                rec.possession_status = existing.get("possession_status")
                rec.land_classification = existing.get("land_classification")
                rec.notice_pdf_parsed = bool(existing.get("notice_pdf_parsed"))
                rec.flags.append(
                    "Part 5B (notice PDF) reused from the DB, not re-fetched "
                    "this run -- listing unchanged and already parsed."
                )

        # --- 3. Store: new/changed/unchanged/collision detection ---
        store_result = store_records(conn, records)
        store_results_list = store_result["results"]

        # --- 4. Score the full batch fresh, in-memory, never persisted ---
        score_a = score_batch_5a(records)
        score_b = score_batch_5b(records)
        score_c = score_batch_5c(records)

        # --- 5. Decide which listings need Part 6 re-run vs. reuse ---
        reenrich_idx: list[int] = []
        reused_idx: list[int] = []
        collision_idx: list[int] = []

        for i, rec in enumerate(records):
            sr = store_results_list[i]
            if sr["status"] == "collision":
                collision_idx.append(i)
                continue
            needs = needs_reenrichment(
                conn,
                sr["listing_key"],
                status=sr["status"],
                details_pdf_parsed=bool(getattr(rec, "details_pdf_parsed", False)),
                notice_pdf_parsed=bool(getattr(rec, "notice_pdf_parsed", False)),
            )
            (reenrich_idx if needs else reused_idx).append(i)

        # --- 6. Re-run Part 6 only for reenrich_idx, via the existing batch
        # helpers (their pacing/retry logic already confirmed in 6A/6B/6C) ---
        subset_records = [records[i] for i in reenrich_idx]

        if subset_records:
            gemini_results = generate_narratives_for_batch(subset_records)
            mca_results = enrich_batch_with_mca(subset_records)
            if config.NEWS_SEARCH_ENABLED:
                news_results = enrich_batch_with_news(subset_records)
            else:
                news_results = [
                    {"news_data": None, "flags": ["News search skipped: config.NEWS_SEARCH_ENABLED is False"]}
                    for _ in subset_records
                ]
        else:
            gemini_results, mca_results, news_results = [], [], []

        enrichment_by_index: dict[int, dict] = {}
        reused_by_index: dict[int, bool] = {}

        for pos, i in enumerate(reenrich_idx):
            rec = records[i]
            sr = store_results_list[i]
            row = upsert_enrichment(
                conn,
                sr["listing_key"],
                gemini_result=gemini_results[pos],
                mca_result=mca_results[pos],
                news_result=news_results[pos],
                details_pdf_parsed=bool(getattr(rec, "details_pdf_parsed", False)),
                notice_pdf_parsed=bool(getattr(rec, "notice_pdf_parsed", False)),
            )
            enrichment_by_index[i] = row
            reused_by_index[i] = False

        for i in reused_idx:
            sr = store_results_list[i]
            enrichment_by_index[i] = get_enrichment(conn, sr["listing_key"])
            reused_by_index[i] = True

        for i in collision_idx:
            enrichment_by_index[i] = None
            reused_by_index[i] = False

        # --- 7. Assemble one dataset per listing, original scrape order ---
        assembled = []
        for i, rec in enumerate(records):
            sr = store_results_list[i]
            entry = {
                "listing_key": sr["listing_key"],
                "status": sr["status"],
                "changes": sr.get("changes", []),
                "price_drop": sr.get("price_drop", False),
                "raw": _rec_to_raw_dict(rec),
                "score": {
                    "5a": score_a[i],
                    "5b": score_b[i],
                    "5c": score_c[i],
                },
                "enrichment": enrichment_by_index[i],
                "enrichment_reused": reused_by_index[i],
            }
            if sr["status"] == "collision":
                entry["flags"] = list(sr.get("flags", [])) + [
                    "Part 6 enrichment SKIPPED this run: listing_key collides "
                    "with an existing, different listing (see `collisions` "
                    "table) -- writing enrichment here would corrupt that "
                    "other listing's row. Resolve the collision, then this "
                    "listing will enrich normally on a later run."
                ]
            assembled.append(entry)

        result = {
            "assembled": assembled,
            "scrape_problems": scrape_problems,
            "store_summary": store_result["summary"],
            "enrichment_summary": {
                "reenriched": len(reenrich_idx),
                "reused": len(reused_idx),
                "skipped_collision": len(collision_idx),
            },
            # Added 2026-08-13 alongside the PDF-fetch gating fix -- makes
            # the actual runtime savings visible in the run's own output
            # (main.py prints this), rather than only inferable from how
            # long the job took.
            "pdf_fetch_summary": {
                "details_fetched": len(need_details_idx),
                "details_reused": len(records) - len(need_details_idx),
                "notice_fetched": len(need_notice_idx),
                "notice_reused": len(records) - len(need_notice_idx),
            },
        }
    finally:
        conn.close()

    return result


def filter_assembled_by_location(
    assembled: list[dict],
    included_locations: Optional[dict] = None,
) -> dict:
    """Owner request 2026-08-14 (Part 9): report-only include filter,
    kept OUT of run_pipeline() above on purpose -- run_pipeline()/storage
    still see and keep every listing regardless of location; this is a
    separate, explicit step main.py runs on run_pipeline()'s "assembled"
    output, after the fact, only for what goes into the PDF/email. See
    config.py's "Report location filter" section for why and for the
    keyword lists.

    Each region in included_locations is either:
      {"kind": "state", "values": [...]}   -- compared with EXACT,
          case-insensitive equality against the listing's clean `state`
          field (only correct for regions that are exactly one whole
          state -- see config.py's INCLUDED_LOCATIONS docstring).
      {"kind": "keyword", "values": [...]} -- case-insensitive substring
          match against the listing's raw `location` text (for anything
          narrower or broader than one state -- a city, or a multi-state
          area).
    A listing is kept if it matches ANY region by its region's own kind
    (region labels themselves don't matter for matching -- they're just
    for the caller's own reporting). Never a silent drop: every listing
    ends up in exactly one of the three returned lists, never just
    missing.

    included_locations: None -> config.INCLUDED_LOCATIONS. Pass an
        explicit dict to override (e.g. in a test).

    Returns:
      {
        "kept": [entry, ...],                    -- location matched
        "excluded_other_location": [entry, ...],  -- location known, no match
        "excluded_unknown_location": [entry, ...],-- location None/empty
                                                       (details PDF not
                                                       parsed yet, or the
                                                       PDF genuinely never
                                                       stated one)
      }
    """
    included_locations = config.INCLUDED_LOCATIONS if included_locations is None else included_locations
    state_values = {
        v.lower() for spec in included_locations.values()
        if spec.get("kind") == "state" for v in spec.get("values", [])
    }
    keyword_values = [
        kw.lower() for spec in included_locations.values()
        if spec.get("kind") == "keyword" for kw in spec.get("values", [])
    ]

    kept: list[dict] = []
    excluded_other_location: list[dict] = []
    excluded_unknown_location: list[dict] = []

    for entry in assembled:
        raw = entry.get("raw") or {}
        location = raw.get("location")
        state = raw.get("state")
        if not location and not state:
            excluded_unknown_location.append(entry)
            continue

        matched = False
        if state and state.lower() in state_values:
            matched = True
        elif location:
            location_lower = location.lower()
            if any(kw in location_lower for kw in keyword_values):
                matched = True

        if matched:
            kept.append(entry)
        else:
            excluded_other_location.append(entry)

    return {
        "kept": kept,
        "excluded_other_location": excluded_other_location,
        "excluded_unknown_location": excluded_unknown_location,
    }


def filter_assembled_by_asset_type(
    assembled: list[dict],
    excluded_keywords: Optional[list[str]] = None,
    registration_plate_pattern: Optional[str] = None,
) -> dict:
    """Owner request 2026-08-14 (Part 9, item 1): report-only exclude
    filter for vehicle/car listings. Same "report-only, kept OUT of
    run_pipeline()" pattern as filter_assembled_by_location() above --
    see config.py's "Report asset-type exclusion filter" section for why,
    for the keyword list, and for why this only covers "cars" and not
    "loan-recovery" (no source for the latter exists yet).

    A listing's `nature_of_assets` text is excluded if EITHER:
      1. it matches one of excluded_keywords, case-insensitively,
         `\\b`-bounded ("vehicle", "truck", etc.), or
      2. it contains an Indian vehicle registration plate
         (registration_plate_pattern) -- added 2026-08-31 because
         individual car/bike disposal listings (e.g. "Maruti Suzuki -
         Swift Dzire VXI MH02EK5147") are often just a make/model + plate
         with no keyword like "car"/"vehicle" in the text at all, so (1)
         alone missed them. See config.py's
         ASSET_REGISTRATION_PLATE_PATTERN docstring for detail/validation.
    A match on either signal excludes the whole listing (see config.py
    docstring on why a mixed "land + vehicle" listing is still excluded,
    not kept for its land).

    excluded_keywords: None -> config.EXCLUDED_ASSET_KEYWORDS. Pass an
        explicit list to override (e.g. in a test).
    registration_plate_pattern: None -> config.ASSET_REGISTRATION_PLATE_PATTERN.
        Pass an explicit regex string to override, or "" to disable this
        signal and fall back to keyword-only matching.

    Returns:
      {
        "kept": [entry, ...],              -- neither signal matched
        "excluded_asset_type": [entry, ...],-- nature_of_assets matched
                                                a keyword or a plate
      }
    Listings with no nature_of_assets text at all are kept -- absence of
    the field is not evidence it's a vehicle listing, same "never
    penalize missing data" principle used throughout this project.
    """
    excluded_keywords = config.EXCLUDED_ASSET_KEYWORDS if excluded_keywords is None else excluded_keywords
    registration_plate_pattern = (
        config.ASSET_REGISTRATION_PLATE_PATTERN
        if registration_plate_pattern is None
        else registration_plate_pattern
    )
    patterns = [
        re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
        for kw in excluded_keywords
    ]
    plate_pattern = re.compile(registration_plate_pattern) if registration_plate_pattern else None

    kept: list[dict] = []
    excluded_asset_type: list[dict] = []

    for entry in assembled:
        text = (entry.get("raw") or {}).get("nature_of_assets")
        matched = bool(text) and (
            any(p.search(text) for p in patterns)
            or (plate_pattern is not None and bool(plate_pattern.search(text)))
        )
        if matched:
            excluded_asset_type.append(entry)
        else:
            kept.append(entry)

    return {
        "kept": kept,
        "excluded_asset_type": excluded_asset_type,
    }


if __name__ == "__main__":
    # -----------------------------------------------------------------
    # OFFLINE wiring smoke test only -- synthetic data, no network, same
    # "confirms the logic, does NOT confirm the real chain" caveat as
    # every other __main__ block in this project (see storage/db.py).
    # Monkeypatches every network-touching function this module calls so
    # the full scrape->store->score->enrich->assemble chain can be
    # exercised end-to-end without a live scrape, Gemini key, MCA CSVs, or
    # DuckDuckGo access. A REAL small-batch pull against the live chain is
    # test_part7a.py, run separately on the owner's own machine (per
    # Section 0 rule 2: this sandbox has no network, ever) -- that is the
    # run that actually confirms Part 7A, not this one.
    # -----------------------------------------------------------------
    import copy
    from datetime import date
    import scraper.ibbi as ibbi_mod  # only used below for the IBBIRecord dataclass

    def fake_scrape_all_pages(max_pages=None, cutoff_date=None):
        r1 = ibbi_mod.IBBIRecord(
            notice_type="Sale Notice", corporate_debtor="ABC Textiles Pvt Ltd",
            ip_name="Ramesh Kumar", nature_of_assets="Industrial land 5 acres",
            reserve_price=5000000, auction_date=date(2026, 9, 1),
            notice_date=date(2026, 8, 1), emd_due_date=date(2026, 8, 25),
            details_pdf_url="http://fake/d1.pdf", notice_pdf_url="http://fake/n1.pdf",
        )
        r2 = ibbi_mod.IBBIRecord(
            notice_type="Sale Notice", corporate_debtor="XYZ Foods Ltd",
            ip_name="Sunita Rao", nature_of_assets="Warehouse 2 acres",
            reserve_price=2000000, auction_date=date(2026, 9, 15),
            notice_date=date(2026, 8, 5), emd_due_date=date(2026, 8, 30),
            details_pdf_url="http://fake/d2.pdf", notice_pdf_url="http://fake/n2.pdf",
        )
        return [r1, r2], [{"page": 1, "reason": "synthetic test, not a real problem"}]

    def fake_enrich_details(records, delay_seconds=None):
        for rec in records:
            rec.cin = "U18101KA2002PLC030185" if "ABC" in rec.corporate_debtor else None
            rec.location = "Rajpura, Punjab" if "ABC" in rec.corporate_debtor else "Nagpur, Maharashtra"
            rec.plot_area_mentions = ["5 acres"]
            rec.details_pdf_parsed = True

    def fake_enrich_notice(records, delay_seconds=None):
        for rec in records:
            rec.possession_status = "physical"
            rec.land_classification = "industrial"
            rec.notice_pdf_parsed = True

    def fake_generate_narratives_for_batch(records, api_key=None, model=None, delay_seconds=None):
        return [
            {"narrative": {"summary": f"Synthetic summary for {r.corporate_debtor}",
                            "price_read": "no comparable data", "risk_notes": [], "data_gaps": []},
             "flags": []}
            for r in records
        ]

    def fake_enrich_batch_with_mca(records, data_dir=None):
        out = []
        for r in records:
            result = {"mca_data": {"company_name": r.corporate_debtor.upper()}, "flags": []}
            r.mca_data = result["mca_data"]
            r.mca_lookup_attempted = True
            out.append(result)
        return out

    def fake_enrich_batch_with_news(records, delay_seconds=None):
        out = []
        for r in records:
            result = {"news_data": [{"title": "Synthetic hit", "url": "http://fake",
                                      "snippet": "..."}], "flags": []}
            r.news_data = result["news_data"]
            r.news_search_attempted = True
            out.append(result)
        return out

    # Patch the names actually looked up inside run_pipeline() -- those
    # were bound into THIS module's own global namespace by the `from
    # scraper.ibbi import ...` etc. lines at the top of this file, so they
    # must be reassigned right here (module-level globals), NOT via a
    # fresh `import pipeline as pipeline_mod`, which -- when this file is
    # run directly as `__main__` -- would create a second, separate module
    # object with its own separate globals that run_pipeline() never
    # actually reads from. (Caught by running this test: the first attempt
    # patched the wrong module object and the real network call fired
    # anyway -- fixed before this was called a passing test.)
    orig = {
        "scrape_all_pages": scrape_all_pages,
        "enrich_all_with_details": enrich_all_with_details,
        "enrich_all_with_notice": enrich_all_with_notice,
        "generate_narratives_for_batch": generate_narratives_for_batch,
        "enrich_batch_with_mca": enrich_batch_with_mca,
        "enrich_batch_with_news": enrich_batch_with_news,
    }

    scrape_all_pages = fake_scrape_all_pages
    enrich_all_with_details = fake_enrich_details
    enrich_all_with_notice = fake_enrich_notice
    generate_narratives_for_batch = fake_generate_narratives_for_batch
    enrich_batch_with_mca = fake_enrich_batch_with_mca
    enrich_batch_with_news = fake_enrich_batch_with_news

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        db_path = f"{tmp}/test.db"

        print("--- Pass 1: both listings are brand new -> both re-enrich ---")
        out1 = run_pipeline(db_path=db_path)
        assert out1["store_summary"] == {"new": 2, "unchanged": 0, "changed": 0, "collision": 0}
        assert out1["enrichment_summary"] == {"reenriched": 2, "reused": 0, "skipped_collision": 0}
        assert len(out1["assembled"]) == 2
        for entry in out1["assembled"]:
            assert entry["enrichment"] is not None
            assert entry["enrichment_reused"] is False
            assert entry["score"]["5a"]["partial_score_5a"] is not None
            assert entry["score"]["5b"]["partial_score_5b"] is not None
        print("  OK: 2 new listings, both scored + freshly enriched.")

        print("\n--- Pass 2: identical re-scrape (same fake data) -> both unchanged, both reused ---")
        out2 = run_pipeline(db_path=db_path)
        assert out2["store_summary"] == {"new": 0, "unchanged": 2, "changed": 0, "collision": 0}
        assert out2["enrichment_summary"] == {"reenriched": 0, "reused": 2, "skipped_collision": 0}
        for entry in out2["assembled"]:
            assert entry["enrichment_reused"] is True
            assert entry["enrichment"] is not None
            # a reused row must still carry its own honesty flags forward
            assert "flags" in entry["enrichment"] or entry["enrichment"].get("news_flags_json") is not None
        print("  OK: 2 unchanged listings, both correctly reused (no Gemini/MCA/DuckDuckGo re-spend).")

        print("\n--- Pass 3: reserve_price drops on listing 1 -> only that one re-enriches ---")
        real_fake_scrape = scrape_all_pages
        def scrape_with_price_drop(max_pages=None, cutoff_date=None):
            recs, problems = real_fake_scrape(max_pages=max_pages, cutoff_date=cutoff_date)
            recs[0].reserve_price = 4500000  # price drop on ABC Textiles
            return recs, problems
        scrape_all_pages = scrape_with_price_drop
        out3 = run_pipeline(db_path=db_path)
        scrape_all_pages = real_fake_scrape
        assert out3["store_summary"] == {"new": 0, "unchanged": 1, "changed": 1, "collision": 0}
        assert out3["enrichment_summary"] == {"reenriched": 1, "reused": 1, "skipped_collision": 0}
        changed_entries = [e for e in out3["assembled"] if e["status"] == "changed"]
        assert len(changed_entries) == 1
        assert changed_entries[0]["enrichment_reused"] is False
        assert changed_entries[0]["price_drop"] is True
        print("  OK: price-drop listing re-enriched, the untouched one reused -- selective re-enrichment confirmed.")

        print("\n--- Pass 4: forced collision status -> enrichment SKIPPED for that listing only ---")
        # A real hash collision can't be forced in a synthetic test (same
        # caveat storage/db.py's own __main__ block notes) -- so this pass
        # directly patches store_records() to return a "collision" status
        # for one record, to test THIS file's own collision-handling
        # branch (see module docstring) in isolation from whether
        # storage.db can actually produce one.
        real_store_records = store_records
        def store_records_with_forced_collision(conn, records):
            result = real_store_records(conn, records)
            result["results"][0]["status"] = "collision"
            result["summary"]["unchanged"] -= 1
            result["summary"]["collision"] = result["summary"].get("collision", 0) + 1
            return result
        store_records = store_records_with_forced_collision
        out4 = run_pipeline(db_path=db_path)
        store_records = real_store_records

        assert out4["enrichment_summary"]["skipped_collision"] == 1
        assert out4["enrichment_summary"]["reenriched"] == 0  # the other listing is still unchanged
        collision_entry = out4["assembled"][0]
        assert collision_entry["status"] == "collision"
        assert collision_entry["enrichment"] is None
        assert collision_entry["enrichment_reused"] is False
        assert any("Part 6 enrichment SKIPPED" in f for f in collision_entry["flags"])
        # the OTHER listing must be completely unaffected by the forced collision
        other_entry = out4["assembled"][1]
        assert other_entry["status"] == "unchanged"
        assert other_entry["enrichment"] is not None
        print("  OK: collision listing skips Part 6 enrichment with an explanatory "
              "flag; the other listing is unaffected -- no corruption of an "
              "unrelated listing's enrichment row.")

        print("\nAll pipeline.py offline wiring smoke-test assertions passed "
              "(synthetic data, monkeypatched network calls -- confirms the "
              "scrape->store->score->enrich->assemble WIRING is correct, "
              "does NOT confirm the real chain against a live scrape/Gemini/"
              "MCA/DuckDuckGo. Run test_part7a.py on a machine with network "
              "access before marking Part 7A confirmed in PROJECT_STATUS.md.)")

    # restore originals (harmless here since the process exits right after,
    # but keeps this block safe to copy into a future pytest-style test)
    scrape_all_pages = orig["scrape_all_pages"]
    enrich_all_with_details = orig["enrich_all_with_details"]
    enrich_all_with_notice = orig["enrich_all_with_notice"]
    generate_narratives_for_batch = orig["generate_narratives_for_batch"]
    enrich_batch_with_mca = orig["enrich_batch_with_mca"]
    enrich_batch_with_news = orig["enrich_batch_with_news"]
