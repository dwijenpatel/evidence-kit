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

FAILURE_CLASSES = ("dns-failure", "connection-refused", "timeout", "tls-error",
                   "robots-disallowed", "other")
def failure_class_for(exc_type_name: str, detail: str = "") -> str
def classify_failure(failure_class: str, attempt: int,
                     max_attempts: int = 3) -> Disposition   # attempt is 0-BASED;
                                                             # item 7a compares the
                                                             # result `is Disposition.RETRY`
```

## Provides

```
uv run --project fetcher python -m evidence_fetch \
    --seeds <path to a Seeds document> \
    --cache-root <dir> \
    --manifest <path to manifest.jsonl> \
    --contact <URL or mailto: for the User-Agent> \
    [--jobdir <dir>]        # default: <cache-root>/.jobdir
    [--limit N]             # stop after N 2xx entries RECORDED this run (see the
                            # bullet below); for smoke runs
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
  yield; R5). Once reached, **no new seed requests are scheduled. A retry already
  decided by the callback or errback is not a new request and still runs to its
  classification conclusion** (round-3 T17) — cutting a retry chain short would leave
  `disposition: "retry"` as a URL's last word with no attempt behind it, the
  escalation-by-abandonment rule 18 exists to prevent. The manifest may therefore
  exceed N by the in-flight responses plus the outstanding retry budget of URLs already
  started (at most `max_attempts` further attempts each). **A warm `HTTPCACHE` makes
  `--limit` a no-op for already-cached URLs** (round-3 P1, measured): cache-served
  responses write no entry and never advance the counter, so after a `.jobdir` delete
  every cached seed is walked (at zero wire cost) and only *uncached* seeds are bounded
  by N. Delete `<cache-root>/httpcache/` too if a smoke run must be bounded end-to-end.
- An **empty seed table** (header + alignment row, zero data rows — guard-valid, and
  `read_seeds` returns `[]`) is a no-op: exit 0, zero requests, manifest untouched.
- **Duplicate seed URLs: the first row wins** — it is enqueued and its `signal` becomes
  `seed_signal`; each later duplicate is logged at WARNING with substring `duplicate seed`.

`--contact` is **required**. Starting without it exits 2 with a message containing
`--contact is required`. Rationale: RFC 9309 §2.2.1 makes the product token functional —
an unidentified crawler falls under the most restrictive `*` robots group — and the
`USER_AGENT` in settings carries a literal `{contact}` placeholder that must never reach
the wire.

**Every completed crawl exits 0** (round-3 T18) — including a run whose URLs all ended
`blocked` or `fatal`: the run did its job; `blocked` is a claim about an attempt
sequence, never about the world (task 4), and a nonzero exit would make one dead host
fail a multi-host crawl. Nonzero exits are reserved for the **five** startup failures
(exit 2 — U9 added seed-URL validation to the original four), a manifest schema
violation (exit **1** — see the error model, U10), and an unhandled crash. A subprocess
test may therefore assert `returncode == 0` on any run that reached the reactor **with
no schema violation**. **The pinned command's
`--project fetcher` is RELATIVE and uv resolves it against the process cwd** (round-3
T7, probed: from a foreign cwd it degrades to `Project directory 'fetcher' does not
exist` + `No module named evidence_fetch`) — any test invoking it as a subprocess runs
with **cwd = the repository root**, or passes an absolute `--project` path.

## Behaviour, pinned

1. Read seeds. A `SeedFormatError` exits **2** before any network call. **Then validate
   every seed URL before the crawler is created** (round-4 U9): `urlparse(url)` must
   yield a scheme in `{http, https}` and a non-empty netloc; any failing row exits **2**
   with a message containing `seed url is not fetchable` plus the offending value.
   Task 1 deliberately lets a Seeds row hold a not-yet-fetchable source description, so
   the guard never catches this — and without this gate, `scrapy.Request(bad_url)`
   raises `ValueError` **inside `async def start()`**, which kills the async generator:
   every later seed is silently dropped while the run reports `finish_reason: finished`
   and exits 0 (probed; Scrapy logs one ERROR naming the bad URL, and nothing about the
   seeds it cost). Never start a partial crawl from a malformed queue — this rule is
   why that sentence exists, not just `SeedFormatError`.
