# Corpus conventions — layout, tags, contracts

## Layout (what scaffold.py creates)

```
<corpus>/
  index.md             # OKF bundle-root index: okf_version declaration + top-level listing
  README.md            # index: topic, consumer, pass narrative, corrections ledger,
                       # recheck schedule, mirror pointer
  terminology.md       # every acronym, coined term, and tag defined once
  external/            # the world's evidence, organized by subtopic
    README.md          #   map of subtopics w/ coverage glyphs: ● rich · ◐ moderate · ○ thin
    <subtopic>/README.md   # scope · holdings · related · open questions
    <subtopic>/<holdings-doc>.md
  internal/            # evidence the corpus owner generated (runs, probes, measurements)
    README.md          #   defects weigh more than wins; wins need committed artifacts
  distilled/           # the Tier-A subset only
    README.md          #   pointer to the kit's GRADING.md edition (pinned) + THIS domain's
                       #   decay table + local maintenance notes
    external.md        #   Tier-A facts from the world
    internal.md        #   Tier-A facts from own runs
  tests/
    test_reference.py  # the guard: every relative md link resolves; anchors exist
    corpus_guard.json  # guard config: required files, minimum doc count
```

The split is by **who produced the evidence**, because provenance is the first thing that
determines weight: external (we did not run it — strongest replicated or against-interest),
internal (we ran it — defects strong, wins need artifacts), distilled (Tier A only; start
here).

## OKF alignment (the corpus is a knowledge bundle)

Every corpus is a conformant **Open Knowledge Format (OKF) v0.1** knowledge bundle
([spec](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)):
any OKF consumer — an index generator, a graph viewer, an agent doing progressive
disclosure — can read a corpus without knowing anything about the evidence method. The
method rides on top; the format underneath is plain OKF.

- **Frontmatter.** Every markdown document except OKF's reserved files (`index.md`,
  `log.md`) opens with YAML frontmatter carrying a non-empty `type`, plus `title`,
  `description`, and `timestamp` (refreshed whenever a pass meaningfully changes the doc).
  The kit's type vocabulary: `Corpus` (corpus README) · `Terminology` · `Subtopic Map`
  (external/README) · `Subtopic` (subtopic README) · `Holdings` (holdings doc) ·
  `Internal Evidence` · `Distilled Index` (distilled/README) · `Distilled` (the two Tier-A
  docs) · `Parameters` (a cost/performance surface: one table, warrant and decay per row).
  Unknown types are legal OKF; these are the ones consumers of an evidence corpus can rely
  on.
- **Extension keys** (kit-defined, legal per OKF §4.1): `consumer` and `kit_commit` on the
  corpus README; `grade: retrieval | adversarial` on every holdings doc and every
  `Parameters` doc — the machine-legible half of the provenance header.
- **index.md.** The bundle root carries `index.md` with `okf_version: "0.1"` frontmatter
  (the only index permitted frontmatter) and a top-level listing for progressive
  disclosure. Deeper directories rely on their READMEs; OKF consumers may synthesize
  deeper indexes on the fly.
- **log.md.** Not emitted: the corpus README's pass narrative and corrections ledger are
  this method's history-of-record, and the ledger's never-deleted guarantee stays in one
  place. A corpus MAY additionally maintain a root `log.md` mirroring the pass narrative
  for OKF consumers; the README stays canonical.
- **Links.** House style is *relative* links (they render on GitHub and stay valid when a
  bundle nests inside a larger repo); bundle-absolute links (`/external/...`, OKF §5.1)
  are accepted and the guard resolves both against the corpus root. The guard *fails* on
  broken links — deliberately stricter than OKF's tolerate-broken-links consumer minimum,
  because here a dangling link is a lost evidence chain, not "not-yet-written knowledge."
- **Citations.** A holdings doc's source list lives under a `# Citations` heading (OKF
  §8), numbered; entries may point at the primary URL and at the corpus's mirror. The
  mirror `MANIFEST.md` remains the authority on what was actually captured.
- **Two tag layers, distinct on purpose.** Frontmatter `tags:` are OKF's cross-cutting
  *topical* labels (what a doc is about — for filtering and search). The inline evidence
  tags below grade *individual claims* and never move to frontmatter: a document is not
  `[measured]`; a claim is.

The guard test enforces the conformance floor mechanically: frontmatter present, `type`
non-empty, root `okf_version` declared, reserved files clean, every link resolving.

## Lake and project profiles

A machine that runs several corpora splits them by the method's own seam: **warrant is
consumer-independent, distillation is not.** Three profiles (scaffold `--profile`):

| Profile | Has | Lacks |
|---|---|---|
| `standalone` (default) | everything above | — |
| `lake` | `<domain>/<subtopic>/` holdings · `mirrors/` · generated `XREF.md` · one README (consumers **plural**, pass narrative, corrections ledger, recheck schedule) · terminology + **tag registry** | `internal/`, `distilled/` |
| `project` | `internal/` · `distilled/` · README (consumer, project narrative, project ledger) | `external/`, `mirrors/` |

- **Lake tree is storage, not meaning**: two levels (`<domain>/<subtopic>/`), never
  deeper; a doc lives in exactly one folder — canonical home is the domain whose decay
  context governs it; membership elsewhere via `tags`, "Related material elsewhere"
  lines, and links. Never duplicate a doc. A subtopic that wants children is two
  subtopics.
- **Citations across the seam**: a project's distilled rows cite lake holdings as
  `lake:<path> §<section> @ <lake-commit>`. The pin answers "which edition graded
  this"; re-pinning is a deliberate recheck-time act. The project guard resolves
  `lake:` paths against `lake_root` in `tests/corpus_guard.json` and fails loudly when
  they don't resolve.
