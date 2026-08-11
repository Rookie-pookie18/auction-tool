"""
ai_analysis/news_search.py — Part 6C: unofficial, no-key web-search news
pass per listing, via DuckDuckGo's plain HTML results endpoint
(html.duckduckgo.com/html/).

--------------------------------------------------------------------------
SCOPE (per PROJECT_STATUS.md Section 2, background-check depth item 2):
"an unofficial free web-search pass (e.g. DuckDuckGo HTML scrape, no key)
for recent news -- fragile, ToS-grey, best-effort only, never trusted
blindly, always labeled 'unverified' in the output if used." This module
does exactly that and nothing more: it surfaces a small number of raw
search-result hits (title, snippet, url) for a listing's corporate_debtor
name. It does NOT summarize, fact-check, or draw any conclusion from
those results -- that judgment call is left to the owner reading the PDF
(and explicitly out of scope for 6A's Gemini narrative too, per that
module's own docstring). Every result this module returns carries an
"unverified" label; nothing here is ever presented as confirmed.

WHY DUCKDUCKGO'S HTML ENDPOINT, NOT AN API: no key, no paid tier, no
CAPTCHA encountered on plain server-rendered results as of this writing
-- fits this project's "$0" rule the same way IBBI/data.gov.in do.
Google/Bing have no comparably scrapeable free path for a v1 best-effort
layer (not evaluated further than that).

ToS-GREY, FLAGGED HONESTLY (not glossed over) -- same spirit as the
BAANKNET decision (2026-08-07, config.py): no robots.txt block found on
html.duckduckgo.com's /html/ path, but DuckDuckGo's general ToS
discourages automated querying. Mitigations, matching the BAANKNET
pattern: identify honestly via the project's shared config.USER_AGENT
(never spoof a real browser), keep
config.NEWS_SEARCH_REQUEST_DELAY_SECONDS to a once-a-day-batch pace, cap
results per listing low (config.NEWS_SEARCH_MAX_RESULTS), and never
redistribute/republish results anywhere outside the owner's own PDF/email
report. config.NEWS_SEARCH_ENABLED lets the owner turn this off entirely
with no code change, same pattern as MCA_LOOKUP_MODE.

--------------------------------------------------------------------------
FAILURE HANDLING (same "never silently drop, always flag" pattern as
ai_analysis/gemini_narrative.py and ai_analysis/mca_lookup.py): no
corporate_debtor name, NEWS_SEARCH_ENABLED=False, a blocked/malformed/
empty response, a network error, or zero results -- none of these ever
raise out of search_news_for_debtor()/enrich_record_with_news()/
enrich_batch_with_news(). They come back as news_data=None plus a
human-readable flag. One bad/missing search never blocks the rest of a
batch.

--------------------------------------------------------------------------
RATE LIMITING: config.NEWS_SEARCH_REQUEST_DELAY_SECONDS is applied
between calls in enrich_batch_with_news() (not on a single ad-hoc call),
same pattern as config.GEMINI_REQUEST_DELAY_SECONDS /
config.MCA_DATA_GOV_REQUEST_DELAY_SECONDS. No retry-on-failure here
(unlike 6A's one retry on 429/5xx) -- a blocked/failed search-engine
scrape retrying immediately is more likely to look like abuse than a
transient blip, so this module fails fast and flags instead.

MATCHING STRATEGY (widened 2026-08-10 after real run #1 -- see
PROJECT_STATUS.md decision log): a single narrow query left genuine
zero-coverage companies indistinguishable from a query that was simply
too strict, so this now tries a chain of progressively broader queries
per listing, stopping at the first one that returns a result:
  1. `"<corporate_debtor>" <location> auction OR insolvency OR NCLT`
     (most specific -- best disambiguation against common company names)
  2. `"<corporate_debtor>" <location>` (drops the auction/insolvency/NCLT
     restriction, in case the only coverage is e.g. a company-registry or
     news mention that doesn't use those exact words)
  3. `"<corporate_debtor>"` (drops location, in case location was noisy
     or the coverage is national/generic)
  4. `<corporate_debtor>` (no exact-phrase quoting at all, in case the
     scraped name has punctuation/spacing that doesn't exactly match how
     the company is referred to online)
Each step is a genuinely broader net for the SAME company, not a
different company or a guess -- this is a real, honest attempt to find
whatever coverage exists, not a way to manufacture a hit. A listing that
still returns nothing after all four attempts almost certainly has no
real indexed coverage, and stays a clean "0 results" flag rather than
being forced to show something. This is expected to raise the real hit
rate but will NOT reach 100% -- some small/low-profile corporate debtors
genuinely have no online news footprint, and this module will never
substitute an unrelated or fabricated result to paper over that (see
FAILURE HANDLING above -- "never trust blindly" applies here too: a
broader net raises recall, it does not lower the bar for what counts as
a real match). Every result from every step stays labeled "unverified"
regardless of which query tier found it, and the flag on a genuine
zero-hit records which tiers were actually tried, not just that "0
results" happened once.
"""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Optional

