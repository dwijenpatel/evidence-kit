import os
import tempfile
import unittest

from evidence_fetch.seeds import Seed, SeedFormatError, read_seeds

DOC = """---
type: Seeds
title: "Fetch queue"
timestamp: 2026-07-25
---

# Fetch queue

Some prose that mentions a | pipe outside a table.

| url | added | signal | question |
|---|---|---|---|
| https://example.com/a | 2026-07-25 | named in conversation | what does it cost |
| https://example.com/b | 2026-07-24 | seen in a talk | how fast is it |
"""


def write(tmp, text):
    path = os.path.join(tmp, "seeds.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


class ReadSeedsTests(unittest.TestCase):
    def test_reads_rows_in_document_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            seeds = read_seeds(write(tmp, DOC))
        self.assertEqual(len(seeds), 2)
        self.assertEqual(seeds[0], Seed("https://example.com/a", "2026-07-25",
                                        "named in conversation", "what does it cost"))
        self.assertEqual(seeds[1].url, "https://example.com/b")

    def test_case_insensitive_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = DOC.replace("| url | added |", "| URL | Added |")
            self.assertEqual(len(read_seeds(write(tmp, doc))), 2)

    def test_rejects_wrong_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = DOC.replace("type: Seeds", "type: Holdings")
            with self.assertRaises(SeedFormatError) as cm:
                read_seeds(write(tmp, doc))
            self.assertIn("type: Seeds", str(cm.exception))

    def test_rejects_reordered_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = DOC.replace("| url | added |", "| added | url |")
            with self.assertRaises(SeedFormatError) as cm:
                read_seeds(write(tmp, doc))
            self.assertIn("expected", str(cm.exception))

    def test_rejects_row_with_wrong_cell_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = DOC + "| https://example.com/c | 2026-07-25 | short |\n"
            with self.assertRaises(SeedFormatError) as cm:
                read_seeds(write(tmp, doc))
            self.assertIn("cells", str(cm.exception))

    def test_escaped_pipe_is_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = DOC.replace("what does it cost", r"cost \| latency")
            seeds = read_seeds(write(tmp, doc))
            self.assertEqual(seeds[0].question, "cost | latency")

    def test_empty_table_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = DOC.split("| https://example.com/a")[0]
            self.assertEqual(read_seeds(write(tmp, doc)), [])
