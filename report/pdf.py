"""
report/pdf.py — Part 7B: PDF layout + report categorization.

--------------------------------------------------------------------------
FILENAME/LOCATION DECISION (flagged per Section 0 rule 1, not guessed):
inside the existing (empty) report/ package, as report/pdf.py rather than
report/__init__.py itself — mirrors how ai_analysis/'s three modules each
get their own file rather than living in ai_analysis/__init__.py. Named
`pdf.py` (not `generate.py`/`layout.py`) since PDF is the only output
format this project has ever specified (Section 2: "reportlab for PDF").
--------------------------------------------------------------------------
WHAT THIS CONSUMES: `run_pipeline()`'s return value (pipeline.py, Part
7A) — specifically its "assembled" list, one dict per listing:
  {
    "listing_key": str,
    "status": "new"|"unchanged"|"changed"|"collision",
    "changes": [{"field","old","new"}, ...]   -- only non-empty for "changed"
    "price_drop": bool,
    "raw": {...scraped IBBIRecord fields, incl. any dataclass date objects...},
    "score": {"5a": {...}, "5b": {...}, "5c": {...}},   -- scoring/rules.py output
    "enrichment": {...raw sqlite row, JSON columns as TEXT...} | None,
    "enrichment_reused": bool,
    "flags": [...],   -- only present on collision entries (see pipeline.py)
  }
This module reads `changes`/`status` straight off these dicts (which
pipeline.py already populated from storage.db.store_records()) rather
than re-querying `listing_history` itself, per the Part 7B roadmap entry
in PROJECT_STATUS.md ("the latter two read new/changed status and
field-level diffs straight from 7A's store_records() call ... not a
second DB query").
--------------------------------------------------------------------------
NO REAL FINAL SCORE YET (flagged, not glossed over): config.SCORE_WEIGHTS
is still all None (owner hasn't set real weights across the five scoring
criteria — see Part 5's own comments in config.py). `combined_score()`
below is a plain average of whichever of partial_score_5a/5b/5c are
available for a listing — a reasonable placeholder ranking (Claude-picked
default, same status as REPORT_TOP_N/LOCATION_MATCH_NEUTRAL/etc.), NOT
the finished weighted score Part 7's architecture decision describes.
The PDF itself says so under the "Top-scored" heading rather than
presenting this as a finished ranking.
--------------------------------------------------------------------------
CATEGORIES (Section 1's own description: "top-scored -> closing soon ->
new today -> watchlist changes"):
  - top_scored: every listing with a combined_score, sorted best-first,
    capped at config.REPORT_TOP_N. A listing missing a combined score
    entirely (a rare case per combined_score()'s own docstring) is
    excluded from this section, not scored 0/last — 0 would misreport it
    as a genuinely bad listing rather than an unscored one.
  - closing_soon: auction_date or emd_due_date falls within
    config.CLOSING_SOON_DAYS of the report date and is not already in the
    past. Sorted by that nearest date, soonest first.
  - new_today: status == "new".
  - watchlist_changes: status == "changed", each with its field-level
    diff (old -> new) straight from `changes`.
A listing can legitimately appear in more than one section (e.g.
top-scored AND closing soon) — flagged as a deliberate default, not an
oversight: an owner reading a morning report benefits from seeing "this
is both a great match AND closes in 3 days" rather than having it
silently de-duplicated into only one section.

COLLISIONS get their own small section (not in Section 1's original
list, but this project's "never silently hide a flagged listing" rule
covers it) — still scored, but enrichment for a collision entry is None
this run (see pipeline.py's own collision-handling docstring), so its
card says so plainly rather than showing an empty narrative silently.
--------------------------------------------------------------------------
"""

from __future__ import annotations

import html
import json
import os
from datetime import date, datetime
from typing import Optional

