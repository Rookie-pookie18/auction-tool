"""
test_part4.py — real-network confirmation for Part 4 (SQLite storage).

Run this from the project root (where config.py lives):
    python test_part4.py

What it does:
  1. Scrapes page 1 of IBBI's live listing table (real network call).
  2. Stores those records in data/auctions.db via storage/db.py.
  3. Runs the exact same records through storage a second time, to prove
     the "unchanged" detection works on a real re-scrape, not just the
     synthetic fixtures in storage/db.py's own __main__ block.

Paste the full printed output (or the full traceback, if it errors) back
so Part 4 can be marked confirmed in PROJECT_STATUS.md.
"""

import sys
sys.path.insert(0, ".")

from scraper.ibbi import scrape_all_pages
from storage.db import get_connection, store_records

print("Fetching page 1 from ibbi.gov.in ...")
recs, problems = scrape_all_pages(max_pages=1)
print("scraped:", len(recs), "problems:", len(problems))

conn = get_connection("data/auctions.db")

result = store_records(conn, recs)
print("first run:", result["summary"])

result2 = store_records(conn, recs)
print("re-run (should be all unchanged):", result2["summary"])

conn.close()
print("\nDone. data/auctions.db now has this run's data in it.")
