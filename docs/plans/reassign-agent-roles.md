# Plan: reassign workflow roles (Claude plans/decides, Codex verifies/reviews/merges)

## Context
Today: Codex investigates, plans, verifies and makes the completion decision; DeepSeek
implements; a **human** reviews and merges, and the code enforces that (GitHub `User`
merger + `User` approval on the exact head).

Target split (user request):

| Owner | Responsibility |
|---|---|
| Linear | Requirements, priority, dependencies, acceptance criteria, bounded plans, progress, HANDOFF (unchanged) |
| contract-master | Shared contracts, registry, pinned context, durable queue, workspace ownership, recovery, serialized Linear writes (unchanged) |
| Orca | Sole scheduler/coordinator (unchanged); coordinator turn now runs on **Claude** |
| Claude | Code investigation, brainstorming, design, planning, completion decision |
| DeepSeek | Scoped implementation, tests, requested corrections (unchanged) |
| Codex | Independent verification, PR review, merge |
| Human | **Escalation only** (second failed verification, provider errors, scope disputes); may still veto a PR |

Decisions confirmed with user: humans are optional/escalation-only; Claude is the Orca
coordinator provider.

Out of scope (still forbidden by AGENTS.md): live workers, provisioning the Codex GitHub
bot credential, enabling automation, any real merge. This change is contracts, code,
config, tests and docs only. Creating the Codex merge identity becomes a pilot gate.

## Phase gate changes (docs/policies/workflow.md)
1. **planning** — Claude (was Codex): investigation, brainstorming/design, bounded plan.
2. **ready → implementing** — unchanged (DeepSeek).
3. **verifying** — Codex, unchanged: reads diff, reruns registry checks at output commit.
4. **rework** — unchanged; max two attempts; second failure escalates to human.
5. **awaiting_review** (keep the phase name to avoid churn; meaning becomes
   "awaiting Codex review/merge") — Codex submits a GitHub APPROVE review from its
   registered bot identity on the exact verified head, then merges. A new head still
   invalidates verification. A human `CHANGES_REQUESTED` as the latest human review on
   that head blocks merge (veto kept, approval not required).
6. **done** — Claude reads provider merge facts, confirms the merge was by the
   registered Codex identity at the accepted head, checks squash/rebase correspondence,
   reruns checks on the merged commit and records completion (`author: claude`).

No change to `contract_master/phases.py` (phases/transitions stay the same).

## Code and contract changes

### Schemas (`contracts/v1/`) — edit v1 in place (nothing is live yet; note it in HANDOFF)
- `plan.schema.json`, and the embedded plan in `task.schema.json`: `author` const `codex` → `claude`.
- `completion.schema.json`: `author` → `claude`; rename `human_reviewer` → `reviewer`,
  `human_merger` → `merger` (both required, minLength 1).
- `verification-result.schema.json`: stays `codex`.
- `runner.schema.json`: role enum add `claude`.

### `contract_master/github.py` (stays read-only)
- `confirm(repository_url, pr_url, accepted_commit, merge_identity)`:
  - require `merged`, head == accepted commit, `merged_by.login == merge_identity["login"]`
    and `merged_by.type == merge_identity["type"]` (e.g. `Bot`);
  - require latest review from the Codex identity to be `APPROVED` on the exact head;
  - reject if any human's latest non-comment review on that head is `CHANGES_REQUESTED`;
  - return `reviewer`, `merger` (renamed keys); update evidence text.
- Keep the existing pagination and null `merged_by` handling.

### `contract_master/manager.py`
- `MERGE_FIELDS` and the `required` set in `confirm_merge` → `reviewer`, `merger`.
- `confirm_merge` passes `repo["merge_identity"]`; refuse if missing.
- Triage comment: "Claude planning" (line ~102). `complete` error text: "Independent
  provider confirmation of Codex review and merge required".
- `prepare_dispatch` live gate (`gates_open`): also require a configured `merge_identity`.

### Other code
- `contract_master/adapters.py:192` message → "reconciled by Claude".
- `contract_master/readiness.py`: blocker when `merge_identity` is missing, and when
  `planning_runner != "claude"` or `verification_runner`/`merge_runner != "codex"`.

### Config
- `config/registry.json` per repo: `planning_runner: "claude"`, keep
  `verification_runner: "codex"`, add `merge_runner: "codex"` and
  `merge_identity: null` (placeholder; readiness reports it as a blocker).
- `config/orca-automation.json`: `provider: "claude"` (stays `enabled: false`).

### Tests (update fixtures, add cases)
- `tests/support.py`: plan/completion `author: "claude"`, renamed merge fields, fake
  provider receipts, registry fixture with `merge_identity` `{login: "codex-bot[bot]", type: "Bot"}`.
- `tests/test_adapters.py`: Codex-identity merge accepted; human merger or other bot
  rejected; missing Codex approval rejected; human `CHANGES_REQUESTED` on head blocks;
  no human approval needed; null `merged_by` still clean refusal.
- `tests/test_workflow.py`: rename `test_09` to "...final_claude_confirmation"; bad
  author cases (`codex` now rejected for plan/completion); live gate refuses without
  `merge_identity`.
- `tests/test_phase_gates.py`: `MergedProvider` fixture keys.
- Readiness test for the new blockers.

## Docs
Update the role table, phase gates and wording ("Codex plans", "humans review and
merge", "final Codex confirmation") in:
- `AGENTS.md` (summary paragraph: "Claude plans and decides completion; DeepSeek
  implements; Codex verifies, reviews and merges; humans handle escalations. Never mark
  Done before Codex merge and final Claude confirmation.")
- `docs/policies/workflow.md` (table, intake "Orca/Claude propose clarifications",
  phase gates, Trust: `author` assertions are data, not auth)
- `docs/contracts/v1.md`, `docs/operations/coordinator-prompt.md`,
  `docs/operations/orca.md`, `docs/operations/pilot.md` (new gate: create Codex GitHub
  bot identity, branch protection requiring its approval, record `merge_identity`),
  `docs/templates/target-AGENTS.md`, `docs/onboarding/repositories.md`, `README.md`.
- `docs/operations/HANDOFF.md`: record the role change and the in-place v1 schema edit.
- Leave historical records unchanged (`d3s-99-review.md`, `linear-status-audit.md`,
  `runner-verification.md`); add a one-line note at the top of `verification.md` if it
  describes the old flow as current.

## Execution
Work on a new branch from `main` (e.g. `feat/reassign-agent-roles`); one PR.

## Verification
- `python3 -m unittest discover -s tests -v` passes (includes `test_style.py`, 120 cols).
- `grep -rniE "human (review|merge)|final codex|codex (plan|investigat)" AGENTS.md README.md docs/policies docs/operations/{orca,pilot,coordinator-prompt}.md docs/contracts docs/templates contract_master`
  returns nothing stale.
- `python3 -m contract_master doctor` (readiness) lists the new `merge_identity` blocker.
