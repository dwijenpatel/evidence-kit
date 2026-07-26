# Task 6 — the spider: seeds → queue → cache → manifest

**Tier:** `contract` · **PRD criteria:** A2, A7, A9

The integration task. Everything else in this plan is a component; this is the thing an
operator runs.

## Files

| Path | Responsibility |
|---|---|
| `fetcher/evidence_fetch/spiders/__init__.py` (new) | Empty package marker |
| `fetcher/evidence_fetch/spiders/fetch.py` (new) | `FetchSpider` |
| `fetcher/evidence_fetch/cli.py` (new) | `python -m evidence_fetch` entry point |
| `fetcher/tests/test_spider.py` (new) | End-to-end against a local server |
| `fetcher/README.md` (modify) | Runbook |

## Consumes

Restated in full — a fresh implementer sees only this spec:

```python
# evidence_fetch.seeds
@dataclass(frozen=True)
class Seed:
    url: str; added: str; signal: str; question: str
def read_seeds(path: str) -> list[Seed]
class SeedFormatError(ValueError): ...

# evidence_fetch.cache
def write_artifact(cache_root: str, body: bytes) -> tuple[str, str]   # (digest, relpath)

# evidence_fetch.manifest
def append_entry(manifest_path: str, entry: dict) -> None
def load_prior_index(manifest_path: str) -> dict[str, str]            # url -> digest
REQUIRED_KEYS: frozenset[str]

# evidence_fetch.backoff
def backoff_delay(attempt: int, base: float = 1.0, cap: float = 60.0,
                  rand: Callable[[], float] = random.random) -> float  # attempt is 0-BASED
def parse_retry_after(value: str | None, now: datetime) -> float | None
def classify_status(status: int, attempt: int, max_attempts: int = 3) -> Disposition
                                                                        # attempt is 0-BASED
class Disposition(enum.Enum): OK / RETRY / BLOCKED / FATAL
```

## Provides

```
uv run --project fetcher python -m evidence_fetch \
    --seeds <path to a Seeds document> \
    --cache-root <dir> \
    --manifest <path to manifest.jsonl> \
    --contact <URL or mailto: for the User-Agent> \
    [--jobdir <dir>]        # default: <cache-root>/.jobdir
    [--limit N]             # stop after N successful fetches; for smoke runs
```

**Runtime settings the CLI derives** — both land under the cache root so the single
`cache/` ignore line covers everything the fetcher writes:

```
HTTPCACHE_DIR = <abspath(cache-root)>/httpcache   # data_path() passes absolute paths
                                                  # through; the bare "httpcache" default
                                                  # would land in <cwd>/.scrapy/ (#15)
JOBDIR        = <cache-root>/.jobdir              # unless --jobdir is given
```

- The cache root and the manifest's parent directory are **created on demand**; the
  "not writable" error means creation or a write failed, never mere absence.
- `--limit N` counts **2xx responses with a non-null `seed_signal` recorded this run** —
  robots.txt fetches are recorded but do not count toward N (they are overhead, not
  yield; R5). Once reached, no new requests are scheduled. Responses already in flight
  are still recorded (rule 15), so the manifest may exceed N by up to the cross-host
  concurrency.
- An **empty seed table** (header + alignment row, zero data rows — guard-valid, and
  `read_seeds` returns `[]`) is a no-op: exit 0, zero requests, manifest untouched.
- **Duplicate seed URLs: the first row wins** — it is enqueued and its `signal` becomes
  `seed_signal`; each later duplicate is logged at WARNING with substring `duplicate seed`.

`--contact` is **required**. Starting without it exits 2 with a message containing
`--contact is required`. Rationale: RFC 9309 §2.2.1 makes the product token functional —
an unidentified crawler falls under the most restrictive `*` robots group — and the
`USER_AGENT` in settings carries a literal `{contact}` placeholder that must never reach
the wire.

## Behaviour, pinned

1. Read seeds. A `SeedFormatError` exits **2** before any network call. Never start a
   partial crawl from a malformed queue.
2. Load the prior index from the manifest once at start.
3. Enqueue every seed URL **from `async def start()`**. In scrapy 2.17.0 the classic
   `start_requests()` is consulted by **nothing** — it survives only in a docstring, and
   the default `start()` reads `start_urls` alone, so a spider defining only
   `start_requests` crawls zero URLs with no warning (probed: 0 requests, clean
   `finish_reason: finished`). Seed requests carry
   `meta={"attempt_n": 1, "seed_signal": <row's signal>}` — the recorder is a downloader
   middleware and learns both values from meta, nowhere else — and `dont_filter=False`,
   so Scrapy's fingerprint dedup and the persisted `JOBDIR` frontier give A9's resume.
