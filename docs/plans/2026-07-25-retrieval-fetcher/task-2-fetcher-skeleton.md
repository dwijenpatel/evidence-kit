# Task 2 — fetcher skeleton, settings, cache layout, seed reader

**Tier:** `code-complete` · **PRD criteria:** A2 (layout half), A9 (config half), A10 (reader half)

Creates the `fetcher/` project and the two pure-function pieces everything else builds on:
the content-addressed cache path, and the reader for the `Seeds` document type from task 1.
No network code in this task — the spider is task 6.

## Files

| Path | Responsibility |
|---|---|
| `fetcher/pyproject.toml` (new) | uv project; the **only** place a dependency is declared |
| `fetcher/README.md` (new) | How an operator runs it |
| `fetcher/evidence_fetch/__init__.py` (new) | Empty package marker |
| `fetcher/evidence_fetch/cache.py` (new) | Content-addressed path computation |
| `fetcher/evidence_fetch/seeds.py` (new) | Parse a `type: Seeds` document into `Seed` records |
| `fetcher/evidence_fetch/settings.py` (new) | Scrapy settings — politeness and storage defaults |
| `fetcher/tests/__init__.py` (new) | Empty |
| `fetcher/tests/test_cache.py` (new) | Cache path tests |
| `fetcher/tests/test_seeds.py` (new) | Seed reader tests |
| `fetcher/tests/test_settings.py` (new) | Settings assertions — the values are behaviour |

**The repository root gains no dependency** (CLAUDE.md rule 13). Nothing under `fetcher/`
may be imported by `scaffold.py` or `templates/tests/test_reference.py`.

## Consumes

The `Seeds` document format from task 1 — pinned columns, in this order:

```
url | added | signal | question
```

Header compared case-insensitively; row 0 is the header, row 1 the alignment row, data from
row 2. A cell may contain `\|` as an escaped literal pipe.

## Provides

```python
# evidence_fetch/cache.py
def cache_relpath(sha256_hex: str) -> str
    """'sha256/ab/abcdef…' — relative to the cache root. Raises ValueError on a
    string that is not 64 lowercase hex characters."""

def cache_path(cache_root: str, sha256_hex: str) -> str
    """Absolute path: os.path.join(cache_root, cache_relpath(sha256_hex))."""

def write_artifact(cache_root: str, body: bytes) -> tuple[str, str]
    """Write body to its content-addressed path, creating parents. Returns
    (sha256_hex, relpath). Idempotent: an existing identical file is left alone."""

# evidence_fetch/seeds.py
@dataclass(frozen=True)
class Seed:
    url: str
    added: str      # ISO date, as written
    signal: str
    question: str

def read_seeds(path: str) -> list[Seed]
    """Parse a `type: Seeds` document. Raises SeedFormatError on a malformed table."""

class SeedFormatError(ValueError): ...
```

## Step 1 — `fetcher/pyproject.toml`

```toml
[project]
name = "evidence-fetch"
version = "0.1.0"
description = "Polite fetcher with a byte-exact cache, for an evidence corpus."
requires-python = ">=3.12"
dependencies = ["scrapy>=2.17"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["evidence_fetch"]
```

Verify with `uv sync --project fetcher`, then `uv run --project fetcher python -c "import
scrapy; print(scrapy.__version__)"`.

## Step 2 — `cache.py`

Write the failing test first, in `fetcher/tests/test_cache.py`:

```python
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
```

`uv run --project fetcher python -m unittest discover -s fetcher/tests -t fetcher -q` →
fails with `ModuleNotFoundError: No module named 'evidence_fetch.cache'`.

Now the implementation, `fetcher/evidence_fetch/cache.py`:

```python
"""Content-addressed artifact storage.

The path is derived from the bytes, so identical fetches — across time or across
sources — collapse to one file, and a manifest entry's `raw_bytes_sha256` is enough
to locate the artifact without consulting an index.
"""

import hashlib
import os
import re

HEX64 = re.compile(r"^[0-9a-f]{64}$")


def cache_relpath(sha256_hex: str) -> str:
    """Cache-root-relative path for a digest: sha256/<first-2>/<full>.

    Sharded on the first two hex characters because a flat directory of tens of
    thousands of entries is slow to list on most filesystems. No extension: the path
    must stay stable, and an extension would encode a guess about content into it.
    """
    if not HEX64.match(sha256_hex):
        raise ValueError(
            f"not a lowercase 64-character hex digest: {sha256_hex!r}")
    return f"sha256/{sha256_hex[:2]}/{sha256_hex}"


def cache_path(cache_root: str, sha256_hex: str) -> str:
    """Absolute path of the artifact with this digest under cache_root."""
    return os.path.join(cache_root, cache_relpath(sha256_hex))


def write_artifact(cache_root: str, body: bytes) -> tuple[str, str]:
    """Store body at its content-addressed path; return (digest, relpath).

    Idempotent by construction: if the file exists its contents are already these
    bytes, so it is left untouched rather than rewritten. That keeps mtime meaningful
    as "first seen" and makes a re-run cheap.
    """
    digest = hashlib.sha256(body).hexdigest()
    rel = cache_relpath(digest)
    full = os.path.join(cache_root, rel)
    if not os.path.exists(full):
        os.makedirs(os.path.dirname(full), exist_ok=True)
        tmp = full + ".part"
        with open(tmp, "wb") as fh:
            fh.write(body)
        os.replace(tmp, full)        # atomic: a reader never sees a partial artifact
    return digest, rel
```

