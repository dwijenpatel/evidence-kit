# Retrieval fetcher — implementation plan

**PRD:** [`~/repos/idea-gen/docs/superpowers/specs/2026-07-25-retrieval-crawler-design.md`](../../../../idea-gen/docs/superpowers/specs/2026-07-25-retrieval-crawler-design.md) (authority, ratified 2026-07-25)
**References:** idea-gen `docs/DECISIONS.md` D15–D21 · idea-gen `docs/research/2026-07-25-{crawler-candidates,wayback-apis,polite-crawling-and-change-detection}.md` · this repo's `AGENTS.md`, `CLAUDE.md`, `method/CONVENTIONS.md`, `method/GRADING.md`

**Goal:** A polite, resumable fetcher that writes byte-exact artifacts and a per-attempt
manifest to a local cache, so that agents read files from disk instead of making network
calls.

**Architecture:** Scrapy is the engine, configured for one connection per host with a
resumable `JOBDIR` frontier and `HTTPCACHE` under `DummyPolicy` for byte-exact storage.
Four small components are written on top, because Scrapy lacks each: a `RobotsTxtMiddleware`
subclass that enforces the `Crawl-delay` Protego already parses and Scrapy discards; a status
escalator that treats 403 as a rate-limit signal; a manifest writer emitting one JSONL entry
per attempt with the fidelity set a later WARC export needs; and a Wayback adapter that
enqueues `id_` capture URLs through the ordinary fetch path. Seeds arrive as a hand-editable
`type: Seeds` document in the corpus — a pipe table read with the same conventions as
`Parameters`.

## Scope — sub-project 1 of 2

The PRD spans two separable subsystems. **This plan is the fetch layer only.**

| In scope (this plan) | Deferred (sub-project 2) |
|---|---|
| A1 `Crawl-delay` enforced · A2 byte-exact cache · A3 per-attempt manifest · A4 403 backoff · A5 fidelity set · A7 one code path for JSON and HTML · A8 Wayback fallback · A9 unattended and resumable · A10 hand-editable seeds | A6 `change_class` computation · A7b table-aware pricing extraction · normalized-content hashing, SimHash, `source_class` comparison rules |

**The seam is the manifest schema**, which this plan pins (task 5). Sub-project 2 consumes
cached bytes plus manifest entries and computes `normalized_content_sha256`, `simhash64`, and
`change_class`. Those fields are **written by sub-project 2, not by the fetcher** — the
fetcher records only what it observed, per CLAUDE.md rule 16.

## Global Constraints

Copied verbatim from the PRD and `CLAUDE.md`; every task implicitly includes them.

- **CLAUDE.md rule 13:** the fetcher is its own `uv` project under `fetcher/`; the repository
  root stays dependency-free. `scaffold.py` and `templates/tests/test_reference.py` must
  still run on a bare machine with no install step.
- **CLAUDE.md rule 14:** the fetcher writes exactly two things — raw bytes into the cache
  directory, and append-only lines to the manifest.
- **CLAUDE.md rule 15:** one manifest entry per attempt, written before interpretation.
- **CLAUDE.md rule 16:** the fetcher does not extract.
- **CLAUDE.md rule 17:** one connection per host; `Crawl-delay` honoured to a 60s ceiling;
  5–10s default where none is declared.
- **CLAUDE.md rule 18:** a 403 is a rate-limit signal on first occurrence.
- **CLAUDE.md rule 19:** `unittest`, and **no network calls in tests** — bind a
  `ThreadingHTTPServer` on `127.0.0.1:0`.
- **CLAUDE.md rule 20:** JSON and HTML share one code path; format handling is downstream,
  keyed on `content_type`.
- **CLAUDE.md rule 3:** no absolute local path, machine-specific location, or private-project
  name in `method/`, `templates/`, `SKILL.md`, or `scaffold.py`. (The `fetcher/` tree is
  likewise kept clean; `docs/plans/` is exempt, as in the parameters plan.)
- **CLAUDE.md rule 7:** a guard check collects every offender, then asserts once.
- **CLAUDE.md rule 8:** assert on message substrings, never whole sentences.
- **PRD §13 non-goals:** not a general-purpose crawler; no JS rendering in v1; no
  credentialed or paywalled access; no CAPTCHA solving; **not an autonomous discovery
  system**; IEEE Xplore out of scope.

