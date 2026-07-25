# Parameters doc type — implementation plan

**PRD:** `/Users/dwijen/repos/idea-gen/docs/superpowers/specs/2026-07-25-idea-gen-design.md` (authority)
**References:** `/Users/dwijen/repos/idea-gen/docs/DECISIONS.md` (D9, D13, D14) ·
`AGENTS.md` · `method/GRADING.md` · `method/CONVENTIONS.md` · `method/PASS-PROTOCOL.md`

**Goal:** give evidence-kit a `type: Parameters` document — a guard-enforced cost/performance
table whose every row carries its own warrant, decay class, measurement regime, and date.

**Architecture:** A new pass-time template `templates/corpus/external/_parameters.md.tmpl`
carries a pinned nine-column markdown table. A new check in the corpus guard template
(`templates/tests/test_reference.py`) finds any document whose frontmatter `type` is
`Parameters`, requires exactly one pipe table with exactly the pinned header, and requires
every cell of every data row to be non-empty. The kit-side smoke matrix
(`tests/test_scaffold.py`) proves the check both passes a complete table and fails an
incomplete one, exercising the real scaffold→guard path rather than a fixture.
`scaffold.py` is not modified: `render_tree` already skips `_*`-prefixed templates.

## Global Constraints

Copied verbatim from PRD §12 and root `CLAUDE.md`. Every task implicitly includes these.

From the PRD:

> 3. **Every `Parameters` row carries `as_of` and `source`.** A row missing either fails the
>    guard test. Half-lives may be provisional; dates may not.
> 9. **Kit changes are ported to canonical `~/repos/evidence-kit`**, never left in an
>    instance, and must contain no absolute local path or private-project reference.
> 10. **Python tooling is `uv`** — `uv init` / `uv add` / `uv run`; no `pip`, no `venv`, no
>     `requirements.txt`.

From `CLAUDE.md` "Engineering conventions": rules 1–12, in full. The load-bearing ones for
this plan:

> 1. **Python 3, standard library only.** Neither `scaffold.py` nor the guard template may
>    import a third-party package.
> 3. **The kit stays standalone.** No absolute local path, machine-specific location, or
>    private-project name may appear in `method/`, `templates/`, `SKILL.md`, or
>    `scaffold.py`.
> 4. **Templates named `_*.tmpl` are pass-time** and must never be instantiated by
>    `scaffold.py`.
> 7. **A guard check collects every offender, then asserts once.**
> 8. **Assert on message substrings, never whole sentences.**
> 10. **After any change to `templates/` or `scaffold.py`, run**
>     `python3 -m unittest tests.test_scaffold -q`.

**Pinned column set** (one-way door, operator-ratified 2026-07-25) — exactly these nine, in
exactly this order:

```
subject | parameter | value | unit | regime | as_of | warrant | decay | source
```

## PRD coverage

| Criterion | Task |
|---|---|
| A0.1 template with per-row columns | T1 |
| A0.2 `tests.test_scaffold` passes | T1 (must not break), T2 (extends) |
| A0.3 guard green on a scaffold containing a valid Parameters doc | T2 |
| A0.4 missing `as_of` **or** `source` fails, with a test proving it | T2 |
| A0.5 five substrate decay classes documented as worked examples | T1 |
| A0.6 no absolute local path or private-project name in kit files | T1, T2 (both check) |

## Decision log

| Decision | Rejected alternative | Why | Cost of changing later |
|---|---|---|---|
| Markdown pipe table for rows | YAML block in frontmatter; fenced YAML in body | `CONVENTIONS.md` "Document conventions" is explicit: *"Numbers that must line up get tables; reasoning stays in prose."* The kit is markdown-native and its value proposition is a human-walkable chain; a YAML blob is machine-first and invisible in the rendered doc. | High — every row rewritten, and the guard's parser replaced. |
| Pass-time template (`_parameters.md.tmpl`) | Scaffold-time template | A Parameters doc is authored per subtopic during a pass, exactly like `_holdings.md.tmpl`. `render_tree` skips `_*` by prefix, so **`scaffold.py` needs no change** — which removes the scaffolder/template coupling risk `AGENTS.md` warns about. | Low — move the file and add a scaffold entry. |
| Nine columns incl. `subject` and `regime` | PRD-literal seven columns | `subject` makes grouping-by-tier a column read instead of parsing a human-authored label. `regime` enforces `GRADING.md`'s fit-check that *"a warrant covers the claim inside its measured regime"* — without it, S3's first-50TB price and its above-50TB price read as a contradiction, and regime-blind crossing detection is the most likely way the downstream consumer produces confident garbage. | Very high — this is the one-way door; every row rewritten. Operator-ratified. |
| Guard keys off frontmatter `type: Parameters` | A config list of parameter-doc paths in `corpus_guard.json` | Self-describing documents; a new Parameters doc is validated the moment it is written, with no config edit to forget. Consistent with `test_okf_conformance`, which already reads `type`. | Low. |
| Exactly one pipe table per Parameters doc | Allow many, validate each | One table is sufficient by construction — `subject` and `parameter` already distinguish rows, so a second table would be a redundant axis. A single-table rule makes the guard unambiguous about what it is validating. | Low — relax the count check. |
| Cells may not contain `|` | Support escaped pipes | Escaping doubles the parser's complexity to buy a case no parameter value needs. Stated as a rule so the failure is a guard error, not a silent mis-parse. | Low. |
| Negative test in `tests/test_scaffold.py` | A fixture corpus committed under the kit | Exercises the real scaffold→write→guard path, matching the existing `test_lake_guard_enforces_tag_registry` precedent, and cannot drift from what `scaffold.py` actually emits. | Low. |
| Decay classes into `GRADING.md` as a **second** worked example, flagged *(technology domains)* | Promote them to the universal class table; or leave them only in the lake instance | PRD §5.1 says *"documented as worked examples… alongside the existing"*, and `GRADING.md` already flags a domain-scoped class this way (`llm-class` *(AI domains)*). Leaving them in the instance would violate `AGENTS.md`'s rule that kit improvements are ported upstream. | Low — prose move. |
| Plan under `docs/plans/` | `docs/superpowers/plans/`, the repo's existing location | `tech-plan` pins `docs/plans/<date>-<name>/` and the runner reads `tasks.json` from the repo root. The prior directory holds a completed superpowers-flow plan and is left untouched. | Trivial. |
| Half-lives ship provisional and labeled | Derive values now | PRD D13: a decay rate is learned by watching rows move, and nothing rests on the corpus yet. Empirical recalibration ~2 weeks after the first rows land. `as_of` is what makes that recalibration possible, which is why it is guard-enforced and the half-lives are not. | Trivial — edit prose. |

## Operator questions asked (Gate G2a front half)

One, spent on the single one-way door. Everything else was derived from the repo under
`CLAUDE.md` conventions → ratified precedent → general principles.

1. **Column set for a Parameters row.** Answered 2026-07-25: nine columns including
   `subject` and `regime`, over the PRD-literal seven. Recorded above.

## Tasks

| # | id | tier | Deliverable |
|---|---|---|---|
| 1 | `parameters-template` | `code-complete` | The template, plus the four method/SKILL edits that keep the kit self-consistent |
| 2 | `parameters-guard` | `code-complete` | The guard check and the tests that prove it fires |

Task 2 depends on Task 1 only for the column set, which is pinned in Global Constraints
above and restated in each spec — the tasks are independently implementable.

## Ratification

- **ratified-by:** operator (dwijen)
- **date:** 2026-07-25

Any edit after ratification voids it.