The `.part`-then-`os.replace` is not ceremony: the fetcher is interruptible by design
(A9), and a half-written artifact whose name claims a digest it does not have would be
undetectable corruption.

Re-run the tests → 5 pass.

## Step 3 — `seeds.py`

Failing test first, `fetcher/tests/test_seeds.py`:

```python
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
```

Implementation, `fetcher/evidence_fetch/seeds.py`:

```python
"""Reader for the `Seeds` document type.

A seed list is edited by hand, with no code run and the fetcher not running, so this
parser is deliberately forgiving about everything except the shape it must trust:
the column set and their order.
"""

import re
from dataclasses import dataclass

COLUMNS = ("url", "added", "signal", "question")
FENCE = re.compile(r"\A---[ \t]*\r?\n(.*?)^---[ \t]*\r?$", re.DOTALL | re.MULTILINE)
SEED_TYPE = re.compile(r"""^type:\s*["']?Seeds["']?\s*(#.*)?$""", re.MULTILINE)
ALIGN_ROW = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
CELL_SPLIT = re.compile(r"(?<!\\)\|")


class SeedFormatError(ValueError):
    """The document is not a well-formed Seeds table."""


@dataclass(frozen=True)
class Seed:
    url: str
    added: str
    signal: str
    question: str


def _cells(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [c.replace("\\|", "|").strip() for c in CELL_SPLIT.split(body)]


def _table_lines(body: str) -> list[str]:
    """Pipe-table lines outside fenced code blocks, in document order."""
    lines, fenced = [], False
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced and line.lstrip().startswith("|"):
            lines.append(line)
    return lines


def read_seeds(path: str) -> list[Seed]:
    """Parse a Seeds document into Seed records, in document order."""
    with open(path, encoding="utf-8") as fh:
        body = fh.read()
    m = FENCE.match(body)
    if m is None or not SEED_TYPE.search(m.group(1)):
        raise SeedFormatError(f"{path}: frontmatter must declare `type: Seeds`")
    rows = _table_lines(body)
    if not rows:
        raise SeedFormatError(f"{path}: no pipe table found")
    header = tuple(c.lower() for c in _cells(rows[0]))
    if header != COLUMNS:
        raise SeedFormatError(
            f"{path}: header is {list(header)}, expected {list(COLUMNS)}")
    if len(rows) < 2 or not ALIGN_ROW.match(rows[1]):
        raise SeedFormatError(f"{path}: no `|---|` alignment row under the header")
    seeds = []
    for offset, line in enumerate(rows[2:], start=2):
        cells = _cells(line)
        if len(cells) != len(COLUMNS):
            raise SeedFormatError(
                f"{path} row {offset}: {len(cells)} cells, expected {len(COLUMNS)}")
        seeds.append(Seed(*cells))
    return seeds
```

Note the alignment row is skipped **by position**, not by pattern — a row of dashes that
is actually data must not be silently swallowed. (This is finding F3 from the parameters
plan, applied at authoring time rather than rediscovered.)

Re-run → 7 pass.

## Step 4 — `settings.py`

