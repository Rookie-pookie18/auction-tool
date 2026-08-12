"""
test_part8a.py — real-network, real-send confirmation for Part 8A (email
delivery, email_delivery/smtp_send.py).

Run this from the project root (where config.py lives):
    python test_part8a.py

Before running, you need:
  1. A Gmail account with 2-Step Verification turned ON.
  2. A Gmail App Password: https://myaccount.google.com/apppasswords
     (16 characters, no spaces when you paste it). This is NOT your normal
     Gmail login password -- Gmail blocks plain-password SMTP login.
  3. Fill in config.py locally (not committed with real values):
         EMAIL_FROM = "your.gmail.address@gmail.com"
         EMAIL_TO   = "your.gmail.address@gmail.com"   # or a different inbox
     (SMTP_HOST/SMTP_PORT already default correctly for Gmail -- no change
     needed unless you're using a different provider.)
  4. Put the App Password in a local .env file in the project root (never
     committed -- .gitignore already excludes .env):
         SMTP_APP_PASSWORD=your16charapppassword
     ...or export it in your shell instead:
         export SMTP_APP_PASSWORD=your16charapppassword

Note: per PROJECT_STATUS.md Section 0 rule 2, the code-running sandbox has
no network access -- the IBBI scrape AND the real SMTP send below both have
to run on the owner's own machine, same as every other test_partN.py so far.

What it does:
  1. Runs a SMALL real pipeline pass (max_pages=1, same "small on purpose"
     pattern as every other real-network test in this project) via
     pipeline.run_pipeline() -- real scrape, real store, real score, real
     Part 6 enrichment (subject to normal needs_reenrichment() reuse).
  2. Builds a real PDF via report.pdf.generate_report() into a throwaway
     path under data/reports/, exactly like a real run would.
  3. Sends a REAL email via email_delivery.smtp_send.send_report_email()
     with that PDF attached, to config.EMAIL_TO.

Paste the full printed output (or the full traceback, if it errors) back
so Part 8A can be marked confirmed in PROJECT_STATUS.md. Things to check:
  - Did the script print "EMAIL SENT" with no exception?
  - Did the email actually arrive in the EMAIL_TO inbox (check spam too,
    first send from a new sender pattern sometimes lands there)?
  - Does the subject line show today's date?
  - Does the PDF attachment open correctly and match what
    generate_report() would produce (same content as Part 7B's own
    confirmed output)?
  - Does the plain-text body's summary counts look sane / match what the
    pipeline actually did this run?
"""

import sys
sys.path.insert(0, ".")

import os
import tempfile

import config
from pipeline import run_pipeline
from report.pdf import generate_report, categorize_assembled
from email_delivery.smtp_send import send_report_email

MAX_PAGES = 1  # kept small on purpose for this first confirmation run --
                # real Gemini/MCA/DuckDuckGo quota may be spent on
                # not-yet-seen listings, plus this is a real email send.

missing = []
if not config.EMAIL_FROM:
    missing.append("config.EMAIL_FROM")
if not config.EMAIL_TO:
    missing.append("config.EMAIL_TO")
if not config.SMTP_PASSWORD:
    missing.append("SMTP_APP_PASSWORD (env var / .env)")

if missing:
    print(
        "test_part8a.py: cannot run -- missing required setting(s): "
        + ", ".join(missing)
        + ". See this file's own module docstring for exact setup steps."
    )
    sys.exit(1)

print(f"--- Running a small real pipeline pass (max_pages={MAX_PAGES}) ---")
# Throwaway DB path so this confirmation run never touches the owner's
# real data/auctions.db -- same pattern as test_part7a.py.
db_fd, db_path = tempfile.mkstemp(suffix=".db")
os.close(db_fd)
os.remove(db_path)  # get_connection() creates it fresh

try:
    result = run_pipeline(max_pages=MAX_PAGES, db_path=db_path)
    print(f"  store_summary: {result['store_summary']}")
    print(f"  enrichment_summary: {result['enrichment_summary']}")
    print(f"  scrape_problems: {len(result['scrape_problems'])}")
    print(f"  assembled listings: {len(result['assembled'])}")

    print("\n--- Building the PDF ---")
    pdf_path = generate_report(
        result["assembled"],
        output_path=os.path.join(config.REPORT_OUTPUT_DIR, "test_part8a_report.pdf"),
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

    print(f"\n--- Sending real email to {config.EMAIL_TO} ---")
    send_report_email(
        pdf_path=pdf_path,
        run_summary={
            "store_summary": result["store_summary"],
            "enrichment_summary": result["enrichment_summary"],
            "scrape_problems": result["scrape_problems"],
        },
        categorized_counts=categorized_counts,
    )
    print("EMAIL SENT -- check the inbox (and spam folder) for "
          f"{config.EMAIL_TO!r} now.")

finally:
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except OSError as e:
        # Should not happen now that run_pipeline() closes its own
        # connection in a finally block (fixed 2026-08-11) -- kept as a
        # non-fatal fallback rather than removed outright, since a
        # leftover temp DB file is harmless (it's in the OS temp dir,
        # not the project folder) and must never mask whether the real
        # send above succeeded.
        print(f"  (non-fatal: could not remove temp DB {db_path!r}: {e})")
