"""Kit-side smoke matrix: scaffold each profile into a temp dir, run the corpus guard there."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_scaffold(tmp, profile, extra=None):
    out = os.path.join(tmp, f"corpus-{profile}")
    cmd = [sys.executable, os.path.join(KIT, "scaffold.py"),
           "--topic", "Smoke: colon topic", "--slug", "smoke",
           "--out", out, "--consumer", "smoke consumer",
           "--profile", profile] + (extra or [])
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out


def run_guard(corpus):
    return subprocess.run([sys.executable, "-m", "unittest", "tests.test_reference", "-q"],
                          cwd=corpus, capture_output=True, text=True)


class ScaffoldMatrix(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ek-smoke-")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_standalone_profile_guard_green_pre_git(self):
        corpus = run_scaffold(self.tmp, "standalone")
        r = run_guard(corpus)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(corpus, "tests", "corpus_guard.json")) as fh:
            cfg = json.load(fh)
        self.assertEqual(cfg["profile"], "standalone")
        self.assertIn("external/README.md", cfg["required"])
        self.assertIn("distilled/README.md", cfg["required"])

    def test_default_profile_is_standalone(self):
        out = os.path.join(self.tmp, "corpus-default")
        subprocess.run([sys.executable, os.path.join(KIT, "scaffold.py"),
                        "--topic", "T", "--slug", "t", "--out", out,
                        "--consumer", "c"], check=True, capture_output=True, text=True)
        with open(os.path.join(out, "tests", "corpus_guard.json")) as fh:
            cfg = json.load(fh)
        self.assertEqual(cfg["profile"], "standalone")


if __name__ == "__main__":
    unittest.main()
