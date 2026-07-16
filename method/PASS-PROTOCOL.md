# The pass protocol — how research enters a corpus

A **pass** is one bounded research effort with a declared scope, a declared verification
grade, and a written trail: mirrored primaries → tagged holdings document(s) → README
updates. Passes are how a corpus grows; nothing enters any other way.

## Declare the grade first

| Grade | What it buys | What it may touch |
|---|---|---|
| **retrieval** | Fast map of a target: primary artifacts found, mirrored, read; claims tagged (`author-claimed`, `single-source`, `[reported]`…); reception noted. Single agent per target, no refutation round. | `external/` holdings + READMEs only. **Nothing enters distilled/.** Distillation candidates are flagged for a later adversarial pass. |
| **adversarial** | Claims a decision can rest on. Fan-out to primaries with **identity checks** (right paper, right version, right authors — confabulated citations are common), claim extraction, then a refutation round: each load-bearing claim through ≥3 independent verification lenses (source-fidelity: does the primary actually say this; methodology/regime-fit: does the method support it, in what regime; independent-replication: who else found it). A claim killed by ≥2/3 lenses dies; corrections are recorded. | May feed Operation 3 (distill). Keep the machine-readable verification record (per-claim verdicts) committed alongside the holdings doc. |

Record the grade in the holdings document's **provenance header**: date, agent
count/models, what was fanned out, what was mirrored, the grade, and what the grade means
for the reader ("nothing here entered distilled/" for retrieval).

## Mirror discipline

- Every primary artifact gets a local mirror at the corpus's declared mirror location
  (large binary mirrors live *outside* the corpus repo; the corpus stores the pointer):
  pages as extracted text/markdown, papers as PDFs, repositories as `git clone --depth 1`
  **pinned to a SHA recorded in the manifest**.
- Each mirror directory carries a `MANIFEST.md`: local file → source URL, retrieval date,
  type, approximate size. Un-mirrorable sources (paywalls, bot-blocked, deleted) are listed
  in the manifest as such — the gap is part of the record.
- Live external ledgers (leaderboards, status files) are snapshotted with their date; the
  holdings doc cites the snapshot, never "the current state."

## Source discipline

- **Primary sources first**; label secondary coverage (press, forums, threads) as secondary
  and use it for reception, never for the claim itself.
- **Author-claimed vs independently confirmed vs disputed** — every number carries one of
  these, with who confirmed. A party's unreplicated measurement of its own system is Tier C
  (see GRADING.md).
- **No fabrication; absence is a finding.** If the target doesn't exist under the searched
  name, say so and report the closest real thing, noting the mismatch.
- **Quotes**: at most a few per source, each under 15 words, attributed. Summaries in the
  pass author's own words, substantially shorter than the source.
- **Dates and URLs on everything.** A claim without a date cannot decay gracefully.

## Running the fan-out

- One sub-agent per target or cluster; give each: the mission, the mirror directory, the
  discipline block above, and a required report structure (identity/provenance → mechanism →
  claims with verification tags → artifact inventory → reception → open questions).
- Tell agents their final message is data for the orchestrator, and that treating search
  summaries as leads (verify against the primary before reporting) is mandatory — a good
  agent reports which candidate claims it *discarded* as unverifiable.
- Where a generic deep-research skill is available, it can serve as the adversarial-grade
  engine; the corpus adds what it lacks — mirrors, tags, distillation, corrections, decay.

## What a pass updates (checklist)

1. The **holdings document(s)** under the right `external/<subtopic>/` (new subtopic → new
   folder with a scoped README from the kit template; empty folders are legitimate queue
   markers).
2. The **subtopic README**: holdings list + open questions.
3. The **corpus README**: pass narrative (one entry: date, method, what it added), recheck
   schedule additions, corrections if the pass falsified anything already held.
4. **terminology.md** for new terms of art.
5. The **guard test** passes: `python3 -m unittest tests.test_reference -q`.
6. Commit per the host repo's discipline (branch-first where mainline is protected).
