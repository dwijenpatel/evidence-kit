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
