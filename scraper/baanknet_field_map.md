# BAANKNET field-to-selector map

Built from 4 owner-saved samples (2026-08-09), all "Webpage, Complete" saves
so the post-render DOM is captured (site is Next.js/Turbopack, JS-rendered,
but the save method used gets us real data — good):

- `Buy_Indian_Bank_Auction_Properties___BAANKNET.html` — search results,
  Industrial Plot filter, New Delhi (1 result)
- `Buy_Indian_Bank_Auction_Properties___BAANKNET_1_.html` — search results,
  Agricultural filter (10 of 220 results, infinite-scroll first batch)
- `Industrial_Plot_for_sale_in_New_Delhi___BAANKNET.html` — detail page for
  the single Industrial result above
- `Agriculture_Land_for_sale_in_VILLAGE_Adawal___BAANKNET.html` — detail
  page for the first Agricultural result above

Not real HTTP fetches — these are saved DOM snapshots, per Section 0 rule 2.
Live-fetch behavior (headers, rate limits, session/login walls) is still
untested and owner-side-only pending.

## Bonus: JSON-LD ItemList (free, cheap backbone)

Every listing page has `<script type="application/ld+json">` with
`@type: CollectionPage` containing an `ItemList`. Each item gives, for
free and without touching card markup: `name` (title string with area+unit
baked in), and `url` (canonical `property-detail/{numeric_id}` link).
Useful as a cheap way to enumerate what's on a page and get canonical
detail URLs, but it does NOT carry price/dates/bank/etc — still need the
card markup for those.

## Card-level fields (search results page)

Each card starts at `<div class="mt-3 rounded-lg bg-white p-5">`. **Card
content is duplicated twice per listing** (once for a `lg:flex` desktop
layout, once for a `lg:hidden` mobile layout) — dedupe by taking the
first occurrence only, or scope to the desktop block.

