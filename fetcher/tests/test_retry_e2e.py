import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DRIVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_crawl.py")

ROBOTS_BODY = b"User-agent: *\nAllow: /\n"
CHALLENGE_BODY = b"<html>WAF says no</html>"
REAL_BODY = b"<html>the actual page</html>"
MAINTENANCE_BODY = b"<html>down for maintenance</html>"


class RetryHandler(BaseHTTPRequestHandler):
    # path -> list of (status, body, extra_headers); the last script entry
    # repeats once the list is exhausted.
    scripts: dict[str, list[tuple[int, bytes, dict]]] = {}
    hits: dict[str, list[float]] = {}

    def do_GET(self):
        RetryHandler.hits.setdefault(self.path, []).append(time.monotonic())
        if self.path == "/robots.txt":
            status, body, extra = 200, ROBOTS_BODY, {}
        else:
            script = RetryHandler.scripts[self.path]
            index = min(len(RetryHandler.hits[self.path]) - 1, len(script) - 1)
            status, body, extra = script[index]
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        for name, value in extra.items():
            self.send_header(name, value)
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


class RetryEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), RetryHandler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        RetryHandler.hits = {}
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = self._tmp.name
        self.cache_root = os.path.join(self.tmp, "cache")
        self.manifest = os.path.join(self.tmp, "manifest.jsonl")

    def crawl(self, paths: list[str], download_delay: float = 0.0):
        seeds = write_seeds(self.tmp, [f"{self.base}{p}" for p in paths])
        proc = subprocess.run(
            [sys.executable, "-P", DRIVER, seeds, self.cache_root,
             self.manifest, str(download_delay)],
            capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            raise AssertionError(f"crawl failed:\n{proc.stderr[-4000:]}")
        with open(self.manifest, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh.read().splitlines()]

    def lines_for(self, lines: list[dict], path: str) -> list[dict]:
        return [e for e in lines if e["url_requested"].endswith(path)]

    def assert_cached(self, entry: dict, body: bytes):
        full = os.path.join(self.cache_root, entry["cache_relpath"])
        with open(full, "rb") as fh:
            self.assertEqual(fh.read(), body)
        self.assertEqual(entry["raw_bytes_sha256"],
                         hashlib.sha256(body).hexdigest())

    def test_403_then_200_yields_two_entries_and_the_body_is_cached(self):
        # THE composed R2+R3+R4 regression: red if the callback never sees the
        # 403 (HttpError drop), if the dupefilter eats the retry, or if the
        # retry is answered from the HTTP cache (one wire hit, one entry).
        RetryHandler.scripts = {"/target": [
            (403, CHALLENGE_BODY, {}),
            (200, REAL_BODY, {}),
        ]}
        lines = self.crawl(["/target"])
        self.assertEqual(len(RetryHandler.hits["/target"]), 2)  # TWO wire hits
        target = self.lines_for(lines, "/target")
        self.assertEqual([e["attempt_n"] for e in target], [1, 2])
        self.assertEqual([e["disposition"] for e in target], ["retry", "ok"])
        self.assertEqual([e["http_status"] for e in target], [403, 200])
        self.assert_cached(target[0], CHALLENGE_BODY)   # the WAF page is evidence
        self.assert_cached(target[1], REAL_BODY)

    def test_503_reaches_the_recorder_and_is_cached(self):
        # A3 plus the worked example: a 503-forever host takes exactly 4
        # attempts (classify blocks when zero_based >= 3, i.e. on the 4th),
        # every one on the wire (R4), every body cached.
        RetryHandler.scripts = {"/status": [(503, MAINTENANCE_BODY, {})]}
        lines = self.crawl(["/status"])
        self.assertEqual(len(RetryHandler.hits["/status"]), 4)
        status_lines = self.lines_for(lines, "/status")
        self.assertEqual([e["attempt_n"] for e in status_lines], [1, 2, 3, 4])
        self.assertEqual([e["disposition"] for e in status_lines],
                         ["retry", "retry", "retry", "blocked"])
        for entry in status_lines:
            self.assertEqual(entry["http_status"], 503)
            self.assert_cached(entry, MAINTENANCE_BODY)

    def test_retry_after_header_defers_the_retry(self):
        # T5/F5: the only instrument that can see a deferred retry. The header
        # (3s) must EXCEED the slot delay (1s) or the test proves nothing.
        RetryHandler.scripts = {"/ra": [
            (403, CHALLENGE_BODY, {"Retry-After": "3"}),
            (200, REAL_BODY, {}),
        ]}
        lines = self.crawl(["/ra"], download_delay=1.0)
        hits = RetryHandler.hits["/ra"]
        self.assertEqual(len(hits), 2)
        # 2.95 not 3.0: same ms-jitter tolerance as the crawl-delay wall-clock
        # test; an unhonoured header paces at the 1.0s slot delay.
        self.assertGreaterEqual(hits[1] - hits[0], 2.95)
        ra_lines = self.lines_for(lines, "/ra")
        self.assertEqual([e["disposition"] for e in ra_lines], ["retry", "ok"])
