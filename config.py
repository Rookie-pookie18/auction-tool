"""
Central config. Every threshold, weight, and setting the owner might want
to tune lives here, not buried in scraper/scoring/report logic.
Nothing in this file makes network calls or does work by itself.
"""

# ---------------------------------------------------------------------------
# Shared HTTP settings (used by every scraper)
# ---------------------------------------------------------------------------
USER_AGENT = "auction-intel-personal-tool/0.1 (personal non-commercial monitoring; low frequency)"
REQUEST_DELAY_SECONDS = 3          # pause between requests within one run
REQUEST_TIMEOUT_SECONDS = 20

# ---------------------------------------------------------------------------
# IBBI (Phase 1 source, re-ordered 2026-08-09 — was Phase 3)
# ---------------------------------------------------------------------------
IBBI_BASE_URL = "https://ibbi.gov.in"
IBBI_LISTING_PATH = "/liquidation-auction-notices/lists"  # ?page=N for page>=2

# ---------------------------------------------------------------------------
# BAANKNET (Phase 2 source — was Phase 1 before the 2026-08-09 re-baseline)
# ---------------------------------------------------------------------------
BAANKNET_BASE_URL = "https://baanknet.com"
BAANKNET_LISTING_PATH = "/eauction-psb/eproc-listing"  # land/plot search results

# BAANKNET's robots.txt disallows automated access, and its T&Cs restrict
# reuse of listed material. Decision (2026-08-07, owner-confirmed): scrape
# anyway, for personal non-commercial use only, respectfully:
#   - identify honestly via USER_AGENT above, don't spoof a browser
#   - keep REQUEST_DELAY_SECONDS matched to "once a day", not a hammering pace
#   - never redistribute or republish scraped data anywhere outside this
#     owner's own PDF/email report

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
DB_PATH = "data/auctions.db"

# ---------------------------------------------------------------------------
# Scoring (land/plot) — PLACEHOLDER WEIGHTS, not yet set by owner.
# Still-open questions from the master spec, to be filled in before Part 5
# (scoring engine) is built:
#   - budget / rate-per-unit ceiling
#   - target cities / regions
#   - minimum plot size -- decided 2026-08-09: none for now (see
#     MIN_PLOT_SIZE_SQFT below), can be revisited any time
#   - land classification preference (agricultural vs non-agricultural)
#   - how hard a litigation / possession-status red flag should penalize
# SCORE_WEIGHTS values are placeholders and MUST sum to 1.0 once real.
SCORE_WEIGHTS = {
    "price_vs_reserve": None,      # TBD
    "location_match": None,        # TBD
    "plot_size_fit": None,         # TBD
    "possession_status": None,     # TBD
    "land_classification": None,   # TBD
}

# Flexible-by-design (owner decided 2026-08-09): no hard budget ceiling
# and no exclusive region list. Nothing gets filtered out of the report
# for being "too expensive" or in the "wrong" place — these are scoring
# BONUSES that push good matches toward the top, not gates that hide
# everything else.
BUDGET_CEILING = None
# price_vs_reserve is scored RELATIVELY (e.g. discount vs reserve price,
# or percentile within the current batch) rather than against an
# absolute affordability cutoff, precisely because BUDGET_CEILING is
# None. If the owner later sets a real ceiling, scoring can switch to
# using it directly — revisit at Part 5A.

PREFERRED_REGIONS = ["Delhi", "Rajpura", "Madhya Pradesh"]
# location_match gives a bonus when a listing's `location` field matches
# one of these (substring match, case-insensitive) — it does NOT exclude
# listings from other regions. Owner explicitly wants to keep seeing
# other regions too, just with Delhi/Rajpura/MP naturally floating higher.

# ---------------------------------------------------------------------------
# Part 5A scoring internals (price_vs_reserve + location_match only).
# SCORE_WEIGHTS above stays all-None until 5B/5C are done and the owner
# picks real weights across all five criteria — these two are NOT a
# preview of that. They're just the arithmetic 5A needs on its own two
# criteria, kept in config per the project's "nothing hardcoded" rule
# rather than buried in scoring/rules.py:
#   - LOCATION_MATCH_NEUTRAL: baseline score (0-100) for a listing whose
#     location is known but doesn't match a preferred region, OR whose
#     location isn't known yet (details PDF not parsed) — same neutral
#     score either way, since "not preferred" and "not yet known" are
#     both "no bonus", never a penalty (owner: don't hide/punish other
#     regions).
#   - LOCATION_MATCH_BONUS: points added on top of the neutral baseline
#     when `location` substring-matches a PREFERRED_REGIONS entry.
# These two numbers are a reasonable default Claude picked, not something
# the owner specified — fine to tune later, doesn't block 5A.
LOCATION_MATCH_NEUTRAL = 50
LOCATION_MATCH_BONUS = 25

