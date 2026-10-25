# One-repository pilot

## Prepared scope

- Project: Contract Master Automation (`aefa51f9-333f-4c60-96b8-e0f4fc534b7d`).
- Repository: `d3hl/contract-master`; only `docs/knowledge` may change.
- Task: add one short reusable note with a primary source and reproducible check.
- Check: registered `unit` suite. No deployment, credential changes or product code.
- Linear parent D3S-98; implementation D3S-99; pilot D3S-100 is blocked by D3S-99.
- Work budget: one issue, one active writer, initial implementation plus one rework.
- Human reviews and merges; Codex checks merged result before Done.

The pilot is **not running**. Config files are proposals; no automation/worker has
been launched. The API credential provided in chat was not used or stored. The
bootstrap was implemented directly by Codex; simulations are not a DeepSeek run.

## Activation gates

1. Human reviews/merges the bootstrap. Record the reviewed master SHA, create a
   context bundle with `bundle SHA`, verify its digest and required documents.
2. Verify the configured target base exists. The initial checkout has no commits
   and `origin/main` does not yet exist; no executable issue may use a placeholder SHA.
3. Choose a portable DeepSeek coding client and prove file reading/editing, command
   execution, Git and structured output on the intended host. Capture real model and
   client version, capability evidence, runner isolation and `op://` references.
   Do not merely switch the simulated runner to live.
4. Recheck Linear context completeness and project pagination after any Orca upgrade.
   Blocking relation direction was verified live on the newly created D3S-99/100 pair
   and is covered by an adapter test.
5. Audit Linear's GitHub/GitLab workflow automations. Disable any merge/PR rule that
   can mark participating issues Done before final Codex confirmation. Use link-only
   issue associations rather than closing references. Record a settings screenshot
   or admin receipt and date; set `merge_gate_audited` only after verification.
6. Audit required human review and human merge in the target host. Bots must not merge.
   The adapter requires an approval on the exact head, including after new commits.
7. Enable only the prepared pilot registry/runner and create **one** Orca scheduled
   automation with the documented `automations create` command. Use the coordinator
   prompt, existing manager workspace and Asia/Singapore timezone. Configure 1Password
   externally; never put secret values into the automation prompt/arguments.
8. Create one executable issue using the issue template and real base SHA. Observe
   all ten scenarios with simulated fault injection before widening registration.

## External configuration limits

Installed Orca exposes scheduled automations and Linear issue APIs. The available
Linear connector does not expose a verified setter for GitHub issue-status workflow
automations, and no live DeepSeek coding integration is established. Consequently
those settings are **not configured** by bootstrap. Automatic execution remains
blocked by default (`automation_enabled=false`, runner disabled,
`merge_gate_audited=false`, empty reviewed commit allowlist). These are activation
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
