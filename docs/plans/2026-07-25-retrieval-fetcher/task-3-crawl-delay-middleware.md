# Task 3 — `Crawl-delay`-honouring robots middleware

**Tier:** `contract` · **PRD criteria:** A1

*(Tier chosen deliberately: the **behaviour** below is fully pinned by the table in
"Behaviour, pinned", but the seam this middleware attaches to inside `RobotsTxtMiddleware`
differs across Scrapy versions and must be read from the installed source. Prescribing it
here would be guessing — which is the failure `contract` exists to prevent.)*

**This is the single mandatory adaptation in the whole project.** Scrapy parses
`Crawl-delay` through Protego and then discards it, which is precisely the defect that
produced the incident this project exists to fix: an agent recorded a hard 403 across ten
hosts for a document that returned 200 to one polite request.

Verified twice — by the research pass and again independently:

```
files in scrapy 2.17.0 mentioning crawl_delay: 0
DOWNLOAD_DELAY = 0                                    (settings/default_settings.py)
robotstxt.py:74  →  if not rp.allowed(request.url, useragent):
protego/_protego.py:225  →  def crawl_delay(self, user_agent) -> float | None:
```

Measured effect: AutoThrottle settled at **626 ms** against a server declaring
`Crawl-delay: 7`. arxiv.org declares **15s**.

## Files

| Path | Responsibility |
|---|---|
| `fetcher/evidence_fetch/middlewares/__init__.py` (new) | Empty package marker |
| `fetcher/evidence_fetch/middlewares/crawl_delay.py` (new) | The subclass |
| `fetcher/evidence_fetch/settings.py` (modify) | Register it in `DOWNLOADER_MIDDLEWARES` |
| `fetcher/tests/test_crawl_delay.py` (new) | Tests, against a local server |

## Consumes

From Scrapy, as installed (read the installed version; do not trust this restatement alone):

```python
scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware
    def process_request(self, request, spider): ...
    async def robot_parser(self, request): ...     # awaitable; NO spider argument
                                                   # (verified against scrapy 2.17.0)
scrapy.crawler.Crawler.engine.downloader.slots   # dict[str, Slot]; Slot has .delay
scrapy.crawler.Crawler.engine.downloader.get_slot_key(request)  # -> str; THE slot
                                                 # dict's key function (see below)
scrapy.utils.httpobj.urlparse_cached(request)    # -> ParseResult
```

**Two dicts, two key functions — pinned (plan-review R1).** The downloader's slot dict is
keyed by `get_slot_key(request)`: `meta["download_slot"]` if set, else
`urlparse_cached(request).hostname or ""` — **port stripped** (probed, 2.17.0).
`robots_info` is keyed by **netloc** (host:port), matching how Scrapy keys its robots
parsers and builds the robots URL. Concretely, for `http://127.0.0.1:60127/a`:

| Dict | Key |
|---|---|
| `downloader.slots` | `"127.0.0.1"` |
| `crawler.robots_info` | `"127.0.0.1:60127"` |

Every slot lookup in this task and in task 5 goes through `get_slot_key(request)`.
`slots.get(netloc)` happens to work on ordinary port-80/443 hosts and returns `None` on
**every** CLAUDE.md rule-19 test server — the delay is silently never applied. **This does
NOT mean the two dicts can share a key function.**

**What the robots seam actually hands you (round-3 T1 — this was wrong for three review
rounds):** Scrapy constructs and passes around its wrapper, never bare Protego. The
wrapper's public surface is `allowed()` plus the `rp` attribute; **`crawl_delay` exists
only on `.rp`**:

```python
scrapy.robotstxt.ProtegoRobotParser          # what robot_parser() yields (2.17.0,
    .allowed(url, user_agent) -> bool        #   robotstxt.py:109-123; the default
    .rp: protego.Protego                     #   ROBOTSTXT_PARSER, which task 2 keeps)
        .crawl_delay(user_agent: str) -> float | None
```

