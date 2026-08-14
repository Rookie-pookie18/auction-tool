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
  - [x] **7A — Pipeline orchestrator + enrichment persistence** — new,
        not previously planned as its own sub-part. Chains scrape → store
        (Part 4, unchanged) → score (Part 5, always recomputed fresh
        in-memory over that day's full batch — see decision log for why
        scores are never persisted) → Part 6's three enrichment modules,
        but only for listings that `needs_reenrichment()` says need it —
        reusing prior enrichment for everything else instead of
        re-spending Gemini/MCA/DuckDuckGo quota. **Storage-layer half DONE
        (2026-08-11): `enrichment` table + `get_enrichment()`/
        `needs_reenrichment()`/`upsert_enrichment()` in `storage/db.py`.**
        **Orchestrator itself now BUILT (2026-08-11, this session):
        `pipeline.py` at the repo root (filename/location decided + flagged
        this session — see that file's own module docstring for the
        reasoning), `run_pipeline()`. Confirmed on a real offline wiring
        smoke test only (synthetic data, monkeypatched network calls, 4
        passes — new/reuse/selective-reenrich/collision-skip all correct;
        see `pipeline.py`'s own `__main__` block). `test_part7a.py`
        written for the real small-batch confirmation this project's
        "never overstate testing" rule requires. **RUN FOR REAL
        (2026-08-11) — owner ran it on their own machine against live
        IBBI, pasted back the full raw output (not a summary), verified
        line-by-line: pass 1 20 new/20 enriched, pass 2 18 unchanged/18
        reused + 2 genuinely new, real Gemini timeout + quota-exceeded
        failures both flagged not crashed, no tracebacks. See "Part 7A
        confirmed against the real chain" in the decision log above.
        7A is DONE.**

  - [x] **7B — PDF layout + report categorization** — DONE (2026-08-11).
        `report/pdf.py`: `categorize_assembled()` + `generate_report()`
        (reportlab platypus), consuming 7A's assembled dataset directly,
        no second DB query. Confirmed for real in-sandbox (no network
        needed for this part) via `test_part7b.py`: real PDF built from
        synthetic data covering every category + edge case, read back
        with pypdf, all 17 expected substrings present, 0 crashes
        including on a listing with nothing populated at all. One real
        bug found + fixed via visual check: the ₹ glyph rendered as a
        solid black box in reportlab's default font — switched to "Rs."
        prefix. See decision log below for full detail.
- [ ] **Part 8 — Email delivery + GitHub Actions cron** — split per
      Section 0 rule 4: two genuinely different systems, each needing
      its own real-world confirmation.
  - [x] **8A — Email delivery** — DONE (2026-08-11), confirmed on a real
        send: owner ran `test_part8a.py` (Windows, real Gmail App
        Password), email arrived and opened correctly. One real bug
        found + fixed: `run_pipeline()` never closed its SQLite
        connection, which blocked deleting the throwaway test DB on
        Windows (harmless on Linux) — fixed with a `finally: conn.close()`.
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
        reasoning and precise implementation spec (Release setup steps,
        the MCA-data download step). **BUILT (2026-08-11, this session):
        owner caught a real second gap before this could actually work —
        see decision (31) — that decision's fix is now built alongside
        30's spec, not deferred:** `.github/workflows/daily_report.yml`
        (scrape→score→enrich→PDF→email on a cron schedule, decision
        (30)'s MCA-data download step, plus a commit-the-DB-back step per
        decision (31)); `main.py` (new — the real production entry point
        against `config.DB_PATH`/full `max_pages=None`, distinct from
        `test_part8a.py`'s throwaway-DB confirmation run — see that
        file's own docstring for why a separate script was needed);
        `.gitignore` (now tracks `data/auctions.db` instead of ignoring
        it — the whole point of decision (31)); `config.py` (`EMAIL_FROM`/
        `EMAIL_TO` now read an env var first, same pattern as
        `SMTP_PASSWORD`/`GEMINI_API_KEY`, since a hosted runner has no way
        to reach a "the owner edits config.py locally" value). **NOT YET
        CONFIRMED** — this sandbox has no network and can't push to
        GitHub or trigger real Actions runs (Section 0 rule 2), so, same
        pattern as every other real-network/real-infrastructure part in
        this project, this is built but unrun. 8B stays unticked until
        the owner: (1) pushes this to GitHub, (2) adds the four repo
        secrets (`GEMINI_API_KEY`, `SMTP_APP_PASSWORD`, `EMAIL_FROM`,
        `EMAIL_TO`) — README.md's new Part 8B section has the exact
        steps, (3) confirms the `mca-data-v1` Release still exists
        (decision (30)), (4) triggers one real run via the Actions tab's
        `workflow_dispatch` button (don't wait for the 06:00 IST
        schedule to find out if it works), and (5) confirms three things
        and reports back: the run went green, the email actually
        arrived, AND a new commit from `github-actions[bot]` updated
        `data/auctions.db` on `main` afterward — that third check is the
        one decision (31) exists for; a green run alone doesn't prove
        persistence is actually working.

**Known open issues:**
- Part 9 (owner request, 2026-08-14): the new `state` field
  (`scraper/ibbi._derive_state_from_location()`) is a best-effort keyword
  match against `location`'s free text, not a guarantee — a listing whose
  location genuinely never mentions a state gets `state=None` plus a
  flag, and the PDF shows "not stated in source data" rather than leaving
  the row blank (per the owner's "make state compulsory" request, this is
  "always shown, honestly" not "always populated" — those are different
  promises and this only makes the first one true). Also: when a
  location string mentions more than one recognized state/UT (rare —
  e.g. a registered-office state alongside the asset's actual state), the
  first match by scan order wins and it's flagged as ambiguous, not
  resolved automatically. Not cross-checked yet against `INCLUDED_
  LOCATIONS` (the Part 9 location filter above) — that filter still
  matches keywords against raw `location` text, not this new `state`
  field; switching Jharkhand/Gujarat/Odisha to match on `state` directly
  would be more precise than substring-matching `location`, worth doing
  next if the raw-text matching turns out too loose in practice.
- Part 9 (owner request, 2026-08-14): the "Delhi NCR" keyword list in
  `config.py`'s new `INCLUDED_LOCATIONS` (`delhi, gurugram, gurgaon,
  noida, ghaziabad, faridabad`) is a Claude-picked reasonable default,
  NOT the NCR Planning Board's full official district list (which also
  reaches into further Haryana/UP/Rajasthan districts). Owner hasn't
  confirmed this is the intended scope — revisit if it's cutting out
  locations that should count as NCR. Also: a listing whose `location`
  is `None` (details PDF not parsed yet) is excluded from the report as
  "unknown", not held back for a later run — if the owner would rather
  see those included-with-a-flag instead of excluded, that's a one-line
  change in `pipeline.filter_assembled_by_location()`.
- Part 8A real full run (2026-08-11, owner's Windows machine): PDF
  confirmed correct in production, not just synthetic tests — all four
  sections rendered in the right order including a clean "None today"
  for an empty Watchlist changes section, and the Rs.-prefix fix held
  with no glyph issues. Two real, expected conditions surfaced, neither
  a code bug: (1) 19/20 Gemini narrative calls failed with a real HTTP
  429 quota-exceeded error — likely the free tier's *daily* cap, since
  this run's 20 calls came on top of earlier sessions' `test_part6a`/
  `test_part7a` calls the same account already made; each failure was
  flagged per-listing exactly as designed, batch did not crash. (2) MCA
  lookups mostly skipped with "no local MCA data file for state X" —
  expected, since the 15 confirmed state CSVs were deliberately kept out
  of the zip (decision (29)) and this particular machine hasn't
  downloaded them yet. **Not a new problem to solve separately** — 8B's
  already-decided runtime-download-from-GitHub-Release step (decision
  (30)) is exactly what wires MCA data onto any machine automatically;
  this resolves itself once 8B is built, no separate fix needed.
- Part 8A build (2026-08-11): confirmed on a real Windows send — email
  arrived correctly. Real bug found during that run + fixed:
  `run_pipeline()` (`pipeline.py`) never closed its SQLite connection,
  which is harmless on Linux but blocked Windows from deleting the
  throwaway test DB afterward (`PermissionError`, file still in use) —
  fixed by wrapping the function body in `try`/`finally: conn.close()`.
  Re-confirmed offline afterward: all 4 of `pipeline.py`'s own smoke-test
  passes still pass with no regressions. Resolved.
- Part 7B (2026-08-11): `combined_score()` (`report/pdf.py`) is a plain
  average of whatever 5A/5B/5C partial scores exist — an explicitly-labeled
  placeholder, not the real weighted ranking (`config.SCORE_WEIGHTS` is
  still all `None`). The PDF itself says so under "Top-scored"; worth
  revisiting once the owner sets real weights — swap the averaging logic
  in `combined_score()` for the real weighted sum at that point. Also: a
  listing can appear in more than one section (e.g. top-scored AND closing
  soon) — a deliberate default (see `report/pdf.py`'s module docstring),
  not a bug, but flagged here in case the owner would rather de-duplicate.
- Part 7A build (2026-08-11): `data/*.db` was never in `.gitignore` (neither
  the real DB nor test_part7a.py's throwaway test DB) — added as a small
  precaution, same spirit as decision (30)'s `.gitignore` fix. Also: a
  "collision" listing now deliberately skips Part 6 enrichment for that
  run (see pipeline.py's module docstring) rather than risk writing into
  another listing's enrichment row — untested against a REAL collision
  (can't be forced synthetically, same as storage/db.py's own caveat),
  only against a forced-status unit test; worth double-checking if a real
  one ever actually occurs.
This file is now ~1030 lines, past the ~500-550
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
- **(31) data/auctions.db persistence across ephemeral runners —
  real gap caught by the owner (2026-08-11, before 8B build started this
  session):** decision (30) fully specs how MCA *reference* data gets
  onto a hosted runner, but says nothing about the pipeline's own working
  *state* — `data/auctions.db` — which is a completely different problem
  decision (30) never actually covered. GitHub-hosted runners are
  ephemeral: a fresh VM every run, nothing on the runner's local disk
  carries over to the next one. `data/auctions.db` has been gitignored
  since Part 7A (see that gitignore entry's own original comment — "keep
  local dev/test DBs out of git"), which was the right call for a
  chat-session/local-dev workflow but is silently fatal for a scheduled
  job: with the DB never persisting anywhere, every single cron run would
  `git checkout` a repo with no DB, `get_connection()` would create a
  brand-new empty one, and `store_records()` would see every listing —
  including ones scored/enriched dozens of times before — as `new`. That
  doesn't just mean a noisier report; it means Part 7A's whole
  `needs_reenrichment()` reuse mechanism (the entire point of the
  `enrichment` table) would never fire on a scheduled run, and a full
  day's Gemini/MCA/news quota would be re-spent from scratch every
  morning on listings the tool already had a complete write-up for.
  **This would have made 8B technically "wire up successfully" while
  silently defeating the reuse mechanism the last several parts were
  built around — exactly the kind of gap this project's "confirm the
  real chain, don't just confirm it doesn't error" rule exists to catch.**

  **Options considered:**
  - **`actions/cache`** — free, no extra service, but explicitly NOT
    designed for state that must survive indefinitely: caches can be
    evicted (GitHub's own eviction policy removes caches unused for 7
    days, and enforces a 10GB-per-repo total cap with oldest-first
    eviction beyond that) and a cache write on one run isn't guaranteed
    visible to a later run the way a git commit is. Section 1's own
    "automatic every morning" must-have makes a fine, silent, and
    infrequent chance of a lost cache too risky to build the reuse
    mechanism on — rejected for the same "must actually be reliable, not
    just usually work" spirit as decision (30) rejecting a self-hosted
    runner.
  - **Commit `data/auctions.db` back to the repo after each run — chosen.**
    The workflow's own `GITHUB_TOKEN` already has repo write access once
    granted `permissions: contents: write`; a plain `git add`/`commit`/
    `push` at the end of the run is the simplest mechanism that offers a
    real persistence guarantee (git history), not a best-effort one, and
    needs no new service/secret beyond what 8B already requires. Trade-
    off, stated plainly: this adds one commit per day to `main`'s
    history, forever — a deliberate, accepted cost for a personal-tool
    repo, not an oversight. (A future refinement, not built now since it
    wasn't asked for and adds complexity for a cosmetic benefit: park the
    DB on a separate orphan branch instead of `main`, so daily DB commits
    don't clutter the code-change history. Noted here for the record,
    not acted on.)

  **Implementation (built this session, see 8B's own checklist entry in
  Section 3 for the exact file list):** `.gitignore`'s blanket
  `data/*.db` rule is replaced with `data/test_*.db` (only the throwaway
  test DBs need to stay ignored — the real DB now needs to be tracked,
  the opposite of what the Part 7A-era rule did); the workflow's last
  step commits `data/auctions.db` with `[skip ci]` in the message and a
  no-op guard (`git diff --cached --quiet`) so a run with zero DB changes
  doesn't create an empty commit; `concurrency: {group: ..., cancel-in-
  progress: false}` at the workflow level queues rather than cancels a
  second run (e.g. a manual `workflow_dispatch` fired close to the
  schedule), since two overlapping runs racing to push the same file is
  exactly the kind of thing that would corrupt this mechanism.

  **A second, smaller gap found while building the fix (same session,
  same "check the actual mechanism, don't assume" instinct that caught
  the first one):** `test_part8a.py` was never the right script to point
  a cron job at — it deliberately uses a throwaway tempfile DB (correct
  for a one-off send confirmation, wrong for a job that needs its DB to
  persist) and `max_pages=1` (correct for a small confirmation run, wrong
  for a real daily pass over the site's full listing set). No production
  entry point actually existed yet. Fixed: new `main.py` at the repo
  root, run against `config.DB_PATH`/`max_pages=None`, is what the
  workflow actually calls — `test_part8a.py` is untouched and keeps its
  original one-off-confirmation job.

  **A third, related gap, same root cause (config.py is a tracked file,
  a hosted runner can't receive "the owner edits it locally"):**
  `EMAIL_FROM`/`EMAIL_TO` were plain `None` in `config.py`, meant to be
  filled in locally without being committed — that has no path onto a
  GitHub-hosted runner at all. Fixed: both now read an env var first
  (`os.environ.get(...)`), the same pattern `GEMINI_API_KEY`/
  `SMTP_PASSWORD` already used — supplied via repo secrets in the
  workflow, or a local `.env`/shell export, either way no change to how
  the owner sets them locally.

  **Testing this session:** no network available in this sandbox
  (Section 0 rule 2, as always) — can't push to GitHub or trigger a real
  Actions run. What WAS re-confirmed offline: `pipeline.py`'s own 4-pass
  synthetic wiring smoke test still passes with no regressions from the
  `config.py`/`.gitignore` changes; `main.py` and `config.py` both
  import/compile cleanly; `main.py` correctly exits non-zero naming every
  missing required setting when run with none set (matches
  `test_part8a.py`'s own missing-config check, same pattern). **None of
  this confirms the real thing decision (31) exists to fix** — that the
  DB genuinely round-trips across two separate scheduled runs on a real
  hosted runner — which needs the owner to push this, run it for real
  (twice, ideally, to see reuse actually happen on the second run the
  same way `test_part7a.py`'s pass 2 proved it locally), and report back.
  See 8B's checklist entry in Section 3 for the exact confirmation steps.

---

## 4. Last updated
*(Overwrite these fields only — see Rule 5 in Section 0.)*

- **Position:** **Part 9 (owner feature requests, post-Phase-1) — 4 of 5
  BUILT, none yet confirmed by the owner (2026-08-14, same session
  continuing):** owner asked to continue straight to items 4 (deeper
  research / detail links) and 5 (compulsory state) after items 2/3
  (page numbers, location filter) from earlier this session. Only item 1
  (exclude car/loan-recovery listings) remains undone — owner hasn't
  asked for it yet since real "loan recovery" auctions still don't exist
  in this pipeline (BAANKNET, the source that would have them, remains
  unbuilt — owner declined to build it earlier this session, see
  decision log).
  **Built this round:** (1) `scraper/ibbi.py` — new `state` field on
  `IBBIRecord`, derived from `location` (never independently scraped —
  the details PDF has no dedicated State field) by
  `_derive_state_from_location()`: 28 states + 8 UTs, `\b`-bounded regex
  per name/variant (word-boundaries matter — a naive substring check
  would false-positive "Goa" inside "Goalpara", a real Assam district;
  confirmed this exact case is caught correctly), common alternate
  spellings included (Orissa→Odisha, Pondicherry→Puducherry,
  Uttaranchal→Uttarakhand). None + a flag when no state name is found;
  more-than-one-match is flagged as ambiguous rather than silently
  resolved. Wired into `enrich_record_with_details()` right after
  `location` is parsed. (2) `storage/db.py` — new `state TEXT` column:
  added to `SCHEMA`, `_LISTINGS_COLUMN_MIGRATIONS` (so it `ALTER TABLE`s
  onto the owner's already-committed `data/auctions.db`, same pattern as
  the 2026-08-13 possession_status/land_classification migration), and
  all three `upsert_listing()` write paths (INSERT new / UPDATE unchanged
  / UPDATE changed). (3) `pipeline.py` — reused-from-DB block now also
  pulls `rec.state = existing.get("state")` alongside `location`/`cin`/
  etc. for listings whose details PDF wasn't re-fetched this run. (4)
  `report/pdf.py` — `_facts_table()` now always shows a "State" row
  (`raw.get("state") or "not stated in source data"` — never blank, never
  omitted, per the owner's "make state compulsory" ask: the row's
  presence is compulsory, the *value* still depends on what the source
  text actually says). Also: new `_pdf_link()` helper renders real
  clickable `<link href=...>` hyperlinks (not just printed URL text) for
  `details_pdf_url`, `notice_pdf_url`, and — new — `auction_platform_url`
  labeled "Auction platform (bidding, possible photos)" since that's
  where photos would realistically live if published anywhere (IBBI's
  own notice/details PDFs are legal/text documents, no photos found in
  any sample so far — flagged to the owner in chat, not something this
  session's code can manufacture). URL escaping handles a literal `&` in
  a query string (e.g. an MSTC platform URL with `?id=1&lot=2`) so it
  doesn't break Paragraph's XML parser.
  **Testing (offline only, no network needed):** `test_part7b.py`
  re-run unchanged, still passes (4-page real PDF, all 17 prior
  assertions hold) — confirms the new State row/links didn't break
  existing rendering. Separately confirmed: (a) `_derive_state_from_
  location()` against 7 synthetic strings incl. the Goa/Goalpara
  false-positive guard, an ambiguous two-state case, and `None` — all
  correct. (b) A real, direct SQLite round-trip through all three
  `upsert_listing()` write paths (insert/unchanged/changed) with `state`
  populated — no placeholder/column-count mismatch, `state` persisted and
  read back correctly. (c) `storage/db.py`'s and `pipeline.py`'s own
  offline synthetic smoke-tests (`python storage/db.py`, `python
  pipeline.py`) both still pass with no regressions. (d) A synthetic
  details-PDF fixture (real text from Scotts Garments Ltd, one of the 4
  original Part 3C fixtures) run through `parse_details_pdf()` AND the
  full `enrich_record_with_details()` — correctly extracted `location`
  and derived `state="Karnataka"`. (e) A hand-built two-listing PDF
  (one with state/links populated, one fully empty) read back with
  `pypdf`: "State"/"Punjab"/"not stated in source data" all present as
  expected, AND — checked via `page.get("/Annots")`, not just text
  extraction — real clickable link annotations with correct `/URI`
  values present for all three link types, including the `&`-containing
  platform URL surviving the escape/unescape round-trip intact.
  **NOT YET CONFIRMED against real IBBI data** — same as the item-2/3
  batch earlier this session, owner is copy-pasting changed files
  directly rather than receiving a new zip; a real `main.py` run (local
  or Actions cron) against live data, on a DB that already has the old
  schema, is what actually confirms the `state` column migration path
  for real (only tested against a fresh throwaway DB above, not an
  ALTER TABLE onto an existing populated one).
  **Next: owner to copy in the 6 changed files
  (`scraper/ibbi.py`, `storage/db.py`, `pipeline.py`, `report/pdf.py`,
  plus item-2/3's already-copied `config.py`/`main.py`), commit, then
  either confirm on a real run or move to item 1 (car/loan-recovery
  exclusion) — the one Part 9 item still undone.**
  **Previous position (2026-08-14, same session, earlier), kept for
  context — Part 9 (owner feature requests, post-Phase-1) BUILT,
  not yet confirmed by the owner:** two of the
  owner's five requested changes done this session (page numbers +
  location filter); the other three (exclude car/loan-recovery listings,
  compulsory `state` field, per-listing deep-link/photos research) are
  still pending, owner explicitly asked to do these two first.
  **Built:** (1) `report/pdf.py` — `_NumberedCanvas` (standard reportlab
  two-pass technique: `showPage()` stashes each finished page instead of
  flushing it, `save()` replays every stashed page once the true total
  page count is known, drawing "Page X of Y" bottom-right on each) wired
  in via `generate_report()`'s `doc.build(..., canvasmaker=
  _NumberedCanvas)` — no flowable/layout changes needed elsewhere. (2)
  New `config.py` section `LOCATION_FILTER_ENABLED` /
  `INCLUDED_LOCATIONS` (6 owner-specified regions: Delhi NCR, Jharkhand,
  Rajpura/Punjab, Gujarat, Odisha, Sikandrabad/UP — keyword lists, not
  exact-match, case-insensitive substring against the scraped `location`
  free text) plus new `pipeline.filter_assembled_by_location()`, called
  from `main.py` **after** `run_pipeline()` returns, **before**
  `generate_report()`/`categorize_assembled()`. Deliberately kept OUT of
  `run_pipeline()`/storage — the database still keeps every listing
  regardless of location; only the PDF/email report is restricted. Every
  excluded listing is counted, not silently dropped: split into
  `excluded_other_location` (location known, no keyword match) vs.
  `excluded_unknown_location` (location still `None` — details PDF not
  parsed yet), both printed by `main.py` and shown in the PDF header via
  a new `run_summary["location_filter"]` block threaded through
  `build_story()`.
  **Testing (offline only, no network needed for either change — same
  reasoning as Part 7B):** `test_part7b.py` re-run unchanged and still
  passes (4-page real PDF, all prior assertions hold) — confirms neither
  change altered `categorize_assembled()`'s existing default behavior.
  Separately confirmed: (a) `report/pdf.py`'s own `__main__` smoke test
  still renders a real PDF; read it back with `pypdf` and verified pages
  literally read "Page 1 of 3" / "Page 2 of 3" / "Page 3 of 3". (b)
  `filter_assembled_by_location()` run directly against synthetic
  location strings covering all 6 target regions (incl. the
  "Sikandarabad" spelling variant) plus one out-of-scope location and one
  `None` — all landed in the correct one of the three returned buckets.
  **NOT YET CONFIRMED against real IBBI data or a real GitHub commit** —
  owner is copy-pasting these 4 changed files (`config.py`, `pipeline.py`,
  `main.py`, `report/pdf.py`) into their repo directly rather than
  receiving a new zip this session; next real `main.py` run (local or via
  the Actions cron) is what actually confirms this against live data.
  **Next: owner to commit, then either confirm this batch on a real run,
  or continue straight to the remaining Part 9 items (car/loan-recovery
  exclusion, compulsory state, deep-link/photos).**
  **Previous position (2026-08-11, new session), kept for context: Part
  8B BUILT, not yet confirmed:** owner opened this session by flagging a real gap in the
  existing spec before any 8B code got written: decision (30) fully
  covers getting MCA reference data onto a GitHub-hosted runner, but
  never addressed `data/auctions.db` itself persisting across runs —
  without that, every scheduled run would see all listings as "new" and
  burn a full day's Gemini/MCA/news quota re-enriching things Part 7A's
  reuse mechanism already knew, silently defeating the point of that
  mechanism while the workflow itself still ran "successfully." See
  decision (31) for the full reasoning, options considered, and two
  smaller related gaps found while fixing it (no real production entry
  point existed yet; `EMAIL_FROM`/`EMAIL_TO` had no path onto a hosted
  runner). **Built this session:** `.github/workflows/daily_report.yml`
  (decision (30)'s MCA-data-download spec + decision (31)'s commit-DB-
  back step, schedule + `workflow_dispatch`, `concurrency` guard,
  `permissions: contents: write`); `main.py` (new production entry
  point — real DB, real `max_pages=None`, distinct from
  `test_part8a.py`); `.gitignore` (`data/auctions.db` now tracked,
  `data/test_*.db` still ignored); `config.py` (`EMAIL_FROM`/`EMAIL_TO`
  now env-var-driven); `README.md` (new Part 8A/8B setup sections).
  **NOT YET CONFIRMED** — no network in this sandbox, so, same pattern as
  every other real-infrastructure part in this project, this needs the
  owner to push it, add the four repo secrets, trigger one real run via
  `workflow_dispatch`, and confirm three things: the run went green, the
  email arrived, AND a new `github-actions[bot]` commit updated
  `data/auctions.db` on `main` afterward. **8B stays unticked in Section
  3 until that real confirmation comes back — see that checklist entry
  for the exact steps, and README.md's new Part 8B section for the
  owner-facing version of the same steps.** Ideally run twice before
  calling it fully confirmed (same reasoning as `test_part7a.py`'s pass
  2): a second run is what actually proves reuse survived the round-trip,
  not just that the first run didn't crash.
  **Previous position (2026-08-11, same session-day, earlier), kept for
  context — Part 8A real full-run confirmed in production (2026-08-11,
  same session, after the send confirmation below):** owner shared the
  actual generated `test_part8a_report.pdf` (not just console output) —
  verified correct: all four sections (Top-scored / Closing soon / New
  today / Watchlist changes) render in the right order, empty sections
  show a clean "None today", and the `Rs.` prefix fix holds with no
  glyph rendering issues in a real production PDF. Two real, expected
  conditions found, neither a code bug (see Known Open Issues, Section
  3, for full detail): Gemini hit a real daily quota 429 on 19/20
  narrative calls (flagged per-listing, batch did not crash, exactly as
  designed); MCA lookups mostly skipped since this machine hasn't
  downloaded the 15 confirmed state CSVs yet (deliberately kept out of
  the zip, decision (29)). **Owner confirmed this resolves itself once
  Part 8B's already-decided runtime-download-from-GitHub-Release step
  exists — no separate MCA-data fix needed, not treating this as new
  work.** **Part 8A fully done. Next: Part 8B (GitHub Actions cron)** —
  build directly from decision (30)'s spec below.
  **Previous position (2026-08-11, earlier same session), kept for
  context: Part 8A (email delivery) is now DONE and confirmed (real
  send, same session continuing from the build below):** owner ran `test_part8a.py` for real on Windows (Gmail
  address `dangsidak5@gmail.com`, real App Password) — small real
  pipeline pass (max_pages=1: 20 new / 0 unchanged / 0 changed, all 20
  freshly enriched), real PDF built (54,539 bytes), real email sent and
  **confirmed arrived and opened correctly** (owner-confirmed). **One
  real bug found + fixed:** `pipeline.py`'s `run_pipeline()` opened a
  SQLite connection via `get_connection()` but never closed it — no
  effect on Linux (files can be removed while a handle is open) but on
  Windows this left the DB file locked, so `test_part8a.py`'s own
  throwaway-DB cleanup failed with `PermissionError: ... being used by
  another process` right after the email had already sent successfully
  (the crash was in cleanup, after the real send — the send itself
  worked). Fixed: the whole function body now runs inside
  `try:`/`finally: conn.close()`. Re-confirmed offline afterward: all 4
  of `pipeline.py`'s own synthetic wiring-smoke-test passes (Part 7A's
  original coverage) still pass with no regressions from the
  reindent/refactor. `test_part8a.py`'s own cleanup also hardened
  (non-fatal `try`/`except OSError` around the temp-file removal) as a
  belt-and-suspenders fallback, though the real fix is in `pipeline.py`.
  **Part 8A ticked in Section 3. Next session: Part 8B (GitHub Actions
  cron)** — full implementation spec (Option B, runtime download from
  the already-live `mca-data-v1` GitHub Release) was already decided
  2026-08-11, see decision (30) below, ready to build directly from it.
  **Previous position (2026-08-11, earlier same session), kept for
  context: Part 8A (email delivery) BUILT, not yet confirmed:**
  `email_delivery/smtp_send.py` — `send_report_email()` sends the report
  PDF as an attachment via Gmail SMTP (STARTTLS, port 587) using
  `smtplib`/stdlib `email`, plain-text body from `build_summary_text()`
  (new/changed/unchanged + enrichment reuse counts + per-section report
  counts + up to 10 scrape-problem lines). `config.py` updated:
  `SMTP_HOST` now defaults to `"smtp.gmail.com"` (Gmail confirmed
  provider, Section 2); `EMAIL_FROM`/`EMAIL_TO` stay `None`/TBD, owner
  fills in locally; new `SMTP_PASSWORD` reads `SMTP_APP_PASSWORD` from
  the environment/`.env`, same never-hardcoded pattern as
  `GEMINI_API_KEY` — no new `.gitignore` entry needed, `.env` already
  covered. **Deliberately does NOT flag-and-continue like Parts 6A-6C**
  — this is the last step of a run with nothing after it to protect, so
  a real send failure raises instead of being silently swallowed (see
  module docstring "FAILURE HANDLING" for the full reasoning). Config
  validation (`_require_email_config()`) checked in-sandbox with a
  synthetic call — confirmed it raises naming exactly which setting(s)
  are missing rather than letting `smtplib` fail confusingly partway
  through connect/login/send; `build_summary_text()` also checked
  in-sandbox with synthetic run-summary data, output looked correct.
  **Neither of those is a real send confirmation** — no network in this
  sandbox (Section 0 rule 2), so, same as every other AI/network-layer
  part, `test_part8a.py` (matching the `test_part6a/b/c.py`/
  `test_part7a.py` convention) is written but **has NOT been run**. 8A
  stays unticked in Section 3 until the owner: (1) turns on Gmail 2-Step
  Verification and generates an App Password at
  `https://myaccount.google.com/apppasswords`, (2) sets `EMAIL_FROM`/
  `EMAIL_TO` in `config.py` and `SMTP_APP_PASSWORD` locally (`.env` or
  shell), (3) runs `python test_part8a.py` (small real pipeline pass +
  real PDF + real send) and pastes back the full output, including
  confirming the email actually arrived. **Next session (not this one):
  get that real send confirmed, tick 8A, then build 8B** (GitHub Actions
  cron) — its full implementation spec (Option B, runtime download from
  the already-live `mca-data-v1` GitHub Release) was already decided
  2026-08-11, see decision (30), and is ready to build once 8A is
  confirmed.
  **Previous position (2026-08-11, earlier same day), kept for context:
  Part 7B (PDF layout + report categorization) is now
  DONE and confirmed (2026-08-11, this session, new session after Part
  7A's real-chain confirmation below):** `report/pdf.py` —
  `categorize_assembled()` splits `run_pipeline()`'s assembled dataset
  into top-scored / closing-soon / new-today / watchlist-changes (per
  Section 1's ordering) plus a collisions "flagged for review" section;
  `generate_report()` renders it via reportlab platypus to
  `config.REPORT_OUTPUT_DIR`. Confirmed for real, in-sandbox, no network
  needed (PDF layout has no external dependency): `test_part7b.py` built
  synthetic data covering every category + edge case, asserted correct
  categorization, then read the actual generated PDF back with `pypdf`
  and asserted 17 expected substrings all present. One real bug found
  visually (not by the text-extraction assertions) and fixed: the ₹ glyph
  isn't in reportlab's default font and rendered as a solid black box —
  switched to a "Rs." prefix. **`combined_score()`'s ranking is an
  explicitly-flagged placeholder** (plain average of available 5A/5B/5C
  partials) since `config.SCORE_WEIGHTS` is still all `None` — see
  Known Open Issues (Section 3) and "Part 7B built and confirmed" in the
  decision log below for full detail. **Part 7 (both sub-parts) is now
  fully done. Next action: Part 8A (email delivery) — needs the owner's
  Gmail SMTP app-password supplied locally, then a real send test.**
  **Previous position (2026-08-11, earlier same day), kept for context:
  Part 7A's orchestrator is now BUILT:
  `pipeline.py` (repo root — filename/location decided + flagged this
  session, see that file's own module docstring), `run_pipeline()`,
  chains scrape (Part 3C/5B PDF enrichment included, unconditional) →
  `storage.db.store_records()` → fresh in-memory `score_batch_5a/5b/5c`
  → per-listing `needs_reenrichment()` → Part 6's three modules only for
  the subset that needs it → `upsert_enrichment()`/`get_enrichment()`
  reuse → one assembled per-listing dataset, exactly per the Part 7
  architecture decisions on record below.** Confirmed on a real offline
  wiring smoke test only (4 passes, synthetic data, monkeypatched network
  calls — see "Part 7A orchestrator built" in the decision log above for
  the full breakdown, including the new collision-skip handling found and
  fixed while wiring this). **`test_part7a.py` (real-network confirmation,
  matching the test_part6a/b/c.py convention) is written but NOT YET RUN**
  — this sandbox has no network, ever (Section 0 rule 2), so the real
  small-batch pull this project's "never overstate testing" rule requires
  has to happen on the owner's own machine. **7A therefore stays
  unticked in Section 3 until the owner runs `python test_part7a.py` and
  pastes back the output — that is the single next action.** 7B (PDF
  layout) still can't start until 7A is confirmed against the real chain.
  Small side fix this session: `data/*.db` added to `.gitignore` (was
  never covered, neither the real DB nor the new test DB) — flagged in
  Known Open Issues (Section 3) rather than assumed harmless.
  **Previous position (2026-08-11, earlier same session-day), kept for
  context: Part 7A's storage-layer half is now DONE:** `storage/db.py`
  has the new `enrichment` table
  (`listing_key`, `gemini_narrative_json`/`gemini_generated_at`,
  `mca_data_json`/`mca_lookup_attempted`/`mca_looked_up_at`,
  `news_data_json`/`news_flags_json`/`news_searched_at`, plus
  `details_pdf_parsed_at_enrich`/`notice_pdf_parsed_at_enrich`) and
  `get_enrichment()`/`needs_reenrichment()`/`upsert_enrichment()`,
  confirmed on a real offline smoke test (6 assertions, synthetic data,
  no network — see that test's own print output for the exact caveat).
  This session started as a design review of the 2026-08-10 Part 7
  architecture decisions (no code, per that session's own instruction)
  and found one real gap in how re-enrichment gets triggered — see
  "Part 7A enrichment-trigger refinement" in the decision log above for
  the full reasoning — which the owner then asked to have implemented.
  **Previous-previous position (2026-08-11, earlier same day), kept for
  context:
  PART 6B FULLY CONFIRMED, 15 states confirmed
  owner-side; Part 8B storage strategy now FINALIZED (2026-08-11).**
  **The `mca-data-v1` GitHub Release is now LIVE (2026-08-11)** — repo

  created (`Sidak-dang/auction-tool`, private), code pushed to `main`
  (with a `.gitignore` fix applied first — see below), and the Release
  itself published with `mca_company_master.zip` (162MB / 169,982,357
  bytes) attached as its one asset, exactly per decision (30)'s spec.
  8B's runtime-download workflow step can now be built and tested
  against a real live asset, not a hypothetical one. One real gap
  surfaced during this: decision (30) Step 4 said a `.gitignore`
  entry for `data/mca_company_master/*.csv` had been added, but the
  zip handed off for this session did not actually contain a
  `.gitignore` file — a real doc/zip mismatch, not just an
  owner-side slip. Caught before any push happened (owner's local
  folder had real state CSVs sitting in it with nothing to stop git
  from tracking them); fixed by creating `.gitignore` locally with
  Step 4's exact rule before the first successful commit, so no state
  CSV ever entered git history. `.gitignore` now exists locally on the
  owner's machine and in the pushed repo; **flagging here because the
  zip this session started from should have had it and didn't — worth
  double-checking the zip-building step that drops `.gitignore` isn't
  silently skipping it.** All
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

- Part 7A enrichment-trigger refinement (2026-08-11, same-day chat-based
  design review of the decision above, owner-approved): the
  2026-08-10 decision gated re-enrichment purely on `store_records()`'s
  status (`new`/`changed`/no row yet). Real gap found by reading
  `ai_analysis/gemini_narrative.py`'s `_build_prompt()` against
  `storage/db.py`'s `TRACKED_FIELDS`: the prompt (and `mca_lookup.py`/
  `news_search.py`) depend on `cin`/`location`/`possession_status`/
  `land_classification`/`plot_area_mentions`, none of which are
  `TRACKED_FIELDS` — those only cover `reserve_price`/`auction_date`/
  `notice_date`/`emd_due_date`. Those enrichment-input fields are
  populated by `scraper.ibbi.enrich_record_with_details()`/
  `enrich_record_with_notice()`, gated by `IBBIRecord.details_pdf_parsed`/
  `notice_pdf_parsed` — and Part 5B's own real-run numbers (0/20
  `possession_status`, 8/20 `land_classification`, several unparseable
  notice PDFs that day) confirm these genuinely do resolve from missing
  to known on a later day for a listing whose tracked fields never
  change in between. Under the original rule, such a listing would be
  reported `unchanged` forever after its first enrichment and would keep
  reusing enrichment generated back when `cin`/`location`/
  `possession_status` were still null — silently, no record it happened.
  **Fix, implemented this session:** `enrichment` table gets two more
  columns, `details_pdf_parsed_at_enrich`/`notice_pdf_parsed_at_enrich`
  — snapshots of those two flags at the moment a row was last written.
  `needs_reenrichment()` now also returns `True` when either flag has
  flipped `False → True` since the stored snapshot, on top of (not
  instead of) the original `new`/`changed`/no-row-yet rule. Still purely
  additive — no changes to `listings`/`listing_history`/`collisions`,
  matching the 2026-08-10 decision's own stated goal. Confirmed on a
  real offline smoke test this session (`storage/db.py`'s `__main__`,
  6 assertions including the exact gap scenario: `unchanged` status +
  `details_pdf_parsed` flipping False→True mid-life). **Scope of what
  was actually built this session: the storage-layer half of 7A only**
  (`enrichment` table + `get_enrichment()`/`needs_reenrichment()`/
  `upsert_enrichment()`) — the orchestrator that will actually call
  these (scrape→store→score→enrich chaining, its own filename/location)
  is still not built. Not overstating this as 7A being done.
- Part 7A orchestrator built (2026-08-11, later same day, new session):
  built the piece flagged as still missing above. **Filename/location
  decided (flagged, not guessed, per Section 0 rule 1):** `pipeline.py`
  at the repo root, alongside the existing `test_part*.py` scripts —
  not inside `scraper/`/`storage/`/`scoring/`/`ai_analysis/`, since this
  is the one file that imports and chains all four together and doesn't
  belong to any single existing package; `run_pipeline()` is the function
  Part 8B's cron will eventually call directly. Implements exactly the
  chain the two prior decision-log entries above spec'd: full scrape
  (`scraper.ibbi.scrape_all_pages`) → Part 3C/5B PDF enrichment
  (unconditional every run, same as before — NOT gated by
  `needs_reenrichment()`, since scoring itself depends on the fields
  those two populate) → `storage.db.store_records()` → fresh in-memory
  `score_batch_5a`/`5b`/`5c` → per-listing `needs_reenrichment()` →
  Part 6's three modules re-run only for the subset that needs it (routed
  through the *existing* `generate_narratives_for_batch()`/
  `enrich_batch_with_mca()`/`enrich_batch_with_news()` batch helpers, so
  their already-confirmed pacing/retry logic from Parts 6A/6B/6C is
  reused rather than reimplemented) → `upsert_enrichment()` for the
  re-enriched subset, `get_enrichment()` reuse for everything else →
  one assembled dict per listing (raw scraped fields + that run's fresh
  score + enrichment, fresh-or-reused, each still carrying its own
  module's honesty/flags exactly as written) — this assembled list is
  `run_pipeline()`'s return value and what Part 7B will consume next.

  **Real gap found while wiring this, not previously decided anywhere
  (flagged here rather than guessed past silently):** a `"collision"`
  status means the incoming record's `listing_key` hash matches an
  *existing, different* listing (near-duplicate identity fields — see
  `storage/db.py`'s own module docstring on the collision path) — the
  incoming row goes to the `collisions` table, nothing in `listings` is
  touched. Running that shared `listing_key` through
  `needs_reenrichment()`/`upsert_enrichment()` would have silently
  written this incoming, unrelated record's AI narrative into the
  enrichment row that actually belongs to the *other*, already-stored
  listing sharing that key — corrupting a real listing's enrichment
  data. **Fix:** collisions are still assembled into the run's output
  (visible, scored, flagged) but skip Part 6 entirely this run —
  `enrichment` is `None` with an explanatory flag, never a guess at
  whose row to touch. Resolves normally once the collision itself is
  resolved (gets its own real `listing_key` on a later run).

  **Testing, per this project's "never overstate testing" rule:** an
  offline wiring smoke test (`pipeline.py`'s own `__main__` block —
  synthetic records, every network-touching function monkeypatched, same
  pattern as every other module's `__main__` in this file) ran 4 passes
  and all passed: (1) two brand-new listings both score + freshly
  enrich, (2) an identical re-scrape comes back `unchanged` and both
  reuse enrichment with zero re-spent Gemini/MCA/DuckDuckGo calls, (3) a
  simulated reserve-price drop on one listing re-enriches only that one,
  the other still correctly reuses, (4) a forced `"collision"` status
  (can't force a real hash collision synthetically, same caveat
  `storage/db.py`'s own test notes) skips enrichment for that listing
  only, with the explanatory flag present, and leaves the other listing
  completely unaffected. **This confirms the wiring logic only — it does
  NOT confirm the real chain** against a live IBBI scrape / real Gemini
  call / real MCA CSV / real DuckDuckGo query, which is exactly the kind
  of network-dependent confirmation this sandbox cannot do (Section 0
  rule 2, no network, ever). `test_part7a.py` was written, matching the
  exact `test_part6a/b/c.py` convention (real network, small `MAX_PAGES`,
  runs the pipeline twice against a throwaway DB to prove real
  same-machine reuse, prints everything Part 7B would consume, asks the
  owner to paste output back) — **but has NOT been run**, so Part 7A
  stays unticked in Section 3 until the owner runs it for real and
  confirms. Small side fix noticed while building this: `data/*.db` was
  never in `.gitignore` (neither the real DB nor `test_part7a.py`'s
  throwaway one) — added as a small precaution, same spirit as decision
  (30)'s own `.gitignore` fix; flagged in Known Open Issues rather than
  silently assumed harmless.

  **Next session (not this one): run `test_part7a.py` for real** (owner's
  machine, `GEMINI_API_KEY` set, network) and paste the output back so
  Part 7A can actually be marked confirmed and Part 7B (PDF layout) can
  start — 7B has no real per-listing dataset to build against until 7A
  is confirmed working against the live chain, not just synthetic data.
- **Part 7A confirmed against the real chain (2026-08-11, later same day,
  new session):** owner ran `test_part7a.py` for real (own machine,
  `GEMINI_API_KEY` set, real IBBI scrape) and pasted the full raw console
  output back (not a summary). Verified line-by-line against this file's
  own checklist:
  - Pass 1: `{'new': 20, 'unchanged': 0, 'changed': 0, 'collision': 0}`,
    all 20 enriched fresh (`enrichment_summary: {'reenriched': 20,
    'reused': 0, 'skipped_collision': 0}`).
  - Pass 2, run immediately after against the same live IBBI page:
    `{'new': 2, 'unchanged': 18, 'changed': 0, 'collision': 0}` —
    `unchanged` (18) matches `enrichment_summary`'s `reused` (18) exactly,
    the one number this test exists to prove. The 2 `new` were listings
    that genuinely appeared on IBBI's live site between the two passes —
    a real site change, not a bug. Spot-checked individual listings
    (e.g. V-Accurate Management Services, Euphoria Technologies) carry
    the identical `listing_key` and identical narrative text across both
    passes with `enrichment_reused` flipping `False -> True` — confirms
    real SQLite persistence and reuse, not a coincidence in the summary
    counts.
  - Two real, correctly-handled failures present in the raw log (not
    hidden or silently dropped): RKKR Holdings hit a genuine Gemini
    `Read timed out` on one lot; NAKODA LIMITED hit a real Gemini `429`
    quota-exceeded response (full error body visible). Both logged as
    flags on the listing, did not crash the run.
  - The known CIN state-code gap (flagged 2026-08-11 earlier this same
    day) is confirmed real in the live data too: BSR Diagnostic Limited
    (`CT`) and V-Accurate Management Services (`PN`) both show the
    "state code isn't in `_CIN_STATE_CODE_TO_NAME`" flag verbatim. Still
    a small future fix, not a Part 7A blocker.
  - No tracebacks, no `ENRICHMENT ROW IS NONE` warnings, no silently
    dropped flags anywhere in the raw output.

  **Part 7A is now fully confirmed — tick it in Section 3.** Part 7B (PDF
  layout) can start next session: it now has a real, confirmed
  per-listing assembled dataset (`run_pipeline()`'s return value) to lay
  out against, from an actual live run rather than synthetic data.
- **Part 7B built and confirmed (2026-08-11, later same day, new
  session):** `report/pdf.py` — `categorize_assembled()` (pure data
  shaping, no reportlab) splits `run_pipeline()`'s assembled list into
  top-scored / closing-soon / new-today / watchlist-changes, per Section
  1's own ordering, plus a "flagged for review" collisions section (not
  in the original list, added per this project's "never silently hide a
  flagged listing" rule — a collision is still fully scored, just has
  `enrichment=None` this run per Part 7A's own collision handling, and
  its card says so rather than showing an empty write-up silently).
  `new`/`changed` status and field-level diffs are read straight off
  each assembled entry (which `pipeline.py` already populated from
  `store_records()`) — no second DB query, matching the roadmap's own
  spec. `generate_report()` renders via reportlab platypus
  (`SimpleDocTemplate`) to `config.REPORT_OUTPUT_DIR` by default.

  **No real final score yet (flagged, not glossed over):**
  `config.SCORE_WEIGHTS` is still all `None`, so `combined_score()` is a
  plain average of whichever of `partial_score_5a/5b/5c` are available —
  a reasonable Claude-picked placeholder (same status as
  `REPORT_TOP_N`/`LOCATION_MATCH_NEUTRAL`/etc — see `config.py`'s new
  Part 7B comment), NOT the finished weighted ranking. The PDF itself
  says this under "Top-scored" rather than presenting it as done. Revisit
  `combined_score()` once the owner sets real weights.

  **Testing — unlike every prior AI-layer part, this one needed no
  network and no owner-side run**, since PDF layout has no external
  dependency: `test_part7b.py` built a synthetic assembled dataset
  covering every category and edge case (a top-scored listing with full
  enrichment, a closing-soon listing, a new-today listing, a
  watchlist-changed listing with a real price-drop diff, a collision with
  enrichment skipped, and a listing with literally nothing populated —
  no name/price/location/dates/enrichment at all), ran it through
  `categorize_assembled()` (asserted every listing landed in the right
  section(s)) and `generate_report()` (asserted a real PDF got written),
  then read the actual PDF bytes back with `pypdf` and asserted all 17
  expected substrings appear (every section heading, every
  `corporate_debtor` name, both sides of the watchlist diff, the
  collision explanation, the zero-reserve-price handling). All passed —
  this is a genuine real-render + real-read-back confirmation, not a
  mocked wiring test, even though it ran inside the sandbox.

  **One real bug found + fixed while visually checking the first render**
  (rendered a page to PNG via `pdftoppm` and looked at it, rather than
  trusting the text-extraction assertions alone): reportlab's default
  base-14 fonts don't include the Indian Rupee sign (₹) glyph — every
  price rendered as a solid black box instead of raising an exception, so
  nothing in the automated checks caught it (the pypdf text-extraction
  check would have silently passed too, since `\u20b9` was genuinely
  present in the extracted text — the bug was purely visual). Fixed:
  `_fmt_currency()` now uses `"Rs. "` instead of `"\u20b9"`, universally
  renderable in the default font without registering a Unicode TTF for
  one symbol. Re-confirmed via a second render + a second visual PNG
  check after the fix. Worth remembering for any future part that adds
  more currency/number formatting: don't trust text-extraction assertions
  alone for glyph-rendering bugs — spot-check an actual rendered page.

  **Next session: Part 8 (email delivery + GitHub Actions cron)** — 8A
  needs the owner's SMTP creds (Gmail app password) supplied locally; 8B's
  full implementation spec (Option B, runtime download from a GitHub
  Release) was already decided 2026-08-11 (see Part 8B roadmap entry
  above) and is ready to build once 8A exists.
