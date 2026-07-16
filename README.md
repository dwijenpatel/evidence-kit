# evidence-kit — a portable evidence-first research method

A Claude Code **skill + templates** for building and maintaining a *graded evidence corpus*
on any topic: primary-sourced holdings organized by subtopic, every claim tagged with how it
was established, a distilled Tier-A layer decisions may rest on, a corrections ledger, and a
recheck schedule for facts that rot. The output is a **persistent corpus**, not a one-shot
research report — that is the difference between this and a generic deep-research pass.

## What's here

| Path | What it is |
|---|---|
| [SKILL.md](SKILL.md) | The skill: four operations — scaffold / pass / distill / recheck. |
| [method/GRADING.md](method/GRADING.md) | The grading method: warrant × decay, the four Tier-A warrants, fit checks, maintenance rules. |
| [method/PASS-PROTOCOL.md](method/PASS-PROTOCOL.md) | How a research pass runs: retrieval-grade vs adversarial-grade, mirror discipline, agent prompts. |
| [method/CONVENTIONS.md](method/CONVENTIONS.md) | Corpus layout, tag vocabulary, the consumption contract, document conventions. |
| [templates/](templates/) | Files `scaffold.py` instantiates into a new corpus repo (incl. the link-integrity guard test). |
| [scaffold.py](scaffold.py) | Instantiates a new corpus: `python3 scaffold.py --topic "..." --slug topic --out DIR --consumer "..."`. |

## Install (user-level, all projects)

```sh
ln -s ~/repos/evidence-kit ~/.claude/skills/evidence-kit
```

## Provenance and the flow rule

The method was **extracted 2026-07-16 from the outrigger project's research corpus**
(`~/repos/outrigger/docs/research/`), where it was developed and battle-tested across a dozen
research passes, two distillation refreshes, and three critique passes that each changed the
method itself. The origin corpus's receipts (official docs caught wrong by probe; a benchmark
whose committed grader could not reproduce its own headline) are kept in GRADING.md as
teaching examples, attributed.

**Drift is managed, not eliminated.** Outrigger keeps its own in-repo edition of the method
(its audit trail requires the text it actually graded against). The declared flow:

1. **This kit is the portable canonical.** New corpora take the method from here.
2. **Improvements flow origin → kit**: when a critique pass improves outrigger's edition, the
   improvement is ported here (and noted in this repo's log). Improvements invented in other
   corpora also land here, never only in an instance.
3. **Instances pin their edition**: a scaffolded corpus records the kit commit it was
   instantiated from, so "which method graded this?" stays answerable.

## Instances

- `~/repos/auto-research-corpus` — instance #1 (2026-07-16): auto-research / self-improving
  research systems, seeded from the 2026-07-15 retrieval pass (Karpathy autoresearch, NVIDIA
  ENPIRE, AlphaEvolve, landscape). Raw mirrors: `~/repos/auto-research-mirrors/`.

## What a skill cannot do

The guard test enforces link integrity mechanically. Everything else — warrants, tiers,
single-source discipline — is **instructed, not enforced**: the method holds exactly as long
as the passes follow it. That is the same deal the origin corpus lives with; the corrections
ledger is where the discipline proves itself.
