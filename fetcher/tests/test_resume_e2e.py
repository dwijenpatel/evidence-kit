import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Handler(BaseHTTPRequestHandler):
    hits: dict[str, int] = {}

    def do_GET(self):
        Handler.hits[self.path] = Handler.hits.get(self.path, 0) + 1
        body = (b"User-agent: *\nAllow: /\n" if self.path == "/robots.txt"
                else f"<html>{self.path}</html>".encode())
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


class ResumeTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        Handler.hits = {}
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = self._tmp.name
        self.cache_root = os.path.join(self.tmp, "cache")
        self.manifest = os.path.join(self.tmp, "manifest.jsonl")

    def cli_args(self, seeds_path: str) -> list[str]:
        return [sys.executable, "-P", "-m", "evidence_fetch",
                "--seeds", seeds_path,
                "--cache-root", self.cache_root,
                "--manifest", self.manifest,
                "--contact", "mailto:ops@example.invalid"]

    def run_cli(self, seeds_path: str):
        proc = subprocess.run(self.cli_args(seeds_path), cwd=REPO_ROOT,
                              env={**os.environ, "PYTHONPATH": "fetcher"},
                              capture_output=True, text=True, timeout=300)
        self.assertEqual(proc.returncode, 0, proc.stderr[-4000:])
        return proc

    def manifest_lines(self) -> list[dict]:
        if not os.path.exists(self.manifest):
            return []
        with open(self.manifest, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh.read().splitlines()]

    def test_rerun_refetches_nothing(self):
        # A9: the persisted JOBDIR frontier drops every seed before the
        # downloader, so no request reaches the robots middleware either.
        seeds = write_seeds(self.tmp, [f"{self.base}/r1"])
        self.run_cli(seeds)
        first_hits = dict(Handler.hits)
        first_lines = self.manifest_lines()
        self.assertEqual(len(first_lines), 2)   # robots + seed
        self.run_cli(seeds)
        self.assertEqual(Handler.hits, first_hits)          # zero new fetches
        self.assertEqual(self.manifest_lines(), first_lines)  # zero new lines

    def test_jobdir_delete_with_httpcache_writes_no_new_entries(self):
        # A 200-serving fixture BY DESIGN: stored 2xx responses are served
        # "cached" and write no entry. A retryable-status fixture would append
        # a fresh attempt sequence instead (that is correct, and the runbook
        # says so — HTTPCACHE_IGNORE_HTTP_CODES keeps retryables out of the
        # cache so backoff reaches the wire).
        seeds = write_seeds(self.tmp, [f"{self.base}/j1"])
        self.run_cli(seeds)
        first_hits = dict(Handler.hits)
        first_lines = self.manifest_lines()
        shutil.rmtree(os.path.join(self.cache_root, ".jobdir"))
        self.run_cli(seeds)
        self.assertEqual(Handler.hits, first_hits)          # 0 server hits
        self.assertEqual(self.manifest_lines(), first_lines)  # 0 new lines

    def test_interrupted_run_resumes_from_jobdir(self):
        # The slow one. Seeds must EXCEED CONCURRENT_REQUESTS (8): requests
        # already pulled into the downloader's slot queue are drained by the
        # graceful stop (measured — a 2-seed interrupt leaves nothing to
        # resume); only what is still in the SCHEDULER persists to the jobdir.
        # One SIGINT after the first seed response is the graceful stop.
        paths = [f"/i{n}" for n in range(10)]
        seeds = write_seeds(self.tmp, [f"{self.base}{p}" for p in paths])
        proc = subprocess.Popen(self.cli_args(seeds), cwd=REPO_ROOT,
                                env={**os.environ, "PYTHONPATH": "fetcher"},
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline and "/i0" not in Handler.hits:
                time.sleep(0.05)
            self.assertIn("/i0", Handler.hits, "first seed never fetched")
            proc.send_signal(signal.SIGINT)
            proc.communicate(timeout=180)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate()

        fetched_before = {e["url_requested"].rsplit("/", 1)[-1]
                          for e in self.manifest_lines()}
        remaining = {p.lstrip("/") for p in paths} - fetched_before
        self.assertTrue(remaining, "nothing left to resume")

        self.run_cli(seeds)
        # Across both runs: every path exactly once — resumed, never refetched.
        for path in ["/robots.txt", *paths]:
            self.assertEqual(Handler.hits.get(path), 1, path)
        lines = self.manifest_lines()
        self.assertEqual(len(lines), 1 + len(paths))
        self.assertEqual([e["http_status"] for e in lines], [200] * 11)
