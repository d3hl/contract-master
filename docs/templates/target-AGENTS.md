# Repository directory

Before planning or editing, explicitly read:

- Local architecture, setup and verification documentation (maintained here).
- The issue and latest HANDOFF from Linear.
- The task's read-only Contract Master bundle; verify recorded source/digest.
- Shared workflow, security and contract guidance inside that bundle.

Product code, tests and API contracts live here. Shared automation policies live
in contract-master. Follow the task's allowed scope, acceptance and required checks.

Work test-first: for each plan step, write the failing test, run it and see it fail,
make the smallest change that passes, then run the required checks. Report check
output as evidence; never claim a check passed without running it. When a test
fails unexpectedly, find the cause before changing code.
Claude investigates and plans; DeepSeek implements and tests; Codex independently
verifies, reviews and merges. Send results to the coordinator. Only the manager
writes Linear. Humans handle escalations.
