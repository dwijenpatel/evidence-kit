# plan-review (lean re-review, round 4) — retrieval fetcher plan, 2026-07-27

**Target:** `docs/plans/2026-07-25-retrieval-fetcher/` after Amendment 4 · `tasks.json` (137 checks)
**Tier:** lean — 2 translators · 2 merged finders · substrate-truth finder · 3 grouped verifiers.
Rounds 1–3 archived at `plan-review-report-round{1,2,3}.md` (same directory).
**Mode:** report-only. Nothing in the plan was modified.
**Probe substrate:** scrapy 2.17.0 · Python 3.14.6 · uv 0.11.30 — claims are true of these versions
on this date; a dependency bump invalidates the substrate sections wholesale.

Read it with:

```
sed -n '/^# Executive tier/,/^# Findings/p'  plan-review-report.md   # the decisions and the ranking
sed -n '/^# Findings/,/^# Negative space/p'  plan-review-report.md   # all sixteen, in full
sed -n '/^# Negative space/,$p'              plan-review-report.md   # what was refuted, and why
```

# Executive tier

**Amendment 4's failure-line design is right in shape and wrong in five producers — and its two
task-3 fences each contain a defect that kills a real crawl or the whole test file, which is the
fourth consecutive round in which the newest fixes carried the sharpest defects.**

18 deduped candidates → **16 CONFIRMED, 2 refuted with quotes**. Translator diff: **zero
divergences, second round running** — everything below is falsehood, seams between two universal
rules, or oracle gaps; nothing is classic ambiguity anymore.

Ranked, most severe first. Two findings need an **OPERATOR DECISION**; the rest are editor work.

| # | One line | Needs |
|---|---|---|
| U1 | `useragent_sent` has no value on a robots-disallowed failure line (headers `{}` at priority 100 — probed) — either it goes nullable or the fetcher records a header never sent | **OPERATOR DECISION** (nullable-set change on the one-way-door schema) |
| U2 | `DOWNLOAD_TIMEOUT` is nowhere set; scrapy's default 180s makes a hung host cost ~15 unattended minutes, and the failure sample's "30.0 seconds" is scrapy's verbatim message at a setting no line ships | **OPERATOR DECISION** (a new pinned politeness value) |
| U3 | BLOCKER — task 3's `__init__` fence never creates `_scheme_by_netloc`; the 6a override raises before `super().robot_parser`, outside the superclass try — **every request on every host dies** (probed) | editor (one line) |
| U4 | BLOCKER — the pinned unit harness's engine stub lacks `download_async`; the robots middleware's own `except` swallows it → parser None, delay never applied, the "highest-value test" unsatisfiable, and the fence's "(probed: 5.0 → 7.0)" was never measured on the documented path | editor (probed stub shipped below) |
| U5 | BLOCKER — `delay_used_s` on a pre-downloader failure line: the request never refreshes `lastseen`, `_slot_gc` reaps the host's slot mid-crawl (probed live: present at t=0.2s, gone at t=130.4s), `slots[key]` → KeyError inside `process_exception` | editor |
| U6 | Two universal rules give a redirect-then-timeout entry two different chains; the meta is present at `process_exception` (probed), so the one-expression rule wins | editor |
| U7 | The fetch-policy fallback's "exactly two reachable moments" missed the third one Amendment 4 itself created (the robots fetch's own *failure* line), and the `process_exception` bullet never mentions `fetch_policy` | editor |
| U8 | The two schema samples, read side by side, contradict the `prior_fetch_ref` rule: same URL, failure line 30s after the 200 line, showing `null` where the rule says carry the digest | editor |
| U9 | A guard-legal non-URL seed row (task 1 blesses it) raises inside `async def start()`, killing the generator: **every later seed silently dropped, exit 0** (probed) — no task ever validates it | editor |
| U10 | "Manifest schema violation → crash the run" is unimplementable as written: middleware exceptions are handled, `CloseSpider` is swallowed (probed) — `engine.close_spider` + a `finish_reason` check works (probed) | editor |

Below the tier: U11–U16 (test drive-order, "unusable" undefined, a vacuous assertion, an honest
unenforceability note, a Consumes block gap, check-scope asymmetry) — all editor work, all in full
below.

**The amendment split:** ~13 of 16 sit in Amendment-4 prose or its direct collateral; U9's root and
U10's root predate it but were armed by Amendment-4 sentences (the carve-out, T18). Four rounds
measured: the newest fixes are always the hottest surface.

# Findings

## Operator decisions