2. Load the prior index from the manifest once at start.
3. Enqueue every seed URL **from `async def start()`**. In scrapy 2.17.0 the classic
   `start_requests()` is consulted by **nothing** — it survives only in a docstring, and
   the default `start()` reads `start_urls` alone, so a spider defining only
   `start_requests` crawls zero URLs with no warning (probed: 0 requests, clean
   `finish_reason: finished`). Seed requests carry
   `meta={"attempt_n": 1, "seed_signal": <row's signal>}` **and
   `errback=self.on_error`** (T3 — transport failures reach the spider only through the
   errback). The recorder reads **`request.meta.get("attempt_n", 1)`** and
   **`request.meta.get("seed_signal")`**, and takes them from nowhere else. **The
   default is load-bearing, not defensive** (round-3 T8): Scrapy builds the robots.txt
   request itself with `meta={"dont_obey_robotstxt": True}` and nothing more (probed —
   a recorder at 1000 sees exactly `dont_obey_robotstxt, download_latency,
   download_slot, download_timeout` on it), so the robots entry's `attempt_n: 1` comes
   from the default and its `seed_signal: null` from the absent key. **This does NOT
   mean `meta["attempt_n"]`** — that raises `KeyError` on the first robots response of
   every run, and `attempt_n` is not in task 5's nullable set. Seeds use
   `dont_filter=False`, so Scrapy's fingerprint dedup and the persisted `JOBDIR`
   frontier give A9's resume.
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

   ```python
   ra = parse_retry_after(retry_after_header, now)
   delay_s = ra if ra is not None else backoff_delay(zero_based)
   ```

   seconds — **`is not None`, never `or`** (round-3 T4): task 4 clamps `Retry-After: 0`,
   a past HTTP-date, and `"-5"` to `0.0`, and `0.0 or x` evaluates to `x`, so the `or`
   form silently replaces an honoured "retry now" with a random backoff; `None` is the
   only "use our own backoff" signal. **The delay must actually defer the retry before
   it is handed to the scheduler** (round-3 T5): re-yielding it immediately is wrong
   even though the slot delay masks the difference — probed, with `Retry-After: 120`
   and `DOWNLOAD_DELAY = 5.0` an immediate re-yield produced a 4.999s gap and identical
   entries and counts, so only the gated timing test below can see this. The deferral
   seam is the implementer's call (`contract`); the delay value is not a seam.
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

7a. **Transport failures retry through the errback** (T3). The recorder (task 5) has
   already written the failure line by the time `on_error(failure)` runs — the
   `process_exception` chain re-raises after recording, and the errback fires (probed
   for all four transport classes). The errback's job is the retry decision only:
   `fc = failure_class_for(type(failure.value).__name__, str(failure.value))`;
   on `classify_failure(fc, zero_based) is Disposition.RETRY`, reschedule with the same
   pinned construction — the receiver is **`failure.request`** (probed:
   `failure.request.replace(dont_filter=True, meta={…, "attempt_n": n + 1})` works) —
   after `backoff_delay(zero_based)` seconds; there is no `Retry-After` without a
   response. **The errback's deferral is not test-enforced and is a review obligation**
   (round-4 U14): `backoff_delay` is full jitter — `rand()` is uniform on [0, 1], so
   the delay's lower bound is 0 for every attempt — and the measured scheduling floor
   between consecutive transport failures is ~0.6s at `DOWNLOAD_DELAY = 0` (probed),
   so no wall-clock assertion can distinguish a correctly deferred retry from an
   immediate re-yield without an injectable `rand` this plan does not specify. What
   the gated tests DO catch is a deferral that loses the retry: returning a bare
   `Deferred` from the errback reschedules nothing (probed: 1 attempt instead of 4),
   which the transport-dead test's `attempt_n` 1–4 assertion turns red.
   On `BLOCKED`, do nothing: the line is written, and `blocked` is a claim about this
   attempt sequence, never about the world. Worked example — a dns-dead seed host,
   default `max_attempts=3`: the host's robots fetch fails once (its own failure line),
   then the page attempt cycle runs `attempt_n` 1–4 → manifest gains **five** failure
   lines: 1 robots (`seed_signal: null`) + 4 page (`retry, retry, retry, blocked`), zero
   wire responses, zero artifacts. **This does NOT mean robots is re-fetched per retry**
   — Scrapy caches the failed parser (`None`) for the netloc, so retries proceed
   directly (probed).

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
test_jobdir_delete_with_httpcache_writes_no_new_entries   # (#13): 0 server hits, 0
                                               # lines — a 200-serving fixture BY
                                               # DESIGN; a retryable-status fixture
                                               # appends a fresh sequence instead
                                               # (T10, see the runbook)