`parser.crawl_delay(ua)` raises `AttributeError: 'ProtegoRobotParser' object has no
attribute 'crawl_delay'` (probed live) — and this task's own error model then swallows
it into `DEFAULT_DELAY` with one WARNING, which is A1 failing silently at runtime. The
five gated delay tests catch it at build (5.0 ≠ 7.0); the correct call is
`parser.rp.crawl_delay(ua)` (probed: 7.0).

## Provides

```python
class CrawlDelayRobotsMiddleware(RobotsTxtMiddleware):
    """RobotsTxtMiddleware that also enforces the Crawl-delay it parses."""

    DEFAULT_DELAY: float   # from settings DOWNLOAD_DELAY
    MAX_DELAY: float       # from settings CRAWL_DELAY_CEILING, the 60s ceiling
```

It also maintains, on the crawler object itself:

```python
crawler.robots_info: dict[str, dict]
# netloc -> {"robots_url": str,          # the URL actually fetched
#            "robots_sha256": str|None,  # sha256 of the robots.txt bytes; None if unusable
#            "robots_fetched_at": str|None}  # UTC ISO-8601 ms Z; None if unusable
```

This is the **only** place robots.txt bytes are observable — stock Scrapy hands the body
to Protego and keeps just the parser, so if this middleware does not record the digest at
fetch time, task 5's `fetch_policy` has no producer and A5's "proof this fetch was polite"
is three nulls forever (plan-review F10). The record middleware (task 5) reads this dict;
never a second GET for robots.txt.

Registered at the same priority the stock middleware occupies, replacing it.

## Behaviour, pinned

1. When a robots.txt parser becomes available for a host, read `crawl_delay(user_agent)`.
2. If it returns a number, set that host's downloader slot delay to
   `min(declared, MAX_DELAY)`.
3. If it returns `None` — no `Crawl-delay` declared — leave the slot at `DEFAULT_DELAY`.
   **This does NOT mean set it to zero.**
4. Never *lower* a slot delay below what is already set. A declared 1s must not undo a
   larger delay another component set.
5. Allow/disallow behaviour is unchanged — that is the superclass's job and it is correct.
6a. **When the robots.txt response arrives, record it**: set
   `crawler.robots_info[netloc]` to the fetched URL, the SHA-256 of the response body,
   and the UTC timestamp — before the body is handed to the parser and lost. On an
   unusable robots response, record the URL with `None` for digest and timestamp; the
   entry's presence still says "we asked." **A robots fetch that dies in transport
   (connection refused, DNS failure, timeout) produces no response at all**, so neither
   rule above fires — hook the superclass's error path and record the same shape with
   `None` for digest and timestamp. **`_robots_error(self, exc, netloc)` receives no
   scheme** (round-3 T9 — probed: its locals are `exc, netloc, self`, and an f-string
   naming `scheme` there raises `NameError`). The scheme's last holder is
   `robot_parser(request)`; stash it per netloc before deferring to the superclass:

   ```python
   async def robot_parser(self, request):
       url = urlparse_cached(request)
       # First scheme wins, matching Scrapy's own one-parser-per-netloc keying —
       # its _parsers dict is scheme-less, so an https and an http origin on one
       # host:port already share a parser (probed; a TLS-dead https robots fetch
       # sets that shared parser to None).
       self._scheme_by_netloc.setdefault(url.netloc, url.scheme)
       return await super().robot_parser(request)

   def _robots_error(self, exc, netloc):
       scheme = self._scheme_by_netloc.get(netloc, "http")
       self.crawler.robots_info[netloc] = {
           "robots_url": f"{scheme}://{netloc}/robots.txt",   # netloc: PORT KEPT
           "robots_sha256": None, "robots_fetched_at": None}
       return super()._robots_error(exc, netloc)
   ```

   **This does NOT mean hardcode `http://`** — that names a different origin on every
   https host. Without this entry, every page recorded on that host falls to task 5's
   fallback and the manifest loses "we asked." (Plan-review R6, corrected by T9.)
6. **The delay persists for the life of the crawl.** Nothing else may write `slot.delay`;
   task 2 disables AutoThrottle for exactly this reason. **This does NOT mean the delay is
   re-applied per response** — it is set once, and the guarantee comes from no other
   component overwriting it. A regression test asserts the value survives N responses.