## Decision log

| Decision | Rejected alternative | Why | Cost of changing later |
|---|---|---|---|
| Cache at `<corpus>/cache/`, content-addressed, ignored by **one** `.gitignore` line; `manifest.jsonl` **tracked** | Bytes committed; or cache under `mirrors/` | Operator-ratified. The manifest carries every hash, so integrity stays checkable while bytes stay maintainer-local. The lake's existing `mirrors/` ignore list has needed a new pattern every pass and is applied unevenly — 623 tracked files against 295 untracked binaries. One rule, no list. | Low for location. **High for the layout itself** — a one-way door; see next row. |
| Cache path is `cache/sha256/<first-2-hex>/<full-hex>` with no file extension | `cache/<url-slug>/…`; or extension from `content_type` | Content-addressing makes identical fetches dedupe for free and makes the path verifiable from the manifest alone. An extension would encode a guess about content into a path that must stay stable. | **High — one-way door.** Every manifest entry references these paths. |
| `manifest.jsonl`, append-only, one JSON object per line | SQLite; one file per fetch | Append-only survives interruption mid-write (the last line is discarded, nothing else corrupts), diffs in git, and needs no schema migration tooling. SQLite would be better for query but the consumer is agents reading files. | Medium — a converter is straightforward. |
| Seeds are a `type: Seeds` document with one pipe table, in the corpus | JSON/TOML seed file; CLI-only seeding | PRD A10 requires hand-editing with no code run. A pipe table in a corpus doc is hand-editable, matches the `Parameters` precedent exactly, is OKF-conformant, and can be guard-validated with the parsing helpers already in `templates/tests/test_reference.py`. | Low. |
| **Two stores, on purpose**: Scrapy's `HTTPCACHE` (`DummyPolicy`) is a *fetch-avoidance* layer; the content-addressed file the manifest points at is the *durable artifact* | One store — either Scrapy's cache alone, or our own alone | Scrapy's cache is byte-exact (verified) but keyed on request fingerprint, not content, so it cannot dedupe identical bodies or be located from a manifest entry alone. Our store cannot answer "have I fetched this URL before?" across runs. Each does one job. **`HTTPCACHE_DIR` is disposable** — deleting it costs a refetch, never data. | Low. The disposable half can be dropped without touching the durable one. |
| Scrapy 2.17+, `HTTPCACHE_ENABLED` with `DummyPolicy`, `JOBDIR` frontier | Crawlee; katana; httpx + custom queue | D17. Byte-exact caching, fingerprint dedup, and a resumable frontier all verified working. Crawlee throttles on 429 but not 403 and its throttling domain list is exact-match; katana cannot combine `-store-response` with headless. | High — the middlewares are Scrapy-shaped. |
| `RobotsTxtMiddleware` subclass enforcing `Crawl-delay` | `DOWNLOAD_DELAY` set globally; AutoThrottle alone | D17, verified twice: zero files in scrapy 2.17.0 mention `crawl_delay`, `DOWNLOAD_DELAY` defaults to 0, and `RobotsTxtMiddleware` calls only `rp.allowed()`. A global delay is wrong in both directions against hosts declaring 1s (ACM) and 15s (arXiv). | Low — it is one middleware. |
| Manifest carries the fidelity set (request headers, response protocol, response headers, redirect chain) | Store body + hash only | D18. The container format is reversible — a 21-line converter round-trips to WARC byte-exactly — but fidelity not captured at fetch time is not. | **High — one-way door.** Unrecoverable for past fetches. |
| Wayback is a URL adapter enqueuing `<ts>id_/<url>` through the normal path | A separate Wayback ingest path | D19 + PRD §4: `id_` returns byte-exact original bytes with origin headers as `X-Archive-Orig-*`, so a capture is just another GET. A second path would duplicate throttle, cache, and manifest. | Low. |
| `unittest` with a local `ThreadingHTTPServer` | `pytest`; VCR-style cassettes; live-network tests | CLAUDE.md rules 2 and 19. A local server makes `Crawl-delay`, 403-then-200, and redirect chains directly constructible — all three are behaviours we must assert and cannot elicit reliably from a real host. | Low. |
| Python floor 3.12 | 3.9 to match nothing in particular | Scrapy 2.17 supports it; the repo has no other constraint; `uv` manages the interpreter. | Low. |
| Root `tasks.json` becomes this plan's manifest; the parameters plan's 21 checks are **copied** to `docs/plans/2026-07-25-parameters-doc-type/tasks.json` | Append the new tasks to the existing array; or drop the old checks | The runner's contract is one root manifest for the current plan, but those 21 checks were deliberately turned into a regression harness and deleting them would undo that. Copying preserves both. | Low. |
| Manifest field named `cache_relpath`, not the PRD's `mirror_path` | Follow the PRD name exactly | `mirrors/` is an existing directory in the consuming corpus, now frozen by operator decision. A field called `mirror_path` would point readers at the store this one replaces. Recorded because deviating from PRD wording needs a stated reason. | Low. |

