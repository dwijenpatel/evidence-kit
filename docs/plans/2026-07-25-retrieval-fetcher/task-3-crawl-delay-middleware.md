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
    def robot_parser(self, request, spider): ...   # -> parser or Deferred
scrapy.crawler.Crawler.engine.downloader.slots   # dict[str, Slot]; Slot has .delay
scrapy.utils.httpobj.urlparse_cached(request)    # -> ParseResult
```

Protego's parser, which Scrapy already constructs:

```python
protego.Protego.crawl_delay(user_agent: str) -> float | None
```

## Provides

```python
class CrawlDelayRobotsMiddleware(RobotsTxtMiddleware):
    """RobotsTxtMiddleware that also enforces the Crawl-delay it parses."""

    DEFAULT_DELAY: float   # from settings DOWNLOAD_DELAY
    MAX_DELAY: float       # from settings AUTOTHROTTLE_MAX_DELAY, the 60s ceiling
```

Registered at the same priority the stock middleware occupies, replacing it.

## Behaviour, pinned

1. When a robots.txt parser becomes available for a host, read `crawl_delay(user_agent)`.
2. If it returns a number, set that host's downloader slot delay to
   `min(declared, MAX_DELAY)`.
3. If it returns `None` — no `Crawl-delay` declared — leave the slot at `DEFAULT_DELAY`.
   **This does NOT mean set it to zero.**
4. Never *lower* a slot delay below what is already set. AutoThrottle may have raised it
   because the host is struggling; a declared 1s must not undo that.
5. Allow/disallow behaviour is unchanged — that is the superclass's job and it is correct.

**Worked example.** Host declares `Crawl-delay: 7`, `DOWNLOAD_DELAY = 5.0`,
`AUTOTHROTTLE_MAX_DELAY = 60.0`:

| Host declares | Slot delay before | Slot delay after |
|---|---|---|
| `Crawl-delay: 7` | 5.0 | **7.0** |
| `Crawl-delay: 15` | 5.0 | **15.0** |
| `Crawl-delay: 900` | 5.0 | **60.0** (ceiling) |
| nothing | 5.0 | **5.0** |
| `Crawl-delay: 1` | 12.0 (AutoThrottle raised it) | **12.0** (never lowered) |

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
```

Implement each with the real middleware wired to a `Crawler` built by
`scrapy.utils.test.get_crawler`, then assert on
`crawler.engine.downloader.slots[<host>].delay`.

**One end-to-end timing test**, marked as the slow one, asserting that two requests to a
host declaring `Crawl-delay: 2` are separated by ≥2s wall-clock. Use 2, not 7 — the test
must prove the wiring, and every second of test runtime is paid on every run forever.

## Step 2 — implementation

`fetcher/evidence_fetch/middlewares/crawl_delay.py`. Sketch, with the load-bearing parts
exact:

```python
class CrawlDelayRobotsMiddleware(RobotsTxtMiddleware):
    def __init__(self, crawler):
        super().__init__(crawler)
        self.crawler = crawler
        self.DEFAULT_DELAY = crawler.settings.getfloat("DOWNLOAD_DELAY", 5.0)
        self.MAX_DELAY = crawler.settings.getfloat("AUTOTHROTTLE_MAX_DELAY", 60.0)
        self._applied: set[str] = set()      # netlocs already adjusted

    def _apply_delay(self, netloc, parser):
        if netloc in self._applied:
            return
        declared = parser.crawl_delay(self._robotstxt_useragent
                                      or self.crawler.settings["USER_AGENT"])
        self._applied.add(netloc)
        if declared is None:
            return                            # keep DOWNLOAD_DELAY; do NOT zero it
        slot = self.crawler.engine.downloader.slots.get(netloc)
        if slot is None:
            return
        slot.delay = max(slot.delay, min(float(declared), self.MAX_DELAY))
```

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
| robots.txt unreachable or malformed | Fall back to `DEFAULT_DELAY`; **never** treat an unreadable robots.txt as "no rules" |
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
! grep -rn 'http://\(?!127\.0\.0\.1\)' fetcher/tests/ || true
uv run --project fetcher python -m unittest discover -s fetcher/tests -t fetcher -q
```

## Regression value

`test_declared_delay_is_applied_to_the_slot` is the highest-value test in the project. If a
future Scrapy upgrade moves the seam this middleware attaches to, that test fails and the
fetcher goes back to hammering hosts silently. **Do not weaken it to make an upgrade
pass.**