**Worked example.** Host declares `Crawl-delay: 7`, `DOWNLOAD_DELAY = 5.0`,
`CRAWL_DELAY_CEILING = 60.0`:

| Host declares | Slot delay before | Slot delay after |
|---|---|---|
| `Crawl-delay: 7` | 5.0 | **7.0** |
| `Crawl-delay: 15` | 5.0 | **15.0** |
| `Crawl-delay: 900` | 5.0 | **60.0** (ceiling) |
| nothing | 5.0 | **5.0** |
| `Crawl-delay: 1` | 12.0 (set by another component) | **12.0** (never lowered) |
| `Crawl-delay: 7`, then 10 further responses | 7.0 | **7.0** (does not decay) |

The 900 → 60 row is the one to get right: a host asking for 15 minutes is telling us it
does not want casual automated traffic, and the correct response is to stop and look for an
official API or bulk export — not to grind at 15-minute intervals. The ceiling makes that
visible instead of silently slow.

## Step 1 — the failing test

`fetcher/tests/test_crawl_delay.py`. The server is local (CLAUDE.md rule 19): no network,
deterministic, and `Crawl-delay` is directly constructible.

```python
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROBOTS = b"User-agent: *\nCrawl-delay: 7\nDisallow: /private\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/robots.txt":
            body = ROBOTS
        else:
            body = b"<html>ok</html>"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class LocalServer:
    def __enter__(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()

    def url(self, path="/"):
        return f"http://127.0.0.1:{self.port}{path}"
```

Then the assertions. Each drives the middleware directly rather than running a full crawl,
so the test is fast and asserts the delay rather than timing it:

```python
class CrawlDelayTests(unittest.TestCase):
    def test_declared_delay_is_applied_to_the_slot(self): ...
        # expect slot.delay == 7.0

    def test_delay_is_capped_at_max(self): ...
        # robots declaring 900 -> slot.delay == 60.0

    def test_absent_delay_leaves_the_default(self): ...
        # robots with no Crawl-delay -> slot.delay == 5.0, NOT 0

    def test_existing_higher_delay_is_never_lowered(self): ...
        # slot.delay pre-set to 12.0, robots declares 1 -> stays 12.0

    def test_disallowed_path_is_still_blocked(self): ...
        # /private raises IgnoreRequest, proving the superclass still works

    def test_delay_survives_ten_responses(self): ...
        # robots declares 7; drive 10 responses through the downloader; assert
        # slot.delay is still 7.0 at the end. THIS IS THE F1 REGRESSION TEST:
        # with AUTOTHROTTLE_ENABLED = True it reads 5.0 after the first 200.

    def test_robots_info_records_url_digest_and_time(self): ...
        # after robots.txt resolves for a host, crawler.robots_info[netloc] has the
        # fetched URL, sha256 of ROBOTS, and an ISO-8601 Z timestamp (F10)

    def test_slot_created_after_robots_still_gets_the_delay(self): ...
        # call _apply_delay when slots has no entry for the host, THEN create the
        # slot and call again -> slot.delay == 7.0. THIS IS THE F3 REGRESSION
        # TEST: with `_applied.add` before the slot lookup it stays at 5.0.

    def test_slot_key_is_hostname_not_netloc(self): ...
        # against the 127.0.0.1:<port> server, after robots resolves:
        #   key = downloader.get_slot_key(request)
        #   assertEqual(key, "127.0.0.1")
        #   assertIn(key, downloader.slots)
        #   assertNotIn(f"127.0.0.1:{port}", downloader.slots)
        #   assertEqual(downloader.slots[key].delay, 7.0)   # <- the discriminating one
        # THIS IS THE R1 REGRESSION TEST — and only the delay assertion can fail on
        # R1 (round-3 T12): the first three are facts about the DOWNLOADER, probed
        # green against a middleware whose own lookup is slots.get(netloc) with the
        # slot left at 5.0. Dropping the delay line leaves a regression test that
        # cannot fail.

    def test_second_port_on_one_hostname_still_applies_its_delay(self): ...
        # two servers, 127.0.0.1:P1 declaring Crawl-delay: 7 and 127.0.0.1:P2
        # declaring 15 — one shared slot key. Drive robots for both; assert the
        # shared slot ends at 15.0. THIS IS THE T6 REGRESSION TEST: memoized on
        # the slot key instead of netloc it reads 7.0, the 15 silently discarded.

    def test_robots_transport_failure_records_url_with_nulls(self): ...
        # bind a socket, note the port, close it; seed an HTTPS url on that port
        # (https to a closed port fails in transport before any TLS — no certs
        # needed). After the robots fetch errors, robots_info[netloc] ==
        # {"robots_url": f"https://{netloc}/robots.txt", "robots_sha256": None,
        #  "robots_fetched_at": None}  (R6/T9 — https-schemed on purpose: an
        # implementation that hardcodes "http://" fails here; the stashed scheme
        # is the only thing that can produce "https://")
```

