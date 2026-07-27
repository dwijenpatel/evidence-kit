import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DRIVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_crawl.py")

RESPONSE_UNIT = (
    "http_status", "response_protocol", "raw_bytes_sha256", "raw_bytes_length",
    "cache_relpath", "content_type", "response_headers", "etag", "etag_is_weak",
    "last_modified",
)


class DisallowHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/robots.txt":
            body = b"User-agent: *\nDisallow: /private\n"
        else:
            body = b"<html>ok</html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
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


class FailureLineTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = self._tmp.name
        self.cache_root = os.path.join(self.tmp, "cache")
        self.manifest = os.path.join(self.tmp, "manifest.jsonl")

    def crawl(self, urls: list[str]):
        seeds = write_seeds(self.tmp, urls)
        proc = subprocess.run(
            [sys.executable, "-P", DRIVER, seeds, self.cache_root, self.manifest],
            capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            raise AssertionError(f"crawl failed:\n{proc.stderr[-4000:]}")
        with open(self.manifest, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh.read().splitlines()]

    def assert_failure_shape(self, entry: dict, failure_class: str):
        for key in RESPONSE_UNIT:
            self.assertIsNone(entry[key], key)
        self.assertEqual(entry["failure"]["class"], failure_class)
        self.assertIsInstance(entry["failure"]["detail"], str)
        self.assertEqual(entry["url_final"], entry["redirect_chain"][-1])
        self.assertEqual(entry["redirect_chain"][0], entry["url_requested"])
        self.assertIsNone(entry["prior_fetch_ref"])


class TransportDeadTests(FailureLineTestCase):
    def test_transport_dead_seed_writes_failure_lines(self):
        # U13 fixture: bind 127.0.0.1:0, read the port, CLOSE the socket —
        # the only construction that yields connection-refused (a bound but
        # non-listening socket times out instead). Assert the MANIFEST, not a
        # hit counter: there is no server, so "zero wire responses" is
        # vacuously true of every implementation.
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        lines = self.crawl([f"http://127.0.0.1:{port}/page"])

        self.assertEqual(len(lines), 5)     # 1 robots + 4 page attempts
        robots = lines[0]
        self.assertTrue(robots["url_requested"].endswith("/robots.txt"))
        self.assertIsNone(robots["seed_signal"])
        self.assertEqual(robots["attempt_n"], 1)
        self.assert_failure_shape(robots, "connection-refused")

        page = [e for e in lines if e["url_requested"].endswith("/page")]
        self.assertEqual([e["attempt_n"] for e in page], [1, 2, 3, 4])
        self.assertEqual([e["disposition"] for e in page],
                         ["retry", "retry", "retry", "blocked"])
        for entry in page:
            self.assert_failure_shape(entry, "connection-refused")
            self.assertEqual(entry["seed_signal"], "test")
            # transport death happens after the header middlewares ran
            self.assertIn("User-Agent", entry["request_headers"])
            self.assertEqual(entry["useragent_sent"],
                             entry["request_headers"]["User-Agent"])
        self.assertFalse(os.path.exists(os.path.join(self.cache_root, "sha256")))


class RobotsDisallowedTests(FailureLineTestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), DisallowHandler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_robots_disallowed_seed_writes_blocked_line(self):
        lines = self.crawl([f"{self.base}/private"])
        seed_lines = [e for e in lines if e["url_requested"].endswith("/private")]
        self.assertEqual(len(seed_lines), 1)        # blocked immediately, no retry
        entry = seed_lines[0]
        self.assert_failure_shape(entry, "robots-disallowed")
        self.assertEqual(entry["disposition"], "blocked")
        self.assertEqual(entry["attempt_n"], 1)
        # U1: IgnoreRequest fires at priority 100, before the header
        # middlewares — the recorder sees empty headers, and recording the
        # configured USER_AGent anyway would be fake fidelity.
        self.assertEqual(entry["request_headers"], {})
        self.assertIsNone(entry["useragent_sent"])
        # the robots fetch itself succeeded: a response line with real
        # provenance in the failure line's fetch_policy
        robots = [e for e in lines if e["url_requested"].endswith("/robots.txt")]
        self.assertEqual(len(robots), 1)
        self.assertEqual(robots[0]["http_status"], 200)
        self.assertIsNotNone(entry["fetch_policy"]["robots_sha256"])
