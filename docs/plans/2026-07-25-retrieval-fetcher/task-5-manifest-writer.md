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
    # attempt is 0-BASED, same convention as backoff_delay
```

From task 3 — the robots provenance producer and the live slot delay:

```python
crawler.robots_info: dict[str, dict]
# netloc -> {"robots_url": str, "robots_sha256": str|None, "robots_fetched_at": str|None}
crawler.engine.downloader.slots[netloc].delay   # float; the delay in effect for the host
```

## Provides

```python
def append_entry(manifest_path: str, entry: dict) -> None
    """Serialise one entry as a single JSON line and append, fsync'd. Creates the
    file if absent. Raises ManifestSchemaError if a required key is missing."""

def load_prior_index(manifest_path: str) -> dict[str, str]
    """url_requested -> raw_bytes_sha256 of its most recent 2xx entry, where
    "most recent" means LAST MATCHING LINE IN FILE ORDER — fetched_at is never
    consulted (append order is the authority; the two can diverge under
    concurrency and after a git merge). Returns {} when the manifest does not
    exist. A trailing partial line is ignored, not an error."""

class ManifestSchemaError(ValueError): ...

REQUIRED_KEYS = frozenset({
    "schema", "url_requested", "url_final", "attempt_n", "fetched_at",
    "http_status", "response_protocol", "raw_bytes_sha256", "raw_bytes_length",
    "cache_relpath", "content_type", "request_headers", "response_headers",
    "redirect_chain", "etag", "etag_is_weak", "last_modified", "disposition",
    "fetch_policy", "useragent_sent", "prior_fetch_ref", "seed_signal",
})   # exactly 22 — the schema sample below, key for key
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
  "response_protocol": "HTTP/1.1",
  "raw_bytes_sha256": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
  "raw_bytes_length": 5,
  "cache_relpath": "sha256/2c/2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
  "content_type": "text/html; charset=utf-8",
  "request_headers": {"User-Agent": "evidence-fetch/0.1 (+mailto:…)", "Accept": "*/*"},
  "response_headers": {"Content-Type": "text/html; charset=utf-8", "ETag": "W/\"abc\""},
  "redirect_chain": ["https://example.com/pricing"],
  "etag": "W/\"abc\"",
  "etag_is_weak": true,
  "last_modified": "Fri, 24 Jul 2026 09:00:00 GMT",
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

- **Every key in `REQUIRED_KEYS` is present in every line. A field with no value is
  written as `null`, never omitted** — with `append_entry` rejecting missing keys, omission
  is the difference between a written line and a crashed run. Nullable: `content_type`
  (header absent), `response_protocol` (Scrapy exposes none), `etag`, `etag_is_weak`
  (`null` exactly when `etag` is), `last_modified`, `prior_fetch_ref`, `seed_signal`, and
  `fetch_policy.robots_sha256` / `robots_fetched_at`. Everything else is never `null`.
- `fetched_at` is UTC, ISO 8601, millisecond precision, `Z` suffix. Not local time. It is
  the instant the recorder observed the response (response side), not the request send time.
- `attempt_n` is **1-based** and counts attempts for this URL *in this run*. Both
  `backoff_delay` and `classify_status` take a **0-based** attempt. The conversion is
  computed **once** — `zero_based = entry["attempt_n"] - 1` — and passed to both; a second
  `- 1` at either call site is the off-by-one this note exists to prevent.
- `response_protocol` is `scrapy.http.Response.protocol` (e.g. `"HTTP/1.1"`), `null` when
  unavailable. **There is deliberately no `response_status_line`**: Scrapy drops the reason
  phrase at the download-handler boundary, so a status line could only be synthesised — and
  `HTTPStatus(522)` raises on codes this fetcher retries. A synthesised line in the fidelity
  set would fake the fidelity the set exists to guarantee. A WARC export renders
  `{protocol} {status}` plus a table phrase and must label itself a reconstruction of the
  phrase only.
- `fetch_policy` is an object with **exactly** `delay_used_s`, `robots_url`,
  `robots_sha256`, `robots_fetched_at` — validated by `append_entry` (the one nested
  validation; header objects stay free-form). `delay_used_s` is the **configured slot
  delay** read from `crawler.engine.downloader.slots[netloc].delay` at record time — with
  `RANDOMIZE_DOWNLOAD_DELAY = False` the configured and actual delays coincide. The three
  robots fields come from `crawler.robots_info[netloc]` (task 3); never from a second
  robots.txt GET.
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
- `schema` is `1`. Conditional-GET fields (`validators_sent`, `conditional_hit`) existed
  in an earlier draft and were **removed** (plan-review F9): no v1 task builds a conditional
  request, `DummyPolicy` forecloses it at the framework level, and a required field for an
  unreachable mechanism is a standing lie. When conditional GET lands, its fields arrive
  with `schema: 2`.

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
- **The recorder is registered at downloader-middleware priority 1000** — above
  `HttpCompressionMiddleware` (590) and `HttpCacheMiddleware` (900) — so its
  `process_response` sees the response **first**, wire-faithful. This replaces an earlier
  sentence ("end of the downloader chain … after redirects and retries are resolved") that
  was self-contradictory: `process_response` runs highest-priority-first, so "after
  redirects" and "end of the chain" name opposite ends (plan-review F4).