**The harness (round-3 T2 — the previously prescribed one cannot work):**
`scrapy.utils.test.get_crawler()` returns a crawler whose `.engine` is `None` — it is
assigned only inside `crawl()` — so `crawler.engine.downloader` raises
`AttributeError` before any assertion runs (probed; every test above died on it as
previously specified). For the unit tests, build the downloader yourself and inject it:

```python
install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")
crawler = get_crawler(Spider, {"DOWNLOAD_DELAY": 5.0, "CRAWL_DELAY_CEILING": 60.0,
                               "ROBOTSTXT_OBEY": True, "AUTOTHROTTLE_ENABLED": False})
crawler.spider = crawler.spidercls.from_crawler(crawler, name="t")
downloader = Downloader(crawler)                            # needs crawler.spider
crawler.engine = SimpleNamespace(downloader=downloader)     # the one injection
downloader._get_slot(request)                               # mint the slot
mw = CrawlDelayRobotsMiddleware.from_crawler(crawler)
# ... drive robots, then assert on
# downloader.slots[downloader.get_slot_key(request)].delay   (probed: 5.0 -> 7.0)
```

`test_delay_survives_ten_responses` and the wall-clock test need real traffic instead:
run a crawl (`CrawlerProcess`) against the local server and read
`self.crawler.engine.downloader.slots[key].delay` from inside a spider callback, where
`crawler.engine` is real (probed). The key always comes from `get_slot_key`, never from
the URL's netloc (R1).

**One end-to-end timing test** — `test_wall_clock_gap_honours_crawl_delay`, marked as the
slow one: run it with `DOWNLOAD_DELAY = 1.0` against a host declaring `Crawl-delay: 3`,
and assert two requests are separated by ≥3s wall-clock.

**The declared delay must exceed `DOWNLOAD_DELAY` or the test proves nothing.** The original
version used `Crawl-delay: 2` against `DOWNLOAD_DELAY = 5.0`: the middleware computes
`max(5.0, 2.0) = 5.0`, so the ≥2s assertion holds even if the middleware never runs. Lowering
`DOWNLOAD_DELAY` for this test keeps it discriminating at 3s of runtime instead of 8.

## Step 2 — implementation

`fetcher/evidence_fetch/middlewares/crawl_delay.py`. Sketch, with the load-bearing parts
exact:

