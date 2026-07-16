# evidence-kit — a portable evidence-first research method

A method kit — **agent instructions + templates + a guard test** — for building and
maintaining a *graded evidence corpus* on any topic: primary-sourced holdings organized by
subtopic, every claim tagged with how it was established, a distilled Tier-A layer that
decisions may rest on, a corrections ledger, and a recheck schedule for facts that rot.

The output is a **persistent corpus, not a one-shot research report**. A report is right
(at best) on the day it's written and rots silently afterward. A corpus knows which of its
claims can bear weight, watches the ones that decay, and ledgers its own corrections.

Two ideas carry the whole method:

- **Warrant × decay.** A claim is load-bearing (Tier A) only if it carries one of four
  warrants — independently replicated · admission against interest · directly verified by
  execution · official commitment — *and* is within its decay window. Everything else is
  directional (Tier B) or framing-only (Tier C). Mechanisms transfer between settings;
  magnitudes usually don't.
- **Audience vs consumer.** Every corpus serves the curious reader automatically. It earns
  its upkeep only from a **consumer with skin in the game** — a named decision surface
  that is damaged if a claim is wrong, and is therefore required to cite Tier-A rows.

## Quickstart

```sh
git clone <this-repo-url> evidence-kit
cd evidence-kit

# 1. Scaffold a corpus (a plain directory; make it a git repo right after)
python3 scaffold.py \
  --topic "Solid-state batteries" --slug ssb \
  --out ../ssb-corpus \
  --consumer "our 2027 cell-supplier decision memo"
cd ../ssb-corpus && git init -b main && git add -A && git commit -m "scaffold"

# 2. Prove the guard runs (every relative md link must resolve, always)
python3 -m unittest tests.test_reference -q

# 3. Fill in the two blanks the scaffold prints:
#    - the domain decay table in distilled/README.md
#    - the mirror location in README.md
```

Then run research **passes** with your agent — for example:

> Using the evidence-kit method (read SKILL.md and method/ in the kit first), run a
> **retrieval-grade** pass on "who are the credible solid-state-battery cell makers as of
> 2026" into this corpus.

and later, when claims need to bear weight:

> Run an **adversarial-grade** pass over the load-bearing claims in
> external/suppliers/, then distill the survivors.

The four operations — **scaffold / pass / distill / recheck** — are specified in
[SKILL.md](SKILL.md); the contract they follow lives in [method/](method/).

## Using it with your agent

- **Claude Code** — install as a user-level skill, then just ask ("start an evidence
  corpus on X", "run a retrieval pass on …"):
  ```sh
  ln -s "$(pwd)" ~/.claude/skills/evidence-kit    # from the clone; Windows: copy instead
  ```
- **Codex** — this repo ships [AGENTS.md](AGENTS.md), which Codex reads automatically when
  working inside the kit. From another project, point at the clone: *"follow the
  evidence-kit method at ../evidence-kit — read its SKILL.md and method/ first"* (or
  reference it from that project's own AGENTS.md).
- **Any agent** — everything here is plain Markdown plus stdlib Python. Point your agent
  at [SKILL.md](SKILL.md) (operations) and [method/](method/) (contract); nothing depends
  on a specific harness. The YAML block at the top of SKILL.md is Claude Code skill
  metadata — other agents can ignore it.

## What's here

| Path | What it is |
|---|---|
| [SKILL.md](SKILL.md) | The operations: scaffold / pass / distill / recheck, with guardrails. |
| [AGENTS.md](AGENTS.md) | Cross-agent entry point (Codex et al.): how to operate and how to modify this kit. |
| [method/GRADING.md](method/GRADING.md) | The grading method: warrant × decay, the four Tier-A warrants, fit checks, maintenance rules. |
| [method/PASS-PROTOCOL.md](method/PASS-PROTOCOL.md) | How a pass runs: retrieval vs adversarial grades, mirror discipline, fan-out, verification lenses. |
| [method/CONVENTIONS.md](method/CONVENTIONS.md) | Corpus layout, tag vocabulary, audience-vs-consumer contract, document conventions. |
| [templates/](templates/) | Files `scaffold.py` instantiates into a new corpus (including the link-integrity guard test). |
| [scaffold.py](scaffold.py) | The instantiator. `python3 scaffold.py --help`. |

## Provenance and the flow rule

The method was extracted in July 2026 from a private research project where it was
developed and battle-tested: a dozen research passes, two distillation refreshes, and
three critique passes that each changed the method itself. Its receipts — official
documentation caught wrong by direct probe; a benchmark whose committed grader could not
reproduce its own headline — are kept in [method/GRADING.md](method/GRADING.md) as
attributed teaching examples, because they are why the rules say what they say.

**The flow rule (how drift is managed, not eliminated):**

1. **This kit is the canonical edition of the method.** New corpora take it from here.
2. **Improvements land here** — a fix to the method discovered while running any instance
   is ported to the kit, never left only in the instance.
3. **Instances pin their edition**: a scaffolded corpus records the kit commit it was
   instantiated from, so "which method graded this?" stays answerable even as the kit
   moves.

## What a skill cannot do

The guard test enforces link integrity mechanically. Everything else — warrants, tiers,
single-source discipline — is **instructed, not enforced**: the method holds exactly as
long as the passes follow it. The corrections ledger is where the discipline proves
itself; read any corpus's ledger before trusting its holdings.

## License

MIT — see [LICENSE](LICENSE).