### U1 — `useragent_sent` and `request_headers` have no producer on a robots-disallowed failure line

**Location:** task-5 nullable rules + failure sample · task-6 `test_robots_disallowed_seed_writes_blocked_line` · task-7's gloss

Probed by three agents independently: `RobotsTxtMiddleware` raises `IgnoreRequest` at priority
**100**, before `DefaultHeadersMiddleware` (400) and `UserAgentMiddleware` (500) populate headers —
the recorder's `process_exception` sees `request.headers == {}` on exactly this class:

```
http://…/page       | IgnoreRequest                  | headers: []
http://…/robots.txt | DownloadConnectionRefusedError | headers: ['Accept','Accept-Language','User-Agent','Accept-Encoding']
```

`useragent_sent` is non-nullable on every line, so the taxonomy's flagship class either violates the
prose or records a synthesized value. (Finder overstatement corrected: `append_entry` as specified
does not enforce non-nullability, so this is prose self-contradiction, not a guaranteed crash.) The
failure sample's populated headers are a *timeout* line — a different class, where headers exist
(probed) — so it pins nothing here.

**Decision:** make `useragent_sent` nullable (null exactly when `request_headers` is empty — the
pre-downloader classes), or record the configured `USER_AGENT` as a value that never reached the
wire. The verifier's recommendation, consistent with the plan's own fidelity rationale (the same one
that removed `response_status_line` and forbade a synthesized 599):

> `useragent_sent` is the `User-Agent` value **in `request.headers`**, and is `null` **exactly when
> `request_headers` is empty** — the robots-disallowed class, where the request died at priority 100
> before the header middlewares ran (probed, 2.17.0). Transport-death lines are unaffected: they
> carry the full header set (probed). **This does NOT mean falling back to the configured
> `USER_AGENT`** — recording a header that never reached the wire is the fake fidelity that removed
> `response_status_line`.

### U2 — `DOWNLOAD_TIMEOUT` is unpinned; the plan's own sample presupposes 30, the default is 180

**Location:** task-2 settings fence · task-5 failure sample · plan.md A9 prose

`DOWNLOAD_TIMEOUT` appears exactly once in the plan — as an Amendment-4 probe parameter. Scrapy's
default is **180** (probed at source). The failure sample's detail string is scrapy's own message
format, verbatim, at a value nothing ships:

```
probe (DOWNLOAD_TIMEOUT=3): "Getting http://127.0.0.1:65274/b took longer than 3.0 seconds."
sample:                     "Getting https://example.com/pricing took longer than 30.0 seconds."
```

At the inherited default, a hung host costs one robots fetch + four page attempts × 180s ≈ **15
unattended minutes**, during which every backoff wait sits in the callback frame (T14's forced-stop
window scales with it).

**Decision:** pin `DOWNLOAD_TIMEOUT = 30.0` in task 2 (the value the sample was written against),
with the A9/politeness rationale, a whole-line grep, and an assertion in
`test_politeness_settings_hold` — or pin 180 and rewrite the sample. The verifier's rewrite (30.0)
is in its transcript; the plan's own "unattended, interruptible, resumable" prose favours it.

## Blockers

### U3 — The task-3 `__init__` fence never creates `_scheme_by_netloc`: every request dies

**Location:** task-3 Step-2 `__init__` fence vs the 6a fence

Amendment 4's T9 fix introduced `self._scheme_by_netloc` in two method fences and never amended
`__init__`. The `robot_parser` override touches it before `super().robot_parser`, **outside** the
superclass's try/except — so the `AttributeError` propagates out of `process_request` and every
request errbacks:

```
RESULTS: {'errback': 'AttributeError("\'MW\' object has no attribute \'_scheme_by_netloc\'")'}
```

Fix (one line, in `__init__` — not lazily in 6a, where the `_robots_error`-first path would be
*silently swallowed* into a nulls-loss instead of crashing):

```python
        self._scheme_by_netloc: dict[str, str] = {}   # netloc -> first scheme seen (6a)
```

Verified green end-to-end: `{'ok': True, 'delay': 7.0, 'robots_info': {…sha256…, …fetched_at…}}`.

### U4 — The pinned unit harness cannot drive robots; its "(probed: 5.0 → 7.0)" was never measured on the documented path

**Location:** task-3 "The harness (round-3 T2)" fence

`robot_parser` awaits `self.crawler.engine.download_async(robotsreq)` — **inside its own
`except Exception`** (robotstxt.py:99–110). The stub `SimpleNamespace(downloader=…)` has no
`download_async`; the AttributeError is converted to `_robots_error` → parser `None` →
`_apply_delay` never runs, and nothing surfaces:

