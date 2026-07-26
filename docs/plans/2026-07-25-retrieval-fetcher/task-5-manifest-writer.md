# Task 5 — the per-attempt manifest

**Tier:** `contract` · **PRD criteria:** A3, A5

**This task pins the seam between sub-project 1 and sub-project 2.** The manifest is what
the change-detection half consumes, and per D18 the container format is reversible while
**fidelity not captured at fetch time is not**. Getting the field set right now is the
one-way door; the file format is not.

## Files

| Path | Responsibility |
|---|---|
| `fetcher/evidence_fetch/manifest.py` (new) | `ManifestEntry`, `append_entry`, `load_prior_index` |
| `fetcher/evidence_fetch/middlewares/record.py` (new) | Downloader middleware that builds an entry per attempt |
| `fetcher/evidence_fetch/settings.py` (modify) | Register the middleware |
| `fetcher/tests/test_manifest.py` (new) | Tests |

## Consumes

From task 2 — restated so this spec is readable alone:

```python
def write_artifact(cache_root: str, body: bytes) -> tuple[str, str]
    """-> (sha256_hex, relpath). Idempotent."""
def cache_relpath(sha256_hex: str) -> str
    """-> 'sha256/<first-2>/<full>'"""
```

From task 4:

```python
class Disposition(enum.Enum): OK / RETRY / BLOCKED / FATAL
def classify_status(status: int, attempt: int, max_attempts: int = 3) -> Disposition
```

## Provides

```python
def append_entry(manifest_path: str, entry: dict) -> None
    """Serialise one entry as a single JSON line and append, fsync'd. Creates the
    file if absent. Raises ManifestSchemaError if a required key is missing."""

def load_prior_index(manifest_path: str) -> dict[str, str]
    """url_requested -> raw_bytes_sha256 of its most recent entry with a 2xx status.
    Returns {} when the manifest does not exist. A trailing partial line is ignored,
    not an error."""

class ManifestSchemaError(ValueError): ...

REQUIRED_KEYS: frozenset[str]     # the fetcher-written set below
```

## The schema — pinned

One JSON object per line. **The fetcher writes exactly these keys and no others.**

```json
{
  "schema": 1,
  "url_requested": "https://example.com/pricing",
  "url_final": "https://example.com/pricing/",
  "attempt_n": 1,
  "fetched_at": "2026-07-25T19:04:11.212Z",
  "http_status": 200,
  "raw_bytes_sha256": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
  "raw_bytes_length": 5,
  "cache_relpath": "sha256/2c/2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
  "content_type": "text/html; charset=utf-8",
  "request_headers": {"User-Agent": "evidence-fetch/0.1 (+mailto:…)", "Accept": "*/*"},
  "response_status_line": "HTTP/1.1 200 OK",
  "response_headers": {"Content-Type": "text/html; charset=utf-8", "ETag": "W/\"abc\""},
  "redirect_chain": ["https://example.com/pricing"],
  "etag": "W/\"abc\"",
  "etag_is_weak": true,
  "last_modified": "Fri, 24 Jul 2026 09:00:00 GMT",
  "validators_sent": {"If-None-Match": "W/\"abc\""},
  "conditional_hit": false,
  "disposition": "ok",
  "fetch_policy": {
    "delay_used_s": 7.0,
    "robots_url": "https://example.com/robots.txt",
    "robots_sha256": "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
    "robots_fetched_at": "2026-07-25T19:03:58.004Z"
  },
  "useragent_sent": "evidence-fetch/0.1 (+mailto:…)",
  "prior_fetch_ref": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
  "seed_signal": "operator noticed it in a discussion"
}
```

**Field notes where a reader could go wrong:**

- `fetched_at` is UTC, ISO 8601, millisecond precision, `Z` suffix. Not local time.
- `attempt_n` is **1-based** and counts attempts for this URL *in this run*. `backoff_delay`
  takes a **0-based** attempt. That mismatch is deliberate — a manifest is read by humans,
  a backoff formula is not — and it is the single most likely place to introduce an
  off-by-one, so the conversion is `backoff_delay(entry["attempt_n"] - 1)` and it appears in
  exactly one place.
- `redirect_chain` **always includes the requested URL as element 0**, so a non-redirected
  fetch has a one-element chain, never an empty one. `url_final` equals the chain's last
  element.
- `prior_fetch_ref` is the `raw_bytes_sha256` of the most recent prior **2xx** fetch of the
  same `url_requested`, or `null` on first fetch. It is deliberately the digest, not an entry
  id: the digest is what a recheck diffs against, and it needs no id scheme to stay stable.
- `seed_signal` is copied from the `Seeds` row that queued this URL, `null` for a
  link-followed or Wayback URL. Carrying it here means the provenance of a fetch survives
  even if the seed row is later edited — and PRD §11 makes that provenance a weak growth
  signal that cannot be reconstructed later.
- `response_headers` and `request_headers` preserve original casing and are objects, not
  lists. A repeated header joins with `", "` (RFC 9110 §5.3 field-order semantics).
