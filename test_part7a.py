"""
test_part7a.py — real-network confirmation for Part 7A (the pipeline
orchestrator, pipeline.py's run_pipeline()).

Run this from the project root (where config.py lives):
    python test_part7a.py

Needs everything Parts 6A/6B/6C each needed on their own, all at once:
  - GEMINI_API_KEY set (see README.md's Part 6A section) -- Gemini narrative
  - at least one state's MCA CSV downloaded (see README.md's Part 6B
    section) if you want to see a real MCA match rather than every listing
    flagging "no local data for that state" -- NOT required to pass this
    test, a clean skip-flag is a legitimate real result too
  - config.NEWS_SEARCH_ENABLED = True (default) for the DuckDuckGo pass

Note: per PROJECT_STATUS.md Section 0 rule 2, the code-running sandbox has
no network access -- the IBBI scrape, the Gemini call, AND the DuckDuckGo
call below all have to run on the owner's own machine, same as every other
test_partN.py so far. pipeline.py's own __main__ block already ran an
OFFLINE wiring smoke test (synthetic data, monkeypatched network calls) --
that confirms the logic is wired correctly, but only THIS script, run for
real, confirms Part 7A itself per this project's "never overstate testing"
rule.

What it does:
  1. Runs run_pipeline() TWICE in a row against a throwaway, real SQLite
     DB (test_part7a_run.db, deleted first if it exists from a prior run)
     -- pass 1 against a small real slice of IBBI's live listing table
     (MAX_PAGES below), pass 2 immediately after with the SAME max_pages,
     so pass 2's listings should mostly come back "unchanged" and prove
     real reuse (no second Gemini/MCA/DuckDuckGo spend) against a live
     chain, not just synthetic data.
  2. Prints, per listing, the assembled Part 7A output: status (new/
     unchanged/changed/collision), the 5a/5b/5c partial scores, whether
     enrichment was fresh or reused this pass, and the narrative/mca/news
     flags -- everything Part 7B would actually consume.
  3. Prints pass 2's enrichment_summary specifically, since
     reenriched=0 / reused=N (matching pass 1's listing count) is the one
     number that actually proves needs_reenrichment()'s reuse logic works
     end to end, not just in the offline synthetic test.

Paste the full printed output (or the full traceback, if it errors) back
so Part 7A can be marked confirmed in PROJECT_STATUS.md. Things to check:
  - Pass 1: does every listing get a status, a score, AND enrichment
    (unless it's a rare real collision -- see pipeline.py's module
    docstring for why collisions skip enrichment on purpose)?
  - Pass 2: does enrichment_summary show reused == however many listings
    came back "unchanged" and reenriched == however many came back
    "changed" (reserve prices/dates on IBBI's live site can genuinely
    move between the two passes; that's a REAL "changed" case, not a bug,
    if it happens)?
  - Do the honesty flags (missing CIN, no MCA data for that state, 0 news
    results, etc.) show up plainly rather than being silently dropped?
  - This is real API quota (Gemini + MCA local reads + DuckDuckGo) for
    however many listings MAX_PAGES pulls in -- kept to 1 page on purpose
    for this first confirmation run, same spirit as test_part6a/b/c.
"""

import os
import sys
sys.path.insert(0, ".")

import config
from pipeline import run_pipeline

MAX_PAGES = 1  # kept small for the first confirmation run -- real Gemini/
               # MCA/DuckDuckGo quota being spent per listing, not just a
               # network call. Raise once this is confirmed working.
TEST_DB_PATH = "data/test_part7a_run.db"  # throwaway, never the real DB

if not config.GEMINI_API_KEY:
    print(
        "GEMINI_API_KEY is not set.\n\n"
        "Get a free key at https://aistudio.google.com/apikey (Google "
        "account, no credit card), then either:\n"
        "  - create a .env file in this project's root containing:\n"
        "        GEMINI_API_KEY=your-key-here\n"
        "  - or export it in your shell:\n"
        "        export GEMINI_API_KEY=your-key-here\n\n"
        "Then re-run: python test_part7a.py"
    )
    sys.exit(0)

if os.path.exists(TEST_DB_PATH):
    os.remove(TEST_DB_PATH)
    print(f"Removed leftover {TEST_DB_PATH} from a prior run.\n")