```python
class CrawlDelayRobotsMiddleware(RobotsTxtMiddleware):
    def __init__(self, crawler):
        super().__init__(crawler)
        self.crawler = crawler
        self.DEFAULT_DELAY = crawler.settings.getfloat("DOWNLOAD_DELAY", 5.0)
        self.MAX_DELAY = crawler.settings.getfloat("CRAWL_DELAY_CEILING", 60.0)
        self._applied: set[str] = set()      # netlocs whose delay is now set
        crawler.robots_info = {}             # netloc -> robots provenance (task 5 reads)

    def _apply_delay(self, request, parser):
        downloader = self.crawler.engine.downloader
        netloc = urlparse_cached(request).netloc  # the MEMO key: host:port (T6)
        if netloc in self._applied:
            return
        key = downloader.get_slot_key(request)   # the slot LOOKUP key: hostname, port
                                                 # stripped — NEVER the netloc (R1)
        # Look the slot up FIRST. Marking a netloc applied before we have a slot
        # strands it forever: the guard above returns on every later call and the
        # declared delay is never applied. (Plan-review F3.)
        slot = downloader.slots.get(key)
        if slot is None:
            return                            # NOT marked; retried on the next request
        try:
            # .rp, not the wrapper: Scrapy hands ProtegoRobotParser around, and only
            # its .rp (the Protego instance) has crawl_delay. `parser.crawl_delay(...)`
            # raises AttributeError, which the except below would swallow into
            # DEFAULT_DELAY forever — A1 dead with one WARNING as the trace (round-3
            # T1, probed live: slot stayed 5.0 against a declared 7).
            declared = parser.rp.crawl_delay(self._robotstxt_useragent
                                             or self.crawler.settings["USER_AGENT"])
        except Exception:
            logger.warning("crawl_delay lookup failed for %s; using DEFAULT_DELAY",
                           netloc)
            declared = None
        self._applied.add(netloc)             # a slot existed: this origin is settled
        if declared is None:
            return                            # keep DOWNLOAD_DELAY; do NOT zero it
        slot.delay = max(slot.delay, min(float(declared), self.MAX_DELAY))
```

**The memo is keyed by netloc; the slot lookup by `get_slot_key`. They must differ**
(round-3 T6): two rule-19 servers `127.0.0.1:P1` (`Crawl-delay: 7`) and `127.0.0.1:P2`
(`Crawl-delay: 15`) share the slot key `"127.0.0.1"`. Memoized on the slot key, the
second server's robots is parsed and its 15 **silently never read** — probed live:
final delay 7.0; memoized on netloc, both apply and the shared slot ends at the max,
15.0, per rule 4. **This does NOT mean the slot lookup may use netloc** — that is R1,
the opposite defect.

Where the robots.txt *response* is observable (the seam differs by version — in 2.17 it
is the callback the superclass attaches to its own robots request), add:

```python
crawler.robots_info[netloc] = {
    "robots_url": response.url,
    "robots_sha256": hashlib.sha256(response.body).hexdigest(),
    "robots_fetched_at": now_iso_ms_z(),
}
```

**Why the one-shot memo is now safe.** It was not, before: `AUTOTHROTTLE_ENABLED = True`
rewrote `slot.delay` on every response with a global floor of `DOWNLOAD_DELAY`, so a per-host
7.0 was dragged to 5.0 by the first 200 and this middleware never re-asserted it. Task 2 now
sets `AUTOTHROTTLE_ENABLED = False`, so **nothing else writes `slot.delay`** and a single
assignment holds for the life of the crawl. If AutoThrottle is ever re-enabled, this memo must
go and the delay must be re-asserted per response — the two designs are not compatible.

Hook `_apply_delay` where the parser for a host first becomes available. Read the installed
`RobotsTxtMiddleware` to find the right seam — it differs across Scrapy versions, and
guessing it from this document would be exactly the failure mode `contract` tier exists to
avoid. The behaviour above is the contract; the attachment point is the implementer's call,
and whichever seam is chosen must be covered by `test_declared_delay_is_applied_to_the_slot`.

The `_applied` set exists because `crawl_delay()` is cheap but the slot lookup runs per
request; recomputing per request would also re-raise a delay AutoThrottle had deliberately
lowered.

## Step 3 — register it

In `settings.py`, add:

```python
DOWNLOADER_MIDDLEWARES = {
    "scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware": None,
    "evidence_fetch.middlewares.crawl_delay.CrawlDelayRobotsMiddleware": 100,
}
```

Setting the stock middleware to `None` is required — without it both run, robots.txt is
fetched twice per host, and the stock one may short-circuit first.

## Error model

