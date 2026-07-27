"""Corpus guard: the corpus stays navigable, whole, and OKF-conformant.

Every markdown link must resolve (relative, or bundle-absolute per OKF §5.1), the
load-bearing files named in tests/corpus_guard.json must exist, and every concept
document must carry OKF frontmatter with a non-empty `type` (OKF v0.1 §9). Stricter
than OKF's permissive consumer minimum on purpose: this guard runs on the producer
side. Part of the evidence-kit method; configure via corpus_guard.json, not by
editing this file.

Run from the corpus root: python3 -m unittest tests.test_reference -q
"""

import functools
import json
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINK = re.compile(r"\[[^\]]*\]\(([^)#\s]+?)(?:#[^)]*)?\)")
LAKE_REF = re.compile(r"\blake:([\w./\-]+)")
FM_TAGS = re.compile(r"^tags:\s*\[([^\]]*)\]", re.MULTILINE)
REGISTERED = re.compile(r"`([A-Za-z0-9_-]+)`")
# OKF reserved filenames (§3.1): not concept documents, exempt from the `type` rule.
RESERVED = {"index.md", "log.md"}
FENCE = re.compile(r"\A---[ \t]*\r?\n(.*?)^---[ \t]*\r?$", re.DOTALL | re.MULTILINE)
# A `type: Parameters` document is a cost/performance surface: one pipe table, pinned
# columns, warrant and decay carried per row.
PARAM_COLUMNS = ("subject", "parameter", "value", "unit", "regime",
                 "as_of", "warrant", "decay", "source")
# A1-A4 and M are the Tier-A warrants from GRADING.md; B and C name the tier where no
# Tier-A warrant applies, because most substrate facts are directional by construction
# and the column would otherwise have no legal value for them.
WARRANTS = frozenset({"A1", "A2", "A3", "A4", "M", "B", "C"})
PARAM_TYPE = re.compile(r"""^type:\s*["']?Parameters["']?\s*(#.*)?$""", re.MULTILINE)
SEED_COLUMNS = ("url", "added", "signal", "question")
SEED_TYPE = re.compile(r"""^type:\s*["']?Seeds["']?\s*(#.*)?$""", re.MULTILINE)
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ALIGN_ROW = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
CELL_SPLIT = re.compile(r"(?<!\\)\|")


def frontmatter(body):
    """The text between the opening '---' fence and its closing fence, or None.

    Tolerates CRLF line endings — a Windows-authored doc is still a concept doc.
    """
    m = FENCE.match(body)
    return m.group(1) if m else None


def has_key(fm, key):
    """True if the frontmatter text has a non-empty top-level `key:` line."""
    return re.search(rf"^{key}:\s*\S", fm, re.MULTILINE) is not None


def split_pipe_row(line):
    r"""Cells of one markdown pipe row: outer pipes dropped, each cell trimmed.

    An escaped pipe (`\|`) is cell content, not a separator, and is unescaped in the
    returned cell.
    """
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [c.replace("\\|", "|").strip() for c in CELL_SPLIT.split(body)]


def pipe_blocks(body):
    """Contiguous runs of markdown pipe-table lines, in document order.

    Lines inside a fenced code block are not table rows: a document may show an
    example table in a fence without it counting as a second table.
    """
    blocks, current, fenced = [], [], False
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced and line.lstrip().startswith("|"):
            current.append(line)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks

def load_config(testcase):
    """Load corpus_guard.json inside the test (not at import time), so a missing
    or malformed config reads as one clear failure instead of a collection error
    that hides every test."""
    path = os.path.join(ROOT, "tests", "corpus_guard.json")
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        testcase.fail(f"guard config missing: {path}")
    except json.JSONDecodeError as e:
        testcase.fail(f"guard config is not valid JSON: {path} ({e})")


@functools.lru_cache(maxsize=None)
def tracked_markdown():
    """Markdown files under version control; filesystem walk if git is absent.

    Cached: the file set cannot change mid-run, and the git call is the expensive part.
    """
    try:
        out = subprocess.run(
            ["git", "-C", ROOT, "ls-files", "*.md"],
            capture_output=True, text=True, check=True,
        ).stdout.split()
        files = [f for f in out if os.path.exists(os.path.join(ROOT, f))]
        if files:
            return files
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    files = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            if name.endswith(".md"):
                files.append(os.path.relpath(os.path.join(dirpath, name), ROOT))
    return files


