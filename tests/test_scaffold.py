"""Kit-side smoke matrix: scaffold each profile into a temp dir, run the corpus guard there."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PARAM_HEADER = ("| subject | parameter | value | unit | regime | as_of | warrant "
                "| decay | source |\n"
                "|---|---|---|---|---|---|---|---|---|\n")
PARAM_ROW = ("| S3 Standard | storage price | 0.023 | USD/GB-month | us-east-1, first "
             "50TB | 2026-07-25 | A4 | price-surface | [1] |\n")


def write_parameters(corpus, row, header=PARAM_HEADER):
    """Write a Parameters doc into a scaffolded corpus; return its path."""
    path = os.path.join(corpus, "external", "storage-prices.md")
    with open(path, "w") as fh:
        fh.write('---\ntype: Parameters\ntitle: "Storage prices"\n'
                 'description: Smoke fixture.\ntimestamp: 2026-07-25\n---\n\n'
                 "# Storage prices\n\n" + header + row +
                 "\n# Citations\n\n[1] https://example.com/pricing\n")
    return path


def set_decay_classes(corpus, classes):
    """Add a decay_classes allow-list to a scaffolded corpus's guard config."""
    cfg_path = os.path.join(corpus, "tests", "corpus_guard.json")
    with open(cfg_path) as fh:
        cfg = json.load(fh)
    cfg["decay_classes"] = classes
    with open(cfg_path, "w") as fh:
        json.dump(cfg, fh, indent=2)


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

    def test_lake_xref_shared_source_normalizes_arxiv_and_collapses_mirrors(self):
        """Same primary cited as abs URL / pdf URL / prose 'arXiv <id>' collapses to one
        shared-source key; a MANIFEST mirror of that key sets a [mirrored] flag instead of
        counting as its own subtopic (mirrors/<domain> must not satisfy the >=2 threshold
        on its own)."""
        lake = run_scaffold(self.tmp, "lake")
        os.makedirs(os.path.join(lake, "ai", "rsi-lab"), exist_ok=True)
        os.makedirs(os.path.join(lake, "ai", "self-improvement"), exist_ok=True)
        os.makedirs(os.path.join(lake, "mirrors", "ai", "x"), exist_ok=True)
        with open(os.path.join(lake, "ai", "rsi-lab", "doc.md"), "w") as fh:
            fh.write("---\ntype: Holdings\ntitle: \"D1\"\ntags: [shared-tag]\n---\n"
                     "# D1\nSee https://arxiv.org/abs/1234.56789 for the source.\n")
        with open(os.path.join(lake, "ai", "self-improvement", "doc.md"), "w") as fh:
            fh.write("---\ntype: Holdings\ntitle: \"D2\"\ntags: [shared-tag]\n---\n"
                     "# D2\nPer arXiv 1234.56789, also mirrored at "
                     "https://www.arxiv.org/pdf/1234.56789v2 for the PDF.\n")
        with open(os.path.join(lake, "mirrors", "ai", "x", "MANIFEST.md"), "w") as fh:
            fh.write("---\ntype: Mirror Manifest\ntitle: \"Mirror manifest — ai/x\"\n"
                     "description: Local mirrors captured for ai/x.\n---\n"
                     "# Mirror manifest — ai/x\n\n"
                     "| local | url | retrieved | type |\n|---|---|---|---|\n"
                     "| paper.pdf | https://arxiv.org/abs/1234.56789 | 2026-07-20 | pdf |\n")
        with open(os.path.join(lake, "terminology.md"), "a") as fh:
            fh.write("- `shared-tag` — test.\n")
        subprocess.run([sys.executable, os.path.join(lake, "index.py")], check=True,
                       cwd=lake, capture_output=True)
        with open(os.path.join(lake, "XREF.md")) as fh:
            body = fh.read()
        rows = [ln for ln in body.splitlines() if ln.startswith("- arxiv:1234.56789")]
        self.assertEqual(len(rows), 1, body)                    # exactly one collapsed row
        row = rows[0]
        self.assertIn("ai/rsi-lab", row)
        self.assertIn("ai/self-improvement", row)
        self.assertIn("[mirrored]", row)
        self.assertNotIn("mirrors/ai", row)                     # mirror namespace not a subtopic
        r = run_guard(lake)
        self.assertEqual(r.returncode, 0, r.stderr)


    def test_guard_accepts_a_complete_parameters_table(self):
        corpus = run_scaffold(self.tmp, "standalone")
        write_parameters(corpus, PARAM_ROW)
        r = run_guard(corpus)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_guard_rejects_parameters_row_missing_as_of(self):
        corpus = run_scaffold(self.tmp, "standalone")
        write_parameters(corpus, PARAM_ROW.replace("| 2026-07-25 |", "|  |"))
        r = run_guard(corpus)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("empty `as_of`", r.stderr + r.stdout)

    def test_guard_rejects_parameters_row_missing_source(self):
        corpus = run_scaffold(self.tmp, "standalone")
        write_parameters(corpus, PARAM_ROW.replace("| [1] |", "|  |"))
        r = run_guard(corpus)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("empty `source`", r.stderr + r.stdout)

    def test_guard_rejects_parameters_header_drift(self):
        corpus = run_scaffold(self.tmp, "standalone")
        write_parameters(corpus, PARAM_ROW,
                         header=PARAM_HEADER.replace("| regime |", "| conditions |"))
        r = run_guard(corpus)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("regime", r.stderr + r.stdout)

    def test_guard_rejects_parameters_header_reordered(self):
        """All nine names present, two swapped. A `set()` comparison would accept
        this and then report a blank `regime` for a cell whose real column is
        `as_of` — the header is an ordered contract, not a membership test."""
        corpus = run_scaffold(self.tmp, "standalone")
        write_parameters(corpus, PARAM_ROW,
                         header=PARAM_HEADER.replace("| regime | as_of |",
                                                     "| as_of | regime |"))
        r = run_guard(corpus)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("expected", r.stderr + r.stdout)

    def test_guard_rejects_parameters_row_that_is_entirely_blank(self):
        corpus = run_scaffold(self.tmp, "standalone")
        write_parameters(corpus, "|  |  |  |  |  |  |  |  |  |\n")
        r = run_guard(corpus)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("empty `as_of`", r.stderr + r.stdout)

    def test_guard_selects_parameters_doc_with_quoted_type(self):
        corpus = run_scaffold(self.tmp, "standalone")
        path = write_parameters(corpus, PARAM_ROW.replace("| 2026-07-25 |", "|  |"))
        with open(path) as fh:
            doc = fh.read()
        with open(path, "w") as fh:
            fh.write(doc.replace("type: Parameters", 'type: "Parameters"'))
        r = run_guard(corpus)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("empty `as_of`", r.stderr + r.stdout)

    def test_guard_rejects_parameters_row_with_illegal_warrant(self):
        corpus = run_scaffold(self.tmp, "standalone")
        write_parameters(corpus, PARAM_ROW.replace("| A4 |", "| measured, single-source |"))
        r = run_guard(corpus)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not one of", r.stderr + r.stdout)

    def test_guard_accepts_tier_b_and_c_warrants(self):
        corpus = run_scaffold(self.tmp, "standalone")
        write_parameters(corpus, PARAM_ROW.replace("| A4 |", "| B |"))
        self.assertEqual(run_guard(corpus).returncode, 0)
        write_parameters(corpus, PARAM_ROW.replace("| A4 |", "| C |"))
        self.assertEqual(run_guard(corpus).returncode, 0)

    def test_guard_validates_decay_only_when_classes_configured(self):
        corpus = run_scaffold(self.tmp, "standalone")
        write_parameters(corpus, PARAM_ROW.replace("| price-surface |", "| their-tree |"))
        self.assertEqual(run_guard(corpus).returncode, 0)   # unset -> not enforced
        set_decay_classes(corpus, ["price-surface", "perf-envelope"])
        r = run_guard(corpus)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not in decay_classes", r.stderr + r.stdout)


if __name__ == "__main__":
    unittest.main()
