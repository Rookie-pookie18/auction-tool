# PROJECT STATUS — Auction Intelligence Tool

> ## ⚠️ IF YOU ARE STARTING A NEW CHAT (new account, token limit hit,
> ## anything) — READ THIS FIRST
>
> **Do this, exactly:**
> 1. Attach **the project zip file itself** to the new chat — the actual
>    `.zip` you downloaded, e.g. `auction-tool-part6b.zip`. **Do NOT**
>    attach chat screenshots, do NOT paste in a chat transcript, do NOT
>    try to summarize verbally what happened. **Screenshots of a
>    conversation do not contain the real code or config** — a new AI
>    reading screenshots only sees prose *describing* the project, never
>    the actual files, and will get it wrong or get confused, even with a
>    lot of screenshots. The zip is the only thing that has ground truth.
> 2. First message, copy-paste exactly this:
>    > Read PROJECT_STATUS.md inside this zip, especially Section 4
>    > ("Last updated"), then continue from exactly where it says the
>    > project left off.
> 3. **After every single reply that changes code — not just at the end
>    of a session — ask: "send updated zip."** Save that zip, overwriting
>    your previous one. That zip is your ONE save file. If you're ever
>    unsure whether to ask for a fresh zip, ask for it.
> 4. If a session gets cut off (token limit, crash, anything) before you
>    got a final zip for the last change discussed — just start the next
>    session with your last saved zip and describe in one sentence what
>    was being worked on when it cut off. Section 4 below will have the
>    last *confirmed-saved* state; anything discussed after that zip was
>    made is what you need to redo or re-describe.

---

> **How to use this file:** This file now lives *inside* the project zip
> (at the repo root) — **attach only the zip to a new chat**, nothing
> else needed. First message: "Read PROJECT_STATUS.md inside this zip,
> continue with Part X." **After each part — not just at the end of a
> session — ask for one updated zip** (code + this file, both inside it),
> and save that as your new working copy. Only one file to keep track of
> from now on.

---

## 0. Handoff protocol

Built across many separate AI sessions (different accounts, hard free-tier
usage limits, sessions can cut off anywhere). Rules:

1. **A checkpoint is one part, not one phase.** Zip after every part —
   don't wait for the whole phase to be done.
2. **Network access is split in two — don't confuse them:**
   - The **code-running sandbox** (where files/zips get built) has NO
     network access, ever (confirmed 2026-08-07, permanent).
   - The **assistant's own browsing tools** (web search / fetch a URL) DO
     have live internet access and were used directly on 2026-08-09 to
     read IBBI's site with no owner upload needed. **Only ask the owner
     to save/upload an HTML file when a site is JS-heavy/infinite-scroll
     and you need the post-render DOM** (e.g. BAANKNET). For plain
     server-rendered sites (e.g. IBBI's tables), just fetch the URL
     directly — don't ask the owner unnecessarily.
3. **Zip proactively.** Don't hold a zip back "for when it's more
   complete." A scaffold-only zip is still a real checkpoint.
4. **If a part is still too big to finish + test in one response, split
   it further** (e.g. 3A becomes 3A-i / 3A-ii) rather than delivering
   incomplete or untested code — same rule as the owner's other two
   projects.
5. **This file is FORMAT-LOCKED. Cap: ~250 lines while still planning-only
   (current stage) — expect to raise this toward ~500-550 once real build
   history/decision-log entries accumulate (that's where the owner's
   other two projects settled).** Normally you may
   ONLY: tick `[ ]` → `[x]` in Section 3 with a one-line result (max ~20
   words); add ONE bullet to "Known open issues"; overwrite Section 4
   using its fixed template. **Exception:** the owner can explicitly
   authorize a full re-baseline (structure/phase-order/scope changes) —
   this happened once, 2026-08-09 (see decisions below). Outside an
   explicit owner request like that, stick to the normal edit-only rules.

---

## 1. What this project is

A personal automation tool replacing the owner's daily manual routine of
checking auction/insolvency listing sites. Scrapes listings, tracks
new/changed day over day, scores land/plot listings against the owner's
own rules, writes an AI-generated analysis per listing, builds a PDF
report, and **emails it automatically every morning — this is a
must-have of v1, not a later add-on.** Primary focus: land/plots (deep
scoring + AI write-up). Secondary: light sweep of
residential/commercial/NCLT-IBC (new + closing-soon only, no deep
scoring).

**What "done" looks like day-to-day for the owner:** instead of manually
checking 4-5 auction sites, open one email each morning with a PDF that
already contains, per interesting listing: what it is, is the price fair,
what's the company/borrower's situation, and every raw detail — the same
judgment call the owner would make by hand, done for them.

---

## 2. Architecture & stack (decided — don't deviate without reason)

**Stack:** Python 3. `requests` + `BeautifulSoup4`/`lxml` for
plain-HTML sources (IBBI). Switch a given source to Playwright only if
confirmed JS-rendered (BAANKNET). `sqlite3` (stdlib) for storage.
`reportlab` for PDF. `smtplib`/`email` (stdlib) for delivery — free SMTP
(Gmail app password). GitHub Actions cron for scheduling — **built and
wired in as soon as a report can be generated, not deferred to the end.**

**AI analysis layer (new, decided 2026-08-09):** a per-listing narrative
write-up (company background, fair-price read, plain-English summary) —
separate from and in addition to the deterministic rule-based score, never
replacing it. LLM call must be genuinely free — **Google Gemini API free
tier or Groq free tier** (both: real API key, no card, generous daily
quota, good enough quality) — owner to sign up and supply the key in
local config, never committed. Anthropic's API was considered but isn't
free at any real volume, so it's out per the owner's explicit "$0" call.

Background-check depth (owner decided 2026-08-09: "max output, $0"):
1. **Primary, always-on, free:** LLM reasons over everything already
   scraped (asset description, legal action type, price, dates,
   borrower/bank) — genuinely unlimited, zero extra cost.
2. **Best-effort enrichment, free, may fail silently-safe (flag, don't
   block):** MCA (Ministry of Corporate Affairs) company master data
   lookup by name/CIN where available — free government lookup, basic
   incorporation/status info only. Plus an unofficial free web-search
   pass (e.g. DuckDuckGo HTML scrape, no key) for recent news — fragile,
   ToS-grey, best-effort only, never trusted blindly, always labeled
   "unverified" in the output if used.
Never claims research depth it didn't actually get — if enrichment fails,
say so in the PDF rather than guessing.

**Folder shape:**
```
auction-tool/
  config.py         # every threshold/weight/setting — nothing hardcoded elsewhere
  scraper/          # one module per source
  storage/          # SQLite, dedup + new/changed detection
  scoring/          # rule-based scoring, reads weights from config.py
  ai_analysis/       # NEW — LLM narrative write-up per listing, free-tier API
  report/           # PDF generation
  email_delivery/   # SMTP send (not named `email` — would shadow stdlib)
  data/             # gitignored — db + generated reports
```

**Conventions:** nothing hardcoded (`config.py`); never silently drop a
flagged listing/missing field/failed enrichment — always surface it;
free tools only end to end, **including the AI layer** — ask before
introducing anything paid; one source fully working end-to-end before
starting the next.

---

## 3. Roadmap — Phase 1: IBBI (re-ordered 2026-08-09, was Phase 3)

**Why IBBI first (owner-approved 2026-08-09):** its listings page is a
plain server-rendered HTML table — no JS rendering, normal `?page=N`
pagination — confirmed by direct fetch on 2026-08-09. Reserve Price and
EMD due date are already in the table. Much less scraping risk than
BAANKNET, so it's the faster real win. BAANKNET (field map already done,
reusable) becomes Phase 2. Auction Tiger / eAuctionsIndia / BankEAuctions
/ BankAuctions.in / IBAPI found via search 2026-08-09, not yet scoped —
Phase 3+, one at a time, robots.txt/ToS check each before building.

- [x] **Part 1 — Repo scaffold** — DONE (2026-08-07). Generic folder
      layout, not source-specific — still valid as-is. `ai_analysis/`
      folder added 2026-08-09, still empty.
- [x] **Part 2 — Source structure confirmed** — DONE (2026-08-09) via
      direct fetch, no owner upload needed (see Section 0 rule 2). Table
      fields confirmed: Type of AN, Date, Corporate Debtor, Auction Date,
      IP name, Reserve Price, Nature of Assets (free text), EMD due date,
      links to notice PDF + details PDF. **Not in the table:** EMD
      amount, exact location, plot area, auction round — likely inside
      the linked PDF notices only. Pagination via `?page=N`, ~9,667
      records / ~484 pages as of 2026-08-09.
- [x] **Part 3 — Scraper module (`scraper/ibbi.py`)** — DONE (2026-08-09),
      all three sub-parts confirmed on real runs.
  - [x] 3A — parse the table into structured records — DONE (2026-08-09),
        confirmed on real live fetch: 20/20 parsed, 0 flags.
  - [x] 3B — pagination across all pages — DONE (2026-08-09), confirmed
        on real re-run: 54 unique/60 raw, 6 dupes dropped, 0 other issues.
  - [x] 3C — details-PDF parsing — DONE (2026-08-09), confirmed on a real
        re-run after the __main__ fix: 3/3 real details PDFs fetched and
        parsed (cin/emd_amount/location/platform all populated), 0 fetch
        errors, only flag was the expected "no area figure found" on
        going-concern-style listings with no size in the text
- [x] **Part 4 — SQLite storage** — DONE (2026-08-09), confirmed on a real
      run: 20 real IBBI listings, first run 20/20 `new`, immediate re-run
      20/20 `unchanged`, 0 collisions, 0 problems.
- [x] **Part 5 — Rule-based scoring** — DONE (2026-08-09). Split into
      5A/5B/5C per Section 0 rule 4 (see below); all three now confirmed
      on real runs. `config.SCORE_WEIGHTS` itself is still all `None` —
      no owner-set weights yet to combine the five criteria into one
      final ranking (that's Part 7's job, once real weights exist);
      until then each part exposes its own `partial_score_5x`.
  - [x] **5A — Scorable-now criteria** — DONE (2026-08-09), confirmed on
        a real run: 20/20 scraped+scored, reserve_price=0 correctly
        excluded (not scored as "cheapest") after a same-session fix.
  - [x] **5B — Possession status & land classification** — DONE
        (2026-08-09), confirmed on a real full-batch run: 0/20
        possession_status, 8/20 land_classification, 5/20 scanned/
        unextractable notice PDFs — code works correctly, finding is
        real (IBBI liquidation notices don't use SARFAESI possession
        wording), kept in score model as-is since it's harmless neutral
        and pays off on BAANKNET later. See Known open issues.
  - [x] **5C — Plot size fit** — DONE (2026-08-09), confirmed on a real
        run: 3/20 listings had a raw area mention at all, 1/20 resolved
        to a single clean plot_size_sqft (unit conversion hand-verified
        correct: 48,859 sq. meters -> 525,913.4 sq ft), 2/20 correctly
        flagged ambiguous (genuinely different area figures, not
        guessed), 17/20 had no area mention. Duplicate-mention collapse
        also confirmed working on real data (HANDUM: two identical
        "31.82 Guntas" mentions did not trigger a false ambiguous flag
        on their own — only the genuinely different "17.93 Guntas"
        mention did). All of Part 5 (5A/5B/5C) is now done.