class CorpusLinkTests(unittest.TestCase):
    def test_corpus_is_present(self):
        config = load_config(self)
        files = tracked_markdown()
        self.assertGreaterEqual(
            len(files), config["min_markdown_files"], "the corpus lost its content?"
        )
        for anchor in config["required"]:
            self.assertIn(anchor, files, f"load-bearing document missing: {anchor}")

    def test_every_relative_link_resolves(self):
        broken = []
        for f in tracked_markdown():
            base = os.path.dirname(os.path.join(ROOT, f))
            with open(os.path.join(ROOT, f), encoding="utf-8") as fh:
                body = fh.read()
            for m in LINK.finditer(body):
                target = m.group(1)
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                if target.startswith("/"):  # bundle-absolute (OKF §5.1): corpus root
                    resolved = os.path.join(ROOT, target.lstrip("/"))
                else:
                    resolved = os.path.join(base, target)
                if not os.path.exists(resolved):
                    broken.append(f"{f} -> {target}")
        self.assertEqual(broken, [], "broken relative links:\n" + "\n".join(broken))

    def test_okf_conformance(self):
        """OKF v0.1 §9: concept docs carry frontmatter with a non-empty `type`;
        the bundle-root index.md declares the okf_version it targets (§11)."""
        bad = []
        for f in tracked_markdown():
            with open(os.path.join(ROOT, f), encoding="utf-8") as fh:
                body = fh.read()
            fm = frontmatter(body)
            if f == "index.md":  # bundle root: the one index allowed frontmatter (§11)
                if fm is None or not has_key(fm, "okf_version"):
                    bad.append(f"{f}: bundle-root index.md must declare okf_version")
                continue
            if os.path.basename(f) in RESERVED:
                if fm is not None:
                    bad.append(f"{f}: reserved OKF file must not carry frontmatter")
                continue
            if fm is None:
                bad.append(f"{f}: missing YAML frontmatter block")
            elif not has_key(fm, "type"):
                bad.append(f"{f}: frontmatter lacks a non-empty `type`")
        self.assertEqual(bad, [], "OKF conformance failures:\n" + "\n".join(bad))

    def test_parameters_tables_are_complete(self):
        """A `type: Parameters` doc carries exactly one pipe table, with exactly the
        pinned column set, and every cell of every data row filled.

        Exactly one row is skipped: the alignment row at offset 1, skipped **by
        position**, and it must actually be an alignment row. Every row from offset 2
        on is validated unconditionally.

        `regime` keeps a number inside the conditions it was measured under, without
        which a volume-tiered price and a queue-depth-specific latency read as
        contradictions. `as_of` and `source` are what a later decay recalibration
        measures against — an undated row can never be rechecked, so it fails here
        rather than rotting quietly.
        """
        config = load_config(self)
        classes = config.get("decay_classes")
        bad = []
        for f in tracked_markdown():
            with open(os.path.join(ROOT, f), encoding="utf-8") as fh:
                body = fh.read()
            fm = frontmatter(body)
            if fm is None or not PARAM_TYPE.search(fm):
                continue
            blocks = pipe_blocks(body)
            if len(blocks) != 1:
                bad.append(f"{f}: type Parameters needs exactly one pipe table, "
                           f"found {len(blocks)}")
                continue
            header = tuple(c.lower() for c in split_pipe_row(blocks[0][0]))
            if header != PARAM_COLUMNS:
                bad.append(f"{f}: header is {list(header)}, expected "
                           f"{list(PARAM_COLUMNS)}")
                continue
            if len(blocks[0]) < 2 or not ALIGN_ROW.match(blocks[0][1]):
                bad.append(f"{f}: table has no `|---|` alignment row under the header")
                continue
            for offset, line in enumerate(blocks[0][2:], start=2):
                cells = split_pipe_row(line)
                if len(cells) != len(PARAM_COLUMNS):
                    bad.append(f"{f} data row {offset}: {len(cells)} cells, expected "
                               f"{len(PARAM_COLUMNS)}")
                    continue
                empty = [c for c, v in zip(PARAM_COLUMNS, cells) if not v]
                for col in empty:
                    bad.append(f"{f} data row {offset}: empty `{col}`")
                if empty:
                    continue
                row = dict(zip(PARAM_COLUMNS, cells))
                if row["warrant"] not in WARRANTS:
                    bad.append(f"{f} data row {offset}: warrant `{row['warrant']}` "
                               f"not one of {sorted(WARRANTS)}")
                if classes and row["decay"] not in classes:
                    bad.append(f"{f} data row {offset}: decay `{row['decay']}` "
                               f"not in decay_classes")
        self.assertEqual(bad, [], "Parameters table defects:\n" + "\n".join(bad))

    def test_seeds_tables_are_complete(self):
        """A `type: Seeds` doc carries exactly one pipe table with the pinned columns,
        every cell filled, and an ISO date in `added`.

        The alignment row at offset 1 is skipped **by position** and must actually be an
        alignment row; every row from offset 2 on is validated unconditionally. `signal`
        is the column an author is most likely to leave blank and the one that cannot be
        reconstructed later, so a blank one fails here rather than rotting quietly.
        """
        bad = []
        for f in tracked_markdown():
            with open(os.path.join(ROOT, f), encoding="utf-8") as fh:
                body = fh.read()
            fm = frontmatter(body)
            if fm is None or not SEED_TYPE.search(fm):
                continue
            blocks = pipe_blocks(body)
            if len(blocks) != 1:
                bad.append(f"{f}: type Seeds needs exactly one pipe table, "
                           f"found {len(blocks)}")
                continue
            header = tuple(c.lower() for c in split_pipe_row(blocks[0][0]))
            if header != SEED_COLUMNS:
                bad.append(f"{f}: header is {list(header)}, expected "
                           f"{list(SEED_COLUMNS)}")
                continue
            if len(blocks[0]) < 2 or not ALIGN_ROW.match(blocks[0][1]):
                bad.append(f"{f}: table has no `|---|` alignment row under the header")
                continue
            for offset, line in enumerate(blocks[0][2:], start=2):
                cells = split_pipe_row(line)
                if len(cells) != len(SEED_COLUMNS):
                    bad.append(f"{f} seed row {offset}: {len(cells)} cells, expected "
                               f"{len(SEED_COLUMNS)}")
                    continue
                empty = [c for c, v in zip(SEED_COLUMNS, cells) if not v]
                for col in empty:
                    bad.append(f"{f} seed row {offset}: empty `{col}`")
                if empty:
                    continue
                row = dict(zip(SEED_COLUMNS, cells))
                if not ISO_DATE.match(row["added"]):
                    bad.append(f"{f} seed row {offset}: `added` is `{row['added']}`, "
                               f"expected YYYY-MM-DD")
        self.assertEqual(bad, [], "Seeds table defects:\n" + "\n".join(bad))

    def test_lake_citations_resolve(self):
        """Every `lake:<path>` citation resolves inside the configured lake root.

        Fails loudly when lake_root is unset but citations exist, and when the lake
        is not present at lake_root — a project corpus without its lake is broken
        by definition (single-machine design; see the kit spec)."""
        config = load_config(self)
        lake_root = config.get("lake_root")
        broken = []
        for f in tracked_markdown():
            with open(os.path.join(ROOT, f), encoding="utf-8") as fh:
                body = fh.read()
            for m in LAKE_REF.finditer(body):
                target = m.group(1).rstrip(".")
                if lake_root is None:
                    broken.append(f"{f}: lake:{target} but no lake_root configured")
                    continue
                if not os.path.exists(os.path.join(os.path.expanduser(lake_root), target)):
                    broken.append(f"{f} -> lake:{target}")
        self.assertEqual(broken, [], "unresolved lake citations:\n" + "\n".join(broken))

    def test_tags_are_registered(self):
        """Lake profile: every frontmatter tag is defined in terminology.md's
        '## Tag registry' section — one vocabulary, no silent splits."""
        config = load_config(self)
        if config.get("profile") != "lake":
            self.skipTest("tag registry is a lake-profile rule")
        with open(os.path.join(ROOT, "terminology.md"), encoding="utf-8") as fh:
            term = fh.read()
        section = term.split("## Tag registry", 1)
        registry = set()
        if len(section) == 2:
            for line in section[1].splitlines():
                if line.lstrip().startswith("-"):
                    registry.update(REGISTERED.findall(line))
        bad = []
        for f in tracked_markdown():
            with open(os.path.join(ROOT, f), encoding="utf-8") as fh:
                fm = frontmatter(fh.read())
            if not fm:
                continue
            m = FM_TAGS.search(fm)
            if not m:
                continue
            for tag in (t.strip() for t in m.group(1).split(",") if t.strip()):
                if tag not in registry:
                    bad.append(f"{f}: tag `{tag}` not in terminology.md tag registry")
        self.assertEqual(bad, [], "unregistered tags:\n" + "\n".join(bad))

    def test_index_is_fresh(self):
        """Lake profile: XREF.md matches what index.py would generate right now."""
        config = load_config(self)
        if config.get("profile") != "lake":
            self.skipTest("INDEX freshness is a lake-profile rule")
        import sys as _sys
        r = subprocess.run([_sys.executable, os.path.join(ROOT, "index.py"), "--check"])
        self.assertEqual(r.returncode, 0,
                         "XREF.md is stale — run: python3 index.py")


if __name__ == "__main__":
    unittest.main()
