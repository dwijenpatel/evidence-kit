# Task 1 — `Seeds` document type

**Tier:** `code-complete` · **PRD criteria:** A10 (format half)

A corpus needs a hand-editable list of what to fetch. PRD §11 makes this permanent: the
operator seeds conversationally, and automation expands from seeds rather than originating
them. So the format must be editable **with no code run and the fetcher not running**, and
each seed must carry the signal that prompted it — a dated record of what people are paying
attention to is a weak leading indicator of domain growth, and it cannot be reconstructed
later.

This task adds the doc type and its guard. It writes no fetcher code.

## Files

| Path | Responsibility |
|---|---|
| `templates/corpus/_seeds.md.tmpl` (new) | Pass-time skeleton an operator copies to `<corpus>/seeds.md` |
| `method/CONVENTIONS.md` (modify) | Register `Seeds` in the type vocabulary; add the authoring rule |
| `templates/tests/test_reference.py` (modify) | Add `test_seeds_tables_are_complete` |
| `tests/test_scaffold.py` (modify) | Five new fixtures |

`scaffold.py` is **not** modified. `_seeds.md.tmpl` is `_`-prefixed, so `render_tree` skips
it by prefix (CLAUDE.md rule 4). Relying on that is correct, not a shortcut.

## Consumes

From `templates/tests/test_reference.py`, already present — do not redefine:

```python
def frontmatter(body): ...          # -> str | None, text between the --- fences
def split_pipe_row(line): ...       # -> list[str], outer pipes dropped, cells trimmed
def pipe_blocks(body): ...          # -> list[list[str]], fence-aware runs of pipe lines
def tracked_markdown(): ...         # -> list[str], repo-relative paths
def load_config(testcase): ...      # -> dict, tests/corpus_guard.json
ALIGN_ROW = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
```

From `tests/test_scaffold.py`, already present:

```python
def run_scaffold(tmp, profile, extra=None): ...   # -> corpus path
def run_guard(corpus): ...                        # -> CompletedProcess
```

## Provides

- Document type `Seeds`, selected by frontmatter `type: Seeds` (quoted or unquoted).
- Pinned column set, used by task 2's reader:
  `url | added | signal | question`
- `templates/corpus/_seeds.md.tmpl`

## Step 1 — the template

Create `templates/corpus/_seeds.md.tmpl` with exactly this content:

```markdown
---
type: Seeds
title: <what this seed list feeds>
description: <one-line summary of the queue's current focus>
timestamp: <date last edited>
---

# <what this seed list feeds>

**How to use.** Add a row by hand. No code is run and the fetcher need not be running. A
row is a request to fetch, not a claim about the world — nothing here is evidence until it
has been fetched and graded.

| url | added | signal | question |
|---|---|---|---|
| <the exact URL to fetch> | <YYYY-MM-DD> | <what prompted this — the conversation, talk, post, or observation> | <what this source should help answer> |

<prose: what this batch of seeds is chasing, and anything a later reader needs to know about
why these sources and not others.>
```

The `signal` column is the load-bearing one and the easiest to leave blank. It is validated
non-empty for that reason.

## Step 2 — `method/CONVENTIONS.md`

**2a.** In the "OKF alignment" section, find this exact text:

```
  `Internal Evidence` · `Distilled Index` (distilled/README) · `Distilled` (the two Tier-A
  docs) · `Parameters` (a cost/performance surface: one table, warrant and decay per row).
```

Replace with:

```
  `Internal Evidence` · `Distilled Index` (distilled/README) · `Distilled` (the two Tier-A
  docs) · `Parameters` (a cost/performance surface: one table, warrant and decay per row) ·
  `Seeds` (a fetch queue: one table, one row per source to retrieve).
```

**2b.** At the end of the "Document conventions" section, after the `Parameters` bullet,
append this bullet:

```markdown
- **`Seeds` documents** carry exactly one pipe table, whose header is these four names in
  this order — `url | added | signal | question`, compared case-insensitively — with an
  alignment row directly beneath it and every cell of every data row non-empty. `added` is
  an ISO date (`YYYY-MM-DD`). A cell may not contain `|` (escape it `\|`). A seed row is a
  **request to fetch, not a claim**: it carries no warrant and enters no distillation. The
  `signal` column records what prompted the seed — the conversation, talk, or observation —
  because a dated record of what people are attending to is a weak leading indicator of
  where a domain is growing, and it cannot be reconstructed after the fact. The corpus guard
  enforces the shape. The pass-time skeleton is `templates/corpus/_seeds.md.tmpl`.
```

## Step 3 — the guard check

In `templates/tests/test_reference.py`, after the `PARAM_TYPE` line, add:

```python
SEED_COLUMNS = ("url", "added", "signal", "question")
SEED_TYPE = re.compile(r"""^type:\s*["']?Seeds["']?\s*(#.*)?$""", re.MULTILINE)
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
```

Then add this method to `CorpusLinkTests`, immediately after
`test_parameters_tables_are_complete`:

```python
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
```

**This does NOT mean** the guard validates that `url` parses as a URL. A seed may name a
source that is not yet a fetchable URL ("the pricing page linked from X's docs"); narrowing
that is task 2's problem, not the guard's.

## Step 4 — fixtures

In `tests/test_scaffold.py`, after the existing `PARAM_ROW` constant, add:

```python
SEED_HEADER = ("| url | added | signal | question |\n"
               "|---|---|---|---|\n")
SEED_ROW = ("| https://example.com/pricing | 2026-07-25 | operator noticed it in a "
            "discussion | what does storage cost per GB-month |\n")


def write_seeds(corpus, row, header=SEED_HEADER):
    """Write a Seeds doc into a scaffolded corpus; return its path."""
    path = os.path.join(corpus, "seeds.md")
    with open(path, "w") as fh:
        fh.write('---\ntype: Seeds\ntitle: "Fetch queue"\n'
                 'description: Smoke fixture.\ntimestamp: 2026-07-25\n---\n\n'
                 "# Fetch queue\n\n" + header + row + "\n")
    return path
```

Then add these five tests to the same class as the Parameters tests:

```python
    def test_guard_accepts_a_complete_seeds_table(self):
        corpus = run_scaffold(self.tmp, "standalone")
        write_seeds(corpus, SEED_ROW)
        self.assertEqual(run_guard(corpus).returncode, 0)

    def test_guard_rejects_seed_row_missing_signal(self):
        corpus = run_scaffold(self.tmp, "standalone")
        write_seeds(corpus, SEED_ROW.replace(
            "| operator noticed it in a discussion |", "|  |"))
        r = run_guard(corpus)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("empty `signal`", r.stderr + r.stdout)

    def test_guard_rejects_seed_row_with_non_iso_added(self):
        corpus = run_scaffold(self.tmp, "standalone")
        write_seeds(corpus, SEED_ROW.replace("| 2026-07-25 |", "| last Tuesday |"))
        r = run_guard(corpus)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("expected YYYY-MM-DD", r.stderr + r.stdout)

    def test_guard_rejects_seeds_header_reordered(self):
        corpus = run_scaffold(self.tmp, "standalone")
        write_seeds(corpus, SEED_ROW,
                    header=SEED_HEADER.replace("| added | signal |",
                                               "| signal | added |"))
        r = run_guard(corpus)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("expected", r.stderr + r.stdout)

    def test_guard_selects_seeds_doc_with_quoted_type(self):
        corpus = run_scaffold(self.tmp, "standalone")
        path = write_seeds(corpus, SEED_ROW.replace("| 2026-07-25 |", "|  |"))
        with open(path) as fh:
            doc = fh.read()
        with open(path, "w") as fh:
            fh.write(doc.replace("type: Seeds", 'type: "Seeds"'))
        r = run_guard(corpus)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("empty `added`", r.stderr + r.stdout)
```

## Worked example

Input `seeds.md` body:

```
| url | added | signal | question |
|---|---|---|---|
| https://fly.io/docs/about/pricing/ | 2026-07-25 | operator named it as an emergent provider | what axis does it price on |
| https://vercel.com/pricing | 2026-07-25 |  | how does egress pricing compare |
```

The guard exits 1 and its failure output **ends with** these two lines:

```
Seeds table defects:
seeds.md seed row 3: empty `signal`
```

**This is a substring contract, not the whole output** — `unittest` has
`longMessage = True`, so `assertEqual(bad, [], …)` prints its standard list diff first and
appends the custom message after `" : "`. A test that asserts the exact full output rejects
the very implementation this document specifies; assert with `assertIn`, per rule 8 and the
Step 4 fixtures.

Row 2 passes. The offset is a **block offset** — the header is row 0, the alignment row is
row 1, so the first data row is row 2. This matches the `Parameters` check exactly and is
deliberate.

## Error model

The check reports every offender and asserts once (CLAUDE.md rule 7). Required message
substrings, which tests assert on (rule 8 — substrings, never whole sentences):

| Condition | Substring |
|---|---|
| Blank cell | ``empty `<column>` `` |
| `added` not ISO | `expected YYYY-MM-DD` |
| Header drift or reorder | `expected` followed by the column list |
| Not exactly one table | `needs exactly one pipe table` |
| Missing alignment row | ``no `|---|` alignment row`` |

## Checks

```
test -f templates/corpus/_seeds.md.tmpl
grep -qF '| url | added | signal | question |' templates/corpus/_seeds.md.tmpl
grep -qF '`Seeds` (a fetch queue' method/CONVENTIONS.md
grep -qF 'carry exactly one pipe table' method/CONVENTIONS.md
grep -qF 'SEED_COLUMNS' templates/tests/test_reference.py
grep -qF 'test_seeds_tables_are_complete' templates/tests/test_reference.py
grep -qF 'test_guard_rejects_seed_row_missing_signal' tests/test_scaffold.py
grep -qF 'test_guard_rejects_seed_row_with_non_iso_added' tests/test_scaffold.py
! grep -rEn --exclude-dir=__pycache__ '/Users/|/home/|/Volumes/|~/|repos/evidence-|\bidea-gen\b' method/ templates/ tests/
python3 -c "import ast; ast.parse(open('templates/tests/test_reference.py').read())"
python3 -m unittest tests.test_scaffold -q
```

The `--exclude-dir=__pycache__` is required, not optional: the unittest run above compiles
the test module and writes `.pyc` files whose `co_filename` embeds an absolute path. Without
the exclusion this check fails on a correct implementation. (Learned the hard way in the
parameters plan, finding F1.)