import requests
from bs4 import BeautifulSoup

import sys
sys.path.insert(0, ".")
import config


class NewsSearchError(Exception):
    """Raised for any HTTP-level/transport/parse failure calling the
    DuckDuckGo HTML endpoint. Callers inside this module catch it and turn
    it into a flag; it should never escape search_news_for_debtor()."""


def _as_dict(record) -> dict:
    return asdict(record) if hasattr(record, "__dataclass_fields__") else dict(record)


def _build_query_chain(corporate_debtor: str, location: Optional[str]) -> list[str]:
    """Returns an ordered list of progressively broader queries for the
    SAME company (see this module's docstring, "MATCHING STRATEGY"). The
    caller tries each in order and stops at the first that returns a real
    result. Order matters: most-specific/best-disambiguated first, so a
    company with genuine narrow coverage still gets the most targeted
    match rather than a noisier one."""
    quoted = f"\"{corporate_debtor}\""
    topic_filter = " auction OR insolvency OR NCLT"

    queries = []
    if location:
        queries.append(quoted + f" {location}" + topic_filter)
        queries.append(quoted + f" {location}")
    else:
        queries.append(quoted + topic_filter)
    queries.append(quoted)
    queries.append(corporate_debtor)  # unquoted -- last resort, no exact-phrase requirement

    # De-dupe while preserving order (e.g. when location is None, some
    # tiers above can otherwise collide).
    seen = set()
    deduped = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            deduped.append(q)
    return deduped


def call_duckduckgo_html(query: str) -> str:
    """Real network call -- POSTs to DuckDuckGo's HTML results endpoint
    (the same form its own no-JS /html/ page submits) and returns the raw
    HTML. Raises NewsSearchError on any transport/HTTP failure; never
    raises for a merely-empty results page (that's a legitimate "0
    results", handled by the caller as a clean flag, not an error)."""
    try:
        resp = requests.post(
            config.NEWS_SEARCH_URL,
            data={"q": query},
            headers={"User-Agent": config.USER_AGENT},
            timeout=config.NEWS_SEARCH_TIMEOUT_SECONDS,
        )
    except requests.RequestException as e:
        raise NewsSearchError(f"network error calling DuckDuckGo: {e}") from e

    if resp.status_code != 200:
        raise NewsSearchError(
            f"DuckDuckGo returned HTTP {resp.status_code} (possible block/"
            f"rate-limit -- this endpoint is unofficial/ToS-grey, see this "
            f"module's docstring)"
        )
    return resp.text


def _parse_results(html: str, max_results: int) -> list[dict]:
    """Parses DuckDuckGo's HTML results page. Each result: {title, url,
    snippet}. UNCONFIRMED against real network output (sandbox has no
    network access, per PROJECT_STATUS.md Section 0 rule 2) -- selectors
    below target the documented/commonly-referenced class names on this
    endpoint's no-JS results page (`result__title`, `result__url`,
    `result__snippet`), but only test_part6c.py's first real run actually
    confirms them. If the real markup differs, this returns an empty list
    (0 results) rather than raising -- a wall of "0 results" across every
    listing in that first real run is the signal to check these selectors
    against the real HTML, same as decision (17)/(18)'s pattern in
    mca_lookup.py for an unconfirmed API assumption."""
    soup = BeautifulSoup(html, "lxml")
    results = []
    for block in soup.select("div.result")[:max_results]:
        title_el = block.select_one("a.result__a") or block.select_one(".result__title a")
        snippet_el = block.select_one(".result__snippet")
        if title_el is None:
            continue
        title = title_el.get_text(strip=True)
        url = title_el.get("href", "")
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""
        if title:
            results.append({"title": title, "url": url, "snippet": snippet})
    return results