- `schema` is `1`. A consumer that sees an unknown value must stop, not guess.

**Fields the fetcher does NOT write** — sub-project 2 owns these, and a fetcher that emits
them has violated CLAUDE.md rule 16:

```
extractor · extractor_version · normalized_content_sha256 · normalized_char_count
simhash64 · source_class · change_class
```

Sub-project 2 appends its own lines keyed by `raw_bytes_sha256`; it does not rewrite
fetcher lines. **The manifest is append-only. Nothing ever edits a written line.**

## Naming deviation from the PRD, and why

PRD §7 calls the storage-location field `mirror_path`. **This plan names it
`cache_relpath`.** `mirrors/` is an existing directory in the consuming corpus holding
LLM-extracted text, and the operator has ratified that it stays frozen and unmigrated. A
field named `mirror_path` would point readers at the wrong store — exactly the confusion the
freeze decision exists to prevent. The value is relative to the cache root, and the name says
so.

## Worked example — the 503-then-200 sequence

This is A3, and it is the behaviour the whole task exists for. Fetching
`https://web.archive.org/cdx/search/cdx?url=example.com` where the first attempt 503s:

```
{"schema":1,"url_requested":"https://web.archive.org/cdx/…","attempt_n":1,
 "http_status":503,"raw_bytes_sha256":"<digest of the 503 body>","raw_bytes_length":112,
 "disposition":"retry","prior_fetch_ref":null, …}
{"schema":1,"url_requested":"https://web.archive.org/cdx/…","attempt_n":2,
 "http_status":200,"raw_bytes_sha256":"<digest of the real body>","raw_bytes_length":48213,
 "disposition":"ok","prior_fetch_ref":null, …}
```

**Two lines. The URL is not marked failed.** The error body of the 503 is cached and hashed
like any other response — a WAF challenge page or a maintenance notice is evidence about the
attempt, and discarding it destroys the ability to recognise the same interstitial later.

`prior_fetch_ref` is `null` on **both** lines: the 503 was not a 2xx, so it never becomes
anything's prior reference.

## Implementation notes

- `append_entry` opens with `"a"`, writes `json.dumps(entry, sort_keys=True,
  ensure_ascii=False) + "\n"`, then `flush()` and `os.fsync()`. Sorted keys make the manifest
  diff cleanly in git, which is the reason it is the tracked half.
- A crash mid-write leaves a partial final line. `load_prior_index` must tolerate exactly
  that: wrap each `json.loads` and skip a line that fails to parse **only if it is the last
  line**; a malformed line anywhere else is corruption and must raise.
- The recording middleware runs at the **end** of the downloader chain so it observes the
  response after redirects and retries are resolved, and it must record even when a later
  middleware will raise. Read the installed Scrapy to place it — this is why the task is
  `contract`.

## Error model

| Failure | Raises / behaviour | Message substring |
|---|---|---|
| Entry missing a required key | `ManifestSchemaError` | `missing required key` |
| Entry has an unknown key | `ManifestSchemaError` | `unknown key` |
| `schema` value unknown to reader | `ManifestSchemaError` | `unknown schema version` |
| Malformed line, not last | `ManifestSchemaError` | `corrupt manifest line` |
| Malformed final line | Skipped silently | — |
| Manifest file absent | `load_prior_index` returns `{}` | — |

Rejecting unknown keys is deliberate: it is what stops sub-project 2's fields from drifting
into fetcher-written lines, which is the seam this task defends.

## Tests to write

```
test_append_then_load_roundtrips
test_missing_required_key_raises
test_unknown_key_raises
test_503_then_200_produces_two_entries_and_url_not_failed
test_prior_fetch_ref_is_none_when_only_non_2xx_exist
test_prior_fetch_ref_points_at_most_recent_2xx
test_partial_final_line_is_tolerated
test_corrupt_middle_line_raises
test_redirect_chain_includes_requested_url_when_no_redirect
test_keys_are_sorted_in_output
```

## Checks

```
test -f fetcher/evidence_fetch/manifest.py
grep -qF 'cache_relpath' fetcher/evidence_fetch/manifest.py
grep -qF 'REQUIRED_KEYS' fetcher/evidence_fetch/manifest.py
! grep -qF 'normalized_content_sha256' fetcher/evidence_fetch/manifest.py
grep -qF 'test_503_then_200_produces_two_entries_and_url_not_failed' fetcher/tests/test_manifest.py
grep -qF 'test_partial_final_line_is_tolerated' fetcher/tests/test_manifest.py
grep -qF 'test_prior_fetch_ref_points_at_most_recent_2xx' fetcher/tests/test_manifest.py
uv run --project fetcher python -m unittest discover -s fetcher/tests -t fetcher -q
```

The negative check on `normalized_content_sha256` enforces the sub-project seam
mechanically. It is the cheapest possible guard against the fetcher growing an extraction
step, which is how this component would stop being trustworthy.