import config

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    HRFlowable,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# ---------------------------------------------------------------------------
# Page numbers (Part 9, owner request 2026-08-14). Standard reportlab
# two-pass technique: SimpleDocTemplate only knows the CURRENT page number
# while drawing, not the final total, so showPage() is overridden to stash
# each page's finished canvas state instead of flushing it immediately;
# save() then replays every stashed page, now that the true total page
# count is known, drawing "Page X of N" on each before the real showPage/
# save happens. No layout-flowable changes needed elsewhere in this file --
# doc.build(..., canvasmaker=_NumberedCanvas) below is the only call site.
# ---------------------------------------------------------------------------
class _NumberedCanvas(Canvas):
    def __init__(self, *args, **kwargs):
        Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_number(total_pages)
            Canvas.showPage(self)
        Canvas.save(self)

    def _draw_page_number(self, total_pages: int):
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.grey)
        text = f"Page {self._pageNumber} of {total_pages}"
        # Bottom-right, inside the doc's own margins (generate_report()
        # below uses 1.8cm side / 1.6cm bottom margins) so this never
        # collides with body content.
        self.drawRightString(A4[0] - 1.8 * cm, 1.0 * cm, text)


# ---------------------------------------------------------------------------
# Small formatting helpers. Every one of these is defensive about missing/
# malformed data on purpose (never raises on a bad field) -- a report that
# crashes on one messy listing and produces NOTHING is strictly worse than
# one that shows "(not available)" on that one field and still delivers
# everything else, which is what this project's own scraper/scoring/
# enrichment modules already do throughout (never block the batch on one
# bad record).
# ---------------------------------------------------------------------------

def _fmt_currency(value) -> str:
    """Indian-style comma grouping (e.g. 5000000 -> 'Rs. 50,00,000'). A
    literal 0 is IBBI's own placeholder for 'no reserve fixed' (see
    scoring/rules.py's compute_price_vs_reserve_scores docstring) -- shown
    as such rather than 'Rs. 0', which would misleadingly read as a real
    free listing.

    Uses 'Rs.' rather than the '\u20b9' glyph on purpose (bug found +
    fixed while visually checking this section's first real render,
    2026-08-11): reportlab's default base-14 fonts (Helvetica etc, no
    font registration done anywhere else in this project either) don't
    include the Indian Rupee sign glyph -- it silently rendered as a
    solid black box in the actual PDF, not an exception, so nothing else
    caught it. 'Rs.' is universally renderable in the default font and
    avoids depending on bundling + registering a Unicode-coverage TTF
    just for one symbol."""
    if value is None:
        return "not disclosed"
    try:
        n = int(value)
    except (TypeError, ValueError):
        return "not disclosed"
    if n == 0:
        return "no reserve fixed (per notice)"
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    sign = "-" if n < 0 else ""
    return f"{sign}Rs. {s}"


def _fmt_date(value) -> str:
    """`raw` fields come straight from dataclasses.asdict() (see
    pipeline.py's _rec_to_raw_dict), which does NOT stringify date objects
    -- so these usually arrive as real datetime.date objects. Handles ISO
    strings too (e.g. if a caller passes JSON-round-tripped data, as
    test_part7b.py's synthetic fixtures do for a couple of cases on
    purpose, to prove both paths work)."""
    if value is None:
        return "unknown"
    if isinstance(value, (date, datetime)):
        return value.strftime("%d %b %Y")
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10]).strftime("%d %b %Y")
        except ValueError:
            return value
    return str(value)