| Failure | Behaviour |
|---|---|
| robots.txt unreachable or malformed | Fall back to `DEFAULT_DELAY` for the **delay**; never zero it. **Access is unchanged: the superclass allows the request** (parser `None`, or an empty parse — probed: empty, HTML-garbage, and binary robots bodies all allow everything with `crawl_delay None`). This is a **stated deviation from PRD §6** ("fail closed … never cache 'unreadable' as 'no robots.txt'"): the fetcher fails *open on access* and records "we asked" via the `robots_info` nulls instead of blocking, because a one-fetch-window transport error must not convert into a recorded inability to fetch — the false-absence shape again. The disallow rules that *did* parse are always honoured. (Round-3 T21) |
| `crawl_delay()` raises | Catch, log at `WARNING` with substring `crawl_delay`, fall back to `DEFAULT_DELAY` |
| Slot does not exist yet | Return; the next request for that host creates it and the delay is applied then |

The second row is not hypothetical: a single non-numeric `Crawl-delay` value aborts parsing
of the *entire* robots.txt in Python's stdlib parser (cpython#153404, July 2026). Protego is
not the stdlib parser, but the failure class — one bad line denying every rule on a host —
is worth defending against by construction.

## Checks

```
test -f fetcher/evidence_fetch/middlewares/crawl_delay.py
grep -qF 'CrawlDelayRobotsMiddleware' fetcher/evidence_fetch/settings.py
grep -qF '"scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware": None' fetcher/evidence_fetch/settings.py
grep -qF 'test_absent_delay_leaves_the_default' fetcher/tests/test_crawl_delay.py
grep -qF 'test_existing_higher_delay_is_never_lowered' fetcher/tests/test_crawl_delay.py
grep -qF 'test_delay_is_capped_at_max' fetcher/tests/test_crawl_delay.py
grep -qF 'test_declared_delay_is_applied_to_the_slot' fetcher/tests/test_crawl_delay.py
grep -qF 'test_delay_survives_ten_responses' fetcher/tests/test_crawl_delay.py
grep -qF 'test_slot_created_after_robots_still_gets_the_delay' fetcher/tests/test_crawl_delay.py
grep -qF 'test_slot_key_is_hostname_not_netloc' fetcher/tests/test_crawl_delay.py
grep -qF 'test_second_port_on_one_hostname_still_applies_its_delay' fetcher/tests/test_crawl_delay.py
grep -qF 'test_robots_transport_failure_records_url_with_nulls' fetcher/tests/test_crawl_delay.py
grep -qF 'test_disallowed_path_is_still_blocked' fetcher/tests/test_crawl_delay.py
grep -qF 'test_wall_clock_gap_honours_crawl_delay' fetcher/tests/test_crawl_delay.py
grep -qF 'CRAWL_DELAY_CEILING' fetcher/evidence_fetch/middlewares/crawl_delay.py
grep -qF 'get_slot_key' fetcher/evidence_fetch/middlewares/crawl_delay.py
grep -qF 'rp.crawl_delay' fetcher/evidence_fetch/middlewares/crawl_delay.py
grep -qF 'robots_info' fetcher/evidence_fetch/middlewares/crawl_delay.py
grep -qF 'test_robots_info_records_url_digest_and_time' fetcher/tests/test_crawl_delay.py
! grep -qF 'AUTOTHROTTLE_MAX_DELAY' fetcher/evidence_fetch/middlewares/crawl_delay.py
uv run --project fetcher python -m unittest discover -s fetcher/tests -t fetcher -q
```

Every test named in this spec's prose is gated by a name grep above (#11) — a listed test
that is never written must fail a check, not fade into the suite silently.
`grep -qF 'rp.crawl_delay'` is the T1 tripwire: the wrapper has no `crawl_delay`, so the
call must go through `.rp`. And `crawl_delay.py` must not contain the string
`AUTOTHROTTLE_MAX_DELAY` **even in a comment** — that check is unanchored `-F` (round-3
T19); the rejected-name rationale lives in `settings.py` and plan.md Amendment 1, not
here.

## Regression value

`test_declared_delay_is_applied_to_the_slot` is the highest-value test in the project. If a
future Scrapy upgrade moves the seam this middleware attaches to, that test fails and the
fetcher goes back to hammering hosts silently. **Do not weaken it to make an upgrade
pass.**