# ---------------------------------------------------------------------------
# Part 5B scoring internals (possession_status + land_classification).
# Decided 2026-08-09 (owner): possession_status is worth a dedicated
# scraper part parsing notice_pdf_url (the big free-text legal notice
# excluded back in Part 3C) — that's where physical/symbolic possession is
# actually disclosed; it's not reliably present in the small details PDF
# or in nature_of_assets. land_classification stays best-effort regex on
# text already scraped (nature_of_assets, falling back to the notice PDF
# text once that's fetched anyway) rather than a new dedicated fetch.
# ---------------------------------------------------------------------------

# possession_status: physical possession is well-established (see e.g. how
# SARFAESI auctions are commonly discussed) as materially less risky to a
# buyer than symbolic possession — this isn't an owner preference call the
# way PREFERRED_REGIONS is, it's close to universal buyer wisdom, so these
# are Claude-picked reasonable score values (same status as
# LOCATION_MATCH_NEUTRAL/BONUS above — fine to tune later, not a business
# decision requiring owner sign-off the way BUDGET_CEILING/PREFERRED_REGIONS
# were).
POSSESSION_STATUS_SCORES = {
    "physical": 100,
    "symbolic": 40,
    "unknown": 50,   # not found / notice PDF unparseable — neutral, never a penalty
}

# land_classification (agricultural / non-agricultural / industrial /
# residential / commercial) has no inherent "better" direction — the master
# spec explicitly still lists "land classification preference" as an open
# question. Same pattern as PREFERRED_REGIONS in 5A: empty by default means
# every classification (including "unknown") scores the same neutral
# baseline, no bonus, nothing hidden or excluded. Owner can fill this in
# later once there's an actual preference to encode.
PREFERRED_LAND_CLASSIFICATIONS = []   # e.g. ["non-agricultural", "industrial"]
LAND_CLASSIFICATION_NEUTRAL = 50
LAND_CLASSIFICATION_BONUS = 25

# ---------------------------------------------------------------------------
# Part 5C scoring internals (plot_size_fit).
# Owner decision (2026-08-09): no minimum plot size right now. Same
# flexible-by-design pattern as BUDGET_CEILING (5A) and PREFERRED_REGIONS/
# PREFERRED_LAND_CLASSIFICATIONS (5A/5B): None means no filter/threshold
# is applied and nothing is scored down for being "too small" -- every
# listing stays at the neutral baseline, its resolved plot size (once
# cleanly parseable) is just shown for the owner's own judgment call.
# Expressed in sq ft (canonical unit) since raw mentions come in a mix of
# sq ft/sq mtrs/acres/hectares/guntas/cents -- scoring/rules.py converts
# all of them to sq ft before comparing against this.
# ---------------------------------------------------------------------------
MIN_PLOT_SIZE_SQFT = None
PLOT_SIZE_NEUTRAL = 50
PLOT_SIZE_BONUS = 25
# plot_size_fit: neutral baseline for every listing while MIN_PLOT_SIZE_SQFT
# is None (informational only, not yet a real filter). Once the owner sets
# a real minimum, listings whose resolved plot_size_sqft meets/exceeds it
# get the bonus on top -- below-minimum or unparseable listings stay at
# the neutral baseline rather than being penalized, same "bonus not
# filter, never punish missing/undecided data" pattern used everywhere
# else in this scoring model.

# ---------------------------------------------------------------------------
# Part 6A: AI narrative write-up (ai_analysis/gemini_narrative.py).
# Owner decision (2026-08-09): Gemini over Groq. Free tier, no card,
# genuinely usable at this project's volume (a few dozen listings/day).
#
# GEMINI_API_KEY is read from the environment (or a local .env file, never
# committed -- .gitignore already excludes .env) rather than hardcoded here,
# same "secrets never live in tracked files" pattern the SMTP settings below
# will follow at Part 8A. Get a free key at https://aistudio.google.com/apikey
# (Google account, no credit card).
#
# GEMINI_MODEL / rate-limit numbers below are Claude's picks (not owner-
# specified, flagged per project convention). Originally set to
# gemini-2.5-flash (2026-08-09 web check at the time) -- corrected same
# day after the owner's real first run came back with a live HTTP 404
# ("This model models/gemini-2.5-flash is no longer available to new
# users"): Google has been retiring 2.5-series models for new API keys
# ahead of their official Oct 16 2026 shutdown date (confirmed as a
# widely-reported issue on Google's own developer forum, not specific to
# this key). gemini-3.5-flash is the current recommended free-tier text
# model (confirmed on Google's own pricing page as of mid-July 2026;
# gemini-3.1-flash-lite is the other free option if higher throughput is
# ever needed). Free tier for 3.5 Flash is commonly reported around
# 15 requests/minute, ~1,500/day -- comfortably enough for a once-a-day
# run over this project's listing volume.
# GEMINI_REQUEST_DELAY_SECONDS=5 stays safely under the per-minute cap;
# bump it down only if the owner's real key shows a higher limit.
# Endpoint uses the legacy-but-fully-supported generateContent call (not
# the newer Interactions API) since it's the simplest fit for one-shot
# narrative generation, no multi-turn/agentic behavior needed.
# ---------------------------------------------------------------------------
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional -- GEMINI_API_KEY can also be set
          # directly in the shell environment without it.

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-3.5-flash"
GEMINI_API_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
GEMINI_REQUEST_TIMEOUT_SECONDS = 30
GEMINI_REQUEST_DELAY_SECONDS = 5   # pause between narrative calls within one run
GEMINI_RETRY_BACKOFF_SECONDS = 15  # one retry, on 429/5xx only, after this pause


