# Workflow and ownership

## Boundaries

| Owner | Responsibility |
|---|---|
| Linear | Requirements, priority, dependencies, acceptance criteria, bounded plans, progress, HANDOFF |
| contract-master | Shared instructions/contracts, registry, pinned context, durable queue, exclusive workspace ownership, recovery, serialized Linear writes |
| Orca | Sole scheduler and coordinator: triage, agent assignment, sequencing, monitoring, escalation |
| Codex | Code investigation, planning, independent verification, completion decision |
| DeepSeek | Scoped implementation, tests, requested corrections |
| Human | Review and merge |
| Target repository | Product implementation, tests, architecture, product docs and API contracts |

The manager records eligibility and state; it has no timer, background poller,
agent event loop or independent dispatch process. An Orca automation invokes the
coordinator. Only explicitly registered project/repository pairs participate.
Feature parents remain tracking items; children have independent identities and
Linear dependency relations. Never bulk migrate historical issues.

## Intake

Use existing Orca Linear reads. A notification is a hint to fetch the **current
full issue**, including HANDOFF/comments, children and relations. Never execute an
event payload directly. The same full project reconciliation runs on Orca's
schedule; it includes waiting and closed issues so dependency changes and missed
notifications are observed. No watermark may skip waiting dependencies. Foreign
project dependencies may be read for readiness, but cannot launch tasks.

Triage requires explicit goal, scope, acceptance, registered check IDs, repository
and full base commit. [Issue template](../templates/issue.md) contains a machine
block. Unstructured/incomplete issues receive a missing-information comment and
remain unqueued; Orca/Codex should propose clarifications, never invent them.
Existing project labels/states are preserved; eligibility does not require adding
an approval label. Tracking parents, closed issues and unmet dependencies stay
unqueued. Unknown dependency shapes and partial provider reads fail closed.

Task revision hashes repository, base, goal, scope, acceptance and check IDs.
Comments, labels, worker updates and manager status updates cannot create a new
revision. Dependency/status changes reconsider readiness with the same identity.
A material revision fences the old task; settle its Orca worker before superseding
and planning the new revision. One active revision per issue is enforced in SQLite.

## Phase gates

1. **planning:** Codex reads the issue, latest HANDOFF (or records verified absence),
   local AGENTS.md and entry points, pinned guidance and relevant code. Record a
   bounded plan and investigation evidence in Linear. No extra plan approval.
2. **ready → implementing:** validate runner identity and capabilities, immutable
   context, scope, dependencies and workspace ownership. Persist request identity
   before an Orca mutation. DeepSeek receives the complete plan, attempt number,
   scope, acceptance, check IDs, bundle reference and prior corrections.
3. **verifying:** collect DeepSeek's result, then Codex independently reads the
   actual diff and runs registry checks at the exact output commit. Implementation
   check completion moves Linear to In Review; failed checks remain in verification
   until Codex records actionable rework. In Review does not mean accepted.
4. **rework:** send concrete file/behavior/test corrections to DeepSeek. Two total
   implementation attempts, including the initial attempt. A second unresolved
   verification escalates to the human. Never reset the counter by creating a new
   task for the same revision.
5. **awaiting_review:** Codex acceptance passed; human reviews and merges. Any new
   head invalidates the verdict and provider merge receipt. Observe actual head
   before using verification. Material scope changes return to planning.
6. **done:** read provider merge facts, confirm human approval at the accepted head
   and human merge, inspect correspondence (including squash/rebase), rerun required
   checks against the merged commit, and record final Codex acceptance. Only then
   enqueue Done. A GitHub merge notification alone is insufficient.

Orca task settlement and product acceptance are separate. `worker_done` settles an
Orca attempt; it does not mark Linear Done. The coordinator checks both identities,
then reuses/releases the settled worker according to Orca's documented lifecycle.

## Trust

The manager API is **coordinator-only**. Workers return JSON and artifacts; they do
not receive manager ownership tokens, database write access, Linear credentials or
permission to call trusted completion APIs. `author: codex` is a data assertion,
not authentication. The trusted coordinator supplies role provenance. File scope
validation is a gate, not an OS sandbox; live runners must constrain writable
workspace and mount the shared bundle read-only. Registry changes require review.