- **Corrections routing**: external claims → the lake's ledger; internal/distilled
  rows → the project's ledger. Projects diff the lake ledger since their last pin at
  every recheck; a lake correction touching a cited doc forces re-verification of the
  citing row.
- **Tag registry**: every frontmatter tag used anywhere in the lake is defined in
  terminology.md's "## Tag registry" (guard-enforced) — one vocabulary keeps the INDEX
  from splitting.
- **Discovery**: `XREF.md` is generated (`python3 index.py`) — tag index with
  cross-domain flags, backlink table with cross-domain edges first, shared-source
  report (URL in ≥2 subtopics). `git diff XREF.md` after a pass is the
  new-connections report; the guard asserts freshness.

## Tag vocabulary (inline, on claims)

`[official]` authoritative/vendor statement (split commitment vs mechanism per GRADING.md) ·
`[measured]` measurement with data (add `, replicated` / `, single-source` / `, local`) ·
`[contested]` conflicting evidence, state both sides · `[folklore]` practitioner consensus,
no data · `[reported]` journalism/secondary · `[E]` established in the cited source ·
`[I]` inference/synthesis by the pass author · plus plain-word labels **author-claimed /
independently confirmed / disputed** on every number. Define any additions in
`terminology.md`.

**Regime labels** — carried alongside the tier on any headline *number*, because source
hedging ("author-claimed") says who ran it while the regime says whether the **method
licenses generalization**: `{held-out}` scored on data/tasks the system never selected
against · `{in-distribution}` optimized against the same metric it reports (selection
circularity — an optimize-on-the-eval number, not generalization) · `{unstated-N}` no
denominator or sample size given · `{within-noise}` the delta is statistically
indistinguishable at the reported N · `{wide-CI}` the interval is too wide to license the
point estimate. A number may carry several. (Imported 2026-07-16 from the first
adversarial pass run with this kit, which found headline numbers correctly source-hedged
but silently regime-unbounded.)

## The consumption contract

Every corpus automatically serves an **audience**: anyone curious and interested in the
rigorous current state of the subject, claims weighed by evidence — **nothing at stake**.
That use-case needs no declaration; it is what the documents are.

The **consumer** is the party with **skin in the game**: a named surface that rests weight
on the corpus and is *damaged if a claim is wrong* — a design doc, an investment memo, an
experiment protocol, public claims made to experts. A consumer is required to cite Tier-A
rows, with claims outside distilled/ entering only as *provisional* with a named promotion
trigger. The distinction matters because a reader never pushes back — only skin in the game
disciplines which pass runs next, justifies the cost of adversarial grading, and fires the
recheck / corrections loop that keeps the corpus from rotting into bookmarks. (This is the
same incentive logic the grading method applies to sources: an admission against interest
is credible because the speaker has skin in the game. Warrant weighs the source's stake;
the consumption contract weighs the reader's.)

The corpus README states the consumer in its header. If there is none yet, it says so
plainly ("audience-only for now — no skin in the game yet; tiers grade reliability, nothing
is load-bearing") — an honest weak contract beats a pretended strong one.

## Document conventions

- Every holdings document — and every `Parameters` document — opens with a **provenance
  header**, split across the OKF frontmatter (`grade:` and `timestamp:` — the
  machine-legible part) and prose immediately below it: method (agents, sources), mirror
  location, and what the grade licenses. The pass-time skeletons are the kit's
  `templates/corpus/external/_holdings.md.tmpl` and `_parameters.md.tmpl`.
- Self-contained documents: define terms on first use or link `terminology.md`; a reader
  should never need the conversation that produced the doc.
- **Corrections ledger** (in the corpus README): dated entries for every falsified,
  narrowed, or struck claim — including the pass's own errors caught later. Never deleted,
  never silently amended.
- **Recheck schedule** (in the corpus README): dated triggers for facts that rot — releases
  promised, live ledgers, policy surfaces. Rechecks strike or refresh; they never quietly
  keep.
- **Empty subtopic folders are deliberate**: they mark subproblems not yet covered and form
  the queue for future passes. A README with scope + "no holdings yet" is a valid state.
- Numbers that must line up get tables; reasoning stays in prose. Dates absolute, never
  "recently."
- **`Parameters` documents** carry exactly one pipe table, whose header is these nine names
  in this order — `subject | parameter | value | unit | regime | as_of | warrant | decay |
  source`, compared case-insensitively — with an alignment row directly beneath it and every
  cell of every data row non-empty. Order is contractual, not the name set: swapping two
  columns is a defect, because every downstream read is positional. A cell may
  not contain `|` (escape it `\|`). `warrant` is one of `A1` `A2` `A3` `A4` `M` `B` `C` —
  the Tier-A letters from GRADING.md, plus `B` for directional and `C` for framing-only,
  because most substrate facts are Tier B by construction and the column would otherwise
  have no legal value for them. A **derived** row carries the weakest warrant among its
  inputs and states the derivation in `regime`. Two columns do work the others do not:
  `regime` records the conditions the number was measured under, without which the
  fit-check below ("not wider than what was measured") cannot be applied — a volume-tiered
  price and a queue-depth-specific latency are different claims, not contradictory ones;
  and `as_of` plus `source` are what make a later decay recalibration possible, since a
  half-life is learned by re-fetching and measuring what moved. The corpus guard enforces
  all of this — and validates `decay` against `decay_classes` in `tests/corpus_guard.json`
  when that key is set. The pass-time skeleton is
  `templates/corpus/external/_parameters.md.tmpl`.