# ---------------------------------------------------------------------------
# Part 6B: MCA company master-data lookup (ai_analysis/mca_lookup.py).
# Free government source (per PROJECT_STATUS.md Section 2, background-check
# depth item 2): data.gov.in's "Registrars of Companies (RoC)-wise Company
# Master Data" resource -- an Open Government Data (OGD) mirror of MCA's
# own registry, published by the Ministry of Corporate Affairs itself.
# mca.gov.in's own live portal search requires solving a CAPTCHA per
# lookup, which this project won't automate around (same spirit as the
# BAANKNET robots.txt call -- scrape respectfully, don't defeat active
# anti-bot measures); data.gov.in's OGD mirror is the legitimate free
# alternative.
#
# DESIGN (this is the SECOND version of this section -- see
# PROJECT_STATUS.md decisions (17)-(21) for the full story of how this was
# figured out): this module does NOT call data.gov.in live per lookup
# anymore. Real testing 2026-08-09 showed the REST API
# (api.data.gov.in/resource/...) consistently failing -- every query (2
# different states, with/without a CIN filter) timed out after ~60s with
# an empty HTTP 502. The cause, confirmed by testing the SAME resource
# through data.gov.in's own website: even their own "Preview & Download"
# button doesn't return data instantly for this resource -- it asks for a
# download purpose, warns it "may take time," and creates a background job
# (My Account -> Download History). This dataset is a BULK EXPORT
# resource, not a real-time lookup API -- data.gov.in's own UI doesn't
# serve it live either. So instead of querying it live, the owner
# downloads each state's CSV ONCE via that same website job (manual, no
# way found to automate triggering/polling that job without a browser
# session) and this module reads the local file. This also fits the data
# better anyway: see the staleness note below -- it's a static extract,
# not something that benefits from being queried live.
#
# MCA_LOCAL_DATA_DIR: where this module looks for per-state CSV files, one
# per state that's actually needed (not all of India up front -- add
# states incrementally as new CINs turn up needing them). Expected
# filename per state: lowercase state name, spaces -> underscores, e.g.
# "delhi.csv", "madhya_pradesh.csv" -- see
# ai_analysis/mca_lookup.py's expected_csv_path_for_state() for the exact
# rule, and README.md's Part 6B section for the click-path to get each
# file from data.gov.in (Data tab -> pick a state -> Preview & Download ->
# fill in a purpose -> wait for My Account -> Download History to show
# "Completed" -> download -> save at this path). A missing state's file is
# just another best-effort "flag, don't block" case, same as everything
# else in this module -- nothing needs to be downloaded up front for the
# code itself to be correct/testable.
#
# NOTE from the resource's own "Note" field: figures are in INR, and "the
# data upto 3rd November 2023" -- despite an "Updated On" date far more
# recent than that, the underlying company records only reflect the state
# of things as of Nov 2023. Enrichment from this module can be a couple of
# years stale; it's still the best free option available, and downloading
# once and reusing indefinitely (until the owner chooses to refresh a
# file) matches what this data actually is.
MCA_LOCAL_DATA_DIR = "data/mca_company_master"

