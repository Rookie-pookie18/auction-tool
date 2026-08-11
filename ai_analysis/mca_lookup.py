"""
ai_analysis/mca_lookup.py — Part 6B: best-effort MCA (Ministry of Corporate
Affairs) company master-data lookup, by CIN, against LOCALLY DOWNLOADED
per-state CSV files from data.gov.in's "Registrars of Companies (RoC)-wise
Company Master Data" resource.

--------------------------------------------------------------------------
WHY LOCAL FILES, NOT A LIVE API CALL (this is the second major redesign of
this module -- see PROJECT_STATUS.md decisions (17)-(21) for the full
story): the original design called data.gov.in's REST endpoint
(api.data.gov.in/resource/...) live, once per CIN, expecting a normal
request/response API. Real testing 2026-08-09 showed this consistently
failing -- every single query (2 different states, with and without a CIN
filter) timed out after ~60s with an empty HTTP 502, regardless of how
small the state was. The root cause was found by testing the SAME
resource through data.gov.in's own website: clicking "Preview & Download"
for even a small state (Goa) didn't return data either -- it asked for a
download purpose, warned the data "may take time" to prepare, and created
a background job (visible under My Account -> Download History, status
"In progress"). That's the real shape of this resource: **it's a bulk
export/batch-job dataset, not a real-time lookup API** -- data.gov.in's
own official UI doesn't serve it instantly either. Treating it as a
live per-request API was the wrong model from the start, not something a
longer timeout or a smarter filter would fix.

The fix that actually matches how this data is shaped: download each
state's CSV ONCE (via that same website job -- a manual, owner-driven
step, not something this module can automate; there's no evidence
data.gov.in exposes a way to trigger/poll/fetch these jobs
programmatically without a browser session), save it locally, and look up
CINs against that local file instead. This is arguably a BETTER fit for
this data than a live API would have been anyway: the resource's own
"Note" field already says the underlying company records only go up to
3 Nov 2023 (see config.py's Part 6B comment) -- it's a static,
infrequently-refreshed extract, not something that benefits from being
queried live. Downloading once and reusing indefinitely (until the owner
chooses to refresh a file) matches what this data actually is.

The old live-API call code is deliberately NOT kept around "for
reference" -- it's a genuinely abandoned design (root-caused in decision
(21) as structurally incompatible with this resource, not a transient
bug), and this project's own convention is "nothing hardcoded / no
unused cruft" (see config.py's Part 6B comment, decision (22)). A dead
`live_api` code path that quietly still behaved like a live call (e.g.
still pausing MCA_DATA_GOV_REQUEST_DELAY_SECONDS between purely-local
reads, if that constant and that pacing loop were carried over unused)
is exactly the kind of half-migrated state this project avoids -- if
data.gov.in's backend ever recovers, the live-API version is still in
git history, not worth carrying live in the module.

--------------------------------------------------------------------------
SETUP THE OWNER NEEDS TO DO (per state, manually, via data.gov.in's
website -- see README.md for the exact click-path): request + download
each state's CSV, and save it as
    {config.MCA_LOCAL_DATA_DIR}/{state_name_with_underscores}.csv
e.g. "delhi.csv", "madhya_pradesh.csv" (state_name comes from
_CIN_STATE_CODE_TO_NAME below, spaces replaced with underscores -- see
`expected_csv_path_for_state()`). Nothing needs downloading up front for
this module's CODE to be correct/testable -- missing files are just
another best-effort "flag, don't block" case, same as everything else
here. The owner can add states incrementally as new CINs turn up needing
them; there's no fixed list this module requires ahead of time.

--------------------------------------------------------------------------
SCOPE (per PROJECT_STATUS.md Section 2, background-check depth item 2):
"best-effort enrichment, free, may fail silently-safe (flag, don't
block)". This module adds basic incorporation/status info ONLY --
company_status, category, class, registration date, registered office,
authorized/paid-up capital. It never claims more than that, and it never
blocks the rest of the pipeline if a lookup fails, a state's file is
missing, or nothing matches.

WHY CIN-ONLY, NEVER NAME-ONLY: matching a company by name alone across a
multi-million-company registry risks silently attaching the wrong
company's data to a listing. This project's "never guess, always flag"
rule doesn't allow that, so a listing with no parsed CIN (Part 3C didn't
always get one) is flagged "skipped, no CIN" rather than attempted by
name.

--------------------------------------------------------------------------
HEADER-MATCHING ROBUSTNESS (added 2026-08-10, same checkpoint as Part 6C
and the Part 7 planning session -- see PROJECT_STATUS.md decision (23)):
the confirmed field names in _FIELD_VARIANTS below (e.g.
CORPORATE_IDENTIFICATION_NUMBER) were confirmed from the live API's own
"Meta Field" list, not from an actual downloaded CSV export -- and a
bulk CSV export from a government data platform doesn't always share
exact header naming/casing with the same platform's JSON API (spacing,
casing, and punctuation commonly drift between the two). Rather than
require an exact match against only the API's field names (which would
make the whole state's file unreadable -- "doesn't have a column" --
over what might just be a header-formatting difference), each logical
field now matches case-insensitively against a short list of plausible
variants (`_match_header()`), and the CIN used for the in-memory index is
normalized (stripped + uppercased) on both the load and lookup side, so
incidental whitespace/case differences in a real export don't turn a
real match into a false "no match". If the CIN column truly can't be
found under ANY known variant, this still fails loudly with the actual
headers found in the file (never silently returns an empty/wrong index)
-- same "never guess, always flag" spirit as everywhere else in this
module, just applied one level earlier (at column-detection time, not
just at row-match time). A state export that turns out to have zero
usable rows, or that has more than one row for the same CIN (a real
data-quality question worth surfacing, not silently overwriting), is
also flagged rather than passed through quietly.

--------------------------------------------------------------------------
FAILURE HANDLING (same "never silently drop, always flag" pattern as
ai_analysis/gemini_narrative.py and every scraper/scoring part before it):
no CIN, unmapped/unknown state code embedded in the CIN, that state's CSV
not yet downloaded, a CSV with no recognizable CIN column, or no matching
CIN row inside a CSV that IS present -- none of these ever raise out of
lookup_company_by_cin()/enrich_record_with_mca()/enrich_batch_with_mca().
They come back as mca_data=None plus a human-readable flag. One bad/
missing lookup never blocks the rest of a batch.

--------------------------------------------------------------------------
PERFORMANCE: each state's CSV is parsed into an in-memory {cin: row} dict
ONCE per process, cached in _STATE_CIN_INDEX_CACHE, regardless of how many
listings from that state appear in a batch -- so a 500-listing batch with
many Delhi companies still only reads+parses delhi.csv once. These are
local file reads, not network calls, so enrich_batch_with_mca() applies
no per-call delay/pacing (unlike Part 6A's Gemini calls or Part 6C's
DuckDuckGo calls, which do need one).
"""