def search_news_for_debtor(
    corporate_debtor: Optional[str],
    location: Optional[str] = None,
) -> dict:
    """Runs one best-effort news search for a single company name.

    Returns:
      {"news_data": [{"title", "url", "snippet"}, ...], "flags": []}
    on a search that returned at least one result, or:
      {"news_data": None, "flags": ["<human-readable reason>"]}
    on: disabled via config, no corporate_debtor name, a network/HTTP
    failure, or zero results found. Every result in `news_data` is a raw,
    unverified web-search hit -- the caller (report layer, Part 7) is
    responsible for labeling it "unverified" when shown to the owner, per
    PROJECT_STATUS.md Section 2's "never claims research depth it didn't
    actually get" rule; this module doesn't format for display itself.
    """
    if not config.NEWS_SEARCH_ENABLED:
        return {
            "news_data": None,
            "flags": ["News search skipped: config.NEWS_SEARCH_ENABLED is False"],
        }

    if not corporate_debtor:
        return {
            "news_data": None,
            "flags": ["News search skipped: no corporate_debtor name available for this listing"],
        }

    queries = _build_query_chain(corporate_debtor, location)
    tried = []
    for tier, query in enumerate(queries, start=1):
        if tier > 1:
            # Only pause between our OWN repeated queries for the same
            # listing -- config.NEWS_SEARCH_REQUEST_DELAY_SECONDS (applied
            # between different listings in enrich_batch_with_news()) is a
            # separate, larger pause; this shorter one just avoids firing
            # a rapid burst of requests for one listing's fallback chain.
            time.sleep(config.NEWS_SEARCH_TIER_DELAY_SECONDS)
        try:
            html = call_duckduckgo_html(query)
            results = _parse_results(html, config.NEWS_SEARCH_MAX_RESULTS)
        except NewsSearchError as e:
            tried.append(f"tier {tier} ({query!r}) failed: {e}")
            continue

        tried.append(f"tier {tier} ({query!r}): {len(results)} result(s)")
        if results:
            flags = []
            if tier > 1:
                flags.append(
                    f"News search for {corporate_debtor!r} only matched on "
                    f"a broadened query (tier {tier}/{len(queries)}: "
                    f"{query!r}), not the most specific one -- results are "
                    f"still labeled unverified and may be a looser match "
                    f"than tier 1 would have given"
                )
            return {"news_data": results, "flags": flags}

    return {
        "news_data": None,
        "flags": [
            f"News search for {corporate_debtor!r} returned 0 results across "
            f"all {len(queries)} query tiers tried ({'; '.join(tried)}) -- "
            f"this is a genuine best-effort exhaustion, not a single narrow "
            f"miss. Most likely a real lack of online coverage for this "
            f"company; if EVERY listing in a batch shows this same "
            f"all-tiers-exhausted pattern, check news_search.py's "
            f"_parse_results() docstring instead, since that would point "
            f"to the selectors rather than genuine no-coverage"
        ],
    }


def enrich_record_with_news(record) -> dict:
    """Runs search_news_for_debtor() for ONE record's `corporate_debtor` /
    `location` fields and writes the result onto the record itself
    (news_data, news_search_attempted), mirroring
    ai_analysis/mca_lookup.py's enrich_record_with_mca() convention. Also
    returns the same dict search_news_for_debtor() does, for callers that
    don't need the mutation."""
    r = _as_dict(record)
    result = search_news_for_debtor(r.get("corporate_debtor"), r.get("location"))

    if hasattr(record, "news_data"):
        record.news_data = result["news_data"]
    if hasattr(record, "news_search_attempted"):
        record.news_search_attempted = True
    if result["flags"] and hasattr(record, "flags") and isinstance(record.flags, list):
        record.flags.extend(result["flags"])

    return result


def enrich_batch_with_news(
    records: list,
    delay_seconds: Optional[float] = None,
) -> list[dict]:
    """Runs enrich_record_with_news() across a batch, same order/length as
    `records`, pausing config.NEWS_SEARCH_REQUEST_DELAY_SECONDS between
    calls. One bad/missing search (see enrich_record_with_news()'s
    failure handling) never stops the batch."""
    delay = config.NEWS_SEARCH_REQUEST_DELAY_SECONDS if delay_seconds is None else delay_seconds
    results = []
    for i, record in enumerate(records):
        results.append(enrich_record_with_news(record))
        if i < len(records) - 1:
            time.sleep(delay)
    return results


