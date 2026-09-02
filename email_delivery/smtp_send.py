"""
email_delivery/smtp_send.py — Part 8A: emailing the finished PDF report.

--------------------------------------------------------------------------
SCOPE: this module does exactly one job -- take a PDF path (Part 7B's
generate_report() output) plus a run summary, build a plain-text email
around it, and send it via Gmail SMTP with an app password (Section 2's
"free (e.g. Gmail app password)" call). It does not run the pipeline or
build the PDF itself -- see run_and_send() in this file for the thin
glue, but scrape/store/score/enrich/render all stay pipeline.py's and
report/pdf.py's jobs, unchanged.

--------------------------------------------------------------------------
CREDENTIALS -- same "secrets never live in tracked files" pattern as
config.GEMINI_API_KEY (Part 6A): SMTP_PASSWORD (the Gmail App Password,
NOT the owner's normal Gmail password -- Gmail requires 2-Step
Verification turned on first, then a 16-character App Password generated
at https://myaccount.google.com/apppasswords) is read from the
environment / local .env file only, via config.SMTP_PASSWORD. It is
never hardcoded here and .gitignore already excludes .env (same file
Part 6A's GEMINI_API_KEY already relies on -- no new .gitignore entry
needed for this part).

config.EMAIL_FROM / config.EMAIL_TO / config.SMTP_HOST are still TBD
(None) as of this writing -- the owner fills these in locally
(EMAIL_FROM is the Gmail address the App Password belongs to; EMAIL_TO
can be the same address or a different inbox the owner actually reads
every morning; SMTP_HOST defaults to "smtp.gmail.com" once Gmail is
confirmed as the provider, matching Section 2's "free SMTP (Gmail app
password)" decision). send_report_email() below raises a clear,
human-readable error (never a bare smtplib traceback) if any of the
four required settings (EMAIL_FROM/EMAIL_TO/SMTP_HOST/SMTP_PASSWORD)
are still None/missing when called -- same "never guess, always flag"
posture as the rest of this project, just surfaced as a hard error here
since a misconfigured send is a full-stop problem, not a per-listing
one to flag-and-continue past.

--------------------------------------------------------------------------
FAILURE HANDLING -- deliberately DIFFERENT from Parts 6A/6B/6C: those
are per-listing, best-effort, "flag and continue" because one bad
listing must never sink the whole report. Email delivery is the last
step of the whole run and there is nothing after it to protect -- so
send_report_email() does NOT swallow errors. A real SMTP failure
(auth error, connection refused, etc.) raises, so a broken send is
loud (visible in GitHub Actions logs at Part 8B, not silently "sent"
when it wasn't). This matches this project's "never overstate what
happened" rule from the opposite direction: Parts 6A-6C under-claim
failure by design (flag, don't crash the batch); this part must NOT
under-claim a failed send.

--------------------------------------------------------------------------
CONTENT: plain-text body only (a short run summary -- new/changed/
unchanged counts, top-scored count, any scrape/enrichment problems) plus
the PDF as the one attachment. No HTML email body -- the PDF is already
the real report; the email body is just enough to see date freshness on
a phone
notification without opening the attachment. Subject line includes the
report date so an inbox full of daily emails stays sortable at a glance.
"""

import os
import smtplib
from datetime import date
from email.message import EmailMessage

import config


def _require_email_config() -> None:
    """
    Raises a clear, human-readable RuntimeError (never a bare smtplib/
    attribute error) if any required setting is still missing -- checked
    up front rather than letting smtplib fail confusingly halfway through
    a connect/login/send sequence.
    """
    missing = []
    if not config.EMAIL_FROM:
        missing.append("config.EMAIL_FROM")
    if not config.EMAIL_TO:
        missing.append("config.EMAIL_TO")
    if not config.SMTP_HOST:
        missing.append("config.SMTP_HOST")
    if not config.SMTP_PASSWORD:
        missing.append("config.SMTP_PASSWORD (set SMTP_APP_PASSWORD in your "
                        ".env or shell environment -- a Gmail App Password, "
                        "not your normal Gmail password)")
    if missing:
        raise RuntimeError(
            "email_delivery.smtp_send: cannot send -- missing required "
            "setting(s): " + ", ".join(missing) + ". Fill these in locally "
            "(config.py for EMAIL_FROM/EMAIL_TO/SMTP_HOST, .env for the App "
            "Password) before running send_report_email()."
        )


