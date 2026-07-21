# evidence-kit — agent instructions

This repository is an **agent-operable research-method kit**. There are two modes of work,
and this file covers both.

## Mode 1 — operating the method (the common case)

When the user asks to start or maintain an evidence corpus, run a research pass, grade
evidence, distill, or recheck:

1. Read [SKILL.md](SKILL.md) — the four operations (scaffold / pass / distill / recheck)
   and their guardrails. (Its YAML frontmatter is Claude Code skill metadata; if you are
   not Claude Code, ignore the frontmatter — the body is agent-agnostic.)
2. Read the contract in [method/](method/): [GRADING.md](method/GRADING.md) (what a claim
   can bear), [PASS-PROTOCOL.md](method/PASS-PROTOCOL.md) (how a pass runs),
   [CONVENTIONS.md](method/CONVENTIONS.md) (layout, tags, the consumer contract).

Non-negotiables, in every operation: **mechanisms importable, magnitudes not** ·
single-source author-run numbers stay labeled until independently confirmed · absence
findings state their sample and date · corrections are ledgered, never silently fixed ·
every corpus document is an OKF concept — YAML frontmatter with a `type` (the corpus is an
Open Knowledge Format v0.1 bundle; see CONVENTIONS.md, "OKF alignment") · the corpus guard
test (`python3 -m unittest tests.test_reference -q`, run from the corpus root) passes
after every documentation change.

Harness notes for non-Claude agents:

- Where SKILL.md or PASS-PROTOCOL.md says "spawn sub-agents" for a fan-out, use your
  harness's equivalent (parallel tasks/sessions); with no parallel primitive, run the
  targets serially — the protocol's discipline (mirrors, tags, verdicts) is what matters,
  not the concurrency.
- Passes that would spawn many agents or spend significant quota are **user-directed** —
  state the expected scale and get a go-ahead; never wire a pass into automation.

## Mode 2 — modifying the kit itself

- The three `method/` files and SKILL.md must stay consistent with each other; a change to
  one usually implicates the others — check before committing.
- `scaffold.py` and `templates/` are coupled: the placeholder set is exactly
  `{{TOPIC}} {{SLUG}} {{CONSUMER}} {{DATE}} {{KIT_COMMIT}} {{KIT_PATH}}`; template
  files named `_*.tmpl` are pass-time templates the scaffolder must skip; and
  frontmatter values embedding `{{TOPIC}}` or `{{CONSUMER}}` must stay double-quoted
  (scaffold.py rejects the characters — `"`, `\`, newline — that would break them,
  and nothing else guards template YAML validity). If you touch
  either side, run a smoke test: scaffold into a temp directory, run the guard test there
  (it must pass on a bare scaffold, even before `git init`), then delete the temp corpus —
  run the smoke test via the kit's own matrix: `python3 -m unittest tests.test_scaffold
  -q` (scaffolds every profile into a temp dir, runs each corpus guard, deletes).
- Keep the kit **standalone**: no references to any private project, absolute local path,
  or machine-specific location may enter the method files or templates (the scaffolder
  substitutes `{{KIT_PATH}}` at instantiation time for the one place a local path is
  useful).
- This kit is the canonical edition of the method (see the flow rule in
  [README.md](README.md)): improvements discovered while running an instance are ported
  here, never left only in the instance.