```
process_request returned normally
slot delay AFTER: 5.0        robots_info: {}       _parsers: {'…': None}
```

A harness bug that presents as a middleware bug: `test_declared_delay_is_applied_to_the_slot` (the
spec's self-declared highest-value test) and four siblings are unsatisfiable through the documented
path. The fence's `(probed: 5.0 -> 7.0)` parenthetical is a measured claim that is true only of
internal-seam driving the spec never describes — a false probe citation inside a spec.

Fix, probed green through the documented `process_request` for every listed unit test including the
transport-failure and disallowed cases: add an async `download_async` stub to the injected engine,
and drive with `loop.run_until_complete` — **not `asyncio.run`**, which closes the loop and kills
the next `Downloader(crawler)` in `_start_slot_gc` (reproduced):

```python
async def download_async(robotsreq):                        # THE robots transport seam
    return Response(robotsreq.url, status=200, body=ROBOTS, request=robotsreq)
    # failure variant: raise ConnectionRefusedError("refused")
crawler.engine = SimpleNamespace(downloader=downloader, download_async=download_async)
...
loop.run_until_complete(mw.process_request(request))        # the documented path
```

```
happy(7): 5.0 -> 7.0 · cap(900): 5.0 -> 60.0 · absent: 5.0 -> 5.0 · disallowed: IgnoreRequest
transport-fail: robots_info={'127.0.0.1:9999': {'robots_url': 'https://…', nulls}}
```

### U5 — `delay_used_s` crashes on a pre-downloader failure line once the slot is GC-reaped

**Location:** task-5 `fetch_policy` bullet (the slot-survival guarantee) vs failure lines

The survival argument ("`lastseen` was set by this very request") is true of responses and false of
requests that die before the downloader: a robots-disallowed request never enters a slot (no
`download_slot` meta — probed) and never refreshes `lastseen`. Probed **inside one crawl at
default GC settings**:

```
{"t": 0.2,   "url": ".../page1", "slot_present": true }
{"t": 130.4, "url": ".../page2", "slot_present": false}   <- same host, same key
```

`slots[get_slot_key(request)]` raises `KeyError` inside `process_exception`; `delay_used_s` is
non-nullable. With rule-17 delays and cross-host concurrency, a host idle >120s mid-crawl is
ordinary. Fix (failure lines only):

```python
slot = downloader.slots.get(get_slot_key(request))
delay_used_s = slot.delay if slot is not None else settings.getfloat("DOWNLOAD_DELAY")
```

with the negative example: **this does NOT mean `.get()` on a response line** — there the subscript
is correct and a `.get()` would hide a real bug. (The fallback is the configured floor that would
have applied — a true statement about policy, not a synthesized wire value.)

## Mechanical

### U6 — Redirect-then-transport-death: two universal chain rules disagree

The one-expression rule (`redirect_urls + [request.url]`) and the failure-line parenthetical
(`[url_requested]`, requested) both claim universality. Probed: a request that timed out after a
301 **does** carry `redirect_urls: ["/a"]` in meta at `process_exception` — so the one-expression
rule is implementable and wins. Fix: the failure-line parenthetical becomes "from the same one
expression as every other entry", with "**this does NOT mean a failure line's chain is always one
element** — that is only the no-redirect case the sample shows."

### U7 — The fetch-policy fallback has three reachable moments, not two, and the `process_exception` bullet omits `fetch_policy` entirely

Probed: at the robots request's own `process_exception`, `robots_info` is empty (`_robots_error`
runs after). Both enumerated moments are worded as *responses*. (Finder's KeyError consequence
corrected: the failure sample already shows `fetch_policy` in fallback shape; the defect is the
count and the response-scoping.) Fix: "exactly **three** reachable moments … the robots.txt fetch's
own entry — response or failure line alike …", and the `process_exception` bullet gains
"`fetch_policy` built by the same rules as a response line — live slot delay (via U5's `.get()`)
plus `robots_info`, or the fallback".

### U8 — The two schema samples contradict the `prior_fetch_ref` rule side by side

