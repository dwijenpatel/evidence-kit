# Task 7 — Wayback adapter and the capture-date grading rule

**Tier:** `code-complete` · **PRD criteria:** A8

Two halves: a URL adapter (code), and a grading rule (method). The grading rule is the half
that would be forgotten, and it is the half that keeps a Wayback-sourced row honest.

Scope is **retrieval fallback only** (D19). Price-history backfill is out of v1 — the
operator judged it not worth the cost, and §4.1 of the PRD sharpens why: the providers with
the deepest capture history are the slow-moving ones, so the available history is the least
informative history. The CDX mechanics below are recorded because they were verified and
would otherwise be re-researched from zero.

## Files

| Path | Responsibility |
|---|---|
| `fetcher/evidence_fetch/wayback.py` (new) | URL construction and CDX row parsing |
| `fetcher/tests/test_wayback.py` (new) | Tests, no network |
| `method/GRADING.md` (modify) | The `as_of` = capture-date rule |
| `method/CONVENTIONS.md` (modify) | One cross-reference |

## Provides

```python
EMPTY_SHA1 = "3I42H3S6NNFQ2MSVX7XZKYAYSCX5QBYJ"   # base32 SHA-1 of b"" — "nothing captured"

def capture_url(timestamp: str, original_url: str) -> str
    """Replay URL returning ORIGINAL bytes: web.archive.org/web/<ts>id_/<url>.
    Raises ValueError unless timestamp is exactly 14 digits."""

def cdx_query_url(url: str, *, from_ts: str | None = None, to_ts: str | None = None,
                  collapse_digest: bool = True, limit: int | None = None) -> str
    """CDX search URL with fl=timestamp,digest,statuscode and output=json."""

@dataclass(frozen=True)
class Capture:
    timestamp: str      # 14 digits
    digest: str         # base32 SHA-1, as CDX reports it
    status: str         # CDX statuscode, a STRING — may be "-" for unknown

def parse_cdx(body: bytes) -> list[Capture]
    """Parse a CDX JSON response. Row 0 is a header row and is dropped.
    Returns [] for an empty response body."""

def distinct_digests(captures: list[Capture]) -> list[str]
    """ALL digests, first-appearance order, deduplicated GLOBALLY. No filtering."""

def content_digests(captures: list[Capture]) -> list[str]
    """Digests representing retrievable content: status == "200" only, and never
    EMPTY_SHA1. This — not distinct_digests — is the input to "how many states has
    this page taken"; counting a failed or empty capture as a state inflates every
    staleness report."""
```

(The full implementation and test file are below — this task is `code-complete`, and after
the review that word is load-bearing: the ratified draft shipped signatures only, which left
`cdx_query_url`'s output and `parse_cdx`'s empty-body behaviour open. Now they are code.)

## The `id_` modifier — why it matters

`https://web.archive.org/web/<ts>id_/<url>` returns the **original unmodified bytes** with
origin headers preserved as `X-Archive-Orig-*`. Verified: `Content-Length` matched
`x-archive-orig-content-length` exactly.

Without `id_`, Wayback returns a *replay* page — rewritten links, injected toolbar. **A
replay page is not the evidence.** A fetcher that cached one would be storing the Internet
Archive's rendering of a document as though it were the document.

This is also why the cache needs no WARC support: a capture enters through the ordinary
fetch path, as an ordinary GET (D18, PRD §4).

## `collapse=digest` — the trap, and it is measured

CDX `collapse=digest` deduplicates **only adjacent rows**. Verified live: `example.com`
across ten days of 2020 returns **25 rows flapping between 3 distinct digests** — so a
row-count reading reports change roughly **8× too often**.

`distinct_digests` therefore deduplicates **globally**, not adjacently. That difference is
the whole function.

**Worked example.** CDX response body:

```json
[["timestamp","digest","statuscode"],
 ["20200101002334","JI6OR3QR4CI526JD6TMMNZNV4QPMPQCH","200"],
 ["20200101100018","WJM2KPM4GF3QK2BISVUH2ASX64NOUY7L","200"],
 ["20200101100757","JI6OR3QR4CI526JD6TMMNZNV4QPMPQCH","200"],
 ["20200106100020","O2XBZT4EZOUL6RS37E7DQFWAWWBEVGVJ","200"]]
```

| Call | Result |
|---|---|
| `len(parse_cdx(body))` | `4` |
| `len(distinct_digests(...))` | **`3`** — not 4 |
| `distinct_digests(...)[0]` | `"JI6OR3QR4CI526JD6TMMNZNV4QPMPQCH"` |

