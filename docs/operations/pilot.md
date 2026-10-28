# One-repository pilot

## Prepared scope

- Project: Contract Master Automation (`aefa51f9-333f-4c60-96b8-e0f4fc534b7d`).
- Repository: `d3hl/contract-master`; only `docs/knowledge` may change.
- Task: add one short reusable note with a primary source and reproducible check.
- Check: registered `unit` suite. No deployment, credential changes or product code.
- Linear parent D3S-98; implementation D3S-99; pilot D3S-100 is blocked by D3S-99.
- Work budget: one issue, one active writer, initial implementation plus one rework.
- Codex reviews and merges; Claude checks merged result before Done; humans handle escalations.

The pilot is **not running**. No scheduled automation is installed. A separate
user-authorized [DeepSeek/OpenCode capability probe](runner-verification.md) passed
with its worker released. That probe used existing client authentication and did
not store/provision credentials. It does not assert production eligibility.

## Activation gates

1. Human reviews/merges the bootstrap. Record the reviewed master SHA, create a
   context bundle with `bundle SHA`, verify its digest and required documents.
2. Verify the configured target base and approved context. The bootstrap now exists
   at commit `32e4e4630b237cb1a9c442355940bba1eb6a2dae` on `main`/`origin/main`;
   its presence does not establish human review approval. No executable issue may
   use a placeholder SHA.
3. The OpenCode 2.1.4 capability probe passed. Before production, apply the verified
   target-workspace model configuration, verify actual session model identity,
   configure runner isolation and approved `op://` references. Keep the runner
   disabled until the other gates pass.
4. Recheck Linear context completeness and project pagination after any Orca upgrade.
   Blocking relation direction was verified live on the newly created D3S-99/100 pair
   and is covered by an adapter test.
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
   Remaining:
   - Require `codex-verification` from App 5511451 on `main`, allow only
     `d3hl-codex` to push and block bypass (phase B branch protection).
7. Enable only the prepared pilot registry/runner and create **one** Orca scheduled
   automation with the documented `automations create` command. Use the coordinator
   prompt, existing manager workspace and Asia/Singapore timezone. Configure 1Password
   externally; never put secret values into the automation prompt/arguments.
8. Create one executable issue using the issue template and real base SHA. Observe
   all ten scenarios with simulated fault injection before widening registration.

The [completion-automation audit](linear-status-audit.md) **passes** as of
2026-10-29: D3S PR events (including merge) map to No action, and parent
auto-close and stale cancellation are disabled. `merge_gate_audited=true`.

## External configuration limits

Installed Orca exposes scheduled automations and Linear issue APIs. The available
Linear connector does not expose a verified setter for GitHub issue-status workflow
automations. A live DeepSeek capability probe is now verified; production
configuration and the external status settings remain separate gates. Automatic execution remains
blocked by default (`automation_enabled=false`, runner disabled, empty reviewed
commit allowlist). These are activation
prerequisites, not extra plan approval for otherwise eligible work.

## Abort and recovery

Disable the single Orca automation to pause new intake. Do not delete the manager
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