def _print_pass(label: str, out: dict) -> None:
    print("\n" + "#" * 78)
    print(f"# {label}")
    print("#" * 78)
    print(f"store_summary:       {out['store_summary']}")
    print(f"enrichment_summary:  {out['enrichment_summary']}")
    print(f"scrape_problems:     {len(out['scrape_problems'])}")

    for entry in out["assembled"]:
        print("\n" + "=" * 78)
        raw = entry["raw"]
        print(f"DEBTOR: {raw.get('corporate_debtor')}")
        print(f"status={entry['status']}  listing_key={entry['listing_key']}")
        if entry["status"] == "changed":
            print(f"  changes: {entry['changes']}  price_drop={entry['price_drop']}")
        print(f"  scores: 5a={entry['score']['5a']['partial_score_5a']}  "
              f"5b={entry['score']['5b']['partial_score_5b']}  "
              f"5c={entry['score']['5c']['partial_score_5c']}")

        if entry["status"] == "collision":
            print(f"  ENRICHMENT SKIPPED (collision): {entry['flags']}")
            continue

        enr = entry["enrichment"]
        print(f"  enrichment_reused={entry['enrichment_reused']}")
        if enr is None:
            print("  ENRICHMENT ROW IS NONE -- this should not happen outside "
                  "the collision case above; flag this in PROJECT_STATUS.md "
                  "if you see it.")
            continue

        import json
        gemini = json.loads(enr["gemini_narrative_json"]) if enr["gemini_narrative_json"] else None
        mca = json.loads(enr["mca_data_json"]) if enr["mca_data_json"] else None
        news_data = json.loads(enr["news_data_json"]) if enr["news_data_json"] else None
        news_flags = json.loads(enr["news_flags_json"]) if enr["news_flags_json"] else []

        if gemini and gemini.get("narrative"):
            n = gemini["narrative"]
            print(f"  narrative.summary:    {n.get('summary')}")
            print(f"  narrative.price_read: {n.get('price_read')}")
        if gemini and gemini.get("flags"):
            print(f"  narrative FLAGS: {gemini['flags']}")

        if mca and mca.get("mca_data"):
            print(f"  mca_data: {mca['mca_data']}")
        if mca and mca.get("flags"):
            print(f"  mca FLAGS: {mca['flags']}")

        if news_data:
            print(f"  news_data ({len(news_data)} UNVERIFIED hit(s)):")
            for hit in news_data:
                print(f"    - {hit.get('title')} ({hit.get('url')})")
        if news_flags:
            print(f"  news FLAGS: {news_flags}")


print(f"Running Part 7A pipeline, pass 1 (max_pages={MAX_PAGES}, real network) ...")
out1 = run_pipeline(max_pages=MAX_PAGES, db_path=TEST_DB_PATH)
_print_pass("PASS 1", out1)

print(
    "\n\nRunning pass 2 immediately (same max_pages, same DB) -- most "
    "listings should now come back 'unchanged' with enrichment_reused=True "
    "and NO new Gemini/MCA/DuckDuckGo calls for them ..."
)
out2 = run_pipeline(max_pages=MAX_PAGES, db_path=TEST_DB_PATH)
_print_pass("PASS 2", out2)

print("\n\n" + "#" * 78)
print("SUMMARY")
print("#" * 78)
print(f"Pass 1 store_summary:       {out1['store_summary']}")
print(f"Pass 1 enrichment_summary:  {out1['enrichment_summary']}")
print(f"Pass 2 store_summary:       {out2['store_summary']}")
print(f"Pass 2 enrichment_summary:  {out2['enrichment_summary']}")
print(
    "\nExpected (not guaranteed -- IBBI's live data can genuinely change "
    "between the two passes): pass 2's 'unchanged' count in store_summary "
    "should roughly match its 'reused' count in enrichment_summary, and "
    "'reenriched' should be low/zero unless something on the live site "
    "actually changed between pass 1 and pass 2."
)
print(
    f"\nThrowaway test DB left at {TEST_DB_PATH} for inspection -- delete it "
    "manually (or just re-run this script, which removes it first) once "
    "you're done checking the output above."
)
print(
    "\nDone. Paste this full output back so Part 7A can be marked confirmed "
    "in PROJECT_STATUS.md -- read through pass 2 especially for real reuse "
    "(not just the offline synthetic test in pipeline.py's own __main__)."
)
