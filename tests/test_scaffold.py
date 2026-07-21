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


def regen_index(lake):
    subprocess.run([sys.executable, os.path.join(lake, "index.py")], check=True,
                   cwd=lake, capture_output=True)


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

    def test_lake_guard_enforces_tag_registry(self):
        lake = run_scaffold(self.tmp, "lake")
        os.makedirs(os.path.join(lake, "ai", "topic"), exist_ok=True)
        with open(os.path.join(lake, "ai", "topic", "doc.md"), "w") as fh:
            fh.write("---\ntype: Holdings\ntags: [unregistered-tag]\n---\n# d\n")
        r = run_guard(lake)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unregistered-tag", r.stderr + r.stdout)
        with open(os.path.join(lake, "terminology.md"), "a") as fh:
            fh.write("- `unregistered-tag` — test tag.\n")
        regen_index(lake)  # doc change -> XREF.md regenerated, per lake workflow
        r = run_guard(lake)
        self.assertEqual(r.returncode, 0, r.stderr)
        # Prose backticks in the registry section must not silently register a tag.
        with open(os.path.join(lake, "terminology.md"), "a") as fh:
            fh.write("\nNote: never use `prose-only-tag` casually.\n")
        with open(os.path.join(lake, "ai", "topic", "doc2.md"), "w") as fh:
            fh.write("---\ntype: Holdings\ntags: [prose-only-tag]\n---\n# d2\n")
        regen_index(lake)  # fresh index isolates the failure to the tag check
        r = run_guard(lake)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("prose-only-tag", r.stderr + r.stdout)

    def test_lake_index_generated_deterministic_and_guarded(self):
        lake = run_scaffold(self.tmp, "lake")
        idx = os.path.join(lake, "XREF.md")
        self.assertTrue(os.path.exists(idx))            # scaffold ran index.py
        with open(idx) as fh:
            first = fh.read()
        subprocess.run([sys.executable, os.path.join(lake, "index.py")], check=True,
                       cwd=lake, capture_output=True)
        with open(idx) as fh:
            self.assertEqual(first, fh.read())            # deterministic
        # cross-domain machinery: two docs sharing a tag + a URL, in two domains
        for dom in ("ai", "etl"):
            os.makedirs(os.path.join(lake, dom, "sub"), exist_ok=True)
            with open(os.path.join(lake, dom, "sub", "doc.md"), "w") as fh:
                fh.write("---\ntype: Holdings\ntitle: \"D\"\ntags: [shared-tag]\n---\n"
                         "# D\nSee https://example.com/paper for the claim.\n")
        with open(os.path.join(lake, "terminology.md"), "a") as fh:
            fh.write("- `shared-tag` — test.\n")
        r = run_guard(lake)
        self.assertNotEqual(r.returncode, 0)             # INDEX now stale -> guard fails
        subprocess.run([sys.executable, os.path.join(lake, "index.py")], check=True,
                       cwd=lake, capture_output=True)
        with open(idx) as fh:
            body = fh.read()
        self.assertIn("shared-tag", body)
        self.assertIn("example.com/paper", body)         # shared-source across domains
        r = run_guard(lake)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
