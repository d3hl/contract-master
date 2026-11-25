# Orca coordination and recovery

Verified against installed Orca **1.4.235**, using its own version-matched guides
and command help on 2026-10-25, and rechecked on installed **1.4.240** (2026-10-25)
and **1.4.243** (2026-10-29: Linear listing, pagination and full reads; pilot gate 4);
**1.4.274** (2026-11-26) changed the remote worker start route to `--on` (see
[below](#deepseek-workers-on-the-paired-rh1-d3-server)).
Re-read the installed guide after upgrades. Resolve the executable once:
`ORCA_CLI_COMMAND`, otherwise `orca-dev` in an advertised dev session, otherwise
`orca-ide` on Linux. Never use Linux's bare GNOME `orca`. The Python adapter
follows this resolution and never switches builds on failure.

## Intake and scheduling

No Orca automation existed at bootstrap. `config/orca-automation.json` records the
one Orca-owned schedule. It was installed at pilot gate 7 as automation
`dc0657b8-923e-4d65-a57f-0a1d8b8ab4a9` on NTNSG-RH1 (every ten minutes) and moved
on 2026-11-03 to `c0e63d16-c147-40b2-bb1b-5698891f2ff0` on ntnsg-rh3 (hourly,
fresh session per run). The CLI exposed scheduled triggers,
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

### Scheduled coordinator runs

The automation's precheck (recorded in `config/orca-automation.json`) skips a tick
unless the checkout is a clean `main`, `doctor` has no blockers, and **no other run
of the automation is still `dispatched`**. Orca does not serialize runs: on
2026-10-29 it started run 106 while run 105 was mid-task, and both coordinators
held the same owner token. A run is marked `dispatched` only after its precheck, so
the check does not see itself; an unreadable run list also skips the tick.

Run status alone is not enough: Orca marks a **manually started** run `completed`
while its session is still working, so on 2026-10-30 scheduled runs 133 and 134
started alongside manual run 132 (both stood down by hand). Every coordinator turn
therefore holds the manager's **turn lease** (`turn-start`, `turn-renew`,
`turn-end`; table `turn_lease` in the manager database), and the precheck ends with
`python3 -m contract_master turn-check`, which exits non-zero while a lease is live.
A second turn's `turn-start` is refused. A lease left by a crashed turn expires after
60 minutes unless renewed; a turn that finds its lease lost stops without writes.

Scheduled runs inherit no 1Password session. `open-pr` and `codex-merge` read the
service account token from the owner-only file `~/.config/op/contract-master-sa-token`
(override with `CONTRACT_MASTER_OP_TOKEN_FILE`) and pass it only to `op`; a file
readable by group or others is refused. It never goes into the prompt or argv.
Each finished run leaves its Claude terminal open; close old ones when convenient.

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
   Preserve the editing workspace. Codex (`codex exec ... < /dev/null`; it hangs
   if stdin stays open) reviews actual diff, runs checks and
   submits structured verification. Send failed criteria as actionable corrections.
8. Rework follows the manager's two-attempt cap. For an Orca *failed/stopped* Task,
   use documented `--task` and `--retry-of`; a successful implementation Dispatch
   followed by semantic verification failure needs a separate dependent rework Task
   under the same manager task/attempt counter. Never misuse `--retry-of` on a
   succeeded Dispatch. Record both Task IDs. Codex review/merge and final Claude
   confirmation follow.

### DeepSeek workers on the paired `rh1-d3` server

The configured runner sets `"environment": "rh1-d3"`: its workers run on a
separate Orca server owned by Linux user `d3` on NTNSG-RH1 ([worker host](worker-host.md)).
The server runs in a systemd sandbox that hides the rest of that account. The
coordinator on ntnsg-rh3 reaches it through an SSH tunnel, copies pinned context in
with `scp` and fetches output commits as git bundles over SSH (exact commands in the
worker host doc).

**Route (Orca 1.4.274 and later): place the worker with `--on rh1-d3`.** The Run, Task
and mailbox stay on the coordinator's own Orca; only the worker lives on the server, and
it is addressed by Dispatch id, never by a terminal handle. Installed 1.4.274 refuses
`worker-start --environment rh1-d3` before launch with `agent_server_route_refused`
(first seen on D3S-136, 2026-11-26) and suggests `--on`. Orca 1.4.243 had the opposite
rule (`--on` refused with `server_required`), so re-read the installed placement guide
after every upgrade (`skills get orchestration --reference references/placement-and-remote.md`).
`--worktree current` is not valid with `--on`.

1. Read the server's own project row: `project setups --environment rh1-d3 --json`.
   Take `repoId` from the row whose `projectId` matches the target and that is `ready`,
   `kind` git, `hostId` `local`. Never reuse this machine's id (the registry's
   `orca_repo_id`).
2. Create the Run and Task on this Orca: `orchestration run-create --objective ...`,
   then `task-create --run <run> --spec ... --retry-request ...`. No `--environment`,
   no `--from`, no server mailbox terminal.
3. `worker_command(..., server_repo_id=<repoId>)` returns `worker-start --task ... --run ...
   --on rh1-d3 --worktree new-top-level --repo id:<repoId> --name <task> --setup skip
   --agent opencode2 --retry-request ... --json`. Then read the worker with
   `orchestration worker-read --dispatch <id>`. On 2026-10-30 (D3S-115) OpenCode showed the
   prompt pasted but unsubmitted: send exactly one Enter and confirm it started, never
   paste the prompt again. How to reach the worker terminal on this route is unverified;
   check it on the first probe.
4. `orchestration check --wait` on the coordinator's own terminal, ack, then
   `worker-release --dispatch <id>`. All local; none take `--environment rh1-d3`.

Until the first probe Dispatch on 1.4.274 passes (upgrade plan Step 5.2), this route is
documented by Orca's own guide and error text, not proven end to end here.

A start refused with `agent_server_route_refused` launched nothing. Evidence for D3S-136:
the manager receipt `refused/agent_server_route_refused`, `request-show` returning
`absent` on both Orcas, empty `worker-list` on both and no worktree on the server. The
Run and mailbox terminal created on `rh1-d3` for that attempt are unused leftovers. Retry
the **same** attempt on the new route (never a fresh task) only with the owner's approval
and only while those facts still hold.

Orca messages from that server are unverified claims: the worker can write its
server's state. The manager database stays authoritative and Codex verifies the
exact output commit in its own checkout. Linear reads and the manager stay on the
coordinator side.

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
