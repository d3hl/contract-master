# D3S-99 technical review and automation remediation

Reviewed by Codex on 2026-10-25. Source: commit
`32e4e4630b237cb1a9c442355940bba1eb6a2dae` of `d3hl/contract-master`.
This is a technical review of the disabled bootstrap. It does not constitute
human approval, a merge receipt, or permission to enable the production pilot.

## Technical assessment

The bootstrap meets its simulation acceptance criteria. No blocking defect was
identified in the reviewed coordinator paths within this assessment. Production
activation remains blocked by the external gates below.

| D3S-99 criterion | Reviewed evidence |
|---|---|
| Ten workflow scenarios | `tests/test_workflow.py` scenarios `test_01` through `test_10`; simulated lifecycle, intake, deduplication, dependencies, restart, context, rework, stale head, completion and outages |
| Identity, ownership and pinned context survive restart | `store.py` transaction/uniqueness constraints, `manager.py` claim/recovery, `context.py` Git blob extraction and digest validation; concurrent intake, restart and workspace collision tests |
| Incomplete work, context, unsupported runners and stale evidence fail closed | Schema validation, normalized full issue reads, scoped registry checks, report bindings, live dispatch gates and exact-head provider approval checks; adapter and negative-path tests |
| Two implementation attempts | `prepare_dispatch` increments the durable attempt; failed verification after attempt two escalates; scenario `test_07` |
| Serialized Linear updates and durable HANDOFF | Outbox persists `sending` before I/O, reconciles delivery by stable marker, blocks uncertain writes and preserves ordering; HANDOFF persists before export; outage and concurrency tests |
| Disabled bounded pilot | Registry automation remains false, reviewed allowlist empty, merge gate false and registered runner disabled; pilot scope is `docs/knowledge` and check ID `unit` |
| Orca evidence and simulation limits | Installed 1.4.235 guide and command evidence recorded in repository operations docs; simulations are explicitly distinguished from the separate D3S-101 real runner probe |

Independent baseline verification in this workspace at the source SHA:
`python3 -m unittest discover -s tests -v` — **38 passed**, 51.924 seconds,
Python 3.9.25. This is the run from the immediately preceding D3S-100 preflight;
the reviewed implementation has not changed. No live pilot was exercised.

The review covered the manager state transitions, SQLite ownership/outbox,
contracts, context extraction, issue normalization/reconciliation, verification
helper, GitHub merge adapter, acceptance tests and disabled configuration. Worker
report fields and an account's GitHub `User` type are not independent proof that
a human acted: the coordinator must preserve actual role provenance and obtain
the required human review/merge. File-scope checks are not an operating-system
sandbox, as the workflow already documents.

## Current automation evidence

Fresh authenticated readback of the D3S workflow page still shows the following
rules. No settings were changed in this review.

| Rule | Current value | Required target for manager-only workflow writes |
|---|---|---|
| Draft PR opened | No action | No action |
| PR/commit opened | In Progress | No action |
| PR review request/activity | In Review | No action |
| Ready for merge | No action | No action |
| PR/commit merged | Done | No action |
| Automatic parent closure | Enabled | Disabled |
| Automatic child closure | Disabled | Disabled |
| Stale issue closure | Enabled, one month to Canceled | Disabled for manager-owned waiting work |

Source: [D3S Workflows & automations](https://linear.app/d3space/settings/teams/D3S/workflow).
These controls apply to the team; no project-only override is exposed on that
page. Changing the defaults would also stop automatic status/closure behavior in
other D3S projects. A separate team is an alternative if those projects need the
existing behavior; creating one would require explicit registration and issue
placement changes. Closed-item archival is a separate rule and does not complete
issues.

The browser exposes disabled ancestors on the merge/review selectors and
parent/stale toggles. Clicking the merge selector did not open it or change its
value; reload and network-idle readback reproduced the disabled state. The page
also labels branch-rule creation as restricted to workspace owners/admins.
The connected Linear account reports `isAdmin=true`, and the browser profile
matches that account. The UI/connector discrepancy is unresolved; do not infer
that credentials or a different account are required, and do not bypass the
disabled controls. The available Linear tools expose no team-workflow setter.

GitHub reports `allow_auto_merge=false`, and no pull requests are listed.
Both branch-protection and repository-ruleset reads return **HTTP 403**, with the
provider stating that GitHub Pro or a public repository is required. The
repository remains private. Required review protection cannot be verified or
configured through those endpoints on the current plan. A billing or repository
visibility change is outside this remediation.

Evidence is preserved locally under `.state/d3s-99-review/`, including workflow
snapshots, disabled-control readback, provider responses and a checksum manifest.
Earlier integration/Loops observations in the coordinator's D3S-101 audit were
not revalidated here; they cannot support a fresh passing audit.

## Remaining acceptance actions

1. Restore editable D3S workflow controls in the authenticated admin session,
   apply the target values above in the selected team scope, and capture saved
   settings after a reload. Recheck integration, branch and Loop completion paths.
2. Establish the required GitHub human review/merge process. The current plan
   does not provide the requested protection endpoints. No automated approval
   submitted using a human account may be represented as a human review.
3. Obtain the human's review of the actual bootstrap commit and record its
   provider approval/merge evidence. The bootstrap is already present on
   `origin/main`; its presence alone does not establish either fact. Do not create
   an empty or unrelated PR as substitute evidence.
4. Codex verifies the approved/merged result and required checks before D3S-99
   becomes Done. Only then register the reviewed context SHA, build its bundle,
   and finish runner isolation/1Password and executable-pilot setup for D3S-100.

Keep `merge_gate_audited=false`, the runner disabled and project automation
disabled until their corresponding evidence is complete.
