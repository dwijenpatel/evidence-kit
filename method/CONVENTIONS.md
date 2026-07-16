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
