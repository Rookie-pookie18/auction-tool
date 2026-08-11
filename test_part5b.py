"""
test_part5b.py — real-network confirmation for Part 5B (possession_status
via notice_pdf_url parsing + land_classification).

Run this from the project root (where config.py lives):
    python test_part5b.py

Note: per PROJECT_STATUS.md Section 0 rule 2, the code-running sandbox has
no network access -- this has to be run on the owner's own machine, same
as test_part4.py / test_part5a.py were.

What it does:
  1. Scrapes page 1 of IBBI's live listing table (real network call).
  2. Runs Part 3C's details-PDF enrichment (so nature_of_assets/location
     etc. are populated, matching a normal run).
  3. Runs the NEW Part 5B notice-PDF enrichment (enrich_all_with_notice())
     on the FULL batch (all 20) -- widened 2026-08-09 after real run #1
     (5 listings) came back 0/5 + 0/5 and manual inspection of two real
     notice PDFs found that "physical possession"/"symbolic possession"
     is SARFAESI-notice vocabulary, not something IBBI liquidation sale
     notices (governed by Liquidation Process Regs 32/33, "as is where
     is... without recourse") reliably use at all. Running the full batch
     (still cheap -- no new code, just more of what already works) is how
     we find out whether that's ALWAYS true for IBBI or just true for
     those first 5, before deciding whether possession_status is worth
     keeping in the score model long-term.
  4. Scores the batch with scoring.rules.score_batch_5b() and prints
     possession_status, land_classification, and partial_score_5b per
     listing.

Paste the full printed output (or the full traceback, if it errors) back
so Part 5B can be marked confirmed in PROJECT_STATUS.md. Things to check
in the output:
  - Does ANY listing across all 20 show a real possession_status (physical
    or symbolic)? If genuinely 0/20, that's a real, confirmed finding
    about IBBI's notice format (not a bug) -- see decision needed below.
  - Any "scanned/image-based PDF" flags are fine (expected failure mode,
    not a bug) -- just sanity-check they're not 20/20.
  - land_classification values look sane against what nature_of_assets
    says for the same listing.
"""

import sys
sys.path.insert(0, ".")

from scraper.ibbi import scrape_all_pages, enrich_all_with_details, enrich_all_with_notice
from scoring.rules import score_batch_5b

print("Fetching page 1 from ibbi.gov.in ...")
recs, problems = scrape_all_pages(max_pages=1)
print("scraped:", len(recs), "problems:", len(problems))

print("\nEnriching with details-PDF data (Part 3C, so the batch looks like a normal run) ...")
enrich_all_with_details(recs)

# Widened to the full batch 2026-08-09 (was capped to 5) -- see module
# docstring. This means 20 notice-PDF fetches, so this run will take
# noticeably longer than the first one; that's expected, not a hang.
sample = recs
print(f"\nEnriching {len(sample)} of {len(recs)} listings with notice-PDF data (Part 5B) ...")
enrich_all_with_notice(sample)

parsed_ok = sum(1 for r in sample if r.notice_pdf_parsed)
print(f"{parsed_ok}/{len(sample)} listings had a notice-PDF enrichment attempt run "
      f"(True even if nothing was found -- see flags per listing below).")

print("\nScoring batch (Part 5B: possession_status + land_classification) ...")
scores = score_batch_5b(sample)

print(f"\n{'debtor':<35} {'nature_of_assets':<30} {'possession':<10} {'classification':<16}  flags")
for rec, res in zip(sample, scores):
    debtor = (rec.corporate_debtor or "")[:34]
    noa = (rec.nature_of_assets or "")[:29]
    possession = rec.possession_status or "(unknown)"
    classification = rec.land_classification or "(unknown)"
    flags = res["flags"]
    print(f"{debtor:<35} {noa:<30} {possession:<10} {classification:<16}  {flags}")

n_possession_found = sum(1 for r in sample if r.possession_status is not None)
n_classification_found = sum(1 for r in sample if r.land_classification is not None)
n_scanned = sum(1 for r in sample if any("scanned/image-based" in f for f in r.flags))
print(f"\n{n_possession_found}/{len(sample)} listings got a possession_status "
      f"(physical or symbolic) from the notice PDF.")
print(f"{n_classification_found}/{len(sample)} listings got a land_classification "
      f"(from notice PDF text or nature_of_assets fallback).")
print(f"{n_scanned}/{len(sample)} listings had a scanned/unextractable notice PDF "
      f"(expected failure mode, not a bug).")
print("\nDone. Confirm this looks right before Part 5B is marked confirmed "
      "in PROJECT_STATUS.md. If possession_status is still 0 (or very low) "
      "across the full 20, that's a real finding to record as a decision, "
      "not something to keep debugging.")
