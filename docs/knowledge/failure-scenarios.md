# Pilot failure scenarios (gate 8)

The ten numbered `WorkflowTests` in `tests/test_workflow.py` inject faults against
temporary Git repositories and a local SQLite manager database. They send no live
messages and make no model calls. `Result` is the pass/fail recorded by the run below;
`Obs` is `live` (also observed live in D3S-114) or `sim` (simulation only).

## Run

Command, on Python 3.9.25 on 2026-10-30:

    python3 -m unittest discover -s tests -p test_workflow.py -k WorkflowTests.test_0 -k WorkflowTests.test_10 -v

Summary: `Ran 10 tests in 15.825s` — `OK`.
Rerun at the output commit: the same ten tests pass (`OK`).

## Commit identity

A commit cannot contain its own SHA. These results were produced on the tree of the
commit that adds this note; its parent is `a6bccb78fcbb4f1f98ba6e4dc9e6d3e4dfd91a3c`,
and it changes only `docs/knowledge`, so code and tests are byte-identical to
`a6bccb7`. The output commit SHA is recorded in the implementation result and by
Codex in verification after rerunning this command at that exact commit.

## Scenarios

|#|Test method|Injected fault|Required safe outcome|Result|Obs|
|---|---|---|---|---|---|
|01|test_01_full_simulated_lifecycle|none (happy path)|review→done; no requeue|pass|live|
|02|test_02_incomplete_tracking_and_blocked_remain_unqueued|incomplete/tracking/blocked|ContractError; no row|pass|sim|
|03|test_03_concurrent_duplicate_intake|20 concurrent intakes|one queue, one task_id|pass|sim|
|04|test_04_dependency_change_reconsiders_waiting_issue|dependency marked done|queue once; no duplicate|pass|sim|
|05|test_05_restart_retains_identity_workspace_and_context|restart; second owner|same task/token; refuse|pass|live|
|06|test_06_missing_context_and_capabilities_prevent_dispatch|missing cap/context|ContractError; attempt 0|pass|sim|
|07|test_07_failed_acceptance_rework_then_escalation|two failed verifications|rework then escalated|pass|sim|
|08|test_08_new_commit_invalidates_verification|new commit C observed|verification cleared|pass|sim|
|09|test_09_done_requires_merge_and_final_claude_confirmation|invalid completions|all refused|pass|sim|
|10|test_10_outage_handoff_and_lost_ack_reconcile_without_duplicates|offline, lost ack|no duplicate sends|pass|sim|

Notes:
- 02: the incomplete issue raises `ContractError`; the tracking parent and the issue
  with an unmet dependency are not queued, and no task row is created.
- 05: the same token is returned on reclaim; another owner/workspace and
  `prepare_dispatch` are refused.
- 09: completion is refused before verification, with a bad merger, a non-Claude
  author, a wrong accepted commit and a failed check.

## Observation provenance

01 and 05 were also observed live in D3S-114: 01 via the plan, DeepSeek Dispatch
`ctx_56bf0be2af03`, Codex verification, PR d3hl/contract-master#29 merged by
`d3hl-codex[bot]` as `a6bccb7`, Claude completion and Done; 05 via coordinator run
107 resuming the task left `awaiting_review` by run 105 with the same task and owner.
Scenarios 02-04 and 06-10 are simulation only, not observed live.
[Issue](https://linear.app/d3space/issue/D3S-114) ·
[PR #29](https://github.com/d3hl/contract-master/pull/29).

Gate 8 is not claimed as passed here; it is recorded separately after this issue is Done.
