import asyncio
import hashlib
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

from scrapy import Request, Spider
from scrapy.core.downloader import Downloader
from scrapy.exceptions import IgnoreRequest
from scrapy.http import Response
from scrapy.robotstxt import ProtegoRobotParser
from scrapy.utils.reactor import install_reactor
from scrapy.utils.test import get_crawler

from evidence_fetch.middlewares.crawl_delay import CrawlDelayRobotsMiddleware

ROBOTS = b"User-agent: *\nCrawl-delay: 7\nDisallow: /private\n"
PROBE_DRIVER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "_crawl_delay_probe.py")
ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def make_harness(robots_by_netloc: dict[str, bytes] | None = None,
                 robots_body: bytes = ROBOTS,
                 transport_error: Exception | None = None):
    """The T2 harness: get_crawler().engine is None, so build the downloader
    and the robots transport seam ourselves. NOT asyncio.run — it closes the
    loop and the next Downloader(crawler) dies in _start_slot_gc."""
    install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")
    loop = asyncio.get_event_loop_policy().get_event_loop()
    asyncio.set_event_loop(loop)
    crawler = get_crawler(Spider, {
        "DOWNLOAD_DELAY": 5.0, "CRAWL_DELAY_CEILING": 60.0,
        "ROBOTSTXT_OBEY": True, "AUTOTHROTTLE_ENABLED": False,
        "USER_AGENT": "evidence-fetch/0.1 (+mailto:t@example.invalid)",
    })
    crawler.spider = crawler.spidercls.from_crawler(crawler, name="t")
    downloader = Downloader(crawler)

    async def download_async(robotsreq):
        if transport_error is not None:
            raise transport_error
        if robots_by_netloc is not None:
            from urllib.parse import urlparse
            body = robots_by_netloc[urlparse(robotsreq.url).netloc]
        else:
            body = robots_body
        return Response(robotsreq.url, status=200, body=body, request=robotsreq)

    crawler.engine = SimpleNamespace(downloader=downloader,
                                     download_async=download_async)
    middleware = CrawlDelayRobotsMiddleware.from_crawler(crawler)
    return loop, crawler, downloader, middleware


class CrawlDelayUnitTests(unittest.TestCase):
    def drive(self, loop, downloader, middleware, url: str):
        request = Request(url)
        downloader._get_slot(request)               # mint the slot
        loop.run_until_complete(middleware.process_request(request))
        return request

    def slot_delay(self, downloader, request) -> float:
        return downloader.slots[downloader.get_slot_key(request)].delay

    def test_declared_delay_is_applied_to_the_slot(self):
        loop, _, downloader, mw = make_harness()
        request = self.drive(loop, downloader, mw, "http://127.0.0.1:60127/a")
        self.assertEqual(self.slot_delay(downloader, request), 7.0)

    def test_delay_is_capped_at_max(self):
        loop, _, downloader, mw = make_harness(
            robots_body=b"User-agent: *\nCrawl-delay: 900\n")
        request = self.drive(loop, downloader, mw, "http://127.0.0.1:60127/a")
        self.assertEqual(self.slot_delay(downloader, request), 60.0)

    def test_absent_delay_leaves_the_default(self):
        loop, _, downloader, mw = make_harness(
            robots_body=b"User-agent: *\nDisallow: /private\n")
        request = self.drive(loop, downloader, mw, "http://127.0.0.1:60127/a")
        self.assertEqual(self.slot_delay(downloader, request), 5.0)

    def test_existing_higher_delay_is_never_lowered(self):
        loop, _, downloader, mw = make_harness(
            robots_body=b"User-agent: *\nCrawl-delay: 1\n")
        request = Request("http://127.0.0.1:60127/a")
        _, slot = downloader._get_slot(request)
        slot.delay = 12.0                           # set by another component
        loop.run_until_complete(mw.process_request(request))
        self.assertEqual(self.slot_delay(downloader, request), 12.0)

    def test_disallowed_path_is_still_blocked(self):
        loop, _, downloader, mw = make_harness()
        request = Request("http://127.0.0.1:60127/private")
        downloader._get_slot(request)
        with self.assertRaises(IgnoreRequest):
            loop.run_until_complete(mw.process_request(request))

    def test_robots_info_records_url_digest_and_time(self):
        loop, crawler, downloader, mw = make_harness()
        self.drive(loop, downloader, mw, "http://127.0.0.1:60127/a")
        info = crawler.robots_info["127.0.0.1:60127"]
        self.assertEqual(info["robots_url"], "http://127.0.0.1:60127/robots.txt")
        self.assertEqual(info["robots_sha256"],
                         hashlib.sha256(ROBOTS).hexdigest())
        self.assertRegex(info["robots_fetched_at"], ISO_Z)

    def test_slot_created_after_robots_still_gets_the_delay(self):
        # F3: marking a netloc applied before a slot exists strands it forever.
        loop, crawler, downloader, mw = make_harness()
        request = Request("http://127.0.0.1:60127/a")
        parser = ProtegoRobotParser.from_crawler(crawler, ROBOTS)
        mw._apply_delay(request, parser)            # no slot yet: must not mark
        self.assertNotIn(downloader.get_slot_key(request), downloader.slots)
        downloader._get_slot(request)
        mw._apply_delay(request, parser)
        self.assertEqual(self.slot_delay(downloader, request), 7.0)

    def test_slot_key_is_hostname_not_netloc(self):
        loop, _, downloader, mw = make_harness()
        port = 60127
        request = self.drive(loop, downloader, mw, f"http://127.0.0.1:{port}/a")
        key = downloader.get_slot_key(request)
        self.assertEqual(key, "127.0.0.1")
        self.assertIn(key, downloader.slots)
        self.assertNotIn(f"127.0.0.1:{port}", downloader.slots)
        self.assertEqual(downloader.slots[key].delay, 7.0)  # the discriminating one

    def test_second_port_on_one_hostname_still_applies_its_delay(self):
        # T6: memoized on the slot key instead of netloc, the second server's 15
        # is parsed and silently never read. Drive 7 FIRST (U11: 15-first is
        # green against the defect this test names).
        loop, _, downloader, mw = make_harness(robots_by_netloc={
            "127.0.0.1:41001": b"User-agent: *\nCrawl-delay: 7\n",
            "127.0.0.1:41002": b"User-agent: *\nCrawl-delay: 15\n",
        })
        first = self.drive(loop, downloader, mw, "http://127.0.0.1:41001/a")
        self.assertEqual(self.slot_delay(downloader, first), 7.0)
        second = self.drive(loop, downloader, mw, "http://127.0.0.1:41002/a")
        self.assertEqual(downloader.slots["127.0.0.1"].delay, 15.0)

    def test_robots_transport_failure_records_url_with_nulls(self):
        # https-schemed on purpose: only the stashed scheme can produce it.
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        loop, crawler, downloader, mw = make_harness(
            transport_error=ConnectionRefusedError("refused"))
        self.drive(loop, downloader, mw, f"https://127.0.0.1:{port}/a")
        netloc = f"127.0.0.1:{port}"
        self.assertEqual(crawler.robots_info[netloc], {
            "robots_url": f"https://{netloc}/robots.txt",
            "robots_sha256": None,
            "robots_fetched_at": None,
        })


