import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from evidence_fetch.manifest import REQUIRED_KEYS
from evidence_fetch.wayback import (EMPTY_SHA1, Capture, capture_url, cdx_query_url,
                                    content_digests, distinct_digests, parse_cdx)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CDX_BODY = (b'[["timestamp","digest","statuscode"],'
            b'["20200101002334","JI6OR3QR4CI526JD6TMMNZNV4QPMPQCH","200"],'
            b'["20200101100018","WJM2KPM4GF3QK2BISVUH2ASX64NOUY7L","200"],'
            b'["20200101100757","JI6OR3QR4CI526JD6TMMNZNV4QPMPQCH","200"],'
            b'["20200106100020","O2XBZT4EZOUL6RS37E7DQFWAWWBEVGVJ","200"]]')


class CaptureUrlTests(unittest.TestCase):
    def test_capture_url_uses_id_modifier(self):
        url = capture_url("20200101002334", "http://example.com/")
        self.assertEqual(
            url, "https://web.archive.org/web/20200101002334id_/http://example.com/")
        self.assertIn("id_/", url)

    def test_capture_url_rejects_short_timestamp(self):
        for bad in ("20200101", "2020010100233", "202001010023345", "not-a-ts"):
            with self.assertRaises(ValueError, msg=bad) as cm:
                capture_url(bad, "http://example.com/")
            self.assertIn("14-digit timestamp", str(cm.exception))


class CdxQueryTests(unittest.TestCase):
    def test_cdx_query_url_includes_collapse_and_fl(self):
        self.assertEqual(
            cdx_query_url("example.com"),
            "https://web.archive.org/cdx/search/cdx?url=example.com&output=json"
            "&fl=timestamp%2Cdigest%2Cstatuscode&collapse=digest")

    def test_cdx_query_url_orders_optional_params(self):
        self.assertEqual(
            cdx_query_url("example.com", from_ts="2020", to_ts="2021", limit=25),
            "https://web.archive.org/cdx/search/cdx?url=example.com&output=json"
            "&fl=timestamp%2Cdigest%2Cstatuscode&from=2020&to=2021"
            "&collapse=digest&limit=25")


class ParseCdxTests(unittest.TestCase):
    def test_parse_cdx_drops_the_header_row(self):
        captures = parse_cdx(CDX_BODY)
        self.assertEqual(len(captures), 4)
        self.assertEqual(captures[0],
                         Capture("20200101002334",
                                 "JI6OR3QR4CI526JD6TMMNZNV4QPMPQCH", "200"))

    def test_parse_cdx_handles_empty_body(self):
        for empty in (b"", b"  \n", b"[]"):
            self.assertEqual(parse_cdx(empty), [], msg=empty)

    def test_parse_cdx_rejects_invalid_json(self):
        with self.assertRaises(ValueError) as cm:
            parse_cdx(b"<html>oops</html>")
        self.assertIn("not valid CDX JSON", str(cm.exception))

    def test_parse_cdx_rejects_short_row(self):
        with self.assertRaises(ValueError) as cm:
            parse_cdx(b'[["timestamp","digest","statuscode"],["20200101002334"]]')
        self.assertIn("CDX row", str(cm.exception))


class DigestTests(unittest.TestCase):
    def test_distinct_digests_dedupes_globally_not_adjacently(self):
        self.assertEqual(len(distinct_digests(parse_cdx(CDX_BODY))), 3)

    def test_distinct_digests_preserves_first_appearance_order(self):
        self.assertEqual(distinct_digests(parse_cdx(CDX_BODY)), [
            "JI6OR3QR4CI526JD6TMMNZNV4QPMPQCH",
            "WJM2KPM4GF3QK2BISVUH2ASX64NOUY7L",
            "O2XBZT4EZOUL6RS37E7DQFWAWWBEVGVJ"])

    def test_content_digests_filters_non_200_and_empty_captures(self):
        captures = parse_cdx(CDX_BODY) + [
            Capture("20200107000000", EMPTY_SHA1, "200"),   # empty capture
            Capture("20200108000000", "SOMEREDIRECTDIGEST0000000000000A", "301"),
            Capture("20200109000000", "UNKNOWNSTATUSDIGEST000000000000B", "-"),
        ]
        self.assertEqual(len(distinct_digests(captures)), 6)   # pure dedupe keeps all
        self.assertEqual(len(content_digests(captures)), 3)    # staleness input filters

    def test_empty_sha1_constant_marks_no_content(self):
        computed = base64.b32encode(hashlib.sha1(b"").digest()).decode("ascii")
        self.assertEqual(computed, EMPTY_SHA1)


CAPTURE_PATH = "/web/20200101002334id_/http://example.com/"
CAPTURE_BODY = b"<html>the original bytes, as archived</html>"


class CaptureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/robots.txt":
            body = b"User-agent: *\nAllow: /\n"
        elif self.path == CAPTURE_PATH:
            body = CAPTURE_BODY
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class CaptureEndToEndTests(unittest.TestCase):
    def test_capture_url_fetches_through_the_ordinary_spider_path(self):
        # A8: a capture URL is an ordinary URL in an ordinary Seeds row —
        # no Wayback code path exists in the fetcher. Invoked through the CLI
        # as a subprocess (R10): an in-process spider bypasses the --contact
        # gate and the {contact} placeholder would reach the wire unnoticed.
        server = ThreadingHTTPServer(("127.0.0.1", 0), CaptureHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_address[1]}"
        with tempfile.TemporaryDirectory() as tmp:
            seeds = os.path.join(tmp, "seeds.md")
            with open(seeds, "w", encoding="utf-8") as fh:
                fh.write("---\ntype: Seeds\ntitle: \"Fetch queue\"\n"
                         "timestamp: 2026-07-27\n---\n\n# Fetch queue\n\n"
                         "| url | added | signal | question |\n|---|---|---|---|\n"
                         f"| {base}{CAPTURE_PATH} | 2026-07-27 | archive test | q |\n")
            cache_root = os.path.join(tmp, "cache")
            manifest = os.path.join(tmp, "manifest.jsonl")
            proc = subprocess.run(
                [sys.executable, "-P", "-m", "evidence_fetch",
                 "--seeds", seeds, "--cache-root", cache_root,
                 "--manifest", manifest,
                 "--contact", "mailto:test@example.invalid"],
                cwd=REPO_ROOT, env={**os.environ, "PYTHONPATH": "fetcher"},
                capture_output=True, text=True, timeout=300)
            self.assertEqual(proc.returncode, 0, proc.stderr[-4000:])
            with open(manifest, encoding="utf-8") as fh:
                lines = [json.loads(line) for line in fh.read().splitlines()]
            capture = [e for e in lines
                       if e["url_requested"].endswith(CAPTURE_PATH)][0]
            # no Wayback-specific fields: the same key set as any other entry
            self.assertEqual(set(capture), set(REQUIRED_KEYS))
            with open(os.path.join(cache_root, capture["cache_relpath"]),
                      "rb") as fh:
                self.assertEqual(fh.read(), CAPTURE_BODY)   # byte-identical
            self.assertIn("mailto:test@example.invalid", capture["useragent_sent"])
            self.assertEqual(capture["seed_signal"], "archive test")
