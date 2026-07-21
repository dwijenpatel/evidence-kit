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

    def test_lake_profile_layout_and_guard(self):
        corpus = run_scaffold(self.tmp, "lake")
        for absent in ("external", "internal", "distilled"):
            self.assertFalse(os.path.exists(os.path.join(corpus, absent)))
        with open(os.path.join(corpus, "terminology.md")) as fh:
            body = fh.read()
        self.assertIn("## Tag registry", body)
        with open(os.path.join(corpus, "README.md")) as fh:
            self.assertIn("## Consumers", fh.read())
        self.assertTrue(os.path.isdir(os.path.join(corpus, "mirrors")))
        r = run_guard(corpus)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_project_profile_requires_and_records_lake_root(self):
        with self.assertRaises(subprocess.CalledProcessError):
            run_scaffold(self.tmp, "project")  # no --lake-root
        lake = run_scaffold(self.tmp, "lake")
        corpus = run_scaffold(self.tmp, "project", ["--lake-root", lake])
        self.assertFalse(os.path.exists(os.path.join(corpus, "external")))
        with open(os.path.join(corpus, "tests", "corpus_guard.json")) as fh:
            cfg = json.load(fh)
        self.assertEqual(cfg["lake_root"], lake)
        r = run_guard(corpus)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_project_guard_checks_lake_citations(self):
        lake = run_scaffold(self.tmp, "lake")
        corpus = run_scaffold(self.tmp, "project", ["--lake-root", lake])
        os.makedirs(os.path.join(lake, "ai", "topic"), exist_ok=True)
        with open(os.path.join(lake, "ai", "topic", "doc.md"), "w") as fh:
            fh.write("---\ntype: Holdings\n---\n# d\n")
        row = ("1. **Fact.** · `A3` · cited lake:ai/topic/doc.md §2 @ abc1234 "
               "and record lake:ai/topic/rec.jsonl\n")
        ext = os.path.join(corpus, "distilled", "external.md")
        with open(ext, "a") as fh:
            fh.write(row)
        r = run_guard(corpus)
        self.assertNotEqual(r.returncode, 0)          # rec.jsonl missing -> fail
        self.assertIn("lake:ai/topic/rec.jsonl", r.stderr + r.stdout)
        with open(os.path.join(lake, "ai", "topic", "rec.jsonl"), "w") as fh:
            fh.write("{}\n")
        r = run_guard(corpus)
        self.assertEqual(r.returncode, 0, r.stderr)   # both resolve -> pass


if __name__ == "__main__":
    unittest.main()