class DelayHandler(BaseHTTPRequestHandler):
    robots = b"User-agent: *\nCrawl-delay: 7\n"
    hit_times: dict[str, list[float]] = {}

    def do_GET(self):
        DelayHandler.hit_times.setdefault(self.path, []).append(time.monotonic())
        body = self.robots if self.path == "/robots.txt" else b"<html>ok</html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def write_seeds(dirpath: str, urls: list[str]) -> str:
    rows = "".join(f"| {u} | 2026-07-27 | test | q |\n" for u in urls)
    doc = ("---\ntype: Seeds\ntitle: \"Fetch queue\"\ntimestamp: 2026-07-27\n---\n\n"
           "# Fetch queue\n\n"
           "| url | added | signal | question |\n|---|---|---|---|\n" + rows)
    path = os.path.join(dirpath, "seeds.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return path


def run_probe_crawl(workdir: str, urls: list[str], download_delay: float) -> str:
    seeds = write_seeds(workdir, urls)
    proc = subprocess.run(
        [sys.executable, "-P", PROBE_DRIVER, seeds,
         os.path.join(workdir, "cache"),
         os.path.join(workdir, "manifest.jsonl"), str(download_delay)],
        capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise AssertionError(f"probe crawl failed:\n{proc.stderr[-4000:]}")
    return proc.stdout


class CrawlDelayTrafficTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), DelayHandler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        DelayHandler.hit_times = {}

    def test_delay_survives_ten_responses(self):
        # THE F1 REGRESSION TEST: with AUTOTHROTTLE_ENABLED = True the slot
        # is dragged to the global DOWNLOAD_DELAY floor by the first 200.
        # Declared 0.5 over DOWNLOAD_DELAY 0 discriminates the same way at a
        # runtime of ~5s instead of the ~70s a declared 7 would pace out.
        DelayHandler.robots = b"User-agent: *\nCrawl-delay: 0.5\n"
        urls = [f"{self.base}/p{i}" for i in range(10)]
        with tempfile.TemporaryDirectory() as tmp:
            out = run_probe_crawl(tmp, urls, download_delay=0.0)
        delays = [float(m) for m in re.findall(r"SLOTDELAY ([\d.]+)", out)]
        self.assertEqual(len(delays), 10, out)
        self.assertEqual(delays, [0.5] * 10)

    def test_wall_clock_gap_honours_crawl_delay(self):
        # The slow one. Declared 3 must EXCEED DOWNLOAD_DELAY 1 or the test
        # proves nothing (max(1, 3) == 3 only if the middleware ran).
        DelayHandler.robots = b"User-agent: *\nCrawl-delay: 3\n"
        urls = [f"{self.base}/w1", f"{self.base}/w2"]
        with tempfile.TemporaryDirectory() as tmp:
            run_probe_crawl(tmp, urls, download_delay=1.0)
        t1 = DelayHandler.hit_times["/w1"][0]
        t2 = DelayHandler.hit_times["/w2"][0]
        # 2.95, not 3.0: scrapy schedules exactly 3.0s from lastseen, so an
        # exact >= 3.0 against server-side arrival times flakes on ms-level
        # timer jitter (measured: 2.9992s). A broken middleware paces at the
        # slot's 1.0s, so the tolerance still discriminates by ~2s.
        self.assertGreaterEqual(abs(t2 - t1), 2.95)