test_malformed_seeds_exits_2_before_any_request # server records zero hits
test_missing_contact_exits_2
test_403_then_200_yields_two_entries_and_the_body_is_cached
    # THE composed R2+R3+R4 regression, and the one test that catches all three:
    # asserts TWO wire hits via the handler's counter (under a broken R4 config the
    # retry is answered from the HTTP cache: one wire hit, and the "cached"-flagged
    # response writes NO line per task 5, so the target URL shows ONE entry, not
    # two — measured; round-3 T11 corrected this comment, which previously claimed
    # a cached retry writes a second line), two entries for the target URL
    # (dispositions retry, ok), and the 200 body cached. Red if the callback never
    # sees the 403 (R2), if the dupefilter eats the retry (R3), or if the retry is
    # answered from the HTTP cache (R4).
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
test_httpcache_lands_under_the_cache_root      # R9, corrected by T7: subprocess with
                                               # cwd = the REPO ROOT (the relative
                                               # `--project fetcher` fails from any
                                               # other cwd — probed) and --cache-root
                                               # in a TemporaryDirectory, so cwd is
                                               # not the cache root's parent. Assert
                                               # <cache-root>/httpcache/ exists and
                                               # <repo-root>/.scrapy does not —
                                               # data_path() is scrapy's ONLY producer
                                               # of <cwd>/.scrapy and only
                                               # HTTPCACHE_DIR flows through it, so a
                                               # correct run can never create it.
                                               # Delete a stale .scrapy in setUp: it
                                               # survives an earlier broken run.
test_retry_after_header_defers_the_retry       # T5: the F5 regression, and the only
                                               # instrument that can see it. Serve
                                               # 403 + `Retry-After: 3` then 200,
                                               # DOWNLOAD_DELAY = 1.0; assert the two
                                               # wire hits are >= 3s apart. The header
                                               # must EXCEED the slot delay or the
                                               # test proves nothing (the same
                                               # discriminance rule Amendment 1 fixed
                                               # in the crawl-delay timing test).
test_transport_dead_seed_writes_failure_lines  # T3, fixture pinned by U13: bind
                                               # 127.0.0.1:0, read the port, CLOSE the
                                               # socket, seed that port — bind-then-
                                               # close is the ONLY construction that
                                               # yields connection-refused; a socket
                                               # held bound but never listening times
                                               # out instead -> class "timeout"
                                               # (probed). Assert the MANIFEST, not a
                                               # hit counter — there is no server, so
                                               # "zero wire responses" is vacuously
                                               # true of every implementation: exactly
                                               # 5 failure lines (1 robots,
                                               # seed_signal null, + 4 for the seed,
                                               # attempt_n 1-4, retry x3 then
                                               # blocked, every one http_status null,
                                               # class "connection-refused"), and
                                               # <cache-root>/sha256/ contains zero
                                               # files.
test_non_url_seed_exits_2_before_any_request  # U9: a guard-legal non-URL row ->
                                               # exit 2, message contains
                                               # `seed url is not fetchable`; server
                                               # records zero hits; without the gate
                                               # the start() generator dies and later
                                               # seeds silently vanish (probed)
test_manifest_schema_violation_exits_nonzero   # U10: force the recorder to build an
                                               # invalid entry (e.g. monkeypatched
                                               # REQUIRED_KEYS in a subprocess env or
                                               # a fixture hook); assert exit 1 and
                                               # finish_reason
                                               # manifest-schema-violation