| Field | Selector / pattern | Sample value | Notes |
|---|---|---|---|
| Title/name | `<h6 class="line-clamp-2 ... font-medium">` | "9.13 hectares Agriculture Land for sale in VILLAGE Adawal" | Area+unit is embedded in this string — see flag below |
| Property ID (bank's) | `<span class="cursor-pointer text-sm text-gray-600">Property ID: {id}</span>` | `SBINSK03092026` | Alphanumeric, bank-issued |
| Numeric site ID | not on card directly | — | Only available via the detail URL (`/property-detail/{numeric_id}`) in the JSON-LD `url` field — two different IDs exist, see flag below |
| Carpet Area | label `<span class="text-xs leading-snug ... text-[#666666]">Carpet Area</span>` → sibling `<h6 class="text-formlabel ...">` | `"NA "` (!) | **Unreliable — see flag below.** Parse area from the title string instead. |
| Land classification | pair of `<span class="w-full">` after the "hotel" icon svg | `"Agriculture Land, Agriculture"` / `"Industrial Plot, Industrial"` | Format is `{Sub Type}, {Type}` |
| Bank/lender | `<span class="flex-1 max-lg:leading-snug">` after the "landmark" icon svg | `"State Bank of India"` | |
| Location | `<span class="line-clamp-2 ...">` after the "map-pin" icon svg | `"Bastar, Adawal, Chhattisgarh"` | Free text, `District, Place, State` — not individually tagged fields on the card (compare to detail page, which has these split) |
| Possession Type | label `Possession Type` → sibling `<h6>` (same grid as Carpet Area) | `"Symbolic "` | Site's own wording — not "possession status" |
| Type of Action | label `Type of Action` → sibling `<h6>` (same grid) | `"Under DRT"` / `"Under SARFAESI"` | Legal auction mechanism, not an "auction round" |
| Price | `<span class="text-lg max-lg:text-base">{value}</span>` inside the price block | `"44.3 Lac"` / `"5.7 Cr"` | **Not reliably labeled "Reserve price" — see flag below.** Rounded/human-formatted, not exact. |
| Auction Start/End Date & Time | label `<span class="block">Auction Start</span><span class="block">Date & Time</span>` → sibling `<h6>` | `"03-09-2026 12:00"` | **Only present when the property has an active/upcoming auction round.** Absent entirely otherwise — must be optional field, not an error. |
| Inspection Start/End Date & Time | same pattern, label `Inspection Start`/`Inspection End` | `"20-08-2026 12:00"` | Same "only if active round" caveat |
| EMD End Date & Time | same pattern, label `EMD End` | `"01-09-2026 17:00"` | Date only — no EMD **amount** found anywhere, see flag below |
| Auction Round | — | — | **Not found in any sample.** No "Round 1/2/3" or bid-increment field anywhere in card or detail markup. |

## Detail page fields (property-detail/{id})

Cleanest markup on the whole site — plain label→value pairs:
`<li class="flex gap-4"><span class="... text-gray-500 ...">{LABEL}</span><span class="... text-gray-800">{VALUE}</span></li>`

**Property Detail section:** Title Deed Type, Type of Action, Property
Address (free text, includes area+unit again), State, District, Pin Code,
CERSAI ID, Facing, Other Detail, **Indicative Price** (exact figure, e.g.
`₹44,30,000.00` — labeled "Indicative Price" here, not "Reserve price").

**Owner Details section:** Ownership of Property, Ownership Type,
Borrower's Name, Registered Address of Borrower.

**Bank Detail section:** Bank, Bank Property ID (matches the card's
"Property ID" in both samples checked).

**Top-of-page big price display:** `<h5>` with rupee icon + value, followed
by a literal on-page disclaimer: *"** Denotes Indicative Price only. The
Final Reserve Price will be declared at the time of Auction."* This
disclaimer text is present on **every** detail page checked, not
conditional.

**Property ID (header):** `<span class="text-sm text-[#666]">Property ID {id}</span>` (note: value is split across HTML comment nodes `<!-- --> <!-- -->` — needs comment-stripping in the parser, don't string-match naively).

**Source URL:** confirmed pattern `https://baanknet.com/property-detail/{numeric_id}` — numeric ID is different from the bank's alphanumeric Property ID (e.g. detail page numeric ID `293420` vs Property ID `SBINSK03092026`).

## Flags — inconsistencies to keep visible, not paper over

1. **Carpet Area field is unreliable.** On the card, the "Carpet Area"
   stat showed `"NA "` even when the title string clearly stated
   `"418.05 sq meter"`. The area+unit is more reliably parsed out of the
   title/name string (regex on a leading number + unit word) than trusted
   from the labeled Carpet Area field. Flag both in the output record
   when they disagree — don't silently prefer one.
2. **"Reserve price" label is conditional and, per the site's own
   disclaimer, may not even be a real reserve price.** When a property has
   an active/upcoming auction round, the card labels this number
   "Reserve price." When it doesn't, the exact same-looking number appears
   with no label at all. The detail page calls this same figure
   "Indicative Price" and explicitly states the real reserve price is
   only set at auction time. Recommendation: store this as
   `indicative_price`, not `reserve_price`, and flag it as provisional in
   scoring/PDF output rather than treating it as final.
3. **EMD Amount is nowhere in these samples.** The site's own i18n string
   table (embedded JS) has a label key for `"EMD Amount"`, confirming the
   UI has a place for it, but no rendered value appeared on either the
   card or the detail page in any of the 4 samples. It's likely behind an
   interaction (an accordion/tab, possibly per-round) that wasn't
   expanded when these pages were saved. **Owner-pending:** please expand
   any "Auction Detail" tab/accordion fully before re-saving one sample
   with an active auction round, or check the browser Network tab for the
   API response that populates it.
4. **Auction Round is nowhere in these samples**, same story as EMD
   Amount — owner-pending, same ask.
5. **Two different property IDs exist per listing** — the bank's
   alphanumeric Property ID (shown on cards/detail header) and a numeric
   site-internal ID (only visible in the detail URL / JSON-LD). Part 4's
   dedup key should probably use the numeric site ID since it's guaranteed
   unique and stable; the bank's ID is more human-readable but its
   uniqueness/stability across relistings is unconfirmed.
6. **Pagination mechanism is unconfirmed.** Search pages use
   `infinite-scroll-component` (react-infinite-scroll-style) with no
   `page=` URL param, no "Load More" button, and no visible API endpoint
   in the saved HTML (the JS bundles that would call it weren't part of
   the upload). Part 3B will need either a Network-tab capture of the
   real API request/response, or a Playwright-driven scroll-and-resave
   approach — flagging as owner-pending, not guessing at an endpoint.

## Still open before Part 3 can start cleanly

- EMD Amount value (flag 3)
- Auction Round value (flag 4)
- Listing pagination/API mechanism (flag 6)
- Only 2 of the 5 property types have samples (Agricultural, Industrial) —
  Residential/Commercial/Other card layout is assumed identical but
  unverified.
