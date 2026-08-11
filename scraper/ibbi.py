"""
scraper/ibbi.py — IBBI liquidation auction-notice listings
(https://ibbi.gov.in/liquidation-auction-notices/lists)

Part 3A + 3B scope: fetch listing pages (one page, or loop across all of
them) and parse each page's table into structured records.

Part 3C scope: fill in fields not in the table (EMD amount, location,
plot area) by opening a PDF — but NOT the big "Auction Notice" PDF
(`notice_pdf_url`, the newspaper-style legal notice, several hundred KB
to a few MB, free-text/possibly-scanned). Direct fetches on 2026-08-09
(assistant's own browsing tool, see Section 0 rule 2) found that the
small "Details" PDF (`details_pdf_url`, consistently ~176-177KB across
every sample checked) is a completely different, much easier document:
a TCPDF-generated structured form with a fixed set of numbered fields
(1. Name of Corporate Debtor ... 16. Location of Assets to be Auctioned),
built by IBBI itself from the liquidator's form submission. It already
has EMD Amount and Location as their own labelled fields — no
prose-parsing needed for those two. Plot area is still free text (inside
field 15, Nature of Assets) so that part is still best-effort regex,
flagged rather than guessed when nothing matches.

Field numbering has two confirmed quirks, not bugs: field "13." never
appears on any sample (13 is skipped outright), and fields "6(a)."
(prior notice reference) and "12(a)." (auction platform name, when field
12 is "Others") are optional — present only when relevant. Parsing below
handles this by locating whichever field labels are actually present in
the text and slicing between them, rather than assuming a fixed field
count.

--------------------------------------------------------------------------
IMPORTANT — how this was built and what "tested" means here (be honest,
don't overstate):

  - 3A (single-page fetch + parse) was confirmed on a real run against the
    live site by the owner on 2026-08-09: 20/20 rows on page 1 parsed
    with 0 flags, first record matched the assistant's own earlier fetch
    exactly. `fetch_page()` and `parse_listing_table()` are genuinely
    network-tested, not just logic-tested.
  - 3B (`scrape_all_pages()` below, looping `?page=N`) has now been run
    for real by the owner (2026-08-09, 3 pages): row count was right
    (60), but 6 rows were exact duplicates of a row on the adjacent page
    — always adjacent pages, never further apart, and every field matched
    exactly. Conclusion: IBBI's `?page=N` windows overlap slightly at
    page boundaries; this is a site quirk, not a parsing bug. Fixed by
    de-duplicating across pages before returning (keyed on
    `details_pdf_url`, with fallbacks) — dropped duplicates are recorded
    in the returned problem list, not silently discarded. Confirmed on a
    real re-run by the owner (2026-08-09): 54 unique / 60 raw rows,
    6 dupes correctly dropped, 0 remaining duplicates, 0 other problems.
    3B is done.
  - 3C (details-PDF parsing, below) — bug in the first version of this
    file, found and fixed 2026-08-09: `__main__` only ran the offline
    synthetic-fixture check (below), and never actually called
    `enrich_record_with_details()` against a real record from a real
    fetch. The owner ran it (2026-08-09) and it "passed" — but that run
    never touched a real details PDF at all, so nothing about the real
    network path was actually confirmed. Fixed by adding a real-network
    test block that enriches a few records from the real 3A/3B fetch
    before the synthetic check runs. What WAS genuinely tested before the
    fix: the assistant fetched 4 real details-PDF URLs directly (its own
    browsing tool, 2026-08-09) covering every field-layout variant seen
    (plain, "Others"-platform, going-concern, Corrigendum), turned those
    into synthetic PDFs, and ran them through the real
    `extract_pdf_text()`/`parse_details_pdf()` code — a real PDF
    round-trip, just never a real fetch. That caught one real bug (the
    `12(a)` label includes "(Others)" and wasn't being stripped). Owner:
    please re-run `python scraper/ibbi.py` — this time it will actually
    hit ibbi.gov.in for a few details PDFs; paste back that section's
    output (or the traceback).
--------------------------------------------------------------------------
"""

from __future__ import annotations

import io
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

sys.path.insert(0, ".")  # allow running this file directly for the smoke test
import config

IBBI_LISTING_URL = f"{config.IBBI_BASE_URL}{config.IBBI_LISTING_PATH}"

# Header text -> internal field name. Matched by case-insensitive substring
# so small wording tweaks on the site don't silently break the mapping.
# Order here doesn't matter — real column order is read from the page.
HEADER_MAP = {
    "type of an": "notice_type",
    "date of auction": "auction_date",       # must be checked BEFORE plain "date"
    "date": "notice_date",
    "name of corporate debtor": "corporate_debtor",
    "name of insolvency professional": "ip_name",
    "auction notice": "notice_pdf_url",
    "reserve price": "reserve_price_raw",
    "nature of assets": "nature_of_assets",
    "last date of submission of emd": "emd_due_date",
    "details": "details_pdf_url",
}


