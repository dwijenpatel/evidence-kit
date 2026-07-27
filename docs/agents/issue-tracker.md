# Issue tracker — local markdown

This repo uses the local-markdown tracker convention (no hosted tracker).

- Tickets live under `.scratch/<effort-slug>/issues/`, one file per ticket,
  numbered `NN-slug.md` in dependency order. `.scratch/` is git-ignored:
  working state stays machine-local and out of the public repository.
- Each ticket carries `**Blocked by:**` (numbers/titles, or "None") and a
  `**Status:**` line (`ready-for-agent` → `in-progress` → `done`).
- The frontier = tickets whose blockers are all `done`. Claim a ticket by
  setting `in-progress` before starting work.
- Wayfinder maps, when used, live at `.scratch/<effort-slug>/map.md` with the
  same privacy posture.

Triage labels: `ready-for-agent` is the only label in use.
