# plan-review — `2026-07-25-parameters-doc-type`

**Tier:** full (3 independent translators + 4 angle finders + 5 grouped adversarial verifiers)
**Plan reviewed:** `docs/plans/2026-07-25-parameters-doc-type/` (`plan.md`, `task-1-parameters-template.md`, `task-2-parameters-guard.md`) + `tasks.json`
**PRD authority:** `~/repos/idea-gen/docs/superpowers/specs/2026-07-25-idea-gen-design.md` (phase 0a, A0.1–A0.6, §12)
**Mode:** report-only. **No plan file was amended.** The plan remains ratified as committed; applying any rewrite below voids that ratification and needs a re-ratification diff read.

**Verdict: 7 CONFIRMED, 8 REFUTED, 3 dropped pre-verification.** The 10-finding cap did **not** bite — every surviving finding is reported.

**One is a hard blocker: `parameters-guard` cannot pass its own check list, on any implementation.**

---

## F1 — `parameters-guard` fails its own checks deterministically · **CONFIRMED (reproduced)**

**Location:** `tasks.json`, `parameters-guard.checks[0]` and `checks[4]`; mirrored in `task-2 ## checks`.

Check `[0]` is `python3 -m unittest tests.test_scaffold -q`. Running it compiles the test module, writing `tests/__pycache__/*.pyc`, whose `co_filename` embeds the absolute source path. Check `[4]` is `! grep -rn '/Users/' templates/ tests/`, which then matches those bytes and inverts to exit 1.

- **Reading A:** correct implementation, checks run in listed order → `[4]` exits 0, task complete.
- **Reading B:** correct implementation, checks run in listed order → `Binary file tests/__pycache__/test_scaffold.cpython-314.pyc matches`, exit 1, **task never completes.**

**Not a divergence — Reading B is simply what happens.** Reproduced on the real repo:

```
rm -rf tests/__pycache__
sh -c "! grep -rn '/Users/' templates/ tests/"   # exit 0
python3 -m unittest tests.test_scaffold -q       # OK
sh -c "! grep -rn '/Users/' templates/ tests/"   # exit 1  <-- same command, now fails
```

**Why it survived pre-ratification review:** `__pycache__/` is in `.gitignore`, so the bytes never appear in a diff; the failure requires check `[0]` to run first, so testing the grep alone on a clean tree passes; and in interactive `zsh` `grep` resolves to a shell function that masks it — it fails only under `sh -c`/`bash -c`, which is how the runner executes checks.

**Proposed rewrite** — merged with F6, which touches the same two lines. See F6.

---

## F2 — the template's own `source` format kills the guard · **CONFIRMED**

**Location:** `task-1 Step 1`, example row `source` cell: `<[n], or lake:path §sec @ commit>`.

- **Reading A:** doc authored from the template with `source` = `[1]` → guard exit 0.
- **Reading B:** doc authored from the template with `source` = `lake:ai/storage-hierarchy §2 @ abc1234` → guard exit **1**, `lake:ai/storage-hierarchy but no lake_root configured` — a **pre-existing, unrelated check** (`test_lake_citations_resolve`) killing a well-formed Parameters doc.

**Unresolved by:** the plan never mentions `lake_root`, `test_lake_citations_resolve`, or profile interaction; `lake:` appears exactly once in the whole plan directory — in the template row itself. `scaffold.py` sets `lake_root` **only** for the `project` profile, and `project` skips the `external/` tree entirely — so the one profile where a `lake:` source is safe is the one profile this template does not ship into. PRD §5.2 puts Parameters docs in the **lake**.

**The PRD makes the dangerous form the more literal one.** A0.1 requires per-row "`source §`" and §5.1 repeats "source § carried **per row**" — a *section-bearing* reference. `[n]` provides no section; `lake:<path> §<section>` does. The acceptance criteria push authors toward the form that breaks the guard.

**Proposed rewrite** — `task-1 Step 1`, example row `source` cell:

```
| … | <decay class> | <[n] §sec — a numbered entry in this document's # Citations section> |
```

and add after the "**A cell may not contain `|`.**" note:

> **`source` is a citation index, never a cross-corpus reference.** Write `[n]`, pointing at
> this document's `# Citations` section, with a `§` where the entry needs one. Do **not**
> write a `lake:` citation in this cell. The guard's pre-existing
> `test_lake_citations_resolve` matches any `lake:<path>` and resolves it against
> `lake_root`, which `scaffold.py` writes only for the `project` profile. In a `standalone`
> or `lake` corpus — where this template's `external/` tree lives — a `lake:` source cell
> fails the guard with `lake:<path> but no lake_root configured`.

