# plan-review (lean re-review, round 3) — retrieval fetcher plan, 2026-07-26

**Target:** `docs/plans/2026-07-25-retrieval-fetcher/` after Amendment 3 · `tasks.json` (121 checks)
**Tier:** lean — 2 translators · 2 merged finders · **substrate-truth finder** (first firing) · 3 grouped
verifiers. Rounds 1–2 archived at
[`plan-review-report-round1.md`](docs/plans/2026-07-25-retrieval-fetcher/plan-review-report-round1.md) ·
[`plan-review-report-round2.md`](docs/plans/2026-07-25-retrieval-fetcher/plan-review-report-round2.md).
**Mode:** report-only. Nothing in the plan was modified.
**Probe substrate:** scrapy 2.17.0 · Python 3.14.6 · uv 0.11.30 · BSD grep 2.6.0 — every claim below is
true of these versions on this date; a dependency bump invalidates the substrate section wholesale.

**Verdict: do not build yet.** 23 deduped candidates → **21 CONFIRMED** (10 reported in full, 11 below
the cap), 1 plausible, 2 refuted outright with quoted pins, 2 partial refutations inside confirmed
classes. The translator diff produced **zero** structural divergences for the first time in three
rounds; nearly everything that survived came from the substrate finder and from probing the semantics
of amendment fixes against each other. Both finders and all three verifiers ran live probes
independently — every framework claim below is measured at least twice.

> **The cap bites:** 10 findings in full; 11 confirmed and 1 plausible in the below-the-cap table.
> Nothing was truncated silently.

Read it with:

```
sed -n '/^## T1/,/^# Below the cap/p'  plan-review-report.md   # the ten findings
sed -n '/^# Below the cap/,$p'         plan-review-report.md   # the rest, the refutations, the split
```

## The one sentence to read first

**Task 3's "load-bearing parts exact" sketch line — `parser.crawl_delay(...)` — raises
`AttributeError` on every call in scrapy 2.17.0, and the task's own error model swallows it into
`DEFAULT_DELAY` with one WARNING: A1, the criterion this whole project exists for, dies at runtime in
the spec's own code** (T1) — and the unit-test harness the same task prescribes cannot catch it,
because `get_crawler()` never builds an engine and the pinned assertion path raises before touching a
slot (T2).

---

## T1 — The crawl-delay call is made on the wrong object; A1 dies silently — **BLOCKER**

**Location:** task-3 Consumes (`protego.Protego.crawl_delay … which Scrapy already constructs`) + Step 2 sketch (`declared = parser.crawl_delay(…)`)

**Falsified substrate claim.** What `robot_parser()` yields is Scrapy's wrapper
`scrapy.robotstxt.ProtegoRobotParser` (public surface: `allowed`, `from_crawler`, `rp`, `spider`) —
the Protego instance lives at `.rp`. Probed end-to-end with the exact sketch line wired in:

```
event: ('crawl_delay-EXC', '127.0.0.1:65434', "AttributeError: 'ProtegoRobotParser' object has no attribute 'crawl_delay'")
FINAL slot.delay: 5.0            (server declared Crawl-delay: 7)
parser.rp.crawl_delay(ua) -> 7.0 (the corrected line, same harness)
```

The `except Exception` in the same sketch catches the AttributeError, logs WARNING, memoizes the host
at `DEFAULT_DELAY` — permanently, because `self._applied.add(key)` runs before the `declared is None`
return. At runtime this is exactly the incident the project exists to fix. At build time the five
gated delay tests do go red (5.0 ≠ 7.0), so the defect costs debugging, not production — but the spec
hands a fresh implementer a false "exact" line and an error model that hides why it fails.

**Rewrite:** Consumes pins `scrapy.robotstxt.ProtegoRobotParser` — `.allowed(url, ua)`; `.rp:
protego.Protego` — `.crawl_delay(ua) -> float | None`. Sketch line becomes
`parser.rp.crawl_delay(…)` with the negative example naming the AttributeError-swallowed-by-except
trap.

## T2 — The prescribed test harness cannot reach a slot: `get_crawler()` has no engine — **BLOCKER**

**Location:** task-3 Step 1 ("wired to a `Crawler` built by `scrapy.utils.test.get_crawler`, then assert on `crawler.engine.downloader.slots[…].delay`")

**Falsified substrate claim.** `crawler.py:87` sets `self.engine = None`; it is assigned only inside
`crawl()`. Probed:

```
crawler.engine : None
PINNED EXPR RAISES: AttributeError 'NoneType' object has no attribute 'downloader'
```