- [ ] **Part 6 — AI analysis module (`ai_analysis/`)** — split per Section
      0 rule 4: three separate integrations, each with its own failure
      modes, per Section 2's background-check plan.
  - [x] **6A — LLM narrative call** — DONE (2026-08-09). Real run: 4/5
        real narratives back from Gemini, grounded and honest; 1/5
        malformed-JSON failure fixed with a retry. Re-confirmed
        2026-08-10 with `GEMINI_API_KEY` set via a real local `.env`
        file (not just a shell env var): 5/5 real, well-grounded
        narratives, no regressions from the `.env`/dotenv loading path.
  - [x] **6B — MCA company-lookup enrichment** — FULLY CONFIRMED
        2026-08-10, both halves now done. Local-file-lookup half: against
        5 real downloaded state CSVs (delhi, goa, madhya_pradesh, punjab,
        sikkim); real header row inspected directly (not guessed); 4
        genuine `_FIELD_VARIANTS` gaps found and fixed (`sub_category`,
        `date_of_registration`, `registered_state`,
        `registrar_of_companies`); real lookup against
        `U25111MP2002PTC015303` returns the correct company name. Live
        IBBI-scrape half (2026-08-10, owner's own machine, real network):
        `test_part6b.py` scraped 10 real listings, 10/10 got a CIN, 1/10
        got a genuine MCA match (HEMA ENGINEERING INDUSTRIES LTD, delhi,
        "Under Liquidation" — a sane status for a company with an active
        IBBI notice); see decision (25). **3 more states added
        2026-08-10** (jharkhand, odisha, uttar_pradesh — 8 total then);
        see decision (26). **6 more states added 2026-08-10** (chandigarh,
        gujarat, jammu_and_kashmir, karnataka, tamil_nadu, telangana — 14
        total now local, all 4 states decision (25)'s real scrape run
        flagged missing are now covered); see decision (27). **Maharashtra
        added 2026-08-10** (15 total now local) — by far the largest file
        yet (~218MB, 755,653 companies); see decision (28). **15 states'
        CSVs removed from the zip 2026-08-10 (data kept owner-side only,
        NOT deleted)** — see decision (29) for why and the exact
        re-upload procedure for any future session that needs to add a
        state's data back.
  - [x] **6C — Unofficial web-search news pass** — DONE (2026-08-10).
        Real run #1: 2/5 real hits, selectors confirmed correct against
        live DuckDuckGo HTML. Widened to a 4-tier fallback-query chain
        same day; real run #2 (widened chain, full re-run) CONFIRMS it:
        5/5 real, on-topic hits (tier breakdown: 1x tier 1, 1x tier 2,
        1x tier 3, 2x tier 4), all quality-checked as genuinely about the
        right company (matching CINs across sources), no noise from
        common names. Chain fully confirmed — see decision log below.
- [ ] **Part 7 — PDF report** — split 2026-08-10 (decision log below,
      "Part 7 architecture decisions") into two sub-parts once Part 7's
      actual scope was investigated against the real codebase — raw
      generation vs. sorting/categorization wasn't the real fork; the
      real one was (1) nothing today chains scrape→store→score→enrich
      end-to-end, so Part 7 can't be tested without building that first,
      and (2) Part 6's AI enrichment (Gemini/MCA/DuckDuckGo) can't cheaply
      re-run for every listing on every run. **Neither sub-part is built
      yet — this was a decisions-only session, no implementation code
      written (owner's explicit instruction for this session).**
  - [ ] **7A — Pipeline orchestrator + enrichment persistence** — new,
        not previously planned as its own sub-part. Chains scrape → store
        (Part 4, unchanged) → score (Part 5, always recomputed fresh
        in-memory over that day's full batch — see decision log for why
        scores are never persisted) → Part 6's three enrichment modules,
        but only for listings `store_records()` reports as `new` or
        `changed` (plus any listing that has never been successfully
        enriched before) — reusing prior enrichment for `unchanged`
        listings instead of re-spending Gemini/MCA/DuckDuckGo quota.
        Requires one new additive DB table (`enrichment`, keyed on
        `listing_key`) in `storage/db.py` — no changes to the existing
        `listings`/`listing_history`/`collisions` tables. This becomes
        the single entry point Part 8B's cron eventually invokes.
  - [ ] **7B — PDF layout + report categorization** — reportlab layout
        consuming 7A's assembled per-listing dataset (raw scraped fields
        + that day's fresh score + enrichment data, whether freshly
        generated or reused, each still carrying its own module's
        honesty/"unverified" labeling). Groups per Section 1: top-scored
        → closing soon → new today → watchlist changes — the latter two
        read `new`/`changed` status and field-level diffs straight from
        7A's `store_records()` call / `listing_history`, not a second DB
        query. Split further only if layout work alone makes this too
        big to finish + test in one response, per Section 0 rule 4.
- [ ] **Part 8 — Email delivery + GitHub Actions cron** — split per
      Section 0 rule 4: two genuinely different systems, each needing
      its own real-world confirmation.
  - [ ] **8A — Email delivery** — owner supplies SMTP creds locally, real
        send test confirmed.
  - [ ] **8B — GitHub Actions cron** — wiring + one real scheduled run
        confirmed before calling Phase 1 done. **DECIDED (2026-08-11,
        owner-confirmed): Option B, runtime download from a GitHub
        Release.** Self-hosted runner (the alternative) was rejected —
        the owner's machine is a regular daily-use laptop, not an
        always-on device, and a self-hosted runner only fires when that
        specific machine is powered on/awake/online at cron time, which
        directly conflicts with Section 1's "must-have, automatic every
        morning" requirement. GitHub-hosted runners (`ubuntu-latest`)
        have no such dependency. See decision (30) for the full
        reasoning and — this is the important part for whoever builds
        8B — the complete, precise implementation spec: exact Release
        setup steps, workflow YAML, and the download step, written so
        this can be built with minimal re-deciding.

**Known open issues:** this file is now ~1030 lines, past the ~500-550
line guidance in Section 0 rule 5 (grew further this session — the 6B/6C
merge decision log entry above). Not trimmed this session — the merge
task itself didn't authorize a full re-baseline (Section 0 rule 5 needs
explicit owner sign-off for that), so archiving stays a next-session
candidate, not something to freelance here. Worth archiving next code session: the fully-superseded Part
6B diagnostic `<details>` blocks in Section 4 (already collapsed, no
longer the active path — the pivot to local-file lookup, decision (21),
is what matters now) are the obvious first candidates to move into a
separate `CHANGELOG.md`/archive file, since Section 0 rule 5 itself
allows this as a full re-baseline only with explicit owner sign-off.
None for Part 6C — widened chain confirmed on a
real run (see decision log below). One thing worth knowing, not a bug:
some broadened-tier (3/4) hits point back to ibbi.gov.in itself, i.e.
the same source already scraped, not independent outside coverage — a
genuine match, just not new information. Corporate-registry sites
(Zaubacorp, RegisterKaro, IndiaMART, thecompanycheck) are the tiers that
add real outside info.
- Part 3C discovery (2026-08-09): `details_pdf_url`
is a small structured TCPDF form with EMD Amount and Location as their
own labelled fields — not free text — so those two no longer need
prose-parsing at all. Plot area is still free text inside that PDF's
Nature-of-Assets field, extracted via best-effort regex, flagged (never
guessed) when nothing matches; "auction round" was not found as a field
anywhere and is still unconfirmed.
- Bug found + fixed 2026-08-09: the first version of `__main__`'s Part 3C
  test never actually called `enrich_record_with_details()` against a
  real fetch (only the offline synthetic-fixture check ran). Fixed;
  owner re-ran and confirmed for real: 3/3 real details PDFs fetched and
  parsed correctly. Resolved.
