# Bootstrap verification

The bootstrap suite uses real temporary Git repositories and SQLite transactions,
with simulated Linear/provider/model adapters. It does not call a model, start
Orca workers, change integration settings, deploy, push or merge.

| Required scenario | Automated evidence |
|---|---|
| Intake → triage → plan → implementation → verification | `test_01_full_simulated_lifecycle`; task envelope includes full plan, pinned context and checks |
| Incomplete / parent / blocked stays unqueued | `test_02_*`, adapter parent/missing-block test |
| Duplicate and concurrent intake | `test_03_concurrent_duplicate_intake`, workspace collision test |
| Dependency changes reconsider | `test_04_*`, reopening dependency dispatch fence |
| Interrupted identity/context/workspace retained | `test_05_*`, persisted Orca receipt test |
| Missing/corrupt context and unsupported runner | `test_06_*`, unreviewed/corrupt bundle and disabled live-runner tests |
| Rework and attempt escalation | `test_07_*`, rework envelope corrections test |
| New commits invalidate verification | `test_08_*`, stale verdict rejection |
| Human merge and final Codex gate | `test_09_*`, independent provider confirmation, exact-head approval, bot/repository/stale approval tests |
| Linear outage and duplicate-free recovery | `test_10_*`, concurrent outbox single-send, ambiguous absent write blocks queue |

Additional checks cover malformed scope edits, project remapping, unchanged
revision recovery after clarification, frozen retry commands, source bundle
isolation from mutable worktrees, capped/partial provider reads and real Git
checkout/diff/test evidence. Failed acceptance evidence cannot be marked passing.

Live read-only verification used Orca 1.4.235's exact guides and full reads of newly
created D3S-99/D3S-100 to establish dependency direction. Shared agent notes and Mem0
were unavailable; neither was treated as evidence. A separate [live DeepSeek/OpenCode capability probe](runner-verification.md)
subsequently passed 7 fixture and 38 repository checks independently at its output
commit. Actual GitHub merge verification remains unperformed; no merge is
authorized by the capability probe. Python 3.13 coverage is prepared in CI, not claimed as
locally executed (local runtime is Python 3.9.25).

Final local run: **38 tests passed** on Python 3.9.25 (42.229 seconds). CLI
help/doctor, bytecode compilation, documentation-link, JSON, whitespace and
credential-pattern checks also passed. Log: `.state/verification.log` (ignored).

Post-bootstrap (uncommitted) changes add `tests/test_phase_gates.py` (every
operation × phase pair, transition table, rework cannot skip dispatch) and adapter
tests for provider read failures. Local run on `23ec8b7` plus those changes:
**45 tests passed** on Python 3.9.25 (about 62 seconds).

A live **read-only** reconciliation of the new project completed successfully:
three ineligible/tracking issues, zero tasks, zero Linear writes, zero workers.
It also exposed and fixed the installed Orca UUID-read limitation; a regression
test preserves UUID task identity while using provider identifiers in the outbox.

A subsequent [authenticated Linear settings inspection](linear-status-audit.md)
read and captured the actual D3S default PR destinations, empty branch-override
section, auto-close rules, disabled commit linking, empty GitHub issue-sync list,
GitLab Enable state and paid-plan Loops gate. Inspection completed without changing
settings; the completion gate fails on PR merge → Done and automatic parent closure.
