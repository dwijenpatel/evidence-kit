import json
import os
import tempfile
import unittest

from evidence_fetch.manifest import (
    REQUIRED_KEYS,
    ManifestSchemaError,
    append_entry,
    load_prior_index,
)

DIGEST_A = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
DIGEST_B = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"


def response_entry(**overrides):
    entry = {
        "schema": 1,
        "url_requested": "https://example.com/pricing",
        "url_final": "https://example.com/pricing",
        "attempt_n": 1,
        "fetched_at": "2026-07-25T19:04:11.212Z",
        "http_status": 200,
        "response_protocol": "HTTP/1.1",
        "raw_bytes_sha256": DIGEST_A,
        "raw_bytes_length": 5,
        "cache_relpath": f"sha256/2c/{DIGEST_A}",
        "content_type": "text/html; charset=utf-8",
        "request_headers": {"User-Agent": "evidence-fetch/0.1 (+mailto:t@example.com)"},
        "response_headers": {"Content-Type": "text/html; charset=utf-8"},
        "redirect_chain": ["https://example.com/pricing"],
        "etag": None,
        "etag_is_weak": None,
        "last_modified": None,
        "disposition": "ok",
        "fetch_policy": {
            "delay_used_s": 5.0,
            "robots_url": "https://example.com/robots.txt",
            "robots_sha256": None,
            "robots_fetched_at": None,
        },
        "useragent_sent": "evidence-fetch/0.1 (+mailto:t@example.com)",
        "prior_fetch_ref": None,
        "seed_signal": "test",
        "failure": None,
    }
    entry.update(overrides)
    return entry


RESPONSE_UNIT = (
    "http_status", "response_protocol", "raw_bytes_sha256", "raw_bytes_length",
    "cache_relpath", "content_type", "response_headers", "etag", "etag_is_weak",
    "last_modified",
)


def failure_entry(**overrides):
    entry = response_entry(
        disposition="retry",
        failure={"class": "timeout",
                 "detail": "Getting https://example.com/pricing took longer than 30.0 seconds."},
    )
    for key in RESPONSE_UNIT:
        entry[key] = None
    entry.update(overrides)
    return entry


class ManifestTempDirTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = os.path.join(self._tmp.name, "manifest.jsonl")


class AppendEntryTests(ManifestTempDirTest):
    def test_required_keys_is_exactly_23(self):
        self.assertEqual(len(REQUIRED_KEYS), 23)
        self.assertEqual(REQUIRED_KEYS, frozenset(response_entry()))

    def test_append_then_load_roundtrips(self):
        append_entry(self.path, response_entry())
        with open(self.path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0]), response_entry())
        self.assertEqual(load_prior_index(self.path),
                         {"https://example.com/pricing": DIGEST_A})

    def test_missing_required_key_raises(self):
        entry = response_entry()
        del entry["etag"]
        with self.assertRaises(ManifestSchemaError) as cm:
            append_entry(self.path, entry)
        self.assertIn("missing required key", str(cm.exception))
        self.assertFalse(os.path.exists(self.path))

    def test_unknown_key_raises(self):
        with self.assertRaises(ManifestSchemaError) as cm:
            append_entry(self.path, response_entry(extractor="x"))
        self.assertIn("unknown key", str(cm.exception))

    def test_fetch_policy_must_have_exactly_four_keys(self):
        for policy in (
            {"delay_used_s": 5.0},
            {"delay_used_s": 5.0, "robots_url": "u", "robots_sha256": None,
             "robots_fetched_at": None, "extra": 1},
            None,
        ):
            with self.assertRaises(ManifestSchemaError, msg=policy) as cm:
                append_entry(self.path, response_entry(fetch_policy=policy))
            self.assertIn("fetch_policy", str(cm.exception))

    def test_keys_are_sorted_in_output(self):
        append_entry(self.path, response_entry())
        with open(self.path, encoding="utf-8") as fh:
            line = fh.readline()
        keys = list(json.loads(line))
        self.assertEqual(keys, sorted(keys))

    def test_failure_line_roundtrips(self):
        append_entry(self.path, failure_entry())
        self.assertEqual(load_prior_index(self.path), {})
        with open(self.path, encoding="utf-8") as fh:
            loaded = json.loads(fh.readline())
        self.assertEqual(loaded, failure_entry())

    def test_failure_xor_is_validated(self):
        bad_entries = [
            # failure non-null alongside an integer status
            response_entry(failure={"class": "timeout", "detail": "d"}),
            # both null
            failure_entry(failure=None),
            # failure line with a non-null response-unit field
            failure_entry(raw_bytes_length=0),
            # class outside FAILURE_CLASSES
            failure_entry(failure={"class": "gremlins", "detail": "d"}),
            # failure not exactly {class, detail}
            failure_entry(failure={"class": "timeout"}),
        ]
        for entry in bad_entries:
            with self.assertRaises(ManifestSchemaError) as cm:
                append_entry(self.path, entry)
            self.assertIn("failure", str(cm.exception))