from __future__ import annotations

import csv
import os
from dataclasses import asdict
from typing import Optional

import sys
sys.path.insert(0, ".")
import config


# CIN structure (21 chars): [1 listing-status][5 industry code][2 STATE
# CODE][4 year][3 ownership][6 registration number] -- e.g.
# "U18101KA2002PLC030185" -> state code = chars[6:8] = "KA".
# This table is the standard, stable MCA/RoC state-code list -- long
# established, not something that needed live verification (unlike the
# resource_id/field names in the earlier live-API version of this
# module). Maps to the lowercase full state name data.gov.in uses for
# this resource (confirmed 2026-08-09 from the resource's own dropdown),
# which is also the naming convention this module expects for local CSV
# filenames (spaces -> underscores, see expected_csv_path_for_state()).
_CIN_STATE_CODE_TO_NAME = {
    "AN": "andaman and nicobar islands",
    "AP": "andhra pradesh",
    "AR": "arunachal pradesh",
    "AS": "assam",
    "BR": "bihar",
    "CH": "chandigarh",
    "CG": "chattisgarh",
    "DN": "dadra & nagar haveli",
    "DD": "daman and diu",
    "DL": "delhi",
    "GA": "goa",
    "GJ": "gujarat",
    "HR": "haryana",
    "HP": "himachal pradesh",
    "JK": "jammu & kashmir",
    "JH": "jharkhand",
    "KA": "karnataka",
    "KL": "kerala",
    "LA": "ladakh",
    "LD": "lakshadweep",
    "MP": "madhya pradesh",
    "MH": "maharashtra",
    "MN": "manipur",
    "ML": "meghalaya",
    "MZ": "mizoram",
    "NL": "nagaland",
    "OR": "odisha",
    "PY": "puducherry",
    "PB": "punjab",
    "RJ": "rajasthan",
    "SK": "sikkim",
    "TN": "tamil nadu",
    "TZ": "tamil nadu",   # RoC Coimbatore -- a second Tamil Nadu state
                           # code alongside RoC Chennai's "TN", found +
                           # fixed 2026-08-09 from a real scraped CIN
                           # (Maharaja Theme Parks and Resorts,
                           # U92199TZ1995PTC005954) that came back
                           # "unrecognized" until this was added.
    "TR": "tripura",
    "UP": "uttar pradesh",
    "UK": "uttarakhand",
    "UA": "uttarakhand",
    "WB": "west bengal",
    "TG": "telangana",
    "TS": "telangana",
}

