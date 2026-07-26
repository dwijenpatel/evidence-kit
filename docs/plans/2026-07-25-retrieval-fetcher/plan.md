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
| *(Amendment 3)* Retryable statuses stay out of Scrapy's HTTP cache via `HTTPCACHE_IGNORE_HTTP_CODES` = the `RETRYABLE` set | `meta={"dont_cache": True}` on retry requests only | The cache must never answer a retry with a stored error (R4 — probed: 4 callbacks, one wire hit). The settings route covers every requester once, keeps successful retries cacheable, and cannot be forgotten by a future request constructor; the meta route must be remembered at each one. `test_httpcache_ignores_exactly_the_retryable_set` pins the list to `backoff.RETRYABLE`. | Low. |
| *(Amendment 3)* A robots.txt fetch is a recorded attempt — rule 15 applies to it | A recorder rule excluding robots fetches | Rule 15 reads that way ("one manifest entry per attempt, written before interpretation"); A5 gains a real artifact for the robots bytes; and the exclusion would be a second special case stated nowhere the PRD licenses. Costs: every per-host line count gains one, and `--limit` counts only seed-originated 2xx (R5). | Low — one skip rule if reversed, before any manifest exists. |
| *(Amendment 4, operator-decided)* **A no-response attempt writes a failure line**: the response unit null as a block, a `failure: {class, detail}` object, disposition from `classify_failure`; six pinned classes; recorder gains `process_exception` | Zero lines (a dead host indistinguishable from never-seeded); or a sentinel status | The method requires absence claims to cite a sample and date — the failure line is that warrant; the PRD's founding incident (a timed-out CDX query) is literally a no-response attempt; and `robots-disallowed` is the otherwise-missing producer for PRD §6's second `blocked` ground. A sentinel status is fake fidelity, rejected for the same reason `response_status_line` was. Schema is 23 keys, amended pre-ship, so no migration. | Medium — the XOR and null-unit rules ride the one-way-door schema; dropping the feature later means dead nullable rules, not data loss. |
| *(Amendment 4)* Robots access **fails open** on an unreadable/unreachable robots.txt — a stated deviation from PRD §6's "fail closed" | Fail closed (block every URL on that host until robots is readable) | The superclass already fails open (probed: empty/garbage/binary robots all allow); failing closed converts a one-window transport error into a recorded inability to fetch — the false-absence shape again. The delay never falls below `DEFAULT_DELAY`, parsed disallow rules are always honoured, and `robots_info` nulls record "we asked" (T21). | Low — one override in the subclass if reversed. |

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
| A1 `Crawl-delay` ≥ declared | 2, 3 | `test_declared_delay_is_applied_to_the_slot` · `test_delay_survives_ten_responses` (F1) · `test_slot_created_after_robots_still_gets_the_delay` (F3) · `test_slot_key_is_hostname_not_netloc` (R1) · `test_settings_that_defeat_a1_stay_off` · the capped/absent/never-lowered trio |
| A2 byte-exact cache | 2, 5, 6 | `write_artifact` content-addressing; `test_cached_bytes_are_byte_identical`; `test_gzip_response_caches_wire_bytes` — "raw bytes" = wire octets (F4) |
| A3 one entry per attempt | 5, 6 | `test_503_then_200_produces_two_entries_and_url_not_failed`; `test_503_reaches_the_recorder_and_is_cached` (the recorder half — it sits upstream of the spider drop, R2); `test_cached_flag_writes_no_entry` — a cache hit is not an attempt (#13) — + **failure lines for no-response attempts** (T3): `test_transport_dead_seed_writes_failure_lines`, `test_failure_line_roundtrips` |
| A4 first 403 backs off | 4, 6 | `test_403_is_retryable_before_exhaustion` / `..._becomes_blocked_only_after_exhaustion` + `test_403_then_200_yields_two_entries_and_the_body_is_cached` — the composed e2e proving the retry reaches the callback (R2), survives the dupefilter (R3), and hits the wire, not the cache (R4) — + `test_retry_after_header_defers_the_retry` (T5: the only instrument that can see the header being honoured) + `classify_failure` retrying transport deaths (T3) |
| A5 fidelity set present | 3, 5 | `REQUIRED_KEYS` (23, enumerated) + `test_missing_required_key_raises` + `test_robots_info_records_url_digest_and_time` — `fetch_policy` now has a producer (F10) — + the robots.txt attempt recorded as its own artifact, with the netloc-synthesized fallback for the two robots_info-less moments (R5, R6). Header names are Scrapy-normalized Title-Case, values byte-preserved; a WARC export reconstructs casing and says so (T15) |
| A7 one code path for JSON and HTML | 6 | key-set equality (`test_json_and_html_take_the_same_path`) + byte identity (`test_cached_bytes_are_byte_identical` — forbids a second *recording* path; the scheduling half rests on item 5's prose plus review, R8) + the `content.?type` absence grep (F8) |
| A8 Wayback via the ordinary path | 7 | `test_capture_url_fetches_through_the_ordinary_spider_path` + the no-Wayback-branch grep |
| A9 unattended, interruptible, resumable | 2, 5, 6 | `JOBDIR` + `DummyPolicy`; `test_rerun_refetches_nothing`, `test_interrupted_run_resumes_from_jobdir`, `test_jobdir_delete_with_httpcache_writes_no_new_entries`, `test_foreign_lines_are_skipped_by_the_reader` (#12 — resume survives sub-project 2's lines) |
| A10 hand-editable seeds with provenance | 1, 2 | Guard rejects a blank `signal`; `read_seeds` round-trip |
| **A6, A7b** | — | **Deferred to sub-project 2**, stated in Scope |

Self-review, re-run after amendment 4 — every item below is an execution, not a count
read off the prose: `tasks.json` is **generated from the spec `## Checks` fences** (7
tasks, 137 checks), so spec/manifest drift is impossible by construction and re-verified
at zero; every check shell-validated (`bash -n`), zero malformed; all 10 negative checks
swept programmatically for a positive gate on the same path in the same task — 10 of 10
paired. **Every test named in spec prose is gated by a name grep** (#11); fence-shipped
tests are enforced by transcription plus the suite run instead. The amended task-2 and
task-4 fences were extracted and executed: **24/24 pass**. Task 7's shipped code was
executed at authoring: 12/12 unit tests; its 13th test is e2e and build-time by design.
Every framework claim in Amendments 3–4 carries a probe row (the two ledgers below) or a
citation into the round-3 report's independently-verified transcripts; the one ledger
row round 3 falsified is corrected in place and says so.

## Amendment 1 — plan-review blockers F1–F3, 2026-07-25

`/one-punch:plan-review` (full tier) raised 53 candidates; **26 survived adversarial
verification**; 3 were blockers. Report: [`plan-review-report-round1.md`](plan-review-report-round1.md) (archived here when the lean re-review claimed the repo-root filename).
The operator directed F1–F3 applied. The remaining 23 findings are **not** addressed here.

Each blocker had the same shape: **it defeated an acceptance criterion while every gating check
stayed green.**

| # | Was | Now | Why it mattered |
|---|---|---|---|
| **F1** | `AUTOTHROTTLE_ENABLED = True`, `RANDOMIZE_DOWNLOAD_DELAY = True` | both `False`; new `CRAWL_DELAY_CEILING = 60.0` replaces the borrowed `AUTOTHROTTLE_MAX_DELAY` | **A1 broken twice from task 2's own pinned constants.** AutoThrottle's `_adjust_delay` ends `slot.delay = new_delay` clamped to a *global* floor of `DOWNLOAD_DELAY`, so a per-host 7.0 is dragged to 5.0 by the **first 200 response** — there is no per-host mindelay, so no configuration rescues it. Separately, `uniform(0.5·delay, 1.5·delay)` floors a declared 7s at **3.5s**. A declared delay is a minimum; jitter below a minimum is a violation. |
| **F2** | Task 6 item 4: "For each response, regardless of status…" | new item 4a pinning `handle_httpstatus_all = True` — **which was itself inert**: that name is read from `request.meta` or the `HTTPERROR_ALLOW_ALL` setting, never as a spider attribute. Corrected by Amendment 3 R2 (`custom_settings = {"HTTPERROR_ALLOW_ALL": True}`, probed live) | Scrapy's `HttpErrorMiddleware` drops every non-2xx **before the callback**. A 503 produced zero manifest entries, a 403 challenge page was never cached, and A4's backoff never fired — **A3, A4, and error-body caching all failed silently.** The setting appears nowhere in the original plan. |
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
| F8 | the A7 test's 8-key allow-list failed a correct spider (`response_headers`, `Date`, `delay_used_s` legitimately differ) and, once widened, admitted a re-serialised body | A7 discharged by three instruments: key-set equality + **byte identity** (now gated) + the `content.?type` absence grep. *This row originally claimed byte identity "actually forbids a second path" — false once this same amendment moved body handling into `record.py`: it forbids a second **recording** path only; the scheduling half rests on item-5 prose plus review (corrected by R8)* |
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
| 23 | empty seed table (guard-valid, `read_seeds → []`) — exit 0 or 2 undefined | a no-op: exit 0, zero requests, manifest untouched; test gated *(the "gated" claim was ahead of the manifest — false until Amendment 3 gated it and every other prose-named test, #11)* |
| 24 | `distinct_digests` never told whether `EMPTY_SHA1` or non-200 captures count as page-states | split: `distinct_digests` stays a pure global dedupe; **`content_digests`** (status `"200"`, never `EMPTY_SHA1`) is the staleness input; both tested |
| 25 | duplicate seed URLs guard-legal; which row's `signal` survives unpinned | first row wins; later duplicates logged at WARNING `duplicate seed` |
| 26 | self-review claimed "4 negative checks paired with a `test -f`" — the true count was 1 of 5; and the spec/manifest totals coincided at 61=61, hiding per-task drift from any count | every negative check now paired in-task; **`tasks.json` is generated from the spec fences**, so drift is impossible by construction — verified at zero across 91 checks |

Also in this round: task 3's `Consumes` corrected to the installed seam (`async def
robot_parser(self, request)` — no `spider` argument); task 6's item 4 moved body-handling
wholly into the record middleware, so the spider never names content types and the absence
grep replaced the four-ways-evadable branch grep.

## Amendment 3 — the lean re-review's 15 findings, 2026-07-26

Operator-directed ("fix the whole set"). The lean re-review confirmed 13 findings (R1–R10
plus #11–#13), one incidental (#14) and one plausible (#15) — **nearly all in Amendment
1–2 prose**, and every blocker an unexecuted claim about Scrapy. Report archived at
[`plan-review-report-round2.md`](plan-review-report-round2.md). All 15 are applied here,
plus one **new** finding (N1) surfaced by this round's own probes. Every Scrapy claim in
this amendment carries a row in the probe ledger below, per the amended tech-plan
discipline: a fix is a substrate claim, exactly as likely to be wrong as what it replaced
— round 2 measured that on Amendments 1–2, and this round caught the review's own
proposed R6 rewrite mis-synthesizing the robots URL (hostname, dropping the port the
middleware keeps).

| # | Was | Now |
|---|---|---|
| **R1** | slot dict read by `slots[netloc]` in tasks 3 and 5 — `None`/`KeyError` on every rule-19 `127.0.0.1:<port>` server | every slot lookup goes through `downloader.get_slot_key(request)` (hostname, port stripped; meta override honoured — probed live and at source); the two-dicts/two-key-functions table pinned in task 3, restated in task 5; `test_slot_key_is_hostname_not_netloc` gated |
| **R2** | Amendment 1's fix pinned `handle_httpstatus_all` as a spider **attribute** — read by nothing (probed: 403 served, callback never fired); its regression test blind since the recorder moved upstream | item 4a pins `custom_settings = {"HTTPERROR_ALLOW_ALL": True}` (probed live: callback fires on 403); the 503 test re-annotated as A3's recorder half; the callback half moved to the gated 403-then-200 e2e |
| **R3** | `dont_filter` pinned `False` once, globally read — the dupefilter ate every spider retry (probed: one wire hit, forever) | retry construction pinned verbatim: `response.request.replace(dont_filter=True, meta={…, "attempt_n": n+1})`, with the seeds-stay-filtered negative example |
| **R4** | `DummyPolicy` cached every status; retries were answered from disk, flagged `"cached"`, skipped by the recorder (probed: 4 callbacks, one wire hit) | `HTTPCACHE_IGNORE_HTTP_CODES` = the `RETRYABLE` set in task 2 (probed live: two wire hits, `[403 wire, 200 wire]`); equality with `backoff.RETRYABLE` gated by a task-4 test; decision-log row added |
| **R5** | robots.txt fetches traverse the recorder (probed: 3 responses for 2 seeds) but item 4's exclusion list and every line count assumed they vanish | decided and pinned: **a robots fetch is a recorded attempt** (decision-log row); worked examples say three lines, robots first, `seed_signal: null`; `--limit` counts seed-originated 2xx only; rerun still appends zero lines (dupefiltered seeds never reach the robots middleware) |
| **R6** | two reachable moments with no `robots_info` entry — the robots response's own recording (recorder at 1000 runs before the middleware at 100 stores it) and a transport-dead robots fetch — forced a crash, a forbidden null, or an unpinned synthesis | fallback pinned in task 5: `<scheme>://<netloc>/robots.txt` + two nulls — **netloc, port kept**, matching the middleware's own construction (the review's proposed hostname synthesis was wrong; probed at source); task 3's 6a extended to record on the error path; `test_robots_fallback_synthesizes_url_with_netloc` and `test_robots_transport_failure_records_url_with_nulls` gated |
| **R7** | `^CONCURRENT_REQUESTS_PER_DOMAIN = 1$` exits 1 against the spec's own line — trailing comment breaks the anchor (reproduced) | comment moved above the assignment in the fence, with the reason stated inline; check unchanged; red/green demonstrated |
| **R8** | task 6 and row F8 claimed byte identity "actually forbids a second code path" — false since body handling moved to `record.py`; a scheduling branch passes all three instruments | overclaim corrected in task 6, the coverage table, and F8's row: byte identity guards the *recording* half; the scheduling half rests on item-5 prose plus review, stated honestly |
| **R9** | #15's cache-root fix gated only by `grep -qF 'HTTPCACHE_DIR' cli.py` — satisfied by a comment; no test binds the effective location | `test_httpcache_lands_under_the_cache_root` (CLI as subprocess, cwd elsewhere; asserts `<cache-root>/httpcache/` exists and `<cwd>/.scrapy` does not), gated; the grep stays as a tripwire |
| **R10** | task 7's e2e consumed the CLI without restating it, and an in-process invocation would ship the literal `{contact}` unnoticed | task 7 gains a `Consumes` block restating the CLI; invocation pinned as a subprocess with `--contact "mailto:test@example.invalid"`; third assertion added: `useragent_sent` contains the contact value |
| 11 | row 23 claimed a test "gated" that no check named; five more prose-listed tests ungated, two cited in the coverage table | **every prose-named test is gated by a name grep** — the rule, stated per task; 121 checks after regeneration (was 91); row 23 annotated rather than silently rewritten |
| 12 | a redirect hop as "its own attempt" fed `attempt_n: 2` into `classify_status` — redirects silently ate retry budget, contradicting the schema sample beside the rule | pinned: a hop is its own **entry**, never its own attempt; `attempt_n` travels in meta, `RedirectMiddleware`'s `replace(...)` inherits it (probed at source), only a RETRY reschedule increments |
| 13 | "every negative check is paired" — false at 1 of 9 (task 2's root-isolation grep had no positive gate) | `test -f scaffold.py` + `test -d templates/` added; the pairing sweep re-run programmatically: 10 of 10 |
| 14 | schema sample's `url_final` was not an element of its own one-element `redirect_chain` | sample is now explicitly the post-redirect entry of a one-hop redirect: chain `[requested, final]`, `url_final` = last element, hop entry noted as its own preceding line |
| 15 | `attempt_n` "in this run" undefined across a `JOBDIR` resume | pinned: the count survives a resume — the frontier serialises `request.meta` (probed: disk queues persist via `Request.to_dict`); "in this run" replaced with "within one frontier lineage" |
| **N1** | *(new — caught by this round's probes, not by the review)* task 6 said "enqueue every seed URL" without naming the entry point; in scrapy 2.17.0 `start_requests()` is consulted by **nothing** — a spider defining only it crawls zero URLs with no warning | item 3 pins `async def start()`; checks require `async def start` and forbid `def start_requests`; seed meta (`attempt_n`, `seed_signal`) pinned in the same sentence — it was the recorder's undocumented input |

### Probe ledger — scrapy 2.17.0, Python 3.14.6, probed 2026-07-26

Per the amended tech-plan skill: every substrate claim this amendment relies on, with how
it was measured. Source reads are against the installed package; live probes ran a real
crawl against a `127.0.0.1:<port>` `ThreadingHTTPServer`. These rows are true of 2.17.0
at this date; a Scrapy bump invalidates the ledger, not just the code.

| Claim | Probe | Result |
|---|---|---|
| Slot key = `meta["download_slot"]` or `urlparse_cached(request).hostname or ""` — port stripped | source: `core/downloader/__init__.py:166-175`; live: recorder logged keys | live on `127.0.0.1:62283`: `slot_key "127.0.0.1"`, `slots_has_netloc false`, `slots_has_slot_key true` — all three responses |
| The slot exists at record time (GC cannot reap it mid-response) | source: `_slot_gc` reaps only `not slot.active` idle slots (`:272`) | *Result corrected by round-3 T16:* slot present, but `request in slot.active` is **False** at record time (`_enqueue_request`'s `finally` removes it before `process_response` runs; probed) — survival is via `lastseen + delay` and the 60s GC loop, **not** the active set. This row's original Result ("response traverses its slot's active set") was false as measured |
| Spider attribute `handle_httpstatus_all` is read by nothing; meta / `HTTPERROR_ALLOW_ALL` / attr `handle_httpstatus_list` are the three inputs | source: `spidermiddlewares/httperror.py:57-74`; live crawl, broken config | broken: 1 wire hit, **0 callbacks**; fixed (`custom_settings HTTPERROR_ALLOW_ALL`): callback fired on the 403 |
| A `dont_filter=False` re-request of a seen URL is dropped by the dupefilter; `replace(dont_filter=True)` passes | live crawl (fixed config reaches attempt 2) | fixed: retry left the scheduler and hit the wire |
| `DummyPolicy.should_cache_response` honours `HTTPCACHE_IGNORE_HTTP_CODES`; without it a stored 403 answers every retry | source: `extensions/httpcache.py:35-51`; live, both configs | r4only: `[403 wire, 403 cached, 403 cached, 403 cached]`, **one** wire hit · fixed: `[403 wire, 200 wire]`, **two** wire hits |
| The robots fetch traverses the full downloader chain; a recorder at 1000 sees it, before `_parse_robots` runs | source: `robotstxt.py:100-101` (`download_async` → then parse); live | live: 2 seeds, **3** recorded responses, `/robots.txt` first |
| Scrapy builds the robots URL with **netloc** (port kept) | source: `robotstxt.py:90` — `f"{url.scheme}://{url.netloc}/robots.txt"` | confirmed — the review's hostname-based rewrite proposal was wrong |
| Redirect requests inherit `meta` (so `attempt_n`/`seed_signal` survive hops) | source: `redirect.py:126` `source_request.replace(url=…)` + `Request.replace` copying all attributes | confirmed |
| `JOBDIR` disk queues persist `request.meta` | source: `squeues.py:89` → `Request.to_dict` (meta among attributes) | confirmed |
| `start_requests()` is dead code; default `start()` reads `start_urls` only | source: grep — the name appears **only in a docstring**; live: spider defining only `start_requests` | live: 0 requests, `finish_reason: finished`, no warning (N1) |
| Robots transport failure yields `parser = None` → requests allowed, no response recorded anywhere | source: `robotstxt.py:110,130-137` (`_robots_error` sets `_parsers[netloc] = None`) | confirmed — R6's second moment |

Validation after applying: 121 checks regenerated from fences (drift zero by
construction), `bash -n` clean on all 121, negative-check pairing 10/10 by script, R7 and
the two new anchored greps demonstrated red against their named defect and green against
the shipped line, and the composed R2+R3+R4 config demonstrated live: broken → 1 wire
hit / 0 callbacks; fixed → 2 wire hits, `retry` then `ok`.

## Amendment 4 — round 3's 22 findings plus the T3 decision, 2026-07-26

Operator-directed ("let's tackle all of amendment 4 now"). The round-3 lean re-review —
the substrate-truth finder's first firing — confirmed 21 findings (T1–T21) plus one
plausible (P1); report archived at
[`plan-review-report-round3.md`](plan-review-report-round3.md). All are applied, and T3
was resolved by an **operator decision**: a no-response attempt writes a *failure line*
(see the decision log). Two of round 3's blockers had survived every previous round
inside "load-bearing parts exact" code — the class the divergence instruments cannot
see and only execution can.

| # | Was | Now |
|---|---|---|
| **T1** | task 3's exact sketch line called `parser.crawl_delay(…)` — the seam yields Scrapy's `ProtegoRobotParser` wrapper (surface: `allowed`, `rp`), so the line raises `AttributeError`, swallowed by the task's own error model: A1 dead at runtime with one WARNING | Consumes pins the wrapper; the call is `parser.rp.crawl_delay(…)` (probed: 7.0) with the swallowed-AttributeError negative example inline; `rp.crawl_delay` gated by a grep |
| **T2** | all ten unit tests prescribed against `get_crawler()`, whose `.engine` is `None` — the pinned assertion raises before touching a slot | harness replaced: build `Downloader(crawler)` and inject it (probed: 5.0→7.0 through the pinned expression); the two traffic tests run a real crawl and assert from inside a callback |
| **T3** | a transport-dead or robots-disallowed attempt produced **zero** manifest lines — unpinned, schema inexpressible, `BLOCKED`-by-robots had no producer | **operator-decided**: failure lines. Schema is **23 keys** (`failure` added); response unit null as a block, XOR validated; taxonomy + `failure_class_for` + `classify_failure` shipped in task 4 (probed exception names); recorder gains `process_exception`; spider gains the errback branch; worked example: dns-dead seed → 5 failure lines |
| **T4** | item 7's `parse_retry_after(…) or backoff_delay(…)` — `0.0 or x` evaluates `x`, so `Retry-After: 0`, past dates, and `"-5"` were silently replaced by random backoff (3 of task 4's 7 worked rows dead at the only call site) | `ra if ra is not None else backoff_delay(zero_based)`, pinned with the falsy-zero negative example |
| **T5** | no mechanism and no instrument for the retry delay — an implementation never reading `Retry-After` was green on all 121 checks (probed: gap tracks the slot delay, never the header) | deferral obligation pinned; `test_retry_after_header_defers_the_retry` gated (header 3s > slot 1s, the discriminance rule); `parse_retry_after` tripwire grep on `fetch.py` |
| **T6** | Amendment 3's sketch memoized `_applied` on the slot key — two rule-19 servers share `"127.0.0.1"`, so the second host's `Crawl-delay: 15` was parsed and silently never applied (probed: 7.0) | memo keyed by **netloc**, lookup by `get_slot_key` — pinned as deliberately different keys; `test_second_port_on_one_hostname_still_applies_its_delay` gated |
| **T7** | the pinned subprocess command's `--project fetcher` is cwd-relative — red from any foreign cwd (probed: `No module named evidence_fetch`), and R9's test description said "cwd elsewhere" | subprocess invocations pinned to cwd = repo root; R9's test asserts `<repo-root>/.scrapy` absent (`data_path` is scrapy's only producer of it — probed); task 7's Consumes carries the same warning |
| **T8** | "learns both values from meta, nowhere else" ∧ robots entry `attempt_n: 1` ∧ never-null — jointly unsatisfiable (the robots request's meta is one key, probed) | recorder reads `meta.get("attempt_n", 1)` / `meta.get("seed_signal")` — the default pinned as load-bearing, with the KeyError negative example |
| **T9** | Amendment 3's 6a synthesized `f"{scheme}://…"` inside `_robots_error`, which receives no scheme (probed: `NameError`); the paired test hardcoded `http://` | scheme stashed per netloc in `robot_parser` (the last frame holding the request); test now seeds an **https** URL to a closed port so only the stash can produce `https://` |
| **T10** | runbook: deleting `.jobdir` "never duplicates manifest history" — falsified by Amendment 3's own R4 fix (probed: 4 fresh wire hits, 4 new lines on a 403-forever host) | claim scoped: 2xx/3xx-final URLs append nothing; retryable-final URLs get a fresh attempt sequence by design; jobdir-delete test fixture pinned 200-serving |
| T11 | the 403-then-200 annotation claimed a cache-served retry "writes a second line" — task 5's skip rule means it writes none (measured: ONE line) | annotation corrected; the wire-hit assertion stays, with the true rationale |
| T12 | `test_slot_key_is_hostname_not_netloc` as described asserted only downloader facts — probed green over the exact defect it names | the discriminating `delay == 7.0` assertion pinned into the test, with the cannot-fail warning |
| T13 | a line with `url_requested` but no `schema` was unclassified — one reading crashes resume on sub-project 2's lines | fetcher line ⇔ **both** keys present; anything else skipped; the seam obligation on sub-project 2 stated |
| T14 | "resumes as 2" claimed unconditionally — a forced stop or crash during the backoff wait loses the retry and the URL is never refetched (probed) | scoped truthfully: frontier-queued retries survive; one Ctrl-C is safe; a second, or a crash, strands the URL at `retry` — remedy documented (fresh jobdir) |
| T15 | "headers preserve original casing" — impossible; `Headers.normkey` is `key.title()`, below every middleware (probed: `ETag` → `Etag`) | Title-Case normalization pinned; values byte-preserved; WARC casing labeled a reconstruction |
| T16 | task 5 and the Amendment-3 probe ledger justified slot survival via the active set — the request leaves `slot.active` before `process_response` runs (probed) | justification corrected in both places; survival is `lastseen + delay` + the 60s GC loop; the ledger row now records its own correction |
| T17 | `--limit` vs a pending retry unpinned — one reading leaves `retry` as a URL's last word with no attempt behind it | retries run to their classification conclusion; the overshoot bound restated |
| T18 | exit code of a completed crawl pinned nowhere; subprocess tests had to guess | **every completed crawl exits 0**, blocked/fatal included; nonzero = startup failures (2) or a crash |
| T19 | three unanchored absence greps forbid tokens the plan's own house style writes into comments; the even-in-comments rule was stated only for `content.?type` and Wayback | the rule extended explicitly at both sites (task 5's field block, task 3's checks note); `def start_requests` stands as refuted — a definition form, not a name |
| T20 | task 2 shipped `REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"` (zero occurrences in scrapy 2.17.0 — removed, unread, unwarned) and an inert `FEED_EXPORT_ENCODING`, under "every value here is a constraint" | both deleted; a comment records why each is deliberately absent |
| T21 | error-model row 1 ("never treat an unreadable robots.txt as 'no rules'") was false of what will be built and an unstated PRD §6 deviation | row rewritten: delay falls back, access **fails open** — a stated deviation, with the rationale; decision-log row added |
| P1 | `--limit` gloss "stop after N successful fetches" vs a warm cache where nothing is recorded (measured: counter never advances) | gloss corrected; warm-cache behaviour documented with the end-to-end-bounding remedy |

### Probe ledger — Amendment 4 additions (scrapy 2.17.0 · Python 3.14.6 · 2026-07-26)

Round 3's transcripts are incorporated by reference — every T-row above marked "probed"
cites [`plan-review-report-round3.md`](plan-review-report-round3.md), whose finders and
verifiers measured each claim independently. New probes run for this amendment's own
substrate claims:

| Claim | Probe | Result |
|---|---|---|
| Transport exceptions arrive wrapped in `scrapy.exceptions.*` with these names | live crawl, recorder `process_exception` at 1000; dns-dead host, closed port, `DOWNLOAD_TIMEOUT=1` vs a 3s handler, https against a plain-HTTP port | `CannotResolveHostError` · `DownloadConnectionRefusedError` · `DownloadTimeoutError` · `DownloadFailedError` with the OpenSSL text in the message |
| A dns-dead host fails **both** its robots fetch and its page fetch | same | two `CannotResolveHostError` events, `/robots.txt` first |
| The spider errback fires after the `process_exception` chain re-raises | same, `errback=` on every seed | errbacks fired for all four transport classes |
| The `process_exception` chain runs highest-priority-first on *any* `_process_request` exception — including one raised by a lower-priority middleware | source: `download_async` try/except wraps `_process_request`; `methods["process_exception"]` is `appendleft`ed | confirmed — the recorder at 1000 sees the robots `IgnoreRequest` (round-3 probe) even though its own `process_request` never ran |
| Scrapy's robots parsers are keyed by **netloc without scheme** — an https and an http origin on one host:port share a parser | source: `_parsers[netloc]`; observed live when a TLS-dead https robots fetch set the shared parser to `None` | confirmed — first-scheme-wins stash mirrors the substrate |
| The amended task-2 and task-4 fences execute | extracted into a scratch package, `unittest discover` | **24/24 pass** (21 backoff including the six new failure tests, 3 settings) |

Validation after applying: **137 checks** regenerated from fences (drift zero by
construction), `bash -n` clean on all 137, negative-check pairing 10/10 by script, and
the amended fences executed (24/24).

## Ratification

- **ratified-by:** *pending*
- **date:** *pending*
- **amended (round 1):** F1–F3, 2026-07-25, pre-ratification
- **amended (round 2):** F4–F26, 2026-07-25, pre-ratification, operator-directed
- **amended (round 3):** R1–R10 + #11–#15 + N1, 2026-07-26, pre-ratification,
  operator-directed ("fix the whole set")
- **amended (round 4):** T1–T21 + P1 + the T3 operator decision (failure lines),
  2026-07-26, pre-ratification, operator-directed
- **review disposition:** rounds 1–3 fully applied — 26 + 15 + 22 findings
  ([round 1](plan-review-report-round1.md) · [round 2](plan-review-report-round2.md) ·
  [round 3](plan-review-report-round3.md)); nothing outstanding. Amendment 4 changed
  mechanism prose and the schema, so a **round-4 lean re-review is due before
  ratification** — operator-directed, not yet run.

Any edit after ratification voids it.
