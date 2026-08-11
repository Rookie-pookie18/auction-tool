"""
test_part6a.py — real-network confirmation for Part 6A (AI narrative via
Gemini, ai_analysis/gemini_narrative.py).

Run this from the project root (where config.py lives):
    python test_part6a.py

Before running, you need a free Gemini API key:
  1. https://aistudio.google.com/apikey -- sign in with a Google account,
     no credit card needed.
  2. Put it in a local .env file in the project root (never committed --
     .gitignore already excludes .env):
         GEMINI_API_KEY=your-key-here
     ...or just export it in your shell instead:
         export GEMINI_API_KEY=your-key-here

Note: per PROJECT_STATUS.md Section 0 rule 2, the code-running sandbox has
no network access -- both the IBBI scrape AND the Gemini call below have to
run on the owner's own machine, same as every other test_partN.py so far.

What it does:
  1. Scrapes a SMALL slice of IBBI's live listing table (MAX_RECORDS below
     -- kept small on purpose for this first confirmation run, since it's
     real API quota being spent, not just a network call. Raise it later
     once this is confirmed working.).
  2. Runs Part 3C's details-PDF enrichment (location/plot_area_mentions/
     etc.) so the narrative has more than just the bare table row to work
     with -- same enrichment prior test scripts used.
  3. Calls generate_narratives_for_batch() for real against Gemini and
     prints each listing's summary / price_read / risk_notes / data_gaps,
     plus any flags (missing-key, rate-limited, blocked, malformed, etc.).

Paste the full printed output (or the full traceback, if it errors) back
so Part 6A can be marked confirmed in PROJECT_STATUS.md. Things to check
in the output:
  - Does `summary` actually describe the right listing (right debtor,
    right notice type/dates) and stay grounded in the data shown, without
    inventing outside facts about the company?
  - Does `price_read` correctly say "no comparable data" rather than
    inventing a fairness judgment out of nothing (there's no market-value
    field to compare against -- see PROJECT_STATUS.md Section 2)?
  - Do `risk_notes`/`data_gaps` look like real, useful buyer-relevant
    observations rather than generic filler?
  - Any flags at all (missing key, HTTP errors, blocked content, JSON
    parse failures)? Those need to be visible here, not just success
    cases.
"""

import sys
sys.path.insert(0, ".")

import config
from scraper.ibbi import scrape_all_pages, enrich_all_with_details
from ai_analysis.gemini_narrative import generate_narratives_for_batch

MAX_RECORDS = 5  # kept small for the first confirmation run -- real API
                  # quota, not just a network call. Raise once confirmed.

if not config.GEMINI_API_KEY:
    print(
        "GEMINI_API_KEY is not set.\n\n"
        "Get a free key at https://aistudio.google.com/apikey (Google "
        "account, no credit card), then either:\n"
        "  - create a .env file in this project's root containing:\n"
        "        GEMINI_API_KEY=your-key-here\n"
        "  - or export it in your shell:\n"
        "        export GEMINI_API_KEY=your-key-here\n\n"
        "Then re-run: python test_part6a.py"
    )
    sys.exit(0)

print("Fetching page 1 from ibbi.gov.in ...")
recs, problems = scrape_all_pages(max_pages=1)
recs = recs[:MAX_RECORDS]
print(f"scraped: {len(recs)} (capped at MAX_RECORDS={MAX_RECORDS}), problems: {len(problems)}")

print("\nEnriching with details-PDF data (Part 3C) ...")
enrich_all_with_details(recs)

print(f"\nCalling Gemini ({config.GEMINI_MODEL}) for {len(recs)} listings, "
      f"{config.GEMINI_REQUEST_DELAY_SECONDS}s between calls ...")
results = generate_narratives_for_batch(recs)

n_ok = 0
n_failed = 0
for rec, res in zip(recs, results):
    print("\n" + "=" * 78)
    print(f"DEBTOR: {rec.corporate_debtor}")
    print(f"notice_type={rec.notice_type}  reserve_price={rec.reserve_price}  "
          f"location={rec.location}")
    if res["narrative"] is not None:
        n_ok += 1
        n = res["narrative"]
        print(f"  summary:    {n.get('summary')}")
        print(f"  price_read: {n.get('price_read')}")
        print(f"  risk_notes: {n.get('risk_notes')}")
        print(f"  data_gaps:  {n.get('data_gaps')}")
    else:
        n_failed += 1
    if res["flags"]:
        print(f"  FLAGS: {res['flags']}")

print("\n" + "=" * 78)
print(f"\n{n_ok}/{len(recs)} listings got a real narrative back from Gemini.")
print(f"{n_failed}/{len(recs)} failed (see FLAGS above for why each one did).")
print("\nDone. Read through the summaries/price_read above for grounding and "
      "honesty (no invented outside facts, no invented price fairness) "
      "before Part 6A is marked confirmed in PROJECT_STATUS.md.")