# Real field names, confirmed 2026-08-09 straight from the resource's own
# "Meta Field" list on data.gov.in (listed first in each variant list --
# always tried first), PLUS plausible spaced/title-case variants a CSV
# *export* of the same underlying resource might actually use instead
# (unconfirmed against a real downloaded file as of this checkpoint --
# see this module's docstring, "HEADER-MATCHING ROBUSTNESS"). Matching
# against these is case-insensitive (see `_match_header()`), so exact
# casing doesn't need to be guessed correctly up front either.
# 2026-08-10 update (see PROJECT_STATUS.md decision (24)): the previous
# variant lists above were confirmed only against the live API's "Meta
# Field" names, never against a real downloaded CSV export -- that gap is
# now closed. Five real state exports (delhi/goa/madhya_pradesh/punjab/
# sikkim, all data.gov.in "RoC-wise Company Master Data") were inspected
# directly and all five share ONE real header row, verbatim:
#   CIN,CompanyName,CompanyROCcode,CompanyCategory,CompanySubCategory,
#   CompanyClass,AuthorizedCapital,PaidupCapital,
#   CompanyRegistrationdate_date,Registered_Office_Address,Listingstatus,
#   CompanyStatus,CompanyStateCode,CompanyIndian/Foreign Company,
#   nic_code,CompanyIndustrialClassification
# The real headers use a THIRD naming convention -- neither the
# ALL_CAPS_WITH_UNDERSCORES "Meta Field" style nor plain "Title Case With
# Spaces", but concatenated PascalCase with no separators at all
# (CompanyROCcode, CompanySubCategory, CompanyStateCode). _match_header()
# only compares lowercased strings for exact equality -- it doesn't strip
# separators -- so "CompanySubCategory" (no space) genuinely does NOT
# match the existing "Company SubCategory" (space) variant; that's a real
# miss, not a false alarm. registered_office_address's existing
# "REGISTERED_OFFICE_ADDRESS" variant DOES still match the real
# "Registered_Office_Address" header (both lowercase to
# "registered_office_address", underscores and all) -- confirmed, no
# change needed there. The four real gaps below are each fixed by adding
# the exact real header as its own variant (kept alongside the old
# unconfirmed variants rather than replacing them, in case a future
# export ever uses one of those instead):
_FIELD_VARIANTS = {
    "company_name": ["COMPANY_NAME", "Company Name", "CompanyName"],
    "cin": ["CORPORATE_IDENTIFICATION_NUMBER", "CIN", "Corporate Identification Number"],
    "company_status": ["COMPANY_STATUS", "Company Status", "CompanyStatus"],
    "company_category": ["COMPANY_CATEGORY", "Company Category", "CompanyCategory"],
    "company_class": ["COMPANY_CLASS", "Company Class", "CompanyClass"],
    "sub_category": ["SUB_CATEGORY", "Company SubCategory", "Sub Category", "SubCategory", "CompanySubCategory"],
    "date_of_registration": ["DATE_OF_REGISTRATION", "Date of Registration", "DateOfRegistration", "CompanyRegistrationdate_date"],
    "registered_state": ["REGISTERED_STATE", "Registered State", "State", "CompanyStateCode"],
    "registrar_of_companies": ["REGISTRAR_OF_COMPANIES", "Registrar of Companies", "RegistrarOfCompanies", "CompanyROCcode"],
    "authorized_capital": ["AUTHORIZED_CAPITAL", "Authorized Capital", "AuthorizedCapital"],
    "paidup_capital": ["PAIDUP_CAPITAL", "Paidup Capital", "PaidupCapital"],
    "registered_office_address": ["REGISTERED_OFFICE_ADDRESS", "Registered Office Address", "RegisteredOfficeAddress", "Address"],
    # principal_business_activity: the real export has NO direct
    # equivalent field -- confirmed by inspecting all 16 real headers
    # above, not assumed. "CompanyIndustrialClassification" (the NIC
    # industrial-classification text, e.g. "Manufacture of other
    # chemical products") is added here as a deliberate, flagged
    # judgment call, not a silent guess: in MCA/RoC data this field is
    # the free-text description of what industry the company's principal
    # activity falls under, which is the closest real-world equivalent
    # to "principal business activity" this export actually has -- but
    # it is genuinely a different underlying concept (an NIC
    # classification label, not a plain-English activity description),
    # so this mapping trades some precision for coverage. See
    # PROJECT_STATUS.md decision (24) for the full reasoning; revisit if
    # this ever produces a misleading-looking value in real output.
    "principal_business_activity": ["PRINCIPAL_BUSINESS_ACTIVITY", "Principal Business Activity", "PrincipalBusinessActivity", "Activity", "CompanyIndustrialClassification"],
}

