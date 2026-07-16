@AGENTS.md

## Claude Code-specific notes

- This repo doubles as a user-level skill: `ln -s <this-clone> ~/.claude/skills/evidence-kit`
  makes the four operations available in every project (see README "Using it with your
  agent").
- Fan-outs in PASS-PROTOCOL.md map to the Agent tool (background sub-agents); the
  adversarial grade's three verification lenses are three parallel agents with distinct
  mandates.
