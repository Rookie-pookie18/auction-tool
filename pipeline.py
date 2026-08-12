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
     notice) PDF enrichment over the full batch, same as always -- these
     are NOT gated by needs_reenrichment(); that gate is Part 6's AI layer
     only (Gemini/MCA/DuckDuckGo quota), never the scraper-level PDF
     parsing that scoring itself depends on (location/possession_status/
     land_classification/plot_area_mentions all come from here).
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

import sys
from dataclasses import asdict, is_dataclass
from typing import Optional

sys.path.insert(0, ".")

import config
from scraper.ibbi import scrape_all_pages, enrich_all_with_details, enrich_all_with_notice
from storage.db import get_connection, store_records, needs_reenrichment, get_enrichment, upsert_enrichment
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
        records, scrape_problems = scrape_all_pages(max_pages=max_pages)

        # --- 2. Scraper-level PDF enrichment (Parts 3C/5B) -- unconditional,
        # every run, same as before this part existed. Not gated by
        # needs_reenrichment(); that gate applies to Part 6's AI layer only. ---
        if run_details_enrichment:
            enrich_all_with_details(records)
        if run_notice_enrichment:
            enrich_all_with_notice(records)

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
        }
    finally:
        conn.close()

    return result


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

    def fake_scrape_all_pages(max_pages=None):
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
        def scrape_with_price_drop(max_pages=None):
            recs, problems = real_fake_scrape(max_pages=max_pages)
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
