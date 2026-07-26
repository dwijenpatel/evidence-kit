# plan-review (lean re-review) — retrieval fetcher plan, 2026-07-26

**Target:** `docs/plans/2026-07-25-retrieval-fetcher/` after Amendments 1–2 · `tasks.json` (91 checks)
**Tier:** lean — 2 translators · 2 merged finders · 2 grouped verifiers. Round 1 (full tier, 26
findings, all applied) is archived at
[`plan-review-report-round1.md`](plan-review-report-round1.md).
**Mode:** report-only. Nothing in the plan was modified.

**Verdict: do not build yet — the amendments themselves introduced a new crop of blockers.** 18
candidates → **13 CONFIRMED**, 4 refuted with quoted sentences, 1 plausible. Nearly every
confirmed finding lives in amendment-added prose — the newest, least-reviewed text, exactly where
a re-review after amendments looks. Both finders ran live probes against Scrapy 2.17.0; the
verifiers re-probed independently, so every framework claim below is measured twice.

> **The cap bites:** 10 findings reported in full; 3 confirmed findings and 2 incidental defects
> are listed under [Below the cap](#below-the-cap). Nothing was truncated silently.

## The one sentence to read first

**R2, R3, and R4 each independently make task 6's four-attempt retry example unreachable, and
the single test that would catch all three — `test_403_then_200_yields_two_entries_and_the_body_is_cached`
— is listed in the spec but gated by nothing.** Gating that one test (plus the fixes below) is
the highest-leverage change available.

---

## R1 — The slot dictionary is keyed by hostname; the plan reads it by host:port — **BLOCKER**

**Location:** task-3 Step 2 · task-5 Consumes + `delay_used_s` field note

Scrapy's `Downloader.get_slot_key` returns `urlparse_cached(request).hostname` — **port
stripped**. The plan's code and both Consumes blocks use `slots.get(netloc)` /
`slots[netloc].delay`. For ordinary hosts `netloc == hostname`, so this is near-invisible in
production — and **guaranteed broken on the `127.0.0.1:<port>` servers CLAUDE.md rule 19 mandates
for every test**. Measured: `slot_keys: ['127.0.0.1']` while `netloc == '127.0.0.1:60127'`.

- **Reading A (as written):** `slots.get("127.0.0.1:60127")` → `None` → the F3 fix loops forever
  without applying the delay; `test_declared_delay_is_applied_to_the_slot` fails; task 5's
  `slots[netloc].delay` raises `KeyError` on the first recorded response.
- **Reading B (hostname):** delay applied; `delay_used_s = 7.0`.

The trap is sharpened by the adjacent line being *correct*: Scrapy's robots parser store **is**
keyed by netloc, so `robots_info[netloc]` is right and `slots[netloc]` is wrong, in the same spec.

**Proposed rewrite:** pin a helper `slot_key(request) = urlparse_cached(request).hostname or ""`
in task 3's Provides, used by both tasks; state explicitly: *"the slot dict is keyed by
**hostname** (port stripped); `robots_info` is keyed by **netloc** (host:port). The two dicts
never share a key function — this does NOT mean they can share one."*

## R2 — The F2 fix is inert: `handle_httpstatus_all` is not a spider attribute — **BLOCKER**

**Location:** task-6 item 4a (Amendment 1's own fix)

`HttpErrorMiddleware` reads `handle_httpstatus_all` **only** from `request.meta` or the
`HTTPERROR_ALLOW_ALL` setting; the only spider attribute it consults is `handle_httpstatus_list`.
Measured: with the class attribute set, a 403 is served, the callback never fires, zero
reschedules — A3/A4 dead while the gating grep and item 4a both look satisfied.

Worse, **F2's own regression test is blind since Amendment 2**: the recorder moved to the
downloader chain (priority 1000), which sits *upstream* of the spider middleware doing the
dropping — so `test_503_reaches_the_recorder_and_is_cached` passes green over a broken spider.
Its annotation ("without handle_httpstatus_all this yields zero manifest lines") is now false.

**Proposed rewrite:** item 4a pins `custom_settings = {"HTTPERROR_ALLOW_ALL": True}` (or the meta
key on every request); the regression test asserts the **callback** observed the 503 (a retry was
scheduled), not that the recorder did; gate `test_403_then_200_…`.

## R3 — Retry requests are eaten by the duplicate filter — **BLOCKER**

**Location:** task-6 item 3 vs item 7

`dont_filter` appears exactly once in the plan — item 3, pinned `False`, with a rationale that
reads global. A spider-issued retry of the same URL is therefore dropped by `RFPDupeFilter`.
Measured: host 403s forever → **one** server hit, **one** manifest line, no `blocked` ever
written; the retry never left the scheduler. (Scrapy's own `RetryMiddleware` sets
`dont_filter=True` on retries for exactly this reason — and F5 turned it off.)

**Proposed rewrite:** item 7 pins the retry construction:
`response.request.replace(dont_filter=True, meta={..., "attempt_n": n+1})` — with the negative
example: *"this does NOT mean seeds change; `dont_filter=False` in item 3 is scoped to seeds."*

## R4 — Even unfiltered retries are served from the HTTP cache and skipped — **BLOCKER**

**Location:** task-5 cached-skip rule (Amendment 2 #13) vs task-6 item 7

`DummyPolicy` caches **every** status (`HTTPCACHE_IGNORE_HTTP_CODES` defaults empty — and task
2's own comment says "returns every cached response regardless"). So attempt 1's 403 is cached;
attempts 2–4 are served from disk with the `"cached"` flag; the #13 skip rule discards them.
Measured with `dont_filter=True`: 4 callbacks, **one** server hit, attempts 2–4 flagged
`cached` — backoff never touches the wire, the four-line worked example unreachable a second
way.

**Proposed rewrite:** task 2 sets `HTTPCACHE_IGNORE_HTTP_CODES` to the retryable set (or retries
carry `meta={"dont_cache": True}`); a test asserts a 403-then-200 host is hit twice on the wire.

## R5 — The robots.txt fetch is recorded, so every line-count in the plan is wrong

**Location:** task-6 item 4 (exclusion list) vs both worked examples

The robots request traverses the full downloader chain; the recorder at 1000 sees it. Item 4's
exclusion list has exactly one entry (`"cached"`). Measured: 2 seeds → **3** recorder lines
(`/robots.txt` first). So "exactly two lines", `test_two_seeds_produce_two_manifest_entries`, and
`--limit` counting "2xx recorded" are all wrong or contradicted.

- **Reading A (item 4 literal):** robots fetches are attempts, recorded — every count in the plan
  off by one per host.
- **Reading B (worked examples literal):** the recorder skips robots — by a rule stated nowhere.

**Proposed rewrite:** decide and pin. Recommended: **record it** (rule 15 reads that way, and A5
gains a real artifact for the robots bytes) and fix the examples to three lines with
`seed_signal: null` — plus `--limit` counting only seed-originated 2xx.

## R6 — Two reachable moments where `fetch_policy`'s source doesn't exist yet — crash or forbidden null

**Location:** task-5 `fetch_policy` note vs task-3 item 6a

(i) The robots.txt response's own recording happens at priority 1000 **before** the robots
middleware (100) stores `robots_info[netloc]` — measured: `robots_info has netloc? False` at
record time. (ii) A transport-level robots failure (connection refused) produces **no response**,
so task 3's "unusable response" rule never fires and no entry is ever written — measured. In both
moments the recorder must `KeyError` (crashing the run per task 6's error model), write
`"robots_url": null` (forbidden: "Everything else is never `null`"), or synthesize — stated
nowhere. This was also the one structural divergence in the 2-way translator diff.

**Proposed rewrite:** pin the fallback: *"when `robots_info` has no entry for the host,
`robots_url` is synthesized as `<scheme>://<hostname>/robots.txt` and the other two fields are
`null`; this does NOT license a second robots GET."* Extend task 3's 6a to the no-response case.

## R7 — An anchored check rejects the exact line its own task ships verbatim

**Location:** `tasks.json` fetcher-skeleton · task-2 Step 4

`grep -qE '^CONCURRENT_REQUESTS_PER_DOMAIN = 1$'` exits 1 against the shipped
`CONCURRENT_REQUESTS_PER_DOMAIN = 1      # one connection per host, always` — the trailing
comment breaks the `$` anchor (verified, both greps). A faithful `code-complete` transcription
fails its own task. Collateral from Amendment 2's F6 anchoring; the only one of the five anchored
greps whose target line carries a comment.

**Proposed rewrite:** move the comment above the line in Step 4 (keeping the check), or relax
that one check to `^CONCURRENT_REQUESTS_PER_DOMAIN = 1\b`.

## R8 — A second *scheduling* path for JSON passes all three A7 instruments

**Location:** task-6 A7 section · Amendment 2 row F8

Amendment 2 moved body handling wholly into `record.py` — which severs the causal link F8's row
still claims: byte identity can no longer "forbid a second code path", because the spider never
touches bodies. A spider with `if response.url.endswith(".json"): <different scheduling>` yields
byte-identical cache, equal key sets, and no content-type string (all three instruments green,
verified) — while the PRD's A7 explicitly puts scheduling in scope ("goes through the same
**throttle**, cache, and manifest … no second code path").

**Proposed rewrite:** correct F8's row and task 6's overclaim; the honest statement is that A7's
spider-side half rests on item 5's prose plus review, and the byte-identity test guards only the
recording half. Optionally add a two-content-type timing assertion.

## R9 — Amendment #15's fix is gated by a substring that a comment satisfies

**Location:** `tasks.json` fetch-spider — `grep -qF 'HTTPCACHE_DIR' cli.py`

The gate passes on a comment (and the plan's own settings comment already contains the token). No
test binds the effective cache location: both cache-touching tests run from one cwd, so a relative
`httpcache` still hits (verified) — #15 can be silently undone with all 91 checks green.

**Proposed rewrite:** anchor the gate to an assignment (`grep -qE 'HTTPCACHE_DIR.*abspath'`) or
add a test asserting the httpcache directory materialises under the cache root.

## R10 — Task 7's end-to-end test consumes contracts it never restates

**Location:** task-7 "How a capture actually gets fetched"

Task 7 has no `Consumes` block, and "runs the spider" does not decide CLI vs in-process. The two
differ observably: an in-process run bypasses the `--contact` gate, so `useragent_sent` records
the literal `{contact}` — which task 6 says must never reach the wire — and the test's two
assertions cannot see it. plan.md's "each Consumes has a matching Provides" is vacuously true
here; task 4's vacuity is legitimate (stdlib-only), task 7's is not.

**Proposed rewrite:** give task 7 a Consumes block restating the CLI signature; pin the
invocation as the CLI with a `--contact` supplied; assert `useragent_sent` contains it.

---

## Below the cap — confirmed, not reported in full

| # | Location | Defect |
|---|---|---|
| 11 | plan.md Amendment 2 row 23 | "test gated" is false — `test_empty_seed_table_is_a_noop` is in no check; five more listed tests are ungated, two of them cited in the coverage table as discharging A9/A5 (Amendment 1 fixed "gated" as meaning in-`tasks.json`) |
| 12 | task-5 redirect rules | A redirect hop being "its own attempt" makes the post-redirect entry `attempt_n: 2` — feeding `zero_based` into `classify_status`, so **a redirect silently eats retry budget** and the 4-attempt example holds only redirect-free; the schema sample shows `attempt_n: 1` on exactly such an entry |
| 13 | plan.md self-review | "Every negative check is paired…" is false at 1 of 9: task 2's `evidence_fetch` grep has no positive gate on `scaffold.py`/`templates/` (mitigated: the scaffold suite in the same task would fail if they vanished) |
| 14 | task-5 schema sample | Incidental: sample's `url_final` (`…/pricing/`) is not an element of its own one-element `redirect_chain` (`…/pricing`) — the sample contradicts the "chain's last element" rule it sits beside |
| 15 | task-5 `attempt_n` "in this run" | PLAUSIBLE: undefined across a JOBDIR resume (1 vs 3 on the resumed attempt) — currently masked by R4, becomes observable once R4 is fixed |

## Negative space

**18 deduped candidates → 13 confirmed, 4 refuted with quoted sentences, 1 plausible.** The
translator diff produced 1 structural divergence (absorbed into R6); the two finders converged
independently, with separate live probes, on R2, R3, R4, and R5.

### Refuted (4)

| Candidate | Refuted because |
|---|---|
| `{contact}` reaches the wire under a header-only reading | *"a literal `{contact}` placeholder that **must never reach the wire**"* pins the observable universally; the setting-override is also the only non-deprecated mechanism in 2.17. (Task 7's in-process leg survives inside R10) |
| `cli.py` could re-enable Scrapy retry; module tests can't see the crawl | *"Scrapy's RetryMiddleware **must stay off**"* (task 2) + *"The spider is the only retry mechanism"* (task 6) — categorical prohibitions; the Scrapy facts were right but immaterial |
| `seed_signal` contradicts itself for a seeded capture | *"There is no Wayback code path"* forbids the null-for-Wayback reading outright; the copy-from-seed-row reading is the only implementable one. Wording residue: rewrite as "null when no Seeds row queued it" |
| Task 7's "verbatim" file lacks the gated 13th test | The e2e paragraph pins adding it ("one end-to-end test lives here", named, with behaviour). Residues survive: "verbatim"/"12/12" become inaccurate, and A8's only e2e ships as prose in a `code-complete` task |

### Verified sound

All 91 checks match the spec fences command-for-command (zero drift — the generation mechanism
held) · all shipped verbatim code extracted and executed: **41/41 tests pass** (cache 5, seeds 7,
settings 3, backoff 14, wayback 12) · `grep -qxF 'cache/'` behaves identically under both greps
and matches the fenced line · task 3's rebuilt timing test is discriminating (~1s dead vs ~3s
live) · `url_requested` for a redirected fetch **is** pinned (chain element 0 + the schema
sample) · task 1's substring output contract holds under `longMessage` · `data_path` absolute
passthrough, recorder-at-1000 wire bytes, `"cached"` flagging, and the 403-forever arithmetic all
re-verified correct · Amendment 1's `async def robot_parser(self, request)` correction matches
installed source.

## Recommended disposition

R1–R4 are blockers of the same species as round 1's: each defeats an acceptance criterion while
every gating check stays green, and R2 is a defect **in a prior fix**. R5+R6 are one coupled
decision (is a robots fetch an attempt?) — decide once, both resolve. R7 makes task 2 unbuildable
as transcribed and is a one-line fix. The pattern across rounds is now unmistakable: **prose that
names a Scrapy mechanism without having run it is wrong at a very high rate** — every fix landing
in an amendment should arrive with a live probe, the way these findings did.

**Do not implement before R1–R7 are resolved.** The rest folds into one amendment round.
