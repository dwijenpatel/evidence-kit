import gzip
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

from scrapy.http import HtmlResponse, Request
from scrapy.settings import Settings

from evidence_fetch.middlewares.record import RecordMiddleware

DRIVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_crawl.py")

ROBOTS_BODY = b"User-agent: *\nAllow: /\n"
JSON_BODY = b'{"x":1}'
HTML_BODY = b"<html>b</html>"
GZ_PLAIN = b"gzip artifact body\n"
GZ_BODY = gzip.compress(GZ_PLAIN)

ROUTES = {
    "/robots.txt": ("text/plain", ROBOTS_BODY, {}),
    "/a.json": ("application/json", JSON_BODY, {}),
    "/b.html": ("text/html", HTML_BODY, {}),
    "/gz": ("text/plain", GZ_BODY, {"Content-Encoding": "gzip"}),
}


class Handler(BaseHTTPRequestHandler):
    hits: dict[str, int] = {}

    def do_GET(self):
        Handler.hits[self.path] = Handler.hits.get(self.path, 0) + 1
        route = ROUTES.get(self.path)
        if route is None:
            self.send_response(404)
            self.end_headers()
            return
        ctype, body, extra = route
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for name, value in extra.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def write_seeds(dirpath: str, urls: list[str]) -> str:
    rows = "".join(f"| {u} | 2026-07-27 | test | what shape |\n" for u in urls)
    doc = ("---\n"
           'type: Seeds\n'
           'title: "Fetch queue"\n'
           "timestamp: 2026-07-27\n"
           "---\n\n"
           "# Fetch queue\n\n"
           "| url | added | signal | question |\n"
           "|---|---|---|---|\n" + rows)
    path = os.path.join(dirpath, "seeds.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return path


def run_crawl(workdir: str, urls: list[str]) -> tuple[list[dict], str, str]:
    seeds = write_seeds(workdir, urls)
    cache_root = os.path.join(workdir, "cache")
    manifest = os.path.join(workdir, "manifest.jsonl")
    proc = subprocess.run(
        [sys.executable, "-P", DRIVER, seeds, cache_root, manifest],
        capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise AssertionError(f"crawl failed:\n{proc.stderr[-4000:]}")
    with open(manifest, encoding="utf-8") as fh:
        lines = [json.loads(line) for line in fh.read().splitlines()]
    return lines, cache_root, manifest


class SpiderEndToEndTests(unittest.TestCase):
    server: ThreadingHTTPServer

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.port = cls.server.server_address[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls._tmp = tempfile.TemporaryDirectory()
        # The worked example: two seeds, one host -> one crawl shared by tests.
        cls.lines, cls.cache_root, cls.manifest = run_crawl(
            cls._tmp.name, [f"{cls.base}/a.json", f"{cls.base}/b.html"])

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls._tmp.cleanup()

    def line_for(self, path: str) -> dict:
        matches = [e for e in self.lines if e["url_requested"].endswith(path)]
        self.assertEqual(len(matches), 1, f"{path}: {len(matches)} lines")
        return matches[0]

    def test_two_seeds_produce_three_entries_including_robots(self):
        self.assertEqual(len(self.lines), 3)
        robots = self.lines[0]
        self.assertTrue(robots["url_requested"].endswith("/robots.txt"))
        self.assertIsNone(robots["seed_signal"])
        self.assertEqual(robots["attempt_n"], 1)
        for entry in self.lines:
            self.assertEqual(entry["http_status"], 200)
            self.assertEqual(entry["disposition"], "ok")
            self.assertIsNone(entry["failure"])
        self.assertEqual(self.line_for("/a.json")["seed_signal"], "test")

    def test_json_and_html_take_the_same_path(self):
        a = self.line_for("/a.json")
        b = self.line_for("/b.html")
        self.assertEqual(set(a), set(b))
        for key in ("schema", "disposition", "http_status"):
            self.assertEqual(a[key], b[key], key)
        self.assertNotEqual(a["content_type"], b["content_type"])

    def test_cached_bytes_are_byte_identical(self):
        served = {"/robots.txt": ROBOTS_BODY, "/a.json": JSON_BODY,
                  "/b.html": HTML_BODY}
        for path, body in served.items():
            entry = self.line_for(path)
            full = os.path.join(self.cache_root, entry["cache_relpath"])
            with open(full, "rb") as fh:
                cached = fh.read()
            self.assertEqual(cached, body, path)
            self.assertEqual(hashlib.sha256(cached).hexdigest(),
                             entry["raw_bytes_sha256"], path)
            self.assertEqual(entry["raw_bytes_length"], len(body), path)

    def test_robots_fallback_synthesizes_url_with_netloc(self):
        # The robots fetch's own entry takes the fallback (the recorder at 1000
        # runs before the robots middleware stores provenance): netloc kept
        # (port included), observation fields null. Seed lines carry the real
        # provenance the crawl-delay middleware recorded.
        robots_url = f"http://127.0.0.1:{self.port}/robots.txt"
        robots_line = self.line_for("/robots.txt")
        self.assertEqual(robots_line["fetch_policy"], {
            "delay_used_s": robots_line["fetch_policy"]["delay_used_s"],
            "robots_url": robots_url,
            "robots_sha256": None,
            "robots_fetched_at": None,
        })
        robots_digest = hashlib.sha256(ROBOTS_BODY).hexdigest()
        for path in ("/a.json", "/b.html"):
            policy = self.line_for(path)["fetch_policy"]
            self.assertEqual(policy["robots_url"], robots_url)
            self.assertEqual(policy["robots_sha256"], robots_digest)
            self.assertIsNotNone(policy["robots_fetched_at"])
            self.assertIsInstance(policy["delay_used_s"], float)

    def test_useragent_sent_matches_request_headers(self):
        for entry in self.lines:
            self.assertEqual(entry["useragent_sent"],
                             entry["request_headers"]["User-Agent"])
            self.assertNotIn("{contact}", entry["useragent_sent"])

    def test_gzip_response_caches_wire_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines, cache_root, _ = run_crawl(tmp, [f"{self.base}/gz"])
            entry = [e for e in lines if e["url_requested"].endswith("/gz")][0]
            full = os.path.join(cache_root, entry["cache_relpath"])
            with open(full, "rb") as fh:
                cached = fh.read()
        self.assertEqual(cached, GZ_BODY)          # wire octets, not the inflation
        self.assertNotEqual(cached, GZ_PLAIN)
        self.assertEqual(entry["raw_bytes_length"], len(GZ_BODY))
        self.assertEqual(entry["response_headers"].get("Content-Encoding"), "gzip")


class CachedFlagTests(unittest.TestCase):
    def test_cached_flag_writes_no_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = os.path.join(tmp, "manifest.jsonl")
            crawler = SimpleNamespace(settings=Settings({
                "EVIDENCE_CACHE_ROOT": os.path.join(tmp, "cache"),
                "EVIDENCE_MANIFEST_PATH": manifest,
            }))
            middleware = RecordMiddleware(crawler)
            request = Request("http://127.0.0.1:1/x")
            response = HtmlResponse("http://127.0.0.1:1/x", status=200,
                                    body=b"cached body", request=request,
                                    flags=["cached"])
            returned = middleware.process_response(request, response, spider=None)
            self.assertIs(returned, response)
            self.assertFalse(os.path.exists(manifest))
            self.assertFalse(os.path.exists(os.path.join(tmp, "cache")))
