"""
test_part5a.py — real-network confirmation for Part 5A (rule-based
scoring: price_vs_reserve + location_match only).

Run this from the project root (where config.py lives):
    python test_part5a.py

Note: per PROJECT_STATUS.md Section 0 rule 2, the code-running sandbox
has no network access -- this has to be run on the owner's own machine,
same as test_part4.py was.

What it does:
  1. Scrapes page 1 of IBBI's live listing table (real network call).
  2. Runs Part 3C's details-PDF enrichment on those records, so at least
     some of them have a real `location` field to score location_match
     against (without this, every listing would fall into the "location
     not yet known" neutral path, which wouldn't actually exercise the
     bonus logic).
  3. Stores them via storage/db.py (Part 4), same as test_part4.py.
  4. Scores the batch with scoring.rules.score_batch_5a() and prints
     every listing's price_vs_reserve score, location_match score/bonus,
     and partial_score_5a, sorted best-first.

Paste the full printed output (or the full traceback, if it errors) back
so Part 5A can be marked confirmed in PROJECT_STATUS.md.
"""

import sys
sys.path.insert(0, ".")

from scraper.ibbi import scrape_all_pages, enrich_all_with_details
from storage.db import get_connection, store_records
from scoring.rules import score_batch_5a

print("Fetching page 1 from ibbi.gov.in ...")
recs, problems = scrape_all_pages(max_pages=1)
print("scraped:", len(recs), "problems:", len(problems))

print("\nEnriching with details-PDF data (location, emd_amount, cin) ...")
enrich_all_with_details(recs)
with_location = sum(1 for r in recs if r.location)
print(f"{with_location}/{len(recs)} listings have a location after enrichment")

conn = get_connection("data/auctions.db")
result = store_records(conn, recs)
print("\nstorage result:", result["summary"])
conn.close()

print("\nScoring batch (Part 5A: price_vs_reserve + location_match) ...")
scores = score_batch_5a(recs)

# Sort best-first by partial_score_5a; listings with no score at all
# (shouldn't happen -- location_match always returns a number -- but
# guard against it rather than crashing on a sort) go last.
ranked = sorted(
    zip(recs, scores),
    key=lambda pair: (pair[1]["partial_score_5a"] is None, -(pair[1]["partial_score_5a"] or 0)),
)

print(f"\n{'debtor':<35} {'reserve_price':>13} {'price_score':>11} {'location':<25} {'loc_score':>9} {'matched':<15} {'partial':>7}  flags")
for rec, res in ranked:
    debtor = (rec.corporate_debtor or "")[:34]
    price = rec.reserve_price if rec.reserve_price is not None else "?"
    price_score = res["price_vs_reserve"]["score"]
    loc = (rec.location or "(unknown)")[:24]
    loc_score = res["location_match"]["score"]
    matched = res["location_match"]["matched_region"] or "-"
    partial = res["partial_score_5a"]
    flags = res["flags"]
    print(f"{debtor:<35} {price!s:>13} {price_score!s:>11} {loc:<25} {loc_score!s:>9} {matched:<15} {partial!s:>7}  {flags}")

n_missing_price = sum(1 for r in scores if r["price_vs_reserve"]["score"] is None)
n_bonus = sum(1 for r in scores if r["location_match"]["matched_region"] is not None)
print(f"\n{n_missing_price}/{len(scores)} listings missing reserve_price (not scored on that criterion, not defaulted).")
print(f"{n_bonus}/{len(scores)} listings matched a preferred region (Delhi/Rajpura/Madhya Pradesh) and got the location bonus.")
print("\nDone. Confirm this looks right (cheaper reserve price -> higher "
      "price_score, preferred-region matches -> higher loc_score, nothing "
      "excluded for being expensive or out-of-region) before Part 5A is "
      "marked confirmed.")