@dataclass
class IBBIRecord:
    notice_type: Optional[str] = None
    notice_date: Optional[date] = None
    notice_date_raw: Optional[str] = None
    corporate_debtor: Optional[str] = None
    auction_date: Optional[date] = None
    auction_date_raw: Optional[str] = None
    ip_name: Optional[str] = None
    notice_pdf_url: Optional[str] = None
    reserve_price: Optional[int] = None
    reserve_price_raw: Optional[str] = None
    nature_of_assets: Optional[str] = None
    emd_due_date: Optional[date] = None
    emd_due_date_raw: Optional[str] = None
    details_pdf_url: Optional[str] = None
    # Which listing page this row came from. None for single-page
    # parse_listing_table() calls; set by scrape_all_pages() so cross-page
    # duplicates can be traced back to their pages for diagnosis.
    source_page: Optional[int] = None
    # Never silently drop a problem — anything odd about this row goes here
    # instead of being hidden. Empty list = nothing flagged.
    flags: list = field(default_factory=list)

    # --- Part 3C: filled in by enrich_record_with_details(), None until
    # that's been run (details_pdf_parsed distinguishes "not attempted yet"
    # from "attempted and the field was genuinely blank/unparseable"). ---
    cin: Optional[str] = None
    emd_amount: Optional[int] = None
    location: Optional[str] = None
    auction_platform: Optional[str] = None
    auction_platform_url: Optional[str] = None
    # Best-effort regex matches of size figures found in the PDF's Nature
    # of Assets text, e.g. ["7,450 sq. ft", "14,200 sq. ft"] — raw strings,
    # deliberately not picked-one/converted-to-a-single-number: a listing
    # can have several area figures (land vs building) and guessing which
    # one is "the" plot size would be silent misinformation, not a fix.
    plot_area_mentions: list = field(default_factory=list)
    details_pdf_parsed: bool = False

    # --- Part 5B: filled in by enrich_record_with_notice(), None until
    # that's been run. Unlike details_pdf_parsed, notice_pdf_parsed being
    # True does NOT guarantee possession_status/land_classification are
    # non-None -- both are best-effort keyword matches on free text and can
    # legitimately come back "not found", which is recorded as a flag, not
    # a silent guess. ---
    possession_status: Optional[str] = None       # "physical" | "symbolic" | None
    land_classification: Optional[str] = None      # e.g. "agricultural", "industrial"
    notice_pdf_parsed: bool = False

    # --- Part 6B: filled in by enrich_record_with_mca() in
    # ai_analysis/mca_lookup.py, None until that's been run.
    # mca_lookup_attempted distinguishes "not attempted yet" from
    # "attempted -- no CIN / no match / lookup failed" (mca_data stays None
    # in both of the latter cases; the reason goes in `flags` instead, same
    # never-silently-drop pattern as everywhere else in this pipeline). ---
    mca_data: Optional[dict] = None
    mca_lookup_attempted: bool = False

    # --- Part 6C: filled in by enrich_record_with_news() in
    # ai_analysis/news_search.py, None until that's been run.
    # news_search_attempted distinguishes "not attempted yet" from
    # "attempted -- no debtor name / zero results / search failed" (news_data
    # stays None in both of the latter cases; the reason goes in `flags`
    # instead, same never-silently-drop pattern as 6B's mca_data). Each
    # result in news_data (when present) is a raw, unverified web-search
    # hit (title/snippet/url) -- never fact-checked, never trusted blindly,
    # per PROJECT_STATUS.md Section 2. ---
    news_data: Optional[list] = None
    news_search_attempted: bool = False


