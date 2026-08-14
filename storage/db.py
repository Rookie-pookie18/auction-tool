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
    -- Added 2026-08-14, owner request (Part 9): derived from `location`
    -- above by scraper.ibbi._derive_state_from_location() at parse time,
    -- not independently scraped -- see that function's docstring. None
    -- when the location text has no recognized state/UT name; the reason
    -- lands in `flags` (below), same never-silent pattern as
    -- possession_status/land_classification.
    state            TEXT,
    auction_platform TEXT,
    auction_platform_url TEXT,
    plot_area_mentions TEXT,   -- JSON list, stored as text
    flags            TEXT,     -- JSON list, stored as text
    details_pdf_parsed INTEGER DEFAULT 0,

    -- Added 2026-08-13, alongside the pipeline.py PDF-fetch-gating fix
    -- (see that file's module docstring): Part 5B's possession_status/
    -- land_classification were previously never persisted anywhere --
    -- only ever held in memory for the run that parsed them, then
    -- discarded. That was fine when every listing's notice PDF was
    -- re-fetched every single day regardless, but it's a blocker for
    -- skipping that re-fetch on unchanged listings, since scoring (Part
    -- 5) needs these two fields for EVERY currently-active listing, not
    -- just ones fetched this run. notice_pdf_parsed is stored for the
    -- same reason details_pdf_parsed already was: so a later run can
    -- tell "never successfully parsed, worth retrying" apart from
    -- "parsed, nothing there" without re-fetching to find out.
    possession_status   TEXT,
    land_classification TEXT,
    notice_pdf_parsed   INTEGER DEFAULT 0,

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

-- ---------------------------------------------------------------------
-- Part 7A: enrichment persistence (Part 7 architecture decisions,
-- 2026-08-10 decision log entry, refined 2026-08-11 same-session chat
-- review -- see that entry and the "2026-08-11 enrichment-trigger
-- refinement" note below _record_to_dict() for the full reasoning).
-- Purely additive: no columns added to listings/listing_history/
-- collisions above. Holds each ai_analysis/ module's latest result per
-- listing_key, reused for `unchanged` listings instead of re-spending
-- Gemini/MCA/DuckDuckGo quota -- see needs_reenrichment() for exactly
-- when a listing is considered stale enough to re-run.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS enrichment (
    listing_key                  TEXT PRIMARY KEY,

    gemini_narrative_json        TEXT,   -- JSON: {"narrative": {...}, "flags": [...]}
    gemini_generated_at          TEXT,

    mca_data_json                TEXT,   -- JSON: {"mca_data": {...}|null, "flags": [...]}
    mca_lookup_attempted         INTEGER DEFAULT 0,
    mca_looked_up_at             TEXT,

    news_data_json                TEXT,  -- JSON: news_data (list|null)
    news_flags_json                TEXT, -- JSON: flags list from search_news_for_debtor()
    news_searched_at              TEXT,

    -- Snapshots of scraper.ibbi.IBBIRecord's details_pdf_parsed /
    -- notice_pdf_parsed AT THE MOMENT this row was last (re)computed.
    -- Neither field is a TRACKED_FIELD (see IDENTITY_FIELDS/TRACKED_FIELDS
    -- above), so store_records() alone can't detect "this listing's PDF
    -- parse just succeeded for the first time" -- these two columns let
    -- needs_reenrichment() detect that directly, without adding
    -- possession_status/land_classification/notice_pdf_parsed as columns
    -- on the listings table itself (which would break this table's own
    -- "purely additive" design goal).
    details_pdf_parsed_at_enrich INTEGER DEFAULT 0,
    notice_pdf_parsed_at_enrich  INTEGER DEFAULT 0,

    FOREIGN KEY (listing_key) REFERENCES listings(listing_key)
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
    _migrate_listings_columns(conn)
    return conn


# Columns added to `listings` after the table already existed in the
# owner's committed data/auctions.db. CREATE TABLE IF NOT EXISTS (in
# SCHEMA above) only helps a brand-new DB -- an already-existing table
# keeps whatever columns it had when it was first created, so anything
# added later needs an explicit ALTER TABLE here too, or every run
# against the real committed DB would crash with "no such column" the
# moment upsert_listing()/classify_pending() below try to read/write one
# of these. Safe to run every time get_connection() is called: each
# ALTER TABLE is skipped once the column already exists.
_LISTINGS_COLUMN_MIGRATIONS = {
    "possession_status": "TEXT",
    "land_classification": "TEXT",
    "notice_pdf_parsed": "INTEGER DEFAULT 0",
    "state": "TEXT",
}


def _migrate_listings_columns(conn: sqlite3.Connection) -> None:
    existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(listings)")}
    for col, coltype in _LISTINGS_COLUMN_MIGRATIONS.items():
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE listings ADD COLUMN {col} {coltype}")
    conn.commit()


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
                emd_amount, location, state, auction_platform, auction_platform_url,
                plot_area_mentions, flags, details_pdf_parsed,
                possession_status, land_classification, notice_pdf_parsed,
                first_seen_at, last_seen_at, raw_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                rec.get("state"),
                rec.get("auction_platform"),
                rec.get("auction_platform_url"),
                json.dumps(rec.get("plot_area_mentions") or []),
                json.dumps(rec.get("flags") or []),
                int(bool(rec.get("details_pdf_parsed"))),
                rec.get("possession_status"),
                rec.get("land_classification"),
                int(bool(rec.get("notice_pdf_parsed"))),
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
        # Still write the PDF-derived fields here, not just last_seen_at:
        # as of the 2026-08-13 pipeline.py fix, an "unchanged" listing
        # whose PDFs weren't successfully parsed on an earlier run gets
        # RE-fetched (see pipeline.py's need_details_idx/need_notice_idx),
        # even though its tracked fields never changed. If this branch
        # only touched last_seen_at, that retry's result would be
        # computed and then silently thrown away every single run,
        # forever. For a listing whose PDFs were reused from the DB
        # rather than re-fetched this run, these values are already
        # identical to what's stored, so this is a harmless no-op write.
        conn.execute(
            """
            UPDATE listings SET
                notice_pdf_url = ?, details_pdf_url = ?, cin = ?,
                emd_amount = ?, location = ?, state = ?, auction_platform = ?,
                auction_platform_url = ?, plot_area_mentions = ?, flags = ?,
                details_pdf_parsed = ?, possession_status = ?,
                land_classification = ?, notice_pdf_parsed = ?,
                last_seen_at = ?
            WHERE listing_key = ?
            """,
            (
                rec.get("notice_pdf_url"), rec.get("details_pdf_url"),
                rec.get("cin"), rec.get("emd_amount"), rec.get("location"),
                rec.get("state"), rec.get("auction_platform"), rec.get("auction_platform_url"),
                json.dumps(rec.get("plot_area_mentions") or []),
                json.dumps(rec.get("flags") or []),
                int(bool(rec.get("details_pdf_parsed"))),
                rec.get("possession_status"), rec.get("land_classification"),
                int(bool(rec.get("notice_pdf_parsed"))),
                now, key,
            ),
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
            cin = ?, emd_amount = ?, location = ?, state = ?, auction_platform = ?,
            auction_platform_url = ?, plot_area_mentions = ?, flags = ?,
            details_pdf_parsed = ?, possession_status = ?,
            land_classification = ?, notice_pdf_parsed = ?,
            last_seen_at = ?, raw_json = ?
        WHERE listing_key = ?
        """,
        (
            rec.get("reserve_price"), rec.get("auction_date"),
            rec.get("notice_date"), rec.get("emd_due_date"),
            rec.get("notice_pdf_url"), rec.get("details_pdf_url"),
            rec.get("cin"), rec.get("emd_amount"), rec.get("location"),
            rec.get("state"), rec.get("auction_platform"), rec.get("auction_platform_url"),
            json.dumps(rec.get("plot_area_mentions") or []),
            json.dumps(rec.get("flags") or []),
            int(bool(rec.get("details_pdf_parsed"))),
            rec.get("possession_status"), rec.get("land_classification"),
            int(bool(rec.get("notice_pdf_parsed"))),
            now, json.dumps(rec, default=str), key,
        ),
    )
    conn.commit()
    return {"status": "changed", "listing_key": key, "changes": changes, "price_drop": price_drop}


def get_listing(conn: sqlite3.Connection, listing_key: str) -> Optional[dict]:
    """Fetch the current stored row for one listing_key, or None if it has
    never been seen. Read-only. Added 2026-08-13 alongside classify_pending
    below, for the same reason: pipeline.py needs to look at what's
    already stored BEFORE deciding whether Part 3C/5B PDF enrichment is
    worth fetching this run."""
    cur = conn.execute("SELECT * FROM listings WHERE listing_key = ?", (listing_key,))
    row = cur.fetchone()
    return dict(row) if row is not None else None


def classify_pending(conn: sqlite3.Connection, record) -> dict:
    """
    Read-only preview of what upsert_listing() would decide for this
    record -- same identity/collision/tracked-field diff rules, but
    nothing is written or committed.

    WHY THIS EXISTS (2026-08-13, alongside the pipeline.py PDF-fetch-
    gating fix -- see that file's module docstring for the full story):
    Part 3C (enrich_all_with_details) and Part 5B (enrich_all_with_notice)
    used to run unconditionally on every single scraped record, every
    single day, regardless of whether that listing had changed since
    yesterday. Against the real site's ~484 pages / ~9,700 listings, at
    ~3s/PDF/listing that is 16+ hours of pure network-fetch delay alone --
    confirmed the hard way: a real run hit GitHub Actions' 4-hour job cap
    without finishing. The fix is to only fetch a listing's PDFs when the
    listing is new, changed, or was never successfully parsed before --
    but the pipeline needs to know WHICH of those applies BEFORE running
    the (slow, network) enrichment, while the real write (store_records())
    can only safely happen AFTER enrichment, once cin/location/
    possession_status/etc. are final for this run. Hence a read-only
    preview pass first.

    Deliberately kept close to upsert_listing()'s own diff logic just
    below -- if you change one, check the other; a real write later in
    the same run always wins if the two ever disagree (classify_pending
    itself changes nothing).

    Returns:
      {"status": "new" | "unchanged" | "changed" | "collision",
       "listing_key": str,
       "existing": dict | None}   -- current stored row, or None if new
    """
    rec = _record_to_dict(record)
    key = build_listing_key(rec)

    cur = conn.execute("SELECT * FROM listings WHERE listing_key = ?", (key,))
    row = cur.fetchone()
    if row is None:
        return {"status": "new", "listing_key": key, "existing": None}

    existing = dict(row)

    for f in IDENTITY_FIELDS:
        if _norm(existing[f]) != _norm(rec.get(f)):
            return {"status": "collision", "listing_key": key, "existing": existing}

    for f in TRACKED_FIELDS:
        if _norm(existing[f]) != _norm(rec.get(f)):
            return {"status": "changed", "listing_key": key, "existing": existing}

    return {"status": "unchanged", "listing_key": key, "existing": existing}


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


# ---------------------------------------------------------------------------
# Part 7A: enrichment persistence
#
# 2026-08-11 ENRICHMENT-TRIGGER REFINEMENT (chat-session design review,
# same day as the 2026-08-10 "Part 7 architecture decisions" entry these
# functions implement): the original decision gated re-enrichment purely
# on store_records()'s status ("new"/"changed"/no row yet). But
# TRACKED_FIELDS above is only [reserve_price, auction_date, notice_date,
# emd_due_date] -- it does NOT cover cin/location/possession_status/
# land_classification/plot_area_mentions, all of which
# ai_analysis/gemini_narrative.py's _build_prompt() (and mca_lookup.py /
# news_search.py) actually depend on. Those fields are populated by
# scraper.ibbi.enrich_record_with_details() / enrich_record_with_notice()
# and gated by IBBIRecord.details_pdf_parsed / notice_pdf_parsed -- and
# Part 5B's own real-run numbers (0/20 possession_status, 8/20
# land_classification, several unparseable notice PDFs that day) confirm
# these genuinely do resolve from missing to known on a LATER day for a
# listing whose reserve_price/dates never change in between. Under the
# status-only rule, that listing would be reported "unchanged" forever
# after its first enrichment and would keep reusing enrichment generated
# back when cin/location/possession_status were still null -- silently,
# with no record that it happened. Fixed by also tracking a snapshot of
# both parse-completion flags on the enrichment row itself (see SCHEMA
# above) and treating a False->True flip in either as a trigger, on top
# of (not instead of) the original new/changed/no-row-yet rule.
# ---------------------------------------------------------------------------

def get_enrichment(conn: sqlite3.Connection, listing_key: str) -> Optional[dict]:
    """Fetch the current enrichment row for one listing_key, or None if this
    listing has never been enriched. Returns a plain dict (sqlite3.Row ->
    dict), JSON columns left as raw text -- callers that need the parsed
    narrative/mca_data/news_data should json.loads() the relevant field
    themselves rather than this function guessing what shape they want."""
    cur = conn.execute("SELECT * FROM enrichment WHERE listing_key = ?", (listing_key,))
    row = cur.fetchone()
    return dict(row) if row is not None else None


def needs_reenrichment(
    conn: sqlite3.Connection,
    listing_key: str,
    status: str,
    details_pdf_parsed: bool,
    notice_pdf_parsed: bool,
) -> bool:
    """
    Decides whether a listing should go through Part 6's three enrichment
    modules again this run, or reuse its existing `enrichment` row.

    `status` is whatever store_records()/upsert_listing() returned for
    this listing this run ("new"/"unchanged"/"changed"/"collision").
    `details_pdf_parsed`/`notice_pdf_parsed` are THIS run's freshly
    scraped IBBIRecord's own flags (not read back from the DB -- Part 7A's
    orchestrator scrapes the full batch fresh every run per the Part 7
    architecture decision, so these are already in memory).

    Returns True (re-enrich) when ANY of:
      - status is "new" or "changed" (original 2026-08-10 rule)
      - no enrichment row exists yet for this listing_key (first-ever
        enrichment, regardless of status)
      - the stored row's details_pdf_parsed_at_enrich was False and this
        run's details_pdf_parsed is True (2026-08-11 refinement)
      - the stored row's notice_pdf_parsed_at_enrich was False and this
        run's notice_pdf_parsed is True (2026-08-11 refinement)

    A "collision" status is treated the same as "new"/"changed" here
    (re-enrich) -- the collisions table flags it for manual review
    separately; there's no reason to also serve stale enrichment for it.
    """
    if status in ("new", "changed", "collision"):
        return True

    existing = get_enrichment(conn, listing_key)
    if existing is None:
        return True

    if details_pdf_parsed and not existing["details_pdf_parsed_at_enrich"]:
        return True
    if notice_pdf_parsed and not existing["notice_pdf_parsed_at_enrich"]:
        return True

    return False


def upsert_enrichment(
    conn: sqlite3.Connection,
    listing_key: str,
    gemini_result: Optional[dict] = None,
    mca_result: Optional[dict] = None,
    news_result: Optional[dict] = None,
    details_pdf_parsed: bool = False,
    notice_pdf_parsed: bool = False,
) -> dict:
    """
    Write (insert or replace) this listing's enrichment row after a fresh
    enrichment pass. Each of gemini_result/mca_result/news_result is the
    dict shape its own module returns (generate_narrative()'s
    {"narrative":..., "flags":...}, lookup_company_by_cin()'s
    {"mca_data":..., "flags":...}, search_news_for_debtor()'s
    {"news_data":..., "flags":...}) -- pass None for any module that
    wasn't run this pass (e.g. NEWS_SEARCH_ENABLED=False) to leave that
    module's columns untouched rather than clobbering a prior real result
    with a null. `details_pdf_parsed`/`notice_pdf_parsed` should be THIS
    run's IBBIRecord flags -- they become the new snapshot
    needs_reenrichment() compares against next time.

    Never raises. Returns the row that was written (see get_enrichment()).
    """
    now = datetime.now(timezone.utc).isoformat()
    existing = get_enrichment(conn, listing_key)

    # Preserve a module's prior stored result if this pass didn't run it,
    # rather than overwriting a real value with NULL.
    gemini_json = (
        json.dumps(gemini_result, default=str) if gemini_result is not None
        else (existing["gemini_narrative_json"] if existing else None)
    )
    gemini_at = now if gemini_result is not None else (existing["gemini_generated_at"] if existing else None)

    mca_json = (
        json.dumps(mca_result, default=str) if mca_result is not None
        else (existing["mca_data_json"] if existing else None)
    )
    mca_attempted = int(mca_result is not None or bool(existing and existing["mca_lookup_attempted"]))
    mca_at = now if mca_result is not None else (existing["mca_looked_up_at"] if existing else None)

    news_data_json = (
        json.dumps((news_result or {}).get("news_data"), default=str) if news_result is not None
        else (existing["news_data_json"] if existing else None)
    )
    news_flags_json = (
        json.dumps((news_result or {}).get("flags"), default=str) if news_result is not None
        else (existing["news_flags_json"] if existing else None)
    )
    news_at = now if news_result is not None else (existing["news_searched_at"] if existing else None)

    conn.execute(
        """
        INSERT INTO enrichment (
            listing_key, gemini_narrative_json, gemini_generated_at,
            mca_data_json, mca_lookup_attempted, mca_looked_up_at,
            news_data_json, news_flags_json, news_searched_at,
            details_pdf_parsed_at_enrich, notice_pdf_parsed_at_enrich
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(listing_key) DO UPDATE SET
            gemini_narrative_json = excluded.gemini_narrative_json,
            gemini_generated_at = excluded.gemini_generated_at,
            mca_data_json = excluded.mca_data_json,
            mca_lookup_attempted = excluded.mca_lookup_attempted,
            mca_looked_up_at = excluded.mca_looked_up_at,
            news_data_json = excluded.news_data_json,
            news_flags_json = excluded.news_flags_json,
            news_searched_at = excluded.news_searched_at,
            details_pdf_parsed_at_enrich = excluded.details_pdf_parsed_at_enrich,
            notice_pdf_parsed_at_enrich = excluded.notice_pdf_parsed_at_enrich
        """,
        (
            listing_key, gemini_json, gemini_at,
            mca_json, mca_attempted, mca_at,
            news_data_json, news_flags_json, news_at,
            int(bool(details_pdf_parsed)), int(bool(notice_pdf_parsed)),
        ),
    )
    conn.commit()
    return get_enrichment(conn, listing_key)


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

        print("\nAll Part 4 offline smoke-test assertions passed. Collision "
              "path is logic-only here (needs two records whose "
              "IDENTITY_FIELDS hash the same but aren't textually equal to "
              "trigger for real — not exercised in this synthetic test "
              "since SHA-256 collisions aren't something we can force in a "
              "demo).")

        # -------------------------------------------------------------
        # Part 7A offline smoke test: enrichment persistence +
        # needs_reenrichment(), including the 2026-08-11 refinement.
        # Synthetic only, no network/Gemini/MCA/DuckDuckGo calls -- same
        # "offline smoke test only, still needs a real run to be marked
        # confirmed" caveat as every other __main__ block in this project.
        # -------------------------------------------------------------
        print("\n--- Part 7A: enrichment persistence ---\n")

        key = res1["listing_key"]  # r1 from the Part 4 test above, still "new"

        # A brand-new listing has no enrichment row yet -> always re-enrich,
        # regardless of status.
        assert needs_reenrichment(conn, key, status="new",
                                   details_pdf_parsed=False, notice_pdf_parsed=False) is True
        print("1. New listing, no enrichment row yet -> needs_reenrichment=True (correct).")

        # Simulate a first enrichment pass. At this point cin/location/
        # possession_status weren't resolved yet (details/notice PDF not
        # parsed on day 1) -- same shape a real first pass would have.
        upsert_enrichment(
            conn, key,
            gemini_result={"narrative": {"summary": "s", "price_read": "p",
                                          "risk_notes": [], "data_gaps": []}, "flags": []},
            mca_result={"mca_data": None, "flags": ["MCA lookup skipped: no CIN available for this listing"]},
            news_result={"news_data": None, "flags": ["no results"]},
            details_pdf_parsed=False,
            notice_pdf_parsed=False,
        )

        # Day 2: reserve_price/dates unchanged (status="unchanged"), and the
        # PDF parses still haven't succeeded either -> reuse, no re-enrich.
        assert needs_reenrichment(conn, key, status="unchanged",
                                   details_pdf_parsed=False, notice_pdf_parsed=False) is False
        print("2. Unchanged listing, parse flags still False -> needs_reenrichment=False (reuse) (correct).")

        # Day 3: THE GAP THIS REFINEMENT FIXES. reserve_price/dates still
        # unchanged (status="unchanged" from store_records()'s point of
        # view -- TRACKED_FIELDS never saw a diff), but the details PDF
        # parse succeeded for the first time this run (cin/location/
        # emd_amount now real instead of null). Without the 2026-08-11
        # refinement this would silently keep reusing day-1's enrichment,
        # which was generated with cin=None. With it, this must re-enrich.
        assert needs_reenrichment(conn, key, status="unchanged",
                                   details_pdf_parsed=True, notice_pdf_parsed=False) is True
        print("3. Unchanged listing, details_pdf_parsed flips False->True -> "
              "needs_reenrichment=True (the gap this refinement fixes).")

        # Re-enrich for real (simulating what the orchestrator would do
        # after case 3 above fires) and record the new parse-flag snapshot.
        upsert_enrichment(
            conn, key,
            mca_result={"mca_data": {"company_name": "ABC TEXTILES PVT LTD"}, "flags": []},
            details_pdf_parsed=True,
            notice_pdf_parsed=False,
        )
        row = get_enrichment(conn, key)
        assert row["details_pdf_parsed_at_enrich"] == 1
        assert json.loads(row["mca_data_json"])["mca_data"]["company_name"] == "ABC TEXTILES PVT LTD"
        # gemini_narrative_json from day 1 must survive untouched -- this
        # pass only re-ran MCA (gemini_result=None), so upsert_enrichment()
        # must preserve the prior narrative rather than nulling it out.
        assert row["gemini_narrative_json"] is not None
        print("4. Re-enrichment preserves modules not re-run this pass "
              "(gemini_narrative_json untouched when only mca_result is "
              "passed) -- confirmed.")

        # Day 4: now that details_pdf_parsed_at_enrich=True is on record,
        # a further day with unchanged status and unchanged parse flags
        # goes back to reusing -- the trigger doesn't fire forever, only
        # on the actual flip.
        assert needs_reenrichment(conn, key, status="unchanged",
                                   details_pdf_parsed=True, notice_pdf_parsed=False) is False
        print("5. Unchanged listing, parse flags now both match the stored "
              "snapshot -> needs_reenrichment=False again (correct).")

        # A "changed" status (e.g. a real reserve_price drop) always
        # re-enriches too, independent of parse flags -- unchanged from
        # the original 2026-08-10 decision.
        assert needs_reenrichment(conn, key, status="changed",
                                   details_pdf_parsed=True, notice_pdf_parsed=False) is True
        print("6. Changed listing (e.g. price drop) -> needs_reenrichment=True (correct).")

        conn.close()
        print("\nAll Part 7A offline smoke-test assertions passed (synthetic "
              "data only, no real Gemini/MCA/DuckDuckGo calls made -- still "
              "needs a real small-batch run through an actual orchestrator, "
              "which does not exist yet, before Part 7A itself can be marked "
              "confirmed; this only confirms the enrichment table + "
              "needs_reenrichment()/upsert_enrichment() logic in isolation).")
