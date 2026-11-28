# Plan: enforce the coordinator role (Claude plans, DeepSeek implements, Codex merges)

Status: guard merged in PR #77 (2026-11-28). Activation reworked on branch
`d3adc3II/lease-gated-guard`: Orca refused the planned `--settings` launch argument.
Tracking: beads `contract-master-ber` (done) and `contract-master-9ol`.

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
2. **Lease-gated shared hook.** The shared `.claude/settings.json` runs the guard as a
   `PreToolUse` hook for every session, but the guard acts only while a coordinator
   turn holds a live turn lease. Manual manager changes outside turns still work.
   (First version: a coordinator-only `--settings` file passed through the
   automation's `--extra-agent-args`. Orca rejects that: "\"--settings\" isn't allowed
   in extra arguments for Claude. Allowed: --model, --effort, --add-dir.")
3. **Guard.** `contract_master/guard.py`: writes only under the temp directory; no
   `git commit`/`git push`/`gh pr merge`; no `--agent`/`--provider claude…`;
   `worker-start` only to an enabled DeepSeek runner from the registry; only read-only
   subagents. Fails closed during a turn; an unreadable lease database means no turn.

## Rejected

- Deny rules alone: path globs cannot allow temp spec files while denying the rest
  (deny wins over allow), and they cannot check `worker-start` flags.
- Always-on guard in the shared settings: it would block the manual changes the policy
  allows. Gating on the turn lease keeps them working outside turns.
- Orca environment markers: none is documented for automation runs; the lease is the
  manager's own record of a turn and is already held for the whole turn.
- Disabling superpowers: the policy still uses four of its skills; the role text and
  the guard override the conflicting ones.

## Verification

`python3 -m unittest discover -s tests -v` (`tests/test_guard.py`). The automation needs
no change. After merge, confirm with a throwaway turn: `turn-start`, then a Claude
session in the checkout tries a Write in the repo (refused), then `turn-end`.
