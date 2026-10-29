# Orca coordination and recovery

Verified against installed Orca **1.4.235**, using its own version-matched guides
and command help on 2026-10-25, and rechecked on installed **1.4.240** (2026-10-25)
and **1.4.243** (2026-10-29: Linear listing, pagination and full reads; pilot gate 4).
Re-read the installed guide after upgrades. Resolve the executable once:
`ORCA_CLI_COMMAND`, otherwise `orca-dev` in an advertised dev session, otherwise
`orca-ide` on Linux. Never use Linux's bare GNOME `orca`. The Python adapter
follows this resolution and never switches builds on failure.

## Intake and scheduling

No Orca automation existed at bootstrap. `config/orca-automation.json` is a disabled
proposal for one Orca-owned ten-minute schedule. The CLI exposed scheduled triggers,
not a verified Linear webhook registration capability. Full reconciliation is the
working intake path. A future existing webhook can wake the **same** coordinator;
it must fetch current issues and call the same manager, not create another scheduler.
No webhook server, cron daemon or autonomous harness poller is installed here.

`python3 -m contract_master reconcile` is a one-shot read/triage pass. It uses
`linear list-issues --project UUID --workspace UUID` and full issue reads, pages
listings, rejects partial/capped required context and revisits stored waiting
snapshots. It enqueues comments locally; `flush-one` is the separate serialized
writer. Both are suitable for a bounded Orca coordinator turn.

A failed or incomplete provider read (`ProviderError`) says nothing about the
issue. That issue is skipped with `retry: true` in the output: no triage comment,
no fencing of its active task. Other issues continue; a failed project listing
still aborts the pass. Coordinators should surface issues that keep returning
`retry`, since they never receive a triage comment.

Live reads of new issues D3S-99 and D3S-100 verified the provider relation shape:
`type: blocks`, `direction: inbound`, `relationship: blockedBy` blocks execution;
`direction: outbound`, `relationship: blocks` identifies a downstream issue.
The adapter normalizes these fields and tests them; ambiguous shapes fail closed. Scheduled intake
is eventual (up to its cadence); it does not claim instant push notification.

## Durable authority

The manager SQLite database is local to one coordinator host, with WAL, full
synchronous writes, transaction fencing, unique active issue/revision and exclusive
canonical workspace path. Concurrent coordinators must share this exact database;
different database copies are not a distributed lock. Do not place it on an
unsupported network filesystem. Back up database, bundles and preserved workspaces
together using SQLite's online-backup API or while the coordinator is quiescent.
Execution policy (scope, check argv, runner and documentation requirements) is
snapshotted and digested per task, so config edits cannot change retry commands.
Tokens and database access remain coordinator-only. No ownership expiry steals a
workspace. Interrupted work resumes its existing task, token, branch and bundle.

Persist Orca Run/Task/Dispatch/request receipts on the task. A prepared attempt has
a durable `dispatch_request_id` **before** launch. A crash before/after launch is
recovered with that identity and Orca's receipt lookup; never issue a fresh start.
The manager API generates no live worker process; only Orca owns placement and launch.

## Documented coordinator sequence (activation only)

These are command forms, not commands to run during bootstrap. Load
`skills get orchestration --json`, and its placement reference before creating
worktrees. Use exact IDs/flags from that execution host's receipts.

1. Discover `status --json` and recover the recorded Run with `orchestration run-use`.
   Use `run-create --objective ...` only when no corresponding Run exists. A Run
   is a namespace/inbox, not a scheduler.
2. Claim a separate target workspace in the manager. Use Orca's worktree placement
   capability, target repo/base and validated setup policy. Never share an editing
   workspace between concurrent tasks. Claude investigation/plan must finish before
   an implementation Dispatch is eligible.
3. Create an Orca Task with a self-contained spec via `orchestration task-create
   --spec ... --run ... --retry-request ...`. Record its receipt. The spec contains
   target, change, constraints, ownership and observable acceptance. It explicitly
   instructs loading the pinned task/plan/context and returning the versioned result.
4. `worker-start --task ORCA_TASK --run RUN --worktree EXACT --agent VERIFIED_CLIENT
   --retry-request REQUEST --json` starts the authoritative attempt. The DeepSeek
   adapter can use any verified coding client. Do not assume a model flag is
   supported for that client; honor the installed help and client configuration.
5. Persist returned Dispatch and request IDs with `orca-receipt`. Failed or unknown
   launch receipts include residual resources and exact recovery actions; preserve
   them. `worker_command` builds argv only after live runner validation; it never
   executes the command and never wraps shell commands from issue text.