# Historical note: the earlier live-API version of this section had
# MCA_DATA_GOV_API_KEY, MCA_DATA_GOV_RESOURCE_ID, MCA_DATA_GOV_TIMEOUT_
# SECONDS, MCA_DATA_GOV_REQUEST_DELAY_SECONDS, and MCA_DATA_GOV_CIN_FIELD_
# NAME here. None of those are used by the current local-file design --
# removed rather than left as dead config, per this project's own "nothing
# hardcoded / no unused cruft" spirit. The resource_id
# (4dbe5667-7b6b-41d7-82af-211562424d9a) and the real column name
# (CORPORATE_IDENTIFICATION_NUMBER) they recorded are still correct and
# still relevant -- they now live in ai_analysis/mca_lookup.py itself
# (CIN_COLUMN_NAME, and the resource name/ID are referenced in this
# module's docstring for anyone re-downloading a state's file).
#
# Lookup is keyed on CIN only (never on corporate_debtor name alone) -- a
# name-only search over ~3M+ companies risks matching the wrong company
# silently, which this project's "never guess, always flag" rule doesn't
# allow. CIN is already extracted for most listings by Part 3C's details-PDF
# parse; listings without a parsed CIN are flagged "skipped, no CIN" rather
# than attempting a name match.
#
# UPDATE (2026-08-10, same checkpoint as Part 6C): ai_analysis/mca_lookup.py
# now matches a downloaded CSV's column headers case-insensitively against a
# short list of plausible variants, not just the live API's exact field
# names -- see that module's docstring, "HEADER-MATCHING ROBUSTNESS", for
# why (a bulk CSV export commonly doesn't share exact header formatting with
# the same platform's JSON API). No config changes needed for this; it's
# purely internal to mca_lookup.py's CSV parsing.

# ---------------------------------------------------------------------------
# Part 6C: unofficial web-search news pass (ai_analysis/news_search.py).
# Per PROJECT_STATUS.md Section 2, background-check depth item 2: "an
# unofficial free web-search pass (e.g. DuckDuckGo HTML scrape, no key)
# for recent news -- fragile, ToS-grey, best-effort only, never trusted
# blindly, always labeled 'unverified' in the output if used."
#
# WHY DUCKDUCKGO'S HTML ENDPOINT (html.duckduckgo.com/html/): no API key,
# no paid tier, no CAPTCHA on plain server-rendered results (confirmed by
# it being the standard free-scrape target used across many open-source
# no-key search wrappers) -- fits the project's "$0" rule the same way
# IBBI/data.gov.in do. Google/Bing have no comparably scrapeable free
# path (both either require a paid API or actively block scraping much
# harder than DDG's HTML endpoint does) -- not evaluated further than
# that for a v1 best-effort layer.
#
# ToS-GREY, FLAGGED HONESTLY (not glossed over): scraping DuckDuckGo's
# HTML results page for automated use sits in the same grey zone as the
# BAANKNET decision (2026-08-07) -- no robots.txt block encountered on
# html.duckduckgo.com's own /html/ path as of this writing, but their
# general ToS discourages automated querying. Same mitigation approach
# as BAANKNET: honest USER_AGENT (shared config.USER_AGENT above, not a
# spoofed browser string), NEWS_SEARCH_REQUEST_DELAY_SECONDS below kept
# to a once-a-day-batch pace, results never redistributed/republished
# anywhere outside the owner's own PDF/email report, and low volume (one
# query per listing per day, not per-listing-per-refresh).
#
# WHAT THIS ADDS: for each listing, a small number of recent news
# headline+snippet+url results for the corporate_debtor's name (plus
# location, when known, to reduce false-positive matches against
# common company names) -- raw search results only, no AI
# summarization/claims layer on top (that risk lives one level up, if
# ever added: 6C's job is just to surface links, not to assert what
# they mean). Every result carries "unverified web search result, not
# fact-checked" in the flag/label the report ultimately shows, per
# Section 2's "never claims research depth it didn't actually get" rule.
#
# FAILURE HANDLING (same pattern as 6A/6B): no corporate_debtor name, a
# blocked/empty/malformed response, a network error, or zero results --
# none of these ever block the batch. news_data stays None plus a
# human-readable flag, same shape as mca_data/mca_lookup_attempted.
# ---------------------------------------------------------------------------
NEWS_SEARCH_ENABLED = True   # owner can flip off entirely, no code change needed
NEWS_SEARCH_URL = "https://html.duckduckgo.com/html/"
NEWS_SEARCH_MAX_RESULTS = 3       # per listing -- small on purpose, best-effort only
NEWS_SEARCH_TIMEOUT_SECONDS = 20
NEWS_SEARCH_REQUEST_DELAY_SECONDS = 5   # pause between DIFFERENT listings in a batch
NEWS_SEARCH_TIER_DELAY_SECONDS = 2   # pause between fallback-query tiers for the
                                      # SAME listing (added 2026-08-10, see
                                      # news_search.py's "MATCHING STRATEGY" --
                                      # shorter than the between-listing delay
                                      # since this is one logical search, just
                                      # tried a few different ways)

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
CLOSING_SOON_DAYS = 7   # a listing counts as "closing soon" inside this window
REPORT_OUTPUT_DIR = "data/reports"

# ---------------------------------------------------------------------------
# Email delivery — placeholders, filled in at Part 7. Free (e.g. Gmail SMTP
# with an app password) — no paid email API.
# ---------------------------------------------------------------------------
EMAIL_FROM = None      # TBD
EMAIL_TO = None        # TBD
SMTP_HOST = None       # TBD
SMTP_PORT = 587