REQUIRED_MCA_KEYS = list(_FIELD_VARIANTS.keys())

# In-memory cache: state_name -> {cin_upper: {...normalized fields...}}.
# Built once per process the first time a state is needed, reused after
# that -- see module docstring's Performance note. A single sentinel
# value (rather than just omitting a failed state) distinguishes "we
# tried to load this state's file and it didn't exist / was broken" from
# "never asked yet", so a bad file only gets one clear flag per batch
# instead of a fresh error on every listing that needs it.
_STATE_CIN_INDEX_CACHE: dict = {}
_LOAD_FAILURE = object()


class MCALookupError(Exception):
    """Raised for any file-missing/malformed-CSV failure while building a
    state's CIN index. Callers inside this module catch it and turn it
    into a flag; it should never escape lookup_company_by_cin()/
    enrich_*()."""


def _as_dict(record) -> dict:
    return asdict(record) if not isinstance(record, dict) else record


def _clean_field(value):
    """MCA source data commonly uses blank string, 'NA', 'N.A.', or '-' as
    a placeholder for "no value" -- normalize all of those to a real None
    rather than passing a fake-looking value through."""
    if value is None:
        return None
    if isinstance(value, str) and value.strip().upper() in ("", "NA", "N.A.", "N/A", "-"):
        return None
    return value


