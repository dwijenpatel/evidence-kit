# Task 1 — `parameters-template`

**Tier:** `code-complete`
**Discharges:** PRD acceptance criteria A0.1, A0.5, A0.6

Add a pass-time template for a new document type, `Parameters`: a cost/performance table
whose every row carries its own warrant, decay class, measurement regime, and date. Then
make the four documents that describe the kit's vocabulary agree with it — `CLAUDE.md`
rule 11 requires `method/`'s three files and `SKILL.md` to stay mutually consistent.

**Do not modify `scaffold.py`.** `render_tree` skips files whose name starts with `_`, so a
pass-time template needs no scaffolder change. Adding one would ship a literal `{{…}}`
placeholder or an unwanted file into every scaffolded corpus.

## Pinned column set

Exactly these nine, in exactly this order. Operator-ratified 2026-07-25; this is a one-way
door.

```
subject | parameter | value | unit | regime | as_of | warrant | decay | source
```

## Provides

- `templates/corpus/external/_parameters.md.tmpl` — the pass-time skeleton, containing the
  header row above verbatim.
- The document type name `Parameters`, registered in `method/CONVENTIONS.md`'s type
  vocabulary.
- Five decay class names usable in the `decay` column: `price-surface`, `perf-envelope`,
  `media-generation`, `spec-standard`, `adoption-curve`.

## Consumes

Nothing from another task.

---

## Step 1 — create `templates/corpus/external/_parameters.md.tmpl`

New file. Angle-bracket prose is the pass-time authoring instruction, matching the style of
the sibling `_holdings.md.tmpl`. Note the escaped pipes (`\|`) inside the example row's
`warrant` cell — an unescaped `|` there would create a tenth column.

```markdown
---
type: Parameters
title: <the hierarchy or surface this table covers>
description: <one-line summary of what is measured here>
tags: [<topical tags>]
timestamp: <pass date>
grade: <retrieval | adversarial>
---

# <the hierarchy or surface this table covers>

**Provenance.** <agent count/models · what was fanned out · what was mirrored (mirror
directory) · what the grade licenses — for retrieval: "nothing here entered distilled/">

**Scope.** <which hierarchy or surface this covers · which tiers are in · which are
deliberately out and why>

| subject | parameter | value | unit | regime | as_of | warrant | decay | source |
|---|---|---|---|---|---|---|---|---|
| <tier or part> | <what is measured> | <number> | <unit> | <the conditions the number was measured under> | <YYYY-MM-DD> | <A1 \| A2 \| A3 \| A4 \| M \| B \| C> | <decay class> | <[n] §sec — a numbered entry in this document's # Citations section> |

<prose: what the ratios between these rows mean, what moved since the last pass, and which
rows sit near a recheck trigger. Reasoning lives here; numbers live in the table.>

# Citations

[1] <primary URL — plus mirror path where captured>
```

**Every cell is mandatory.** A row with an empty cell fails the corpus guard (Task 2).
`as_of` and `source` are the two that make later recalibration possible at all: a decay
half-life is learned by re-fetching a source and measuring what moved, which an undated or
unsourced row cannot support.

**A cell may not contain `|`.** Escape it as `\|`, as the example row does.

**`warrant` is one of `A1` `A2` `A3` `A4` `M` `B` `C`.** `A1`–`A4` and `M` are the Tier-A
warrants from `GRADING.md`. `B` means directional — no Tier-A warrant applies — and `C`
means framing only. Both exist because most substrate facts are Tier B by construction
(single-source vendor benchmarks, official *mechanism* claims, derived ratios), and without
them the column has no legal value for the majority of rows. A **derived** row carries the
weakest warrant among its inputs and states the derivation in `regime`; it does not inherit
`A4` from an official input, because "import the mechanism, never the magnitude" makes a
derived ratio a new claim.

**`source` is a citation index, never a cross-corpus reference.** Write `[n]`, pointing at
this document's `# Citations` section, with a `§` where the entry needs one. Do **not**
write a `lake:` citation in this cell. The corpus guard's pre-existing
`test_lake_citations_resolve` matches any `lake:<path>` string and resolves it against
`lake_root` in `tests/corpus_guard.json`, and `scaffold.py` writes `lake_root` only for the
`project` profile — which skips the `external/` tree entirely. So in a `standalone` or
`lake` corpus, where this template's documents live, a `lake:` source cell fails the guard
with `lake:<path> but no lake_root configured`: an unrelated check killing a well-formed
Parameters doc.

This does NOT mean `lake:` citations are banned from Parameters docs everywhere — in a
`project` corpus, where `lake_root` is configured, they resolve normally. And it is NOT
fixed by writing `lake:<path>` with angle brackets: brackets protect only the template
text, never an author who substitutes a real path.