Reading "4 rows" as "4 changes" is the defect. Three distinct digests over four captures
means the page took three distinct states, and the alternation is Wayback seeing different
variants — not the page changing four times.

## Step 1 — `fetcher/evidence_fetch/wayback.py`, verbatim

```python
"""Wayback URL construction and CDX parsing. No network code lives here — a capture
URL is fetched by the ordinary spider path, and CDX responses arrive as cached bytes."""

import json
import re
from dataclasses import dataclass
from urllib.parse import urlencode

EMPTY_SHA1 = "3I42H3S6NNFQ2MSVX7XZKYAYSCX5QBYJ"   # base32 SHA-1 of b"": nothing captured
TS14 = re.compile(r"^\d{14}$")
CDX_BASE = "https://web.archive.org/cdx/search/cdx"
FIELDS = "timestamp,digest,statuscode"


def capture_url(timestamp: str, original_url: str) -> str:
    """Replay URL returning ORIGINAL bytes (the id_ modifier), scheme included."""
    if not TS14.match(timestamp):
        raise ValueError(f"need a 14-digit timestamp, got {timestamp!r}")
    return f"https://web.archive.org/web/{timestamp}id_/{original_url}"


def cdx_query_url(url: str, *, from_ts: str | None = None, to_ts: str | None = None,
                  collapse_digest: bool = True, limit: int | None = None) -> str:
    """CDX search URL. Parameter order is pinned: url, output, fl, from, to,
    collapse, limit — so the string is stable and testable."""
    params = [("url", url), ("output", "json"), ("fl", FIELDS)]
    if from_ts is not None:
        params.append(("from", from_ts))
    if to_ts is not None:
        params.append(("to", to_ts))
    if collapse_digest:
        params.append(("collapse", "digest"))
    if limit is not None:
        params.append(("limit", str(limit)))
    return f"{CDX_BASE}?{urlencode(params)}"


@dataclass(frozen=True)
class Capture:
    timestamp: str      # 14 digits
    digest: str         # base32 SHA-1, as CDX reports it
    status: str         # CDX statuscode — a STRING, may be "-" for unknown


def parse_cdx(body: bytes) -> list[Capture]:
    """CDX JSON -> Captures. Row 0 is the header row and is dropped. An empty body
    AND an empty JSON array both mean "no captures" and return [] — CDX sends the
    former for never-archived URLs, and treating either as an error would turn
    "never archived" into a crash."""
    if not body.strip():
        return []
    try:
        rows = json.loads(body)
    except json.JSONDecodeError as e:
        raise ValueError(f"not valid CDX JSON: {e}") from e
    if not isinstance(rows, list):
        raise ValueError("not valid CDX JSON: top level is not a list")
    captures = []
    for i, row in enumerate(rows[1:], start=1):
        if not isinstance(row, list) or len(row) < 3:
            raise ValueError(f"CDX row {i}: expected 3 fields, got {row!r}")
        captures.append(Capture(str(row[0]), str(row[1]), str(row[2])))
    return captures


def distinct_digests(captures: list[Capture]) -> list[str]:
    """All digests, first-appearance order, deduplicated globally — CDX's own
    collapse=digest is adjacent-only and over-reports change ~8x (measured)."""
    seen: set[str] = set()
    out: list[str] = []
    for c in captures:
        if c.digest not in seen:
            seen.add(c.digest)
            out.append(c.digest)
    return out


def content_digests(captures: list[Capture]) -> list[str]:
    """Digests of retrievable content only: status "200", never EMPTY_SHA1."""
    return distinct_digests([c for c in captures
                             if c.status == "200" and c.digest != EMPTY_SHA1])
```

## Step 2 — `fetcher/tests/test_wayback.py`, verbatim