def _match_header(fieldnames: list, variants: list) -> Optional[str]:
    """Case-insensitive match of a CSV's actual header names against a
    list of known/plausible variants for one logical field (see
    _FIELD_VARIANTS). Returns the real fieldname to use, or None if none
    of the variants are present -- callers decide whether that's fatal
    (the CIN column) or just means that one optional field stays None."""
    lookup = {fn.strip().lower(): fn for fn in fieldnames}
    for variant in variants:
        hit = lookup.get(variant.strip().lower())
        if hit is not None:
            return hit
    return None


def state_name_from_cin(cin: str) -> Optional[str]:
    """Extracts a CIN's embedded 2-letter RoC state code (chars 7-8) and
    maps it to the lowercase full state name this project's local CSV
    filenames are keyed on. Returns None (never guesses) if the CIN isn't
    the standard 21-character length, or if the 2-letter code it finds
    isn't in _CIN_STATE_CODE_TO_NAME (e.g. "CI" for some foreign-company
    CINs, which follow a different scheme -- deliberately left unmapped
    rather than guessed at)."""
    if not cin or len(cin) != 21:
        return None
    code = cin[6:8].upper()
    return _CIN_STATE_CODE_TO_NAME.get(code)


def expected_csv_path_for_state(state_name: str, data_dir: Optional[str] = None) -> str:
    """The local file path this module expects for a given state name,
    e.g. "madhya pradesh" -> "{data_dir}/madhya_pradesh.csv". Exposed as
    its own function so README.md / test_part6b.py / the owner can all
    compute the same expected filename this module will actually look
    for, rather than that convention living in three places at once."""
    data_dir = data_dir or config.MCA_LOCAL_DATA_DIR
    filename = state_name.strip().lower().replace(" ", "_").replace("&", "and") + ".csv"
    return os.path.join(data_dir, filename)


def _load_state_index(state_name: str, data_dir: Optional[str] = None) -> dict:
    """Loads+parses one state's CSV (if not already cached) into a
    {cin_upper: {...normalized fields...}} index, matching headers
    case-insensitively against _FIELD_VARIANTS (see module docstring,
    "HEADER-MATCHING ROBUSTNESS"). Raises MCALookupError -- never
    silently returns an empty/wrong index -- if: the file is missing,
    NONE of the known CIN-column variants are present (which would mean
    every lookup would silently find nothing), or the file parses but
    has zero usable (non-empty-CIN) rows. Callers turn this into a flag."""
    if state_name in _STATE_CIN_INDEX_CACHE:
        cached = _STATE_CIN_INDEX_CACHE[state_name]
        if cached is _LOAD_FAILURE:
            raise MCALookupError(
                f"previously failed to load the local CSV for '{state_name}' "
                f"this run -- see the first failure's flag for why"
            )
        return cached

    path = expected_csv_path_for_state(state_name, data_dir)
    if not os.path.isfile(path):
        _STATE_CIN_INDEX_CACHE[state_name] = _LOAD_FAILURE
        raise MCALookupError(
            f"no local MCA data file for state '{state_name}' -- expected "
            f"it at {path}. Download it from data.gov.in (My Account -> "
            f"Download History once a Preview & Download request "
            f"completes -- see README.md's Part 6B section for the exact "
            f"steps) and save it at that exact path."
        )

    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            cin_header = _match_header(fieldnames, _FIELD_VARIANTS["cin"])
            if cin_header is None:
                raise MCALookupError(
                    f"{path} doesn't have any recognized CIN column. Known "
                    f"variants tried: {_FIELD_VARIANTS['cin']}. Actual "
                    f"columns found: {fieldnames}. This usually means the "
                    f"file wasn't exported from the 'Registrars of "
                    f"Companies (RoC)-wise Company Master Data' resource, "
                    f"or the export uses a header name not yet in "
                    f"_FIELD_VARIANTS['cin'] -- add it there once you see "
                    f"what it actually is."
                )
            header_map = {
                clean_key: _match_header(fieldnames, variants)
                for clean_key, variants in _FIELD_VARIANTS.items()
            }
            index: dict = {}
            duplicate_cins = 0
            for row in reader:
                raw_cin = row.get(cin_header)
                cin_key = _clean_field(raw_cin)
                if not cin_key:
                    continue
                cin_key = cin_key.strip().upper()
                normalized = {
                    clean_key: (_clean_field(row.get(real_header)) if real_header else None)
                    for clean_key, real_header in header_map.items()
                }
                if cin_key in index:
                    duplicate_cins += 1  # data-quality note, not fatal -- last one wins
                index[cin_key] = normalized
    except MCALookupError:
        _STATE_CIN_INDEX_CACHE[state_name] = _LOAD_FAILURE
        raise
    except (OSError, csv.Error) as e:
        _STATE_CIN_INDEX_CACHE[state_name] = _LOAD_FAILURE
        raise MCALookupError(f"failed to read {path}: {e}") from e

    if not index:
        _STATE_CIN_INDEX_CACHE[state_name] = _LOAD_FAILURE
        raise MCALookupError(
            f"{path} was read successfully but contained zero usable rows "
            f"(0 rows with a non-empty CIN column) -- check the file isn't "
            f"empty/corrupted/still mid-download."
        )
    if duplicate_cins:
        # Not fatal (see docstring) -- but worth a flag on first load
        # rather than staying invisible, since it's a real data-quality
        # property of the downloaded file, not something this module can
        # fix by picking a "better" duplicate.
        index["__duplicate_cins__"] = duplicate_cins

    _STATE_CIN_INDEX_CACHE[state_name] = index
    return index


