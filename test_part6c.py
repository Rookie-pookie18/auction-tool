"""
test_part6c.py — real-network confirmation for Part 6C (unofficial
web-search news pass, ai_analysis/news_search.py).

Run this from the project root (where config.py lives):
    python test_part6c.py

No API key needed for this one -- DuckDuckGo's HTML endpoint is queried
directly, no signup. (config.NEWS_SEARCH_ENABLED must be True, which it
is by default.)

Note: per PROJECT_STATUS.md Section 0 rule 2, the code-running sandbox has
no network access -- both the IBBI scrape AND the DuckDuckGo call below
have to run on the owner's own machine, same as every other
test_partN.py so far.

What it does:
  1. Scrapes a SMALL slice of IBBI's live listing table (MAX_RECORDS below).
  2. Runs Part 3C's details-PDF enrichment (so `location` is available for
     the query-narrowing heuristic described in news_search.py).
  3. Calls enrich_batch_with_news() for real against DuckDuckGo's HTML
     endpoint and prints each listing's results (title/url/snippet) or
     flags.

Paste the full printed output (or the full traceback, if it errors) back
so Part 6C can be marked confirmed in PROJECT_STATUS.md. Things to check
in the output:
  - Does at least SOME listing get real, non-empty results back? (If
    every single listing comes back with the "0 results" flag, that's
    the signal news_search.py's _parse_results() selectors don't match
    DuckDuckGo's real HTML right now -- see that function's docstring for
    exactly what to check/fix.)
  - For listings that DID get results, do the titles/snippets look
    plausibly related to the actual corporate_debtor (even loosely) --
    or do they look like unrelated noise from a too-common company name?
    This is exactly the "never trust blindly, label unverified" judgment
    call Section 2 calls for; this test doesn't try to auto-verify it.
  - Any HTTP-level flags (blocked / non-200 / network error)? If DDG is
    blocking this pattern of request outright, that needs to be visible
    here, not just silently degrading to empty results every time.
"""

import sys
sys.path.insert(0, ".")

import config
from scraper.ibbi import scrape_all_pages, enrich_all_with_details
from ai_analysis.news_search import enrich_batch_with_news

MAX_RECORDS = 5  # kept small for the first confirmation run, same spirit
                  # as test_part6a.py -- raise once confirmed working.

if not config.NEWS_SEARCH_ENABLED:
    print(
        "config.NEWS_SEARCH_ENABLED is False -- Part 6C is turned off.\n"
        "Set NEWS_SEARCH_ENABLED = True in config.py and re-run: "
        "python test_part6c.py"
    )
    sys.exit(0)

print("Fetching page 1 from ibbi.gov.in ...")
recs, problems = scrape_all_pages(max_pages=1)
recs = recs[:MAX_RECORDS]
print(f"scraped: {len(recs)} (capped at MAX_RECORDS={MAX_RECORDS}), problems: {len(problems)}")

print("\nEnriching with details-PDF data (Part 3C, for `location`) ...")
enrich_all_with_details(recs)

print(f"\nSearching DuckDuckGo for {len(recs)} listings, "
      f"{config.NEWS_SEARCH_REQUEST_DELAY_SECONDS}s between queries ...")
results = enrich_batch_with_news(recs)

n_ok = 0
n_failed = 0
total_results = 0
for rec, res in zip(recs, results):
    print("\n" + "=" * 78)
    print(f"DEBTOR: {rec.corporate_debtor}")
    print(f"location={rec.location}")
    if res["news_data"] is not None:
        n_ok += 1
        total_results += len(res["news_data"])
        for hit in res["news_data"]:
            print(f"  [UNVERIFIED] {hit['title']}")
            print(f"      {hit['url']}")
            if hit["snippet"]:
                print(f"      {hit['snippet']}")
        if res["flags"]:
            # A non-empty flag alongside real news_data means this hit came
            # from a broadened fallback tier (see news_search.py's
            # MATCHING STRATEGY) -- worth reading before trusting it as
            # much as a tier-1 hit.
            print(f"  NOTE: {res['flags']}")
    else:
        n_failed += 1
        print(f"  FLAGS: {res['flags']}")

print("\n" + "=" * 78)
print(f"\n{n_ok}/{len(recs)} listings got at least one real result back from DuckDuckGo.")
print(f"{n_failed}/{len(recs)} got zero results or failed (see FLAGS above for why each one did).")
print(f"total raw results across all listings: {total_results}")
print("\nDone. Read through the results above -- check they're plausibly "
      "related to the right company (not noise from a common name) before "
      "Part 6C is marked confirmed in PROJECT_STATUS.md. If EVERY listing "
      "shows the '0 results' flag, check news_search.py's _parse_results() "
      "selectors against DuckDuckGo's real HTML first.")