6. Check the coordinator mailbox for worker_done/escalation/question. Verify the
   authoritative Dispatch and output, process every message, then ack the delivery.
   Workers obey the live preamble for heartbeat, follow-up checks and exactly one
   `worker_done --outcome succeeded|failed`. Worker settlement is not acceptance.
7. After a valid settlement, release/reuse the proven terminal per Orca docs.
   Transfer to a separate Codex verification checkout with the **exact output SHA**.
   Preserve the editing workspace. Codex reviews actual diff, runs checks and
   submits structured verification. Send failed criteria as actionable corrections.
8. Rework follows the manager's two-attempt cap. For an Orca *failed/stopped* Task,
   use documented `--task` and `--retry-of`; a successful implementation Dispatch
   followed by semantic verification failure needs a separate dependent rework Task
   under the same manager task/attempt counter. Never misuse `--retry-of` on a
   succeeded Dispatch. Record both Task IDs. Codex review/merge and final Claude
   confirmation follow.

### DeepSeek workers on the paired `cm-worker` server

The configured runner sets `"environment": "cm-worker"`: its workers run on a
separate Orca server owned by Linux user `cm-worker` ([worker host](worker-host.md)).
This coordinator's runtime is SSH-managed and refuses `worker-start --on`
(`server_required`), so every orchestration command for an implementation attempt
goes to that server with `--environment cm-worker`, and the Run, Task and mailbox
live there:

1. `terminal create --environment cm-worker --worktree <repo root id>`: one plain
   terminal used as the coordinator's mailbox handle on that server. Record it.
2. `orchestration run-create --environment cm-worker --from <mailbox> --objective ...`
   (or `run-use` for the recorded Run), then `task-create --environment cm-worker
   --from <mailbox> --run <run> --spec ... --retry-request ...`.
3. `worker_command(..., mailbox=<mailbox>)` returns `worker-start --task ... --run ...
   --worktree ... --agent opencode2 --retry-request ... --environment cm-worker
   --from <mailbox>`; for a fresh worktree use `--worktree new-top-level --repo
   id:<worker repo> --setup skip`.
4. `orchestration check --environment cm-worker --terminal <mailbox> --wait`, ack,
   then `worker-release --environment cm-worker --dispatch <id>` (no `--from`).

Orca messages from that server are unverified claims: `cm-worker` can write its
server's state. The manager database stays authoritative and Codex verifies the
exact output commit in its own checkout. Linear reads and the manager stay on the
coordinator side; never pass `--environment` to `linear` or manager commands.

Use the installed `coordinator-loop.md` and `placement-and-remote.md` references for
phase transitions/placement. No generic subagent substitution provides Orca provenance.

## Interruption and unknown outcomes

A timeout, idle UI, missing heartbeat or unreachable remote is **unverifiable**,
not exited. Inspect `worker-list --run RUN --include-remote --json`, page it, and
follow its literal nextAction. Only positive exit/failed/stopped evidence permits
stop/abandon/retry; only accepted settlement permits release. Never silently steal
ownership or close unrelated terminals. Restore the same request with
`orchestration request-show` and documented `--retry-request` recovery.

## Linear updates and outages

Only `Outbox` calls the Linear workflow transport. Queue items have deterministic
keys; comments carry stable hidden markers. Writes are ordered globally by sequence.
`flush-one` commits `sending` before I/O. Concurrent flushers can observe delivery
but cannot send that entry again. Confirmed pre-send outages restore pending.
Accepted writes with lost acknowledgments reconcile by comment marker/current
state. No readback proof leaves the item uncertain and blocks later workflow writes.

Orca `linear_write_unconfirmed` receipts are preserved as typed error text. Follow
the returned exact writeId/nextSteps for a bounded replay, or inspect complete
readback first. Never blind-resend a comment or generate a new key. If no positive
delivery proof is possible, keep uncertain and escalate; an operator must resolve
that specific row based on the provider receipt, not reset the whole queue.

HANDOFF is stored in SQLite before export and enqueue. `export-handoffs` recreates
`.state/handoffs/*.json` after an interrupted export. The outbox survives process
restart, preserves order and reconciles delivery without duplicate updates.

Installed Orca 1.4.235 rejected raw issue UUIDs with `linear issue` (even with
`--id`). That limitation is fixed in installed **1.4.240**, whose help accepts a
Linear key, raw issue ID or URL for both the positional argument and `--id`. Use
provider identifiers such as D3S-99 in human-facing text, and preserve UUIDs for
durable task/dependency identity. Intake uses listing and relation identifiers,
and outbox entries carry provider identifiers.