def lookup_company_by_cin(cin: Optional[str], data_dir: Optional[str] = None) -> dict:
    """
    Best-effort MCA company master-data lookup for ONE CIN, against a
    locally downloaded per-state CSV. Never raises.

    Returns:
      {"mca_data": {...normalized fields, see _FIELD_VARIANTS...},
       "flags": []}
    on a clean match, or:
      {"mca_data": None, "flags": ["<human-readable reason>"]}
    on: no CIN given, a CIN whose embedded state code isn't in
    _CIN_STATE_CODE_TO_NAME, that state's CSV not downloaded yet / not
    readable, or no matching CIN row inside a CSV that IS present.
    """
    if not cin:
        return {
            "mca_data": None,
            "flags": ["MCA lookup skipped: no CIN available for this listing"],
        }

    state_name = state_name_from_cin(cin)
    if state_name is None:
        return {
            "mca_data": None,
            "flags": [
                f"MCA lookup skipped: CIN {cin!r}'s embedded state code "
                f"isn't in this project's known RoC state-code table "
                f"(_CIN_STATE_CODE_TO_NAME in mca_lookup.py)"
            ],
        }

    try:
        index = _load_state_index(state_name, data_dir)
    except MCALookupError as e:
        return {"mca_data": None, "flags": [f"MCA lookup skipped: {e}"]}

    raw = index.get(cin.strip().upper())
    if raw is None:
        n_companies = sum(1 for k in index if k != "__duplicate_cins__")
        return {
            "mca_data": None,
            "flags": [
                f"MCA lookup found no match for CIN {cin} in the local "
                f"'{state_name}' data ({n_companies} companies loaded) -- "
                f"likely means this company was registered after the "
                f"dataset's own cutoff (data.gov.in's note on this "
                f"resource says company records only go up to 3 Nov "
                f"2023), or a state-code/RoC mismatch worth "
                f"double-checking if this happens a lot"
            ],
        }
    return {"mca_data": raw, "flags": []}