def build_summary_text(run_summary: dict, categorized_counts: dict, report_date: date) -> str:
    """
    Plain-text email body. Takes run_pipeline()'s own summary dict
    (store_summary/enrichment_summary/scrape_problems -- see
    pipeline.py's run_pipeline() docstring for the exact shape) plus a
    small dict of per-section counts from the categorized report
    (top_scored/closing_soon/new_today/watchlist_changes/collisions --
    caller computes these from categorize_assembled()'s own output,
    this function doesn't recompute categorization itself).
    """
    store = run_summary.get("store_summary", {}) if run_summary else {}
    enrich = run_summary.get("enrichment_summary", {}) if run_summary else {}
    problems = run_summary.get("scrape_problems", []) if run_summary else []

    lines = [
        f"Auction Intelligence Daily Report -- {report_date.isoformat()}",
        "",
        "Full report is attached as a PDF.",
        "",
        "This run:",
        f"  New listings:        {store.get('new', '?')}",
        f"  Changed listings:    {store.get('changed', '?')}",
        f"  Unchanged listings:  {store.get('unchanged', '?')}",
        f"  Collisions:          {store.get('collision', '?')}",
        "",
        "AI enrichment:",
        f"  Freshly enriched:    {enrich.get('reenriched', '?')}",
        f"  Reused from before:  {enrich.get('reused', '?')}",
        f"  Skipped (collision): {enrich.get('skipped_collision', '?')}",
        "",
        "Report sections:",
        f"  Top-scored:          {categorized_counts.get('top_scored', '?')}",
        f"  Closing soon:        {categorized_counts.get('closing_soon', '?')}",
        f"  New today:           {categorized_counts.get('new_today', '?')}",
        f"  Watchlist changes:   {categorized_counts.get('watchlist_changes', '?')}",
        f"  Flagged for review:  {categorized_counts.get('collisions', '?')}",
    ]
    if problems:
        lines += ["", f"Scrape problems this run ({len(problems)}):"]
        # Cap how many raw problem lines land in the email body itself --
        # the point of this section is "something needs a look", not a
        # full dump; full detail (if any exists beyond these strings) is
        # what the PDF/logs are for. Claude-picked cap, flagged not
        # owner-specified, same status as REPORT_TOP_N etc.
        for p in problems[:10]:
            lines.append(f"  - {p}")
        if len(problems) > 10:
            lines.append(f"  ... and {len(problems) - 10} more (see run logs).")
    else:
        lines += ["", "No scrape problems this run."]

    return "\n".join(lines)


def send_report_email(
    pdf_path: str,
    run_summary: dict,
    categorized_counts: dict,
    report_date: date = None,
) -> None:
    """
    Sends the report email with `pdf_path` attached. Raises on any real
    failure (missing config, auth error, connection error, missing PDF
    file) -- see module docstring "FAILURE HANDLING" for why this part
    does not flag-and-continue the way Parts 6A/6B/6C do.
    """
    _require_email_config()

    if not os.path.isfile(pdf_path):
        raise RuntimeError(
            f"email_delivery.smtp_send: PDF not found at {pdf_path!r} -- "
            "was generate_report() actually run before this call?"
        )

    if report_date is None:
        report_date = date.today()

    subject = f"{config.EMAIL_SUBJECT_PREFIX} {report_date.isoformat()}"
    body = build_summary_text(run_summary, categorized_counts, report_date)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.EMAIL_FROM
    msg["To"] = config.EMAIL_TO
    if config.EMAIL_CC:
        # Optional -- if unset, no Cc header is added and this is a plain
        # single-recipient send exactly as before. smtplib's
        # server.send_message() below reads To+Cc (+Bcc) headers together
        # to build the actual RCPT TO envelope, so setting this header is
        # the whole fix -- no separate recipient list needed.
        msg["Cc"] = config.EMAIL_CC
    msg.set_content(body)

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    msg.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=os.path.basename(pdf_path),
    )

    # STARTTLS on 587 (Gmail's standard submission port) -- not implicit
    # TLS on 465 -- matches Google's own documented app-password setup
    # instructions. config.SMTP_PORT already defaults to 587 (set at
    # Part 7, unchanged here).
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=config.SMTP_TIMEOUT_SECONDS) as server:
        server.starttls()
        server.login(config.EMAIL_FROM, config.SMTP_PASSWORD)
        server.send_message(msg)


if __name__ == "__main__":
    # -----------------------------------------------------------------
    # test_part8a.py (real-network confirmation, matching the
    # test_part6a/b/c.py convention) is the actual confirmation script
    # for this part -- see that file. This __main__ block is intentionally
    # NOT where the real send test lives, since this project's convention
    # (Section 0 rule 4 / every prior test_part*.py) keeps the real
    # small-batch confirmation in its own top-level test_partN.py file,
    # not buried in the module's own __main__.
    print("email_delivery/smtp_send.py has no offline-only self-test -- "
          "sending mail always needs real network + real credentials, so "
          "there's nothing meaningful to smoke-test without them. "
          "Run test_part8a.py instead (needs EMAIL_FROM/EMAIL_TO/SMTP_HOST "
          "in config.py and SMTP_APP_PASSWORD set locally).")