Both samples use `https://example.com/pricing`; the failure sample is stamped 30 seconds after the
200 sample yet shows `prior_fetch_ref: null` where the unconditional rule ("most recent prior 2xx
of the same `url_requested`") says `2cf24dba…`. Reading A is what the field exists for — a recheck
diffs "unreachable as of <date>" against last-known bytes. Fix: state "this holds on failure lines
too"; change the failure sample's URL to one with no printed history (the smaller edit).

### U9 — A guard-legal non-URL seed row silently voids the rest of the queue

Task 1 blesses non-URL `url` cells ("narrowing that is task 2's problem"); task 2 never narrows;
`scrapy.Request(bad)` raises `ValueError` inside `async def start()`, killing the generator. Probed:

```
ERROR: Error while reading start items and requests: Missing scheme in request url: …
HITS: ['/good1']   finish_reason: finished   exit 0     <- /good2 never fetched, never mentioned
```

(Finder corrected: Scrapy logs one ERROR naming the bad URL; what is silent is the loss of every
*later* seed — durable, since dropped seeds never enter the frontier.) "Never start a partial crawl
from a malformed queue" is scoped by its own sentence to `SeedFormatError`; task 5's "startup
error" label is contradicted by task 6's "four startup failures". Fix: the CLI validates every seed
URL (`urlparse` scheme in `{http, https}`, non-empty netloc) after `read_seeds`, before the
crawler; failing row → exit 2, message `seed url is not fetchable` + the row; "four startup
failures" becomes five; gated `test_non_url_seed_exits_2_before_any_request`.

### U10 — "Crash the run" on a manifest schema violation is unimplementable as written

Probed three ways: a raise from `process_response` is caught as that request's download error
(crawl continues, exit 0); `CloseSpider` from a downloader middleware is **swallowed the same way**;
`crawler.engine.close_spider(spider, "manifest-schema-violation")` + re-raise **works** —
`finish_reason: manifest-schema-violation`, readable from stats after the reactor stops, so the CLI
can exit **1**. T18's exit-0 sentence needs the scope note ("scoped to runs with no schema
violation"). Gated `test_manifest_schema_violation_exits_nonzero`.

### U11 — The T6 regression test is order-dependent: driven 15-first it cannot fail

Probed all four combinations: `memo=slotkey order=[15,7] → delay=15.0` — green against the defect it
names. (And the "assert both netlocs in `robots_info`" alternative was *disproven*: `_parse_robots`
is the superclass's, keyed by netloc — identical under the defect.) Fix: one clause — "Drive robots
for P1 (7) FIRST, then P2 (15); order is load-bearing (probed)."

### U12 — "Unusable robots response" is undefined, and the spec's own fence already picks a side

No parse-side predicate exists (the plan's own probe: garbage parses fine), and the superclass
hands a 404 body to `_parse_robots` unconditionally (probed: 404 HTML → digest recorded, allow-all
as a side effect of parsing HTML into no rules). The Step-2 fence hashes `response.body`
unconditionally — Reading A — while the 6a prose asks for nulls that nothing can produce. Fix:
"a delivered robots response is always recorded with its digest, whatever its status; the `None`
digest has exactly one producer — `_robots_error`, where no response exists at all", and the two
`str|None` comments updated to say so.

### U13 — "Assert zero wire responses" against a closed port is vacuous

No server is bound, so the hit counter can never advance — true of any implementation, including
one that fetches nothing. Also probed: a socket held **bound-but-not-listening times out**
(`failure.class "timeout"`, not `"connection-refused"`) — bind-then-close is the only fixture
yielding the class the test names; and the port-reuse race did not reproduce in 200 ephemeral
binds. Fix: assert the **manifest** — exactly 5 failure lines (1 robots + 4 page, `retry ×3,
blocked`, all `http_status: null`, class `connection-refused`) and `<cache-root>/sha256/` empty.

### U14 — The errback's deferral is honestly unenforceable — say so, and note what *is* caught

`backoff_delay` is full jitter (lower bound 0 for every attempt) and the measured scheduling floor
is ~0.6s at `DOWNLOAD_DELAY = 0`, so no wall-clock assertion can be sound and discriminating
without an injectable `rand` the plan does not specify. (Finder corrected: "observationally
identical" was too strong — the naive defect, returning a bare `Deferred` from the errback, loses
the retry entirely: probed 1 attempt instead of 4, which the existing `attempt_n` 1–4 assertion
catches.) Fix: the verifier's scope-note paragraph in item 7a — a review obligation, stated, not a
manufactured test.

### U15 — Task 6's "Restated in full" Consumes block omits the two task-4 functions item 7a calls

The local pattern (task 5 restates all three) makes the break real; the finder's misuse reading was
refuted (item 7a pins the call verbatim), so what is genuinely missing is the return type
(`Disposition`, needed for `is Disposition.RETRY`) and the `max_attempts` default. Fix: extend the
block with `FAILURE_CLASSES`, `failure_class_for`, `classify_failure` signatures.

### U16 — The nine-name comment ban is enforced for one name; `record.py` is unguarded for eight

Prose: package-wide, nine names, even in comments. Checks: `validators_sent` file-scoped to
`manifest.py`, `conditional_hit` and five others unchecked anywhere, only `normalized_content_sha256`
recursive. Fix (verified `bash -n` clean, red against a `simhash64` in `record.py`, green on a
clean tree):

```
! grep -rqE 'validators_sent|conditional_hit|normalized_content_sha256|normalized_char_count|simhash64|source_class|change_class|extractor' fetcher/evidence_fetch/
```

# Negative space

**18 deduped candidates → 16 confirmed, 2 refuted; 6 finder overstatements corrected by
counter-probe.** Translator diff: zero structural divergences across ~230 keyed assertions from two
full-coverage readers — the second consecutive silent round.

### Refuted

| Candidate | Refuted because |
|---|---|
| The robots failure line's disposition (retry-forever vs blocked) | Pinned: *"`disposition` on a failure line comes from `classify_failure(class, zero_based)`, never `classify_status`"* — one legal reading (`retry`). The T17 analogy does not carry: `/robots.txt` is not a seed, holds no absence claim, and is re-fetched fresh next run (the parser cache is per-crawl). Optional half-sentence suggested for the worked example, not required |
| `max_attempts` hardcode passes the mutation test | Task 4 is `code-complete` and ships the body verbatim — *"they carry their own code"*; a hardcode is a transcription failure, foreclosed by the executed-fences discipline, and no consumer passes a non-default. Dropped |
| (sub-refutations) | J's misuse reading — item 7a pins the `failure_class_for` call verbatim; K's port-reuse race — 0 reassignments in 200 binds; K's bound-not-listening alternative — yields `timeout`, not `connection-refused` (probed), so it was wrong as an alternative, not just unnecessary |

### Finder overstatements corrected

`append_entry` does not enforce non-nullability (U1 is contradiction, not crash) · the fetch-policy
fallback does apply on the sample (U7 is count/scoping, not KeyError) · Scrapy logs one ERROR for
the bad seed (U9's silence is the *later* seeds) · "observationally identical" errback (U14 — the
lost-retry defect IS caught) · "no message" and "requires foreign cwd" analogues from round 3 did
not recur.

### Verified sound (substrate confirms, one line each)

The full corrected task-3 subclass works end-to-end in a real crawl (7.0 applied, `robots_info`
digest+timestamp populated) · task-2 + task-4 fences execute **24/24**, and mutations kill: dropping
403 from the ignore list and un-blocking `classify_failure` each fail their named test · all four
transport exception names as pinned (`CannotResolveHostError`, `DownloadConnectionRefusedError`,
`DownloadTimeoutError`, `DownloadFailedError`+SSL) and `failure_class_for` maps each · robots
`IgnoreRequest` reaches the recorder's `process_exception` at 1000 · dns-dead host fails robots and
page both · the errback receives `failure.request`, and `failure.request.replace(dont_filter=True,
meta={…, attempt_n: 2})` works · the dns-dead worked example measured exactly: **5 failure lines**,
robots not refetched per retry · robots-request meta is exactly the four scrapy keys (the
`meta.get` defaults are load-bearing as pinned) · Title-case header normalization re-confirmed ·
`uv --project` cwd-relativity re-confirmed · a completed `CrawlerProcess` run exits 0 with no CLI
arrangement · `downloader._get_slot(request)` exists and mints; `from_crawler` needs
`ROBOTSTXT_OBEY: True` (the harness supplies it) · checks matrix: every sharp check green on the
shipped tree and red on its named defect (the `async def start` positive alone would pass on
`async def start_requests` — the negative pair member is what adjudicates, by design).

# Recommended disposition

U1 and U2 are the operator's; both have a recommended side with the plan's own rationale behind it.
U3+U4 are one fix session in one file, with the corrected fences already probed green in the
verifier transcripts — including the false "(probed)" parenthetical to retract. U5–U16 are
mechanical spec edits; every rewrite above was executed before being proposed. The pattern is now
four rounds deep: **the defect rate lives in the newest fixes, and only execution sees it** — the
probe-first discipline is necessary but not sufficient; probes of the fix's *fences as shipped*
(U3, U4) are the remaining gap, i.e. transcribe-and-run the amended fence, not just the idea behind
it.

**Do not implement before U3–U5 are resolved; ratification also wants U1 and U2 decided and
recorded in the decision log.**