```python
"""Scrapy settings: politeness first, storage second.

Every value here is a PRD or CLAUDE.md constraint, not a tuning preference. The
`Crawl-delay` enforcement these settings cannot express lives in the middleware added
by task 3 — Scrapy parses Crawl-delay via Protego and discards it.
"""

BOT_NAME = "evidence-fetch"
SPIDER_MODULES = ["evidence_fetch.spiders"]
NEWSPIDER_MODULE = "evidence_fetch.spiders"

# --- politeness (CLAUDE.md rule 17) -----------------------------------------
ROBOTSTXT_OBEY = True
# One connection per host, always. The comment sits ABOVE the assignment on purpose:
# the gating check anchors the whole line (`^CONCURRENT_REQUESTS_PER_DOMAIN = 1$`),
# and a trailing comment turns that check red against this task's own code (R7).
CONCURRENT_REQUESTS_PER_DOMAIN = 1
CONCURRENT_REQUESTS = 8                 # across hosts; politeness is per-host
DOWNLOAD_DELAY = 5.0                    # floor where no Crawl-delay is declared

# A1 requires "waits >= the declared Crawl-delay". Both of the following would
# break that, and both were measured breaking it — see plan.md Amendment 1.
#
#   AUTOTHROTTLE_ENABLED = True   ->  AutoThrottle's _adjust_delay runs on every
#       response and ends `slot.delay = new_delay`, clamped to a GLOBAL floor of
#       DOWNLOAD_DELAY. A per-host 7.0 is dragged back to 5.0 by the FIRST 200.
#       There is no per-host mindelay, so no configuration rescues this.
#   RANDOMIZE_DOWNLOAD_DELAY = True  ->  Slot.download_delay() returns
#       uniform(0.5*delay, 1.5*delay); at delay=7.0 the floor is 3.5s.
#       A declared delay is a MINIMUM, and jitter below a minimum is a violation.
AUTOTHROTTLE_ENABLED = False
RANDOMIZE_DOWNLOAD_DELAY = False

# The rule-17 ceiling. Deliberately NOT AUTOTHROTTLE_MAX_DELAY: that setting is
# inert once AutoThrottle is off, and reading an inert setting is a trap for the
# next person who turns AutoThrottle back on. Task 3 reads this name.
CRAWL_DELAY_CEILING = 60.0

# Identify the crawler. RFC 9309 §2.2.1: robots.txt groups match on a product token,
# so an unidentified crawler falls under the most restrictive `*` group.
USER_AGENT = "evidence-fetch/0.1 (+{contact})"

# --- storage ----------------------------------------------------------------
# DummyPolicy serves every STORED response regardless of HTTP cache semantics, which
# is what "resume without refetching what I already have" means here (A9). This is a
# fetch-avoidance layer only; the durable artifact is the content-addressed file the
# manifest points at, so HTTPCACHE_DIR may be deleted at any time without data loss.
HTTPCACHE_ENABLED = True
HTTPCACHE_POLICY = "scrapy.extensions.httpcache.DummyPolicy"
HTTPCACHE_EXPIRATION_SECS = 0           # 0 = never expire
# What gets STORED is filtered: DummyPolicy.should_cache_response consults this list
# (probed, 2.17.0). Retryable statuses must never be stored -- DummyPolicy serves a
# stored 403 to every later request for that URL, so the spider's retries (task 6
# item 7) would be answered from disk, flagged "cached", skipped by the recorder,
# and backoff would never touch the wire (plan-review R4; probed: 4 callbacks, ONE
# wire hit). The list must equal backoff.RETRYABLE (task 4); a test there asserts
# the equality, because this module is built before backoff.py exists and must not
# import it. The comment sits above the line for the same R7 reason as above.
HTTPCACHE_IGNORE_HTTP_CODES = [403, 408, 429, 500, 502, 503, 504, 522, 524]
# A RELATIVE value here resolves through scrapy.utils.project.data_path to
# <cwd>/.scrapy/httpcache -- outside the cache root and outside the one
# `cache/` ignore line. The CLI (task 6) overrides this at runtime to
# <abspath(cache-root)>/httpcache; data_path passes absolute paths through
# unchanged. This default is a fallback, never the operating value. (#15)
HTTPCACHE_DIR = "httpcache"

# --- retry ------------------------------------------------------------------
# The SPIDER is the only retry mechanism (task 6 item 7): classify_status decides,
# backoff_delay/parse_retry_after pace. Scrapy's RetryMiddleware must stay off --
# its source contains zero occurrences of "Retry-After", so with it on, a 503
# carrying `Retry-After: 120` is retried at the slot delay and the header is never
# honoured; worse, the callback never sees a retryable response while its retries
# remain, so the spider's own retry logic becomes dead code. (Plan-review F5.)
RETRY_ENABLED = False

TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
# Deliberately absent — both are `scrapy startproject` template leftovers, and neither
# is a PRD or CLAUDE.md constraint (the docstring above says every value here is one):
#   REQUEST_FINGERPRINTER_IMPLEMENTATION — removed from scrapy; 2.17.0 contains ZERO
#     occurrences of the name, reads it nowhere, warns never (probed). Only
#     REQUEST_FINGERPRINTER_CLASS exists, and its default is correct.
#   FEED_EXPORT_ENCODING — a real setting, but consumed only by feed exports, and
#     CLAUDE.md rule 14 forbids this component a third write path.
```

