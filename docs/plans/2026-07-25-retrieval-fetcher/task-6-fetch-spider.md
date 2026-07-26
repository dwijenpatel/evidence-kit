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

`--contact` is **required**. Starting without it exits 2 with a message containing
`--contact is required`. Rationale: RFC 9309 §2.2.1 makes the product token functional —
an unidentified crawler falls under the most restrictive `*` robots group — and the
`USER_AGENT` in settings carries a literal `{contact}` placeholder that must never reach
the wire.

## Behaviour, pinned

1. Read seeds. A `SeedFormatError` exits **2** before any network call. Never start a
   partial crawl from a malformed queue.
2. Load the prior index from the manifest once at start.
3. Enqueue every seed URL. `dont_filter=False`, so Scrapy's fingerprint dedup and the
   persisted `JOBDIR` frontier give A9's resume.
4. For each response, **regardless of status or content type**: write the body to the
   content-addressed cache, build the manifest entry, append it.
5. `content_type` is recorded and nothing is branched on it. **This is A7.** A JSON body and
   an HTML body traverse identical code; the only difference that ever exists is the value
   in that field.
6. The spider **parses nothing and follows no links in v1.** It fetches exactly what is
   queued. Link-following is PRD §11's automated expansion and is not in this sub-project.
7. On `Disposition.RETRY`, reschedule with a delay of
   `parse_retry_after(...) or backoff_delay(attempt_n - 1)` — honouring the server's own
   number when it gives one.

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
`<html>b</html>` as `text/html`. After one run, `manifest.jsonl` has exactly two lines,
both `"http_status":200`, with `content_type` differing and **every other structural field
present in both**. Both bodies exist under `cache-root/sha256/…`, byte-identical to what
the server sent.

Re-running the same command with the same `--jobdir` and manifest performs **zero** new
fetches and appends **zero** new lines.

## Tests to write

```
test_two_seeds_produce_two_manifest_entries
test_json_and_html_take_the_same_path          # every key but content_type/digest matches
test_cached_bytes_are_byte_identical           # sha256 of file == sha256 of served bytes
test_rerun_refetches_nothing                   # A9
test_interrupted_run_resumes_from_jobdir       # A9
test_malformed_seeds_exits_2_before_any_request # server records zero hits
test_missing_contact_exits_2
test_403_then_200_yields_two_entries_and_the_body_is_cached
test_redirect_records_full_chain_and_url_final
```

`test_json_and_html_take_the_same_path` is the one that actually enforces A7. Assert it
structurally — compare the two entries' key sets for equality and assert the differing
values are confined to `{content_type, raw_bytes_sha256, raw_bytes_length, cache_relpath,
url_requested, url_final, redirect_chain, fetched_at}`. A prose assertion that "they use the
same path" is not a test.

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
| Manifest schema violation | crash the run | `missing required key` |

The last two rows differ on purpose. A dead host is expected and must not stop a multi-host
crawl. A manifest schema violation is a bug in this code, and continuing would write
unusable records — fail loudly instead.

## Runbook — add to `fetcher/README.md`

Cover: `uv sync --project fetcher`; the full command with every flag; that `cache/` is
ignored by exactly one `.gitignore` line while `manifest.jsonl` is tracked; that
`httpcache/` and `.jobdir/` are disposable and deleting them costs only a refetch; and that
adding a seed means editing `seeds.md` by hand — no code run, fetcher need not be running.

## Checks

```
test -f fetcher/evidence_fetch/spiders/fetch.py
test -f fetcher/evidence_fetch/cli.py
grep -qF 'test_json_and_html_take_the_same_path' fetcher/tests/test_spider.py
grep -qF 'test_rerun_refetches_nothing' fetcher/tests/test_spider.py
grep -qF 'test_malformed_seeds_exits_2_before_any_request' fetcher/tests/test_spider.py
grep -qF '--contact is required' fetcher/evidence_fetch/cli.py
! grep -qE 'if .*content_type.*==|if .*\.json\b.*:' fetcher/evidence_fetch/spiders/fetch.py
grep -qF 'cache/' fetcher/README.md
uv run --project fetcher python -m unittest discover -s fetcher/tests -t fetcher -q
```

The negative grep is a blunt instrument and will need judgement if a legitimate use appears
— but branching on content type inside the spider is exactly how A7 gets violated, and a
check that makes the violation visible in review is worth a small false-positive risk.
State in the commit message if it had to be relaxed, and why.
