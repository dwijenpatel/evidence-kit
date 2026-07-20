# Evidence Lake — shared external evidence across project corpora

**Date:** 2026-07-17 · **Status:** approved design, pre-implementation
**Scope:** evidence-kit (method + scaffolder + guard), a new `evidence-lake` repo, and
migration of the two existing corpora (`~/repos/auto-research-corpus`,
`~/repos/outrigger/docs/research/`).

## 1. Problem

Multiple evidence-kit corpora exist on one machine and overlap heavily. Costs observed:

- **Redundant work** — the same primary sources get mirrored, read, and verified per
  corpus. (Primary pain.)
- **Missed connections** — related holdings live in different corpora with no mechanism
  to surface cross-topic links. (Primary pain.)
- **Content drift** — `auto-research-corpus` was seeded from outrigger's
  `self-improvement/auto-research-systems-2026-07.md`; the fork then received four
  ledgered corrections that never propagated back.
- **Upkeep burden** — parallel recheck schedules, ledgers, guards.

Constraints from brainstorming: the shared layer is **private** (nothing published
as-is); corpus population is several efforts, mostly AI/agents-adjacent but not all
(e.g., a future ETL research effort); no knowledge-graph database — discovery machinery
must stay at the stdlib-script level.

## 2. Design principle

The grading method already draws the line this design follows: **warrant is
consumer-independent** (a registry filing is A3 for everyone), while **distillation,
decay-relevance, and internal evidence are per-consumer**. Therefore external evidence
pools; distilled and internal do not.

## 3. Architecture

Three corpus **profiles** (a new kit concept):

