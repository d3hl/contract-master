# One-repository pilot

## Prepared scope

- Project: Contract Master Automation (`aefa51f9-333f-4c60-96b8-e0f4fc534b7d`).
- Repository: `d3hl/contract-master`; only `docs/knowledge` may change.
- Task: add one short reusable note with a primary source and reproducible check.
- Check: registered `unit` suite. No deployment, credential changes or product code.
- Linear parent D3S-98; implementation D3S-99; pilot D3S-100 is blocked by D3S-99.
- Work budget: one issue, one active writer, initial implementation plus one rework.
- Codex reviews and merges; Claude checks merged result before Done; humans handle escalations.

Coordination was **enabled** at gate 7: one Orca scheduled automation runs the
coordinator turn (currently disabled; see [HANDOFF](HANDOFF.md)). Gate 8 **passed**
on 2026-10-30 (D3S-114 and D3S-115 Done). A separate
user-authorized [DeepSeek/OpenCode capability probe](runner-verification.md) passed
with its worker released. That probe used existing client authentication and did
not store/provision credentials. It does not assert production eligibility.

## Activation gates

1. Human reviews/merges the bootstrap. Record the reviewed master SHA, create a
   context bundle with `bundle SHA`, verify its digest and required documents.
   **Done 2026-10-29:** pinned `26e14a8c21f1046abdecdc9bde1bd68b5a3e7259` (PR #21,
   reviewed and merged by the owner). Bundle digest
   `9ac1eae1c4e0b8fa89ac5788ecf554812ab9db11aada0524f2cb295b49c5b7eb`: recomputed
   digest, source commit and the five required documents match `git show` at that
   commit; file mode 0444. The bundle lives under the ignored `.state/context/`;
   rebuild it on another host with `bundle <SHA>` and compare the digest.
2. Verify the configured target base and approved context. The bootstrap now exists
   at commit `32e4e4630b237cb1a9c442355940bba1eb6a2dae` on `main`/`origin/main`;
   its presence does not establish human review approval. No executable issue may
   use a placeholder SHA.
3. The OpenCode 2.1.4 capability probe passed. Before production, apply the verified
   target-workspace model configuration, verify actual session model identity,
   configure runner isolation and approved `op://` references.
   **Done 2026-10-29:** workers run as Linux user `cm-worker` on a localhost-only
   Orca server ([worker host](worker-host.md)). An isolated probe (Dispatch
   `ctx_ac7cba883d03`) confirmed from session metadata OpenRouter
   `deepseek/deepseek-v4.1-flash-1017`, found every coordinator credential path
   blocked, and committed `7acb8fb` (checked independently). The worker's only
   credential is its own OpenRouter login; it needs no `op://` reference. The
   runner is `enabled: true`; live dispatch still requires `automation_enabled`.
4. Recheck Linear context completeness and project pagination after any Orca upgrade.
   Blocking relation direction was verified live on the newly created D3S-99/100 pair
   and is covered by an adapter test.
   **Rechecked 2026-10-29 on Orca 1.4.243** (read-only, through the adapter's own
   code): the project listing returned the same 6 issues with the default limit,
   unbounded, and paged one at a time (6 pages, issued cursor advanced each time,
   `partial: false`). Full reads of all 6 passed the completeness checks (comments,
   children and relations uncapped). Completed issues that Linear auto-archives
   (for example D3S-100) appear only with `--include-archived`; this is safe because
   intake only queues open issues and reads dependencies by ID (full read of D3S-100
   passes). The D3S-99/100 relation no longer exists (Linear confirms), and none of
   the 60 most recent D3S issues has a blocking relation, so relation direction was
   not re-observed live. Unknown relation shapes fail closed; re-observe direction on
   the gate 8 issue if it has a dependency.
5. Audit Linear's GitHub/GitLab workflow automations. Disable any merge/PR rule that
   can mark participating issues Done before final Claude confirmation. Use status-neutral `Related to D3S-123`
   associations, and audit branch/title auto-linking as well as closing keywords. Record a settings screenshot
   or admin receipt and date; set `merge_gate_audited` only after verification.
