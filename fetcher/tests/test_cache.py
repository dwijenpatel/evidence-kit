import os
import tempfile
import unittest

from evidence_fetch.cache import cache_relpath, cache_path, write_artifact

DIGEST = "a" * 64


class CachePathTests(unittest.TestCase):
    def test_relpath_shards_on_first_two_hex(self):
        self.assertEqual(cache_relpath(DIGEST), f"sha256/aa/{DIGEST}")

    def test_relpath_rejects_non_hex(self):
        for bad in ("", "xyz", "A" * 64, "a" * 63, "a" * 65):
            with self.assertRaises(ValueError, msg=bad):
                cache_relpath(bad)

    def test_path_joins_under_root(self):
        self.assertEqual(cache_path("/tmp/c", DIGEST),
                         os.path.join("/tmp/c", "sha256", "aa", DIGEST))

    def test_write_artifact_is_content_addressed_and_idempotent(self):
        with tempfile.TemporaryDirectory() as root:
            digest, rel = write_artifact(root, b"hello")
            self.assertEqual(
                digest,
                "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824")
            full = os.path.join(root, rel)
            self.assertTrue(os.path.exists(full))
            with open(full, "rb") as fh:
                self.assertEqual(fh.read(), b"hello")
            mtime = os.stat(full).st_mtime_ns
            again = write_artifact(root, b"hello")
            self.assertEqual(again, (digest, rel))
            self.assertEqual(os.stat(full).st_mtime_ns, mtime)  # not rewritten

    def test_write_artifact_handles_empty_body(self):
        with tempfile.TemporaryDirectory() as root:
            digest, _ = write_artifact(root, b"")
            self.assertEqual(
                digest,
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
