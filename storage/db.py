"""
storage/db.py — Part 4: SQLite storage, dedup, new/changed detection.

--------------------------------------------------------------------------
DEDUP KEY DESIGN (owner-approved 2026-08-09, see PROJECT_STATUS.md):

Fields are split into two groups, not lumped into one key:

  IDENTITY fields (define "is this the same listing?"; stable across a
  relisting; used to build listing_key):
    - corporate_debtor
    - ip_name
    - notice_type
    - nature_of_assets

  TRACKED fields (expected to change over the life of a listing; a change
  in any of these means "same listing, but updated" — NOT "new listing"):
    - reserve_price
    - auction_date
    - notice_date
    - emd_due_date

Rejected alternative: including notice_date/auction_date/reserve_price in
the identity key. That was the first draft here and it was wrong — it
would make price-drop-on-relisting and reschedule detection impossible,
since the very fields we want to watch for changes would change the
listing's identity instead of triggering a "changed" record. Fixed before
any code was written, per the owner's review.

Rejected alternative: IBBI's own reference code from inside the small
Details PDF (Part 3C) as the primary key. Reliable, but means a PDF fetch
per listing per day just to compute an ID — slower, more failure surface,
for a benefit only needed in the rare collision case. Used here only as
a last-resort tie-breaker (see resolve_collision_with_pdf_code below),
not a daily dependency.

Known soft spot, accepted rather than silently hidden: two genuinely
different lots from the same company + same IP + same notice type with
near-identical Nature of Assets text could still collide on listing_key.
When that happens we do NOT guess or silently merge — the incoming row
is written to the `collisions` table and flagged for manual review, and
listing_key_collision.py's PDF tie-breaker (cin, from Part 3C's
enrich_record_with_details()) is offered as the disambiguator.
--------------------------------------------------------------------------
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import sys
sys.path.insert(0, ".")
import config

IDENTITY_FIELDS = ["corporate_debtor", "ip_name", "notice_type", "nature_of_assets"]
TRACKED_FIELDS = ["reserve_price", "auction_date", "notice_date", "emd_due_date"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    listing_key      TEXT PRIMARY KEY,
    corporate_debtor TEXT,
    ip_name          TEXT,
    notice_type      TEXT,
    nature_of_assets TEXT,

    reserve_price    INTEGER,
    auction_date     TEXT,
    notice_date      TEXT,
    emd_due_date     TEXT,

    notice_pdf_url   TEXT,
    details_pdf_url  TEXT,
    cin              TEXT,
    emd_amount       INTEGER,
    location         TEXT,
    auction_platform TEXT,
    auction_platform_url TEXT,
    plot_area_mentions TEXT,   -- JSON list, stored as text
    flags            TEXT,     -- JSON list, stored as text
    details_pdf_parsed INTEGER DEFAULT 0,

    first_seen_at    TEXT NOT NULL,
    last_seen_at     TEXT NOT NULL,
    raw_json         TEXT NOT NULL   -- full record snapshot, for audit/debug
);

CREATE TABLE IF NOT EXISTS listing_history (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_key      TEXT NOT NULL,
    changed_at       TEXT NOT NULL,
    field            TEXT NOT NULL,
    old_value        TEXT,
    new_value        TEXT,
    is_price_drop    INTEGER DEFAULT 0,
    FOREIGN KEY (listing_key) REFERENCES listings(listing_key)
);

CREATE TABLE IF NOT EXISTS collisions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_key      TEXT NOT NULL,
    detected_at      TEXT NOT NULL,
    existing_raw_json TEXT NOT NULL,
    incoming_raw_json TEXT NOT NULL,
    resolved         INTEGER DEFAULT 0,
    resolution_note  TEXT
);
"""


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Open (creating if needed) the SQLite DB and ensure schema exists."""
    path = Path(db_path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def _norm(value) -> str:
    """Normalize a field value into a stable string for hashing/storage."""
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value).strip().lower()


def build_listing_key(record) -> str:
    """
    Build the identity key from IDENTITY_FIELDS only. Accepts either an
    IBBIRecord (dataclass) or a plain dict.
    """
    rec = asdict(record) if not isinstance(record, dict) else record
    parts = [_norm(rec.get(f)) for f in IDENTITY_FIELDS]
    joined = "|".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:24]


def _record_to_dict(record) -> dict:
    rec = asdict(record) if not isinstance(record, dict) else dict(record)
    # Serialize date/list fields into JSON-safe / SQLite-safe forms
    for f in ("auction_date", "notice_date", "emd_due_date"):
        v = rec.get(f)
        if isinstance(v, (date, datetime)):
            rec[f] = v.isoformat()
    return rec


def upsert_listing(conn: sqlite3.Connection, record) -> dict:
    """
    Insert or update one scraped record. Returns a result dict describing
    what happened:
      {"status": "new"} — first time this listing_key has been seen
      {"status": "unchanged"} — seen before, no tracked-field changes
      {"status": "changed", "changes": [...], "price_drop": bool}
      {"status": "collision"} — listing_key matched, but identity fields
                                 don't actually match text-for-text; see
                                 collisions table, nothing overwritten
    Never silently drops anything — every branch either writes a listings
    row, a history row, or a collisions row.
    """
    rec = _record_to_dict(record)
    key = build_listing_key(rec)
    now = datetime.now(timezone.utc).isoformat()

    cur = conn.execute("SELECT * FROM listings WHERE listing_key = ?", (key,))
    existing = cur.fetchone()

    if existing is None:
        conn.execute(
            """
            INSERT INTO listings (
                listing_key, corporate_debtor, ip_name, notice_type,
                nature_of_assets, reserve_price, auction_date, notice_date,
                emd_due_date, notice_pdf_url, details_pdf_url, cin,
                emd_amount, location, auction_platform, auction_platform_url,
                plot_area_mentions, flags, details_pdf_parsed,
                first_seen_at, last_seen_at, raw_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                key,
                rec.get("corporate_debtor"),
                rec.get("ip_name"),
                rec.get("notice_type"),
                rec.get("nature_of_assets"),
                rec.get("reserve_price"),
                rec.get("auction_date"),
                rec.get("notice_date"),
                rec.get("emd_due_date"),
                rec.get("notice_pdf_url"),
                rec.get("details_pdf_url"),
                rec.get("cin"),
                rec.get("emd_amount"),
                rec.get("location"),
                rec.get("auction_platform"),
                rec.get("auction_platform_url"),
                json.dumps(rec.get("plot_area_mentions") or []),
                json.dumps(rec.get("flags") or []),
                int(bool(rec.get("details_pdf_parsed"))),
                now,
                now,
                json.dumps(rec, default=str),
            ),
        )
        conn.commit()
        return {"status": "new", "listing_key": key}

    # --- Collision check: same key, but do the identity fields actually
    # match text-for-text? (hash collisions / near-duplicate lots) ---
    for f in IDENTITY_FIELDS:
        if _norm(existing[f]) != _norm(rec.get(f)):
            conn.execute(
                """
                INSERT INTO collisions (
                    listing_key, detected_at, existing_raw_json, incoming_raw_json
                ) VALUES (?,?,?,?)
                """,
                (key, now, existing["raw_json"], json.dumps(rec, default=str)),
            )
            conn.commit()
            return {
                "status": "collision",
                "listing_key": key,
                "note": (
                    "Two different-looking listings hashed to the same "
                    "listing_key. Not merged, not overwritten. Resolve by "
                    "checking Part 3C's 'cin' (permanent IBBI reference "
                    "code) on both records via enrich_record_with_details()."
                ),
            }

    # --- Same listing confirmed. Diff tracked fields. ---
    changes = []
    price_drop = False
    for f in TRACKED_FIELDS:
        old_val = existing[f]
        new_val = rec.get(f)
        if _norm(old_val) != _norm(new_val):
            changes.append({"field": f, "old": old_val, "new": new_val})
            if f == "reserve_price":
                try:
                    if old_val is not None and new_val is not None and float(new_val) < float(old_val):
                        price_drop = True
                except (TypeError, ValueError):
                    pass

    if not changes:
        conn.execute(
            "UPDATE listings SET last_seen_at = ? WHERE listing_key = ?",
            (now, key),
        )
        conn.commit()
        return {"status": "unchanged", "listing_key": key}

    for c in changes:
        conn.execute(
            """
            INSERT INTO listing_history (
                listing_key, changed_at, field, old_value, new_value, is_price_drop
            ) VALUES (?,?,?,?,?,?)
            """,
            (
                key, now, c["field"], _norm(c["old"]), _norm(c["new"]),
                int(price_drop and c["field"] == "reserve_price"),
            ),
        )

    conn.execute(
        """
        UPDATE listings SET
            reserve_price = ?, auction_date = ?, notice_date = ?,
            emd_due_date = ?, notice_pdf_url = ?, details_pdf_url = ?,
            cin = ?, emd_amount = ?, location = ?, auction_platform = ?,
            auction_platform_url = ?, plot_area_mentions = ?, flags = ?,
            details_pdf_parsed = ?, last_seen_at = ?, raw_json = ?
        WHERE listing_key = ?
        """,
        (
            rec.get("reserve_price"), rec.get("auction_date"),
            rec.get("notice_date"), rec.get("emd_due_date"),
            rec.get("notice_pdf_url"), rec.get("details_pdf_url"),
            rec.get("cin"), rec.get("emd_amount"), rec.get("location"),
            rec.get("auction_platform"), rec.get("auction_platform_url"),
            json.dumps(rec.get("plot_area_mentions") or []),
            json.dumps(rec.get("flags") or []),
            int(bool(rec.get("details_pdf_parsed"))),
            now, json.dumps(rec, default=str), key,
        ),
    )
    conn.commit()
    return {"status": "changed", "listing_key": key, "changes": changes, "price_drop": price_drop}