- Part 5A (2026-08-09): `scoring/rules.py` written — `price_vs_reserve`
  scored as reserve_price percentile within the batch (not a hard
  ceiling), `location_match` scored as neutral baseline + bonus for
  PREFERRED_REGIONS matches (never a filter). Real run #1 (owner,
  `test_part5a.py`) found one genuine issue: reserve_price = literal "0"
  (a known IBBI placeholder for "no reserve fixed", per
  `_parse_reserve_price()`'s own docstring) was being percentile-ranked
  as the cheapest listing and scored 100 — misleading, since it isn't a
  real price. Fixed same session: reserve_price = 0 now excluded from
  the peer group and scored None + flagged, same treatment as a missing
  price. Real run #2 confirmed the fix for real: the affected listing
  (UNITECH TRANSFORMERS) now scores `None` with the correct flag and
  sorts to the bottom, not the top. Resolved.
- One real-run oddity, not a code bug: one parsed listing's location came
  back "Kanpur, Gujrat" (Kanpur is in UP) — the extracted CIN for that
  same record checks out exactly against public records, so this reads
  as a likely typo on the liquidator's own form, not a parsing error.
  Not fixed/altered here (would be guessing at intent) — worth a manual
  glance if the owner wants to confirm, otherwise leave as-is; this is
  exactly the kind of thing flags/pass-through is for, not silent
  correction.
- IBBI's `?page=N` adjacent-page boundary overlap (confirmed 2026-08-09)
  is handled: dedup step in `scrape_all_pages()` confirmed on a real
  3-page re-run (54 unique/60 raw, 6 dupes correctly dropped and logged,
  0 other problems, 0 remaining duplicates). Resolved.
- Part 5B (2026-08-09): real run #1 (5-listing sample) found 0/5
  possession_status, 0/5 land_classification. Root cause (not a bug):
  checked two real IBBI notice PDFs directly — "physical possession"/
  "symbolic possession" is SARFAESI-notice vocabulary; IBBI liquidation
  sale notices (Liquidation Process Regs 32/33, "as is where is...
  without recourse") don't appear to use it at all. Widened to the full
  20-listing batch to confirm before treating this as settled. Real run
  #2 (full batch) CONFIRMS it: 0/20 possession_status, 8/20
  land_classification, 5/20 scanned/unextractable notice PDFs (expected
  failure mode) — Part 5B's code is working correctly; the possession
  finding is a genuine property of IBBI liquidation notices, not a
  parsing gap. Decision (Claude, 2026-08-09, flagged not owner-specified):
  keep `possession_status` scoring in the model as-is rather than remove
  it — `score_possession_status()` already treats unknown as neutral
  (never penalized), so it costs nothing for IBBI, and the same field/
  scraper logic should earn its keep once BAANKNET (Phase 2, a SARFAESI-
  governed source) is built, since that's where this vocabulary is
  actually expected to appear. Resolved — no code change needed.
- Part 6A (2026-08-09): code written (`ai_analysis/gemini_narrative.py`,
  `config.py` Gemini settings, `test_part6a.py`) and exercised offline
  against a mocked Gemini API (success, missing-key, 429-retry-then-
  succeed, 429-twice-fails-gracefully, non-retryable HTTP error, blocked/
  no-candidates response, malformed JSON, markdown-fenced JSON, mixed-
  outcome batch — all passed). Real run #1 (owner, `test_part6a.py`,
  real key + live IBBI data) found a genuine issue: `gemini-2.5-flash`
  returned a live HTTP 404 ("no longer available to new users") on all
  5/5 listings — Google has been retiring 2.5-series models for new API
  keys ahead of their official Oct 16 2026 shutdown, confirmed as a
  widely-reported issue on Google's own developer forum, not specific to
  this key. Every failure was caught and flagged correctly rather than
  crashing the run — the error-handling code itself worked exactly as
  designed; only the hardcoded model name was wrong. Fixed same session:
  `config.GEMINI_MODEL` switched to `gemini-3.5-flash` (current
  recommended free-tier text model, confirmed on Google's own pricing
  page as of mid-July 2026), `GEMINI_REQUEST_DELAY_SECONDS` lowered from
  7 to 5 (3.5 Flash's free tier is commonly reported at ~15 RPM, higher
  than 2.5 Flash's ~10). Real run #2 (owner, same day) confirmed the fix:
  4/5 listings got real, well-grounded narratives (correctly said "no
  independent valuation data available" rather than guessing at price
  fairness; risk_notes/data_gaps caught genuine specifics like a
  mortgaged-property note and cumulative multi-lot pricing). 1/5 (METAL
  CLOSURES) failed with malformed JSON from the model (a
  `json.JSONDecodeError`, not an HTTP error) — a one-off generation slip,
  not systematic. Fixed same session: `generate_narrative()` now retries
  once on `JSONDecodeError` too (previously only retried on HTTP
  429/5xx), confirmed offline with a mocked bad-then-good response
  sequence. Owner has not re-run live data with this last fix in place,
  but real run #2's 4/5 success plus the offline-confirmed fix for the
  5th are enough to mark Part 6A done rather than holding it open for a
  3rd live run over one already-understood, already-fixed failure mode.
- Part 5C (2026-08-09): owner decided no minimum plot size right now —
  `config.MIN_PLOT_SIZE_SQFT = None`, same flexible/no-filter pattern as
  `BUDGET_CEILING`. `scoring/rules.py` written: `_parse_plot_size_sqft()`
  converts `plot_area_mentions`' mixed units (sq ft/sq mtrs/acres/
  hectares/guntas/cents) to one clean sq-ft number, flags (never guesses)
  when mentions are missing or genuinely ambiguous (e.g. separate land vs
  building figures); `score_plot_size_fit()` scores every listing neutral
  while no minimum is set — size is shown for reference, not yet a real
  filter. Real run (owner, `test_part5c.py`) CONFIRMS it works correctly
  on live data: 3/20 listings had a raw area mention at all, 1/20 (48,859
  sq. meters) correctly resolved and unit-converted (hand-verified:
  48,859 x 10.7639 = 525,913.4 sq ft, exact match), 2/20 correctly
  flagged ambiguous rather than guessed (ASIS: "2000 sq. ft" vs "300 sq.
  ft" — genuinely different figures; HANDUM: "31.82 Guntas" x2 + "17.93
  Guntas" — the duplicate correctly did NOT trigger a false-ambiguous
  flag on its own, only the genuinely different 17.93 figure did), 17/20
  had no area mention at all (expected, not a bug — most of this batch
  isn't land/plot listings, consistent with 5B's nature_of_assets spread).
  Resolved — no code change needed. All of Part 5 (5A/5B/5C) is now done.
- Part 6B (2026-08-09): `ai_analysis/mca_lookup.py` written against
  data.gov.in's free "Registrars of Companies (RoC)-wise Company Master
  Data" resource (CIN-only lookup, never name-only — see module
  docstring). mca.gov.in's own live portal needs a CAPTCHA solved per
  lookup, so data.gov.in's open mirror is used instead, same "don't
  defeat active anti-bot measures" spirit as the BAANKNET call. An
  initial version of this module guessed the data was split into a
  separate resource per Registrar of Companies — CORRECTED the same day
  after the owner walked through data.gov.in's own UI with screenshots:
  it's actually ONE resource for the whole country
  (`config.MCA_DATA_GOV_RESOURCE_ID = "4dbe5667-7b6b-41d7-82af-211562424d9a"`,
  public, not a secret, now set as a real default — the owner only needs
  the free API key, nothing else to find). Also confirmed for real from
  those screenshots (not guessed): the actual field names
  (`CORPORATE_IDENTIFICATION_NUMBER` with underscores — an earlier guess
  of `CORPORATEIDENTIFICATIONNUMBER`, no underscores, sourced from an
  unrelated resource's example, was wrong); that `filters[CompanyStateCode]`
  is a REQUIRED parameter on every query, accepting full lowercase state
  names (`"delhi"`, `"karnataka"`, etc.) rather than the CIN's own 2-letter
  code — `mca_lookup.py` now derives this automatically from each CIN's
  embedded state-code segment via a hardcoded, stable MCA/RoC state-code
  table (`_CIN_STATE_CODE_TO_NAME`, not something that needed live
  verification, unlike the resource_id/field names); and that the
  underlying data only covers company records up to 3 Nov 2023 (per the
  resource's own "Note" field), despite a much more recent "Updated On"
  date — worth knowing this enrichment can run ~2-3 years stale. The real
  registration URL was also confirmed:
  https://auth.mygov.in/user/register?destination=oauth2/register/datagovindia
  — `config.py`, `README.md`, `.env.example` all updated to match.
  STILL UNCONFIRMED (flagged, not guessed): whether
  `filters[CORPORATE_IDENTIFICATION_NUMBER]` can be combined with the
  required `filters[CompanyStateCode]` in the same request for an exact
  single-company match server-side, or whether it'll need a
  state-only-filter-then-match-client-side fallback instead. NOT YET
  CONFIRMED live either way — needs the owner to get a free key and run
  `test_part6b.py`; that script's own docstring explains exactly what a
  wall of "no match" flags across every listing would mean (the combo
  isn't supported) versus a few real matches (it is).
- Part 6B/6C merge (2026-08-10, same checkpoint as the Part 6C real run
  and Part 7 planning above): a same-day divergent chat (started from an
  earlier zip with less 6B context, "auction-tool-part7-status.zip")
  independently redid 6B from scratch, then went on to build + confirm
  6C and do the Part 7 planning above. Rather than throw away either
  version, the two 6B implementations were compared and merged in a
  follow-up session:
  **(22) "no dead code" convention reaffirmed against a real violation:**
  the divergent chat's 6B kept the entire dead live-API call path around
  behind a `MCA_LOOKUP_MODE` flag, defaulting to local-file mode but
  never removing the old code "for reference." This isn't neutral —
  grepped and confirmed it caused two real bugs: `enrich_batch_with_mca()`
  still slept `MCA_DATA_GOV_REQUEST_DELAY_SECONDS` between every record
  even in local-file mode (inherited, unused network-pacing logic
  applying to pure local file reads), and `README.md`'s Part 6B section /
  `.env.example` were never updated for the pivot — both still told the
  owner to register for a data.gov.in API key the actual default mode
  doesn't need. This project's own no-hardcoded/no-unused-cruft
  convention (Section 2) means half-migrated dead paths get removed, not
  kept "just in case" — the old live-API version is still recoverable
  from the zip history if data.gov.in's backend is ever fixed, without
  needing it live in the module. **(23) the actual merge:** kept
  `auction-tool-part6b.zip`'s clean single-mode structure (no mode flag,
  no dead code, no unused pacing) as the base, and folded in the
  divergent chat's genuinely better piece — case-insensitive
  multi-header-variant matching (`_match_header()`) plus CIN
  normalization (strip/upper on both load and lookup side) — since an
  exported CSV's headers aren't guaranteed to match the live API's exact
  field names, and an earlier version's exact-match-only approach would
  make a whole state's file unreadable over a formatting difference, not
  a real data problem. Merged `mca_lookup.py` offline-tested this session
  (re-run + confirmed): the existing missing-file/unmapped-state/no-CIN
  checks all still pass, plus a new check confirming header matching
  works against spaced/lowercase headers AND whitespace-padded CIN
  values — something neither original version handled alone. `config.py`,
  `README.md`, `.env.example` all merged to the clean key-free version
  (Part 6C's README section, which needs no key either, folded in
  alongside it). A full cross-module import check
  (`scraper.ibbi`, `ai_analysis.gemini_narrative`,
  `ai_analysis.mca_lookup`, `ai_analysis.news_search`, `scoring.rules`,
  `storage.db`) confirmed clean this session — a prior throwaway
  sanity-check script's `generate_narrative_for_listing` import error
  traced to a wrong function name in that disposable script itself
  (the real names are `generate_narrative`/`generate_narratives_for_batch`,
  confirmed via `gemini_narrative.py`, which this merge never touched),
  not a real bug — no fix needed there. **6B is merged and offline-tested
  but still NOT confirmed against a real downloaded state CSV** — that
  real-file confirmation was never done in either original chat either,
  so this is not a regression, just still-open work (unchanged from
  decision (21)'s pause: owner downloads at least one state's CSV,
  saves it under `data/mca_company_master/`, runs `test_part6b.py`).
- **(24) Part 6B CONFIRMED against 5 real downloaded state CSVs, header
  variants widened (2026-08-10):** owner supplied 5 real data.gov.in
  exports (delhi, goa, madhya_pradesh, punjab, sikkim), each identified
  by its dominant CIN state code / `CompanyStateCode` value and saved at
  the exact path `expected_csv_path_for_state()` computes. All five share
  one real header row, verbatim: `CIN,CompanyName,CompanyROCcode,
  CompanyCategory,CompanySubCategory,CompanyClass,AuthorizedCapital,
  PaidupCapital,CompanyRegistrationdate_date,Registered_Office_Address,
  Listingstatus,CompanyStatus,CompanyStateCode,CompanyIndian/Foreign
  Company,nic_code,CompanyIndustrialClassification` — the real,
  concatenated-PascalCase naming convention this data actually uses,
  confirmed to differ from both unconfirmed variant styles already in
  `_FIELD_VARIANTS` (the ALL_CAPS live-API style and a plain "Title Case
  With Spaces" guess). Comparing this real header list against
  `_FIELD_VARIANTS` field by field found 4 genuine misses —
  `sub_category` (`CompanySubCategory`), `date_of_registration`
  (`CompanyRegistrationdate_date`), `registered_state`
  (`CompanyStateCode`), `registrar_of_companies` (`CompanyROCcode`) —
  each now added as an additional variant (old variants kept, not
  replaced). `registered_office_address` was checked and found to
  already match (`REGISTERED_OFFICE_ADDRESS` lowercases to the same
  string as the real `Registered_Office_Address`) — no change needed
  there, not silently assumed. `principal_business_activity` has no
  direct equivalent in the real export — flagged rather than guessed:
  `CompanyIndustrialClassification` (NIC industrial-classification text,
  e.g. "Manufacture of other chemical products") was deliberately added
  as its variant as the closest real available field, on the reasoning
  that it's the free-text description of the company's principal
  industry — but this is noted in `mca_lookup.py` itself as a genuine
  concept swap (an industrial-classification label standing in for a
  plain-English activity description), not a confirmed exact match;
  revisit if real output ever looks misleading. Re-ran the offline smoke
  check (`python ai_analysis/mca_lookup.py`) — all pass, no regressions.
  Real lookup against `U25111MP2002PTC015303` (Madhya Pradesh) CONFIRMED:
  `company_name` returns exactly "BHOPAL MINERALS AND METALS PRIVATE
  LIMITED" as expected, and the three previously-null fields now
  populate correctly — `sub_category`: "Non-government company",
  `date_of_registration`: "2002-09-25", `registrar_of_companies`: "ROC
  Gwalior" — plus every other field (status, category, class, capital
  figures, address, the new principal_business_activity mapping) came
  back populated and plausible. **Part 6B is now CONFIRMED against real
  local CSV data for 5 states.** `test_part6b.py`'s IBBI-scrape half
  still needs the owner's own machine (live network — see Section 0 rule
  2), so the full scrape+enrich confirmation is still theirs to run, but
  the local-file-lookup half this decision covers (the part the sandbox
  *can* test) is done.
- **(25) Part 6B's IBBI-scrape half CONFIRMED live, PART 6B NOW FULLY
  DONE (2026-08-10):** owner ran `test_part6b.py` for real on their own
  machine (live network, per Section 0 rule 2 — the last remaining
  unconfirmed piece of Part 6B) and pasted back the full console output
  as two screenshots. Result: page 1 of ibbi.gov.in scraped, 10 records
  (capped at `MAX_RECORDS=10`), 0 scrape problems; Part 3C's
  details-PDF enrichment got a `cin` for 10/10 of them; `enrich_batch_
  with_mca()` then ran against the 5 already-downloaded state CSVs.
  1/10 got a real match: **HEMA ENGINEERING INDUSTRIES LTD**, CIN
  `U74210DL1987PLC029299`, found in `delhi.csv` — `company_status`
  "Under Liquidation", `company_category` "Company limited by shares",
  `company_class` "Public", registered 1987-09-22 under ROC Delhi,
  authorized capital ₹50,00,00,000 / paid-up ₹40,85,00,000, a real-
  looking Vasant Kunj registered-office address. This is a genuinely
  strong plausibility signal, not just a clean-looking row: "Under
  Liquidation" is exactly the status expected for a company with an
  active IBBI sale notice, and it lines up with this being an IBBI
  liquidation listing in the first place. The other 9/10 had a valid CIN
  + a recognized embedded state code but that state's CSV isn't
  downloaded yet — `test_part6b.py`'s own end-of-run summary named
  exactly which 5 states this run's listings needed: gujarat, karnataka,
  tamil_nadu, telangana, uttar_pradesh (one debtor, Vrundavan Ceramic
  Private Limited, a gujarat CIN, appeared 3 times among the 10 —
  plausibly a real IBBI relisting, not a scrape bug; Part 4's dedup logic
  only dedupes across `scrape_all_pages()` runs, not within Part 3C's raw
  per-page listing, so 3 raw rows for one relisted asset within a single
  10-record page is expected behavior, not new information to chase).
  **This checkpoint independently re-verified the screenshots against
  this zip's own code + data rather than accepting them on trust** (full
  steps in Verification below): re-ran the exact matched CIN directly
  against this zip's `delhi.csv` and got an identical row; called
  `lookup_company_by_cin()` on it directly and got identical output; and
  reproduced the exact "first miss for a state gets the full flag, every
  later miss for that SAME state in the same run gets the short
  'previously failed to load ... see the first failure's flag for why'
  pointer" pattern the screenshots show repeating for gujarat, confirming
  it's `_load_state_index()`'s documented `_STATE_CIN_INDEX_CACHE`/
  `_LOAD_FAILURE` caching design working exactly as intended — not a bug,
  and not a regression from decision (23)'s merge. **No code was changed
  as a result of this checkpoint.** With this, `test_part6b.py`'s own
  stated bar for confirmation — "did at least one listing from a
  downloaded state get a real match? Does mca_data look like a plausible
  match?" — is met for real, live-scraped data (not just the direct
  known-CIN check decision (24) already confirmed), so **Part 6B is now
  fully confirmed end-to-end, both halves.** Downloading the remaining 5
  states' CSVs stays optional/best-effort per this module's original
  design (Section 2) — it would mean more of a given day's real listings
  get enriched, but doesn't gate Part 6B being done or Part 7A starting.
