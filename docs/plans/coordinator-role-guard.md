# Plan: enforce the coordinator role (Claude plans, DeepSeek implements, Codex merges)

Status: implemented on branch `d3adc3II/coordinator-role-guard` (2026-11-28); live
automation change waits for merge. Tracking: bead `contract-master-ber`.

## Context

The role split lived only in `AGENTS.md` and `docs/policies/`. Claude Code loads
`CLAUDE.md`, which held only the Beads block, so manual sessions never saw the rules.
The superpowers session hook also pushes `subagent-driven-development` and
`executing-plans`, and the orchestration guide defaults `--agent` to the caller's own
agent, so "hand off" quietly became "Claude does it". Nothing blocked Edit/Write.

## Changes

1. **Load the rules.** `CLAUDE.md` imports `AGENTS.md`, `workflow.md` and
   `superpowers.md` and states the role, the handoff targets and the one exception
   (a person asks for a contract-master change).
2. **Coordinator-only settings.** `.claude/coordinator-settings.json` denies Claude
   implementer subagents and runs the guard as a `PreToolUse` hook. It is not in the
   shared `.claude/settings.json`, so manual manager changes still work.
3. **Guard.** `contract_master/guard.py`: writes only under the temp directory; no
   `git commit`/`git push`/`gh pr merge`; no `--agent`/`--provider claude…`;
   `worker-start` only to an enabled DeepSeek runner from the registry. Fails closed.

## Rejected

- Deny rules alone: path globs cannot allow temp spec files while denying the rest
  (deny wins over allow), and they cannot check `worker-start` flags.
- Guard in the shared settings: it would block the manual changes the policy allows.
- Disabling superpowers: the policy still uses four of its skills; the role text and
  the guard override the conflicting ones.

## Verification

`python3 -m unittest discover -s tests -v` (new `tests/test_guard.py`). After merge,
set the automation's `--extra-agent-args` (command in `docs/operations/orca.md`) and
confirm a fresh coordinator turn sees a guard refusal for a test Write in the repo.
