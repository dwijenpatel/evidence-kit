"""Corpus guard: the corpus stays navigable, whole, and OKF-conformant.

Every markdown link must resolve (relative, or bundle-absolute per OKF §5.1), the
load-bearing files named in tests/corpus_guard.json must exist, and every concept
document must carry OKF frontmatter with a non-empty `type` (OKF v0.1 §9). Stricter
than OKF's permissive consumer minimum on purpose: this guard runs on the producer
side. Part of the evidence-kit method; configure via corpus_guard.json, not by
editing this file.

Run from the corpus root: python3 -m unittest tests.test_reference -q
"""

import json
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINK = re.compile(r"\[[^\]]*\]\(([^)#\s]+?)(?:#[^)]*)?\)")
# OKF reserved filenames (§3.1): not concept documents, exempt from the `type` rule.
RESERVED = {"index.md", "log.md"}
TYPE_KEY = re.compile(r"^type:\s*\S", re.MULTILINE)
OKF_VERSION_KEY = re.compile(r"^okf_version:\s*\S", re.MULTILINE)


def frontmatter(body):
    """The text between the opening '---' fence and its closing fence, or None."""
    if not body.startswith("---\n"):
        return None
    end = body.find("\n---", 4)
    return None if end == -1 else body[4:end + 1]

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


def tracked_markdown():
    """Markdown files under version control; filesystem walk if git is absent."""
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
            if os.path.basename(f) in RESERVED:
                if f == "index.md":  # bundle root: the one index allowed frontmatter
                    if fm is None or not OKF_VERSION_KEY.search(fm):
                        bad.append(f"{f}: bundle-root index.md must declare okf_version")
                elif fm is not None:
                    bad.append(f"{f}: reserved OKF file must not carry frontmatter")
                continue
            if fm is None:
                bad.append(f"{f}: missing YAML frontmatter block")
            elif not TYPE_KEY.search(fm):
                bad.append(f"{f}: frontmatter lacks a non-empty `type`")
        self.assertEqual(bad, [], "OKF conformance failures:\n" + "\n".join(bad))


if __name__ == "__main__":
    unittest.main()