- **(26) 3 more state exports added — jharkhand, odisha, uttar_pradesh
  (2026-08-10):** owner downloaded and supplied 3 more real data.gov.in
  exports, same header convention as the original 5 (confirmed by direct
  inspection, not assumed). One naming subtlety worth recording: the
  owner's file was named "orrisa_csv.csv" and its own `CompanyStateCode`
  column literally says "orissa" (the old pre-2011 spelling) — but this
  project's `_CIN_STATE_CODE_TO_NAME` table (built from the CIN's own
  embedded RoC code, "OR") maps that code to `"odisha"`, so
  `expected_csv_path_for_state()` looks for `odisha.csv`, not
  `orissa.csv`/`orrisa.csv`. Saved at the correct derived path
  accordingly — this is not a mismatch/bug, just two different
  spellings for the same state existing in different places (the file's
  own in-row text vs. this project's lookup-key convention), and
  `_load_state_index()` doesn't care what a row's own state-name field
  says anyway — only the CIN column matters for building the index.
  jharkhand/uttar_pradesh needed no such translation (straightforward
  name match). All 3 saved at their `expected_csv_path_for_state()`
  paths and real-lookup-confirmed directly (not just assumed from a
  clean file read): `U59200JH2025PTC024589` → GLOBAL NEXTRACK PRIVATE
  LIMITED (jharkhand.csv, Active, ROC Ranchi); `U72200OR2010PTC012427` →
  HB SOLUTIONS PRIVATE LIMITED (odisha.csv, Active, ROC Cuttack);
  `U23941UP2023PTC191927` → MRD CEMENT INDIA PRIVATE LIMITED
  (uttar_pradesh.csv, Active, ROC Kanpur) — all three came back with
  every field correctly populated (status, sub_category,
  date_of_registration, registrar_of_companies), no header-matching gaps
  this time (same convention as the original 5, per decision (24)).
  Offline smoke check (`python ai_analysis/mca_lookup.py`) and the full
  cross-module import check both re-run and still pass clean — no code
  changed, this was purely a data addition. **8 states now local**:
  delhi, goa, jharkhand, madhya_pradesh, odisha, punjab, sikkim,
  uttar_pradesh. Still not locally downloaded, from the 5 flagged in
  decision (25)'s real scrape run: gujarat, karnataka, tamil_nadu,
  telangana (uttar_pradesh is now covered). Same as before — optional,
  best-effort, does not gate anything.
- **(27) 6 more state exports added — chandigarh, gujarat,
  jammu_and_kashmir, karnataka, tamil_nadu, telangana (2026-08-10):**
  owner supplied 7 files this round; one (`odisha_csv.csv`) was checked
  byte-for-byte (`diff`/md5) against the already-saved `odisha.csv` from
  decision (26) and confirmed to be an exact duplicate re-upload of the
  same data.gov.in export — not re-copied, no action needed, owner was
  told this rather than silently dropped. The other 6 are genuinely new
  states, all same header convention as before (confirmed by direct
  inspection, no new `_FIELD_VARIANTS` gaps). One more filename-mapping
  note worth recording alongside decision (26)'s "orissa"-file
  vs. "odisha"-derived-path one: `jammu_kashmir_csv.csv`'s own CIN state
  code ("JK") maps in `_CIN_STATE_CODE_TO_NAME` to `"jammu & kashmir"`,
  and `expected_csv_path_for_state()` turns that into
  `jammu_and_kashmir.csv` (the `&` -> `"and"` substitution already built
  into that function) — saved there, not as `jammu_kashmir.csv` (the
  owner's own filename), which would never be found by a real lookup.
  `telengana_csv.csv` (owner's misspelling) saved as the correctly
  spelled `telangana.csv`, matching `_CIN_STATE_CODE_TO_NAME`'s own
  entry. Both `jammu_kashmir_csv.csv` and `telengana_csv.csv` have an
  LLP CIN (non-21-char, e.g. "AAD-6140"/"AAW-4715") as their very first
  data row — expected and harmless (this project's `state_name_from_cin()`
  already returns `None` for non-21-char CINs by design, so LLP-format
  identifiers never get force-mapped to a state; they just don't get an
  MCA enrichment, same as any other listing with no usable CIN), so a
  real company-format CIN deeper in each file was used for the
  confirmation lookup instead: `U01100JK2019PTC011028` -> GREENGLOBE
  HORTIFRESH PRIVATE LIMITED (jammu_and_kashmir.csv, ROC Jammu);
  `U13100TG2008PTC061913` -> ROBO MINES & DEVELOPERS PRIVATE LIMITED
  (telangana.csv, ROC Hyderabad). The other 4 confirmed directly off
  their own first row: `U51397CH1993PTC013541` -> NORTHERN AGRI INPUTS
  COMPANY PVT LTD (chandigarh.csv, ROC Chandigarh);
  `U74999GJ1995PLC024124` -> PALCO RECYCLE EXCHANGE LIMITED
  (gujarat.csv, ROC Ahmedabad); `U68100KA2024PTC183989` -> BULOKE
  INTERIO PRIVATE LIMITED (karnataka.csv, ROC Bangalore);
  `U74999TN2016NPL113117` -> SAMHIT ASSESSMENTS AND RESEARCH FOUNDATION
  (tamil_nadu.csv, ROC Chennai) — all 6 came back with every field
  populated, no partial matches. Offline smoke check and full
  cross-module import both re-run and still pass clean; no code changed,
  data addition only. **14 states now local**: chandigarh, delhi, goa,
  gujarat, jammu_and_kashmir, jharkhand, karnataka, madhya_pradesh,
  odisha, punjab, sikkim, tamil_nadu, telangana, uttar_pradesh. This
  covers all 4 states decision (25)'s real scrape run flagged as missing
  (gujarat, karnataka, tamil_nadu, telangana) — a fresh IBBI scrape run
  should now show a materially higher MCA-match rate than the 1/10 seen
  in that run, though this hasn't been re-confirmed with a fresh live
  scrape yet (worth doing if/when convenient, not blocking anything).
- **(28) Maharashtra state export added (2026-08-10):** owner supplied
  one more real data.gov.in export (same "RoC-wise Company Master Data"
  resource, same header row as all 14 states above — confirmed by direct
  `diff` against `delhi.csv`'s header line, byte-identical). Target
  filename derived via `state_name_from_cin()`/`expected_csv_path_for_state()`
  on a real MH-coded CIN from the file (`U25269MH1990PTC057895`) rather
  than trusting the owner's own filename — this one resolved to
  `maharashtra.csv`, matching what the owner named it, but that was
  confirmed, not assumed (unlike decision (27)'s jammu_kashmir/telengana
  cases, where the derived path differed from the owner's filename).
  Worth recording: a meaningful minority of rows in this file carry a
  non-standard embedded CIN state code — `PN` (135,417 rows) plus small
  counts of `MR`/`ME`/other real state codes — alongside the dominant
  `MH` (457,657 rows); `PN` isn't in `_CIN_STATE_CODE_TO_NAME`, so those
  rows' CINs correctly fail `state_name_from_cin()` and would flag
  "unmapped state code" rather than being force-matched to Maharashtra —
  this project's own "never guess" design handling exactly as intended,
  not a bug to fix. Real-lookup-confirmed via `lookup_company_by_cin()`
  directly on the MH-coded CIN above: `U25269MH1990PTC057895` -> SHREE
  SAI POLYSET INDUSTRIES PRIVATE LIMITED (Strike Off, ROC Mumbai,
  registered 1990-08-28) — every field populated correctly, no partial
  match. Full state index loaded clean: 755,653 usable CIN rows, zero
  `__duplicate_cins__` flag. Offline smoke check and full cross-module
  import check both re-run and still pass clean; no code changed, data
  addition only. **15 states now local**: chandigarh, delhi, goa,
  gujarat, jammu_and_kashmir, jharkhand, karnataka, madhya_pradesh,
  maharashtra, odisha, punjab, sikkim, tamil_nadu, telangana,
  uttar_pradesh.
- **(29) 15 state CSVs removed from the zip; Part 8B storage strategy
  flagged for explicit owner decision (2026-08-11, owner-requested):**
  the checkpoint zip had grown to ~170MB (798MB uncompressed data alone)
  and was starting to make each new-session upload slow — owner asked to
  fix this by keeping `data/mca_company_master/` empty in the zip going
  forward, holding the 15 real state CSVs (chandigarh, delhi, goa,
  gujarat, jammu_and_kashmir, jharkhand, karnataka, madhya_pradesh,
  maharashtra, odisha, punjab, sikkim, tamil_nadu, telangana,
  uttar_pradesh) owner-side only. **Nothing was deleted from the owner's
  side** — this only affects what travels inside the zip; the owner
  still has all 15 files on their own machine. `data/mca_company_master/`
  now holds only a `.gitkeep` placeholder. Re-confirmed the module
  degrades exactly as designed with the directory empty (clean
  "no local MCA data file" flag, no crash) — offline smoke check and
  full cross-module import check both re-run and still pass clean.
  **This also surfaced a real Part 8B question, not just a zip-size
  fix**: a hosted GitHub Actions runner has no access to the owner's own
  machine, so whatever storage approach Part 8B ends up using has to
  actually get the data onto GitHub's infrastructure somehow — "keep it
  local, add it when needed" only works for this chat-based zip
  workflow, not for the eventual cron job. Two genuinely free options
  (self-hosted runner; runtime download from GitHub Release assets) were
  discussed but NOT decided — see Section 3's flagged 8B checklist entry
  above, which any future session MUST read and ask the owner about
  before starting 8B, rather than picking one unprompted.
  **Re-upload procedure for any future session** (when a listing needs a
  state not currently in the zip, or Part 6B needs re-confirming after a
  gap): (1) owner attaches the state's CSV from their own machine, same
  as decisions (24)/(26)/(27)/(28); (2) derive the correct target
  filename via `state_name_from_cin()`/`expected_csv_path_for_state()`
  on a real CIN from the file — never trust the owner's own filename,
  see decision (27)'s jammu_kashmir/telengana mismatches for why; (3)
  save at `data/mca_company_master/{derived_name}.csv`; (4)
  real-lookup-confirm via `lookup_company_by_cin()` directly, not just a
  clean file read; (5) re-run the offline smoke check + full
  cross-module import check; (6) update this file the same way decisions
  (24)-(28) did. The 15 states already confirmed above don't need
  re-verifying if re-added later — only the filename/path convention
  needs to stay correct.
- **(30) Part 8B storage — FINAL DECISION: Option B, runtime download
  from a GitHub Release (2026-08-11, owner-confirmed):** self-hosted
  runner was the alternative on the table (decision (29)); rejected
  because the owner's machine is a regular daily-use laptop, not a
  dedicated always-on device — a self-hosted runner only executes when
  that specific machine is powered on, awake, and online at cron time,
  which would make "automatic every morning" (Section 1's own must-have
  wording) unreliable by design, not just occasionally flaky.
  GitHub-hosted runners (`ubuntu-latest`) have no such dependency, so
  Option B is what 8B will be built against. **Full precise spec below —
  whoever builds 8B should follow this directly, not re-derive it.**

  **Step 1 — one-time: package the data.** All 15 states' CSVs
  (chandigarh, delhi, goa, gujarat, jammu_and_kashmir, jharkhand,
  karnataka, madhya_pradesh, maharashtra, odisha, punjab, sikkim,
  tamil_nadu, telangana, uttar_pradesh — see decision (29) for why
  they're not in the repo/zip) get zipped into ONE archive,
  `mca_company_master.zip`, flat inside the zip (no `data/` prefix
  needed, the workflow step below handles the destination path):
  ```
  cd data/mca_company_master && zip -X -r ../../mca_company_master.zip .
  ```
  Confirmed size with the owner's real 15 files, this checkpoint:
  **169,982,357 bytes (~170MB) compressed**, well under GitHub Release's
  2GB-per-asset limit — no splitting needed even if a few more states
  get added later.

  **Step 2 — one-time: create the GitHub Release.** Via the repo's own
  GitHub web UI (Releases → "Draft a new release" — no `gh` CLI or extra
  tooling needed): tag `mca-data-v1`, title "MCA company master data
  v1 (15 states)", attach `mca_company_master.zip` as a release asset,
  publish. This is a **data-only Release, separate from any code-version
  tags** this project might use later — don't conflate the two.

  **Step 3 — the workflow step (add to the 8B `.github/workflows/*.yml`
  cron job, BEFORE the enrichment/pipeline step runs):**
  ```yaml
  - name: Download MCA company master data
    run: |
      mkdir -p data/mca_company_master
      curl -L -o mca_company_master.zip \
        "https://github.com/${{ github.repository }}/releases/download/mca-data-v1/mca_company_master.zip"
      unzip -o mca_company_master.zip -d data/mca_company_master
  ```
  `${{ github.repository }}` resolves automatically to `owner/repo` —
  no hardcoded username needed. The release TAG (`mca-data-v1`) is
  pinned deliberately, not `latest` — so data updates are a conscious,
  versioned action (see Step 5), never a silent change to what a
  scheduled run pulls in.

  **Step 4 — safety net added this checkpoint (small, precautionary code
  change, not deferred to 8B):** `data/mca_company_master/*.csv` added
  to `.gitignore` (keeping `.gitkeep` tracked) so a real downloaded state
  CSV can never be accidentally `git add`-ed/pushed later and hit
  GitHub's 100MB-without-LFS block — this was a real gap before (the
  files were only absent from the zip by omission, not actually
  ignored).

  **Step 5 — updating the data later (e.g. adding a 16th state, or
  refreshing an existing one):** re-run Step 1's zip command locally with
  the updated `data/mca_company_master/` contents, then either (a) edit
  the existing `mca-data-v1` Release and replace the asset (simplest,
  same URL, no workflow change needed), or (b) publish a new tag (e.g.
  `mca-data-v2`) and update the URL in Step 3's workflow — (b) is safer
  if the owner wants an easy rollback path, (a) is less to maintain.
  Either way: MCA data can be updated independently of a code deploy,
  no PR/merge required for a pure data refresh.

  **What this means for 8B's build/test bar:** the "one real scheduled
  run confirmed" checklist item (Section 3) should include seeing this
  download step actually pull real data into a hosted runner and
  `lookup_company_by_cin()` return a genuine match during that run — not
  just that the workflow doesn't error. Ready to build once 7A/7B are
  done; not blocked on anything else.

---

## 4. Last updated
*(Overwrite these fields only — see Rule 5 in Section 0.)*

- **Position:** **PART 6B FULLY CONFIRMED, 15 states confirmed
  owner-side; Part 8B storage strategy now FINALIZED (2026-08-11).** All
  15 states (chandigarh, delhi, goa, gujarat, jammu_and_kashmir,
  jharkhand, karnataka, madhya_pradesh, maharashtra, odisha, punjab,
  sikkim, tamil_nadu, telangana, uttar_pradesh) have been
  real-lookup-confirmed across decisions (24)-(28). **PART 6C REMAINS
  FULLY CONFIRMED. PART 7 ARCHITECTURE DECISIONS REMAIN DECIDED, NO CODE
  WRITTEN YET.**
  Prior checkpoint (same day) removed all 15 state CSVs from the
  checkpoint zip to fix its ~170MB size (decision (29)) — nothing
  deleted owner-side, `data/mca_company_master/` holds only `.gitkeep`
  in the zip/repo.
  **New this checkpoint:** the Part 8B storage question that removal
  surfaced is now DECIDED, not just flagged. Self-hosted runner (one of
  the two free options on the table) was ruled out — the owner's machine
  is a regular laptop, not an always-on device, and a self-hosted runner
  only fires when that machine is on/awake/online at cron time, which
  conflicts with Section 1's "automatic every morning" must-have. **Final
  choice: Option B, runtime download from a GitHub Release** — see
  decision (30) for the complete, precise build spec (exact zip/Release
  steps, the workflow YAML download step, `.gitignore` safety net, and
  how to update the data later), written so 8B can be built directly
  from it with minimal re-deciding. Confirmed this session: the real 15
  files zip cleanly to **169,982,357 bytes (~170MB)**, well under
  GitHub's 2GB-per-Release-asset limit. `data/mca_company_master/*.csv`
  added to `.gitignore` (small precautionary code change, not deferred)
  so a real state CSV can never be accidentally committed and hit
  GitHub's 100MB-without-LFS push block.
  **Next: Part 7A** — `storage/db.py`'s new `enrichment` table + a new
  orchestrator entry point (exact filename/location not yet decided —
  flagged, not guessed) wiring Parts 4/5/6 together per the Part 7
  architecture decisions already on record below, tested against a real
  small-batch run before 7B starts — is the one real next coding step,
  unblocked by anything (8B's now-finalized storage plan doesn't block
  7A), whenever the owner's ready to start it.
  Earlier this session (unchanged from before, kept for context): merged two
  divergent zips that had branched from the same earlier checkpoint: one
  (`auction-tool-part6b.zip`) had a clean, no-dead-code 6B but hit its
  token limit before going further; the other
  (`auction-tool-part7-status.zip`) independently redid 6B, then built +
  fully confirmed 6C and did the Part 7 architecture planning below —
  both already recorded in this file. The merge combined `part6b.zip`'s
  clean single-mode 6B structure with `part7-status.zip`'s more robust
  CSV header matching, dropped `part7-status.zip`'s dead live-API code
  path (which was violating this project's own no-unused-cruft
  convention and had caused two real bugs — see decision (22)/(23) in
  the decision log above for the full reasoning), and carried 6C +
  the Part 7 planning forward unchanged, since neither touches 6B code.
  **6B is merged and offline-tested this session** (existing checks
  re-confirmed, plus a new header/CIN-normalization check that neither
  original version had alone) **but still needs a real downloaded state
  CSV to be confirmed live** — that was never done in either original
  chat, so this isn't a regression, just still-open work (unchanged from
  decision (21)'s pause). `test_part6b.py` was updated to match the
  merged module's actual function names/config vars (a light edit, not a
  rewrite, since both originals already agreed on those); `README.md`
  and `.env.example` now correctly say no API key is needed for 6B and
  include 6C's section (which also needs no key). A full cross-module
  import check (`scraper.ibbi`, `ai_analysis.gemini_narrative`,
  `ai_analysis.mca_lookup`, `ai_analysis.news_search`, `scoring.rules`,
  `storage.db`) passed clean this session.
  **Part 6C stays exactly as it was at the last checkpoint: fully
  confirmed** — real run #2 (widened 4-tier fallback chain) got 5/5 real,
  on-topic hits, quality-checked via cross-matching CINs across
  independent sources — see decision log above for the full breakdown.
  Nothing about 6C changed in this merge; its code was carried over
  verbatim, and its offline smoke check was re-confirmed after the merge
  as part of this session's full re-run of every module's offline check.
  **Part 7's two architecture decisions (does the DB hold score/AI
  fields; does Part 7 build the orchestrator) also stand unchanged** —
  see "Part 7 architecture decisions" at the end of the decision log
  below for the full reasoning; short version: scores stay ephemeral
  (recomputed fresh in-memory every run, never persisted), Part 6's AI
  enrichment gets a new additive `enrichment` DB table so it's only
  re-run for `new`/`changed`/never-yet-enriched listings, and Part 7A
  (pipeline orchestrator + enrichment persistence) is the real next
  coding step, not 7B/PDF layout directly, since nothing today chains
  scrape→store→score→enrich end-to-end.
  (Superseded 2026-08-10, same checkpoint as decision (25): the "still
  needs a real downloaded state CSV to be confirmed live" open item this
  paragraph originally described is now closed — see the top of
  Position above and decision (25) for the real IBBI-scrape confirmation
  that closed it. Kept here, unedited, purely as a record of what this
  merge session actually said/knew at the time.)
  <details>
  <summary>2026-08-10 Part 6B pause (kept for context, not the active
  next step right now)</summary>

  Goa/Delhi/MP exports were queued on data.gov.in but still "In progress"
  as of the prior checkpoint (these can take a while, especially Delhi
  given its company count — see decision (19)'s size theory, still
  plausible as an explanation for job duration even if it wasn't the 502
  cause). Rather than block on that queue, owner chose to move on to 6C
  first, per the option decision (20)/(21) already built in ("Part 6B was
  always best-effort/non-blocking — the rest of the pipeline does NOT
  need to wait").
  </details>
  <details>
  <summary>2026-08-10 pivot details (why 6B moved to local-file lookup —
  kept for context, not the active next step right now)</summary>

  the diagnosis from 2026-08-09 (below, kept for history) turned out to
  be exactly right in spirit but the root cause is even more basic than
  "data.gov.in's backend is degraded": the owner checked data.gov.in's
  OWN "Preview & Download" UI directly (screenshot) and even a small
  state (Goa) queues a background job ("In progress" / "may take time,
  large data"), not an instant response. This resource was never meant
  to be queried live per-record — it's a bulk/batch export. `mca_lookup.py`
  is rewritten to look up CINs against a **local per-state CSV** the
  owner downloads once via that same Preview & Download flow (see the
  module's own docstring for exact steps), instead of calling the live
  API. Offline-tested with two synthetic sample CSVs (both underscored
  API-style headers and spaced/title-case headers matched correctly).
  </details>
  <details>
  <summary>2026-08-09 diagnosis history (superseded by the pivot above,
  kept for context)</summary>

  Part 6B code was written and corrected; resource_id +
  real field names are confirmed and hardcoded (owner doesn't need to
  find anything on data.gov.in). Owner has a real API key working and ran
  `test_part6b.py` for real (2026-08-09) — **diagnosis concluded that
  this looks like a problem on data.gov.in's own end, not this project's
  code; PAUSED pending either the owner's non-code checks or a decision
  to move on. This is the very next thing to pick up — check what the
  owner's next message says before continuing:**
  - `test_part6b.py` run #1 result: 10/10 listings got a CIN from Part
    3C. 9/10 derived a valid CompanyStateCode from their CIN. 1/10
    ("Maharaja Theme Parks and Resorts Pvt Ltd", CIN
    U92199TZ1995PTC005954) hit a real gap in `_CIN_STATE_CODE_TO_NAME` —
    state code "TZ" (Tamil Nadu's SECOND RoC, Coimbatore, distinct from
    "TN" for RoC Chennai) wasn't in the table. **This has been FIXED**
    (added to `ai_analysis/mca_lookup.py`) but not yet re-tested live.
  - The other 9/10 (valid CIN + valid state) ALL failed with the exact
    same error: `network error calling data.gov.in:
    HTTPSConnectionPool(host='api.data.gov.in', port=443): Read timed
    out. (read timeout=20)`. This is NOT a clean "0 records found"
    response — it's the HTTP request itself timing out after
    `config.MCA_DATA_GOV_TIMEOUT_SECONDS` (20s) with no response at all.
    This is a DIFFERENT problem than the "is the combined CIN+state
    filter even supported" question this project was originally worried
    about (see Known open issues) — a real HTTP timeout doesn't tell us
    whether the filter combo works, only that the server didn't answer
    in time.
  - **Diagnostic v1 RESULT (received, 2026-08-09):** Query A
    (state-only, "delhi", limit=1) and Query B (state+CIN, "delhi") BOTH
    responded in ~60s with **HTTP 502 Bad Gateway, empty body** — not a
    client-side timeout this time (their server DID respond, just with an
    error), and critically, A and B failed IDENTICALLY (same ~60s, same
    502) regardless of whether the CIN filter was even present. This
    rules out "the CIN filter specifically is slow/unsupported" as the
    sole explanation — the state-only query alone already fails the same
    way. Working theory: querying a big/populous state (Delhi has a huge
    number of registered companies) may be too much for data.gov.in's own
    backend regardless of what else is filtered, and it's giving up
    (502) after ~60s of its own internal processing.
  - **Diagnostic v2 RESULT (received, 2026-08-09):** Query C ("sikkim")
    and Query D ("goa") — both small, low-company-count states — BOTH
    failed EXACTLY the same way as Delhi did: ~60s, HTTP 502, empty body.
    **This RULES OUT dataset size as the cause** — small states fail
    identically to Delhi. Combined with v1's finding (CIN filter presence
    doesn't change the outcome either), this now looks systemic: every
    single query tried against this resource_id so far — 2 states, with
    and without a CIN filter — has failed the same way, in almost exactly
    the same ~60s. That consistency (not a range of times, a tight
    60.2-60.4s cluster, empty body rather than even a small error page)
    reads like a fixed backend/gateway timeout that's failing for
    everyone right now, not something wrong with how this project's
    requests are built. Checked for a public data.gov.in outage report —
    found nothing conclusive either way.
  - **STATUS: paused, not blocking.** No code fix identified yet because
    nothing points to a code problem — the leading theory is this
    specific resource (or api.data.gov.in more broadly) is currently
    broken/degraded on the government's end. Two non-code next steps
    given to the owner: (1) try "Preview & Download" on data.gov.in's own
    website UI for a small state, to see if the outage is visible even
    outside our API calls (if yes, confirms it's not our code at all);
    (2) the resource's own "Write to CDO" contact form
    (sidhil.sasi@nic.in) to report it. **Per this project's original
    design (see Section 2, background-check depth), Part 6B was always
    meant to be best-effort/non-blocking** — every listing already gets a
    clean flag instead of crashing when this fails, so the rest of the
    pipeline (6C, Part 7) does NOT need to wait on this being fixed.
    Owner may choose to move on to 6C/Part 7 now and revisit Part 6B
    later once data.gov.in's side is working, or keep investigating —
    whichever they pick, **check the owner's next message for which
    path they chose before continuing.**
  (21) Part 6B pivot to local-file lookup (2026-08-10, owner-confirmed):
  owner checked data.gov.in's own "Preview & Download" UI directly
  (screenshot) as decision (20) suggested — even a small state (Goa)
  queues a background job ("In progress", "may take time, large data",
  checked via Download History) rather than responding live. This
  confirms decisions (19)/(20)'s 502s weren't a fixable code problem
  AND reveals the deeper reason: this resource is a bulk/batch export by
  design, not a live per-record lookup API — trying to call it like one
  was always going to be unreliable. Fix: `mca_lookup.py` now looks up
  CINs against a local per-state CSV the owner downloads once (via that
  same Preview & Download flow) and saves under
  `config.MCA_DATA_GOV_LOCAL_EXPORT_DIR`, rather than calling the live
  API per lookup — a one-time cost per state instead of a per-lookup
  network call, which also fits the data better (frozen as of Nov 2023
  per the resource's own note, so nothing "live" is lost by doing this
  offline). `config.MCA_LOOKUP_MODE` defaults to `"local_export"`; the
  old live-API code is kept in `mca_lookup.py` for reference but is off
  by default. Column headers inside a real downloaded CSV are still
  UNCONFIRMED (only two synthetic sample files tested offline so far,
  one in each plausible header style) — `load_state_export()` raises a
  clear error naming the actual headers found if none of the known
  variants match, rather than silently indexing nothing.
  `diagnose_part6b_timeout.py` / `diagnose_part6b_timeout_v2.py` deleted
  (per their own file-header note: "safe to delete once this is
  resolved") — the 502/timeout question they were built to isolate is
  now moot given the live-API path is no longer used.
  - Once the real cause is confirmed and a run gets at least a few
    genuine matches with plausible-looking company data, Part 6B can be
    marked confirmed. Then: **6C** (unofficial web-search news pass),
    then Part 7 (PDF report — where 6A's narrative AND 6B's mca_data
    actually get laid out per listing; nothing currently persists either
    to `storage/db.py`, worth deciding at Part 7 whether it should).
  </details>
- **Verification (this checkpoint, 2026-08-11, Part 8B decision
  finalized — planning + one small precautionary code change, no
  pipeline code written):** owner confirmed their machine is a regular
  laptop, not an always-on device — this directly decided the
  self-hosted-runner-vs-runtime-download question (see decision (30)).
  Re-extracted all 15 states' real CSVs from the prior full checkpoint
  zip (nothing was ever actually lost — decision (29) only removed them
  from the zip, not from record) and zipped them into a single
  `mca_company_master.zip` test bundle to get exact, real figures for
  the build spec rather than estimating: **169,982,357 bytes (~170MB)
  compressed**, confirmed under GitHub Release's 2GB-per-asset limit.
  Added `data/mca_company_master/*.csv` to `.gitignore` (keeping
  `.gitkeep` tracked) — a genuine gap before this (the files were only
  absent from the zip by omission, not actually ignored, so a future
  `git add .` could have re-introduced the 100MB push-block risk decision
  (29) was trying to avoid). No pipeline/module code touched — 8B itself
  isn't built yet, this checkpoint only finalized its storage
  architecture and closed the one open gap that could've undermined it
  later. Offline smoke check and full cross-module import check both
  re-run and still pass clean (unaffected by this checkpoint's changes,
  confirmed rather than assumed).
- **Files touched this checkpoint:** `.gitignore` (one line added:
  `data/mca_company_master/*.csv`). `PROJECT_STATUS.md` (this entry +
  Section 3's 8B checklist line, now marked DECIDED + decision (30), the
  full precise build spec). No pipeline `.py` files were changed.
- **Decisions on record (2026-08-09):** (1) Phase order: IBBI → BAANKNET
  → other bank-auction portals. (2) Email + scheduling treated as a v1
  must-have, built as soon as a report exists, not deferred. (3) New AI
  narrative-analysis layer added, separate from rule-based scoring;
  must use a genuinely free-tier LLM (Gemini or Groq), owner to choose +
  get key. (4) Background-check depth: reason over scraped data (free,
  primary) + best-effort free MCA lookup / unofficial free web search
  (flagged if it fails, never blocking). (5) BAANKNET's robots.txt/ToS
  decision from 2026-08-07 still stands, applies to BAANKNET only. (6)
  Part 3C parses `details_pdf_url` (small structured form), not
  `notice_pdf_url` (big free-text/possibly-scanned legal notice) — the
  structured form already has EMD Amount and Location as own fields.
  (7) Part 4 dedup key uses corporate_debtor + ip_name + notice_type +
  nature_of_assets as the IDENTITY key (stable across a relisting);
  reserve_price/auction_date/notice_date/emd_due_date are TRACKED fields
  whose changes trigger a "changed" record (incl. price-drop flag), not
  a new listing_key — this split was corrected before coding after the
  owner caught that an earlier draft would have broken price-drop
  detection by putting tracked fields inside the identity key. IBBI's
  permanent reference code (`cin`, from Part 3C) is used only as a
  last-resort manual tie-breaker on the rare hash collision, not a daily
  dependency.
  (8) Part 5A scoring inputs (owner, 2026-08-09): flexible by design, not
  rigid. `BUDGET_CEILING = None` in config.py — no hard price cutoff;
  `price_vs_reserve` scores relatively (discount-to-reserve or
  percentile), not pass/fail. `PREFERRED_REGIONS = ["Delhi", "Rajpura",
  "Madhya Pradesh"]` in config.py — a scoring BONUS for `location_match`,
  not an exclusive filter; listings from other regions still appear in
  the report, just without the bonus. Owner was explicit: does not want
  other regions hidden.
  (9) Part 5A implementation choices (Claude, 2026-08-09, not owner-
  specified — flagged here for visibility, not presented as owner
  decisions): with no market-value field to discount against,
  `price_vs_reserve` is scored as reserve_price's percentile rank
  *within the current scoring batch* (cheaper-than-peers scores higher)
  — re-derived fresh per batch, not a stored/comparable-across-days
  number. `LOCATION_MATCH_NEUTRAL = 50` / `LOCATION_MATCH_BONUS = 25`
  are reasonable round defaults for the bonus's size, not owner-
  specified — fine to tune later. `SCORE_WEIGHTS` in config.py stays
  untouched (still all `None`) — 5A's two scores are combined into a
  `partial_score_5a` (plain average of whichever of the two are
  available for a listing) purely for a usable ranking now, explicitly
  labeled "partial" rather than presented as the finished weighted
  score, since 3 of 5 criteria aren't scored until 5B/5C exist and real
  weights haven't been set.
  (10) Real-run #1 fix (2026-08-09, see Known open issues above):
  reserve_price = 0 is IBBI's own placeholder for "no reserve price
  fixed", not a genuine ₹0 asset — `price_vs_reserve` now treats it the
  same as a missing reserve_price (excluded, scored None, flagged), not
  as the cheapest listing in the batch.
  (11) Part 5B scope decision (owner, 2026-08-09): possession_status gets
  a real new scraper part parsing `notice_pdf_url` — the big free-text
  legal notice Part 3C deliberately excluded (large, free-text, possibly
  scanned) — rather than being skipped for v1, because that's where
  physical/symbolic possession is actually disclosed; it isn't reliably
  present in the small details PDF or `nature_of_assets`. Owner picked
  this after being walked through the trade-off in plain terms.
  (12) Part 5B land_classification decision (owner, 2026-08-09, "choose
  whatever provides the most output/utility"): Claude's call was to do
  BOTH — best-effort regex on `nature_of_assets` (already scraped, so
  free) AND, since the notice PDF is now being fetched anyway for
  possession_status, prefer that fuller text for land_classification too
  when it's available, falling back to `nature_of_assets` only when the
  notice PDF isn't usable. Maximizes coverage at no extra fetch cost.
  `PREFERRED_LAND_CLASSIFICATIONS` is empty by default (mirrors 5A's
  `PREFERRED_REGIONS` pattern) — every classification scores the same
  neutral baseline until the owner sets an actual preference; this
  wasn't a business decision to make on the owner's behalf, since the
  master spec still lists it as an open question.
  (13) Part 5B possession_status keep-as-is (Claude, 2026-08-09, flagged
  not owner-specified): full 20-listing real run confirmed 0/20
  possession_status on IBBI — kept the field/scoring code rather than
  removing it, since unknown already scores strictly neutral (never
  penalized, per decision above) so it costs nothing, and the same
  scraper logic is expected to actually pay off once BAANKNET (a
  SARFAESI-governed source, Phase 2) is built. Revisit only if BAANKNET
  also comes back 0/N.
  (14) Part 5C minimum plot size (owner, 2026-08-09): none decided right
  now. `config.MIN_PLOT_SIZE_SQFT = None`, same flexible-by-design
  pattern as `BUDGET_CEILING` — plot_size_fit scores every listing
  neutral for now (informational display only), not a filter/penalty.
  Owner can set a real number any time; the scoring code already handles
  that path (bonus for meeting/exceeding it, neutral — not penalized —
  below it), so no further code change will be needed when they do.
  (15) Part 6A LLM choice (owner, 2026-08-09): Gemini over Groq.
  (16) Part 6A implementation choices (Claude, 2026-08-09, flagged not
  owner-specified): originally picked `gemini-2.5-flash`; corrected same
  day to `gemini-3.5-flash` after real run #1 hit a live 404 (Google
  retiring 2.5-series models for new keys early — see Known open issues).
  Called directly over HTTP with `requests` rather than adding the
  `google-generativeai` SDK, to keep dependencies small and the call
  auditable; `GEMINI_REQUEST_DELAY_SECONDS=7` between batch calls to stay
  under the free tier's ~10 req/min; one retry on HTTP 429/5xx only,
  fails fast on anything else (bad key, blocked content) since retrying
  wouldn't help. Narrative scope is deliberately limited to fields
  already scraped (per Section 2's tier-1 background-check plan) — the
  prompt explicitly tells the model not to use outside knowledge about
  the specific company/location or invent a fair-price judgment beyond
  what the data supports, and to name missing fields as gaps rather than
  filling them. Output is a strict 4-key JSON contract (summary,
  price_read, risk_notes, data_gaps) so it's directly usable by Part 7's
  PDF layout later without further parsing. `test_part6a.py` caps the
  first confirmation run at 5 listings (`MAX_RECORDS`) since it spends
  real API quota, not just network calls — raise it once confirmed.
  (17) Part 6B implementation choices (Claude, 2026-08-09, flagged not
  owner-specified): used data.gov.in's free OGD "Registrars of Companies
  (RoC)-wise Company Master Data" resource rather than mca.gov.in's own
  portal, because the latter requires solving a CAPTCHA per lookup and
  this project won't automate around active anti-bot measures (same
  principle as the BAANKNET robots.txt call, applied the other way — here
  it means picking the alternate free source instead of scraping the
  CAPTCHA-gated one). Lookup is strictly CIN-only, never by
  corporate_debtor name alone, since a name-only match across a
  multi-million-company registry risks silently attaching the wrong
  company's data — consistent with the project's "never guess, always
  flag" rule. An initial guess that this data was split per-RoC (and that
  `config.MCA_DATA_GOV_RESOURCE_IDS` needed to stay empty until the owner
  found their own resource_id) was corrected the same day once the owner
  actually walked data.gov.in's UI with screenshots — it's one national
  resource with a fixed, public resource_id, now hardcoded as
  `config.MCA_DATA_GOV_RESOURCE_ID`'s default. The one thing still not
  guessed at, and left for the owner's first real `test_part6b.py` run to
  settle: whether this resource's required `filters[CompanyStateCode]`
  parameter can be combined with a `filters[CORPORATE_IDENTIFICATION_NUMBER]`
  filter in the same request — reasonable to expect (this platform's
  CKAN-style datastore API generally supports filtering on any field, not
  just the documented one, per a separate example resource that supported
  an undocumented field filter), but not confirmed, so `mca_lookup.py`'s
  "no match" flag explicitly says what a wall of these would mean if that
  assumption turns out wrong.
  (18) Part 6B first live run findings (2026-08-09): confirmed 9/10
  scraped listings got a real CIN + valid derivable state; found and
  fixed a genuine gap in `_CIN_STATE_CODE_TO_NAME` — Tamil Nadu has TWO
  RoC state codes ("TN" for RoC Chennai, "TZ" for RoC Coimbatore), only
  "TN" was originally mapped. All 9 valid lookups then failed with an
  HTTP read timeout at 20s (`config.MCA_DATA_GOV_TIMEOUT_SECONDS`), NOT a
  clean "0 records" response — meaning decision (17)'s open question
  (does the combined CIN+state filter even work?) is STILL unanswered;
  a timeout doesn't distinguish "the query works but is slow" from "the
  query is fundamentally broken." One-off diagnostic script
  `diagnose_part6b_timeout.py` added (root of repo, not part of the
  regular pipeline, safe to delete once this is resolved) to isolate the
  cause with a patient 90s timeout, by comparing a state-only query
  against the combined state+CIN query on one real CIN. Result pending —
  see Section 4 "Position" for exactly what to do with the owner's next
  message.
  (19) Part 6B diagnostic v1 result (2026-08-09): state-only and
  state+CIN queries against "delhi" BOTH failed identically — ~60s, then
  HTTP 502 Bad Gateway, empty body. Same timing and same failure whether
  or not the CIN filter was present, which rules out decision (17)'s
  original worry (CIN filter specifically unsupported/slow) as the SOLE
  cause — the state-only query alone already fails the same way. Working
  theory: this may be a dataset-size problem specific to big/populous
  states (Delhi has a huge registered-company count), not a filter-combo
  problem. `diagnose_part6b_timeout_v2.py` added to test this directly
  against two much smaller states (sikkim, goa) — result pending, see
  Section 4 "Position" for what to do with it.
  (20) Part 6B diagnostic v2 result + pause decision (2026-08-09): sikkim
  and goa (small states) failed EXACTLY like Delhi did (~60s, HTTP 502,
  empty body) — ruling out decision (19)'s dataset-size theory too. Every
  query tried so far (2 states x with/without CIN filter) fails
  identically. No public data.gov.in outage report found via web search,
  but the tight, consistent timing (~60.2-60.4s every time) and empty
  body point to a backend/gateway-level failure on data.gov.in's own
  side, not a problem with this project's request-building code. No
  further code changes made on the strength of a guess — nothing here
  actually points at a fixable bug in `mca_lookup.py`. Owner given two
  non-code checks (data.gov.in's own website "Preview & Download" for a
  small state; the resource's "Write to CDO" contact form) and the option
  to move on to 6C/Part 7 and revisit Part 6B later, since it was always
  designed as best-effort/non-blocking (Section 2) and every listing
  already degrades to a clean flag rather than crashing. Outcome/owner's
  choice not yet known as of this zip — see Section 4 "Position."
- Part 6C real run #1 result + widened matching (2026-08-10): owner ran
  `test_part6c.py` live for the first time. Result: 2/5 listings got
  real, plausibly-relevant hits (including one result correctly stating
  a debtor is under liquidation); 3/5 returned 0 results. This CONFIRMS
  `_parse_results()`'s selectors are correct — a broken selector would
  have produced 0/5, not 2/5 with on-topic content — so Part 6C is marked
  done rather than held open on a false "selectors unconfirmed" basis.
  Owner asked for a 100% hit rate. Flagged plainly (not silently
  attempted): a genuine 100% isn't achievable or honest for this kind of
  best-effort public web search — some corporate debtors, especially
  smaller/less-newsworthy ones, have no real indexed online coverage, and
  forcing a hit for every listing would mean either loosening the query
  until it starts matching unrelated noise, or fabricating relevance —
  both break this module's own core "never trust blindly, always flag"
  rule from Section 2. What WAS legitimately fixable: the single query
  used in real run #1 was narrow (exact-phrase name + a hard
  auction/insolvency/NCLT topic filter), so some of those 3 zero-result
  companies may have real coverage that query was simply too strict to
  find. `_build_query()` replaced with `_build_query_chain()`: tries up
  to 4 progressively broader queries per listing (quoted name + location
  + topic filter → quoted name + location → quoted name alone → bare
  unquoted name), stopping at the first real hit; a result found only on
  a broadened tier is flagged as such (not presented identically to a
  tier-1 hit) so the owner can weigh it accordingly when reading the PDF.
  `config.NEWS_SEARCH_TIER_DELAY_SECONDS` (2s) added, separate from the
  existing between-listing `NEWS_SEARCH_REQUEST_DELAY_SECONDS` (5s), to
  pace the extra requests one listing's fallback chain can now make.
  Offline-tested with a mocked `call_duckduckgo_html()` confirming both
  the fall-through case (tier 1 empty, tier 2 hits — returns tier 2's
  result with the broadened-tier flag) and full exhaustion (all 4 tiers
  empty — clean flag naming all tiers tried, doesn't raise). Real run #2
  (owner, widened chain, same 5 listings) CONFIRMS it live: 5/5 got real
  hits (tier breakdown: METAL CLOSURES tier 1, ROTOMAC GLOBAL tier 2,
  Maharaja Theme Parks tier 3, KONASEEMA GAS POWER + PRATISHTHA DAIRY
  FARMS both tier 4). Quality-checked, not just counted: every hit is
  genuinely about the right company (CINs cross-match across sources,
  e.g. Konaseema's own site + Zaubacorp + IBBI's own PDF all agree on
  U40101TG1997PLC037013), no wrong-company noise despite some fairly
  generic-sounding names (METAL CLOSURES, Maharaja Theme Parks). One
  caveat, not a defect: a few broadened-tier (3/4) hits point back to
  ibbi.gov.in itself, i.e. confirm the match but add no independent
  outside information — the corporate-registry-site hits (Zaubacorp,
  RegisterKaro, IndiaMART, thecompanycheck) are what add real outside
  info beyond what's already scraped. 100% hit rate happened on this
  5-listing sample, but this remains a best-effort ceiling, not a
  guarantee — a larger batch will very likely include at least some
  companies with genuinely zero indexed coverage even across all 4
  tiers, and that will still show as a clean flag rather than a fake
  hit. Part 6C is fully confirmed; next is Part 7.
- Part 7 architecture decisions (2026-08-10, Claude-decided per the
  owner's explicit delegation this session — "resolve them yourself,"
  flagged here the same way earlier Claude-picked-not-owner-specified
  calls have been throughout this file — **planning/decisions only, no
  code written this session**, per the owner's separate explicit
  instruction not to touch code this time): two open questions from the
  end of the last session, resolved by reading the real codebase rather
  than guessing (see "Verification" above for exactly what was read).

  **Q1 — does the DB hold score/AI fields?** Neither option as
  originally posed, straight up. **(a) "read back out of the DB"
  rejected**: `scoring/rules.py`'s own docstring is explicit that
  `price_vs_reserve` is a percentile rank *within that run's batch*,
  "recomputed fresh per batch — a listing scored yesterday's batch will
  not carry the same number today, by design." Persisting a score to a
  DB column would misrepresent an intentionally-ephemeral, batch-relative
  number as a stable stored fact, and would mean an unnecessary schema
  migration on the `listings` table for something that shouldn't be
  cached at all. **(b) "everything in memory, DB only for new/changed"
  rejected too, but only as originally framed**: Section 1's own report
  categories (top-scored, closing soon) need ranking/filtering over
  *every currently-active listing*, not just today's new/changed diff —
  most listings on most days are `unchanged`, so a pure today's-diff-only
  pass genuinely cannot produce those two categories on its own (the
  prompt's instinct to question this was correct). Fixed by scraping the
  full current listing set every run (not an incremental diff) and
  scoring all of it fresh in-memory — cheap, pure computation, no reason
  not to. Where (b) breaks down is Part 6's AI layer: re-running Gemini
  narrative generation + the MCA lookup + a DuckDuckGo scrape for every
  currently-active listing on every single run — including the large
  majority that are `unchanged` from yesterday — is exactly the
  quota/fragility cost the prompt flagged, and repeatedly re-labeling
  something "unverified" after re-fetching data that didn't change
  teaches nothing new; it just spends quota for the same honesty label
  already on record. **Decision: a hybrid.** Add ONE new, purely
  additive DB table, `enrichment` (keyed on `listing_key`, no changes to
  `listings`/`listing_history`/`collisions`), holding each module's
  latest result: `gemini_narrative_json` + `gemini_generated_at`,
  `mca_data_json` + `mca_lookup_attempted` + `mca_looked_up_at`,
  `news_data_json` + `news_flags_json` + `news_searched_at`. Each run:
  score every currently-scraped listing fresh (never cached); re-run
  Part 6's enrichment modules only for listings `store_records()` marks
  `new` or `changed`, or that have no `enrichment` row yet (first-ever
  enrichment) — everything else reuses its existing `enrichment` row.
  Every enrichment field keeps carrying its own module's honesty
  label regardless of whether it's fresh or reused this run (a reused
  "unverified" news hit is still exactly as unverified as it was the day
  it was fetched — reuse doesn't change that label's meaning).

  **Q2 — does Part 7 build the orchestrator?** Yes, as Part 7A, not
  deferred to a separate part. Grep across every `test_part*.py`
  (see Verification above) confirms no script anywhere chains
  scrape→store→score→enrich together — the widest any existing script
  goes is two of those four stages. Part 7B (PDF layout) has no real
  per-listing dataset to lay out or test against until something
  assembles raw fields + fresh score + enrichment (fresh-or-reused) +
  new/changed status into one object per listing — that assembly *is*
  the orchestrator, so 7B cannot be built or tested first. Scoping the
  orchestrator as a separate "Part 6.5" was considered and rejected:
  orchestration and enrichment-persistence are the same piece of work
  (the orchestrator's whole job is deciding what to reuse vs. re-enrich,
  which is exactly the new `enrichment` table's read/write logic), so
  splitting them into different parts would just mean 7A depending on
  a not-yet-built prior part for no real isolation benefit. This also
  sets up Part 8 cleanly: 8B's GitHub Actions cron will invoke 7A's
  single entry point directly, and 8A's email send will attach 7B's PDF
  output at the end of that same run, rather than Part 8 needing to
  re-discover how to wire the pipeline together from scratch.

  **Next session (not this one): build 7A** — `storage/db.py` schema
  addition (`enrichment` table only) + a new orchestrator entry point
  (exact filename/location not yet decided — flagged here rather than
  guessed) wiring Parts 4/5/6 together per the above, tested against a
  real small-batch run before 7B starts. See Section 3's updated Part 7
  entry for the checklist form of this.
