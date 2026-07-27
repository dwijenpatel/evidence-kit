# evidence-fetch

A polite fetcher with a byte-exact, content-addressed cache. It fetches what a
`Seeds` document queues and records one manifest entry per attempt; it never
extracts, parses, or edits a corpus's tracked files.

## Setup

```sh
uv sync --project fetcher
```

Tests (from the repository root — `-P` keeps the repo's own root `tests/`
package from shadowing `fetcher/tests`):

```sh
uv run --project fetcher python -P -m unittest discover -s fetcher/tests -t fetcher -q
```

## What it writes, and where

Exactly two things, both under the corpus you point it at:

- **`<cache-root>/sha256/<xx>/<digest>`** — raw response bytes, content-addressed
  by their SHA-256. Wire octets: a gzip body is stored compressed.
- **`manifest.jsonl`** — one JSON line per fetch attempt, append-only. A 503
  followed by a 200 is two lines; nothing ever edits a written line.

In the corpus's `.gitignore`, the cache directory is ignored by exactly one line
while `manifest.jsonl` stays tracked:

```
cache/
```

## Adding a seed

Edit the corpus's `seeds.md` by hand — one table row per source
(`| url | added | signal | question |`). No code runs; the fetcher does not need
to be running.
