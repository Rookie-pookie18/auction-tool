"""
test_part5c.py — real-network confirmation for Part 5C (plot_size_fit).

Run this from the project root (where config.py lives):
    python test_part5c.py

Note: per PROJECT_STATUS.md Section 0 rule 2, the code-running sandbox has
no network access -- this has to be run on the owner's own machine, same
as test_part4.py / test_part5a.py / test_part5b.py were.

What it does:
  1. Scrapes page 1 of IBBI's live listing table (real network call).
  2. Runs Part 3C's details-PDF enrichment (populates `plot_area_mentions`
     -- the raw area strings 5C turns into one clean sq-ft number).
  3. Scores the batch with scoring.rules.score_batch_5c() and prints, per
     listing: the raw plot_area_mentions, the resolved plot_size_sqft (or
     None + why), and the score.

No minimum plot size is set (config.MIN_PLOT_SIZE_SQFT = None, owner
decision 2026-08-09) -- every listing should score the same neutral
baseline (config.PLOT_SIZE_NEUTRAL) regardless of size. This run is about
confirming the UNIT PARSING is right on real data, not about the score
number itself.

Paste the full printed output (or the full traceback, if it errors) back
so Part 5C can be marked confirmed in PROJECT_STATUS.md. Things to check
in the output:
  - Do the resolved plot_size_sqft numbers look right for their raw
    mentions (e.g. "2 acres" -> 87120.0, "500 sq. mtrs" -> ~5381.9)?
  - Do listings with two genuinely different area figures (land vs
    building) correctly come back None + an "ambiguous" flag, rather than
    silently picking one?
  - Do listings with no area mentions at all correctly come back None +
    a "no area figure found" flag?
"""

import sys
sys.path.insert(0, ".")

from scraper.ibbi import scrape_all_pages, enrich_all_with_details
from scoring.rules import score_batch_5c

print("Fetching page 1 from ibbi.gov.in ...")
recs, problems = scrape_all_pages(max_pages=1)
print("scraped:", len(recs), "problems:", len(problems))

print("\nEnriching with details-PDF data (Part 3C, populates plot_area_mentions) ...")
enrich_all_with_details(recs)
with_mentions = sum(1 for r in recs if r.plot_area_mentions)
print(f"{with_mentions}/{len(recs)} listings have at least one raw area mention")

print("\nScoring batch (Part 5C: plot_size_fit) ...")
scores = score_batch_5c(recs)

print(f"\n{'debtor':<35} {'plot_area_mentions':<45} {'plot_size_sqft':>14} {'score':>6}  flags")
for rec, res in zip(recs, scores):
    debtor = (rec.corporate_debtor or "")[:34]
    mentions = str(rec.plot_area_mentions)[:44]
    sqft = res["plot_size_fit"]["plot_size_sqft"]
    score = res["plot_size_fit"]["score"]
    flags = res["flags"]
    print(f"{debtor:<35} {mentions:<45} {sqft!s:>14} {score!s:>6}  {flags}")

n_resolved = sum(1 for r in scores if r["plot_size_fit"]["plot_size_sqft"] is not None)
n_ambiguous = sum(1 for r in scores if any("multiple different" in f for f in r["flags"]))
n_missing = sum(1 for r in scores if any("no area figure found" in f for f in r["flags"]))
print(f"\n{n_resolved}/{len(scores)} listings resolved to a single clean plot_size_sqft.")
print(f"{n_ambiguous}/{len(scores)} listings had genuinely ambiguous area mentions (flagged, not guessed).")
print(f"{n_missing}/{len(scores)} listings had no area mention at all.")
print("\nDone. Confirm the unit conversions look right (spot-check a few "
      "against the raw mentions by hand) before Part 5C is marked "
      "confirmed in PROJECT_STATUS.md.")