def fetch_page(page: int = 1) -> str:
    """Fetch one listing page. page=1 has no query param on the real site;
    page>=2 uses ?page=N (confirmed in Part 2's pagination links)."""
    url = IBBI_LISTING_URL if page == 1 else f"{IBBI_LISTING_URL}?page={page}"
    resp = requests.get(
        url,
        headers={"User-Agent": config.USER_AGENT},
        timeout=config.REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.text


def _find_listing_table(soup: BeautifulSoup):
    """Locate the auction-notice table by header text, not by class name
    (class names are unknown — never fetched raw HTML, see module docstring)."""
    for table in soup.find_all("table"):
        header_text = table.get_text(" ", strip=True).lower()
        if "reserve price" in header_text and "corporate debtor" in header_text:
            return table
    return None


def _map_headers(header_cells) -> dict:
    """Return {column_index: internal_field_name} using substring matching.
    Checks longer/more-specific keys before shorter ones (e.g. 'date of
    auction' before 'date') so a generic key doesn't steal a specific
    column's match."""
    ordered_keys = sorted(HEADER_MAP.keys(), key=len, reverse=True)
    col_map = {}
    for idx, cell in enumerate(header_cells):
        text = cell.get_text(" ", strip=True).lower()
        for key in ordered_keys:
            if key in text:
                col_map[idx] = HEADER_MAP[key]
                break
    return col_map


def _parse_date(raw: str) -> Optional[date]:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%d-%m-%Y").date()
    except ValueError:
        return None


def _parse_reserve_price(raw: str) -> Optional[int]:
    """Indian comma-grouped rupee figure, e.g. '1,11,41,39,999' -> int.
    Returns None (not zero) if it isn't a plain number — callers should
    check reserve_price_raw for the original text (seen values include
    literal '0' and non-numeric placeholders like 'NRRA')."""
    raw = (raw or "").strip()
    digits_only = raw.replace(",", "")
    if re.fullmatch(r"\d+", digits_only):
        return int(digits_only)
    return None


def _extract_pdf_url(cell) -> Optional[str]:
    link = cell.find("a", href=True)
    if link and link["href"] and not link["href"].startswith("javascript"):
        href = link["href"]
        if href.startswith("http"):
            return href
        return f"{config.IBBI_BASE_URL}{href}"
    return None


def _clean_nature_of_assets(cell) -> tuple[str, bool]:
    """The site shows a truncated teaser ('Land and Building , ...') right
    next to the full text in the same cell (confirmed in Part 2's fetch —
    see module docstring on how that was confirmed). Collapse the two into
    one string; if we can't confidently tell they're teaser+full of the
    same text, keep both and flag it as uncertain rather than guessing."""
    pieces = [s.strip() for s in cell.stripped_strings if s.strip()]
    if not pieces:
        return "", False
    if len(pieces) == 1:
        return pieces[0], False

    teaser, rest = pieces[0], " ".join(pieces[1:])
    core = teaser[:-3].strip() if teaser.endswith("...") else teaser
    probe_len = min(len(core), 20)
    if probe_len and rest.startswith(core[:probe_len]):
        return rest, False
    # Couldn't confirm the teaser is a prefix of the full text — don't
    # silently pick one, surface both and flag for a human to check.
    return f"{teaser} | {rest}", True


def get_total_records(html: str) -> Optional[int]:
    """Parses the 'Total Records: N' text seen on the listing page.
    Not used for pagination logic here (that's Part 3B) — just exposed
    since it falls out of the same page parse almost for free."""
    match = re.search(r"Total Records:\s*([\d,]+)", html)
    if match:
        return int(match.group(1).replace(",", ""))
    return None


def parse_listing_table(html: str) -> tuple[list[IBBIRecord], list[dict]]:
    """Parse one listing page's table.

    Returns (records, problem_rows).
      - records: one IBBIRecord per table row, always returned even if
        some fields failed to parse (those fields are None + noted in
        .flags) — a row is never dropped just because one field is messy.
      - problem_rows: rows that couldn't be matched to the expected
        columns at all (e.g. unexpected column count), with the raw cell
        text so nothing is silently lost. Should normally be empty.
    """
    soup = BeautifulSoup(html, "lxml")
    table = _find_listing_table(soup)
    if table is None:
        raise ValueError(
            "Could not find the listing table on the page (no <table> "
            "containing both 'reserve price' and 'corporate debtor' in its "
            "text). The page structure may have changed — inspect the raw "
            "HTML before assuming this module is just broken."
        )

    rows = table.find_all("tr")
    if not rows:
        raise ValueError("Listing table found but has no <tr> rows at all.")

    header_cells = rows[0].find_all(["th", "td"])
    col_map = _map_headers(header_cells)
    expected_fields = set(HEADER_MAP.values())
    matched_fields = set(col_map.values())
    missing = expected_fields - matched_fields
    if missing:
        raise ValueError(
            f"Header row didn't match {len(missing)} expected column(s): "
            f"{sorted(missing)}. Header text seen was: "
            f"{[c.get_text(' ', strip=True) for c in header_cells]}"
        )

    records: list[IBBIRecord] = []
    problem_rows: list[dict] = []

    for row in rows[1:]:
        cells = row.find_all("td")
        if not cells:
            continue  # a stray header/spacer row, not real data
        if len(cells) < len(header_cells) - 1:  # allow off-by-one slack
            problem_rows.append({
                "reason": f"expected ~{len(header_cells)} cells, got {len(cells)}",
                "raw_text": row.get_text(" | ", strip=True),
            })
            continue

        rec = IBBIRecord()
        for idx, field_name in col_map.items():
            if idx >= len(cells):
                rec.flags.append(f"missing cell for {field_name}")
                continue
            cell = cells[idx]

            if field_name == "notice_date":
                raw = cell.get_text(strip=True)
                rec.notice_date_raw = raw
                rec.notice_date = _parse_date(raw)
                if raw and rec.notice_date is None:
                    rec.flags.append(f"unparseable notice_date: {raw!r}")
            elif field_name == "auction_date":
                raw = cell.get_text(strip=True)
                rec.auction_date_raw = raw
                rec.auction_date = _parse_date(raw)
                if raw and rec.auction_date is None:
                    rec.flags.append(f"unparseable auction_date: {raw!r}")
            elif field_name == "emd_due_date":
                raw = cell.get_text(strip=True)
                rec.emd_due_date_raw = raw
                rec.emd_due_date = _parse_date(raw)
                if raw and rec.emd_due_date is None:
                    rec.flags.append(f"unparseable emd_due_date: {raw!r}")
            elif field_name == "reserve_price_raw":
                raw = cell.get_text(strip=True)
                rec.reserve_price_raw = raw
                rec.reserve_price = _parse_reserve_price(raw)
                if rec.reserve_price is None:
                    rec.flags.append(f"non-numeric reserve price: {raw!r}")
            elif field_name == "nature_of_assets":
                text, uncertain = _clean_nature_of_assets(cell)
                rec.nature_of_assets = text
                if uncertain:
                    rec.flags.append("nature_of_assets teaser/full-text split uncertain")
            elif field_name in ("notice_pdf_url", "details_pdf_url"):
                url = _extract_pdf_url(cell)
                setattr(rec, field_name, url)
                if url is None:
                    rec.flags.append(f"no PDF link found for {field_name}")
            else:
                setattr(rec, field_name, cell.get_text(strip=True))

        records.append(rec)

    return records, problem_rows


def scrape_all_pages(
    max_pages: Optional[int] = None,
    delay_seconds: Optional[float] = None,
) -> tuple[list[IBBIRecord], list[dict]]:
    """Loop across listing pages, reusing fetch_page/parse_listing_table
    (already network-confirmed for a single page — see module docstring).

    max_pages: stop after this many pages regardless of what the site
        reports. None = use the site's own "Total Records" count (via
        get_total_records on page 1) to compute how many pages exist.
        Pass a small number (e.g. 3) for a first real-network smoke test
        of the loop itself before doing a full ~484-page run.
    delay_seconds: pause between page requests. Defaults to
        config.REQUEST_DELAY_SECONDS (matched to "once a day" use, not a
        hammering pace — see config.py).

    Stops early (without erroring) if a page comes back with 0 rows, on
    the assumption that means we've run past the last real page — this
    is a guess, not confirmed, since 484 pages have never actually been
    walked. Every page's problem_rows are pooled together; per-page fetch
    or parse errors are recorded as a problem row with the page number
    rather than silently stopping the whole run.
    """
    delay = config.REQUEST_DELAY_SECONDS if delay_seconds is None else delay_seconds

    first_page_html = fetch_page(1)
    total_records = get_total_records(first_page_html)

    all_records: list[IBBIRecord] = []
    all_problems: list[dict] = []

    recs, problems = parse_listing_table(first_page_html)
    for r in recs:
        r.source_page = 1
    all_records.extend(recs)
    all_problems.extend(problems)

    if max_pages is not None:
        page_limit = max_pages
    elif total_records is not None and recs:
        # ceiling division: records-per-page inferred from page 1's own count
        per_page = len(recs)
        page_limit = -(-total_records // per_page)
    else:
        page_limit = 1  # couldn't determine page count and no override given

    page = 2
    while page <= page_limit:
        time.sleep(delay)
        try:
            html = fetch_page(page)
        except Exception as exc:  # noqa: BLE001 — surface, don't crash the run
            all_problems.append({"page": page, "reason": f"fetch failed: {exc}"})
            page += 1
            continue

        try:
            recs, problems = parse_listing_table(html)
        except Exception as exc:  # noqa: BLE001
            all_problems.append({"page": page, "reason": f"parse failed: {exc}"})
            page += 1
            continue

        if not recs:
            # Unconfirmed assumption: empty page means past the last real
            # page. Flagged rather than silent in case it's wrong.
            all_problems.append({"page": page, "reason": "0 rows returned, stopped here"})
            break

        for p in problems:
            p["page"] = page
        for r in recs:
            r.source_page = page
        all_records.extend(recs)
        all_problems.extend(problems)
        page += 1

    # Real-run finding (2026-08-09, owner-confirmed): IBBI's ?page=N
    # windows overlap by a few rows at each boundary — adjacent pages
    # (never non-adjacent) sometimes return an identical row. This is a
    # site quirk, not a parsing bug (every field in the duplicate rows
    # matched exactly). Dedupe here, keep the first-seen copy, and record
    # what was dropped rather than silently discarding it.
    seen_keys = set()
    deduped: list[IBBIRecord] = []
    for rec in all_records:
        key = rec.details_pdf_url or rec.notice_pdf_url or (
            rec.corporate_debtor, rec.notice_date_raw, rec.notice_type, rec.reserve_price_raw
        )
        if key in seen_keys:
            all_problems.append({
                "page": rec.source_page,
                "reason": "cross-page boundary duplicate, dropped (kept earlier page's copy)",
                "corporate_debtor": rec.corporate_debtor,
                "notice_date": rec.notice_date_raw,
            })
            continue
        seen_keys.add(key)
        deduped.append(rec)

    return deduped, all_problems


# ---------------------------------------------------------------------------
# Part 3C — details-PDF parsing
#
# `details_pdf_url` points at a small TCPDF-generated form, not the big
# free-text "Auction Notice" (see module docstring for how this was
# confirmed). Its fields are numbered and mostly fixed, but 6(a)/12(a) are
# optional and "13." never appears — so rather than assuming a fixed set
# of fields at fixed positions, DETAILS_FIELD_PATTERNS below is a list of
# (key, label_regex) pairs; parsing finds whichever labels are actually
# present in the extracted text, sorts them by where they occur, and takes
# each field's value as the text between its label and the next label
# found (or the "Unique Number -" footer for the last field, 16).
# ---------------------------------------------------------------------------

DETAILS_FIELD_PATTERNS = [
    ("corporate_debtor_pdf", r"1\.\s*Name of Corporate Debtor"),
    ("cin", r"2\.\s*CIN/LLPIN of Corporate Debtor"),
    ("insolvency_commencement_date_pdf", r"3\.\s*Insolvency Commencement Date"),
    ("process_number_pdf", r"4\.\s*Process Number"),
    ("liquidation_commencement_date_pdf", r"5\.\s*Liquidation Commencement Date"),
    ("form_type", r"6\.\s*Form is being filed for"),
    ("prior_notice_reference", r"6\(a\)\.\s*Auction notices issued"),
    ("notice_date_pdf", r"7\.\s*Date of Issue of Auction Notice in Newspapers"),
    ("emd_due_date_pdf", r"8\.\s*Last Date of Submission of EMD"),
    ("auction_date_pdf", r"9\.\s*Date of Auction"),
    ("reserve_price_pdf_raw", r"10\.\s*Reserve Price"),
    ("emd_amount_raw", r"11\.\s*EMD Amount"),
    # negative lookahead so "12." doesn't also match the start of "12(a)."
    ("auction_platform", r"12\.\s*Auction Platform(?!\s*\()"),
    ("auction_platform_other", r"12\(a\)\.\s*Auction Platform\s*\(Others\)"),
    ("auction_platform_url", r"14\.\s*Web address of Auction Platform"),
    ("nature_of_assets_pdf", r"15\.\s*Nature of Assets to be Auctioned"),
    ("location_raw", r"16\.\s*Location of Assets to be Auctioned"),
]
DETAILS_END_MARKER = r"Unique Number\s*-"

# Best-effort area-figure matcher for free text like "7,450 sq. ft",
# "1,68,003.00 Sq mtrs", "182.15, Sq.Mtrs.", "7.62 acres". Deliberately
# broad rather than exact — misses are flagged (see parse_details_pdf),
# never silently guessed.
AREA_PATTERN = re.compile(
    r"([\d,]+\.?\d*)\s*(sq\.?\s*(?:ft|feet|mtrs?|meters?|metres?|m)\.?|acres?|hectares?|guntas?|cents?)\b",
    re.IGNORECASE,
)

# Fields we'd genuinely expect on every real notice; used only to decide
# whether to flag, never to drop a record.
REQUIRED_DETAILS_FIELDS = {"cin", "reserve_price_pdf_raw", "emd_amount_raw", "nature_of_assets_pdf", "location_raw"}


def fetch_pdf_bytes(url: str) -> bytes:
    resp = requests.get(
        url,
        headers={"User-Agent": config.USER_AGENT},
        timeout=config.REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.content


def extract_pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _parse_amount(raw: Optional[str]) -> Optional[int]:
    """Digits-only parse. Safe here because every raw value this is called
    on (Reserve Price, EMD Amount) has a non-digit label suffix like
    '(In Rupees)' baked into the slice — stripping all non-digits leaves
    just the number, since none of those suffixes contain digits."""
    if not raw:
        return None
    digits_only = re.sub(r"[^\d]", "", raw)
    return int(digits_only) if digits_only else None


def _extract_area_mentions(text: Optional[str]) -> list[str]:
    if not text:
        return []
    return [f"{num.strip()} {unit.strip()}" for num, unit in AREA_PATTERN.findall(text)]


def _parse_details_fields(text: str) -> tuple[dict, list[str]]:
    """Locate whichever DETAILS_FIELD_PATTERNS labels are present in text
    and slice the value following each one, up to the next label found (or
    the footer marker, for the last field). Returns (values, flags) —
    values maps key -> cleaned single-line string; a key is simply absent
    if its label wasn't found (never a guessed/empty placeholder)."""
    flags: list[str] = []
    matches = []
    for key, pattern in DETAILS_FIELD_PATTERNS:
        m = re.search(pattern, text)
        if m:
            matches.append((m.start(), m.end(), key))
    matches.sort(key=lambda t: t[0])

    end_m = re.search(DETAILS_END_MARKER, text)
    boundary_end = end_m.start() if end_m else len(text)
    if end_m is None:
        flags.append(
            "could not find 'Unique Number -' end marker; text extraction "
            "may be incomplete or the form layout has changed"
        )

    values: dict[str, str] = {}
    for i, (_start, label_end, key) in enumerate(matches):
        next_start = matches[i + 1][0] if i + 1 < len(matches) else boundary_end
        values[key] = " ".join(text[label_end:next_start].split())

    found_keys = {k for _, _, k in matches}
    for missing_key in sorted(REQUIRED_DETAILS_FIELDS - found_keys):
        flags.append(f"expected field label not found in details PDF: {missing_key}")

    return values, flags


def parse_details_pdf(text: str) -> tuple[dict, list[str]]:
    """Parse one details-PDF's extracted text. Returns (result, flags).
    result keys: cin, location, auction_platform, auction_platform_url,
    nature_of_assets_pdf, emd_amount (int or None), reserve_price_pdf (int
    or None, for cross-checking against the table's own reserve_price),
    area_mentions (list[str], best-effort, may be empty)."""
    values, flags = _parse_details_fields(text)

    emd_amount = _parse_amount(values.get("emd_amount_raw"))
    if values.get("emd_amount_raw") and emd_amount is None:
        flags.append(f"could not parse EMD amount as a number: {values['emd_amount_raw']!r}")

    reserve_price_pdf = _parse_amount(values.get("reserve_price_pdf_raw"))
    if values.get("reserve_price_pdf_raw") and reserve_price_pdf is None:
        flags.append(f"could not parse PDF reserve price as a number: {values['reserve_price_pdf_raw']!r}")

    area_mentions = _extract_area_mentions(values.get("nature_of_assets_pdf"))
    if not area_mentions:
        flags.append("no area/size figure found in PDF nature-of-assets text (best-effort regex, may still be there in wording it doesn't recognize)")

    result = {
        "cin": values.get("cin") or None,
        "location": values.get("location_raw") or None,
        "auction_platform": values.get("auction_platform_other") or values.get("auction_platform") or None,
        "auction_platform_url": values.get("auction_platform_url") or None,
        "nature_of_assets_pdf": values.get("nature_of_assets_pdf") or None,
        "emd_amount": emd_amount,
        "reserve_price_pdf": reserve_price_pdf,
        "area_mentions": area_mentions,
    }
    return result, flags


def enrich_record_with_details(rec: IBBIRecord) -> None:
    """Fetch + parse rec.details_pdf_url and fill in cin/location/
    emd_amount/auction_platform/plot_area_mentions. Mutates rec in place.
    Never raises — any failure (missing URL, fetch error, empty/unparseable
    PDF) is appended to rec.flags and rec.details_pdf_parsed stays False,
    so one bad PDF never drops or silently skips a listing from the run."""
    if not rec.details_pdf_url:
        rec.flags.append("no details_pdf_url — cannot run Part 3C enrichment for this row")
        return

    try:
        pdf_bytes = fetch_pdf_bytes(rec.details_pdf_url)
    except Exception as exc:  # noqa: BLE001 — surface, don't crash the run
        rec.flags.append(f"details PDF fetch failed: {exc}")
        return

    try:
        text = extract_pdf_text(pdf_bytes)
    except Exception as exc:  # noqa: BLE001
        rec.flags.append(f"details PDF text extraction failed: {exc}")
        return

    if not text.strip():
        rec.flags.append("details PDF text extraction returned empty text")
        return

    parsed, flags = parse_details_pdf(text)
    rec.cin = parsed["cin"]
    rec.location = parsed["location"]
    rec.auction_platform = parsed["auction_platform"]
    rec.auction_platform_url = parsed["auction_platform_url"]
    rec.emd_amount = parsed["emd_amount"]
    rec.plot_area_mentions = parsed["area_mentions"]
    rec.details_pdf_parsed = True
    rec.flags.extend(flags)

    # Cross-check against the table's own reserve price (from 3A/3B) —
    # two independently-parsed copies of the same number; a mismatch is
    # worth surfacing even though it's not any single field's fault.
    pdf_rp = parsed["reserve_price_pdf"]
    if pdf_rp is not None and rec.reserve_price is not None and pdf_rp != rec.reserve_price:
        rec.flags.append(f"reserve price mismatch: table={rec.reserve_price} pdf={pdf_rp}")


def enrich_all_with_details(
    records: list[IBBIRecord],
    delay_seconds: Optional[float] = None,
) -> None:
    """Run enrich_record_with_details across every record, one PDF fetch
    per record, with a delay between requests (same politeness rule as the
    listing-page fetches — this is a second network pass, not a free
    lunch). Mutates records in place; nothing is returned because nothing
    here can be dropped — nothing to collect separately from rec.flags."""
    delay = config.REQUEST_DELAY_SECONDS if delay_seconds is None else delay_seconds
    for i, rec in enumerate(records):
        if i > 0:
            time.sleep(delay)
        enrich_record_with_details(rec)


# ---------------------------------------------------------------------------
# Part 5B — notice_pdf_url parsing (possession_status + land_classification)
#
# Decided 2026-08-09 (owner): this is a real scraper part, not a
# skip-for-now. possession_status is disclosed in the auction notice's own
# free text (the big `notice_pdf_url` PDF Part 3C deliberately did NOT
# parse — several hundred KB to a few MB, free-text/possibly-scanned, per
# that module's own docstring above), not in the small structured details
# PDF or the table's nature_of_assets column. land_classification has no
# dedicated field anywhere, so it's read off the SAME text opportunistically
# (falling back to nature_of_assets, already scraped, if the notice PDF
# isn't usable) rather than justifying a third fetch.
#
# Both are best-effort keyword matches on free text, same philosophy as
# Part 3C's plot_area_mentions: flagged and left None when nothing
# recognizable is found, never guessed. A scanned/image-only notice PDF
# (no OCR here) is the expected main failure mode — flagged, not fatal.
# ---------------------------------------------------------------------------

# Ordered so more-specific patterns are checked first — "non-agricultural"
# contains "agricultural" as a \b-bounded substring (the hyphen is a
# non-word character), so if "agricultural" were checked first it would
# also match inside "non-agricultural" and silently misclassify it.
LAND_CLASSIFICATION_PATTERNS = [
    ("non-agricultural", re.compile(r"non[\s-]?agricultural", re.IGNORECASE)),
    ("agricultural", re.compile(r"\bagricultural\b", re.IGNORECASE)),
    ("industrial", re.compile(r"\bindustrial\b", re.IGNORECASE)),
    ("residential", re.compile(r"\bresidential\b", re.IGNORECASE)),
    ("commercial", re.compile(r"\bcommercial\b", re.IGNORECASE)),
]

POSSESSION_PHYSICAL_PATTERN = re.compile(r"\bphysical possession\b", re.IGNORECASE)
POSSESSION_SYMBOLIC_PATTERN = re.compile(r"\bsymbolic possession\b", re.IGNORECASE)


def _detect_possession_status(text: str) -> tuple[Optional[str], list[str]]:
    """Best-effort keyword search for 'physical possession' / 'symbolic
    possession' in notice text. Returns (status, flags). Both phrases
    present -> ambiguous (some notices cover multiple assets/lots with
    different possession per lot) -> None + flagged, not guessed. Neither
    present -> None + flagged (may just use different wording)."""
    has_physical = bool(POSSESSION_PHYSICAL_PATTERN.search(text))
    has_symbolic = bool(POSSESSION_SYMBOLIC_PATTERN.search(text))
    if has_physical and has_symbolic:
        return None, [
            "possession_status ambiguous: notice text mentions both "
            "'physical possession' and 'symbolic possession' (e.g. "
            "different lots) -- not auto-resolved, needs a manual read"
        ]
    if has_physical:
        return "physical", []
    if has_symbolic:
        return "symbolic", []
    return None, [
        "possession_status not found: neither 'physical possession' nor "
        "'symbolic possession' appears in the notice text (best-effort "
        "keyword search — the notice may use different wording, or this "
        "may not be a SARFAESI-style disclosure)"
    ]


def _detect_land_classification(text: Optional[str]) -> tuple[Optional[str], list[str]]:
    """Best-effort keyword search for a land-classification term. Returns
    (classification, flags). None + flagged if no recognized keyword is
    present, never guessed from surrounding context."""
    if not text or not text.strip():
        return None, ["land_classification not scored: no text available to search"]
    for label, pattern in LAND_CLASSIFICATION_PATTERNS:
        if pattern.search(text):
            return label, []
    return None, [
        "land_classification not found: no recognized keyword "
        "(agricultural/non-agricultural/industrial/residential/commercial) "
        "in the searched text"
    ]


def enrich_record_with_notice(rec: IBBIRecord) -> None:
    """Fetch + parse rec.notice_pdf_url for possession_status, and use that
    same text (or, if unavailable, the already-scraped nature_of_assets) for
    a best-effort land_classification guess. Mutates rec in place. Never
    raises — any failure is appended to rec.flags; rec.notice_pdf_parsed
    marks whether a real fetch was attempted, same "attempted vs found
    nothing" distinction as Part 3C's details_pdf_parsed."""
    text: Optional[str] = None

    if not rec.notice_pdf_url:
        rec.flags.append("no notice_pdf_url -- cannot run Part 5B enrichment for this row")
    else:
        pdf_bytes = None
        try:
            pdf_bytes = fetch_pdf_bytes(rec.notice_pdf_url)
        except Exception as exc:  # noqa: BLE001 — surface, don't crash the run
            rec.flags.append(f"notice PDF fetch failed: {exc}")

        if pdf_bytes is not None:
            try:
                text = extract_pdf_text(pdf_bytes)
            except Exception as exc:  # noqa: BLE001
                rec.flags.append(f"notice PDF text extraction failed: {exc}")
                text = None
            else:
                if not text.strip():
                    rec.flags.append(
                        "notice PDF text extraction returned empty text -- "
                        "likely a scanned/image-based PDF, no OCR attempted"
                    )
                    text = None
        rec.notice_pdf_parsed = True

    # possession_status only ever comes from the notice PDF's own text
    # (per the 2026-08-09 decision — it isn't reliably present anywhere
    # else already scraped). No fallback source for this one.
    if text:
        possession, p_flags = _detect_possession_status(text)
        rec.possession_status = possession
        rec.flags.extend(p_flags)
    else:
        rec.flags.append("possession_status not scored: no usable notice PDF text")

    # land_classification prefers the fuller notice-PDF text when available,
    # falls back to the shorter nature_of_assets text already scraped in
    # 3A/3B otherwise.
    classification_source = text if text else rec.nature_of_assets
    classification, c_flags = _detect_land_classification(classification_source)
    rec.land_classification = classification
    rec.flags.extend(c_flags)
    if classification and not text:
        rec.flags.append(
            "land_classification derived from the shorter nature_of_assets "
            "text (notice PDF text unavailable), not the fuller notice text"
        )


def enrich_all_with_notice(
    records: list[IBBIRecord],
    delay_seconds: Optional[float] = None,
) -> None:
    """Run enrich_record_with_notice across every record, one PDF fetch per
    record, with a delay between requests (same politeness rule as every
    other network pass here). Notice PDFs run larger than details PDFs
    (hundreds of KB to a few MB, per Part 3C's own docstring) so this pass
    is slower — that's expected, not a bug. Mutates records in place."""
    delay = config.REQUEST_DELAY_SECONDS if delay_seconds is None else delay_seconds
    for i, rec in enumerate(records):
        if i > 0:
            time.sleep(delay)
        enrich_record_with_notice(rec)


if __name__ == "__main__":
    # Manual smoke test.
    # Part 3A (single page) was already confirmed on a real run
    # (2026-08-09: 20/20 parsed, 0 flags) — this still re-runs it as a
    # quick sanity check every time. Part 3B (the pagination loop below)
    # has NOT yet been run — owner, please run `python scraper/ibbi.py`
    # and paste back the output (or the traceback if it errors).
    print(f"Fetching {IBBI_LISTING_URL} ...")
    page_html = fetch_page(1)
    total = get_total_records(page_html)
    print(f"Total Records reported by site: {total}")

    recs, problems = parse_listing_table(page_html)
    print(f"Parsed {len(recs)} records, {len(problems)} unparseable rows.")

    flagged = [r for r in recs if r.flags]
    print(f"{len(flagged)} of {len(recs)} records have at least one flag.")

    if recs:
        print("\nFirst record:")
        print(recs[0])

    if problems:
        print("\nProblem rows:")
        for p in problems[:5]:
            print(p)

    print("\n--- Part 3B: pagination smoke test (first 3 pages only) ---")
    all_recs, all_problems = scrape_all_pages(max_pages=3)
    print(f"Fetched {len(all_recs)} unique records across up to 3 pages "
          f"(cross-page boundary duplicates are de-duplicated automatically), "
          f"{len(all_problems)} problem entries total.")

    dropped_dupes = [p for p in all_problems if "boundary duplicate" in p.get("reason", "")]
    other_problems = [p for p in all_problems if p not in dropped_dupes]
    print(f"  {len(dropped_dupes)} were cross-page boundary duplicates (expected, "
          f"a site quirk — see module docstring); {len(other_problems)} were "
          f"other problems (should normally be 0).")
    for p in dropped_dupes[:10]:
        print(f"    dropped dupe: page {p['page']} | {p['corporate_debtor']} | "
              f"{p['notice_date']}")
    for p in other_problems[:10]:
        print(f"    OTHER PROBLEM: {p}")

    # Sanity check: no duplicate details_pdf_url should remain post-dedup.
    urls = [r.details_pdf_url for r in all_recs if r.details_pdf_url]
    remaining_dupes = len(urls) - len(set(urls))
    print(f"Remaining duplicate details_pdf_url after dedup: {remaining_dupes} "
          f"(should be 0)")

    print("\n--- Part 3C: details-PDF parsing (real network test) ---")
    sample = [r for r in all_recs if r.details_pdf_url][:3]
    if not sample:
        print("No records with a details_pdf_url available from the runs "
              "above — can't run a real test here.")
    else:
        print(f"Enriching {len(sample)} real record(s) from the fetch above "
              f"— actually hits ibbi.gov.in for each one.")
        for i, rec in enumerate(sample):
            if i > 0:
                time.sleep(config.REQUEST_DELAY_SECONDS)
            print(f"  [{i+1}/{len(sample)}] {rec.corporate_debtor!r} "
                  f"({rec.details_pdf_url}) ...")
            enrich_record_with_details(rec)
            print(f"      details_pdf_parsed={rec.details_pdf_parsed} "
                  f"cin={rec.cin} emd_amount={rec.emd_amount} "
                  f"location={rec.location!r} "
                  f"auction_platform={rec.auction_platform!r} "
                  f"plot_area_mentions={rec.plot_area_mentions}")
            new_flags = [f for f in rec.flags if "details PDF" in f or "reserve price mismatch" in f
                         or "area/size figure" in f or "not found in details PDF" in f
                         or "CIN not found" in f or "location not found" in f]
            if new_flags:
                print(f"      flags from this enrichment: {new_flags}")
        parsed_ok = sum(1 for r in sample if r.details_pdf_parsed)
        print(f"{parsed_ok}/{len(sample)} real details PDFs parsed successfully.")

    print("\n--- Part 3C: offline synthetic-fixture check (supplementary, "
          "not a substitute for the real test above) ---")
    print("Runs the same extract_pdf_text()/parse_details_pdf() code against "
          "synthetic PDFs built from 4 real details-PDF texts fetched "
          "directly on 2026-08-09, covering every field-layout variant "
          "seen (plain, 'Others'-platform, going-concern, Corrigendum) — "
          "useful for catching regex/layout bugs even when the real test "
          "above already passed.")

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as _canvas
    except ImportError:
        print("reportlab not installed — skipping the Part 3C offline test.")
    else:
        # Real text extracted (via the assistant's browsing tool, not this
        # sandbox) from 4 real details_pdf_url documents on 2026-08-09,
        # chosen to cover every field-layout variant seen: plain single-
        # platform notice, "Others" platform (12(a)), going-concern sale,
        # and a Corrigendum (6(a)).
        fixtures = {
            "single_platform (Scotts Garments)": """1. Name of Corporate Debtor SCOTTS GARMENTS LIMITED
2. CIN/LLPIN of Corporate Debtor U18101KA2002PLC030185
3. Insolvency Commencement Date 13/08/2018
4. Process Number 1
5. Liquidation Commencement Date 31/10/2023
6. Form is being filed for Issue of Auction Notice
7. Date of Issue of Auction Notice in Newspapers 28/02/2025
8. Last Date of Submission of EMD (including extension) 17/03/2025
9. Date of Auction 19/03/2025
10. Reserve Price (In Rupees) 10000000
11. EMD Amount (In Rupees) 1000000
12. Auction Platform PDA - National E-Governance Services Limited
14. Web address of Auction Platform https://nbid.nesl.co.in
15. Nature of Assets to be Auctioned Industrial property situated at No. 1028, Irudayapuram,
Robertsonpet, Bangarpet Taluk, Kolar District - Land
measuring 7,450 sq. ft and building with built up area of
14,200 sq. ft. excluding all items, machines, fixtures in the
premises whether attached to it or not
16. Location of Assets to be Auctioned Robertsonpet, Bangarpet Taluk, Kolar District. KA
Unique Number - Liq.AN/U18101KA2002PLC030185/1/IP-11707/0225/00080
Name of IP - Mr. Madhugiri Venkatarayappa Sudarshan""",
            "others_platform (JVL Agro)": """1. Name of Corporate Debtor JVL Agro Industries Limited
2. CIN/LLPIN of Corporate Debtor L15140UP1989PLC011396
3. Insolvency Commencement Date 25/07/2018
4. Process Number 1
5. Liquidation Commencement Date 19/08/2020
6. Form is being filed for Issue of Auction Notice
7. Date of Issue of Auction Notice in Newspapers 27/02/2025
8. Last Date of Submission of EMD (including extension) 31/03/2025
9. Date of Auction 02/04/2025
10. Reserve Price (In Rupees) 60244500
11. EMD Amount (In Rupees) 6024450
12. Auction Platform eBKray
14. Web address of Auction Platform https://ebkray.in
15. Nature of Assets to be Auctioned Parcel of Land; Vehicle
16. Location of Assets to be Auctioned Kamalpur, District Kamrup, Assam; Varanasi, Uttar
Pradesh
Unique Number - Liq.AN/L15140UP1989PLC011396/1/IP-11098/0225/00022
Name of IP - Mr. Supriyo Kumar Chaudhuri""",
            "going_concern (Arambagh Hatcheries)": """1. Name of Corporate Debtor Arambagh Hatcheries LImited
2. CIN/LLPIN of Corporate Debtor U01222WB1973PLC029137
3. Insolvency Commencement Date 01/05/2024
4. Process Number 1
5. Liquidation Commencement Date 17/05/2024
6. Form is being filed for Issue of Auction Notice
7. Date of Issue of Auction Notice in Newspapers 01/03/2025
8. Last Date of Submission of EMD (including extension) 01/04/2025
9. Date of Auction 04/04/2025
10. Reserve Price (In Rupees) 943731000
11. EMD Amount (In Rupees) 47186550
12. Auction Platform Others
12(a). Auction Platform (Others) MSTC
14. Web address of Auction Platform www.mstcindia.co.in
15. Nature of Assets to be Auctioned Sale of entire Corporate Debtor M/s. Arambagh Hatcheries
Limited - in Liquidation as a Going Concern
16. Location of Assets to be Auctioned Across various locations in the state of West Bengal
Unique Number - Liq.AN/U01222WB1973PLC029137/1/IP-10982/0325/00003
Name of IP - Mr. Rajiv Kumar Agarwal""",
            "corrigendum (PPS Enviro Power)": """1. Name of Corporate Debtor PPS Enviro Power Pvt Ltd
2. CIN/LLPIN of Corporate Debtor U40106TG2002PTC048720
3. Insolvency Commencement Date 13/08/2019
4. Process Number 1
5. Liquidation Commencement Date 29/12/2021
6. Form is being filed for Corrigendum
6(a). Auction notices issued Liq.AN/U40106TG2002PTC048720/1/IP-12980/0225/00014
7. Date of Issue of Auction Notice in Newspapers 16/02/2025
8. Last Date of Submission of EMD (including extension) 10/03/2025
9. Date of Auction 13/03/2025
10. Reserve Price (In Rupees) 540000000
11. EMD Amount (In Rupees) 20000000
12. Auction Platform Others
12(a). Auction Platform (Others) bankeauctions
14. Web address of Auction Platform www.bankeauctions.com
15. Nature of Assets to be Auctioned No changes. Corrigendum No 2 issued on 28.02.2025 for
(i) Additional Disclosure of 2 pending legal matters
16. Location of Assets to be Auctioned No changes. Corrigendum No 2 issued on 28.02.2025
Unique Number - Liq.AN/U40106TG2002PTC048720/1/IP-12980/0225/00014-C04
Name of IP - Kallat Vatsa Kumar""",
        }

        expected = {
            "single_platform (Scotts Garments)": {"cin": "U18101KA2002PLC030185", "emd_amount": 1000000, "reserve_price_pdf": 10000000, "location": "Robertsonpet, Bangarpet Taluk, Kolar District. KA"},
            "others_platform (JVL Agro)": {"cin": "L15140UP1989PLC011396", "emd_amount": 6024450, "reserve_price_pdf": 60244500, "auction_platform": "eBKray"},
            "going_concern (Arambagh Hatcheries)": {"cin": "U01222WB1973PLC029137", "emd_amount": 47186550, "auction_platform": "MSTC"},
            "corrigendum (PPS Enviro Power)": {"cin": "U40106TG2002PTC048720", "emd_amount": 20000000, "auction_platform": "bankeauctions"},
        }

        all_ok = True
        for name, fixture_text in fixtures.items():
            buf = io.BytesIO()
            c = _canvas.Canvas(buf, pagesize=A4)
            c.setFont("Helvetica", 9)
            y = 800
            for line in fixture_text.split("\n"):
                c.drawString(40, y, line)
                y -= 14
            c.save()
            pdf_bytes = buf.getvalue()

            extracted_text = extract_pdf_text(pdf_bytes)
            parsed, flags = parse_details_pdf(extracted_text)

            checks = expected[name]
            mismatches = [
                f"{k}: expected {v!r}, got {parsed.get(k)!r}"
                for k, v in checks.items() if parsed.get(k) != v
            ]
            status = "OK" if not mismatches else "MISMATCH"
            if mismatches:
                all_ok = False
            print(f"  [{status}] {name}: emd_amount={parsed['emd_amount']} "
                  f"cin={parsed['cin']} platform={parsed['auction_platform']} "
                  f"area_mentions={parsed['area_mentions']} "
                  f"({len(flags)} flag(s))")
            for mm in mismatches:
                print(f"      MISMATCH: {mm}")
            for fl in flags:
                print(f"      flag: {fl}")

        print(f"\nPart 3C offline round-trip: {'ALL 4 FIXTURES OK' if all_ok else 'SOME MISMATCHES — see above'}")