test_robots_disallowed_seed_writes_blocked_line # T3: live server, robots Disallow on
                                               # the seed path; assert one failure
                                               # line, class "robots-disallowed",
                                               # disposition "blocked", attempt_n 1,
                                               # and exactly one attempt (no retry)
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
| A no-response attempt (transport death, robots disallow) | failure line written by the recorder (task 5); transport classes retried via the errback; crawl continues | — |
| Crawl completed — all outcomes, `blocked`/`fatal` included | exit **0** (T18) | — |
| Cache root / manifest parent absent | created on demand; not an error | — |
| Empty seed table | exit 0, zero requests, manifest untouched | — |
| Duplicate seed URL | first row wins; later rows logged at WARNING | `duplicate seed` |
| Non-URL seed row (guard-legal by task 1's design) | exit 2, before the crawler is created — the fifth startup failure (U9) | `seed url is not fetchable` |
| Manifest schema violation | the recorder calls `crawler.engine.close_spider(spider, "manifest-schema-violation")` and re-raises; the CLI reads `crawler.stats.get_value("finish_reason")` after the reactor stops and exits **1** on that reason (round-4 U10). **This does NOT mean raising is enough** — an exception out of `process_response` is caught as that request's download error and the crawl continues to exit 0 (probed); nor is `CloseSpider` enough — from a downloader middleware it is swallowed the same way (probed) | `missing required key` |

**"A single URL fails all retries" and "Manifest schema violation" differ on purpose.** A dead
host is expected and must not stop a multi-host crawl. A manifest schema violation is a bug in
this code, and continuing would write unusable records — fail loudly instead.

## Runbook — add to `fetcher/README.md`

Cover: `uv sync --project fetcher`; the full command with every flag; that `cache/` is
ignored by exactly one `.gitignore` line while `manifest.jsonl` is tracked; that
`<cache-root>/httpcache/` and `<cache-root>/.jobdir/` are disposable — deleting them
costs a refetch at most. **For a URL whose last status was 2xx or 3xx a jobdir delete
appends nothing** (the stored response is served `"cached"` and writes no entry); **for
a URL whose last status was retryable it appends a fresh attempt sequence** (round-3
T10, measured: 4 wire hits and 4 new lines against a 403-forever host), because
`HTTPCACHE_IGNORE_HTTP_CODES` deliberately keeps retryable statuses out of the cache so
backoff reaches the wire. That is correct — a new sequence is new attempts, and rule 15
records attempts — but it is not zero-cost: delete `.jobdir` only when you intend to
re-attempt the failures. A retry interrupted mid-backoff by a forced stop or crash is
lost with its URL left at `disposition: "retry"` (task 5, T14); the remedy is a fresh
jobdir. And: adding a seed means editing `seeds.md` by hand — no code run, fetcher need
not be running.

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
grep -qF 'test_retry_after_header_defers_the_retry' fetcher/tests/test_spider.py
grep -qF 'test_transport_dead_seed_writes_failure_lines' fetcher/tests/test_spider.py
grep -qF 'test_robots_disallowed_seed_writes_blocked_line' fetcher/tests/test_spider.py
grep -qF 'test_non_url_seed_exits_2_before_any_request' fetcher/tests/test_spider.py
grep -qF 'test_manifest_schema_violation_exits_nonzero' fetcher/tests/test_spider.py
grep -qF -- 'seed url is not fetchable' fetcher/evidence_fetch/cli.py
grep -qF -- '--contact is required' fetcher/evidence_fetch/cli.py
grep -qF 'HTTPCACHE_DIR' fetcher/evidence_fetch/cli.py
grep -qF 'HTTPERROR_ALLOW_ALL' fetcher/evidence_fetch/spiders/fetch.py
grep -qF 'async def start' fetcher/evidence_fetch/spiders/fetch.py
! grep -qF 'def start_requests' fetcher/evidence_fetch/spiders/fetch.py
grep -qF 'dont_filter=True' fetcher/evidence_fetch/spiders/fetch.py
grep -qF 'parse_retry_after' fetcher/evidence_fetch/spiders/fetch.py
grep -qF 'errback' fetcher/evidence_fetch/spiders/fetch.py
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
dead code that fails silently. `dont_filter=True` must appear in `fetch.py` because
retries pass it (item 7); its absence means retries are being eaten by the dupefilter
(R3). And `parse_retry_after` / `errback` are the T5/T3 tripwires: an implementation
missing either has re-invented the RetryMiddleware defect (header never read) or made
transport failures invisible to retry.