```python
import base64
import hashlib
import unittest

from evidence_fetch.wayback import (EMPTY_SHA1, Capture, capture_url, cdx_query_url,
                                    content_digests, distinct_digests, parse_cdx)

CDX_BODY = (b'[["timestamp","digest","statuscode"],'
            b'["20200101002334","JI6OR3QR4CI526JD6TMMNZNV4QPMPQCH","200"],'
            b'["20200101100018","WJM2KPM4GF3QK2BISVUH2ASX64NOUY7L","200"],'
            b'["20200101100757","JI6OR3QR4CI526JD6TMMNZNV4QPMPQCH","200"],'
            b'["20200106100020","O2XBZT4EZOUL6RS37E7DQFWAWWBEVGVJ","200"]]')


class CaptureUrlTests(unittest.TestCase):
    def test_capture_url_uses_id_modifier(self):
        url = capture_url("20200101002334", "http://example.com/")
        self.assertEqual(
            url, "https://web.archive.org/web/20200101002334id_/http://example.com/")
        self.assertIn("id_/", url)

    def test_capture_url_rejects_short_timestamp(self):
        for bad in ("20200101", "2020010100233", "202001010023345", "not-a-ts"):
            with self.assertRaises(ValueError, msg=bad) as cm:
                capture_url(bad, "http://example.com/")
            self.assertIn("14-digit timestamp", str(cm.exception))


class CdxQueryTests(unittest.TestCase):
    def test_cdx_query_url_includes_collapse_and_fl(self):
        self.assertEqual(
            cdx_query_url("example.com"),
            "https://web.archive.org/cdx/search/cdx?url=example.com&output=json"
            "&fl=timestamp%2Cdigest%2Cstatuscode&collapse=digest")

    def test_cdx_query_url_orders_optional_params(self):
        self.assertEqual(
            cdx_query_url("example.com", from_ts="2020", to_ts="2021", limit=25),
            "https://web.archive.org/cdx/search/cdx?url=example.com&output=json"
            "&fl=timestamp%2Cdigest%2Cstatuscode&from=2020&to=2021"
            "&collapse=digest&limit=25")


class ParseCdxTests(unittest.TestCase):
    def test_parse_cdx_drops_the_header_row(self):
        captures = parse_cdx(CDX_BODY)
        self.assertEqual(len(captures), 4)
        self.assertEqual(captures[0],
                         Capture("20200101002334",
                                 "JI6OR3QR4CI526JD6TMMNZNV4QPMPQCH", "200"))

    def test_parse_cdx_handles_empty_body(self):
        for empty in (b"", b"  \n", b"[]"):
            self.assertEqual(parse_cdx(empty), [], msg=empty)

    def test_parse_cdx_rejects_invalid_json(self):
        with self.assertRaises(ValueError) as cm:
            parse_cdx(b"<html>oops</html>")
        self.assertIn("not valid CDX JSON", str(cm.exception))

    def test_parse_cdx_rejects_short_row(self):
        with self.assertRaises(ValueError) as cm:
            parse_cdx(b'[["timestamp","digest","statuscode"],["20200101002334"]]')
        self.assertIn("CDX row", str(cm.exception))


class DigestTests(unittest.TestCase):
    def test_distinct_digests_dedupes_globally_not_adjacently(self):
        self.assertEqual(len(distinct_digests(parse_cdx(CDX_BODY))), 3)

    def test_distinct_digests_preserves_first_appearance_order(self):
        self.assertEqual(distinct_digests(parse_cdx(CDX_BODY)), [
            "JI6OR3QR4CI526JD6TMMNZNV4QPMPQCH",
            "WJM2KPM4GF3QK2BISVUH2ASX64NOUY7L",
            "O2XBZT4EZOUL6RS37E7DQFWAWWBEVGVJ"])

    def test_content_digests_filters_non_200_and_empty_captures(self):
        captures = parse_cdx(CDX_BODY) + [
            Capture("20200107000000", EMPTY_SHA1, "200"),   # empty capture
            Capture("20200108000000", "SOMEREDIRECTDIGEST0000000000000A", "301"),
            Capture("20200109000000", "UNKNOWNSTATUSDIGEST000000000000B", "-"),
        ]
        self.assertEqual(len(distinct_digests(captures)), 6)   # pure dedupe keeps all
        self.assertEqual(len(content_digests(captures)), 3)    # staleness input filters

    def test_empty_sha1_constant_marks_no_content(self):
        computed = base64.b32encode(hashlib.sha1(b"").digest()).decode("ascii")
        self.assertEqual(computed, EMPTY_SHA1)
```

`test_distinct_digests_dedupes_globally_not_adjacently` uses the exact four rows from the
worked example and asserts `3` — if someone later "optimises" to adjacent dedup, it fails.
`test_content_digests_filters_non_200_and_empty_captures` pins the split the review found
unpinned: **`distinct_digests` never filters; `content_digests` is the staleness input.**
Counting a failed or empty capture as a page-state inflates every staleness report; counting
it out of the raw dedupe would silently hide captures from a completeness audit. Both
behaviours are wanted — under different names.

No test makes a network call (CLAUDE.md rule 19). CDX fixtures are real, from a verified
live query, trimmed.

## Step — the grading rule in `method/GRADING.md`