| Profile | Has | Lacks | Instances |
|---|---|---|---|
| `standalone` | everything (today's layout) | — | outside users; default |
| `lake` | external/ (as domain shards), mirrors/, INDEX.md, single README (consumers, pass narrative, corrections ledger, recheck schedule), terminology + tag registry | internal/, distilled/ | `~/repos/evidence-lake` |
| `project` | internal/, distilled/, README (consumer, project pass narrative, project ledger), guard w/ `lake_root` | external/, mirrors/ | auto-research-corpus; outrigger/docs/research |

### 3.1 The lake repo (`~/repos/evidence-lake`, private, one OKF v0.1 bundle)

```
evidence-lake/
  index.md              # OKF root: okf_version + top-level listing
  README.md             # consumers (plural, named) · pass narrative · corrections
                        # ledger · recheck schedule — one of each, lake-wide
  terminology.md        # shared vocabulary + tag registry (§6)
  INDEX.md              # generated (§6): tag index · backlinks · shared-source report
  <domain>/<subtopic>/  # holdings + scoped READMEs — two levels, never deeper
  mirrors/<domain>/<target>/   # mirrors + URL-keyed MANIFESTs
  tests/                # guard + INDEX-freshness check
```

- **Tree is storage, not meaning** (OKF stance): a doc lives in exactly one folder.
  Two-domain docs: canonical home = the domain whose **decay context governs the doc**
  (whose recheck cadence applies); membership elsewhere via frontmatter `tags`, a
  "Related material elsewhere" line in the other subtopic README, and inline links.
  Never duplicated. A subtopic that wants children is two subtopics.
- **Consumers are plural and named**: the lake README lists each project consumer with a
  pointer to its corpus. Every pass provenance names the motivating consumer. Initial
  domains: `ai/`; `etl/` etc. arrive by `mkdir`.
- Single corrections ledger and recheck schedule cover all external claims.

### 3.2 Project corpora

Keep `internal/` (artifacts co-located with the code that produced them — the artifact
is the warrant), `distilled/` (per-consumer Tier-A subset + decay table), README
(consumer; project-local pass narrative; ledger for internal/distilled corrections —
external corrections belong to the lake ledger), guard.

**Citation convention:** distilled rows cite lake holdings as

```
lake:ai/rsi-lab/recursive-superintelligence-2026-07.md §5 @ <lake-commit>
```

path + section + pinned lake commit — "which edition graded this" stays answerable.
Re-pinning is a deliberate recheck-time act, never automatic.

## 4. Flow rules

1. **Content flow (applies to all profiles, adopted regardless of the lake):** any doc
   seeded or imported from another corpus records origin + commit in its provenance;
   corrections to either edition are ledgered in both. Governs the migration itself.
2. **Multi-project relevance — pull, never push.** Nothing copies findings into project
   repos (that would bypass distillation's second look). Two signals make the pull
   cheap: (i) pass checklist gains an **implications line** — the pass narrative entry
   names other project consumers plausibly implicated; (ii) each project's
   recheck/distill starts with **"diff the lake pass narrative + corrections ledger
   since my last pin"** — both append-only, so the diff is complete by construction.
3. **Method percolation — the pin mechanism.** Kit changes land in the kit (existing
   flow rule). Every corpus (lake included) pins its kit edition and keeps operating on
   the pin. At recheck (or a dedicated upgrade op): bump the pin, **diff the kit method
   files between pins**, re-grade affected rows, ledger strikes. No kit edit ever
   silently re-grades evidence.
4. **Human-learner use is in scope** as the method's audience half: the lake's subtopic
   READMEs / terminology / INDEX are the learning surface; `viz.html` renderable on
   demand. No lake-level Tier-A front door (no distilled/ in the lake) — for a one-off
   goal, generate a briefing-style artifact from holdings (EVENT-BRIEFING pattern); if a
   learning goal becomes load-bearing it is by definition a consumer → thin project
   corpus. Note both patterns in the lake README template.

## 5. Kit changes (Mode 2; the three method files + SKILL.md stay consistent)

- **scaffold.py**: `--profile standalone|lake|project` (default `standalone`, today's
  behavior). Profile selects template subset; `project` writes `lake_root` into
  corpus_guard.json; `lake` installs INDEX machinery.
- **Guard (templates/tests/test_reference.py)**: resolve the `lake:` prefix against
  `lake_root` (strip `§…`/`@…` suffixes; **fail loudly** when the target is missing —
  single-machine setup, no silent skip). Lake profile: INDEX-freshness test (regenerate
  to temp, assert no diff) and tag-registry check (every frontmatter tag is defined in
  terminology.md's registry).
- **CONVENTIONS.md**: new "Lake and project profiles" section — the table above, the
  citation convention, corrections routing, two-level rule, canonical-home tiebreak,
  cross-membership mechanics.
- **PASS-PROTOCOL.md**: external passes write into the lake (when one exists);
  provenance names motivating project/consumer; checklist adds the implications line,
  "regenerate INDEX.md", and a pre-pass dedup check ("grep INDEX.md's shared-source
  table before mirroring").
- **SKILL.md**: operation 4 (recheck) gains the lake-diff and pin-bump/method-diff
  steps; operation 2 notes the lake as the write target for external evidence.
- **README.md (kit)**: content flow rule added to the flow rules.

## 6. INDEX.md generator (`index.py`, stdlib, ~150 lines, lake-only)

Walks all `*.md` frontmatter + MANIFESTs; deterministic output, committed. Three views:

1. **Tag index** — tag → docs, cross-domain tags flagged. Tags must come from the
   registry section in terminology.md (guard-enforced) to prevent vocabulary splits.
2. **Backlink table** — inverted link graph, cross-domain edges sorted first.
3. **Shared-source report** — any URL in ≥2 MANIFESTs or cited in ≥2 subtopics; doubles
   as the pre-pass dedup surface.

`git diff INDEX.md` after a pass is the new-connections report. No database; the
knowledge-catalog `viz.html` remains an optional pretty view.

## 7. Migration (ordered; **start after the 2026-07-18 summit** — the event briefing
cites the current corpus layout; churn before the event buys nothing)

1. Kit: implement §5; smoke-test all three profiles (scaffold → guard → delete).
2. Scaffold the lake. Move `auto-research-corpus/{external/,mirrors/}` → `lake/ai/`
   (copy with provenance notes + origin commits per flow rule 1; both pass narratives
   record the migration).
3. Move outrigger's 15 external subtopics → `lake/ai/`. **Reconcile the forked systems
   doc**: the corrected auto-research edition becomes canonical; outrigger's stale
   edition retired with a pointer; the four corrections back-ledgered.
4. Convert both projects to `project` profile; rewrite distilled citations to `lake:`
   form (auto-research: 16 rows; outrigger: counted at execution). All three guards
   green.
5. First `index.py` run — the initial INDEX.md is deliverable #1: the overlap map.

## 8. Edge cases

- Two-domain doc → tiebreak + cross-membership; never duplicated.
- Lake absent → project guard fails loudly (explicit config, no magic).
- Lake doc struck → lake ledger entry; projects catch it at next pin-diff; a struck doc
  cited by a distilled row forces re-verification of that row.
- New domain → `mkdir`; zero method changes.
- EVENT-BRIEFING and similar artifacts: repoint at migration time, not before.

## 9. Testing

- Kit smoke matrix: 3 profiles × (scaffold → guard green pre-git and post-git → delete).
- Guard unit coverage: `lake:` resolution (present / missing / with §-anchor and @-pin
  suffixes); INDEX freshness; tag-registry enforcement.
- Index determinism: two consecutive runs byte-identical.
- Migration acceptance: three guards green; hand-walk of sampled distilled rows
  (distilled → lake holdings → primary); INDEX shared-source report contains the known
  overlap (the reconciled systems doc's sources).

## 10. Resolved decisions

- `@ <lake-commit>` pin on distilled citations: **adopted**; re-pin is a deliberate
  recheck act (user-approved).
- Migration timing: **post-summit** (user-approved).
- Push vs pull for multi-project relevance: **pull** with the two signals (flow rule 2).
- Discovery: generated INDEX.md only; no graph database.
