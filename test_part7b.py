"""
test_part7b.py — confirmation for Part 7B (report/pdf.py: PDF layout +
report categorization).

UNLIKE every other test_part*.py in this project, this one needs NO
network and NO owner-side run: PDF layout has no external dependency
(reportlab renders purely from the assembled dataset already in memory),
so this can genuinely be run and confirmed inside the sandbox, same as
Part 5/5B/5C's synthetic __main__ blocks were "confirmed on a real run"
using real IBBI data -- here "real" means a real reportlab render + a
real pypdf read-back of the actual bytes produced, not mocked out.

What it does:
  1. Builds a small synthetic `assembled`-shaped dataset covering every
     category report/pdf.py handles: top-scored, closing-soon, new-today,
     watchlist-changed (with a real diff), a collision (enrichment
     skipped), and a listing with missing price/location/dates/enrichment
     entirely (the "nothing available" case every card must survive).
  2. Runs report.pdf.categorize_assembled() and checks each listing landed
     in the right section(s).
  3. Runs report.pdf.generate_report() to a real temp file.
  4. Opens the real PDF with pypdf and checks: it has at least one page,
     every listing's corporate_debtor name appears somewhere in the
     extracted text, every section heading appears, and the watchlist
     change's old->new values both appear.

Run from the project root:
    python test_part7b.py
"""

import sys
import tempfile
from datetime import date, timedelta

sys.path.insert(0, ".")

from pypdf import PdfReader

from report.pdf import categorize_assembled, generate_report, combined_score

TODAY = date(2026, 8, 11)


def _entry(**kw):
    return {
        "listing_key": kw["listing_key"],
        "status": kw.get("status", "unchanged"),
        "changes": kw.get("changes", []),
        "price_drop": kw.get("price_drop", False),
        "raw": kw["raw"],
        "score": kw.get("score", {
            "5a": {"partial_score_5a": 65},
            "5b": {"partial_score_5b": 55},
            "5c": {"partial_score_5c": 50},
        }),
        "enrichment": kw.get("enrichment"),
        "enrichment_reused": kw.get("enrichment_reused", False),
        **({"flags": kw["flags"]} if "flags" in kw else {}),
    }


import json

TOP_LISTING = _entry(
    listing_key="top-1", status="unchanged",
    raw={
        "corporate_debtor": "Sunrise Steel Industries",
        "notice_type": "Sale Notice", "reserve_price": 12000000,
        "location": "Rajpura, Punjab",
        "auction_date": TODAY + timedelta(days=30), "emd_due_date": TODAY + timedelta(days=25),
        "ip_name": "Vikram Joshi", "nature_of_assets": "Industrial land 8 acres",
        "details_pdf_url": "http://fake/sunrise-details.pdf",
        "notice_pdf_url": "http://fake/sunrise-notice.pdf",
    },
    score={"5a": {"partial_score_5a": 92}, "5b": {"partial_score_5b": 80}, "5c": {"partial_score_5c": 70}},
    enrichment={
        "gemini_narrative_json": json.dumps({
            "narrative": {
                "summary": "Large industrial land parcel with highway access.",
                "price_read": "Reserve price is well below comparable listings this batch.",
                "risk_notes": [], "data_gaps": [],
            },
            "flags": [],
        }),
        "mca_data_json": json.dumps({"mca_data": {"company_name": "SUNRISE STEEL INDUSTRIES LTD", "status": "Under Liquidation"}, "flags": []}),
        "news_data_json": json.dumps([{"title": "Sunrise Steel liquidation sale draws interest", "url": "http://fake/news1"}]),
        "news_flags_json": json.dumps(["unverified web search result, not fact-checked"]),
    },
)

CLOSING_SOON_LISTING = _entry(
    listing_key="closing-1", status="unchanged",
    raw={
        "corporate_debtor": "Northgate Warehousing Pvt Ltd",
        "notice_type": "Liquidation Notice", "reserve_price": 3000000,
        "location": "Nagpur, Maharashtra",
        "auction_date": TODAY + timedelta(days=2), "emd_due_date": TODAY + timedelta(days=1),
        "ip_name": "Meena Iyer", "nature_of_assets": "Warehouse 1.5 acres",
    },
)

NEW_TODAY_LISTING = _entry(
    listing_key="new-1", status="new",
    raw={
        "corporate_debtor": "Harborview Realty Ltd",
        "notice_type": "Sale Notice", "reserve_price": 4500000,
        "location": "Delhi", "auction_date": TODAY + timedelta(days=45),
        "emd_due_date": TODAY + timedelta(days=40),
        "ip_name": "Rohit Bhatia", "nature_of_assets": "Commercial plot",
    },
)

CHANGED_LISTING = _entry(
    listing_key="changed-1", status="changed",
    changes=[{"field": "reserve_price", "old": 9000000, "new": 8100000}],
    price_drop=True,
    raw={
        "corporate_debtor": "Kingfisher Textiles Ltd",
        "notice_type": "Sale Notice", "reserve_price": 8100000,
        "location": "Ludhiana, Punjab", "auction_date": TODAY + timedelta(days=50),
        "emd_due_date": TODAY + timedelta(days=45),
        "ip_name": "Asha Nair", "nature_of_assets": "Factory building + land",
    },
)

