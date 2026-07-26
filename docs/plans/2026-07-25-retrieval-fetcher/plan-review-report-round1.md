# plan-review — retrieval fetcher plan, 2026-07-25

**Target:** `docs/plans/2026-07-25-retrieval-fetcher/` (plan.md + 7 task specs) · `tasks.json`
**Authority:** `~/repos/idea-gen/docs/superpowers/specs/2026-07-25-retrieval-crawler-design.md`
**Tier:** full — 3 independent translators · 4 angle finders · 6 grouped adversarial verifiers
**Mode:** report-only. Nothing in the plan was modified.

**Verdict: do not build from this plan as written.** Three findings are blockers — each
independently defeats an acceptance criterion while leaving every gating check green.

> **The cap bit.** 53 candidates were raised; **26 survived adversarial verification**; the
> report caps at 10. Sixteen confirmed findings are listed in
> [Below the cap](#below-the-cap--confirmed-not-reported-in-full) rather than dropped. Nothing
> was truncated silently.

**One environment fact that colours everything below:** there is no `fetcher/` directory. No
check in this plan beyond `grep`/`test -f` on plan prose has ever been executed. Verifiers
installed Scrapy 2.17.0 in a scratchpad to test framework claims; the repo was not touched.

---

## The pattern worth seeing before the list

Three blockers share one cause: **`settings.py` was written `code-complete` — pinned constants
handed to the implementer verbatim — without simulating how those constants interact with
Scrapy's own components.** They are not `contract`-tier judgement calls anyone is expected to get
right. They are wrong values presented as correct ones.

The check-quality findings share a different cause: **greps that assert text exists, treated as
if they asserted behaviour.** Nine admit a wrong implementation, reject a correct one, or both.

---

## F1 — `AUTOTHROTTLE_ENABLED` and `RANDOMIZE_DOWNLOAD_DELAY` defeat A1, twice, from task 2's own settings

**Location:** `task-2-fetcher-skeleton.md` Step 4 (`settings.py`) · interacts with task 3 · **BLOCKER**

A1 requires "A fetch of a host declaring `Crawl-delay: 7` waits ≥7s between requests to that
host." Two pinned constants each break it independently.

- **Reading A (settings as written):** the middleware sets `slot.delay = 7.0`. AutoThrottle's
  `_adjust_delay` runs on **every** response and ends `slot.delay = new_delay`, clamped to
  `mindelay = DOWNLOAD_DELAY = 5.0`. Simulated with the plan's exact settings: after **response
  1**, `slot.delay = 5.0`, and 5.0 for responses 2–10. The `_applied` set guarantees the
  middleware never re-asserts. Separately `RANDOMIZE_DOWNLOAD_DELAY = True` makes
  `Slot.download_delay()` return `uniform(0.5·delay, 1.5·delay)` — measured draws at `delay=7.0`:
  `[9.41, 8.81, 6.44, 5.31, 7.08, 6.33, 8.99, 5.62]`, **floor 3.5s**. A1 fails on the first
  request pair, before AutoThrottle acts at all.
- **Reading B (A1 honoured):** every inter-request gap for that host is ≥7.0s.

**Checked, does not resolve:** task 3's worked-example table pins a single transition
(`5.0 → 7.0`) and says nothing about persistence. Its rationale endorses the one-shot choice:
*"recomputing per request would also re-raise a delay AutoThrottle had deliberately lowered."*
Task 3's end-to-end timing test uses `Crawl-delay: 2` against `DOWNLOAD_DELAY = 5.0`, so it
passes whether or not the middleware does anything — **non-discriminating by construction**.

**Proposed rewrite** — task 2 Step 4:

```python
# AutoThrottle's floor is DOWNLOAD_DELAY and it rewrites slot.delay on every
# response, so a declared Crawl-delay must be a floor re-asserted per response,
# not a one-shot assignment. Otherwise the first 200 drags 7.0 back to 5.0.
AUTOTHROTTLE_ENABLED = False        # re-enable only with a per-host floor (task 3)
RANDOMIZE_DOWNLOAD_DELAY = False    # 0.5x jitter violates "waits >= declared"
```

**This does NOT mean** politeness is weakened: `CONCURRENT_REQUESTS_PER_DOMAIN = 1` and the
per-host `Crawl-delay` floor remain. Randomisation is an anti-fingerprinting measure that
contradicts a *declared minimum*, and A1 is stated as a minimum.

**Pattern break to call out:** task 3 is the plan's declared "single mandatory adaptation." Task
2 ships constants that neutralise it, and neither spec mentions the other.

---

## F2 — Non-2xx responses never reach the recorder: `handle_httpstatus_all` is never set

**Location:** `task-6-fetch-spider.md` "Behaviour, pinned" item 4 · **BLOCKER**

Item 4: "For each response, **regardless of status or content type**: write the body to the
content-addressed cache, build the manifest entry, append it."

- **Reading A (as written, no extra setting):** Scrapy's `HttpErrorMiddleware` drops every non-2xx
  response before the spider callback. A 503 produces **zero** manifest entries; a 403 challenge
  page is never cached. A3 ("a 503-then-200 sequence produces two entries"), A4 ("a first 403
  produces a backoff-and-retry, never a recorded block"), and task 5's "the 503 body is cached and
  hashed like any other response" all fail.
- **Reading B (`handle_httpstatus_all = True`, or the recorder placed below `HttpErrorMiddleware`):**
  two entries, both bodies cached.

**Checked, does not resolve:** `handle_httpstatus_all`, `handle_httpstatus_list`, and
`HttpErrorMiddleware` appear **nowhere** in the plan. Task 5's "Implementation notes" place the
recorder in the downloader chain, which would sidestep this — but item 4 is written as spider
behaviour and the two specs never reconcile.

**Proposed rewrite** — task 6, new item 4a:

> The spider sets `handle_httpstatus_all = True`. Without it Scrapy's `HttpErrorMiddleware` drops
> every non-2xx response before the callback, and a 503 produces zero manifest entries instead of
> the one A3 requires. **This does NOT mean errors are ignored** — `classify_status` still decides
> the disposition; the setting only guarantees the response is *seen*.

---

## F3 — `_applied.add(netloc)` precedes the slot lookup, permanently stranding hosts

**Location:** `task-3-crawl-delay-middleware.md` Step 2 · **BLOCKER**

```python
self._applied.add(netloc)                                  # line 183
if declared is None: return
slot = self.crawler.engine.downloader.slots.get(netloc)    # line 186
if slot is None: return                                    # already marked applied
```

- **Reading A (the sketch):** slot absent at first robots resolution → the host is marked applied
  and `_apply_delay` returns at its guard forever. `slot.delay` stays 5.0 against a declared
  `Crawl-delay: 15`.
- **Reading B (the Error model row):** *"Slot does not exist yet | Return; the next request for
  that host creates it and the delay is applied then."*

**Checked, does not resolve:** plan.md delegates the *seam* ("their attachment seam is the
implementer's call") but task 3's local prose pushes the other way twice — "Sketch, with the
load-bearing parts exact", and a paragraph rationalising the exact ordering that strands the path.
Every task-3 unit test must "assert on `crawler.engine.downloader.slots[<host>].delay`", i.e. a
slot that already exists — so no test can see it.

**Proposed rewrite:** move `self._applied.add(netloc)` to after the successful assignment, so a
host is marked done only once its delay was actually applied.

---

## F4 — "Raw bytes" is undefined for a compressed response; the readings differ by 975 bytes

**Location:** `task-5` schema (`raw_bytes_sha256`, `raw_bytes_length`) · `task-2` `write_artifact` · `task-6` item 4

`COMPRESSION_ENABLED` defaults to `True` and Scrapy sends `Accept-Encoding: gzip, deflate`, so
this is the normal case, not a corner.

- **Reading A (recorder below `HttpCompressionMiddleware`, priority < 590):** measured live —
  cached body **1013 bytes**, `Content-Length` header still **38** (carried over unchanged), and
  `Content-Encoding` **deleted** by the middleware. A WARC export from that entry is a
  reconstruction, which is precisely what D18 says the fidelity set exists to prevent.
- **Reading B (recorder above, priority > 590):** cached body **38 bytes**, wire-faithful,
  `Content-Encoding: gzip` intact.

**Checked, does not resolve:** the one placement instruction is self-contradictory. Task 5 says
the recorder "runs at the **end** of the downloader chain **so it observes the response after
redirects and retries are resolved**" — but `process_response` runs in *descending* priority, and
Redirect is 600 / Retry is 550, so "after redirects and retries" forces priority < 550 → Reading
A, while "end of the downloader chain" in Scrapy's vocabulary means 900+ → Reading B. PRD A2 says
"byte-identical to the source"; "the source" is the ambiguous term. Task 6's local test server
never compresses, so `test_cached_bytes_are_byte_identical` **cannot discriminate**. Note Scrapy's
own `HTTPCACHE` (900) stores the wire gzip — which is what the PRD's "byte-exact (verified)" lab
result actually measured.

**Proposed rewrite** — task 5 "Implementation notes":

> The recorder observes the **wire** response: register it above `HttpCompressionMiddleware`
> (priority > 590). `raw_bytes_sha256` digests the octets as received, so a gzip response caches
> 38 bytes with `Content-Encoding: gzip` intact and `Content-Length: 38` consistent. **This does
> NOT mean the decompressed body is discarded** — decompression is sub-project 2's job, reading
> from the cache. Add a test serving `Content-Encoding: gzip`; the current server cannot see this.

---

## F5 — Two retry mechanisms are enabled for the same codes; `Retry-After` is never honoured

**Location:** `task-2` Step 4 (`RETRY_*`) vs `task-6` "Behaviour, pinned" item 7

- **Reading A (Scrapy's `RetryMiddleware` owns it, per task 2's settings):**
  `RetryMiddleware.process_response` returns a new Request for any status in `RETRY_HTTP_CODES`,
  so the callback never sees a retryable response while retries remain. Verified: the module
  contains **zero occurrences of `Retry-After`**. A 503 carrying `Retry-After: 120` is retried at
  the slot delay (~5s), not 120s. `parse_retry_after` is never called; item 7's `RETRY` branch is
  dead code. **PRD §6's "honor `Retry-After` in both forms" is unmet.**
- **Reading B (the spider owns it):** `Retry-After` honoured — contradicting task 2's verbatim
  settings and the check pinning `RETRY_HTTP_CODES`.

**Checked, does not resolve:** two sentences pin opposite owners — task 6 item 7 (spider) and task
5's "after redirects and retries are resolved" (Scrapy). A grep across all seven specs found no
other statement of retry ownership. Two sentences pinning opposite readings is not a refutation.

**Proposed rewrite** — task 2 Step 4:

```python
# The spider owns retry so it can honour Retry-After, which RetryMiddleware does
# not implement (zero occurrences of "Retry-After" in its source).
RETRY_ENABLED = False
```

and in task 6 item 7, state that `classify_status` + `backoff_delay` are the **only** retry
mechanism. **This does NOT mean fewer retries** — `max_attempts` replaces `RETRY_TIMES`.

---

## F6 — Nine acceptance checks assert that text exists, not that behaviour holds

**Location:** `tasks.json`, all tasks · deduped from 9 verified instances

The sharpest: **`grep -qF 'CONCURRENT_REQUESTS_PER_DOMAIN = 1'` passes on `= 16`, `= 10`, and
`= 100`** — `-F` is an unanchored substring match. It also passes on a commented-out `= 1` above a
live `= 8`. One connection per host is the aggregate-hammering fix from PRD §2, and nothing else
gates it: no test imports `settings.py`.

| Check | Wrong impl PASSES | Correct impl FAILS |
|---|---|---|
| `grep -qF 'CONCURRENT_REQUESTS_PER_DOMAIN = 1'` | `= 16`, `= 100`, comment-above-live | — |
| `grep -qF 'AUTOTHROTTLE_MAX_DELAY = 60.0'` | commented-out above a live `= 3600.0` | `= 60` (identical via `getfloat`) |
| `grep -qE '^RETRY_HTTP_CODES = \[403,'` | `[403, 429]` — drops every 5xx | black-style multi-line literal |
| `grep -qF 'RETRYABLE = frozenset({403,'` | `frozenset({403, 999})` | `frozenset({429, 403, …})`, `frozenset([…])`, PEP-526 annotation |
| `grep -qF 'id_/' wayback.py` | docstring only, `capture_url` returns a replay page | — |
| `grep -qF 'cache/' README.md` | satisfied by `httpcache/`, which the same runbook requires | — |
| `! grep -qE 'if .*content_type.*=='` | `.startswith()`, `match/case`, dict dispatch, `"json" in …` | a comment stating the invariant |
| `! grep -qiE 'wayback\|archive\.org'` | branch in `cli.py`; `"web.archive" + ".org"` | a docstring stating the invariant |
| `! grep -qF 'normalized_content_sha256' manifest.py` | field written in `record.py` — which **this task creates** and which carries zero checks | — |

All verified by execution under both BSD grep and this machine's ugrep shim; they agree.

**Proposed rewrite:** replace value-assertion greps with tests that import and assert
(`from evidence_fetch import settings; assert settings.CONCURRENT_REQUESTS_PER_DOMAIN == 1`), and
scope negative greps to the package (`! grep -rqF 'normalized_content_sha256'
fetcher/evidence_fetch/`) rather than one file. Keep name-greps only where a behavioural test is
also gated.

---

## F7 — Spec `## Checks` blocks and `tasks.json` drift in three tasks; the totals coincide at 61

**Location:** `tasks.json` vs task-3, task-6, task-7 `## Checks`

Per-task composition is **8/9/9** (specs) vs **7/8/11** (manifest) — both summing to 61, which is
why plan.md's self-review ("`tasks.json` parses (7 tasks, 61 checks)") saw nothing. It never
opened the specs.

- **task 6, spec-only:** `! grep -qE 'if .*content_type.*==' …` — the check the spec calls the
  mechanical guard against A7. **The runner never executes it.**
- **task 6:** the spec writes `grep -qF '--contact is required'` without `--`; grep parses it as a
  long option and exits 2. That form is **red for every possible implementation**.
- **task 3, spec-only:** `! grep -rn 'http://\(?!127\.0\.0\.1\)' … || true` — dead three ways (BRE
  has no `(?!`; `|| true` forces 0; ugrep errors to 2, which `!` inverts to 0).
- **task 7, manifest-only:** two checks appearing in no spec.

**Checked, does not resolve:** plan.md names `tasks.json` "this plan's manifest" but never says
the spec blocks are non-normative. The ratified `Parameters` precedent treats any such difference
as a defect to reconcile without saying which side wins.

**Proposed rewrite:** state in plan.md that `tasks.json` is normative and each spec's `## Checks`
block is a copy, and add a check that diffs them per task.

---

## F8 — The A7 test is unsatisfiable, and widening it to pass admits the violation it guards

**Location:** `task-6` "Tests to write" — `test_json_and_html_take_the_same_path`

- **Reading A (allow-set taken literally):** measured against the worked example's own server, the
  two entries differ on `Content-Type`, `Content-Length`, **and `Date`** (5s apart under
  `DOWNLOAD_DELAY = 5.0`). `response_headers` is a required key and is **not** in the 8-key
  allow-set → the test fails a correct, single-code-path spider.
- **Reading B (author widens the set):** a spider doing
  `body = json.dumps(json.loads(body)).encode()` before caching — a second code path and a rule-16
  extraction — moves only `raw_bytes_*` and `cache_relpath`, all already allowed. Test green,
  violation shipped.

**Checked, does not resolve:** the same spec contradicts itself — the test-list comment says
"every key but content_type/digest matches" while the prose four lines later lists eight keys. The
worked example says "every other structural field **present** in both", a key-set claim.

**Proposed rewrite:** assert key-set equality only, and add a *separate* positive test that cached
bytes equal served bytes for both — that is what actually forbids the re-serialization path. Drop
the value-confinement assertion; it cannot be made both sound and complete.

---

## F9 — `validators_sent` and `conditional_hit` are required fields for a mechanism no task builds

**Location:** `task-5` schema

Both occur **exactly once each** in the entire plan — in the schema sample. Zero occurrences
anywhere of `conditional`, `304`, `If-None-Match`, `If-Modified-Since`, or `revalidate`.

- **Reading A (no conditional GET is ever issued):** every entry forever carries
  `"validators_sent": {}` and `"conditional_hit": false`; the sample shows an unreachable state.
  `etag`, `etag_is_weak`, `last_modified` are recorded for a purpose the PRD states ("Enable a
  conditional GET next time") and no task owns.
- **Reading B (implementer builds one):** a 304 has an empty body, task 6 item 4 caches
  "regardless of status", and task 4 classifies 304 as `OK` — so `raw_bytes_sha256` becomes
  `e3b0c442…b855` and `cache_relpath` points at the **empty file** instead of the document.

**Checked, does not resolve:** `load_prior_index` is pinned to return digests, so it structurally
cannot supply a validator. `HTTPCACHE_POLICY = DummyPolicy` forecloses it at framework level:
`_set_conditional_validators` lives only in `RFC2616Policy`.

**Proposed rewrite:** either move the four fields to sub-project 2, or add an explicit task-6 item
building the conditional request plus a rule that a 304 **never** overwrites `cache_relpath`.

---

## F10 — `fetch_policy`'s robots fields have no producer anywhere in the plan

**Location:** `task-5` schema — `fetch_policy`

`fetch_policy`, `robots_url`, `robots_sha256`, `robots_fetched_at`, `delay_used_s` each occur
**exactly once** in the whole plan directory: inside the schema sample. No `Provides`, no
`Consumes`, no test, no implementation note names a producer.

- **Reading A (real values):** the implementer must reach into `RobotsTxtMiddleware`'s private
  parser store (Scrapy hands the body to Protego and keeps only the parser — the bytes are gone)
  or issue a **second** GET for `/robots.txt`, making the per-path hit count 2 and breaking task
  6's "the handler counts hits per path so 'zero fetches' is directly assertable".
- **Reading B (nulls):** `REQUIRED_KEYS` is a flat top-level frozenset, so
  `{"delay_used_s": 5.0, "robots_url": …, "robots_sha256": null, "robots_fetched_at": null}` is
  accepted, every named test passes, and A5's "proof this fetch was polite" is nominal.

**Proposed rewrite:** have the task-3 middleware stash `{url, sha256, fetched_at}` per netloc when
it fetches robots.txt, add it to task 3's `Provides`, and restate it in tasks 5 and 6's
`Consumes`. Also state whether `delay_used_s` is the configured slot delay or the measured gap —
with `RANDOMIZE_DOWNLOAD_DELAY` they never coincide.

---

## Below the cap — confirmed, not reported in full

Verified with divergence pairs; omitted only because the report caps at 10.

| # | Location | Defect |
|---|---|---|
| 11 | task-5 / task-4 | `classify_status`'s `attempt` base is unpinned — 3 vs 4 requests to a 403ing host |
| 12 | task-5 Error model | Which function raises `unknown key`? If `load_prior_index` does, resume breaks in every corpus where sub-project 2 has run (A9) |
| 13 | task-6 / task-2 | A response served from `HTTPCACHE` reaches `process_response` like a network one — delete `.jobdir/` as the runbook licenses and the manifest grows with fetches that never happened |
| 14 | task-5 schema | `response_status_line` — Scrapy drops the reason phrase at the handler boundary, so it must be synthesised, and `HTTPStatus(522)`/`(524)` **raise `ValueError`** on codes this plan retries. (`Response.protocol` *is* available and fixes the HTTP/1.0-vs-1.1 half) |
| 15 | task-2 Step 4 | `HTTPCACHE_DIR = "httpcache"` resolves via `data_path()` to `<cwd>/.scrapy/httpcache` — not under `cache/`, and not the path the runbook tells operators to delete |
| 16 | task-7 | Tagged `code-complete`, ships **22** Python lines — inside the `contract` band, below contract task 3's 84 — and its only fence is not valid Python. `cdx_query_url` has no worked output; `parse_cdx` undefined for `[]` vs `b""` |
| 17 | task-1 Worked example | "Exact guard output" shows 2 of the 8 lines `unittest` actually emits (`longMessage = True`). Reproduced by execution |
| 18 | task-5 | `null`-vs-omitted unpinned for `content_type`, `etag`, `last_modified`; with `REQUIRED_KEYS` that is the difference between a written line and a crashed run |
| 19 | task-5 | Does validation descend into `fetch_policy`? A flat `frozenset[str]` has no path convention |
| 20 | task-5 | "most recent" in `load_prior_index` — file order or `fetched_at` order? They diverge under concurrency and after a git merge |
| 21 | task-6 | `--limit N` — counts what, and are in-flight responses recorded? Under one reading the line count is non-deterministic at `CONCURRENT_REQUESTS = 8` |
| 22 | task-6 | Error model has "cache root not writable" and no row for "absent" — the normal first run |
| 23 | task-6 | Empty seed table (guard-valid, `read_seeds` → `[]`): exit 0 or exit 2? No row, no test |
| 24 | task-7 | `distinct_digests` is never told to exclude `EMPTY_SHA1` or non-200 captures — "two distinct states" vs "never changed" |
| 25 | task-5 | Duplicate seed URLs are guard-legal; `dont_filter=False` collapses them, and which row's `signal` survives is unpinned |
| 26 | plan.md | Self-review claims "4 negative checks paired with a `test -f`" — there are 5 and exactly **1** is paired |

---

## Negative space

**53 candidates → 26 confirmed, 12 refuted with quoted sentences, 15 dropped pre-verification.**
A zero-findings verdict has to show its work; a 26-finding one does too.

### Refuted (12) — the quoted sentence won

| Candidate | Angle | Refuted because |
|---|---|---|
| robots.txt unreachable = fail closed, starving tasks 6/7 tests | seam | *"Allow/disallow behaviour is unchanged — that is the superclass's job and it is correct."* A server not serving `/robots.txt` returns **404**, not "unreachable"; stock Scrapy allows. The premise was wrong |
| Recorder placement over-determined (2 entries vs redirect chain) | seam | plan.md delegates the seam; behaviour is triple-pinned to two entries. The claimed cost was fictional — Scrapy accumulates `redirect_urls` in meta, so a downloader-adjacent recorder keeps the chain |
| `seed_signal` null for Wayback needs forbidden host-detection | seam | *"There is no Wayback code path, no Wayback middleware, and no Wayback branch in the spider"* — unqualified. The null clause is dead text in v1: prose inaccuracy, not a build divergence |
| `capture_url` returns a schemeless URL | convention | The docstring's own words are "Replay URL returning ORIGINAL bytes"; schemeless would be self-falsifying. Local pattern — every fixture, task 5's own example — is on the scheme's side |
| Task 7 is the only spec with no `Consumes` block | convention | **Task 4 has none either.** The convention is that tasks consuming nothing omit it |
| Guard and parser enforce different seeds rules | seam | *"this parser is deliberately forgiving about everything except the shape it must trust"* — and the guard iterates `tracked_markdown()`, so an uncommitted file is out of reach by construction. The split is the design |
| "Seeds malformed" fixture underdetermined | oracle | Same quote; plan.md's coverage row assigns the halves explicitly. Residual looseness in task 6's substring row only |
| `HTTPCACHE_DIR` cannot live under `--cache-root` | seam | `data_path()` returns absolute paths unchanged, and the plan already does runtime-override twice (`{contact}`, `--jobdir`). The dichotomy was false |
| A1 test coverage lets a dead middleware pass | oracle | `test_delay_is_capped_at_max` must assert `900 → 60.0` on a live slot — a positive assertion a dead middleware fails |
| task-3 spec/manifest check drift | convention | Unobservable: that command cannot fail under either reading |
| `--contact` message divergence | oracle | *"Starting without it exits 2 with a message containing `--contact is required`."* Pins it; no second reading |
| Task 5 has no "This does NOT mean" | convention | True absence, but the negative constraints are present in other words. Vehicle for #11, not a finding |

### Dropped pre-verification (15)

Error-model column shapes vary (style) · task 2 has no `## Worked example` heading (values are in
shipped test code) · task 1's `Provides` is prose where others use fences (cosmetic) ·
`_seeds.md.tmpl` sits at `templates/corpus/` not `.../external/` (verified: `render_tree` skips
`_`-prefixed files at any depth — identical behaviour) · the `.gitignore` line is stated but
created by no task (single reading) · `distinct_digests` ordering (pinned by the worked example) ·
`redirect_chain` element 0 (pinned explicitly) · `attempt_n` reset across runs (pinned by "in this
run") · guard offset numbering (pinned by the worked example) · zero-length digest (pinned by a
test) · `parse_retry_after` forms (fully tabulated) · `write_artifact` `.part` collisions
(identical bodies, no observable divergence) · CDX query-parameter order · 1xx classification
(unobservable) · task-2's "→ 7 pass" vs `discover` running 12 (arithmetic, no behavioural fork).

### Verified sound

`split_pipe_row` already unescapes `\|` identically to task 2's `_cells` · `pipe_blocks` and
`_table_lines` agree on the single-table case · all find-and-replace anchors exist uniquely ·
`write_artifact`/`cache_relpath` restatements in tasks 5 and 6 match task 2 exactly · `Disposition`
string values match task 5's `disposition` field ·
`append_entry`/`load_prior_index`/`REQUIRED_KEYS` restatements in task 6 match task 5 · CLAUDE.md
rules 1, 2, 4, 5, 7, 8, 12, 19 clean across all seven specs · `scaffold.py` correctly untouched.

### One stale restatement, not a divergence

Task 3's `Consumes` gives `def robot_parser(self, request, spider)` returning "parser or Deferred".
Scrapy 2.17.0 has **`async def robot_parser(self, request)`** — no `spider` argument, awaitable.
The task does tell the implementer to read the installed version, so it misleads rather than forks.

---

## Recommended disposition

F1, F2 and F3 are blockers: each defeats an acceptance criterion while its checks stay green. F4
and F9 touch the fidelity set, which D18 identifies as the one-way door — cheapest to fix now and
unrecoverable for artifacts already fetched. F6 and F7 should land together, since F7's drift is
what hides F6's weakest instances from the runner.

**Do not implement any task before F1–F3 are resolved.** Everything else can be folded into one
amendment round and re-ratified as a diff read.