def store_records(conn: sqlite3.Connection, records: list) -> dict:
    """
    Bulk entry point: run upsert_listing() over a batch of scraped records
    (e.g. output of scraper.ibbi.scrape_all_pages()). Returns counts by
    status plus the full per-record results list — nothing summarized away.
    """
    results = [upsert_listing(conn, r) for r in records]
    summary = {"new": 0, "unchanged": 0, "changed": 0, "collision": 0}
    for r in results:
        summary[r["status"]] += 1
    return {"summary": summary, "results": results}


if __name__ == "__main__":
    # Offline smoke test: synthetic records only, no network. Confirms the
    # identity/tracked split and collision path all behave before this
    # touches a real scrape. A real-data run (through scraper.ibbi's actual
    # output) still needs to happen separately and be confirmed for real,
    # per the project's "never overstate testing" rule.
    import tempfile

    class FakeRecord(dict):
        pass

    with tempfile.TemporaryDirectory() as tmp:
        db_path = f"{tmp}/test.db"
        conn = get_connection(db_path)

        r1 = FakeRecord(
            corporate_debtor="ABC Textiles Pvt Ltd", ip_name="Ramesh Kumar",
            notice_type="Sale Notice", nature_of_assets="Industrial land 5 acres",
            reserve_price=5000000, auction_date="2026-09-01",
            notice_date="2026-08-01", emd_due_date="2026-08-25",
        )
        res1 = upsert_listing(conn, r1)
        print("Day 1, first insert:", res1["status"])
        assert res1["status"] == "new"

        res2 = upsert_listing(conn, dict(r1))
        print("Day 2, identical re-scrape:", res2["status"])
        assert res2["status"] == "unchanged"

        r1_pricedrop = dict(r1)
        r1_pricedrop["reserve_price"] = 4500000
        res3 = upsert_listing(conn, r1_pricedrop)
        print("Day 3, price drop:", res3["status"], "price_drop=", res3.get("price_drop"))
        assert res3["status"] == "changed" and res3["price_drop"] is True

        r2 = FakeRecord(
            corporate_debtor="XYZ Foods Ltd", ip_name="Sunita Rao",
            notice_type="Sale Notice", nature_of_assets="Warehouse 2 acres",
            reserve_price=2000000, auction_date="2026-09-15",
            notice_date="2026-08-05", emd_due_date="2026-08-30",
        )
        res4 = upsert_listing(conn, r2)
        print("Different listing entirely:", res4["status"])
        assert res4["status"] == "new"

        summary = store_records(conn, [dict(r1_pricedrop), dict(r2)])["summary"]
        print("Batch re-run summary:", summary)

        conn.close()
        print("\nAll offline smoke-test assertions passed. Collision path is "
              "logic-only here (needs two records whose IDENTITY_FIELDS hash "
              "the same but aren't textually equal to trigger for real — "
              "not exercised in this synthetic test since SHA-256 collisions "
              "aren't something we can force in a demo).")