def enrich_record_with_mca(record, data_dir: Optional[str] = None) -> dict:
    """Runs lookup_company_by_cin() for ONE record's `cin` field and writes
    the result onto the record itself (mca_data, mca_lookup_attempted),
    mirroring scraper/ibbi.py's enrich_record_with_details() /
    enrich_record_with_notice() convention. Also returns the same dict
    lookup_company_by_cin() does, for callers that don't need the mutation."""
    r = _as_dict(record)
    result = lookup_company_by_cin(r.get("cin"), data_dir=data_dir)

    if hasattr(record, "mca_data"):
        record.mca_data = result["mca_data"]
    if hasattr(record, "mca_lookup_attempted"):
        record.mca_lookup_attempted = True
    if result["flags"] and hasattr(record, "flags") and isinstance(record.flags, list):
        record.flags.extend(result["flags"])

    return result


def enrich_batch_with_mca(records: list, data_dir: Optional[str] = None) -> list:
    """Runs enrich_record_with_mca() across a batch, same order/length as
    `records`. No delay needed between calls -- these are local file
    reads, not network requests (each state's file is parsed once and
    cached, see module docstring's Performance note), so this doesn't use
    config.GEMINI_REQUEST_DELAY_SECONDS/NEWS_SEARCH_REQUEST_DELAY_SECONDS
    -style pacing the way Parts 6A/6C do."""
    return [enrich_record_with_mca(record, data_dir=data_dir) for record in records]


if __name__ == "__main__":
    # Offline-only smoke check -- no local CSV files are required for
    # these to pass; they test the parts of this module that don't touch
    # disk at all (CIN parsing/state mapping, header matching), plus that
    # a genuinely missing local file degrades to a clean flag rather than
    # raising.
    print("Offline smoke check (no local data files required):\n")

    assert state_name_from_cin("U18101KA2002PLC030185") == "karnataka"
    assert state_name_from_cin("L15140UP1989PLC011396") == "uttar pradesh"
    assert state_name_from_cin("U01222WB1973PLC029137") == "west bengal"
    assert state_name_from_cin("U40106TG2002PTC048720") == "telangana"
    assert state_name_from_cin("U92199TZ1995PTC005954") == "tamil nadu"  # RoC Coimbatore
    assert state_name_from_cin(None) is None
    assert state_name_from_cin("TOO_SHORT") is None
    print("1. state_name_from_cin() extraction+mapping: all correct.")

    assert expected_csv_path_for_state("madhya pradesh", "data/x") == os.path.join("data/x", "madhya_pradesh.csv")
    assert expected_csv_path_for_state("delhi", "data/x") == os.path.join("data/x", "delhi.csv")
    print("2. expected_csv_path_for_state() naming convention: correct.")

    assert _match_header(["COMPANY_NAME", "CIN"], _FIELD_VARIANTS["cin"]) == "CIN"
    assert _match_header(["Corporate Identification Number"], _FIELD_VARIANTS["cin"]) == "Corporate Identification Number"
    assert _match_header(["corporate_identification_number"], _FIELD_VARIANTS["cin"]) == "corporate_identification_number"
    assert _match_header(["Some Other Column"], _FIELD_VARIANTS["cin"]) is None
    print("3. _match_header() case-insensitive variant matching: all correct.")

    r1 = lookup_company_by_cin(None)
    print(f"4. No CIN:                mca_data={r1['mca_data']!r}  flags={r1['flags']}")
    assert r1["mca_data"] is None and r1["flags"]

    r2 = lookup_company_by_cin("U99999ZZ2002PLC030185")  # "ZZ" isn't a real state code
    print(f"5. Unmapped state code:   mca_data={r2['mca_data']!r}  flags={r2['flags']}")
    assert r2["mca_data"] is None and r2["flags"]

    r3 = lookup_company_by_cin("U18101KA2002PLC030185", data_dir="/tmp/definitely_does_not_exist")
    print(f"6. Missing local file:    mca_data={r3['mca_data']!r}  flags={r3['flags']}")
    assert r3["mca_data"] is None and r3["flags"]

    print("\nAll offline checks passed. Real matches need at least one "
          "state's CSV downloaded and placed per expected_csv_path_for_"
          "state() -- see README.md's Part 6B section, then run "
          "test_part6b.py.")