Add to `task-1` checks and `tasks.json`: `! grep -n 'lake:' templates/corpus/external/_parameters.md.tmpl`

**This does NOT mean the `.tmpl` file itself fails the guard** (it is never instantiated and never scanned), **nor that `lake:` citations are banned from Parameters docs everywhere** — in a `project` corpus, where `lake_root` is configured, they resolve normally. **Nor does re-bracketing to `lake:<path>` fix it:** brackets protect only the template text, not an author who substitutes a real path.

---

## F3 — `ALIGN_ROW` silently swallows blank and dash-only data rows · **CONFIRMED**

**Location:** `task-2 Step 2` (`ALIGN_ROW`) and `Step 3` (`if ALIGN_ROW.match(line): continue`).

The skip is a **pattern match applied to every row**, not a positional skip of offset 1. Every character in `[\s:|-]` qualifies.

- **Reading A:** doc with pinned header, alignment row, then data row `|  |  |  |  |  |  |  |  |  |` → guard exit **0**, no output.
- **Reading B:** same input → exit 1, nine messages from ``data row 2: empty `subject` `` through ``… empty `source` ``.

Also affected: `| - | - | - | - | - |  | - | - | - |` — a row using `-` for not-applicable with `as_of` **blank** → exit 0. **PRD A0.4's central promise is false for that input.**

**Unresolved by:** the only sentence touching the skip is the worked example's *"the alignment row `|---|…|` is offset 1 and is skipped"* — which describes it as **positional and singular**, leaning toward Reading B, the opposite of the code. Reading B is promised in three places: the Error model row (``| Any empty cell | empty `<column>` |``), the check's own docstring (*"every cell of every data row filled"*), and Global Constraint 3 quoted verbatim from the PRD (*"A row missing either fails the guard test"*). Nothing adjudicates code against contract. The plan's own Step 1 tests pass anyway, because `PARAM_ROW.replace(...)` leaves letters in the row.

**Proposed rewrite** — `task-2 Step 3`, replace the loop:

```python
            if not ALIGN_ROW.match(blocks[0][1]):
                bad.append(f"{f}: table has no `|---|` alignment row under the header")
                continue
            for offset, line in enumerate(blocks[0][2:], start=2):
                cells = split_pipe_row(line)
                ...
```

> Exactly one row is skipped: the alignment row at offset 1, skipped **by position**, and it
> must actually be an alignment row. Every row from offset 2 on is validated
> unconditionally. Exact example — pinned header, `|---|` row, then the single data row
> `|  |  |  |  |  |  |  |  |  |` → exit `1` with nine messages,
> ``external/storage-prices.md data row 2: empty `subject` `` through ``… empty `source` ``.

**This does NOT mean the skip is a pattern match applied to every row.** Under that rejected reading, any row of spaces, dashes, colons and pipes is silently dropped, giving exit 0 on the maximally-defective row the guard most obviously must catch.

Add to `Step 1`:

```python
    def test_guard_rejects_parameters_row_that_is_entirely_blank(self):
        corpus = run_scaffold(self.tmp, "standalone")
        write_parameters(corpus, "|  |  |  |  |  |  |  |  |  |\n")
        r = run_guard(corpus)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("empty `as_of`", r.stderr + r.stdout)
```

---

## F4 — `PARAM_TYPE` fails open on quoted or comment-trailed `type` · **CONFIRMED**

**Location:** `task-2 Step 2`, `PARAM_TYPE = re.compile(r"^type:\s*Parameters\s*$", re.MULTILINE)`.

- **Reading A:** doc with `type: "Parameters"` and an empty `as_of` → guard exit **0**, silent, whole table unvalidated, defect ships.
- **Reading B:** same doc → exit 1, ``empty `as_of` ``.

Measured, against a defective doc: `type: Parameters` → exit 1 (rejected) · `type: "Parameters"` → exit 0 (**accepted**) · `type: Parameters  # cost surface` → exit 0 (**accepted**). `test_okf_conformance` stays green throughout, because `has_key` needs only `^type:\s*\S`.

**Unresolved by:** the nearest candidate — *"A document without `type: Parameters` frontmatter is skipped entirely"* — **is** the ambiguity; the plan uses backticked `` `type: Parameters` `` throughout as a type-name shorthand, never as a byte-literal spec. `plan.md` states the selector in YAML terms: *"finds any document whose frontmatter `type` is `Parameters`"* — and `type: "Parameters"` **is** such a document.