4. **Caching and recording are the record middleware's job (task 5), never the spider's.**
   Every response — every status, every content type, redirect hops **and robots.txt
   fetches included**; `"cached"`-flagged responses excluded (the one exclusion) — is
   cached and recorded there, wire-faithful. A robots fetch goes through
   `engine.download_async` and the full downloader chain, so the recorder at 1000 sees it
   (probed: 2 seeds on one host → **3** recorded responses, `/robots.txt` first); its
   entry carries `seed_signal: null`, `attempt_n: 1`, and task 5's fetch-policy fallback.
   The spider callback never touches `response.body` and never names content types, **even
   in comments or docstrings** — a check greps `fetch.py` for the absence of the string.
   The spider's whole job is scheduling: seeds in, retry decisions out.
4a. **The spider pins `custom_settings = {"HTTPERROR_ALLOW_ALL": True}`.** Without it,
   Scrapy's `HttpErrorMiddleware` drops every non-2xx before the callback: it consults
   `request.meta["handle_httpstatus_all"]`, the `HTTPERROR_ALLOW_ALL` setting, and a
   `handle_httpstatus_list` spider attribute — **a spider attribute named
   `handle_httpstatus_all` is read by nothing** (probed; Amendment 1 pinned exactly that
   attribute, and it was inert: the 403 was served, the callback never fired, zero
   reschedules). The recorder at 1000 sits *upstream* of this spider-middleware drop, so
   A3's manifest lines survive either way — what dies without the setting is **the
   callback**, i.e. every retry decision and A4 itself. **This does NOT mean errors are
   ignored** — `classify_status` still sets the disposition; the setting only guarantees
   the response reaches `parse`. (Plan-review F2, corrected by R2.)
5. `content_type` is recorded and nothing is branched on it. **This is A7.** A JSON body and
   an HTML body traverse identical code; the only difference that ever exists is the value
   in that field.
6. The spider **parses nothing and follows no links in v1.** It fetches exactly what is
   queued. Link-following is PRD §11's automated expansion and is not in this sub-project.