All **ten** unit tests in the block are specified against that expression — including the two R1/R6
regression tests Amendment 3 added — and die before any assertion. Two working harnesses were probed:
(a) build the downloader yourself and inject it (`Downloader(crawler)` +
`crawler.engine = SimpleNamespace(downloader=…)` → delay 5.0→7.0 observed through the pinned
expression); (b) assert from inside a live `CrawlerProcess` crawl (engine real; needed anyway for
`test_delay_survives_ten_responses` and the wall-clock test).

**Rewrite:** replace the harness sentence with (a) for the unit block and (b) for the two traffic
tests, plus the negative example quoting the AttributeError.

## T3 — An attempt that produces no response vanishes without trace, and nothing pins it

**Location:** task-5 recorder rules + nullable list · task-6 error model · CLAUDE.md rule 15

Two finders converged; the verifier narrowed it. A connection-refused / DNS-dead / timed-out fetch
never reaches `process_response`; probed at priority 1000:

```
{"hook":"process_exception","url":"http://127.0.0.1:65441/robots.txt","exc_type":"DownloadConnectionRefusedError"}
{"hook":"process_exception","url":"http://127.0.0.1:65441/page","exc_type":"DownloadConnectionRefusedError"}
```

Zero manifest lines — not even a robots line for the host. A robots-`Disallow`ed seed likewise
(`IgnoreRequest` → no response, no line), even though PRD §6 makes robots-disallow one of exactly two
grounds for `blocked` — **task 4 ships `Disposition.BLOCKED` with no producer for that ground.** The
null-entry reading is refuted by quote ("Everything else is never `null`"), so the surviving
divergence is: recorder implements `process_response` only (zero lines) vs `process_exception` too
(a line with an invented sentinel status). The PRD's §7 narrative justifies per-attempt recording
with a timed-out CDX query yet defines no shape for one — it cannot adjudicate.

**Rewrite (decision, not schema invention):** pin the zero-lines reading as a stated exception to
rule 15 — "no response → no entry and no artifact; absence of a line means never-fetched, never
fetched-and-failed; this does NOT mean a 403/503 is unrecorded (those are responses), and does NOT
license nulls" — plus a decision-log row recording the alternative (sentinel status under
`schema: 2`) as the deliberate deferral, and a note that robots-disallowed seeds are visible only in
the log.

## T4 — `parse_retry_after(...) or backoff_delay(...)` discards an honoured `Retry-After: 0`

**Location:** task-6 item 7 (the pinned expression) vs task 4's contract

`0.0` is falsy. Probed:

```
header='0'    parse_retry_after=0.0    `or` -> 1.0     `is not None` -> 0.0
header='-5'   parse_retry_after=0.0    `or` -> 1.0
header=None   parse_retry_after=None   `or` -> 1.0     (the only case `or` should catch)
```

Task 4 pins `"0"` → `0.0`, past-date → `0.0`, `"-5"` → `0.0`, and "every parse failure returns
`None` … 'use our own backoff'" — `None` is the only fall-through signal. Three of task 4's seven
worked-example rows are dead code at their only call site.

**Rewrite:** `ra if (ra := parse_retry_after(retry_after_header, now)) is not None else
backoff_delay(zero_based)` — "**`is not None`, never `or`**", with the falsy-zero negative example.

## T5 — `Retry-After` is unenforced end-to-end: no mechanism, no instrument

**Location:** task-6 item 7 ("reschedule after … seconds") · F5's rationale in plan.md and task-2

An implementation that never calls `parse_retry_after` and re-yields the retry immediately is green
against every check in the plan. Probed: with `Retry-After: 120` and `DOWNLOAD_DELAY = 5.0`, the
immediate re-yield produced a 4.999s gap and identical entries/wire-counts; with `DOWNLOAD_DELAY =
1.0`, a 1.001s gap — the gap tracks the slot delay, never the header. No check greps `fetch.py` for
`parse_retry_after`; task 4 tests the function, never its use. So the stated reason Scrapy's
RetryMiddleware was turned off — it cannot honour `Retry-After` — is currently true of the
replacement too, invisibly.

