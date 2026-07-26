@AGENTS.md

## Claude Code-specific notes

- This repo doubles as a user-level skill: `ln -s <this-clone> ~/.claude/skills/evidence-kit`
  makes the four operations available in every project (see README "Using it with your
  agent").
- Fan-outs in PASS-PROTOCOL.md map to the Agent tool (background sub-agents); the
  adversarial grade's three verification lenses are three parallel agents with distinct
  mandates.

## Engineering conventions

Numbered so a review pass can quote them. A convention that lives only in a task spec is
requested of one implementer and enforced on none.

1. **Python 3, standard library only.** Neither `scaffold.py` nor the guard template may
   import a third-party package — a corpus must run its own guard on a bare machine.
2. **`unittest`, never `pytest`.** Kit-side tests live in `tests/`; the corpus-side guard
   ships as the template `templates/tests/test_reference.py`.
3. **The kit stays standalone.** No absolute local path, machine-specific location, or
   private-project name may appear in `method/`, `templates/`, `SKILL.md`, or
   `scaffold.py`. `{{KIT_PATH}}` is the one sanctioned local path, substituted at
   instantiation.
4. **Templates named `_*.tmpl` are pass-time** and must never be instantiated by
   `scaffold.py`; `render_tree` skips them by prefix. Adding one requires no scaffolder
   change — relying on that is correct, not a shortcut.
5. **The placeholder set is exactly** `{{TOPIC}} {{SLUG}} {{CONSUMER}} {{DATE}}
   {{KIT_COMMIT}} {{KIT_PATH}}`. Adding a placeholder without updating `scaffold.py`
   ships a corpus with a literal `{{…}}` in it.
6. **Frontmatter values embedding `{{TOPIC}}` or `{{CONSUMER}}` stay double-quoted.**
   `scaffold.py` rejects `"`, `\`, and newline in those inputs; nothing else guards
   template YAML validity.
7. **A guard check collects every offender, then asserts once** —
   `self.assertEqual(bad, [], "<what failed>:\n" + "\n".join(bad))`. Failing on the first
   offender hides the rest and turns one fix cycle into many.
8. **Assert on message substrings, never whole sentences.** Exact-message asserts reject
   correct rephrasings.
9. **Numbers that must line up get tables; reasoning stays in prose; dates are absolute,
   never "recently."**
10. **After any change to `templates/` or `scaffold.py`, run**
    `python3 -m unittest tests.test_scaffold -q`. It scaffolds every profile into a temp
    directory, runs each corpus guard, and deletes.
11. **`method/`'s three files and `SKILL.md` stay mutually consistent.** A change to one
    usually implicates the others; check before committing.
12. **Python tooling is `uv`** (`uv run`, `uv tool`) — never `pip`, `venv`, or
    `requirements.txt`.

### Fetcher conventions (added 2026-07-25, retrieval plan)

The fetcher is the kit's first component with third-party dependencies. Rules 13–20 exist
so that fact stays contained.

13. **The fetcher is its own `uv` project under `fetcher/`**, with `fetcher/pyproject.toml`
    declaring every dependency. **The repository root stays dependency-free**: rule 1 binds
    `scaffold.py` and `templates/tests/test_reference.py`, which must still run on a bare
    machine with no install step. Nothing under `fetcher/` may be imported by either.
14. **The fetcher never writes a corpus's tracked files.** It writes exactly two things: raw
    bytes into the cache directory, and append-only lines to the manifest. Editing a
    holdings doc, a `Parameters` table, or a README is an agent's job, never the fetcher's.
15. **One manifest entry per attempt, written before interpretation.** A 503 followed by a
    200 is two entries. Never collapse attempts into a per-URL status — a transient failure
    recorded as a fact about the world is the defect this component exists to prevent.
16. **The fetcher does not extract.** It fetches and records; parsing, extraction, and
    judgment are downstream and out of scope. A fetcher that returns cleaned text has
    reintroduced the defect it replaced.
17. **Politeness defaults are: one connection per host, `Crawl-delay` honoured up to a 60s
    ceiling, and 5–10s between requests to a host that declares none.** Cross-host
    concurrency may be high; politeness is a per-host obligation.
18. **A 403 is treated as a rate-limit signal on first occurrence**, never as a permanent
    block. Escalation to blocked requires persistence across backoff cycles at reduced
    pace, or a robots.txt rule.
19. **Fetcher tests use `unittest` and make no network calls.** Bind a
    `http.server.ThreadingHTTPServer` on `127.0.0.1:0` inside the test. A test that reaches
    the public internet is non-deterministic, impolite, and fails on a plane.
20. **A JSON response and an HTML response take the same code path** through queue,
    throttle, cache, and manifest. Format-specific handling belongs downstream of the
    fetch, keyed on `content_type` — never as a second fetch path.