- **"Raw bytes" means the wire octets.** Below 590, `HttpCompressionMiddleware` inflates a
  gzip body (measured: 38 → 1013 bytes), carries `Content-Length: 38` over unchanged, and
  deletes `Content-Encoding` — hashing that is hashing a reconstruction. At 1000 the cached
  gzip artifact keeps `Content-Encoding: gzip` in `response_headers`, and its length matches
  `Content-Length`. Decompression is sub-project 2's job, reading from the cache. The test
  suite serves one `Content-Encoding: gzip` response to pin this; the plain-text server
  cannot see it.
- **A response carrying the `"cached"` flag writes no entry and no artifact** — Scrapy's
  `HttpCacheMiddleware` serves cache hits through every `process_response`, and a cache hit
  is not an attempt (rule 15). Without this skip, deleting `.jobdir/` (which the runbook
  calls disposable) mints manifest lines for fetches that never happened.
- **A redirect hop is its own attempt.** At priority 1000 the recorder sees the 301 before
  `RedirectMiddleware` (600) converts it, so the hop is recorded — its body cached, its
  `redirect_chain` ending at the hop, `disposition: "ok"` (3xx is `OK`). The final entry's
  `redirect_chain` spans requested → final via `response.meta["redirect_urls"]`. A
  two-hop-free redirect example therefore produces **two** manifest lines.
- It must record even when a later middleware will raise. Read the installed Scrapy for the
  exact registration mechanics — that seam is why the task is `contract`; the priority and
  the four rules above are not seams, they are pinned.

## Error model

Validation is owned per function — pinned, because the review showed the unowned version
breaks resume the moment sub-project 2 appends its own lines (plan-review #12):

| Failure | Function · raises / behaviour | Message substring |
|---|---|---|
| Entry missing a required key | `append_entry` raises `ManifestSchemaError` | `missing required key` |
| Entry has an unknown key | `append_entry` raises `ManifestSchemaError` | `unknown key` |
| `fetch_policy` not exactly its four keys | `append_entry` raises `ManifestSchemaError` | `fetch_policy` |
| Valid JSON line **without** `url_requested` | `load_prior_index` **skips it silently** — it is another producer's line (sub-project 2), not corruption | — |
| Line with `url_requested` and `schema != 1` | `load_prior_index` raises `ManifestSchemaError` | `unknown schema version` |
| Malformed JSON line, not last | `load_prior_index` raises `ManifestSchemaError` | `corrupt manifest line` |
| Malformed JSON final line | Skipped silently | — |
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
test_foreign_lines_are_skipped_by_the_reader     # sub-project 2's lines never break resume
test_unknown_schema_version_on_a_fetcher_line_raises
test_gzip_response_caches_wire_bytes             # 38 gzip octets, not 1013 inflated (F4)
test_cached_flag_writes_no_entry                 # a cache hit is not an attempt (#13)
```

## Checks

```
test -f fetcher/evidence_fetch/manifest.py
test -f fetcher/evidence_fetch/middlewares/record.py
grep -qF 'cache_relpath' fetcher/evidence_fetch/manifest.py
grep -qF 'REQUIRED_KEYS' fetcher/evidence_fetch/manifest.py
grep -qF 'response_protocol' fetcher/evidence_fetch/manifest.py
! grep -qF 'validators_sent' fetcher/evidence_fetch/manifest.py
! grep -rqF 'normalized_content_sha256' fetcher/evidence_fetch/
grep -qF '"cached"' fetcher/evidence_fetch/middlewares/record.py
grep -qF 'test_503_then_200_produces_two_entries_and_url_not_failed' fetcher/tests/test_manifest.py
grep -qF 'test_partial_final_line_is_tolerated' fetcher/tests/test_manifest.py
grep -qF 'test_prior_fetch_ref_points_at_most_recent_2xx' fetcher/tests/test_manifest.py
grep -qF 'test_foreign_lines_are_skipped_by_the_reader' fetcher/tests/test_manifest.py
grep -qF 'test_gzip_response_caches_wire_bytes' fetcher/tests/test_manifest.py
grep -qF 'test_cached_flag_writes_no_entry' fetcher/tests/test_manifest.py
uv run --project fetcher python -m unittest discover -s fetcher/tests -t fetcher -q
```

The negative check on `normalized_content_sha256` is scoped to the whole
`fetcher/evidence_fetch/` package, not one file — the review showed the one-file version
was blind to the field being written in `record.py`, the very module this task creates.
`record.py` also now carries its own `test -f`, so the negative checks in this task cannot
pass vacuously.