`USER_AGENT` carries a `{contact}` placeholder that the spider (task 6) formats from a
required `--contact` argument. **This does NOT mean the literal string `{contact}` is ever
sent**; task 6 fails fast when no contact is supplied.

## Step 4b — `fetcher/tests/test_settings.py`

The settings above are behaviour, and text-presence greps cannot gate behaviour — the
review measured `grep -qF '… = 1'` passing on `= 16`. These tests import and assert.

```python
import unittest

from evidence_fetch import settings


class PolitenessSettingsTests(unittest.TestCase):
    def test_politeness_settings_hold(self):
        self.assertEqual(settings.CONCURRENT_REQUESTS_PER_DOMAIN, 1)
        self.assertTrue(settings.ROBOTSTXT_OBEY)
        self.assertGreaterEqual(settings.DOWNLOAD_DELAY, 5.0)
        self.assertEqual(settings.CRAWL_DELAY_CEILING, 60.0)

    def test_settings_that_defeat_a1_stay_off(self):
        # AutoThrottle rewrites slot.delay with a global DOWNLOAD_DELAY floor;
        # randomize jitters below a declared minimum. Both measured breaking A1.
        self.assertFalse(settings.AUTOTHROTTLE_ENABLED)
        self.assertFalse(settings.RANDOMIZE_DOWNLOAD_DELAY)

    def test_scrapy_retry_stays_off(self):
        # The spider owns retry so Retry-After is honoured (plan-review F5).
        self.assertFalse(settings.RETRY_ENABLED)
        self.assertFalse(hasattr(settings, "RETRY_HTTP_CODES"))
```

Run → 3 pass. These are the real gate on the settings; the anchored greps in `## Checks`
are redundant tripwires that catch a hand-edit without a test run.

## Step 5 — `fetcher/README.md`

Document, in this order: `uv sync --project fetcher`; where the cache and manifest are
written; that a seed is added by editing `seeds.md` by hand; and that the cache directory
must be ignored by exactly one `.gitignore` line while `manifest.jsonl` is tracked. State
the `.gitignore` line verbatim:

```
cache/
```

## Error model

| Failure | Raises | Required message substring |
|---|---|---|
| Digest is not 64 lowercase hex | `ValueError` | `not a lowercase 64-character hex digest` |
| Frontmatter lacks `type: Seeds` | `SeedFormatError` | `type: Seeds` |
| Header drifted or reordered | `SeedFormatError` | `expected` |
| No table at all | `SeedFormatError` | `no pipe table found` |
| Missing alignment row | `SeedFormatError` | ``no `\|---\|` alignment row`` |
| Row cell count wrong | `SeedFormatError` | `cells` |

Substrings only (CLAUDE.md rule 8).

## Checks

```
test -f fetcher/pyproject.toml
test -f fetcher/README.md
grep -qF 'scrapy>=2.17' fetcher/pyproject.toml
grep -qE '^CONCURRENT_REQUESTS_PER_DOMAIN = 1$' fetcher/evidence_fetch/settings.py
grep -qE '^CRAWL_DELAY_CEILING = 60.0$' fetcher/evidence_fetch/settings.py
grep -qE '^AUTOTHROTTLE_ENABLED = False$' fetcher/evidence_fetch/settings.py
grep -qE '^RANDOMIZE_DOWNLOAD_DELAY = False$' fetcher/evidence_fetch/settings.py
grep -qE '^RETRY_ENABLED = False$' fetcher/evidence_fetch/settings.py
grep -qE '^HTTPCACHE_IGNORE_HTTP_CODES = \[403, 408, 429, 500, 502, 503, 504, 522, 524\]$' fetcher/evidence_fetch/settings.py
! grep -qE '^RETRY_HTTP_CODES' fetcher/evidence_fetch/settings.py
grep -qF 'test_settings_that_defeat_a1_stay_off' fetcher/tests/test_settings.py
grep -qF 'test_scrapy_retry_stays_off' fetcher/tests/test_settings.py
test -f scaffold.py
test -d templates/
! grep -rn 'evidence_fetch' scaffold.py templates/
uv sync --project fetcher
uv run --project fetcher python -m unittest discover -s fetcher/tests -t fetcher -q
python3 -m unittest tests.test_scaffold -q
```

The `! grep -rn 'evidence_fetch' scaffold.py templates/` check enforces CLAUDE.md rule 13
mechanically: the root must stay runnable with no install step, and the cheapest way for
that to break is an import added for convenience. The `test -f scaffold.py` / `test -d
templates` pair ahead of it exists so the negative grep can never pass vacuously against
paths that stopped existing (#13) — the pairing rule every other negative check in this
plan already follows.
