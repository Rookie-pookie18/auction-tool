"""
test_part6b.py — real confirmation for Part 6B (MCA company master-data
lookup, ai_analysis/mca_lookup.py) -- now reading LOCAL downloaded CSV
files rather than a live API (see config.py's Part 6B comment and
PROJECT_STATUS.md decisions (17)-(21) for why this changed). The lookup
matches a real downloaded CSV's headers case-insensitively against a list
of plausible variants (not just the live API's exact field names), and
normalizes CIN values (strip/upper) on both sides -- see
mca_lookup.py's module docstring, "HEADER-MATCHING ROBUSTNESS", for why.
This is offline-tested already; this run is the first real confirmation
against an actual downloaded state CSV.

Run this from the project root (where config.py lives):
    python test_part6b.py

--------------------------------------------------------------------------
BEFORE RUNNING -- download at least one state's data (README.md's Part 6B
section has the exact click-path on data.gov.in): pick a state, request +
download its CSV, and save it as
    data/mca_company_master/<state_name_with_underscores>.csv
No API key needed anymore. This script will still run with ZERO states
downloaded -- it'll just show a clean "no local file" flag for every
listing, same as it would for any other missing piece of enrichment.

Note: per PROJECT_STATUS.md Section 0 rule 2, the code-running sandbox has
no network access -- the IBBI scrape below has to run on the owner's own
machine, same as every other test_partN.py so far. (The MCA half of this
script needs NO network at all now -- it's pure local file reads.)

--------------------------------------------------------------------------
What it does:
  1. Scrapes a SMALL slice of IBBI's live listing table (MAX_RECORDS
     below).
  2. Runs Part 3C's details-PDF enrichment so records have a `cin` to look
     up (MCA lookup is CIN-only -- see mca_lookup.py's module docstring
     for why).
  3. For each listing, shows which state its CIN maps to and whether that
     state's CSV is present locally yet.
  4. Calls enrich_batch_with_mca() and prints, per listing: the resulting
     mca_data fields if a match was found, or the flag explaining why not
     (no CIN, unmapped state, missing local file, or no match inside a
     file that IS present).

Paste the full printed output back so Part 6B can be marked confirmed in
PROJECT_STATUS.md. Things to check in the output:
  - For any state whose CSV you DID download: did at least one listing
    from that state get a real match? Does mca_data.company_name look
    like a plausible match for the listing's corporate_debtor (allowing
    for formatting differences)? Do the other fields (company_status,
    dates, capital figures) look like real, sane data?
  - For states without a downloaded CSV yet: you should see a clean flag
    naming the exact expected file path -- useful for deciding which
    states are worth downloading next based on what your actual scraped
    listings need.
"""

import sys
sys.path.insert(0, ".")

import os
import config
from scraper.ibbi import scrape_all_pages, enrich_all_with_details
from ai_analysis.mca_lookup import (
    enrich_batch_with_mca,
    state_name_from_cin,
    expected_csv_path_for_state,
)

MAX_RECORDS = 10  # kept modest for this first confirmation run.

print(f"Looking for local MCA data under: {config.MCA_LOCAL_DATA_DIR}")
if os.path.isdir(config.MCA_LOCAL_DATA_DIR):
    found = [f for f in os.listdir(config.MCA_LOCAL_DATA_DIR) if f.endswith(".csv")]
    print(f"  {len(found)} state file(s) found: {found}" if found else
          "  Directory exists but no .csv files in it yet.")
else:
    print("  Directory doesn't exist yet -- every listing below will show "
          "a 'no local file' flag until at least one state's CSV is "
          "downloaded (see README.md's Part 6B section).")

print("\nFetching page 1 from ibbi.gov.in ...")
recs, problems = scrape_all_pages(max_pages=1)
recs = recs[:MAX_RECORDS]
print(f"scraped: {len(recs)} (capped at MAX_RECORDS={MAX_RECORDS}), problems: {len(problems)}")

print("\nEnriching with details-PDF data (Part 3C) -- this is where `cin` "
      "gets populated, which Part 6B's lookup needs ...")
enrich_all_with_details(recs)
n_with_cin = sum(1 for r in recs if r.cin)
print(f"{n_with_cin}/{len(recs)} listings got a CIN from Part 3C.")

print("\nRunning MCA lookups (local file reads, no network) ...")
results = enrich_batch_with_mca(recs)

n_matched = 0
n_no_cin = 0
n_unmapped_state = 0
n_missing_file = 0
n_no_match_in_file = 0
for rec, res in zip(recs, results):
    print("\n" + "=" * 78)
    print(f"DEBTOR: {rec.corporate_debtor}")
    derived_state = state_name_from_cin(rec.cin) if rec.cin else None
    expected_path = expected_csv_path_for_state(derived_state) if derived_state else None
    file_present = os.path.isfile(expected_path) if expected_path else False
    print(f"cin={rec.cin!r}   derived state={derived_state!r}   "
          f"expected file={expected_path!r}   present={file_present}")
    if res["mca_data"] is not None:
        n_matched += 1
        m = res["mca_data"]
        print(f"  MATCHED -- company_name: {m.get('company_name')}")
        print(f"  company_status: {m.get('company_status')}   "
              f"category: {m.get('company_category')}   "
              f"class: {m.get('company_class')}   "
              f"sub_category: {m.get('sub_category')}")
        print(f"  date_of_registration: {m.get('date_of_registration')}   "
              f"registered_state: {m.get('registered_state')}   "
              f"registrar_of_companies: {m.get('registrar_of_companies')}")
        print(f"  authorized_capital: {m.get('authorized_capital')}   "
              f"paidup_capital: {m.get('paidup_capital')}")
        print(f"  registered_office_address: {m.get('registered_office_address')}")
        print(f"  principal_business_activity: {m.get('principal_business_activity')}")
    else:
        if not rec.cin:
            n_no_cin += 1
        elif derived_state is None:
            n_unmapped_state += 1
        elif not file_present:
            n_missing_file += 1
        else:
            n_no_match_in_file += 1
    if res["flags"]:
        print(f"  FLAGS: {res['flags']}")

print("\n" + "=" * 78)
print(f"\n{n_matched}/{len(recs)} listings got a real MCA match.")
print(f"{n_no_cin}/{len(recs)} had no CIN to look up (Part 3C didn't parse one).")
print(f"{n_unmapped_state}/{len(recs)} had a CIN but an unrecognized embedded state code.")
print(f"{n_missing_file}/{len(recs)} had a valid state but that state's CSV isn't downloaded yet.")
print(f"{n_no_match_in_file}/{len(recs)} had a downloaded file for the right state but no matching CIN row in it.")

needed_states = sorted({
    state_name_from_cin(r.cin) for r in recs
    if r.cin and state_name_from_cin(r.cin)
})
missing = [s for s in needed_states if not os.path.isfile(expected_csv_path_for_state(s))]
if missing:
    print(f"\nTo get real matches on THIS run's listings, download these "
          f"{len(missing)} state export(s) (one-time each, see README.md's "
          f"Part 6B section for the exact click-path), then re-run:")
    for s in missing:
        print(f"  - {s}  ->  save as {expected_csv_path_for_state(s)}")
else:
    print("\nAll state exports this run's listings need are already downloaded locally.")

print("\nDone. Read through any matched company_name/company_status/dates "
      "above for plausibility (right company, sane-looking values) before "
      "Part 6B is marked confirmed in PROJECT_STATUS.md. If every listing "
      "shows 'missing file', download at least one relevant state's CSV "
      "(see README.md's Part 6B section) and re-run.")