if __name__ == "__main__":
    # Offline-only smoke check (no network -- see PROJECT_STATUS.md Section
    # 0 rule 2). Confirms the disabled/no-name skip paths return a clean
    # flag instead of raising, and that _build_query()/_parse_results()
    # behave sanely on synthetic input. The part that actually needs a
    # real DuckDuckGo response can only be confirmed on the owner's own
    # machine, per test_part6c.py.
    print("Offline smoke check (no network calls made):\n")

    chain1 = _build_query_chain("ABC Textiles Pvt Ltd", "Rajpura")
    chain2 = _build_query_chain("ABC Textiles Pvt Ltd", None)
    print(f"1. _build_query_chain() with location:    {chain1}")
    print(f"   _build_query_chain() without location: {chain2}")
    assert any("Rajpura" in q for q in chain1)
    assert not any("Rajpura" in q for q in chain2)
    assert chain1[-1] == "ABC Textiles Pvt Ltd"  # last tier: unquoted, bare name
    assert len(chain1) == 4  # tier1+location, tier2 (no topic filter)+location, quoted-only, bare
    assert len(chain2) == 3  # no location tiers to dedupe against

    r1 = search_news_for_debtor(None)
    print(f"2. No corporate_debtor: news_data={r1['news_data']!r}  flags={r1['flags']}")
    assert r1["news_data"] is None and r1["flags"]

    original_enabled = config.NEWS_SEARCH_ENABLED
    config.NEWS_SEARCH_ENABLED = False
    r2 = search_news_for_debtor("ABC Textiles Pvt Ltd")
    print(f"3. NEWS_SEARCH_ENABLED=False: news_data={r2['news_data']!r}  flags={r2['flags']}")
    assert r2["news_data"] is None and r2["flags"]
    config.NEWS_SEARCH_ENABLED = original_enabled

    sample_html = """
    <div class="result">
      <a class="result__a" href="https://example.com/a">ABC Textiles land auction notice</a>
      <a class="result__snippet">Sample snippet about the auction.</a>
    </div>
    <div class="result">
      <a class="result__a" href="https://example.com/b">ABC Textiles NCLT order</a>
      <a class="result__snippet">Sample snippet about the NCLT case.</a>
    </div>
    """
    parsed = _parse_results(sample_html, max_results=3)
    print(f"4. _parse_results() on synthetic HTML: {len(parsed)} result(s) found")
    assert len(parsed) == 2 and parsed[0]["title"] == "ABC Textiles land auction notice"

    # 5. Confirm the fallback chain actually falls through: tier 1 empty,
    #    tier 2 has a hit -- search_news_for_debtor() should return tier
    #    2's result and flag that it wasn't the most-specific tier.
    empty_html = "<html><body>no results</body></html>"
    hit_html = sample_html  # from check 4 above, reused here
    call_sequence = [empty_html, hit_html]

    def _fake_call(query):
        return call_sequence.pop(0)

    original_call = call_duckduckgo_html
    globals()["call_duckduckgo_html"] = _fake_call
    r3 = search_news_for_debtor("ABC Textiles Pvt Ltd", "Rajpura")
    globals()["call_duckduckgo_html"] = original_call
    print(f"5. Fallback chain (tier 1 empty, tier 2 hits): "
          f"news_data={len(r3['news_data']) if r3['news_data'] else 0} result(s), "
          f"flags={r3['flags']}")
    assert r3["news_data"] is not None and len(r3["news_data"]) == 2
    assert r3["flags"] and "tier 2" in r3["flags"][0]

    # 6. Confirm total exhaustion (all tiers empty) still returns a clean
    #    flag naming how many tiers were tried, not a raised exception.
    call_sequence_all_empty = [empty_html] * 4
    globals()["call_duckduckgo_html"] = lambda query: call_sequence_all_empty.pop(0)
    r4 = search_news_for_debtor("Totally Obscure Pvt Ltd", "Nowhere")
    globals()["call_duckduckgo_html"] = original_call
    print(f"6. All tiers exhausted: news_data={r4['news_data']!r}")
    print(f"   flags={r4['flags']}")
    assert r4["news_data"] is None
    assert "all 4 query tiers" in r4["flags"][0]

    print("\nAll offline checks passed. Real results need a live network "
          "call against html.duckduckgo.com -- see test_part6c.py, which "
          "also confirms whether _parse_results()'s selectors actually "
          "match the real page (see this module's _parse_results() "
          "docstring for what a wall of '0 results' flags would mean), "
          "AND now confirms whether the new fallback-query chain (see "
          "MATCHING STRATEGY in this module's docstring) meaningfully "
          "raises the real hit rate versus the single-query approach from "
          "the first real run.")