COLLISION_LISTING = _entry(
    listing_key="collision-1", status="collision",
    flags=["Part 6 enrichment SKIPPED this run: listing_key collides with an existing, different listing."],
    raw={
        "corporate_debtor": "Ambient Plastics Ltd",
        "notice_type": "Sale Notice", "reserve_price": 0,
        "location": "Pune, Maharashtra", "auction_date": None, "emd_due_date": None,
        "ip_name": "S. Kulkarni", "nature_of_assets": "Plant and machinery",
    },
    enrichment=None,
)

NOTHING_AVAILABLE_LISTING = _entry(
    listing_key="empty-1", status="unchanged",
    raw={
        "corporate_debtor": None, "notice_type": None, "reserve_price": None,
        "location": None, "auction_date": None, "emd_due_date": None,
        "ip_name": None, "nature_of_assets": None,
    },
    score={"5a": {"partial_score_5a": None}, "5b": {"partial_score_5b": 50}, "5c": {"partial_score_5c": 50}},
    enrichment=None,
)

ASSEMBLED = [
    TOP_LISTING, CLOSING_SOON_LISTING, NEW_TODAY_LISTING,
    CHANGED_LISTING, COLLISION_LISTING, NOTHING_AVAILABLE_LISTING,
]

print("--- Step 1: categorize_assembled() ---")
cat = categorize_assembled(ASSEMBLED, report_date=TODAY)
print("counts:", cat["counts"])

assert cat["counts"]["total"] == 6
assert [e["listing_key"] for e in cat["closing_soon"]] == ["closing-1"], cat["closing_soon"]
assert [e["listing_key"] for e in cat["new_today"]] == ["new-1"]
assert [e["listing_key"] for e in cat["watchlist_changes"]] == ["changed-1"]
assert [e["listing_key"] for e in cat["collisions"]] == ["collision-1"]
# top_scored: all 6 have at least one non-None partial (empty-1's 5b/5c are 50),
# so all 6 should be scored and present (REPORT_TOP_N=15 default is > 6).
assert cat["counts"]["top_scored"] == 6
top_keys = [e["listing_key"] for e in cat["top_scored"]]
assert top_keys[0] == "top-1", f"expected top-1 to rank first, got {top_keys}"
print("OK: every listing landed in the expected section(s).")

print("\n--- Step 2: combined_score() sanity ---")
score, flags = combined_score(TOP_LISTING)
assert score == round((92 + 80 + 70) / 3, 1), score
score2, flags2 = combined_score(NOTHING_AVAILABLE_LISTING)
assert score2 == round((50 + 50) / 2, 1), score2
assert any("5A" in f for f in flags2), flags2
print(f"OK: top-1 combined={score}, empty-1 combined={score2} (5A flagged unavailable: {flags2})")

print("\n--- Step 3: generate_report() -> real PDF file ---")
with tempfile.TemporaryDirectory() as tmp:
    out_path = f"{tmp}/report.pdf"
    written = generate_report(
        ASSEMBLED, output_path=out_path, report_date=TODAY,
        run_summary={
            "scrape_problems": [{"page": 12, "reason": "synthetic test problem"}],
            "store_summary": {"new": 1, "unchanged": 3, "changed": 1, "collision": 1},
            "enrichment_summary": {"reenriched": 1, "reused": 4, "skipped_collision": 1},
        },
    )
    assert written == out_path

    print("\n--- Step 4: read the real PDF back with pypdf ---")
    reader = PdfReader(out_path)
    assert len(reader.pages) >= 1, "PDF has no pages"
    text = "\n".join(page.extract_text() or "" for page in reader.pages)

    expected_substrings = [
        "Auction Intelligence",
        "Top-scored",
        "Closing soon",
        "New today",
        "Watchlist changes",
        "Flagged for review",
        "Scrape problems this run",
        "Sunrise Steel Industries",
        "Northgate Warehousing Pvt Ltd",
        "Harborview Realty Ltd",
        "Kingfisher Textiles Ltd",
        "Ambient Plastics Ltd",
        "Rs. 1,20,00,000",   # Indian comma grouping, Sunrise Steel's reserve price
        "9000000",   # old reserve_price in the watchlist diff
        "8100000",   # new reserve_price in the watchlist diff
        "no reserve fixed",   # Ambient Plastics' reserve_price=0 handling
        "collides with an existing",   # collision flag text
    ]
    missing = [s for s in expected_substrings if s not in text]
    assert not missing, f"expected substrings missing from rendered PDF text: {missing}"
    print(f"OK: all {len(expected_substrings)} expected substrings found in the rendered PDF "
          f"({len(reader.pages)} page(s), {len(text)} chars extracted).")

    # The "nothing available" listing must not have crashed the render --
    # confirm its section (top_scored, since it's the only section it's in)
    # rendered a card at all rather than being silently skipped.
    assert "not disclosed" in text  # its reserve_price=None
    assert "not yet known" in text  # its location=None
    print("OK: the fully-empty listing rendered gracefully (no crash, honest placeholders).")

print("\nAll test_part7b.py assertions passed -- Part 7B (PDF layout + "
      "report categorization) confirmed on a real render + real pypdf "
      "read-back, no network required.")