## Tasks

| # | id | Tier | Delivers | PRD criteria |
|---|---|---|---|---|
| 1 | `seeds-doc-type` | `code-complete` | `type: Seeds` doc type: template, method edits, guard validation | A10 (format half) |
| 2 | `fetcher-skeleton` | `code-complete` | `fetcher/` uv project, Scrapy settings, cache layout, seed reader | A2, A9, A10 |
| 3 | `crawl-delay-middleware` | `contract` | `RobotsTxtMiddleware` subclass enforcing per-host `Crawl-delay` | A1 |
| 4 | `status-backoff` | `code-complete` | 403/429/503 escalator, `Retry-After` both forms, full jitter | A4 |
| 5 | `manifest-writer` | `contract` | Per-attempt JSONL manifest with the fidelity set | A3, A5 |
| 6 | `fetch-spider` | `contract` | The spider: seeds → queue → cache → manifest, one path for JSON and HTML | A2, A7, A9 |
| 7 | `wayback-adapter` | `code-complete` | `id_` capture URLs through the ordinary fetch path; `as_of` grading rule in `method/` | A8 |

Tasks 3, 5 and 6 are `contract` rather than `code-complete`, for one shared reason: each
attaches to a Scrapy extension point whose exact shape differs across versions and must be
read from the installed source. Their **behaviour** is pinned by worked examples and tables;
their attachment seam is the implementer's call. Prescribing a seam from memory is the
specific failure `contract` exists to prevent — and writing it as if it were certain would
have been worse than admitting it, because a fresh implementer would have transcribed it.

Tasks 1, 2, 4 and 7 are pure functions and documents with no framework coupling, so they
carry their own code.

## PRD coverage

Every in-scope criterion maps to a task, and every task maps back — no orphans.

