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
    """Digests in first-appearance order, deduplicated GLOBALLY."""
```

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

## Tests to write

```
test_capture_url_uses_id_modifier                 # asserts 'id_/' is in the result
test_capture_url_rejects_short_timestamp          # 8 digits -> ValueError
test_cdx_query_url_includes_collapse_and_fl
test_parse_cdx_drops_the_header_row
test_parse_cdx_handles_empty_body                 # b"" -> []
test_distinct_digests_dedupes_globally_not_adjacently   # the 4-row/3-digest example above
test_distinct_digests_preserves_first_appearance_order
test_empty_sha1_constant_marks_no_content
```

`test_distinct_digests_dedupes_globally_not_adjacently` uses the exact four rows above and
asserts `3`. If someone later "optimises" it to adjacent dedup, that test fails — which is
the point, because the bug it prevents is silent and would inflate every staleness report.

No test makes a network call (CLAUDE.md rule 19). CDX responses are fixtures — real ones,
copied from a verified live query and trimmed.

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
absence of such a branch.

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
grep -qF 'id_/' fetcher/evidence_fetch/wayback.py
grep -qF '3I42H3S6NNFQ2MSVX7XZKYAYSCX5QBYJ' fetcher/evidence_fetch/wayback.py
grep -qF 'test_distinct_digests_dedupes_globally_not_adjacently' fetcher/tests/test_wayback.py
grep -qF 'Archived captures' method/GRADING.md
grep -qF 'capture date' method/GRADING.md
! grep -rEn --exclude-dir=__pycache__ '/Users/|/home/|/Volumes/|~/|repos/evidence-|\bidea-gen\b' method/
uv run --project fetcher python -m unittest discover -s fetcher/tests -t fetcher -q
python3 -m unittest tests.test_scaffold -q
```

`python3 -m unittest tests.test_scaffold -q` is included because this task edits `method/`,
and CLAUDE.md rule 11 requires `method/` and `SKILL.md` to stay mutually consistent.
