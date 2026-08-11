# Auction Intelligence Tool

Personal automation: scrapes auction/insolvency listing sites daily, tracks
new/changed listings, scores land/plot listings against owner-set rules
(no LLM in the pipeline), builds a PDF report, and emails it. Free tools
only, end to end.

## Status
Scaffold only — see `PROJECT_STATUS.md` for the real roadmap and current
part. Nothing here runs yet.

## Setup (once there's code to run)
```
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## AI narrative layer (Part 6A) — free Gemini API key
The AI write-up per listing (separate from and in addition to the rule-based
score) calls Google's Gemini API, free tier, no credit card:
1. Get a key: https://aistudio.google.com/apikey
2. Copy `.env.example` to `.env` and paste your key in as `GEMINI_API_KEY=...`
   (`.env` is gitignored — never commit the real key).

## Company background lookup (Part 6B) — free MCA data via data.gov.in
Best-effort company master-data enrichment (status, category, registration
date, capital, registered address) by CIN — never blocks the report if it
fails or finds nothing. **This reads locally downloaded CSV files, not a
live API** — real testing found this dataset is a bulk-export/batch-job
resource on data.gov.in's end (even their own website UI can't serve it
instantly), so this project downloads each state's data once instead of
querying it live. To add a state:
1. Go to https://data.gov.in/catalogs and open "Registrars of Companies
   (RoC)-wise Company Master Data" (Ministry of Corporate Affairs).
2. On the **Data** tab, pick a state from the "Company State Code"
   dropdown, then click **Preview & Download**. Fill in a purpose when
   asked, and submit.
3. Go to your data.gov.in profile → **My Account** → **Download
   History**. Your request will show "In progress," then eventually
   "Completed" (this can take a while for large states — the site itself
   warns about this). Once completed, click its Download Link.
4. Save the downloaded file as
   `data/mca_company_master/<state_name>.csv`, where `<state_name>` is
   the state's lowercase name with spaces replaced by underscores — e.g.
   Delhi → `data/mca_company_master/delhi.csv`, Madhya Pradesh →
   `data/mca_company_master/madhya_pradesh.csv`. (Run
   `python -c "from ai_analysis.mca_lookup import expected_csv_path_for_state as f; print(f('madhya pradesh'))"`
   from the project root if you want to double-check the exact filename
   this project expects for any state.)
5. That's it for that state — no API key, no repeating this per listing.
   `ai_analysis/mca_lookup.py` derives which state a listing's CIN needs
   automatically and reads the matching file. A listing whose state's
   file hasn't been downloaded yet just gets a clean flag, same as any
   other best-effort enrichment gap in this project.

Note the underlying data only covers company records up to 3 Nov 2023,
per the resource's own published note — a couple of years stale, but
still the best free option available, and this project only needs to
download each state once regardless.

See `config.py`'s Part 6B comment and `test_part6b.py` for the full
reasoning and a real confirmation run.

## Unofficial news search (Part 6C) — free, no key
Best-effort recent-news lookup per listing (by `corporate_debtor` name),
via DuckDuckGo's free HTML results endpoint — no signup, no key needed.
Tries up to 4 progressively broader queries per listing before giving up
(quoted name + location + topic filter → quoted name + location → quoted
name alone → bare unquoted name), stopping at the first real hit; a
result found only on a broadened tier is flagged as such, not presented
identically to a tier-1 hit. Every result is a raw, unverified search
hit, never fact-checked; never blocks the report if it fails or finds
nothing — some companies genuinely have no indexed coverage, and this
module will never fake a match to force a hit. Set
`NEWS_SEARCH_ENABLED = False` in `config.py` to turn it off entirely.
See `config.py`'s Part 6C comment and `test_part6c.py` for the full
reasoning — confirmed on a real run (5/5 on-topic hits across the
4-tier chain, quality-checked via cross-matching CINs across sources).

## A note on BAANKNET (Phase 1 source)
BAANKNET's `robots.txt` disallows automated access, and its Terms &
Conditions contain broad restrictive language about reusing listed
material. Owner's decision (2026-08-07): scrape anyway for personal,
non-commercial, once-a-day use, done respectfully — see `config.py` for
the honest user-agent string and the rate limit that encodes this. Never
redistribute or republish scraped data outside this owner's own report.

## Folder layout
```
scraper/     one module per source (baanknet.py first)
storage/     SQLite storage, dedup + new/changed detection
scoring/     rule-based scoring, weights live in config.py, not here
report/      PDF generation
email_delivery/  SMTP send (named to avoid shadowing Python's stdlib email package)
data/        gitignored — sqlite db + generated reports land here
```
