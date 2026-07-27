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

## Running it

From the repository root:

```sh
uv run --project fetcher python -m evidence_fetch \
    --seeds <path to a Seeds document> \
    --cache-root <dir> \
    --manifest <path to manifest.jsonl> \
    --contact <URL or mailto: for the User-Agent> \
    [--jobdir <dir>]        # default: <cache-root>/.jobdir
    [--limit N]             # stop scheduling new seeds after N 2xx seed fetches
```

`--contact` is required: it fills the User-Agent so site operators can reach
you, and robots.txt matches crawlers by that product token. Exit codes: **0**
for every completed crawl (a host that ended `blocked` is an attempt-sequence
outcome, not a run failure), **2** for startup failures (missing/malformed
seeds, a non-fetchable seed URL, missing `--contact`, unwritable cache root)
before any network call, **1** if the crawl stopped on a manifest schema
violation. `<cache-root>/httpcache/` and `<cache-root>/.jobdir/` are
disposable — deleting them costs at most a refetch.

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