**Pattern break, called out:** the plan's decision log justifies this design as *"Consistent with `test_okf_conformance`, which already reads `type`"* — but that check uses `has_key`, which **accepts** the quoted form. **The cited precedent argues for the rejected reading.** Aggravating: `task-2 Step 1`'s fixture writes both conventions four lines apart, in one string literal — `'---\ntype: Parameters\ntitle: "Storage prices"\n'`.

**Proposed rewrite** — `task-2 Step 2`:

```python
PARAM_TYPE = re.compile(r"""^type:\s*["']?Parameters["']?\s*(#.*)?$""", re.MULTILINE)
```

> Selection is on the YAML **value** of `type`. `type: Parameters`, `type: "Parameters"`,
> `type: 'Parameters'`, and `type: Parameters  # cost surface` are the same YAML scalar and
> all select the document. Exact example — a doc whose frontmatter reads `type: "Parameters"`
> with an emptied `as_of` cell → exit `1`, ``external/storage-prices.md data row 2: empty `as_of` ``.

**This does NOT mean selection is a byte-exact match on the unquoted line.** Under that rejected reading the document is skipped in full at exit 0, and nothing else catches it — `has_key` accepts the quoted line as a non-empty `type`, so `test_okf_conformance` passes it too.

Add a covering test asserting a quoted-`type` doc with a blank `as_of` still fails.

---

## F5 — `checks[3]` rejects a compliant implementation · **CONFIRMED**

**Location:** `tasks.json`, `parameters-guard.checks[3]`: ``grep -qF 'empty `as_of`' tests/test_scaffold.py``.

- **Reading A:** guard emits ``empty `as_of` ``, test asserts it → check passes.
- **Reading B:** guard message rephrased to `` `as_of` is empty ``, test assertions updated, **full suite green, A0.2/A0.3/A0.4 all satisfied** → this grep exits 1 → **task 2 fails on a correct implementation.**

Reproduced across three kit states:

| state | suite | `checks[3]` |
|---|---|---|
| spec-verbatim message, negative tests present | 12/12 green | pass |
| **rephrased message, negative tests present** | **12/12 green** | **FAIL** |
| guard written, negative tests missing | 8/8 green | fail |

**Unresolved by:** `task-2`'s own preamble quotes CLAUDE.md rule 8 as governing — *"Assert on message substrings, never whole sentences"* — declaring wording non-contractual, while this check makes wording contractual **in a file that is not the message's source**. Nothing resolves the conflict.

**One prong of the original finding was neutralized:** "it cannot detect a guard that never emits the string" is false — `checks[0]` catches that. But the third row above shows `checks[3]` has one real job no other check does: proving the negative tests exist, which A0.4 requires (*"with a test proving the failure"*). **Replace, do not delete.**

**Proposed rewrite** — strictly dominating (keeps the missing-tests detection, kills the false rejection):

```
grep -qF 'test_guard_rejects_parameters_row_missing_as_of' tests/test_scaffold.py && grep -qF 'test_guard_rejects_parameters_row_missing_source' tests/test_scaffold.py
```

**This does NOT mean message wording is unconstrained** — `task-2`'s Error model still pins the substrings the guard emits. It means the *check* keys on the tests' existence rather than on prose the plan itself declares rephraseable.

---

## F6 — the A0.6 check tests one sixth of what A0.6 forbids · **CONFIRMED**

**Location:** `tasks.json`, `parameters-template.checks[7]` and `parameters-guard.checks[4]`.

A0.6 and CLAUDE.md rule 3 forbid absolute local paths, **machine-specific locations**, and **private-project names**. Only the literal `/Users/` is checked.

- **Reading A:** `Step 5` adds to `method/PASS-PROTOCOL.md`: ``See the shared lake at `~/repos/evidence-lake`; the idea-gen corpus distills from it.`` → check exits 0, **A0.6 recorded discharged.**
- **Reading B:** same input → A0.6 violated on two counts.

Reproduced: the appended line passes the current check.

**Unresolved by:** this is a **negative** check — its job is catching what the spec did *not* say to write, so "Steps 2–6 give verbatim replacement text" cannot pin it. Aggravating: the tilde idiom is live in the implementer's own reading material — `plan.md`'s Global Constraints quote *"ported to canonical `~/repos/evidence-kit`"*, and `plan.md` line 3 carries a literal `/Users/dwijen/...` path inside the kit repo.