**One table per document.** `subject` and `parameter` already separate rows; a second table
would be a redundant axis, and the guard rejects it. Tables inside a fenced code block do
not count toward that limit.

**The template file itself is never validated.** The corpus guard globs `*.md`, and this
file ends in `.tmpl`, so its angle-bracket cells are not "empty cells" and do not need
filling. This does NOT mean templates are exempt by rule — it means a template is not a
markdown document. Any `.md` file carrying `type: Parameters` is checked wherever it lives.

## Step 2 — register the type in `method/CONVENTIONS.md`

Find this text under "OKF alignment (the corpus is a knowledge bundle)":

```
  `Internal Evidence` · `Distilled Index` (distilled/README) · `Distilled` (the two Tier-A
  docs). Unknown types are legal OKF; these are the ones consumers of an evidence corpus
  can rely on.
```

Replace with:

```
  `Internal Evidence` · `Distilled Index` (distilled/README) · `Distilled` (the two Tier-A
  docs) · `Parameters` (a cost/performance surface: one table, warrant and decay per row).
  Unknown types are legal OKF; these are the ones consumers of an evidence corpus can rely
  on.
```

## Step 3 — add the authoring rule to `method/CONVENTIONS.md`

Find this bullet, the last one under "## Document conventions":

```
- Numbers that must line up get tables; reasoning stays in prose. Dates absolute, never
  "recently."
```

Replace with:

```
- Numbers that must line up get tables; reasoning stays in prose. Dates absolute, never
  "recently."
- **`Parameters` documents** carry exactly one pipe table, whose header is exactly
  `subject | parameter | value | unit | regime | as_of | warrant | decay | source`, and
  every cell of every data row is non-empty. A cell may not contain `|` (escape it `\|`).
  Two of the columns do work the others do not: `regime` records the conditions the number
  was measured under, without which the fit-check below ("not wider than what was
  measured") cannot be applied — a volume-tiered price and a queue-depth-specific latency
  are different claims, not contradictory ones. `as_of` plus `source` are what make a
  later decay recalibration possible: a half-life is learned by re-fetching and measuring
  what moved. The corpus guard enforces all of this; the pass-time skeleton is
  `templates/corpus/external/_parameters.md.tmpl`.
```

## Step 3b — extend the two holdings-scoped bullets in `method/CONVENTIONS.md`