| PRD | Task(s) | Discharged by |
|---|---|---|
| A1 `Crawl-delay` ≥ declared | 2, 3 | `test_declared_delay_is_applied_to_the_slot` · `test_delay_survives_ten_responses` (F1) · `test_slot_created_after_robots_still_gets_the_delay` (F3) · `test_settings_that_defeat_a1_stay_off` · the capped/absent/never-lowered trio |
| A2 byte-exact cache | 2, 5, 6 | `write_artifact` content-addressing; `test_cached_bytes_are_byte_identical`; `test_gzip_response_caches_wire_bytes` — "raw bytes" = wire octets (F4) |
| A3 one entry per attempt | 5, 6 | `test_503_then_200_produces_two_entries_and_url_not_failed`; `test_503_reaches_the_recorder_and_is_cached` (F2); `test_cached_flag_writes_no_entry` — a cache hit is not an attempt (#13) |
| A4 first 403 backs off | 4 | `test_403_is_retryable_before_exhaustion` / `..._becomes_blocked_only_after_exhaustion` |
| A5 fidelity set present | 3, 5 | `REQUIRED_KEYS` (22, enumerated) + `test_missing_required_key_raises` + `test_robots_info_records_url_digest_and_time` — `fetch_policy` now has a producer (F10) |
| A7 one code path for JSON and HTML | 6 | key-set equality (`test_json_and_html_take_the_same_path`) + byte identity (`test_cached_bytes_are_byte_identical`, the assertion that forbids a second path) + the `content.?type` absence grep (F8) |
| A8 Wayback via the ordinary path | 7 | `test_capture_url_fetches_through_the_ordinary_spider_path` + the no-Wayback-branch grep |
| A9 unattended, interruptible, resumable | 2, 5, 6 | `JOBDIR` + `DummyPolicy`; `test_rerun_refetches_nothing`, `test_interrupted_run_resumes_from_jobdir`, `test_jobdir_delete_with_httpcache_writes_no_new_entries`, `test_foreign_lines_are_skipped_by_the_reader` (#12 — resume survives sub-project 2's lines) |
| A10 hand-editable seeds with provenance | 1, 2 | Guard rejects a blank `signal`; `read_seeds` round-trip |
| **A6, A7b** | — | **Deferred to sub-project 2**, stated in Scope |

Self-review, re-run after amendment 2: `tasks.json` is **generated from the spec `## Checks`
fences** (7 tasks, 91 checks), so spec/manifest drift is now impossible by construction and
verified at zero; every check shell-validated with zero malformed commands; placeholder scan
clean; each `Consumes` block has a matching `Provides`. Every negative check is paired with a
`test -f` or positive gate on the same path in the same task — the ratified draft claimed "4
negative checks paired" when the true count was 1 of 5 (plan-review #26); the claim is now
made true rather than restated. Task 7's shipped code was extracted from the spec and
executed: 12/12 tests pass, including the exact `cdx_query_url` strings and the `EMPTY_SHA1`
base32 self-check.

## Amendment 1 — plan-review blockers F1–F3, 2026-07-25

`/one-punch:plan-review` (full tier) raised 53 candidates; **26 survived adversarial
verification**; 3 were blockers. Report: [`plan-review-report.md`](../../../plan-review-report.md).
The operator directed F1–F3 applied. The remaining 23 findings are **not** addressed here.

Each blocker had the same shape: **it defeated an acceptance criterion while every gating check
stayed green.**

| # | Was | Now | Why it mattered |
|---|---|---|---|
| **F1** | `AUTOTHROTTLE_ENABLED = True`, `RANDOMIZE_DOWNLOAD_DELAY = True` | both `False`; new `CRAWL_DELAY_CEILING = 60.0` replaces the borrowed `AUTOTHROTTLE_MAX_DELAY` | **A1 broken twice from task 2's own pinned constants.** AutoThrottle's `_adjust_delay` ends `slot.delay = new_delay` clamped to a *global* floor of `DOWNLOAD_DELAY`, so a per-host 7.0 is dragged to 5.0 by the **first 200 response** — there is no per-host mindelay, so no configuration rescues it. Separately, `uniform(0.5·delay, 1.5·delay)` floors a declared 7s at **3.5s**. A declared delay is a minimum; jitter below a minimum is a violation. |
| **F2** | Task 6 item 4: "For each response, regardless of status…" | new item 4a pinning `handle_httpstatus_all = True` | Scrapy's `HttpErrorMiddleware` drops every non-2xx **before the callback**. A 503 produced zero manifest entries, a 403 challenge page was never cached, and A4's backoff never fired — **A3, A4, and error-body caching all failed silently.** The setting appears nowhere in the original plan. |
| **F3** | `self._applied.add(netloc)` before the slot lookup | slot looked up first; a netloc is marked applied only once a slot existed | A host whose slot did not yet exist was marked done and its declared delay **never applied**. Every task-3 test asserts on a slot that already exists, so no test could see it. |

**Two consequential edits F1 forced, recorded because they are easy to mistake for scope creep:**

1. **`CRAWL_DELAY_CEILING` is a new setting, not a rename for its own sake.** With AutoThrottle
   off, `AUTOTHROTTLE_MAX_DELAY` is inert — and a middleware reading an inert setting is a trap
   for whoever turns AutoThrottle back on. Task 3 now reads the new name, and a check forbids the
   old one appearing in `crawl_delay.py`.
2. **The end-to-end timing test was non-discriminating and is fixed.** It used `Crawl-delay: 2`
   against `DOWNLOAD_DELAY = 5.0`; the middleware computes `max(5.0, 2.0) = 5.0`, so the ≥2s
   assertion held even if the middleware never ran. It now uses `DOWNLOAD_DELAY = 1.0` against
   `Crawl-delay: 3`. **A regression test that cannot fail is not a regression test.**

**Two regression tests added, each named for the defect it catches:**
`test_delay_survives_ten_responses` (F1 — reads 5.0 after the first 200 under the old settings)
and `test_slot_created_after_robots_still_gets_the_delay` (F3 — stays at 5.0 under the old
ordering). Both are now gated in `tasks.json`, as is
`test_declared_delay_is_applied_to_the_slot`, which the review found was the plan's declared
"highest-value test" and the one name the manifest did not grep.

**Adjacent, done because the edits touched the same lists — F7's check drift is closed.** All
seven spec `## Checks` blocks now match `tasks.json` command-for-command, verified
programmatically. That closed three real defects: the A7-enforcing negative grep existed only in
task 6's spec and **the runner never executed it**; task 6's spec wrote `grep -qF '--contact is
required'` without `--`, which grep parses as a long option and which was therefore red for
every possible implementation; and task 3's spec carried a no-network check that could never fail
(BRE has no `(?!`, and `|| true` forces exit 0), now deleted rather than kept as decoration.

**Also corrected in passing:** task 3's `Consumes` restated `def robot_parser(self, request,
spider)` returning "parser or Deferred". Scrapy 2.17.0 has `async def robot_parser(self,
request)` — no `spider` argument, awaitable.

**Still open — 23 confirmed findings, F4 onward**, including: "raw bytes" undefined for a
compressed response (38 vs 1013 bytes, and it touches the fidelity set D18 calls the one-way
door); two retry mechanisms owning the same status codes, with `Retry-After` never honoured;
nine checks that assert text rather than behaviour; and the A7 test being unsatisfiable as
written. See the report.

## Amendment 2 — the remaining 23 review findings, 2026-07-25

Operator-directed ("take the whole remainder"). F7 was closed inside Amendment 1. Each row
is a defect in the reviewed plan, not a scope change; the architecture, the cache layout,
and the sub-project seam are untouched. Where a row deviates from PRD §7's field table, the
deviation is stated in the row — the PRD text itself is ratified and unedited.

| # | Was | Now |
|---|---|---|
| F4 | recorder placement self-contradictory ("end of the chain … after redirects" names opposite ends); "raw bytes" undefined under compression — 38 wire octets vs 1013 inflated, and the plain-text test server could not tell | recorder pinned at priority **1000** (above compression 590 and cache 900); **raw bytes = wire octets**; `Content-Encoding` survives in `response_headers`; gzip regression test gated; redirect hops are their own recorded attempts |
| F5 | `RetryMiddleware` and the spider both owned retry; `RetryMiddleware` has zero occurrences of `Retry-After`, so the header was never honoured and item 7 was dead code | `RETRY_ENABLED = False`, `RETRY_HTTP_CODES` deleted; **the spider is the only retry mechanism**; `test_scrapy_retry_stays_off` gated |
| F6 | nine checks asserted text, not behaviour — `grep -qF '… = 1'` measured passing on `= 16` | verbatim `test_settings.py` imports and asserts every politeness value; remaining greps anchored whole-line (`^…$`, `-qxF`); negative greps scoped to the package |
| F8 | the A7 test's 8-key allow-list failed a correct spider (`response_headers`, `Date`, `delay_used_s` legitimately differ) and, once widened, admitted a re-serialised body | A7 discharged by three instruments: key-set equality + **byte identity** (the assertion that actually forbids a second path, now gated) + the `content.?type` absence grep |
| F9 | `validators_sent` / `conditional_hit` required for a conditional-GET mechanism no task builds — an unreachable state in the schema sample | both **removed**; conditional GET arrives with `schema: 2`. Deviation from PRD §7, stated |
| F10 | `fetch_policy`'s robots fields had no producer anywhere — Scrapy hands robots bytes to Protego and keeps only the parser | task 3 records `crawler.robots_info[netloc]` at robots-fetch time (the only moment the bytes exist); `delay_used_s` pinned = the slot delay at record time |
| 11 | `classify_status`'s `attempt` base unpinned — 3 vs 4 requests to a 403ing host | pinned **0-based** in task 4's code; `zero_based = attempt_n - 1` computed once, passed to both APIs; 403-forever worked example = 4 attempts, `retry ×3, blocked` |
| 12 | unknown-key raiser unnamed; validation-on-read would break resume the moment sub-project 2 appends its sanctioned lines | `append_entry` validates; `load_prior_index` **skips** valid-JSON lines without `url_requested` (another producer's), raises only on fetcher lines with `schema != 1`; `test_foreign_lines_are_skipped_by_the_reader` gated |
| 13 | an `HTTPCACHE` hit reaches every `process_response`, so deleting `.jobdir/` (runbook-licensed) minted manifest lines for fetches that never happened | recorder skips `"cached"`-flagged responses — a cache hit is not an attempt; `test_jobdir_delete_with_httpcache_writes_no_new_entries` gated |
| 14 | `response_status_line` unobservable — Scrapy drops the reason phrase at the handler boundary, and `HTTPStatus(522)` raises on a code this fetcher retries | replaced by `response_protocol` (`Response.protocol`, nullable); a WARC export reconstructs the phrase only and must say so. Deviation from PRD §7, stated |
| 15 | `HTTPCACHE_DIR = "httpcache"` resolves via `data_path()` to `<cwd>/.scrapy/httpcache` — outside `cache/`, and not the path the runbook told operators to delete | CLI overrides to `<abspath(cache-root)>/httpcache` (absolute paths pass through `data_path` unchanged); settings default documented as fallback-only |
| 16 | task 7 tagged `code-complete` with **22** lines of non-code — below `contract` task 3's 84; `cdx_query_url` had no worked output, `parse_cdx` undefined for `b""` vs `b"[]"` | full `wayback.py` and test file shipped verbatim; **extracted and executed: 12/12 pass**; exact query strings pinned; both empty-body forms return `[]` |
| 17 | task 1's "Exact guard output" showed 2 of the 8 lines `unittest` emits (`longMessage=True`) — an exact-output assert rejected the specified implementation | reworded to a substring contract ("ends with"), with the mechanism stated |
| 18 | `null`-vs-omitted unpinned; with `REQUIRED_KEYS` that is the difference between a written line and a crashed run | every key always present; value-less fields are `null`; the nullable set enumerated |
| 19 | whether validation descends into `fetch_policy` unpinned | exactly its four keys, validated by `append_entry` (the one nested check); `robots_sha256`/`robots_fetched_at` nullable |
| 20 | "most recent" in `load_prior_index` — file order and `fetched_at` order diverge under concurrency and after a git merge | **last matching line in file order**; `fetched_at` never consulted |
| 21 | `--limit` counted nothing in particular; line count non-deterministic at concurrency 8 | counts 2xx recorded this run; stops scheduling; in-flight responses still recorded — may exceed N by up to the concurrency |
| 22 | error model had "not writable" and no row for the normal first run (absent cache root) | created on demand; "not writable" means creation or write failed |
| 23 | empty seed table (guard-valid, `read_seeds → []`) — exit 0 or 2 undefined | a no-op: exit 0, zero requests, manifest untouched; test gated |
| 24 | `distinct_digests` never told whether `EMPTY_SHA1` or non-200 captures count as page-states | split: `distinct_digests` stays a pure global dedupe; **`content_digests`** (status `"200"`, never `EMPTY_SHA1`) is the staleness input; both tested |
| 25 | duplicate seed URLs guard-legal; which row's `signal` survives unpinned | first row wins; later duplicates logged at WARNING `duplicate seed` |
| 26 | self-review claimed "4 negative checks paired with a `test -f`" — the true count was 1 of 5; and the spec/manifest totals coincided at 61=61, hiding per-task drift from any count | every negative check now paired in-task; **`tasks.json` is generated from the spec fences**, so drift is impossible by construction — verified at zero across 91 checks |

Also in this round: task 3's `Consumes` corrected to the installed seam (`async def
robot_parser(self, request)` — no `spider` argument); task 6's item 4 moved body-handling
wholly into the record middleware, so the spider never names content types and the absence
grep replaced the four-ways-evadable branch grep.

## Ratification

- **ratified-by:** *pending*
- **date:** *pending*
- **amended (round 1):** F1–F3, 2026-07-25, pre-ratification
- **amended (round 2):** F4–F26, 2026-07-25, pre-ratification, operator-directed
- **review disposition:** all 26 confirmed findings from `plan-review-report.md` are now
  applied; nothing outstanding

Any edit after ratification voids it.