7. **The spider is the only retry mechanism.** `RETRY_ENABLED = False` (task 2) — Scrapy's
   `RetryMiddleware` cannot honour `Retry-After` (its source contains zero occurrences of
   the header), and with it on, the callback never sees a retryable response while its
   retries remain, making this item dead code. On `Disposition.RETRY`, reschedule after
   `parse_retry_after(retry_after_header, now) or backoff_delay(zero_based)` seconds, where
   `zero_based = attempt_n - 1` is computed **once** and passed to both `classify_status`
   and `backoff_delay`. **The retry request is pinned** (plan-review R3):

   ```python
   response.request.replace(dont_filter=True,
                            meta={**response.request.meta, "attempt_n": n + 1})
   ```

   `dont_filter=True` because a retry re-requests a URL whose fingerprint the dupefilter
   has already seen — with the item-3 default, the scheduler eats every retry silently
   (probed: a host 403ing forever produced **one** wire hit, and no retry ever left the
   scheduler; Scrapy's own `RetryMiddleware` sets the same flag for the same reason).
   **This does NOT mean seeds change** — item 3's `dont_filter=False` is scoped to seed
   requests; only retries pass `True`. Retries then reach the wire only because task 2
   keeps every retryable status out of Scrapy's HTTP cache
   (`HTTPCACHE_IGNORE_HTTP_CODES`): `DummyPolicy` serves any stored response to any later
   request for that URL, so without the setting, attempts 2–4 of a 403 are answered from
   disk, flagged `"cached"`, skipped by the recorder — and backoff never touches the wire
   (probed: 4 callbacks, one wire hit; plan-review R4). Worked example — a host answering
   403 to every request, default `max_attempts=3`: exactly **4 attempts** hit the host
   (the handler's hit counter reads 4); manifest lines `attempt_n` 1–4 with dispositions
   `retry, retry, retry, blocked`. **This does NOT mean 3 attempts** — `classify_status`
   blocks when `zero_based >= 3`, i.e. on the 4th.

**This does NOT mean the spider skips non-2xx bodies.** A 403 challenge page and a 503
maintenance notice are cached and hashed like any other response (task 5). Recognising the
same interstitial on a later run is only possible if it was stored.

## Worked example

`seeds.md`:

```
| url | added | signal | question |
|---|---|---|---|
| http://127.0.0.1:PORT/a.json | 2026-07-25 | test | what shape |
| http://127.0.0.1:PORT/b.html | 2026-07-25 | test | what shape |
```

Local server: `/a.json` returns `{"x":1}` as `application/json`; `/b.html` returns
`<html>b</html>` as `text/html`. After one run, `manifest.jsonl` has exactly **three**
lines (both seeds share one host, so one robots fetch): the host's `/robots.txt` first —
`seed_signal: null`, its bytes cached like any other response — then the two seeds, both
`"http_status":200`, with `content_type` differing and **every other structural field
present in both seed lines**. All three bodies exist under `cache-root/sha256/…`,
byte-identical to what the server sent. **This does NOT mean two lines** — the earlier
draft said two, before R5 established that the recorder at 1000 sees the robots fetch.

Re-running the same command with the same `--jobdir` and manifest performs **zero** new
fetches and appends **zero** new lines — the dupefilter drops every seed before the
downloader, so no request reaches the robots middleware and the robots fetch is not
re-issued either.

## Tests to write

```
test_two_seeds_produce_three_entries_including_robots  # robots line FIRST, seed_signal
                                                       # null on it (R5)
test_json_and_html_take_the_same_path          # key sets equal; see the A7 note below
test_cached_bytes_are_byte_identical           # sha256 of file == sha256 of served bytes
test_rerun_refetches_nothing                   # A9; zero new lines, robots included
test_interrupted_run_resumes_from_jobdir       # A9
test_jobdir_delete_with_httpcache_writes_no_new_entries   # (#13): 0 server hits, 0 lines
test_malformed_seeds_exits_2_before_any_request # server records zero hits
test_missing_contact_exits_2
test_403_then_200_yields_two_entries_and_the_body_is_cached
    # THE composed R2+R3+R4 regression, and the one test that catches all three:
    # asserts TWO wire hits via the handler's counter (a cache-served retry writes a
    # second line but not a second hit), two entries for the target URL (dispositions
    # retry, ok), and the 200 body cached. Red if the callback never sees the 403
    # (R2), if the dupefilter eats the retry (R3), or if the retry is answered from
    # the HTTP cache (R4).
test_503_reaches_the_recorder_and_is_cached    # A3: the recorder at 1000 writes the
                                               # entry and caches the 503 body. The
                                               # recorder sits UPSTREAM of the
                                               # HttpError drop, so this test alone
                                               # cannot see a broken spider — the
                                               # 403-then-200 test covers the
                                               # callback half (R2).
test_redirect_records_full_chain_and_url_final # the 301 hop is ALSO its own entry
                                               # (task 5) and BOTH entries carry the
                                               # same attempt_n (#12)
test_empty_seed_table_is_a_noop                # exit 0, zero requests (#23)
test_duplicate_seed_first_row_wins             # first signal survives; WARNING logged (#25)
test_httpcache_lands_under_the_cache_root      # R9: run the CLI as a subprocess with
                                               # cwd != cache-root's parent; assert
                                               # <cache-root>/httpcache/ exists and
                                               # <cwd>/.scrapy does not — the settings
                                               # default resolves through data_path()
                                               # into <cwd>/.scrapy and both cache
                                               # tests sharing one cwd could not see
                                               # the override being lost
```

**A7 is enforced by three instruments together**, because the review proved no single one
can be sound and complete (plan-review F8):

1. `test_json_and_html_take_the_same_path` asserts the two entries' **key sets are equal**
   and that `schema`, `disposition`, and `http_status` are equal. It does **NOT** enumerate
   which values may differ — the ratified version's 8-key allow-list failed a correct spider
   (`response_headers`, `Date`, and `fetch_policy.delay_used_s` legitimately differ between
   the two responses), and any list wide enough to pass a correct spider also passes a
   re-serialised body.
2. `test_cached_bytes_are_byte_identical` — forbids a second **recording** path: anything
   that re-serialises, decompresses, or normalises a body before caching changes the bytes
   and fails it. Since Amendment 2 moved all body handling into `record.py`, this is the
   half byte identity can guard. **It cannot see a second *scheduling* path** — a spider
   branching on `.json` URLs to schedule differently leaves bytes identical and key sets
   equal (plan-review R8). That half of A7 rests on item 5's prose plus review; no
   instrument below proves it, and claiming otherwise was the defect R8 names.
3. The `content.?type` absence grep on `fetch.py` (below) — a tripwire, not a proof.

All tests bind `ThreadingHTTPServer` on `127.0.0.1:0` (CLAUDE.md rule 19). The handler
counts hits per path so "zero fetches" is directly assertable rather than inferred.

## Error model

| Failure | Exit / behaviour | Message substring |
|---|---|---|
| `--contact` absent | exit 2 | `--contact is required` |
| Seeds file missing | exit 2 | `no such seeds file` |
| Seeds malformed | exit 2, no network call | `expected` or `type: Seeds` |
| Cache root not writable | exit 2 | `cache root is not writable` |
| A single URL fails all retries | crawl continues; entries recorded | — |
| Any non-2xx response | recorded and cached like any other; **never** dropped | — |
| Cache root / manifest parent absent | created on demand; not an error | — |
| Empty seed table | exit 0, zero requests, manifest untouched | — |
| Duplicate seed URL | first row wins; later rows logged at WARNING | `duplicate seed` |
| Manifest schema violation | crash the run | `missing required key` |

**"A single URL fails all retries" and "Manifest schema violation" differ on purpose.** A dead
host is expected and must not stop a multi-host crawl. A manifest schema violation is a bug in
this code, and continuing would write unusable records — fail loudly instead.

## Runbook — add to `fetcher/README.md`

Cover: `uv sync --project fetcher`; the full command with every flag; that `cache/` is
ignored by exactly one `.gitignore` line while `manifest.jsonl` is tracked; that
`<cache-root>/httpcache/` and `<cache-root>/.jobdir/` are disposable — deleting them costs
a refetch at most, and **never** duplicate manifest history, because a cache-served response
writes no entry; and that adding a seed means editing `seeds.md` by hand — no code run,
fetcher need not be running.

## Checks

```
test -f fetcher/evidence_fetch/spiders/fetch.py
test -f fetcher/evidence_fetch/cli.py
grep -qF 'test_two_seeds_produce_three_entries_including_robots' fetcher/tests/test_spider.py
grep -qF 'test_json_and_html_take_the_same_path' fetcher/tests/test_spider.py
grep -qF 'test_cached_bytes_are_byte_identical' fetcher/tests/test_spider.py
grep -qF 'test_rerun_refetches_nothing' fetcher/tests/test_spider.py
grep -qF 'test_interrupted_run_resumes_from_jobdir' fetcher/tests/test_spider.py
grep -qF 'test_jobdir_delete_with_httpcache_writes_no_new_entries' fetcher/tests/test_spider.py
grep -qF 'test_malformed_seeds_exits_2_before_any_request' fetcher/tests/test_spider.py
grep -qF 'test_missing_contact_exits_2' fetcher/tests/test_spider.py
grep -qF 'test_403_then_200_yields_two_entries_and_the_body_is_cached' fetcher/tests/test_spider.py
grep -qF 'test_503_reaches_the_recorder_and_is_cached' fetcher/tests/test_spider.py
grep -qF 'test_redirect_records_full_chain_and_url_final' fetcher/tests/test_spider.py
grep -qF 'test_empty_seed_table_is_a_noop' fetcher/tests/test_spider.py
grep -qF 'test_duplicate_seed_first_row_wins' fetcher/tests/test_spider.py
grep -qF 'test_httpcache_lands_under_the_cache_root' fetcher/tests/test_spider.py
grep -qF -- '--contact is required' fetcher/evidence_fetch/cli.py
grep -qF 'HTTPCACHE_DIR' fetcher/evidence_fetch/cli.py
grep -qF 'HTTPERROR_ALLOW_ALL' fetcher/evidence_fetch/spiders/fetch.py
grep -qF 'async def start' fetcher/evidence_fetch/spiders/fetch.py
! grep -qF 'def start_requests' fetcher/evidence_fetch/spiders/fetch.py
grep -qF 'dont_filter=True' fetcher/evidence_fetch/spiders/fetch.py
! grep -qiE 'content.?type' fetcher/evidence_fetch/spiders/fetch.py
grep -qxF 'cache/' fetcher/README.md
uv run --project fetcher python -m unittest discover -s fetcher/tests -t fetcher -q
```

Notes on these. Every test in "Tests to write" is gated by a name grep (#11). The
`content.?type` grep is stronger than a branch-pattern grep (which the review evaded four
ways) because the spider now has **no reason to name content types at all** — recording
lives in `record.py`; keep even the invariant's own wording out of `fetch.py`.
`grep -qxF 'cache/'` is whole-line, so `httpcache/` no longer satisfies it. `HTTPCACHE_DIR`
in `cli.py` gates the runtime override that keeps the HTTP cache under the cache root
instead of `<cwd>/.scrapy/` — and `test_httpcache_lands_under_the_cache_root` gates the
*behaviour*, because the review showed the grep alone is satisfied by a comment (R9). The
`async def start` / `start_requests` pair pins the 2.17 entry point: the classic method is
dead code that fails silently. And `dont_filter=True` must appear in `fetch.py` because
retries pass it (item 7); its absence means retries are being eaten by the dupefilter (R3).