**Proposed rewrite** — verified zero false positives on today's kit under both BSD `grep` and ugrep. `evidence-lake` is a legitimate *tag* in `templates/lake/*`, so the pattern matches only the path form `repos/evidence-`. The `parameters-guard` form also carries the `__pycache__` exclusion that **fixes F1**.

`parameters-template.checks[7]`:
```
! grep -rEn '/Users/|/home/|/Volumes/|~/|repos/evidence-|\bidea-gen\b' method/ templates/ SKILL.md scaffold.py
```

`parameters-guard.checks[4]`:
```
! grep -rEn --exclude-dir=__pycache__ '/Users/|/home/|/Volumes/|~/|repos/evidence-|\bidea-gen\b' templates/ tests/
```

(In `tasks.json`, escape as `\\bidea-gen\\b`.)

---

## F7 — `grade:` is left scoped to holdings docs · **CONFIRMED** (two independent angles)

**Location:** `task-1` Steps 2–6, against `method/CONVENTIONS.md:48-50` and `:151-155`, both unedited.

`Step 1`'s template puts `grade:` in `type: Parameters` frontmatter and `Step 5` inserts *"It carries the same provenance header and grade"* into `PASS-PROTOCOL.md`. But `CONVENTIONS.md` still reads *"`grade: retrieval | adversarial` on every holdings doc"* and *"Every holdings document opens with a **provenance header**…"*. A Parameters doc is explicitly **not** a holdings doc — `Step 5` says it is written *"alongside the holdings doc"*.

- **Reading A** (the five enumerated edits only): `CONVENTIONS.md` scopes `grade:` to holdings docs while two other files assert Parameters docs carry it. All nine checks pass.
- **Reading B** (apply rule 11): the Extension-keys and provenance bullets also name Parameters docs. All nine checks also pass.

**Unresolved by:** `task-1`'s preamble states the goal as *"make the four documents that describe the kit's vocabulary agree with it — CLAUDE.md rule 11…"*, pushing to B; the six enumerated steps deliver only part, pushing to A. `Step 4`'s *"leave the paragraph itself unchanged"* proves the author writes explicit scope-closing language when they mean it — and wrote none here.

**Pattern break, called out:** Steps 2 and 3 already edit `CONVENTIONS.md` in two other places, so multi-site consistency within that file was being tracked; the third site was missed rather than excluded.

**Proposed rewrite** — add a Step 3b with two exact edits:

`CONVENTIONS.md` Extension-keys bullet: `` `grade: retrieval | adversarial` on every holdings doc `` → `` `grade: retrieval | adversarial` on every holdings doc and every `Parameters` doc ``

`CONVENTIONS.md` first "Document conventions" bullet: `Every holdings document opens with a **provenance header**` → `Every holdings document — and every `Parameters` document — opens with a **provenance header**`, and name both pass-time skeletons at the end.

Add: ``grep -qF 'on every holdings doc and every' method/CONVENTIONS.md``

**This does NOT mean the guard must enforce `grade:` on Parameters docs.** `test_parameters_tables_are_complete` has no opinion about frontmatter beyond `type`, and `write_parameters` deliberately omits `grade:`. The edit is documentation scope only. The equally valid opposite fix is to **remove** `grade:` from the template and strike "and grade" from `Step 5`. What is not acceptable is three files disagreeing.

---

# Negative space

A zero-findings verdict has to show its work; so does a seven-findings one. **Eight candidates were refuted with quoted pinning sentences, three were dropped before verification.**

## Refuted (8)

