"""Corpus guard: the corpus stays navigable and whole.

Every relative markdown link must resolve, and the load-bearing files named in
tests/corpus_guard.json must exist. Portable edition of the outrigger corpus guard
(evidence-kit); configure via corpus_guard.json, not by editing this file.

Run from the corpus root: python3 -m unittest tests.test_reference -q
"""

import json
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINK = re.compile(r"\[[^\]]*\]\(([^)#\s]+?)(?:#[^)]*)?\)")

with open(os.path.join(ROOT, "tests", "corpus_guard.json"), encoding="utf-8") as fh:
    CONFIG = json.load(fh)


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
        files = tracked_markdown()
        self.assertGreaterEqual(
            len(files), CONFIG["min_markdown_files"], "the corpus lost its content?"
        )
        for anchor in CONFIG["required"]:
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
                if not os.path.exists(os.path.join(base, target)):
                    broken.append(f"{f} -> {target}")
        self.assertEqual(broken, [], "broken relative links:\n" + "\n".join(broken))


if __name__ == "__main__":
    unittest.main()