6. Create a dedicated Codex GitHub identity (GitHub App or machine user) with merge
   rights on the target only; keep its credential in 1Password. Require its approval
   in branch protection, record it as `merge_identity` (`login`, `type`) in the
   registry, and confirm no other bot can merge. The adapter requires Codex approval
   on the exact head, including after new commits, and refuses if a human's latest
   review requests changes. Done: `d3hl-codex` (App 5511451, installation 176202750)
   is recorded in `merge_identity` and `github_apps.merge`.
   `d3hl-orca` (App 5516831, installation 176325322) is recorded in `github_apps.pr`.
   **Live test passed 2026-10-29** in the throwaway repo `d3hl/sandbox`
   ([PR #1](https://github.com/d3hl/sandbox/pull/1)): opened by `d3hl-orca[bot]` with
   `Related to SANDBOX-1`; `codex-verification` success from App 5511451 on
   `60941a7`; `d3hl-codex[bot]` APPROVED `60941a7`; merged by `d3hl-codex[bot]` (Bot),
   merge commit `eb980c3`; read-only gate confirmed. A second run of both commands
   made no new PR, review or check. Manager state was a temporary database; no
   Linear writes.
   Both App keys now live in the dedicated 1Password vault `contract-master`; the
   service account can read only that vault (verified 2026-10-29: one vault, two
   items). A second live run with those references passed the same day
   ([PR #2](https://github.com/d3hl/sandbox/pull/2): opened by `d3hl-orca[bot]`,
   `codex-verification` success and APPROVED on `4352260`, merged by
   `d3hl-codex[bot]` as `2cc428e`); its rerun made no new writes.
   Branch protection: `contract-master` **stays on phase A** (PR required, `unit`
   checks from GitHub Actions, push limited to `d3hl-codex` and the owner, admin
   bypass allowed). Its own PRs are opened by people or Claude, not by the manager,
   so `codex-merge` never runs on them and a required `codex-verification` would
   block every merge. Phase B (require `codex-verification` from App 5511451, push
   only `d3hl-codex`, no bypass) applies to target repositories when they are
   onboarded, after their first `codex-merge`. Applied on 2026-10-30 to
   `d3-corp/cf-mcp-gw` and `d3-corp/action1-dashboard` (D3S-109). Revisit if
   contract-master gets a command for Codex to review and merge non-task PRs.
7. Enable only the prepared pilot registry/runner and create **one** Orca scheduled
   automation with the documented `automations create` command. Use the coordinator
   prompt, existing manager workspace and Asia/Singapore timezone. Configure 1Password
   externally; never put secret values into the automation prompt/arguments.
   **Done 2026-10-29:** pinned reviewed master `b590eb4` (bundle digest
   `84ca586bee80287de4953ea320ba084c9f3b276002ad457ea39661248380fad8`; the five
   required documents match `git show`; mode 0444) and set `automation_enabled`.
   Exactly one scheduler exists for this workspace: the earlier delivery-only
   automation `dc0657b8-…` was converted rather than adding a second. It had been
   failing every run since its agent was changed to `openclaude` (not installed);
   it now uses `claude`, `*/10 * * * *`, Asia/Singapore, the existing manager
   workspace, fresh sessions, and a prompt that only points to
   `docs/operations/coordinator-prompt.md`. Its precheck skips a run unless the
   checkout is a clean `main` and `doctor` reports no blockers. The separate
   "Daily change review" automation (Codex, read-only report) is not a manager
   scheduler. Intake now comments only on open issues; settled issues without an
   automation block are skipped without a comment.
8. Create one executable issue using the issue template and real base SHA. Observe
   all ten scenarios with simulated fault injection before widening registration.
   **Passed 2026-10-30.** [D3S-114](https://linear.app/d3space/issue/D3S-114) (base
   `35c7ff5`) is **Done** (2026-10-29): planned and Codex-verified in run 105
   (DeepSeek output `cd7486f`); after the 1Password token-file fix, run 107 opened
   PR #29 as `d3hl-orca[bot]`, `d3hl-codex[bot]` approved and merged it as `a6bccb7`,
   and Claude confirmed completion. This observed scenarios 01 (full lifecycle) and
   05 (restart recovery, run 107 resuming run 105's task) live. Overlapping runs
   were found and blocked by the precheck run lock.
   [D3S-115](https://linear.app/d3space/issue/D3S-115) records all ten scenarios at
   one commit and is **Done** (2026-10-30). Its first scheduled runs (109–131) ran on
   Codex instead of Claude and could not reach the Orca runtime. A human closed it by
   hand and then reopened it. Manual run 132 then queued it (base `a6bccb7`), planned
   it, and ran DeepSeek on `cm-worker` (Dispatch `ctx_1e04d27edf3a`, output
   `f5540e6`). Codex verified it (5/5 criteria). `d3hl-orca[bot]` opened PR #32 and
   `d3hl-codex[bot]` approved and merged it as `9b3e141`. Claude reran the checks on
   the merged commit (all ten scenarios and 86 unit tests pass) and confirmed Done.
   The result is [failure-scenarios.md](../knowledge/failure-scenarios.md): all ten
   scenarios fail safe under simulated fault injection; 01 and 05 were also observed
   live in D3S-114, the other eight are simulation only.
   Found during this gate (not yet fixed): intake queues a `TRIAGE: Issue is closed`
   comment for a closed issue that has a complete block; `worker-start` pasted the
   OpenCode prompt without submitting it (one Enter was needed); `codex exec` must
   run with stdin closed or it waits forever.

The [completion-automation audit](linear-status-audit.md) **passes** as of
2026-10-29: D3S PR events (including merge) map to No action, and parent
auto-close and stale cancellation are disabled. `merge_gate_audited=true`.

## External configuration limits

Installed Orca exposes scheduled automations and Linear issue APIs. The available
Linear connector does not expose a verified setter for GitHub issue-status workflow
automations. A live DeepSeek capability probe is now verified; production
configuration and the external status settings are recorded in the gates above.
`automation_enabled=true` since gate 7; live dispatch still needs every per-task
gate. These are activation prerequisites, not extra plan approval for otherwise
eligible work.

## Abort and recovery

Disable the single Orca automation to pause new intake
(`automations edit dc0657b8-923e-4d65-a57f-0a1d8b8ab4a9 --disabled`). Do not delete the manager
state, task workspace or context bundle. Preserve unknown worker authority and
inspect through Orca; never launch a replacement on timeout alone. Keep Linear
handoffs queued locally through outages. Resume with existing identity after the
host confirms state. Destructive cleanup or abandoning changes requires explicit
human direction.

## Simulation evidence

Run `python3 -m unittest discover -s tests -v`. The suite covers the ten required
scenarios plus malicious scope/check expansion, corrupt/unreviewed context,
workspace collisions, material revisions, stale snapshots, outbox concurrency,
ambiguous delivery and actual Git diff/check execution. Each fixture uses temporary
Git repositories and local SQLite state; it sends no live messages or model calls.
