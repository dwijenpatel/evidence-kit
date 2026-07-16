# Corpus conventions — layout, tags, contracts

## Layout (what scaffold.py creates)

```
<corpus>/
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

## Tag vocabulary (inline, on claims)

`[official]` authoritative/vendor statement (split commitment vs mechanism per GRADING.md) ·
`[measured]` measurement with data (add `, replicated` / `, single-source` / `, local`) ·
`[contested]` conflicting evidence, state both sides · `[folklore]` practitioner consensus,
no data · `[reported]` journalism/secondary · `[E]` established in the cited source ·
`[I]` inference/synthesis by the pass author · plus plain-word labels **author-claimed /
independently confirmed / disputed** on every number. Define any additions in
`terminology.md`.

## The consumption contract

A corpus earns its upkeep only if something **consumes** it: a named decision surface
(a design doc, an investment memo, an experiment protocol) that is required to cite
Tier-A rows — with claims outside distilled/ entering decisions only as *provisional*,
carrying a named promotion trigger. The corpus README states the consumer in its header.
If there is no consumer yet, the README says so plainly ("briefing library; the tiers
grade reliability but nothing is load-bearing yet") — an honest weak contract beats a
pretended strong one.

## Document conventions

- Every holdings document opens with a **provenance header**: pass date, grade
  (retrieval/adversarial), method (agents, sources), mirror location, and what the grade
  licenses.
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