Step 1's template carries `grade:`, and Step 5 asserts a Parameters doc "carries the same
provenance header and grade" — but `CONVENTIONS.md` currently scopes both to *holdings*
docs, and a Parameters doc is explicitly not one (Step 5 writes it "alongside the holdings
doc"). `CLAUDE.md` rule 11 requires these files to agree.

Find, under "OKF alignment":

```
- **Extension keys** (kit-defined, legal per OKF §4.1): `consumer` and `kit_commit` on the
  corpus README; `grade: retrieval | adversarial` on every holdings doc — the
  machine-legible half of the provenance header.
```

Replace with:

```
- **Extension keys** (kit-defined, legal per OKF §4.1): `consumer` and `kit_commit` on the
  corpus README; `grade: retrieval | adversarial` on every holdings doc and every
  `Parameters` doc — the machine-legible half of the provenance header.
```

Find, the first bullet under "## Document conventions":

```
- Every holdings document opens with a **provenance header**, split across the OKF
  frontmatter (`grade:` and `timestamp:` — the machine-legible part) and prose immediately
  below it: method (agents, sources), mirror location, and what the grade licenses. The
  kit's `templates/corpus/external/_holdings.md.tmpl` is the pass-time skeleton.
```

Replace with:

```
- Every holdings document — and every `Parameters` document — opens with a **provenance
  header**, split across the OKF frontmatter (`grade:` and `timestamp:` — the
  machine-legible part) and prose immediately below it: method (agents, sources), mirror
  location, and what the grade licenses. The pass-time skeletons are the kit's
  `templates/corpus/external/_holdings.md.tmpl` and `_parameters.md.tmpl`.
```

This does NOT mean the guard enforces `grade:` on Parameters docs. Task 2's
`test_parameters_tables_are_complete` has no opinion about frontmatter beyond `type`, and
its `write_parameters` fixture deliberately omits `grade:`. This step is documentation
scope only.

## Step 4 — add the substrate decay table to `method/GRADING.md`

Find this paragraph under "## Decay: warrant and durability are different axes":

```
**Each corpus defines the rest of its decay table at scaffold time** in
`distilled/README.md`, naming the domain's own volatility layers (release cadences, live
record ledgers, funding press, policy surfaces…), each with a half-life and a trigger. The
origin corpus's table — `model-generation` / `vendor-policy` / `vendor-build` /
`our-tree` / `their-tree` — is the worked example of the granularity to aim for.
```

Append immediately after it (leave the paragraph itself unchanged):

```
A second worked example, for corpora holding hardware and software cost-performance
substrate — the granularity a `Parameters` table needs:

| Class *(technology domains)* | Depends on | Half-life | Recheck trigger |
|---|---|---|---|
| `price-surface` | Vendor or cloud list pricing. | Quarters | A pricing-page change, or a new SKU family |
| `perf-envelope` | A measured throughput, latency, or IOPS figure for a specific part or service. | Tied to the part | A firmware, driver, or silicon revision |
| `media-generation` | A storage or memory generation. | 2–3 years | The next generation shipping at volume |
| `spec-standard` | A published standard revision. | ~5 years | The next revision ratified |
| `adoption-curve` | How broadly a technology is deployed. | ~1 year | A major platform changing its default |

**These half-lives are provisional and deliberately uncalibrated.** A decay rate is not
derivable a priori — it is learned by watching rows move. A corpus adopting this table
should re-fetch its fastest class and measure what actually changed after a few weeks of
holdings, then replace these figures with observed ones. This is safe to defer only while
nothing rests on the corpus; it stops being safe the moment a decision cites a row. What
cannot be deferred is the `as_of` date on every row, because it is what the recalibration
measures against.
```

## Step 5 — route passes to the template in `method/PASS-PROTOCOL.md`

Find this paragraph:

```
Record the grade in the holdings document's **provenance header**: the machine-legible
part in its OKF frontmatter (start from the kit's
`templates/corpus/external/_holdings.md.tmpl`; field set per CONVENTIONS.md, "OKF
alignment"), the rest as prose immediately below — agent count/models, what was fanned
out, what was mirrored, and what the grade means for the reader ("nothing here entered
distilled/" for retrieval).
```

Append immediately after it:

```
Where a subtopic's evidence is a **surface of numbers** rather than a set of claims —
prices, latencies, bandwidths, capacities, adoption shares — write a `Parameters` document
alongside the holdings doc, from `templates/corpus/external/_parameters.md.tmpl`. It
carries the same provenance header and grade. The split is by shape, not importance: a
number whose meaning depends on the conditions it was measured under belongs in a table
with a `regime` column; a claim belongs in prose with an inline evidence tag.
```

## Step 6 — mention the template in `SKILL.md`, Operation 2

Find step 3 of "Operation 2 — pass (research into a corpus)":

```
3. Write one holdings document per subtopic touched (start it from
   `templates/corpus/external/_holdings.md.tmpl`; instantiate
   `templates/corpus/external/_subtopic-README.md.tmpl` for any new subtopic folder), tag
```

Replace with:

```
3. Write one holdings document per subtopic touched (start it from
   `templates/corpus/external/_holdings.md.tmpl`; add a `Parameters` document from
   `templates/corpus/external/_parameters.md.tmpl` where the evidence is a surface of
   numbers rather than claims; instantiate
   `templates/corpus/external/_subtopic-README.md.tmpl` for any new subtopic folder), tag
```

## Error model

This task adds no executable code, so it has no runtime error model. Its failure modes are
caught by `checks`:

- A changed or reordered column header — the `grep -q` check fails with exit 1.
- An absolute local path, tilde path, or private-project name introduced into a method file
  or template — the negative `grep -rEn` check matches and the negated command exits 1.
- A `lake:` citation left in the template's `source` cell — the `! grep -n 'lake:'` check
  exits 1.
- A malformed template breaking the smoke matrix — `tests.test_scaffold` fails.

## checks

```
test -f templates/corpus/external/_parameters.md.tmpl
grep -qF '| subject | parameter | value | unit | regime | as_of | warrant | decay | source |' templates/corpus/external/_parameters.md.tmpl
grep -qF '`Parameters` (a cost/performance surface' method/CONVENTIONS.md
grep -qF 'price-surface' method/GRADING.md
grep -qF 'adoption-curve' method/GRADING.md
grep -qF '_parameters.md.tmpl' method/PASS-PROTOCOL.md
grep -qF '_parameters.md.tmpl' SKILL.md
grep -qF 'on every holdings doc and every' method/CONVENTIONS.md
! grep -n 'lake:' templates/corpus/external/_parameters.md.tmpl
! grep -rEn '/Users/|/home/|/Volumes/|~/|repos/evidence-|\bidea-gen\b' method/ templates/ SKILL.md scaffold.py
python3 -m unittest tests.test_scaffold -q
```

The last grep is a **negative** check: its job is catching contamination the steps above
cannot enumerate, which is why it is broader than `/Users/`. A0.6 and `CLAUDE.md` rule 3
forbid absolute paths, **machine-specific locations**, and **private-project names** — and
the tilde idiom is live in this plan's own Global Constraints (`~/repos/evidence-kit`), so
it is exactly the contamination an implementer is most likely to copy.