Add to the section covering `as_of` and decay:

```markdown
**Archived captures.** A row sourced from a web archive carries the **capture date** as
`as_of`, never the retrieval date, and it is evidence about what the page said *at that
capture*. Cite the capture URL including its timestamp, so the claim is re-checkable
against the same bytes. A capture is not weaker evidence than a live fetch for the moment
it covers — but it says nothing about the present, and a `price-surface` row built from a
two-year-old capture is two years stale no matter when it was retrieved. The archive's own
content digest may be recorded alongside; the base32 SHA-1 of empty content
(`3I42H3S6NNFQ2MSVX7XZKYAYSCX5QBYJ`) marks a capture that stored nothing and must never be
read as "the page was empty."
```

In `method/CONVENTIONS.md`, extend the `Parameters` bullet's `as_of` sentence with a
pointer: `(for an archived capture, see GRADING.md "Archived captures")`.

## How a capture actually gets fetched — there is no extra wiring, and that is the design

`capture_url()` returns **an ordinary URL**. It is fetched by putting it in `seeds.md` like
any other source, or by enqueuing it programmatically. There is no Wayback code path, no
Wayback middleware, and no Wayback branch in the spider — that is exactly what "enters the
cache through the same path as a live fetch" (A8) means, and it is why D18 could drop WARC.

So this task adds **no** spider changes. It adds URL construction, CDX parsing, and the
grading rule. To keep A8 from being merely asserted, one end-to-end test lives here:

```
test_capture_url_fetches_through_the_ordinary_spider_path
```

It serves a fake capture from the local `ThreadingHTTPServer` at a path shaped like
`/web/20200101002334id_/http://example.com/`, runs the spider against a seeds file
containing that URL, and asserts the resulting manifest entry has the same key set as any
other entry — no Wayback-specific fields, body byte-identical. If someone later adds a
Wayback branch, this test still passes, so pair it with the check below that greps for the
absence of such a branch. For that grep's sake, `fetch.py` must not name Wayback even in a
comment or docstring — this constraint lives here, not in the spider file it constrains.

**This does NOT mean the fetcher rewrites live URLs into capture URLs automatically.**
Choosing to reach for an archived copy is a judgement about a source, made by an operator or
an agent, not by the fetch layer.

## Error model

| Failure | Raises | Message substring |
|---|---|---|
| Timestamp not exactly 14 digits | `ValueError` | `14-digit timestamp` |
| CDX body is not valid JSON | `ValueError` | `not valid CDX JSON` |
| A CDX row has fewer fields than requested | `ValueError` | `CDX row` |
| CDX body is empty | returns `[]` | — |

The empty-body row is not an oversight: CDX returns an empty body — not an empty JSON array
— when a URL has no captures at all, and treating that as a parse error would turn "never
archived" into a crash.

## Checks

```
test -f fetcher/evidence_fetch/wayback.py
test -f fetcher/evidence_fetch/spiders/fetch.py
grep -qF 'id_/' fetcher/evidence_fetch/wayback.py
grep -qF '3I42H3S6NNFQ2MSVX7XZKYAYSCX5QBYJ' fetcher/evidence_fetch/wayback.py
grep -qF 'def content_digests' fetcher/evidence_fetch/wayback.py
grep -qF 'test_capture_url_uses_id_modifier' fetcher/tests/test_wayback.py
grep -qF 'test_content_digests_filters_non_200_and_empty_captures' fetcher/tests/test_wayback.py
grep -qF 'test_distinct_digests_dedupes_globally_not_adjacently' fetcher/tests/test_wayback.py
grep -qF 'test_capture_url_fetches_through_the_ordinary_spider_path' fetcher/tests/test_wayback.py
! grep -qiE 'wayback|archive\.org' fetcher/evidence_fetch/spiders/fetch.py
grep -qF 'Archived captures' method/GRADING.md
grep -qF 'capture date' method/GRADING.md
! grep -rEn --exclude-dir=__pycache__ '/Users/|/home/|/Volumes/|~/|repos/evidence-|\bidea-gen\b' method/
uv run --project fetcher python -m unittest discover -s fetcher/tests -t fetcher -q
python3 -m unittest tests.test_scaffold -q
```

`python3 -m unittest tests.test_scaffold -q` is included because this task edits `method/`,
and CLAUDE.md rule 11 requires `method/` and `SKILL.md` to stay mutually consistent. The
`test -f` on `spiders/fetch.py` exists so the Wayback-absence grep can never pass vacuously
against a missing file (plan-review #26).