class LoadPriorIndexTests(ManifestTempDirTest):
    def test_absent_manifest_returns_empty(self):
        self.assertEqual(load_prior_index(self.path), {})

    def test_503_then_200_produces_two_entries_and_url_not_failed(self):
        url = "https://web.archive.org/cdx/search/cdx?url=example.com"
        append_entry(self.path, response_entry(
            url_requested=url, url_final=url, redirect_chain=[url],
            http_status=503, disposition="retry", prior_fetch_ref=None))
        append_entry(self.path, response_entry(
            url_requested=url, url_final=url, redirect_chain=[url],
            attempt_n=2, http_status=200, raw_bytes_sha256=DIGEST_B,
            cache_relpath=f"sha256/b9/{DIGEST_B}", disposition="ok"))
        with open(self.path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(load_prior_index(self.path), {url: DIGEST_B})

    def test_prior_fetch_ref_is_none_when_only_non_2xx_exist(self):
        append_entry(self.path, response_entry(http_status=503, disposition="retry"))
        self.assertEqual(load_prior_index(self.path), {})

    def test_prior_fetch_ref_points_at_most_recent_2xx(self):
        # last matching line in FILE ORDER wins; fetched_at is never consulted
        append_entry(self.path, response_entry(
            raw_bytes_sha256=DIGEST_A, fetched_at="2026-07-25T19:04:11.212Z"))
        append_entry(self.path, response_entry(
            raw_bytes_sha256=DIGEST_B, cache_relpath=f"sha256/b9/{DIGEST_B}",
            fetched_at="2026-07-24T00:00:00.000Z"))
        self.assertEqual(load_prior_index(self.path),
                         {"https://example.com/pricing": DIGEST_B})

    def test_failure_lines_never_enter_prior_index(self):
        append_entry(self.path, response_entry(raw_bytes_sha256=DIGEST_A))
        append_entry(self.path, failure_entry(attempt_n=1))
        self.assertEqual(load_prior_index(self.path),
                         {"https://example.com/pricing": DIGEST_A})

    def test_partial_final_line_is_tolerated(self):
        append_entry(self.path, response_entry())
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write('{"schema": 1, "url_requested": "https://exa')
        self.assertEqual(load_prior_index(self.path),
                         {"https://example.com/pricing": DIGEST_A})

    def test_corrupt_middle_line_raises(self):
        append_entry(self.path, response_entry())
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write("not json at all\n")
        append_entry(self.path, response_entry(raw_bytes_sha256=DIGEST_B,
                                               cache_relpath=f"sha256/b9/{DIGEST_B}"))
        with self.assertRaises(ManifestSchemaError) as cm:
            load_prior_index(self.path)
        self.assertIn("corrupt manifest line", str(cm.exception))

    def test_foreign_lines_are_skipped_by_the_reader(self):
        append_entry(self.path, response_entry())
        with open(self.path, "a", encoding="utf-8") as fh:
            # sub-project-2 shapes: no schema key, and no url_requested key
            fh.write(json.dumps({"url_requested": "https://example.com/pricing",
                                 "normalized": "x"}) + "\n")
            fh.write(json.dumps({"schema": 7, "simhash": "y"}) + "\n")
        self.assertEqual(load_prior_index(self.path),
                         {"https://example.com/pricing": DIGEST_A})

    def test_unknown_schema_version_on_a_fetcher_line_raises(self):
        append_entry(self.path, response_entry())
        line = json.loads(json.dumps(response_entry()))
        line["schema"] = 2
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(line) + "\n")
        with self.assertRaises(ManifestSchemaError) as cm:
            load_prior_index(self.path)
        self.assertIn("unknown schema version", str(cm.exception))

    def test_redirect_chain_includes_requested_url_when_no_redirect(self):
        entry = response_entry()
        self.assertEqual(entry["redirect_chain"], [entry["url_requested"]])
        append_entry(self.path, entry)
        with open(self.path, encoding="utf-8") as fh:
            loaded = json.loads(fh.readline())
        self.assertEqual(loaded["redirect_chain"], [loaded["url_requested"]])
        self.assertEqual(loaded["url_final"], loaded["redirect_chain"][-1])