| Candidate | Angle | Refuted because |
|---|---|---|
| Header comparison case-folds while prose says "exactly" | under-det, oracle-fitness, seam | `code-complete` tier; `header = tuple(c.lower() …)` ships verbatim, leaving no reading available to an implementer. **Residue noted below.** |
| `continue` after header mismatch violates rule 7 | convention-break | Rule 7's operational definition is the assert *shape*, which the code matches; nothing raises early. And the skip is substantively **correct** — after header drift, `zip(PARAM_COLUMNS, cells)` maps pinned names onto unknown columns, so ``empty `as_of` `` would assert about a column the document lacks. |
| Zero-data-row table ships green | under-det | `plan.md` Architecture states the check's requirements as a closed enumeration of three; a minimum-row rule is in none. Reading B requires inventing a sixth condition. Legitimate *scope* question for the operator, not a divergence. |
| "data row N" is a block offset, not an ordinal | oracle-fitness | The worked example pins it explicitly and declares it deliberate. Reading B's examples are arithmetic consequences of the pinned rule, not a competing reading. |
| A0.5 discharged by two word-greps | oracle-fitness | `Step 4` dictates the five-row table **verbatim**, including per-row dependency/half-life/trigger and the provisional label. Reading B is disobedience, not interpretation. |
| The template's `type:` line is verified by nothing | oracle-fitness | `Step 1` dictates the template verbatim, and `type:` is unquoted in **12 of 12** existing templates — quoting is conditional (rule 6 / YAML-significant colon), not stylistic. The authoring-side hole is real and is reported as **F4**. |
| Drift test's `assertIn("regime", …)` keys on a constant | oracle-fitness | The Error model pins the message shape to `header is [...], expected [...]`, which necessarily renders `list(PARAM_COLUMNS)`. A message without it violates the Error model, so it is not a correct implementation. Rule 8 constrains the *assert*, not the implementer's freedom to overwrite a pinned message. |
| Guard blind to unstaged files in a git corpus | seam | `task-2 Consumes` states the scanned set as **tracked** `*.md` files; A0.3 pins the environment to a *bare* scaffold where the `os.walk` fallback governs. Reading GC3 as a promise about git-index discovery is scope-invention, and honoring it would rewrite a pre-existing helper shared by five checks nobody asked to change. |

## Dropped pre-verification (3)

- **`pipe_blocks` fence-interrupting-a-table** — a 3-way translator divergence (1 block vs 2). Dropped: translator 3 mis-traced given control flow. Reader error, not spec ambiguity.
- **`plan.md`'s own header carries absolute paths and a private-project name** — real tension against the PRD §12.9 text the plan quotes as binding, but rule 3's scope excludes `docs/plans/`, both readings pass every check, and it flips no acceptance outcome.
- **`import ast,sys` (spec) vs `import ast` (tasks.json)** — cosmetic; both exit 0 on valid syntax and 1 on `SyntaxError`. No behavioral divergence.

## Residues — noted, below the finding bar

1. **Docs stricter than the guard.** `CONVENTIONS.md` will tell corpus authors the header must be "exactly" the pinned string while the guard case-folds. One-line fix either way: drop `.lower()`, or write "…these nine names in this order (compared case-insensitively)".
2. **Coverage gap against a pinned behavior.** A `set(header) != set(PARAM_COLUMNS)` guard passes all 12 tests and all six checks while **accepting a reordered header** — then reports ``empty `regime` `` for a blank cell whose real column is `as_of`. Not a divergence (no implementer can defensibly ship it), but a fifth fixture swapping two column names would close it.
3. **Decision-log overstatement.** *"validated the moment it is written"* — in a git-backed corpus, validated the moment it is `git add`ed. The contrast class is a config path list, so the intent is "with no registration step"; tightening the wording removes the only sentence that reads as endorsing the refuted git-staging finding.
4. **Under-sampled checks, by design.** No check greps `perf-envelope`, `media-generation`, `spec-standard`, `Half-life`, or `Recheck trigger`; `task-1 Step 3` has no check at all. Refuted as a finding (verbatim-dictated text), but cheap hardening if wanted: ``grep -qF 'media-generation' method/GRADING.md`` and ``grep -qF 'carry exactly one pipe table' method/CONVENTIONS.md``.

## What was checked and found sound

- **All five find-and-replace anchors** exist byte-for-byte and **uniquely** in their targets, verified programmatically including the `·`, `—`, `…` characters.
- **The nine-column header is byte-identical in all six locations**, including the two-part `PARAM_HEADER` concatenation.
- **Every name in `task-2 Consumes`** exists in the current files; every insertion point exists.
- **`scaffold.py` needs no change** — `render_tree`'s `_`-prefix skip verified.
- **A0.1–A0.6 each map to a produced artifact.**
- **Shell quoting is safe** — backticks and pipes inside single quotes, `!` negation works under `sh -c`, the nested-quote `python3 -c` runs.
- **Baseline is honest** — `tests/test_scaffold.py` has exactly 8 tests; applying Step 1 alone fails exactly 3 of 4 as the plan predicts; applying Steps 1–3 gives 12/12 green.

---

**Recommended disposition.** F1 is a blocker and F2/F3/F4 defeat the guard's stated purpose on inputs a real pass will produce. F5 and F6 are check-surface fixes; F7 is documentation. F6's `parameters-guard` rewrite also resolves F1, so the two should be applied together. All seven are small, local edits; none disturbs the ratified architecture or the pinned column set.
