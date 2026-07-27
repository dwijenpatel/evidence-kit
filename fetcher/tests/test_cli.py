import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROUTES = {
    "/robots.txt": ("text/plain", b"User-agent: *\nAllow: /\n"),
    "/a.json": ("application/json", b'{"x":1}'),
    "/b.html": ("text/html", b"<html>b</html>"),
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
        ctype, body = route
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def write_seeds_doc(dirpath: str, rows: list[tuple[str, str]],
                    doc_type: str = "Seeds") -> str:
    table_rows = "".join(
        f"| {url} | 2026-07-27 | {signal} | what shape |\n" for url, signal in rows)
    doc = ("---\n"
           f"type: {doc_type}\n"
           'title: "Fetch queue"\n'
           "timestamp: 2026-07-27\n"
           "---\n\n"
           "# Fetch queue\n\n"
           "| url | added | signal | question |\n"
           "|---|---|---|---|\n" + table_rows)
    path = os.path.join(dirpath, "seeds.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return path


def run_cli(args: list[str], python_prelude: str | None = None):
    """Run the CLI as a subprocess with cwd = the repo root (pinned by the plan:
    the relative --project form resolves against the process cwd)."""
    if python_prelude is None:
        cmd = [sys.executable, "-P", "-m", "evidence_fetch", *args]
    else:
        cmd = [sys.executable, "-P", "-c", python_prelude, *args]
    env = {**os.environ, "PYTHONPATH": "fetcher"}
    return subprocess.run(cmd, cwd=REPO_ROOT, env=env,
                          capture_output=True, text=True, timeout=120)


class CliTestCase(unittest.TestCase):
    def setUp(self):
        Handler.hits = {}
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = self._tmp.name
        self.cache_root = os.path.join(self.tmp, "cache")
        self.manifest = os.path.join(self.tmp, "manifest.jsonl")

    def base_args(self, seeds_path: str, extra: list[str] = ()) -> list[str]:
        return ["--seeds", seeds_path,
                "--cache-root", self.cache_root,
                "--manifest", self.manifest,
                "--contact", "mailto:ops@example.invalid",
                *extra]

    def manifest_lines(self) -> list[dict]:
        with open(self.manifest, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh.read().splitlines()]


class StartupFailureTests(CliTestCase):
    def test_missing_contact_exits_2(self):
        seeds = write_seeds_doc(self.tmp, [])
        proc = run_cli(["--seeds", seeds, "--cache-root", self.cache_root,
                        "--manifest", self.manifest])
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("--contact is required", proc.stderr)

    def test_missing_seeds_file_exits_2(self):
        proc = run_cli(self.base_args(os.path.join(self.tmp, "absent.md")))
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("no such seeds file", proc.stderr)

    def test_cache_root_not_writable_exits_2(self):
        seeds = write_seeds_doc(self.tmp, [])
        ro_dir = os.path.join(self.tmp, "ro")
        os.makedirs(ro_dir)
        os.chmod(ro_dir, stat.S_IRUSR | stat.S_IXUSR)
        self.addCleanup(os.chmod, ro_dir, stat.S_IRWXU)
        proc = run_cli(["--seeds", seeds,
                        "--cache-root", os.path.join(ro_dir, "cache"),
                        "--manifest", self.manifest,
                        "--contact", "mailto:ops@example.invalid"])
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("cache root is not writable", proc.stderr)


class ServerBackedTests(CliTestCase):
    server: ThreadingHTTPServer

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_malformed_seeds_exits_2_before_any_request(self):
        seeds = write_seeds_doc(self.tmp, [(f"{self.base}/a.json", "test")],
                                doc_type="Holdings")
        proc = run_cli(self.base_args(seeds))
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("type: Seeds", proc.stderr)
        self.assertEqual(Handler.hits, {})

    def test_non_url_seed_exits_2_before_any_request(self):
        seeds = write_seeds_doc(self.tmp, [
            (f"{self.base}/a.json", "test"),
            ("ask Bob for the quarterly PDF", "hallway"),
        ])
        proc = run_cli(self.base_args(seeds))
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("seed url is not fetchable", proc.stderr)
        self.assertIn("ask Bob", proc.stderr)
        self.assertEqual(Handler.hits, {})

    def test_empty_seed_table_is_a_noop(self):
        seeds = write_seeds_doc(self.tmp, [])
        proc = run_cli(self.base_args(seeds))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(Handler.hits, {})
        self.assertFalse(os.path.exists(self.manifest))

    def test_completed_crawl_exits_0_and_records(self):
        seeds = write_seeds_doc(self.tmp, [(f"{self.base}/a.json", "test")])
        proc = run_cli(self.base_args(seeds))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = self.manifest_lines()
        self.assertEqual(len(lines), 2)     # robots + seed
        self.assertTrue(lines[0]["url_requested"].endswith("/robots.txt"))
        ua = lines[1]["useragent_sent"]
        self.assertIn("mailto:ops@example.invalid", ua)
        self.assertNotIn("{contact}", ua)

    def test_duplicate_seed_first_row_wins(self):
        seeds = write_seeds_doc(self.tmp, [
            (f"{self.base}/a.json", "first"),
            (f"{self.base}/a.json", "second"),
        ])
        proc = run_cli(self.base_args(seeds))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("duplicate seed", proc.stderr)
        seed_lines = [e for e in self.manifest_lines()
                      if e["url_requested"].endswith("/a.json")]
        self.assertEqual(len(seed_lines), 1)
        self.assertEqual(seed_lines[0]["seed_signal"], "first")

    def test_httpcache_lands_under_the_cache_root(self):
        stale = os.path.join(REPO_ROOT, ".scrapy")
        if os.path.exists(stale):   # survives an earlier broken run
            shutil.rmtree(stale)
        seeds = write_seeds_doc(self.tmp, [(f"{self.base}/a.json", "test")])
        proc = run_cli(self.base_args(seeds))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(os.path.isdir(os.path.join(self.cache_root, "httpcache")))
        self.assertFalse(os.path.exists(stale))

    def test_manifest_schema_violation_exits_nonzero(self):
        seeds = write_seeds_doc(self.tmp, [(f"{self.base}/a.json", "test")])
        prelude = ("import evidence_fetch.manifest as m; "
                   "m.REQUIRED_KEYS = frozenset(m.REQUIRED_KEYS | {'bogus_key'}); "
                   "from evidence_fetch.cli import main; "
                   "import sys; sys.exit(main())")
        proc = run_cli(self.base_args(seeds), python_prelude=prelude)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("manifest-schema-violation", proc.stderr)