def _as_date(value) -> Optional[date]:
    """Same tolerant parsing as _fmt_date, but returns a real date (or
    None) for comparisons -- used by closing-soon detection and sorting."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _safe_json_loads(text) -> Optional[dict]:
    """Enrichment JSON columns (storage/db.py's enrichment table) are
    stored as TEXT; get_enrichment()'s own docstring is explicit that
    callers must parse them themselves. Never raises -- a malformed/None
    value just means "nothing to show", flagged in the card rather than
    crashing the whole report over one bad row."""
    if not text:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def parse_enrichment(enrichment: Optional[dict]) -> dict:
    """Normalizes one assembled-entry's raw `enrichment` sqlite row (or
    None) into the shape this module actually wants to render. Matches
    the JSON shapes documented in storage/db.py's SCHEMA comment for the
    enrichment table (gemini_narrative_json/mca_data_json/news_data_json/
    news_flags_json)."""
    out = {
        "available": enrichment is not None,
        "narrative": None,
        "narrative_flags": [],
        "mca_data": None,
        "mca_flags": [],
        "news_data": None,
        "news_flags": [],
        "reused": None,
    }
    if enrichment is None:
        return out

    gemini = _safe_json_loads(enrichment.get("gemini_narrative_json"))
    if gemini:
        out["narrative"] = gemini.get("narrative")
        out["narrative_flags"] = gemini.get("flags") or []

    mca = _safe_json_loads(enrichment.get("mca_data_json"))
    if mca:
        out["mca_data"] = mca.get("mca_data")
        out["mca_flags"] = mca.get("flags") or []

    out["news_data"] = _safe_json_loads(enrichment.get("news_data_json"))
    out["news_flags"] = _safe_json_loads(enrichment.get("news_flags_json")) or []

    return out


def combined_score(entry: dict) -> tuple[Optional[float], list[str]]:
    """See module docstring's "NO REAL FINAL SCORE YET" section. Averages
    whichever of partial_score_5a/5b/5c are not None. Returns
    (score_or_None, flags) -- flags explain when/why a component was
    unavailable, never silently dropped."""
    score = entry.get("score", {})
    parts = []
    flags = []
    for key, label in (("5a", "5A (price/location)"), ("5b", "5B (possession/classification)"), ("5c", "5C (plot size)")):
        partial = (score.get(key) or {}).get(f"partial_score_{key}")
        if partial is not None:
            parts.append(partial)
        else:
            flags.append(f"{label} unavailable for this listing's combined score")
    if not parts:
        return None, flags + ["no scoring components available at all"]
    return round(sum(parts) / len(parts), 1), flags


def _nearest_upcoming_date(raw: dict, today: date) -> tuple[Optional[date], Optional[str]]:
    """Picks whichever of auction_date/emd_due_date is soonest AND not
    already in the past, for closing-soon detection/sorting. Returns
    (date, field_name) or (None, None) if neither is a usable future
    date."""
    candidates = []
    for field in ("auction_date", "emd_due_date"):
        d = _as_date(raw.get(field))
        if d is not None and d >= today:
            candidates.append((d, field))
    if not candidates:
        return None, None
    candidates.sort(key=lambda t: t[0])
    return candidates[0]


# ---------------------------------------------------------------------------
# Categorization -- pure data-shaping, no reportlab involved, so this half
# is independently unit-testable without touching PDF rendering at all.
# ---------------------------------------------------------------------------

def categorize_assembled(assembled: list[dict], report_date: Optional[date] = None) -> dict:
    """
    Splits `run_pipeline()`'s "assembled" list into the report's sections.
    See module docstring for exactly what each section means and why a
    listing can appear in more than one.

    Returns:
      {
        "report_date": date,
        "top_scored": [entry, ...],       -- each carries injected
                                              "_combined_score"/"_combined_score_flags"
        "closing_soon": [entry, ...],     -- each carries injected
                                              "_closing_date"/"_closing_field"
        "new_today": [entry, ...],
        "watchlist_changes": [entry, ...],
        "collisions": [entry, ...],
        "counts": {"total": N, "top_scored": N, "closing_soon": N,
                   "new_today": N, "watchlist_changes": N, "collisions": N},
      }
    """
    report_date = report_date or date.today()

    scored: list[dict] = []
    closing: list[dict] = []
    new_today: list[dict] = []
    changed: list[dict] = []
    collisions: list[dict] = []

    for entry in assembled:
        raw = entry.get("raw", {})

        cscore, cflags = combined_score(entry)
        if cscore is not None:
            annotated = {**entry, "_combined_score": cscore, "_combined_score_flags": cflags}
            scored.append(annotated)

        closing_date, closing_field = _nearest_upcoming_date(raw, report_date)
        if closing_date is not None and (closing_date - report_date).days <= config.CLOSING_SOON_DAYS:
            closing.append({**entry, "_closing_date": closing_date, "_closing_field": closing_field})

        if entry.get("status") == "new":
            new_today.append(entry)
        elif entry.get("status") == "changed":
            changed.append(entry)
        elif entry.get("status") == "collision":
            collisions.append(entry)

    scored.sort(key=lambda e: e["_combined_score"], reverse=True)
    top_scored = scored[: config.REPORT_TOP_N]
    closing.sort(key=lambda e: e["_closing_date"])

    return {
        "report_date": report_date,
        "top_scored": top_scored,
        "closing_soon": closing,
        "new_today": new_today,
        "watchlist_changes": changed,
        "collisions": collisions,
        "counts": {
            "total": len(assembled),
            "top_scored": len(top_scored),
            "closing_soon": len(closing),
            "new_today": len(new_today),
            "watchlist_changes": len(changed),
            "collisions": len(collisions),
        },
    }


# ---------------------------------------------------------------------------
# PDF rendering (reportlab platypus -- per Section 2's stack decision)
# ---------------------------------------------------------------------------

_styles = getSampleStyleSheet()
_STYLE_TITLE = ParagraphStyle("ReportTitle", parent=_styles["Title"], fontSize=20, spaceAfter=4)
_STYLE_SUBTITLE = ParagraphStyle("ReportSubtitle", parent=_styles["Normal"], fontSize=10, textColor=colors.grey, spaceAfter=14)
_STYLE_SECTION = ParagraphStyle("SectionHeading", parent=_styles["Heading1"], fontSize=15, spaceBefore=18, spaceAfter=4, textColor=colors.HexColor("#1a3d5c"))
_STYLE_SECTION_NOTE = ParagraphStyle("SectionNote", parent=_styles["Normal"], fontSize=8.5, textColor=colors.grey, spaceAfter=10, alignment=TA_LEFT)
_STYLE_CARD_TITLE = ParagraphStyle("CardTitle", parent=_styles["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=2)
_STYLE_BODY = ParagraphStyle("Body", parent=_styles["Normal"], fontSize=9.5, leading=13)
_STYLE_LABEL = ParagraphStyle("Label", parent=_styles["Normal"], fontSize=9.5, leading=13, textColor=colors.HexColor("#333333"))
_STYLE_FLAG = ParagraphStyle("Flag", parent=_styles["Normal"], fontSize=8.5, leading=12, textColor=colors.HexColor("#8a5a00"))
_STYLE_EMPTY = ParagraphStyle("Empty", parent=_styles["Normal"], fontSize=9.5, textColor=colors.grey, spaceAfter=10)


def _facts_table(raw: dict) -> Table:
    # Plain strings in a Table cell are drawn as ONE unwrapped line and
    # silently clip at the column edge -- reportlab only wraps text that's
    # inside a Paragraph flowable. Location/nature_of_assets are the two
    # longest free-text fields here, so they're the ones that visibly hit
    # the wall (bug found from a real report render, 2026-08-13). Escaping
    # via html.escape matters now that these values go through Paragraph's
    # mini-XML parser -- raw scraped text containing "&"/"<"/">" (e.g.
    # "Plant & Machinery") would otherwise break the parse or vanish
    # silently instead of just clipping.
    def cell(text: str) -> Paragraph:
        return Paragraph(html.escape(str(text)), _STYLE_BODY)

    rows = [
        [cell("Reserve price"), cell(_fmt_currency(raw.get("reserve_price")))],
        [cell("Location"), cell(raw.get("location") or "not yet known")],
        [cell("Auction date"), cell(_fmt_date(raw.get("auction_date")))],
        [cell("EMD due date"), cell(_fmt_date(raw.get("emd_due_date")))],
        [cell("IP / liquidator"), cell(raw.get("ip_name") or "unknown")],
        [cell("Nature of assets"), cell(raw.get("nature_of_assets") or "unknown")],
    ]
    t = Table(rows, colWidths=[3.3 * cm, 12 * cm])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#555555")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def _score_line(entry: dict) -> str:
    score = entry.get("score", {})
    a = (score.get("5a") or {}).get("partial_score_5a")
    b = (score.get("5b") or {}).get("partial_score_5b")
    c = (score.get("5c") or {}).get("partial_score_5c")

    def fmt(v):
        return "n/a" if v is None else f"{v:.0f}"

    line = f"5A price/location: {fmt(a)} &nbsp;|&nbsp; 5B possession/classification: {fmt(b)} &nbsp;|&nbsp; 5C plot size: {fmt(c)}"
    if "_combined_score" in entry:
        line = f"<b>Combined (placeholder average): {entry['_combined_score']:.0f}/100</b> &nbsp;&mdash;&nbsp; " + line
    return line


def _listing_flowables(entry: dict, story: list) -> None:
    raw = entry.get("raw", {})
    ench = parse_enrichment(entry.get("enrichment"))

    title = raw.get("corporate_debtor") or "(name not available)"
    story.append(Paragraph(f"{title} &mdash; {raw.get('notice_type') or 'Notice'}", _STYLE_CARD_TITLE))
    story.append(Paragraph(_score_line(entry), _STYLE_LABEL))
    story.append(Spacer(1, 4))
    story.append(_facts_table(raw))
    story.append(Spacer(1, 4))

    if ench["narrative"]:
        n = ench["narrative"]
        if n.get("summary"):
            story.append(Paragraph(f"<b>Summary:</b> {n['summary']}", _STYLE_BODY))
        if n.get("price_read"):
            story.append(Paragraph(f"<b>Price read:</b> {n['price_read']}", _STYLE_BODY))
        risks = n.get("risk_notes") or []
        if risks:
            story.append(Paragraph("<b>Risk notes:</b> " + "; ".join(risks), _STYLE_BODY))
        gaps = n.get("data_gaps") or []
        if gaps:
            story.append(Paragraph("<b>Data gaps:</b> " + "; ".join(gaps), _STYLE_FLAG))
    elif entry.get("status") == "collision":
        story.append(Paragraph(
            "AI write-up not available this run: this listing collided with an "
            "existing different listing's identity hash and enrichment was "
            "skipped to avoid corrupting that other listing's data (see "
            "pipeline.py). Will enrich normally once the collision resolves.",
            _STYLE_FLAG,
        ))
    else:
        story.append(Paragraph("AI write-up not available for this listing yet.", _STYLE_FLAG))

    if ench["mca_data"]:
        mca = ench["mca_data"]
        bits = [f"{k}: {v}" for k, v in mca.items() if v]
        if bits:
            story.append(Paragraph("<b>Company registry (MCA):</b> " + "; ".join(bits), _STYLE_BODY))
    if ench["news_data"]:
        for item in ench["news_data"][:3]:
            t = item.get("title") or item.get("url") or "(untitled)"
            story.append(Paragraph(f"<b>News (unverified):</b> {t}", _STYLE_BODY))

    if entry.get("status") == "changed":
        for c in entry.get("changes", []):
            story.append(Paragraph(
                f"<b>Changed &mdash; {c['field']}:</b> {c.get('old')} \u2192 {c.get('new')}",
                _STYLE_FLAG,
            ))

    all_flags = list(entry.get("flags", [])) + ench["narrative_flags"] + ench["mca_flags"] + ench["news_flags"]
    if all_flags:
        story.append(Paragraph("Flags: " + "; ".join(all_flags), _STYLE_FLAG))

    links = []
    if raw.get("details_pdf_url"):
        links.append(f"Details PDF: {raw['details_pdf_url']}")
    if raw.get("notice_pdf_url"):
        links.append(f"Notice PDF: {raw['notice_pdf_url']}")
    if links:
        story.append(Paragraph(" &nbsp;|&nbsp; ".join(links), _STYLE_FLAG))

    story.append(HRFlowable(width="100%", color=colors.HexColor("#dddddd"), spaceBefore=6, spaceAfter=6))


def _section(story: list, heading: str, note: str, entries: list) -> None:
    story.append(Paragraph(heading, _STYLE_SECTION))
    if note:
        story.append(Paragraph(note, _STYLE_SECTION_NOTE))
    if not entries:
        story.append(Paragraph("None today.", _STYLE_EMPTY))
        return
    for entry in entries:
        _listing_flowables(entry, story)


def build_story(categorized: dict, run_summary: Optional[dict] = None) -> list:
    """Builds the reportlab flowable list for one report. Split out from
    generate_report() so a caller (or a test) can inspect/measure the
    story without writing a file, same "pure data in, easily testable"
    spirit as categorize_assembled()."""
    story = []
    story.append(Paragraph("Auction Intelligence — Daily Report", _STYLE_TITLE))
    story.append(Paragraph(categorized["report_date"].strftime("%A, %d %B %Y"), _STYLE_SUBTITLE))

    counts = categorized["counts"]
    summary_bits = [
        f"{counts['total']} listings tracked",
        f"{counts['new_today']} new today",
        f"{counts['watchlist_changes']} changed",
        f"{counts['closing_soon']} closing within {config.CLOSING_SOON_DAYS} days",
    ]
    if counts["collisions"]:
        summary_bits.append(f"{counts['collisions']} flagged for collision review")
    if run_summary:
        ss = run_summary.get("store_summary") or {}
        es = run_summary.get("enrichment_summary") or {}
        sp = run_summary.get("scrape_problems") or []
        summary_bits.append(
            f"enrichment: {es.get('reenriched', 0)} freshly generated, "
            f"{es.get('reused', 0)} reused, {es.get('skipped_collision', 0)} skipped"
        )
        if sp:
            summary_bits.append(f"{len(sp)} scrape problems this run (see below)")
    story.append(Paragraph(" &nbsp;|&nbsp; ".join(summary_bits), _STYLE_LABEL))

    # Location filter (Part 9, owner request 2026-08-14) -- this report
    # only ever contains listings pipeline.filter_assembled_by_location()
    # kept; state the exclusion counts plainly rather than letting a
    # smaller-than-expected report look like a scraping problem.
    if run_summary and run_summary.get("location_filter"):
        lf = run_summary["location_filter"]
        regions = ", ".join(config.INCLUDED_LOCATIONS.keys())
        story.append(Paragraph(
            f"Location filter active — showing only: {regions}. "
            f"{lf.get('excluded_other_location', 0)} listing(s) outside these locations "
            f"and {lf.get('excluded_unknown_location', 0)} with location not yet known "
            f"were excluded from this report.",
            _STYLE_SECTION_NOTE,
        ))

    _section(
        story, "Top-scored",
        "Ranked by a placeholder combined score (plain average of whatever 5A/5B/5C "
        "partial scores are available) — config.SCORE_WEIGHTS hasn't been set by the "
        "owner yet, so this is not the final weighted ranking.",
        categorized["top_scored"],
    )
    _section(
        story, "Closing soon",
        f"Auction date or EMD due date within {config.CLOSING_SOON_DAYS} days.",
        categorized["closing_soon"],
    )
    _section(story, "New today", "", categorized["new_today"])
    _section(story, "Watchlist changes", "Tracked fields that changed since the last run.", categorized["watchlist_changes"])

    if categorized["collisions"]:
        _section(
            story, "Flagged for review (collisions)",
            "Identity hash matched an existing different listing — see each card for detail.",
            categorized["collisions"],
        )

    if run_summary and run_summary.get("scrape_problems"):
        story.append(Paragraph("Scrape problems this run", _STYLE_SECTION))
        items = [ListItem(Paragraph(str(p), _STYLE_BODY)) for p in run_summary["scrape_problems"]]
        story.append(ListFlowable(items, bulletType="bullet"))

    return story


def generate_report(
    assembled: list[dict],
    output_path: Optional[str] = None,
    report_date: Optional[date] = None,
    run_summary: Optional[dict] = None,
) -> str:
    """
    Builds the full PDF and writes it to disk. Returns the path written.

    output_path: None -> config.REPORT_OUTPUT_DIR/auction_report_<date>.pdf
        (directory created if missing, same pattern as storage.db.get_connection).
    report_date: None -> date.today(). Passed through to categorize_assembled().
    run_summary: optional -- pass run_pipeline()'s own return dict (minus
        "assembled", which is `assembled` itself) to show scrape-problem
        counts and enrichment fresh/reused counts in the header. Report
        still renders fine without it.
    """
    categorized = categorize_assembled(assembled, report_date=report_date)

    if output_path is None:
        os.makedirs(config.REPORT_OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(
            config.REPORT_OUTPUT_DIR,
            f"auction_report_{categorized['report_date'].isoformat()}.pdf",
        )
    else:
        d = os.path.dirname(output_path)
        if d:
            os.makedirs(d, exist_ok=True)

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.6 * cm, bottomMargin=1.6 * cm,
        title="Auction Intelligence Daily Report",
    )
    story = build_story(categorized, run_summary=run_summary)
    doc.build(story, canvasmaker=_NumberedCanvas)
    return output_path


if __name__ == "__main__":
    # -----------------------------------------------------------------
    # Offline smoke test -- synthetic assembled-shaped data, no network
    # (this part needs none: PDF layout has no external dependency, unlike
    # 6A/6B/6C/7A). Unlike every prior test_part*.py in this project, this
    # one can actually be run+confirmed IN this sandbox, not just wired --
    # see test_part7b.py for the real confirmation run (it imports this
    # module directly and checks the produced PDF with pypdf).
    # -----------------------------------------------------------------
    from datetime import timedelta

    today = date(2026, 8, 11)

    def entry(**kw):
        base = {
            "listing_key": kw.get("listing_key", "k"),
            "status": kw.get("status", "unchanged"),
            "changes": kw.get("changes", []),
            "price_drop": False,
            "raw": kw["raw"],
            "score": kw.get("score", {
                "5a": {"partial_score_5a": 70},
                "5b": {"partial_score_5b": 60},
                "5c": {"partial_score_5c": 50},
            }),
            "enrichment": kw.get("enrichment"),
            "enrichment_reused": kw.get("enrichment_reused", False),
        }
        if kw.get("flags"):
            base["flags"] = kw["flags"]
        return base

    good_enrichment = {
        "gemini_narrative_json": json.dumps({
            "narrative": {"summary": "Industrial land near a highway junction.",
                           "price_read": "Reserve looks below comparable listings.",
                           "risk_notes": ["Symbolic possession only"], "data_gaps": []},
            "flags": [],
        }),
        "mca_data_json": json.dumps({"mca_data": {"company_name": "ABC TEXTILES PVT LTD", "status": "Active"}, "flags": []}),
        "news_data_json": json.dumps([{"title": "ABC Textiles faces insolvency proceedings", "url": "http://example/1"}]),
        "news_flags_json": json.dumps(["unverified web search result, not fact-checked"]),
    }

    listings = [
        entry(
            listing_key="a", status="unchanged",
            raw={"corporate_debtor": "ABC Textiles Pvt Ltd", "notice_type": "Sale Notice",
                 "reserve_price": 5000000, "location": "Rajpura, Punjab",
                 "auction_date": today + timedelta(days=20), "emd_due_date": today + timedelta(days=15),
                 "ip_name": "Ramesh Kumar", "nature_of_assets": "Industrial land 5 acres",
                 "details_pdf_url": "http://fake/d1.pdf", "notice_pdf_url": "http://fake/n1.pdf"},
            score={"5a": {"partial_score_5a": 88}, "5b": {"partial_score_5b": 40}, "5c": {"partial_score_5c": 50}},
            enrichment=good_enrichment,
        ),
        entry(
            listing_key="b", status="new",
            raw={"corporate_debtor": "XYZ Foods Ltd", "notice_type": "Liquidation Notice",
                 "reserve_price": 2000000, "location": None,
                 "auction_date": today + timedelta(days=3), "emd_due_date": today + timedelta(days=1),
                 "ip_name": "Sunita Rao", "nature_of_assets": "Warehouse 2 acres"},
            enrichment=None,
        ),
        entry(
            listing_key="c", status="changed",
            changes=[{"field": "reserve_price", "old": 9000000, "new": 8000000}],
            raw={"corporate_debtor": "Delta Realty Ltd", "notice_type": "Sale Notice",
                 "reserve_price": 8000000, "location": "Delhi",
                 "auction_date": today + timedelta(days=40), "emd_due_date": today + timedelta(days=35),
                 "ip_name": "Anil Mehta", "nature_of_assets": "Commercial plot"},
        ),
        entry(
            listing_key="d", status="collision",
            flags=["Part 6 enrichment SKIPPED this run: listing_key collides with an existing, different listing."],
            raw={"corporate_debtor": "Gamma Industries", "notice_type": "Sale Notice",
                 "reserve_price": 0, "location": "Nagpur, Maharashtra",
                 "auction_date": None, "emd_due_date": None,
                 "ip_name": "P. Singh", "nature_of_assets": "Plant and machinery"},
            enrichment=None,
        ),
        entry(
            listing_key="e", status="unchanged",
            raw={"corporate_debtor": "Nowhere Corp", "notice_type": "Sale Notice",
                 "reserve_price": None, "location": None,
                 "auction_date": "2026-01-01", "emd_due_date": None,   # ISO-string date path
                 "ip_name": None, "nature_of_assets": None},
            score={"5a": {"partial_score_5a": None}, "5b": {"partial_score_5b": 50}, "5c": {"partial_score_5c": 50}},
        ),
    ]

    cat = categorize_assembled(listings, report_date=today)
    print("counts:", cat["counts"])
    assert cat["counts"]["total"] == 5
    assert cat["counts"]["new_today"] == 1
    assert cat["counts"]["watchlist_changes"] == 1
    assert cat["counts"]["collisions"] == 1
    # b (auction in 3d) and c... c's auction is 40d out, not closing soon.
    # a's emd_due_date is 15d out -> within CLOSING_SOON_DAYS(7)? No, 15>7.
    # so only b should be closing_soon (emd_due in 1 day).
    assert [e["listing_key"] for e in cat["closing_soon"]] == ["b"], cat["closing_soon"]
    # top_scored should exclude nothing here except would exclude any None-combined
    # -- all 5 have at least one partial, e's 5a is None but 5b/5c aren't, so it's still scored.
    assert cat["counts"]["top_scored"] == 5
    # best combined score should be 'a' (88+40+50)/3 = 59.3 vs others lower -- just
    # sanity check ordering is descending.
    scores = [e["_combined_score"] for e in cat["top_scored"]]
    assert scores == sorted(scores, reverse=True)
    print("OK: categorize_assembled() offline assertions passed.")

    out = generate_report(listings, output_path="/tmp/test_part7b_smoke.pdf", report_date=today,
                           run_summary={"scrape_problems": [{"page": 3, "reason": "synthetic"}],
                                        "store_summary": {"new": 1, "unchanged": 2, "changed": 1, "collision": 1},
                                        "enrichment_summary": {"reenriched": 1, "reused": 3, "skipped_collision": 1}})
    print(f"OK: wrote {out}")
