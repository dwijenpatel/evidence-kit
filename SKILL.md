---
name: evidence-kit
description: Build and maintain a graded, evidence-first research corpus on any topic — scaffold the corpus repo, run research passes (retrieval-grade or adversarial-grade) that mirror primary sources and produce tagged holdings, distill Tier-A facts a decision may rest on, and audit decay/recheck schedules. Use when the user wants a persistent graded evidence base (not a one-shot report), says "evidence corpus", "research corpus", "grade this evidence", "start a corpus on X", or asks to run a research pass into an existing corpus.
---

# evidence-kit — operating instructions

You are maintaining an **evidence-first research corpus**. Read the three method files in
this skill's directory before acting — they are the contract:

- `method/GRADING.md` — what a claim can bear (warrant × decay; Tier A/B/C; fit checks).
- `method/PASS-PROTOCOL.md` — how a pass runs (grades, mirrors, verification, agents).
- `method/CONVENTIONS.md` — layout, tags, the consumption contract, document style.

Non-negotiables, in every operation: **mechanisms importable, magnitudes not** ·
single-source author-run numbers stay labeled until independently confirmed · absence
findings state their sample and date · corrections are ledgered, never silently fixed ·
the corpus guard test runs after every doc change.

## Operation 1 — scaffold (new corpus)

1. Ask (or take from the request) three things: the **topic**, the **consumer** (who has
   **skin in the game** — a decision surface that rests weight on the corpus and is damaged
   if a claim is wrong, required to cite Tier-A rows; the curious-reader audience is
   automatic and does not count; "audience-only for now" is an honest answer the README
   must state), and the **target directory**.
2. Run: `python3 <skill-dir>/scaffold.py --topic "..." --slug <slug> --out <dir> --consumer "..."`
3. Fill in the scaffolded `distilled/README.md` **decay table for this domain** with the
   operator (universal classes `math` / `human-factors` / `llm-class` usually survive;
   domain classes — release cadences, live ledgers, funding press — must be named fresh).
4. `git init` + initial commit; run the guard: `python3 -m unittest tests.test_reference -q`.

## Operation 2 — pass (research into a corpus)

Follow `method/PASS-PROTOCOL.md`. In brief:

1. Declare the **grade** up front — `retrieval` (map + mirror + tagged holdings; nothing
   enters distilled/) or `adversarial` (identity-checked primaries, claim extraction,
   multi-lens refutation; survivors may be distilled) — and record it in the holdings doc's
   provenance header.
2. Fan out sub-agents per target/cluster (mirror primary sources to the corpus's declared
   mirror location with a per-topic `MANIFEST.md`; pin repo clones to SHAs).
3. Write one holdings document per subtopic touched (instantiate
   `templates/corpus/external/_subtopic-README.md.tmpl` for any new subtopic folder), tag
   every claim, and update: the subtopic README (holdings + open questions), the corpus
   README (pass narrative + recheck schedule), and `terminology.md` for new terms of art.
4. Run the guard test. Commit on a branch if the corpus has mainline discipline.

## Operation 3 — distill (promote to Tier A)

Only from an adversarial-grade pass, per `method/GRADING.md`: each promoted fact enters
`distilled/external.md` or `distilled/internal.md` with a warrant letter (A1–A4/M), a decay
class from this corpus's table, a date for anything faster than the domain's slow class, and
a named source document + section (the chain distilled → holdings doc → primary must stay
walkable). Internal wins need a committed artifact; internal defects are Tier-A as
admissions. Never distill in the same pass that retrieved — a second look is the point.

## Operation 4 — recheck (decay audit)

Walk the corpus README's recheck schedule and every distilled row whose decay class has a
trigger that fired. Re-verify or **strike** — a stale Tier-A fact is worse than a Tier-B one.
Every strike or correction goes to the corpus README's corrections ledger with a date and
what changed. Re-pull any live external ledgers (leaderboards, status files) before citing.

## Guardrails

- Never let a pass write into `distilled/` directly; distillation is its own operation.
- Never delete a corrections-ledger entry; it is the corpus's most trustworthy page.
- If the operator asks for a conclusion the corpus cannot bear ("is X true?" where holdings
  are Tier B/C), say what tier the answer rests on rather than upgrading it in prose.
- Quota/spend discipline where the host project has one: passes that spawn many agents are
  operator-directed, never automatic.
