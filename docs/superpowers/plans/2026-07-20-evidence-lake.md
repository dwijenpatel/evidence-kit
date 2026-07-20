# Evidence Lake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add lake/project corpus profiles to evidence-kit, then migrate the two existing corpora so all external evidence lives in one private `~/repos/evidence-lake` repo with a generated cross-domain INDEX.

**Architecture:** Three scaffold profiles (`standalone` = today's layout, `lake` = external-only + INDEX machinery, `project` = internal+distilled only with `lake:` citations resolved against a configured lake root). The guard test grows three profile-aware checks; a stdlib `index.py` generates INDEX.md (tags / backlinks / shared sources). Migration is scripted copies with provenance stamps, then citation rewrites, then guards green in all three repos.

**Tech Stack:** Python 3 stdlib only (no pip installs, ever), git, Markdown + OKF v0.1 frontmatter.

**Spec:** `docs/superpowers/specs/2026-07-20-evidence-lake-design.md` (approved). Read it before starting.

## Global Constraints

- Python **stdlib only** in scaffold.py, guard, index.py — no third-party imports.
- `--profile standalone` must be byte-identical in behavior to today's scaffolder (default).
- Guard must pass on a bare scaffold **before `git init`** for every profile.
- Placeholder set is exactly `{{TOPIC}} {{SLUG}} {{CONSUMER}} {{DATE}} {{KIT_COMMIT}} {{KIT_PATH}}`; template files named `_*.tmpl` are pass-time and skipped by the scaffolder; frontmatter values embedding `{{TOPIC}}`/`{{CONSUMER}}` stay double-quoted.
- Lake tree is `<domain>/<subtopic>/` — two levels, never deeper; no `external/` wrapper in the lake.
- Citation form (exact): `lake:<path> §<section> @ <lake-commit>` — `§`/`@` parts optional; guard resolves only the path.
- The kit repo (`~/repos/evidence-kit`) is canonical; every method change lands there first.
- Kit commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- All work in this plan is on `main` of the respective repos (no remotes except evidence-kit's origin; do not push unless asked).

---

### Task 1: Kit test harness + `--profile` flag (standalone parity)

**Files:**
- Create: `tests/__init__.py` (empty), `tests/test_scaffold.py` (kit repo root)
- Modify: `scaffold.py`

**Interfaces:**
- Produces: `scaffold.py --profile {standalone,lake,project}` CLI (default `standalone`); `PROFILES` dict in scaffold.py: `{name: {"skip_top": set[str], "overlay": str|None, "default_min_docs": int}}`; helper `run_scaffold(tmp, profile, extra=[])` in test file (used by Tasks 2–5's tests).
- Consumes: existing scaffold.py behavior (template walk, `emitted_md`, corpus_guard.json writing).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scaffold.py
"""Kit-side smoke matrix: scaffold each profile into a temp dir, run the corpus guard there."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_scaffold(tmp, profile, extra=None):
    out = os.path.join(tmp, f"corpus-{profile}")
    cmd = [sys.executable, os.path.join(KIT, "scaffold.py"),
           "--topic", "Smoke: colon topic", "--slug", "smoke",
           "--out", out, "--consumer", "smoke consumer",
           "--profile", profile] + (extra or [])
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out


def run_guard(corpus):
    return subprocess.run([sys.executable, "-m", "unittest", "tests.test_reference", "-q"],
                          cwd=corpus, capture_output=True, text=True)


class ScaffoldMatrix(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ek-smoke-")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_standalone_profile_guard_green_pre_git(self):
        corpus = run_scaffold(self.tmp, "standalone")
        r = run_guard(corpus)
        self.assertEqual(r.returncode, 0, r.stderr)
        cfg = json.load(open(os.path.join(corpus, "tests", "corpus_guard.json")))
        self.assertEqual(cfg["profile"], "standalone")
        self.assertIn("external/README.md", cfg["required"])
        self.assertIn("distilled/README.md", cfg["required"])

    def test_default_profile_is_standalone(self):
        out = os.path.join(self.tmp, "corpus-default")
        subprocess.run([sys.executable, os.path.join(KIT, "scaffold.py"),
                        "--topic", "T", "--slug", "t", "--out", out,
                        "--consumer", "c"], check=True, capture_output=True, text=True)
        cfg = json.load(open(os.path.join(out, "tests", "corpus_guard.json")))
        self.assertEqual(cfg["profile"], "standalone")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/repos/evidence-kit && python3 -m unittest tests.test_scaffold -v`
Expected: FAIL — `scaffold.py: error: unrecognized arguments: --profile standalone` (first test) and `KeyError: 'profile'` (second).

- [ ] **Step 3: Implement `--profile` in scaffold.py**

In `scaffold.py`, add after the `KIT = …` line:

```python
PROFILES = {
    # skip_top: top-level template dirs not copied · overlay: templates/<name>/ copied
    # after the main walk (overwrites collisions) · default_min_docs: guard floor that
    # passes on a bare scaffold of this profile
    "standalone": {"skip_top": set(), "overlay": None, "default_min_docs": 6},
    "lake": {"skip_top": {"external", "internal", "distilled"}, "overlay": "lake",
             "default_min_docs": 3},
    "project": {"skip_top": {"external"}, "overlay": "project", "default_min_docs": 6},
}
```

Add the argument (near the other `ap.add_argument` calls), and change `--min-docs` to default `None`:

```python
    ap.add_argument("--profile", choices=sorted(PROFILES), default="standalone",
                    help="corpus profile: standalone (default, self-contained), "
                         "lake (shared external evidence), project (internal+distilled "
                         "citing a lake)")
    ap.add_argument("--min-docs", type=int, default=None,
                    help="guard: minimum tracked markdown files (default: per-profile "
                         "floor that passes on a bare scaffold)")
```

In `main()` after parsing: `profile = PROFILES[args.profile]` and
`min_docs = args.min_docs if args.min_docs is not None else profile["default_min_docs"]`.
In the template walk, skip profile-excluded top dirs — replace the `rel = …` line's
surroundings so the inner loop starts:

```python
        rel = os.path.relpath(dirpath, src_root)
        top = rel.split(os.sep)[0]
        if top in profile["skip_top"]:
            continue
```

In the corpus_guard.json dump, add `"profile": args.profile` and use `min_docs`:

```python
        json.dump({
            "profile": args.profile,
            "required": sorted(emitted_md),
            "min_markdown_files": min_docs,
        }, fh, indent=2)
```

(Overlay handling is Task 2 — `overlay: None` makes it a no-op here.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_scaffold -v`
Expected: both tests PASS. (The guard ignores the unknown `profile` key — verify by reading the run output; no guard change needed yet.)

- [ ] **Step 5: Commit**

```bash
cd ~/repos/evidence-kit && git add tests/ scaffold.py && git commit -m "scaffold: --profile flag + kit-side smoke matrix (standalone parity)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Lake and project profile scaffolding (overlays + config)

**Files:**
- Create: `templates/lake/README.md.tmpl`, `templates/lake/index.md.tmpl`, `templates/lake/terminology.md.tmpl`, `templates/project/README.md.tmpl`, `templates/project/index.md.tmpl`
- Modify: `scaffold.py`, `tests/test_scaffold.py`

**Interfaces:**
- Consumes: `PROFILES`, `run_scaffold` from Task 1.
- Produces: overlay copy step in scaffold.py (walks `templates/<overlay>/`, same substitution + `emitted_md` accounting, overwrites main-walk output on collision); `--lake-root` argument (required iff profile=project) written to corpus_guard.json as `lake_root`; lake terminology template contains a `## Tag registry` section (consumed by Task 4's guard check).

- [ ] **Step 1: Extend the failing tests**

Append to `tests/test_scaffold.py`:

```python
    def test_lake_profile_layout_and_guard(self):
        corpus = run_scaffold(self.tmp, "lake")
        for absent in ("external", "internal", "distilled"):
            self.assertFalse(os.path.exists(os.path.join(corpus, absent)))
        body = open(os.path.join(corpus, "terminology.md")).read()
        self.assertIn("## Tag registry", body)
        self.assertIn("## Consumers", open(os.path.join(corpus, "README.md")).read())
        r = run_guard(corpus)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_project_profile_requires_and_records_lake_root(self):
        with self.assertRaises(subprocess.CalledProcessError):
            run_scaffold(self.tmp, "project")  # no --lake-root
        lake = run_scaffold(self.tmp, "lake")
        corpus = run_scaffold(self.tmp, "project", ["--lake-root", lake])
        self.assertFalse(os.path.exists(os.path.join(corpus, "external")))
        cfg = json.load(open(os.path.join(corpus, "tests", "corpus_guard.json")))
        self.assertEqual(cfg["lake_root"], lake)
        r = run_guard(corpus)
        self.assertEqual(r.returncode, 0, r.stderr)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m unittest tests.test_scaffold -v`
Expected: both new tests FAIL (no overlay templates → missing "## Tag registry"; `--lake-root` unrecognized).

- [ ] **Step 3: Write the overlay templates**

`templates/lake/README.md.tmpl`:

```markdown
---
type: Corpus
title: "{{TOPIC}} — evidence lake"
description: "Shared external-evidence lake: all primary-sourced holdings and mirrors, across domains; projects distill from here."
tags: [evidence-lake]
timestamp: {{DATE}}
consumer: "{{CONSUMER}}"
kit_commit: {{KIT_COMMIT}}
---
# {{TOPIC}} — evidence lake

Shared **external evidence** for every project corpus on this machine, built with
evidence-kit conventions, **lake profile** (kit at `{{KIT_PATH}}`, commit
`{{KIT_COMMIT}}`, {{DATE}}). Holds mirrors + holdings only — no `internal/`, no
`distilled/`: warrant is consumer-independent, distillation is not. Projects cite
holdings here as `lake:<path> §<section> @ <commit>` and distill in their own repos.

Layout: `<domain>/<subtopic>/` (two levels, never deeper — a subtopic that wants
children is two subtopics). A document lives in exactly **one** folder — canonical home
= the domain whose decay context governs it; membership elsewhere via frontmatter
`tags`, "Related material elsewhere" lines, and inline links. Domains arrive by
`mkdir`. Discovery: [INDEX.md](INDEX.md) (generated — run `python3 index.py` after
every pass).

## Consumers

<!-- One line per project consumer: name · what rests on this lake · corpus path.
     Every pass provenance names which of these motivated it. -->

- {{CONSUMER}}

*Human learners are the automatic audience (nothing at stake). For a one-off learning
goal, generate a briefing-style artifact from holdings; if a goal becomes load-bearing,
it is a consumer — give it a project corpus.*

## Pass narrative

<!-- One entry per pass: date, grade, motivating consumer, what it added, and an
     "implications" line naming other consumers plausibly implicated. Newest last. -->

- {{DATE}} — lake scaffolded; no passes yet.

## Corrections ledger

<!-- Dated entries for every falsified, narrowed, or struck external claim, lake-wide.
     Never deleted. Projects diff this ledger since their last pin at every recheck. -->

*(empty — nothing falsified yet)*

## Recheck schedule (these facts rot)

*(none registered yet)*

## Guard

After any doc change: `python3 index.py && python3 -m unittest tests.test_reference -q`
(links resolve · OKF conformance floor · every frontmatter tag registered · INDEX fresh).
```

`templates/lake/index.md.tmpl`:

```markdown
---
okf_version: "0.1"
---

# {{TOPIC}} — evidence lake

* [README](README.md) - consumers, pass narrative, corrections ledger, recheck schedule
* [Terminology](terminology.md) - every acronym, coined term, evidence tag, and the tag registry
* [INDEX](INDEX.md) - generated: tag index, backlinks, shared sources

# Evidence

* [mirrors/](mirrors/) - mirrored primaries with per-target MANIFESTs, by domain
```

`templates/lake/terminology.md.tmpl` — copy `templates/corpus/terminology.md.tmpl` verbatim, then append at the end:

```markdown

## Tag registry

Every tag used in any document's frontmatter `tags:` list must be defined here (one
line each — the guard enforces membership; this is what keeps `reward-hacking` and
`reward_hacking` from silently splitting the index).

- `evidence-lake` — this repo's own root documents.
```

`templates/project/README.md.tmpl`:

```markdown
---
type: Corpus
title: "{{TOPIC}} — evidence corpus (project profile)"
description: "Project corpus: internal evidence and the distilled Tier-A subset; external evidence lives in the lake."
tags: [evidence-corpus]
timestamp: {{DATE}}
consumer: "{{CONSUMER}}"
kit_commit: {{KIT_COMMIT}}
---
# {{TOPIC}} — evidence corpus (project profile)

Primary-sourced, graded corpus on **{{TOPIC}}**, **project profile** (kit at
`{{KIT_PATH}}`, commit `{{KIT_COMMIT}}`, {{DATE}}): this repo holds
[internal/](internal/README.md) (our own runs — artifacts live with the code that
produced them) and [distilled/](distilled/README.md) (the Tier-A subset for THIS
consumer). External evidence lives in the lake (path in `tests/corpus_guard.json`,
`lake_root`); distilled rows cite it as `lake:<path> §<section> @ <lake-commit>`.

**Consumer:** {{CONSUMER}}

## Pass narrative

<!-- Project-local operations only (internal passes, distillation, rechecks).
     External passes are recorded in the lake's narrative. Newest last. -->

- {{DATE}} — corpus scaffolded (project profile); no operations yet.

## Corrections ledger

<!-- Corrections to internal/ and distilled/ rows. Corrections to external claims
     belong in the LAKE's ledger. Never deleted. -->

*(empty)*

## Recheck discipline

Every recheck starts with: diff the lake's pass narrative + corrections ledger since
this corpus's last pin; re-pin deliberately; any lake correction touching a cited doc
forces re-verification of the citing distilled row. On kit-pin bumps, diff the kit's
method files between pins and re-grade affected rows.

## Guard

After any doc change: `python3 -m unittest tests.test_reference -q`
(links + `lake:` citations resolve · OKF conformance floor · load-bearing files exist).
```

`templates/project/index.md.tmpl`:

```markdown
---
okf_version: "0.1"
---

# {{TOPIC}} — evidence corpus (project profile)

* [README](README.md) - consumer, project pass narrative, ledger, recheck discipline
* [Terminology](terminology.md) - terms and tags used by this corpus

# Evidence

* [distilled/](distilled/README.md) - the Tier-A subset for this consumer; start here
* [internal/](internal/README.md) - evidence we generated ourselves
```

- [ ] **Step 4: Implement overlay + `--lake-root` in scaffold.py**

Add argument:

```python
    ap.add_argument("--lake-root", default=None,
                    help="project profile: absolute path to the evidence lake this "
                         "corpus cites (written to corpus_guard.json as lake_root)")
```

In `main()` after parsing, validate:

```python
    if args.profile == "project" and not args.lake_root:
        ap.error("--lake-root is required for --profile project")
```

Refactor the main template walk's per-file body into a helper so the overlay reuses it:

```python
def render_tree(src_root, out, subs, emitted_md, skip_top=frozenset()):
    for dirpath, _dirnames, filenames in os.walk(src_root):
        rel = os.path.relpath(dirpath, src_root)
        if rel != "." and rel.split(os.sep)[0] in skip_top:
            continue
        for name in filenames:
            if name.startswith("_"):
                continue  # pass-time template, not scaffold-time
            with open(os.path.join(dirpath, name), encoding="utf-8") as fh:
                body = fh.read()
            for key, val in subs.items():
                body = body.replace(key, val)
            dest_name = name[:-5] if name.endswith(".tmpl") else name
            dest_dir = os.path.join(out, "" if rel == "." else rel)
            os.makedirs(dest_dir, exist_ok=True)
            with open(os.path.join(dest_dir, dest_name), "w", encoding="utf-8") as fh:
                fh.write(body)
            if dest_name.endswith(".md"):
                rel_md = dest_name if rel == "." else f"{rel}/{dest_name}"
                if rel_md not in emitted_md:
                    emitted_md.append(rel_md.replace(os.sep, "/"))
```

Call it twice in `main()`:

```python
    emitted_md = []
    render_tree(os.path.join(KIT, "templates", "corpus"), out, subs, emitted_md,
                skip_top=profile["skip_top"])
    if profile["overlay"]:
        render_tree(os.path.join(KIT, "templates", profile["overlay"]), out, subs,
                    emitted_md)
    if args.profile == "lake":
        os.makedirs(os.path.join(out, "mirrors"), exist_ok=True)
```

Extend the corpus_guard.json dump: include `"lake_root": os.path.abspath(os.path.expanduser(args.lake_root))` when profile is `project` (omit the key otherwise).

- [ ] **Step 5: Run the full matrix**

Run: `python3 -m unittest tests.test_scaffold -v`
Expected: all 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add templates/lake templates/project scaffold.py tests/test_scaffold.py
git commit -m "scaffold: lake + project profiles (overlays, per-profile floors, lake_root)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Guard — `lake:` citation resolution

**Files:**
- Modify: `templates/tests/test_reference.py`, `tests/test_scaffold.py`

**Interfaces:**
- Consumes: corpus_guard.json keys `profile`, `lake_root` (Task 2); existing `tracked_markdown()`, `load_config` pattern in the guard.
- Produces: guard regex `LAKE_REF = re.compile(r"\blake:([\w./\-]+)")` and test `test_lake_citations_resolve` — path resolved against `lake_root`, `§`/`@` suffixes ignored by the regex by construction (they follow a space). Later tasks (9) rely on citations of non-`.md` files (e.g. `.jsonl`) also resolving.

- [ ] **Step 1: Write the failing kit-side test**

Append to `tests/test_scaffold.py`:

```python
    def test_project_guard_checks_lake_citations(self):
        lake = run_scaffold(self.tmp, "lake")
        corpus = run_scaffold(self.tmp, "project", ["--lake-root", lake])
        os.makedirs(os.path.join(lake, "ai", "topic"), exist_ok=True)
        with open(os.path.join(lake, "ai", "topic", "doc.md"), "w") as fh:
            fh.write("---\ntype: Holdings\n---\n# d\n")
        row = ("1. **Fact.** · `A3` · cited lake:ai/topic/doc.md §2 @ abc1234 "
               "and record lake:ai/topic/rec.jsonl\n")
        ext = os.path.join(corpus, "distilled", "external.md")
        with open(ext, "a") as fh:
            fh.write(row)
        r = run_guard(corpus)
        self.assertNotEqual(r.returncode, 0)          # rec.jsonl missing -> fail
        self.assertIn("lake:ai/topic/rec.jsonl", r.stderr + r.stdout)
        open(os.path.join(lake, "ai", "topic", "rec.jsonl"), "w").write("{}\n")
        r = run_guard(corpus)
        self.assertEqual(r.returncode, 0, r.stderr)   # both resolve -> pass
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_scaffold.ScaffoldMatrix.test_project_guard_checks_lake_citations -v`
Expected: FAIL at the first `assertNotEqual` — current guard ignores `lake:` text entirely, so the missing `rec.jsonl` is not reported.

- [ ] **Step 3: Implement in the guard template**

In `templates/tests/test_reference.py`, add near the other regexes:

```python
LAKE_REF = re.compile(r"\blake:([\w./\-]+)")
```

Add a test method to `CorpusLinkTests`:

```python
    def test_lake_citations_resolve(self):
        """Every `lake:<path>` citation resolves inside the configured lake root.

        Fails loudly when lake_root is unset but citations exist, and when the lake
        is not present at lake_root — a project corpus without its lake is broken
        by definition (single-machine design; see the kit spec)."""
        lake_root = CONFIG.get("lake_root")
        broken = []
        for f in tracked_markdown():
            with open(os.path.join(ROOT, f), encoding="utf-8") as fh:
                body = fh.read()
            for m in LAKE_REF.finditer(body):
                target = m.group(1).rstrip(".")
                if lake_root is None:
                    broken.append(f"{f}: lake:{target} but no lake_root configured")
                    continue
                if not os.path.exists(os.path.join(os.path.expanduser(lake_root), target)):
                    broken.append(f"{f} -> lake:{target}")
        self.assertEqual(broken, [], "unresolved lake citations:\n" + "\n".join(broken))
```

(`.rstrip(".")` guards against a citation ending a sentence; the regex already stops at whitespace, so ` §5 @ abc1234` never enters the path.)

- [ ] **Step 4: Run kit tests**

Run: `python3 -m unittest tests.test_scaffold -v`
Expected: all 5 PASS. Also re-run one standalone scaffold guard manually to confirm no regression: standalone has no `lake:` text → the new test passes vacuously.

- [ ] **Step 5: Commit**

```bash
git add templates/tests/test_reference.py tests/test_scaffold.py
git commit -m "guard: resolve lake: citations against configured lake_root

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Guard — tag-registry enforcement (lake profile)

**Files:**
- Modify: `templates/tests/test_reference.py`, `tests/test_scaffold.py`

**Interfaces:**
- Consumes: `frontmatter()` helper, `CONFIG["profile"]`, lake terminology's `## Tag registry` section (Task 2).
- Produces: guard test `test_tags_are_registered` (skips unless profile == "lake"); registry format = backticked tags in list lines under the `## Tag registry` heading.

- [ ] **Step 1: Write the failing kit-side test**

Append to `tests/test_scaffold.py`:

```python
    def test_lake_guard_enforces_tag_registry(self):
        lake = run_scaffold(self.tmp, "lake")
        os.makedirs(os.path.join(lake, "ai", "topic"), exist_ok=True)
        with open(os.path.join(lake, "ai", "topic", "doc.md"), "w") as fh:
            fh.write("---\ntype: Holdings\ntags: [unregistered-tag]\n---\n# d\n")
        r = run_guard(lake)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unregistered-tag", r.stderr + r.stdout)
        with open(os.path.join(lake, "terminology.md"), "a") as fh:
            fh.write("- `unregistered-tag` — test tag.\n")
        r = run_guard(lake)
        self.assertEqual(r.returncode, 0, r.stderr)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_scaffold.ScaffoldMatrix.test_lake_guard_enforces_tag_registry -v`
Expected: FAIL at the first `assertNotEqual` (no such guard check exists).

- [ ] **Step 3: Implement in the guard template**

Add near the other regexes in `templates/tests/test_reference.py`:

```python
FM_TAGS = re.compile(r"^tags:\s*\[([^\]]*)\]", re.MULTILINE)
REGISTERED = re.compile(r"`([A-Za-z0-9_-]+)`")
```

Add the test method:

```python
    def test_tags_are_registered(self):
        """Lake profile: every frontmatter tag is defined in terminology.md's
        '## Tag registry' section — one vocabulary, no silent splits."""
        if CONFIG.get("profile") != "lake":
            self.skipTest("tag registry is a lake-profile rule")
        term = open(os.path.join(ROOT, "terminology.md"), encoding="utf-8").read()
        section = term.split("## Tag registry", 1)
        registry = set(REGISTERED.findall(section[1])) if len(section) == 2 else set()
        bad = []
        for f in tracked_markdown():
            with open(os.path.join(ROOT, f), encoding="utf-8") as fh:
                fm = frontmatter(fh.read())
            if not fm:
                continue
            m = FM_TAGS.search(fm)
            if not m:
                continue
            for tag in (t.strip() for t in m.group(1).split(",") if t.strip()):
                if tag not in registry:
                    bad.append(f"{f}: tag `{tag}` not in terminology.md tag registry")
        self.assertEqual(bad, [], "unregistered tags:\n" + "\n".join(bad))
```

- [ ] **Step 4: Run kit tests**

Run: `python3 -m unittest tests.test_scaffold -v`
Expected: all 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add templates/tests/test_reference.py tests/test_scaffold.py
git commit -m "guard: lake tag-registry enforcement

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: `index.py` generator + INDEX freshness in guard + scaffold integration

**Files:**
- Create: `templates/lake/index.py`
- Modify: `templates/tests/test_reference.py`, `scaffold.py`, `tests/test_scaffold.py`

**Interfaces:**
- Consumes: OKF frontmatter (`title`, `tags`), MANIFEST tables (`| local | url | …` rows), markdown links.
- Produces: `python3 index.py` (regenerates `INDEX.md` in place) and `python3 index.py --check` (exit 0 fresh / 1 stale — consumed by the guard). INDEX.md carries `type: Generated Index` frontmatter. Scaffold (lake profile) runs index.py once so a bare lake has a fresh INDEX.md.

- [ ] **Step 1: Write the failing kit-side tests**

Append to `tests/test_scaffold.py`:

```python
    def test_lake_index_generated_deterministic_and_guarded(self):
        lake = run_scaffold(self.tmp, "lake")
        idx = os.path.join(lake, "INDEX.md")
        self.assertTrue(os.path.exists(idx))            # scaffold ran index.py
        first = open(idx).read()
        subprocess.run([sys.executable, os.path.join(lake, "index.py")], check=True,
                       cwd=lake, capture_output=True)
        self.assertEqual(first, open(idx).read())        # deterministic
        # cross-domain machinery: two docs sharing a tag + a URL, in two domains
        for dom in ("ai", "etl"):
            os.makedirs(os.path.join(lake, dom, "sub"), exist_ok=True)
            with open(os.path.join(lake, dom, "sub", "doc.md"), "w") as fh:
                fh.write("---\ntype: Holdings\ntitle: \"D\"\ntags: [shared-tag]\n---\n"
                         "# D\nSee https://example.com/paper for the claim.\n")
        with open(os.path.join(lake, "terminology.md"), "a") as fh:
            fh.write("- `shared-tag` — test.\n")
        r = run_guard(lake)
        self.assertNotEqual(r.returncode, 0)             # INDEX now stale -> guard fails
        subprocess.run([sys.executable, os.path.join(lake, "index.py")], check=True,
                       cwd=lake, capture_output=True)
        body = open(idx).read()
        self.assertIn("shared-tag", body)
        self.assertIn("example.com/paper", body)         # shared-source across domains
        r = run_guard(lake)
        self.assertEqual(r.returncode, 0, r.stderr)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_scaffold.ScaffoldMatrix.test_lake_index_generated_deterministic_and_guarded -v`
Expected: FAIL at the first assert (no INDEX.md; index.py doesn't exist).

- [ ] **Step 3: Write `templates/lake/index.py`**

```python
#!/usr/bin/env python3
"""Regenerate INDEX.md — tag index, backlinks, shared sources — for a lake corpus.

Deterministic, stdlib-only. Part of the evidence-kit lake profile; run after every
pass:  python3 index.py        (rewrite INDEX.md)
       python3 index.py --check  (exit 1 if INDEX.md is stale; used by the guard)
"""
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
FENCE = re.compile(r"\A---[ \t]*\r?\n(.*?)^---[ \t]*\r?$", re.DOTALL | re.MULTILINE)
FM_TAGS = re.compile(r"^tags:\s*\[([^\]]*)\]", re.MULTILINE)
FM_TITLE = re.compile(r"^title:\s*\"?([^\"\n]+?)\"?\s*$", re.MULTILINE)
LINK = re.compile(r"\[[^\]]*\]\(([^)#\s]+?)(?:#[^)]*)?\)")
URL = re.compile(r"https?://[^\s)\]>|\"']+")
SKIP_FILES = {"INDEX.md"}
SKIP_DIRS = {"tests", "mirrors"}          # mirrors enter via MANIFEST parsing only


def walk_md():
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel = os.path.relpath(dirpath, ROOT)
        top = rel.split(os.sep)[0]
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".")
                             and not (rel == "." and d in SKIP_DIRS))
        for name in sorted(filenames):
            if name.endswith(".md") and name not in SKIP_FILES:
                p = os.path.join(rel, name) if rel != "." else name
                out.append(p.replace(os.sep, "/"))
    return out


def manifests():
    out = []
    for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, "mirrors")):
        dirnames.sort()
        for name in sorted(filenames):
            if name == "MANIFEST.md":
                out.append(os.path.relpath(os.path.join(dirpath, name), ROOT)
                           .replace(os.sep, "/"))
    return out


def domain(path):
    parts = path.split("/")
    if parts[0] == "mirrors" and len(parts) > 2:
        return parts[1]
    return parts[0] if len(parts) > 1 else "(root)"


def subtopic(path):
    parts = path.split("/")
    return "/".join(parts[:2]) if len(parts) > 1 else "(root)"


def build():
    tag_map = defaultdict(list)             # tag -> [path]
    backlinks = defaultdict(list)           # target -> [source]
    url_map = defaultdict(set)              # url -> {subtopic}
    titles = {}
    for path in walk_md():
        with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
            body = fh.read()
        fm = FENCE.match(body)
        fm_text = fm.group(1) if fm else ""
        t = FM_TITLE.search(fm_text)
        titles[path] = t.group(1) if t else path
        m = FM_TAGS.search(fm_text)
        if m:
            for tag in (x.strip() for x in m.group(1).split(",") if x.strip()):
                tag_map[tag].append(path)
        base = os.path.dirname(path)
        for lm in LINK.finditer(body):
            target = lm.group(1)
            if target.startswith(("http://", "https://", "mailto:", "lake:")):
                continue
            resolved = (target.lstrip("/") if target.startswith("/")
                        else os.path.normpath(os.path.join(base, target)))
            backlinks[resolved.replace(os.sep, "/")].append(path)
        for u in URL.findall(body):
            url_map[u.rstrip(".,;")].add(subtopic(path))
    for mpath in manifests():
        with open(os.path.join(ROOT, mpath), encoding="utf-8") as fh:
            for u in URL.findall(fh.read()):
                url_map[u.rstrip(".,;")].add(subtopic(mpath))
    return tag_map, backlinks, url_map, titles


def render():
    tag_map, backlinks, url_map, titles = build()
    L = ["---", "type: Generated Index",
         "title: \"INDEX — tags, backlinks, shared sources (generated)\"",
         "description: \"Generated by index.py; do not edit. Regenerate after every pass.\"",
         "---", "", "# INDEX (generated — do not edit)", "",
         "## Tag index", ""]
    for tag in sorted(tag_map):
        docs = sorted(set(tag_map[tag]))
        doms = sorted({domain(d) for d in docs})
        cross = " **[cross-domain]**" if len(doms) > 1 else ""
        L.append(f"- `{tag}`{cross}: " + " · ".join(f"[{d}]({d})" for d in docs))
    L += ["", "## Backlinks (cross-domain edges first)", ""]
    edges = []
    for target in sorted(backlinks):
        for src in sorted(set(backlinks[target])):
            edges.append((domain(src) != domain(target), src, target))
    for cross, src, target in sorted(edges, key=lambda e: (not e[0], e[1], e[2])):
        mark = " **[cross-domain]**" if cross else ""
        L.append(f"- [{src}]({src}) → [{target}]({target}){mark}")
    L += ["", "## Shared sources (URL in ≥2 subtopics)", ""]
    for u in sorted(url_map):
        subs = sorted(url_map[u])
        if len(subs) > 1:
            L.append(f"- <{u}> — {', '.join(subs)}")
    return "\n".join(L) + "\n"


def main():
    fresh = render()
    idx = os.path.join(ROOT, "INDEX.md")
    current = open(idx, encoding="utf-8").read() if os.path.exists(idx) else None
    if "--check" in sys.argv:
        sys.exit(0 if current == fresh else 1)
    with open(idx, "w", encoding="utf-8") as fh:
        fh.write(fresh)
    print("INDEX.md regenerated")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Wire freshness into the guard template and scaffold**

Guard (`templates/tests/test_reference.py`) — add:

```python
    def test_index_is_fresh(self):
        """Lake profile: INDEX.md matches what index.py would generate right now."""
        if CONFIG.get("profile") != "lake":
            self.skipTest("INDEX freshness is a lake-profile rule")
        import subprocess, sys as _sys
        r = subprocess.run([_sys.executable, os.path.join(ROOT, "index.py"), "--check"])
        self.assertEqual(r.returncode, 0,
                         "INDEX.md is stale — run: python3 index.py")
```

Scaffold (`scaffold.py`) — after the lake `mirrors/` mkdir, generate the initial INDEX:

```python
    if args.profile == "lake":
        subprocess.run([sys.executable, os.path.join(out, "index.py")], check=True)
```

(`sys` is already imported; `subprocess` is already imported for `kit_commit()`. Also append `"INDEX.md"` to `emitted_md` before the corpus_guard.json dump so the guard's required list includes it.)

- [ ] **Step 5: Run the full kit matrix**

Run: `python3 -m unittest tests.test_scaffold -v`
Expected: all 7 PASS.

- [ ] **Step 6: Commit**

```bash
git add templates/lake/index.py templates/tests/test_reference.py scaffold.py tests/test_scaffold.py
git commit -m "lake: INDEX generator (tags/backlinks/shared-sources) + freshness guard

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Method-file updates (CONVENTIONS, PASS-PROTOCOL, SKILL, README, AGENTS)

**Files:**
- Modify: `method/CONVENTIONS.md`, `method/PASS-PROTOCOL.md`, `SKILL.md`, `README.md`, `AGENTS.md`

**Interfaces:**
- Consumes: everything Tasks 1–5 built (profiles, citation form, INDEX).
- Produces: the written contract later corpora and passes follow. Keep the three method files + SKILL.md mutually consistent (AGENTS.md Mode-2 rule).

- [ ] **Step 1: CONVENTIONS.md — add the profiles section**

Insert after the "OKF alignment" section:

```markdown
## Lake and project profiles

A machine that runs several corpora splits them by the method's own seam: **warrant is
consumer-independent, distillation is not.** Three profiles (scaffold `--profile`):

| Profile | Has | Lacks |
|---|---|---|
| `standalone` (default) | everything above | — |
| `lake` | `<domain>/<subtopic>/` holdings · `mirrors/` · generated `INDEX.md` · one README (consumers **plural**, pass narrative, corrections ledger, recheck schedule) · terminology + **tag registry** | `internal/`, `distilled/` |
| `project` | `internal/` · `distilled/` · README (consumer, project narrative, project ledger) | `external/`, `mirrors/` |

- **Lake tree is storage, not meaning**: two levels (`<domain>/<subtopic>/`), never
  deeper; a doc lives in exactly one folder — canonical home is the domain whose decay
  context governs it; membership elsewhere via `tags`, "Related material elsewhere"
  lines, and links. Never duplicate a doc. A subtopic that wants children is two
  subtopics.
- **Citations across the seam**: a project's distilled rows cite lake holdings as
  `lake:<path> §<section> @ <lake-commit>`. The pin answers "which edition graded
  this"; re-pinning is a deliberate recheck-time act. The project guard resolves
  `lake:` paths against `lake_root` in `tests/corpus_guard.json` and fails loudly when
  they don't resolve.
- **Corrections routing**: external claims → the lake's ledger; internal/distilled
  rows → the project's ledger. Projects diff the lake ledger since their last pin at
  every recheck; a lake correction touching a cited doc forces re-verification of the
  citing row.
- **Tag registry**: every frontmatter tag used anywhere in the lake is defined in
  terminology.md's "## Tag registry" (guard-enforced) — one vocabulary keeps the INDEX
  from splitting.
- **Discovery**: `INDEX.md` is generated (`python3 index.py`) — tag index with
  cross-domain flags, backlink table with cross-domain edges first, shared-source
  report (URL in ≥2 subtopics). `git diff INDEX.md` after a pass is the
  new-connections report; the guard asserts freshness.
```

- [ ] **Step 2: PASS-PROTOCOL.md — lake-aware passes**

Append to the "What a pass updates (checklist)" section's list (renumber as needed):

```markdown
8. **Lake corpora only**: regenerate `INDEX.md` (`python3 index.py`) — its diff is the
   pass's new-connections report; register any new tags in the terminology tag
   registry.
```

Insert a short section after "Declare the grade first":

```markdown
## Where a pass writes

Where a lake corpus exists (see CONVENTIONS.md, "Lake and project profiles"), external
evidence from any pass lands **in the lake** — one edition of every holding, whichever
project motivated the work. The provenance header names the **motivating consumer**
(one of the lake README's named consumers), and the pass-narrative entry ends with an
**implications line** naming any other consumers the findings plausibly implicate.
Before mirroring anything, grep `INDEX.md`'s shared-source report — if the URL is
already held, extend the existing mirror instead of re-fetching.
```

- [ ] **Step 3: SKILL.md — operations 2 and 4**

In Operation 2 step 2, after "(mirror primary sources to the corpus's declared mirror location…)", append:

```markdown
   Where a lake corpus exists, external holdings and mirrors land in the lake (see
   PASS-PROTOCOL.md, "Where a pass writes"): name the motivating consumer, add the
   implications line, check INDEX.md before mirroring, regenerate it after.
```

In Operation 4, append to the paragraph:

```markdown
Project-profile corpora start every recheck by diffing the lake's pass narrative and
corrections ledger since their last pin, then re-pin deliberately; on a kit-pin bump,
diff the kit's method files between pins and re-grade affected rows.
```

- [ ] **Step 4: README.md (kit) — content flow rule**

In "Provenance and the flow rule", append to the numbered flow-rule list:

```markdown
4. **Content flows with provenance**: a document seeded or imported from another corpus
   records its origin corpus + commit in its provenance, and corrections to either
   edition are ledgered in **both**. (With a lake this mostly disappears — one edition —
   but it governs migrations and any standalone-corpus seeding.)
```

- [ ] **Step 5: AGENTS.md — Mode-2 coupling note**

In the Mode-2 bullet about scaffold/templates coupling, extend the smoke-test sentence:

```markdown
  run the smoke test via the kit's own matrix: `python3 -m unittest tests.test_scaffold
  -q` (scaffolds every profile into a temp dir, runs each corpus guard, deletes).
```

- [ ] **Step 6: Verify consistency + guard docs**

Run: `python3 -m unittest tests.test_scaffold -q` — Expected: OK.
Manually grep for contradictions: `grep -rn "lake" method/ SKILL.md README.md AGENTS.md | grep -iv "lake:" | head -30` — each mention must match the profiles table (no stray "lake has distilled" style errors).

- [ ] **Step 7: Commit**

```bash
git add method/ SKILL.md README.md AGENTS.md
git commit -m "method: lake/project profiles — conventions, pass routing, flow rules

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Migration A — create the lake; move auto-research external/ + mirrors/

**Files:**
- Create: `~/repos/evidence-lake` (scaffolded), migration script `~/repos/evidence-lake/.migration/migrate_ar.py` (temporary, deleted after)
- Modify: `~/repos/auto-research-corpus` (removal happens in Task 9, not here — this task only copies)

**Interfaces:**
- Consumes: scaffold + guard + index.py from Tasks 1–6.
- Produces: `lake/ai/<subtopic>/` holdings (systems, landscape, eval-integrity, evaluator-construction, rsi-lab), `lake/mirrors/ai/<target>/`, verification-record JSONLs beside their holdings, tag registry seeded, INDEX generated. Task 8 merges outrigger into the same `ai/` tree; Task 9 rewrites project citations against these exact paths.

- [ ] **Step 1: Scaffold the lake**

```bash
cd ~/repos/evidence-kit && python3 scaffold.py \
  --topic "Technical research" --slug lake --out ~/repos/evidence-lake \
  --profile lake \
  --consumer "auto-research decision surface (~/repos/auto-research-corpus) · outrigger design gates (~/repos/outrigger/docs/research)"
cd ~/repos/evidence-lake && git init -qb main && git add -A && git commit -qm "lake scaffold (evidence-kit $(git -C ~/repos/evidence-kit rev-parse --short HEAD))"
python3 -m unittest tests.test_reference -q   # expected: OK
```

- [ ] **Step 2: Write and run the copy script**

`~/repos/evidence-lake/.migration/migrate_ar.py`:

```python
#!/usr/bin/env python3
"""Copy auto-research-corpus external/ + mirrors/ into the lake with origin stamps."""
import os
import re
import shutil
import subprocess

SRC = os.path.expanduser("~/repos/auto-research-corpus")
LAKE = os.path.expanduser("~/repos/evidence-lake")
ORIGIN = subprocess.run(["git", "-C", SRC, "rev-parse", "--short", "HEAD"],
                        capture_output=True, text=True, check=True).stdout.strip()
STAMP = f"origin: auto-research-corpus@{ORIGIN}"

def stamp(path):
    body = open(path, encoding="utf-8").read()
    if body.startswith("---\n") and "origin:" not in body.split("\n---", 1)[0]:
        body = body.replace("---\n", f"---\n{STAMP}\n", 1)  # first line inside fence
        open(path, "w", encoding="utf-8").write(body)

# external/<subtopic> -> ai/<subtopic> ; external root files skipped (lake has its own)
ext = os.path.join(SRC, "external")
for entry in sorted(os.listdir(ext)):
    src_p = os.path.join(ext, entry)
    if os.path.isdir(src_p):
        dst = os.path.join(LAKE, "ai", entry)
        shutil.copytree(src_p, dst, dirs_exist_ok=False)
        for dirpath, _d, files in os.walk(dst):
            for f in files:
                if f.endswith(".md"):
                    stamp(os.path.join(dirpath, f))
    elif entry.endswith(".jsonl"):                       # verification records
        os.makedirs(os.path.join(LAKE, "ai"), exist_ok=True)
        shutil.copy(src_p, os.path.join(LAKE, "ai", entry))

# mirrors/<target> -> mirrors/ai/<target>
mir = os.path.join(SRC, "mirrors")
for entry in sorted(os.listdir(mir)):
    src_p = os.path.join(mir, entry)
    if os.path.isdir(src_p):
        shutil.copytree(src_p, os.path.join(LAKE, "mirrors", "ai", entry),
                        dirs_exist_ok=False)
print(f"copied; origin pin {ORIGIN}")
```

Run: `python3 ~/repos/evidence-lake/.migration/migrate_ar.py`
Expected: `copied; origin pin <commit>`. Note: `EVENT-BRIEFING.html` (a project artifact, not a mirror) is NOT copied — Task 9 moves it into the project repo. Gitignored clone dirs / large binaries in the source stay behind; copy the source `.gitignore` mirror rules:

```bash
grep -A100 "" ~/repos/auto-research-corpus/.gitignore | sed 's|^mirrors/|mirrors/ai/|' >> ~/repos/evidence-lake/.gitignore
```

- [ ] **Step 3: Fix intra-doc relative links + seed the tag registry**

The moved docs link `../../mirrors/...` (was corpus-rooted `mirrors/`), now `../../mirrors/ai/...`. Fix and seed tags:

```bash
cd ~/repos/evidence-lake
grep -rl "mirrors/" ai/ --include='*.md' | xargs sed -i '' 's|(\.\./\.\./mirrors/|(../../mirrors/ai/|g'
python3 - <<'EOF'
import os, re
tags = set()
for dirpath, _d, files in os.walk("ai"):
    for f in files:
        if f.endswith(".md"):
            body = open(os.path.join(dirpath, f)).read()
            m = re.search(r"^tags:\s*\[([^\]]*)\]", body, re.M)
            if m:
                tags |= {t.strip() for t in m.group(1).split(",") if t.strip()}
with open("terminology.md", "a") as fh:
    for t in sorted(tags):
        fh.write(f"- `{t}` — imported 2026-07-20 from auto-research-corpus; refine definition on next pass.\n")
EOF
```

- [ ] **Step 4: Record the migration; regenerate; guard**

Append to the lake README pass narrative:

```markdown
- 2026-07-20 — **migration**: imported all external holdings + mirrors from
  auto-research-corpus@<origin-pin> (five ai/ subtopics + verification records), per
  the kit's content flow rule. Implications: both named consumers.
```

```bash
python3 index.py && python3 -m unittest tests.test_reference -q   # expected: OK
rm -rf .migration && git add -A && git commit -qm "migrate: auto-research external+mirrors -> ai/ (origin-pinned)"
```

Also append a matching entry to `~/repos/auto-research-corpus` README's pass narrative ("external holdings migrated to evidence-lake@<lake-commit>; this repo becomes project-profile in a follow-up") and commit there.

---

### Task 8: Migration B — outrigger external/ into the lake (frontmatter + fork reconciliation)

**Files:**
- Modify: `~/repos/evidence-lake` (new `ai/` subtopics), `~/repos/outrigger/docs/research/` (retirement notes only — removal in Task 9)

**Interfaces:**
- Consumes: lake tree from Task 7; guard's OKF conformance (moved docs must gain frontmatter).
- Produces: outrigger's subtopics under `lake/ai/` (union with Task 7's — name collisions resolved below); the stale `auto-research-systems-2026-07.md` fork retired; corrections back-ledgered in outrigger.

- [ ] **Step 1: Enumerate and copy**

```bash
ls ~/repos/outrigger/docs/research/external/          # record the actual subtopic list
python3 - <<'EOF'
import os, shutil, subprocess
SRC = os.path.expanduser("~/repos/outrigger/docs/research/external")
LAKE = os.path.expanduser("~/repos/evidence-lake")
ORIGIN = subprocess.run(["git", "-C", os.path.expanduser("~/repos/outrigger"),
                         "rev-parse", "--short", "HEAD"],
                        capture_output=True, text=True, check=True).stdout.strip()
print("origin pin:", ORIGIN)
for entry in sorted(os.listdir(SRC)):
    s = os.path.join(SRC, entry)
    if not os.path.isdir(s):
        continue
    d = os.path.join(LAKE, "ai", entry)
    if os.path.exists(d):
        # collision with Task 7 subtopic: copy FILES in, never overwrite; report
        for f in sorted(os.listdir(s)):
            df = os.path.join(d, f)
            if os.path.exists(df):
                print("COLLISION (skipped, resolve by hand):", entry, f)
            else:
                shutil.copy(os.path.join(s, f), df)
    else:
        shutil.copytree(s, d)
EOF
```

Expected collisions: `self-improvement/auto-research-systems-2026-07.md` if outrigger's copy sits in a subtopic name Task 7 also created — in the known layout it lives at `self-improvement/`, which Task 7 did NOT create, so the whole dir copies and the fork arrives at `ai/self-improvement/auto-research-systems-2026-07.md`. That file is the **stale fork** — delete it from the lake now (`rm ai/self-improvement/auto-research-systems-2026-07.md`); the canonical corrected edition already lives at `ai/systems/auto-research-systems-2026-07.md`. Add to `ai/self-improvement/README.md` (once it has frontmatter, next step) under "Related material elsewhere": `The systems deep-read lives at [../systems/](../systems/README.md) — this folder's earlier edition was retired 2026-07-20 (4 corrections; see the lake ledger).`

- [ ] **Step 2: OKF frontmatter pass over the imported docs**

Outrigger's docs predate the kit's OKF edition. For every imported `.md` without a `---` fence, prepend frontmatter derived per-doc — script pattern (title from first `# ` heading; description from the first non-heading paragraph's first sentence, truncated 140 chars; `type: Subtopic` for `README.md` else `type: Holdings`; `grade: retrieval` unless the doc's provenance text contains "adversarial"; `timestamp:` from a `20\d\d-\d\d(-\d\d)?` match in filename or provenance else `2026-07-20`; `origin: outrigger@<pin>`):

```python
import os, re
LAKE_AI = os.path.expanduser("~/repos/evidence-lake/ai")
ORIGIN = "outrigger@<pin printed in step 1>"
for dirpath, _d, files in os.walk(LAKE_AI):
    for f in sorted(files):
        p = os.path.join(dirpath, f)
        if not f.endswith(".md"):
            continue
        body = open(p, encoding="utf-8").read()
        if body.startswith("---\n"):
            continue
        h1 = re.search(r"^# (.+)$", body, re.M)
        title = (h1.group(1) if h1 else f[:-3]).replace('"', "'")
        para = re.search(r"^(?!#)([^\n]{20,})$", body, re.M)
        desc = (para.group(1)[:140] if para else title).replace('"', "'")
        typ = "Subtopic" if f == "README.md" else "Holdings"
        grade = "adversarial" if "adversarial" in body[:1200].lower() else "retrieval"
        dm = re.search(r"20\d\d-\d\d(?:-\d\d)?", f + body[:600])
        ts = dm.group(0) if dm else "2026-07-20"
        fm = [f"---", f"type: {typ}", f'title: "{title}"', f'description: "{desc}"',
              f"timestamp: {ts}", f"origin: {ORIGIN}"]
        if typ == "Holdings":
            fm.append(f"grade: {grade}")
        open(p, "w", encoding="utf-8").write("\n".join(fm) + "\n---\n" + body)
```

Then re-seed the tag registry for any new tags (rerun the Task 7 Step 3 tag snippet) and hand-review every generated `description:` — replace any that read as garbage.

- [ ] **Step 3: Back-ledger the fork corrections in outrigger**

Append to `~/repos/outrigger/docs/research/README.md`'s corrections ledger the four 2026-07-16 corrections from auto-research-corpus (kissing-number attribution, OpenEvolve 0.04% framing, STOP within-noise, seed-mining thread miscite — copy the four entries verbatim from `~/repos/auto-research-corpus/README.md`, prefixed "back-ledgered 2026-07-20 from auto-research-corpus:"). Commit in outrigger.

- [ ] **Step 4: Narrative, INDEX, guard, commit**

Lake README pass narrative:

```markdown
- 2026-07-20 — **migration**: imported outrigger's external subtopics into ai/
  (origin-pinned outrigger@<pin>; OKF frontmatter added); retired the stale
  auto-research-systems fork in favor of the corrected ai/systems/ edition (4
  corrections back-ledgered to outrigger). Implications: both named consumers.
```

```bash
cd ~/repos/evidence-lake && python3 index.py && python3 -m unittest tests.test_reference -q
git add -A && git commit -qm "migrate: outrigger external -> ai/ (frontmatter added, fork retired)"
```

Expected: guard OK (any failure here is a real frontmatter/link defect in the import — fix, don't skip).

---

### Task 9: Migration C — convert both projects; rewrite citations; acceptance

**Files:**
- Modify: `~/repos/auto-research-corpus` (delete `external/`, `mirrors/`; move EVENT-BRIEFING; rewrite `distilled/*.md`; edit README + corpus_guard.json), `~/repos/outrigger/docs/research/` (same shape), `~/repos/evidence-lake` (nothing — read-only here)

**Interfaces:**
- Consumes: lake paths from Tasks 7–8; guard `lake:` resolution from Task 3; citation form from Global Constraints.
- Produces: both corpora as `project` profile, guards green ×3, INDEX as the overlap report.

- [ ] **Step 1: auto-research-corpus conversion**

```bash
cd ~/repos/auto-research-corpus
PIN=$(git -C ~/repos/evidence-lake rev-parse --short HEAD)
mkdir -p briefings && git mv mirrors/EVENT-BRIEFING.html briefings/
git rm -rq external mirrors
```

Rewrite distilled citations (`distilled/external.md`, `distilled/internal.md`): every relative citation into the old `external/` tree becomes plain-text `lake:` form. Script:

```python
import os, re
PIN = os.popen("git -C ~/repos/evidence-lake rev-parse --short HEAD").read().strip()
for name in ("distilled/external.md", "distilled/internal.md"):
    body = open(name, encoding="utf-8").read()
    # [label](../external/<p>.md) -> `lake:ai/<p>.md @ PIN` ; jsonl likewise
    body = re.sub(r"\[([^\]]+)\]\(\.\./external/([^)]+?)\)",
                  lambda m: f"`lake:ai/{m.group(2)} @ {PIN}`", body)
    open(name, "w", encoding="utf-8").write(body)
print("rewritten @", PIN)
```

Where a row's citation text carried a section (`[rsi-lab §5](…)`), the § lives in the label and survives inside the backticks — hand-check each of the 16 external rows + 3 internal rows reads sensibly: format target `` `lake:ai/rsi-lab/recursive-superintelligence-2026-07.md §5 @ <pin>` ``. Update `tests/corpus_guard.json`: set `"profile": "project"`, add `"lake_root": "/Users/dwijen/repos/evidence-lake"`, and remove the now-deleted `external/*` entries from `required` (keep README.md, index.md, terminology.md, distilled/*, internal/README.md). Update README: Mirrors section → "External evidence + mirrors live in the lake: `~/repos/evidence-lake` (`ai/`), pinned per distilled row"; index.md: drop the `external/` line, add a lake pointer line; pass narrative entry for the conversion. Update `briefings/EVENT-BRIEFING.html` footer's corpus-of-record paths (`mirrors/` → `~/repos/evidence-lake/mirrors/ai/`; verdicts path → `~/repos/evidence-lake/ai/rsi-lab/…`).

Run: `python3 -m unittest tests.test_reference -q` — Expected: OK (guard now exercises `lake:` resolution for every rewritten row — this IS the citation-chain check). Commit.

- [ ] **Step 2: outrigger conversion**

Same shape in `~/repos/outrigger/docs/research/`: delete `external/`; rewrite its `distilled/*.md` citations to `lake:ai/... @ $PIN`; its guard config gains `profile`/`lake_root` (outrigger's corpus predates the OKF guard — install the current guard: copy `~/repos/evidence-kit/templates/tests/test_reference.py` over its `tests/test_reference.py`, and bring its docs to the conformance floor with the same frontmatter script as Task 8 Step 2 scoped to `internal/`, `distilled/`, root files). README/index.md updates as in Step 1. Run guard — expected OK. Commit (respect outrigger's branch discipline if its mainline is protected; otherwise main).

- [ ] **Step 3: Acceptance (spec §9)**

```bash
cd ~/repos/evidence-kit && python3 -m unittest tests.test_scaffold -q      # OK
cd ~/repos/evidence-lake && python3 index.py --check && python3 -m unittest tests.test_reference -q   # OK
cd ~/repos/auto-research-corpus && python3 -m unittest tests.test_reference -q  # OK
cd ~/repos/outrigger/docs/research && python3 -m unittest tests.test_reference -q  # OK
```

Hand-walk three sampled distilled rows (one per repo tier): distilled row → `lake:` path opens → holdings §section exists → cited primary/mirror reachable. Open `~/repos/evidence-lake/INDEX.md` and confirm: the shared-source report lists at least one URL held by both an ex-outrigger and an ex-auto-research subtopic, and cross-domain flags render. Record the INDEX highlights in the lake README pass narrative as the migration's closing entry.

- [ ] **Step 4: Final commits + report**

Commit any stragglers in all three repos. Report to the user: lake commit, both project pins, collision list from Task 8 (if any), and the first INDEX overlap findings.

---

## Self-Review (completed at write time)

- **Spec coverage**: §3 profiles → Tasks 1–2; §3.2 citations → Tasks 3, 9; §4 flow rules → Task 6 (rules 1–3) and templates in Task 2 (rule 4 learner note); §5 kit changes → Tasks 1–6; §6 INDEX → Task 5; §7 migration steps 1–5 → Tasks 7–9; §8 edge cases → Task 3 (lake absent), Task 8 (fork), Task 9 (briefing repoint); §9 testing → Tasks 1–5 matrix + Task 9 acceptance. No gaps found.
- **Placeholder scan**: `<pin>` / `<origin-pin>` / `<lake-commit>` occurrences are runtime-determined values with the exact command that produces them adjacent — not plan placeholders. No TBDs.
- **Type consistency**: `run_scaffold`/`run_guard` signatures uniform across Tasks 1–5; corpus_guard.json keys (`profile`, `required`, `min_markdown_files`, `lake_root`) consistent across Tasks 1, 2, 3, 9; `lake:` regex identical in Task 3 and Global Constraints; INDEX filename and `--check` contract identical in Tasks 5, 9.
