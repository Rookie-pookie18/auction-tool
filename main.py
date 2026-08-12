"""
main.py — Part 8B: the real production entry point.

--------------------------------------------------------------------------
WHY THIS FILE EXISTS (flagged per Section 0 rule 1, not silently assumed):
test_part8a.py proved the full scrape -> store -> score -> enrich -> PDF ->
email chain works end to end, but it is deliberately NOT the production
script -- it uses a throwaway tempfile DB (deleted at the end) and a small
max_pages=1, exactly right for a one-off confirmation run, exactly wrong
for a real daily cron run (a throwaway DB defeats Part 7A's whole reuse
mechanism, and max_pages=1 wouldn't see the site's full active listing
set). This file is the actual thing GitHub Actions runs every morning:
  - real DB: config.DB_PATH ("data/auctions.db"), the one Part 8B's
    workflow commits back to the repo after this script exits, so it
    persists to tomorrow's run (see PROJECT_STATUS.md decision (31) for
    why that persistence step exists at all -- GitHub-hosted runners are
    ephemeral, nothing on disk survives between runs on its own).
  - real max_pages: None (the site's full current listing set), not a
    small smoke-test slice.

Run from the project root (same convention as every test_partN.py):
    python main.py

Exits non-zero (via an uncaught exception) on a hard failure -- e.g. a
real SMTP send failure, per email_delivery/smtp_send.py's own "do not
swallow the last step's errors" design. A non-zero exit is what makes a
real failure show up as a failed, visibly-red GitHub Actions run rather
than a silent no-op.
--------------------------------------------------------------------------
"""

import sys
sys.path.insert(0, ".")

import os
from datetime import date

import config
from pipeline import run_pipeline
from report.pdf import generate_report, categorize_assembled
from email_delivery.smtp_send import send_report_email

missing = []
if not config.EMAIL_FROM:
    missing.append("EMAIL_FROM")
if not config.EMAIL_TO:
    missing.append("EMAIL_TO")
if not config.SMTP_PASSWORD:
    missing.append("SMTP_APP_PASSWORD")
if not config.GEMINI_API_KEY:
    missing.append("GEMINI_API_KEY")
if missing:
    print(
        "main.py: cannot run -- missing required env var(s)/secret(s): "
        + ", ".join(missing)
        + ". See .github/workflows/daily_report.yml (env: block) for where "
        "these need to be set as repo secrets, or README.md for local setup."
    )
    sys.exit(1)

today = date.today()
print(f"=== Auction Intelligence Tool -- daily run, {today.isoformat()} ===")
print(f"Using DB: {config.DB_PATH}")

# No max_pages cap and no throwaway db_path here, unlike every
# test_partN.py real-network test -- this is the real production run
# against the real persisted DB (config.DB_PATH via db_path=None), over
# the site's full current listing set (max_pages=None).
result = run_pipeline(max_pages=None, db_path=None)
print(f"  store_summary: {result['store_summary']}")
print(f"  pdf_fetch_summary: {result['pdf_fetch_summary']}")
print(f"  enrichment_summary: {result['enrichment_summary']}")
print(f"  scrape_problems: {len(result['scrape_problems'])}")
print(f"  assembled listings: {len(result['assembled'])}")

print("\n--- Building the PDF ---")
pdf_path = generate_report(
    result["assembled"],
    run_summary={
        "store_summary": result["store_summary"],
        "enrichment_summary": result["enrichment_summary"],
        "scrape_problems": result["scrape_problems"],
    },
)
print(f"  PDF written: {pdf_path} ({os.path.getsize(pdf_path)} bytes)")

categorized = categorize_assembled(result["assembled"])
categorized_counts = {
    "top_scored": len(categorized["top_scored"]),
    "closing_soon": len(categorized["closing_soon"]),
    "new_today": len(categorized["new_today"]),
    "watchlist_changes": len(categorized["watchlist_changes"]),
    "collisions": len(categorized["collisions"]),
}
print(f"  categorized_counts: {categorized_counts}")

print(f"\n--- Sending email to {config.EMAIL_TO} ---")
send_report_email(
    pdf_path=pdf_path,
    run_summary={
        "store_summary": result["store_summary"],
        "enrichment_summary": result["enrichment_summary"],
        "scrape_problems": result["scrape_problems"],
    },
    categorized_counts=categorized_counts,
)
print("EMAIL SENT.")
print("=== Run complete. data/auctions.db updated on disk; "
      "the workflow commits it back to the repo next. ===")