**Rewrite:** pin the deferral obligation ("deferred by that many seconds before it is handed to the
scheduler; the delay value is not a seam") and gate the one instrument that can see it:
`test_retry_after_header_defers_the_retry` — 403 + `Retry-After: 3` then 200, `DOWNLOAD_DELAY = 1.0`,
assert the two wire hits ≥ 3s apart (the header must exceed the slot delay or the test proves
nothing — the same discriminance rule Amendment 1 fixed in the crawl-delay timing test). Tripwire:
`grep -qF 'parse_retry_after' fetcher/evidence_fetch/spiders/fetch.py`.

## T6 — The memo in the fixed sketch is keyed by slot key; a second same-hostname host's delay is silently discarded

**Location:** task-3 Step 2 sketch (`self._applied` — comment says "netlocs", code adds `key`)

Amendment 3's R1 edit changed the lookups but memoized on the slot key. Probed live, two rule-19
servers sharing slot key `127.0.0.1`:

```
memo-by-slot-key: ('applied', ':65471', '5.0->7.0') ('memo-skip', ':65472')  FINAL 7.0   <- 15 never read
memo-by-netloc  : ('applied', ':65491', '5.0->7.0') ('applied', ':65492', '7.0->15.0')  FINAL 15.0
```

Behaviour rule 2 ("set that host's slot delay") is violated for the second host; rule-19 makes the
collision guaranteed in this project's own test suite, and `CONCURRENT_REQUESTS_PER_IP` would extend
it to every host. Amendment 1's F3 row says "a **netloc** is marked applied" — the comment is right,
the code is wrong.

**Rewrite:** memo keyed by `urlparse_cached(request).netloc`; slot lookup stays `get_slot_key`; the
two-server negative example inline.

## T7 — The pinned subprocess invocation is red from any foreign cwd: `--project fetcher` is relative

**Location:** task-6 `test_httpcache_lands_under_the_cache_root` ("cwd elsewhere") · task-7 Consumes/e2e (pins the same command)

Probed (uv 0.11.30): from a tmpdir cwd, `uv run --project fetcher …` → `warning: Project directory
'fetcher' does not exist` + `No module named evidence_fetch`, exit 1 — red against a correct
implementation. The finder's "requires a foreign cwd" was an overstatement: the pin is only
"cwd != cache-root's parent", which **cwd = repo root satisfies** — and `data_path()` is scrapy's
*only* producer of `<cwd>/.scrapy` (only `HTTPCACHE_DIR` flows through it), so asserting
`<repo-root>/.scrapy` absent is sound.

**Rewrite:** pin cwd = repo root for every subprocess invocation of the pinned command (or an
absolute `--project`); cache-root in a TemporaryDirectory; assert `<cache-root>/httpcache/` exists
and `<repo-root>/.scrapy` does not; delete a stale `.scrapy` in setUp. Add one sentence to task 7's
Consumes: the command is cwd-relative.

## T8 — The robots entry's `attempt_n: 1` is jointly unsatisfiable with "from meta, nowhere else"

**Location:** task-6 item 3 ("learns both values from meta, nowhere else") vs item 4 (robots entry "`attempt_n: 1`") vs task-5's nullable list (`attempt_n` never null)

Probed — the robots request's meta at priority 1000:

```
{"url":".../robots.txt","meta_get_attempt_n": null, "meta_get_seed_signal": null,
 "meta_keys":["dont_obey_robotstxt","download_latency","download_slot","download_timeout"]}
```

Scrapy builds it with a one-key meta (`robotstxt.py:90-95`). "Nowhere else" ∧ "robots line carries
`attempt_n: 1`" ∧ "never null" cannot all hold; `meta["attempt_n"]` raises `KeyError` on the first
robots response of every run.

**Rewrite:** recorder reads `meta.get("attempt_n", 1)` / `meta.get("seed_signal")` — "the default is
load-bearing, not defensive", with the probed meta-keys list and the KeyError negative example.

## T9 — Amendment 3's own robots-error recording is untranscribable: `_robots_error` has no scheme

**Location:** task-3 6a ("record `{"robots_url": f"{scheme}://{netloc}/robots.txt", …}` there") + the transport-failure test description (hardcodes `http://`)

Probed: `_robots_error(self, exc, netloc)` — locals are `['exc','netloc','self']`; the 6a f-string
raises `NameError: name 'scheme' is not defined`. The scheme's last holder is `robot_parser(request)`.
The paired test hardcodes `http://`, so it cannot adjudicate the synthesis rule on any https host.

**Rewrite:** stash `urlparse_cached(request).scheme` per netloc in `robot_parser` before deferring to
super; `_robots_error` reads the stash; negative examples for both the NameError and the
`http://`-hardcode; the test asserts against an https-shaped expectation too or states why not.

## T10 — The runbook's "deleting `.jobdir` never duplicates manifest history" was falsified by R4

**Location:** task-6 runbook vs task-2 `HTTPCACHE_IGNORE_HTTP_CODES`

Measured: 403-forever host, run → 5 lines; delete `.jobdir/`, rerun with the same httpcache → **4
fresh wire hits, 4 new lines** (`attempt_n` 1–4 again) — retryable statuses are deliberately never
cached, so nothing shields them from re-attempt. The sentence was true before Amendment 3. The gated
jobdir-delete test's fixture names no statuses, so the natural all-200 fixture is green and blind.

**Rewrite:** scope the claim — 2xx/3xx-final URLs append nothing; retryable-final URLs get a fresh
attempt sequence *by design* (new attempts are new records under rule 15); note it in the test's
fixture comment.

---

# Below the cap — confirmed, not reported in full

| # | Location | Defect |
|---|---|---|
| T11 | task-6 403-then-200 annotation | Parenthetical claims a cache-served retry "writes a second line" — task 5's skip rule (pinned three ways) means it writes none; measured: broken config → **1** line, not 2, not 4. The wire-hit assertion is right; its stated rationale is false, and both finders converged on it |
| T12 | task-3 `test_slot_key_is_hostname_not_netloc` | As enumerated it asserts only downloader facts — probed green over a netloc-reading middleware. "A regression test that cannot fail is not a regression test" (plan.md's own rule). Add the `delay == 7.0` assertion |
| T13 | task-5 line taxonomy | `url_requested` present + `schema` absent is unclassified (crash vs skip divergence); deeper: a sub-project-2 line with `url_requested` + `schema: 2` **raises** per row 5, defeating #12's stated purpose. Pin: fetcher line ⇔ has both keys; state the seam obligation |
| T14 | task-5 #15 resume sentence | "Resumes as 2" holds for a queued retry (probed) — but a **second Ctrl-C or crash during the backoff wait** loses the retry; fingerprint already in `requests.seen` → URL never refetched, last line reads `retry` forever (probed: 0 fetches on resume). Scope the sentence truthfully |
| T15 | task-5 "preserve original casing" | False — `Headers.normkey` is `key.title()`, below every middleware: `ETag`→`Etag`, `x-archive-orig-…`→`X-Archive-Orig-…` (probed). Values byte-preserved. A WARC export reconstructs casing like the reason phrase and must say so |
| T16 | task-5 slot-survival parenthetical + plan.md ledger row | Justification false: the request leaves `slot.active` before `process_response` runs (probed `request in slot.active = False` on every response). Conclusion survives via `lastseen + delay` + the 60s GC loop. Fix the sentence and the ledger row — a probe ledger with a wrong Result row poisons the instrument |
| T17 | task-6 `--limit` vs a pending retry | Unpinned whether a decided retry is a "new request"; suppressing it leaves `disposition: "retry"` as a URL's last word with no attempt behind it. Pin: retries run to their `classify_status` conclusion; restate the overshoot bound |
| T18 | task-6 error model | Exit code of a *completed* crawl (incl. blocked/fatal URLs) pinned nowhere; three subprocess tests must guess. Pin exit 0 for every completed crawl |
| T19 | tasks-3/5 absence greps | `validators_sent`, `normalized_content_sha256` (recursive), `AUTOTHROTTLE_MAX_DELAY` forbid tokens the plan's own house style writes into comments — the "even in comments" rule is stated only for `content.?type` and Wayback. Extend it explicitly at all three sites. (`def start_requests` REFUTED — definition form, composes correctly with the positive check) |
| T20 | task-2 settings fence | `REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"` — **zero occurrences in scrapy 2.17.0**, no warning, no effect (removed; only `…_CLASS` exists); `FEED_EXPORT_ENCODING` real but inert (no feeds; rule 14 forbids a third write path). Both falsify the fence docstring's "Every value here is a PRD or CLAUDE.md constraint". Delete both, comment why |
| T21 | task-3 error model row 1 | "Never treat an unreadable robots.txt as 'no rules'" is false of what will be built (superclass fails open — probed: empty/garbage/binary robots all allow) and an **unstated deviation** from PRD §6's "fail closed … never cache 'unreadable' as 'no robots.txt'". The plan's convention requires deviations stated. Reword the row; state the deviation |
| P1 | task-6 `--limit` gloss | PLAUSIBLE (ambiguity refuted — counter basis is pinned): with a warm httpcache and deleted `.jobdir`, cache-served 200s write no entry, the counter never advances, `--limit` is a no-op and every uncached seed is fetched unbounded (measured). Fix the `# stop after N successful fetches` gloss and document the warm-cache behaviour |

# Negative space

**23 deduped candidates → 21 confirmed, 1 plausible, 2 refuted outright; 2 partial refutations inside
confirmed classes; finder overstatements corrected in six places** (single-SIGINT resume works;
sibling delay tests do catch T1 at build; entry counts do discriminate in T11; R9 needs no foreign
cwd; robots-error recording is implementable with a second hook; `len(slot.active)` nonzero with a
sibling queued).

### Refuted (with the pinning evidence)

| Candidate | Refuted because |
|---|---|
| Redirect-hop entry's chain shape (two finders) | *"the hop is recorded — its body cached, its `redirect_chain` ending at the hop"* binds "the hop" to the 301 response; and the only named mechanism (`response.meta["redirect_urls"]`) **cannot** produce the Location-target reading — probed: the hop's own meta has no `redirect_urls`. General rule verified: `chain = meta.get("redirect_urls", []) + [request.url]` satisfies every invariant on every entry |
| Robots fail-open vs fail-closed | Pinned open by *"every page recorded on that host falls to task 5's fallback"* + *"a response on a host whose robots fetch died in transport"* (declared reachable) + item 5's unchanged-superclass sentence. The PRD-deviation residue survives as T21 |
| `! grep -qF 'def start_requests'` over-pin | Definition form; the plan's prose never writes it; `'async def start'` is a substring of `async def start_requests`, so the pair also catches the near-miss |
| `--limit` warm-cache *ambiguity* | *"counts 2xx responses with a non-null `seed_signal` **recorded this run**"* composed with the cached-skip rule is determinate; the behaviour itself survives as P1 (doc fix) |

### Verified sound

Two independent translations agreed on **every** overlapping contract point — the 22-field schema
sample value-for-value, attempt_n rules, retry construction, worked-example line counts, exit codes,
task-7 URL strings (coverage caveat: translator B went deep on tasks 5–7; tasks 1–4 rest on one
translation plus rounds 1–2) · **30 substrate claims probed and confirmed**, including the full
Amendment-3 ledger minus the two rows corrected above (slot keys, robots-URL netloc, recorder-at-1000
ordering, `HTTPERROR_ALLOW_ALL` via `custom_settings`, `dont_filter=True` retries, ignore-codes
under DummyPolicy, redirect meta inheritance, JOBDIR meta persistence, dead `start_requests`,
AutoThrottle clamping, priorities 100/550/590/600/900, wire-octet recording at 1000, stock-robots
double-fetch without `None`, `data_path` semantics, `id_` capture URL surviving Scrapy verbatim) ·
**every verbatim fence in tasks 2, 4, 7 extracted and executed: 42/42 pass** · task-5 schema sample
internally consistent (22 keys = `REQUIRED_KEYS`, `url_final` = chain[-1], `cache_relpath` derived
from the digest) · `tasks.json` regenerated fences byte-identical (drift 0), `bash -n` 0/121
malformed, negative-check pairing 10/10 · the sharp checks all green against the shipped artifact and
red against their named defects (R7 comment-anchor, drifted ignore-codes, `--` before `--contact`,
whole-line `cache/`, content-type absence, N1 tripwire).

# The amendment split

Round 2 measured "nearly all findings in amendment prose." This round splits roughly **9 of 21 in
Amendment-3-introduced or -collateral prose** (T6, T7, T8, T9, T10, T11, T12, T14, T16) versus **12
in older prose that survived two full review rounds** (T1, T2, T3, T4, T5, T13, T15, T17, T18, T19,
T20, T21). The older half was reachable only by the substrate finder and by execution — T1 sat in
"load-bearing parts exact" code through three rounds of divergence-pair review. The instrument that
changed is the instrument that found them.

# Recommended disposition

T1+T2 are one fix session (same file, same sketch; T2's harness is what proves T1's fix). T3 is the
one **design decision** — it needs the operator, not just an editor, because it states an exception
to rule 15 and touches what "absence" means in a corpus built against false absences. T4/T5 are one
edit to item 7 plus one new gated timing test. T6–T10 and the below-cap items are mechanical spec
edits with probes already in hand. The pattern this round: **fixes are substrate claims** — every
blocker in T1–T9 except T3 lives in or beside a sentence an amendment wrote while fixing something
else. Amendment 4 should land with probe rows (most are already run — reuse these transcripts), and
the regression demonstrations belong in the amended text, not the report.

**Do not implement before T1–T9 are resolved; ratification also wants the T3 decision recorded in
the decision log.**
