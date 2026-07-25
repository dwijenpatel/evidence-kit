# Task 2 — `parameters-guard`

**Tier:** `code-complete`
**Discharges:** PRD acceptance criteria A0.2, A0.3, A0.4, A0.6

Teach the corpus guard to validate `Parameters` documents, and prove it fires. Two files
change: `templates/tests/test_reference.py` (the guard template that ships into every
corpus) and `tests/test_scaffold.py` (the kit-side smoke matrix that exercises the real
scaffold→write→guard path).

Standard library only — the guard must run on a bare machine (`CLAUDE.md` rule 1). Collect
every offender and assert once (rule 7). Assert on substrings, never whole sentences
(rule 8).

## Consumes

From Task 1, the pinned column set — restated here so this spec stands alone:

```
subject | parameter | value | unit | regime | as_of | warrant | decay | source
```

Existing names in `templates/tests/test_reference.py` this task builds on:

- `ROOT: str` — the corpus root directory.
- `FENCE: re.Pattern` — matches a leading YAML frontmatter fence.
- `frontmatter(body: str) -> str | None` — the text between the fences, or `None`.
- `tracked_markdown() -> list[str]` — repo-relative paths of tracked `*.md` files.

Existing names in `tests/test_scaffold.py` this task builds on:

- `run_scaffold(tmp: str, profile: str, extra: list[str] | None = None) -> str` — scaffolds
  a corpus, returns its path.
- `run_guard(corpus: str) -> subprocess.CompletedProcess` — runs the corpus guard there.
- `ScaffoldMatrix` — the `unittest.TestCase` with `self.tmp` set up and torn down.

## Provides

- Guard check `CorpusLinkTests.test_parameters_tables_are_complete`.
- Module-level `PARAM_COLUMNS: tuple[str, ...]` in the guard template.
- Helpers `split_pipe_row(line: str) -> list[str]` and
  `pipe_blocks(body: str) -> list[list[str]]` in the guard template.

---

## Step 1 — write the failing tests

Append to `tests/test_scaffold.py`, at module level immediately after the `KIT` assignment:

```python
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
```

Append these four methods to `class ScaffoldMatrix`:

```python
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
```

Run:

```
python3 -m unittest tests.test_scaffold -q
```

**Expected failure:** three of the four fail. `test_guard_accepts_a_complete_parameters_table`
passes vacuously (the guard has no opinion about Parameters docs yet, so it stays green);
the three rejection tests fail on `assertNotEqual(r.returncode, 0)` with `0 == 0`, because
nothing is checking the table.

## Step 2 — add the constants and helpers to the guard template

In `templates/tests/test_reference.py`, immediately after the existing `FENCE` assignment,
add:

```python
# A `type: Parameters` document is a cost/performance surface: one pipe table, pinned
# columns, warrant and decay carried per row.
PARAM_COLUMNS = ("subject", "parameter", "value", "unit", "regime",
                 "as_of", "warrant", "decay", "source")
PARAM_TYPE = re.compile(r"^type:\s*Parameters\s*$", re.MULTILINE)
ALIGN_ROW = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
CELL_SPLIT = re.compile(r"(?<!\\)\|")
```

Immediately after the existing `has_key` function, add:

```python
def split_pipe_row(line):
    """Cells of one markdown pipe row: outer pipes dropped, each cell trimmed.

    An escaped pipe (`\\|`) is cell content, not a separator, and is unescaped in the
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
```

The fence handling is not decoration. Without it, a Parameters document that illustrates
its own format inside a ``` fence would report `found 2` and fail — a false positive on a
document that is perfectly well formed.

## Step 3 — add the guard check

In `templates/tests/test_reference.py`, add this method to `class CorpusLinkTests`,
immediately after `test_okf_conformance` (it is a structural document check, and belongs
beside the other one):

```python
    def test_parameters_tables_are_complete(self):
        """A `type: Parameters` doc carries exactly one pipe table, with exactly the
        pinned column set, and every cell of every data row filled.

        `regime` keeps a number inside the conditions it was measured under, without
        which a volume-tiered price and a queue-depth-specific latency read as
        contradictions. `as_of` and `source` are what a later decay recalibration
        measures against — an undated row can never be rechecked, so it fails here
        rather than rotting quietly.
        """
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
            for offset, line in enumerate(blocks[0][1:], start=1):
                if ALIGN_ROW.match(line):
                    continue
                cells = split_pipe_row(line)
                if len(cells) != len(PARAM_COLUMNS):
                    bad.append(f"{f} data row {offset}: {len(cells)} cells, expected "
                               f"{len(PARAM_COLUMNS)}")
                    continue
                for col, cell in zip(PARAM_COLUMNS, cells):
                    if not cell:
                        bad.append(f"{f} data row {offset}: empty `{col}`")
        self.assertEqual(bad, [], "Parameters table defects:\n" + "\n".join(bad))
```

Run:

```
python3 -m unittest tests.test_scaffold -q
```

**Expected:** all tests pass, including the four added in Step 1 and the eight that
existed before.

## Worked example

Input document (`external/storage-prices.md` in a scaffolded corpus):

```markdown
---
type: Parameters
title: "Storage prices"
description: Smoke fixture.
timestamp: 2026-07-25
---

# Storage prices

| subject | parameter | value | unit | regime | as_of | warrant | decay | source |
|---|---|---|---|---|---|---|---|---|
| S3 Standard | storage price | 0.023 | USD/GB-month | us-east-1, first 50TB | 2026-07-25 | A4 | price-surface | [1] |

# Citations

[1] https://example.com/pricing
```

Guard result: exit `0`, no output.

Same document with the `as_of` cell emptied (`| 2026-07-25 |` → `|  |`):

Guard result: exit `1`, stderr containing

```
Parameters table defects:
external/storage-prices.md data row 2: empty `as_of`
```

Note `data row 2`, not `1`: the alignment row `|---|…|` is offset 1 and is skipped, so the
first data row is offset 2. This is intentional and matches what a reader counting lines in
the table sees.

## Error model

The guard reports; it never raises to the caller. Every defect is appended to `bad` and the
single `assertEqual(bad, [], …)` at the end fails once with all of them listed.

| Condition | Message substring |
|---|---|
| Frontmatter `type: Parameters`, no pipe table | `needs exactly one pipe table, found 0` |
| Two or more separate pipe tables | `needs exactly one pipe table, found 2` |
| Header column renamed, reordered, added, or dropped | `header is [...], expected [...]` |
| Data row with the wrong number of cells | `cells, expected 9` |
| Any empty cell | ``empty `<column>` `` |

A document without `type: Parameters` frontmatter is skipped entirely — this check has no
opinion about any other document type, and must not acquire one.

The template `_parameters.md.tmpl` is **not** scanned: `tracked_markdown()` globs `*.md`
and the template ends in `.tmpl`. This does NOT mean templates are exempt by rule — it
means they are not markdown documents. A `.md` file carrying `type: Parameters` is checked
wherever it lives.

## checks

```
python3 -m unittest tests.test_scaffold -q
grep -qF 'PARAM_COLUMNS' templates/tests/test_reference.py
grep -qF 'test_parameters_tables_are_complete' templates/tests/test_reference.py
grep -qF 'empty `as_of`' tests/test_scaffold.py
! grep -rn '/Users/' templates/ tests/
python3 -c "import ast,sys; ast.parse(open('templates/tests/test_reference.py').read())"
```
