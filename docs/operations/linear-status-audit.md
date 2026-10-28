# Linear completion-automation audit

**Result: gate PASSES** for the D3S team rules (pilot gate 5), as of **2026-10-29**.
Scope: D3S team, Contract Master Automation project, `d3hl/contract-master`,
default branch `main`. `merge_gate_audited=true` in the registry. Automation, the
runner and live merging remain disabled; passing this gate does not activate them.

- **2026-10-25T06:42:34Z** — initial inspection through an authenticated Orca
  browser. No settings changed. Gate failed (values in the *Before* columns).
- **2026-10-29** — the workspace admin saved the remediation in the Linear UI and
  confirmed the saved values (*After* columns), including PR merged → No action.
  This readback is the admin's; Claude did not independently read the admin page.

## PR destinations

Source: [D3S Workflows & automations](https://linear.app/d3space/settings/teams/D3S/workflow).

| Event | Before (2026-10-25) | After (2026-10-29) |
|---|---|---|
| Draft PR opened | No action | No action |
| PR opened | In Progress | No action |
| PR review request or activity | In Review | No action |
| PR ready for merge | No action | No action |
| PR merged | **Done** | No action |
| Branch-specific overrides | None listed | None listed |

A merged PR no longer moves a linked issue. The only path to Done is the
manager's outbox after Claude's final completion check confirms the Codex merge
and merged acceptance. Open/review activity no longer writes status either.

## Other closing automations

Source: the same team workflow page.

| Rule | Before (2026-10-25) | After (2026-10-29) |
|---|---|---|
| Close parent when its last sub-issue closes | **Enabled** | Disabled |
| Close all sub-issues when parent closes | Disabled | Disabled |
| Close stale issues | **Enabled: 1 month → Canceled** | Disabled |
| Auto-archive closed items | 6 months | 6 months (archival only) |

These rules are team-wide: other D3S projects also no longer move to Done on merge,
close parents automatically or cancel stale work.

## Commit linking, issue sync and Loops

| Surface | Current observation | Source |
|---|---|---|
| GitHub commit linking | **Off** (`Link commits to issues` unchecked) | [GitHub settings](https://linear.app/d3space/settings/integrations/github) |
| GitHub issue sync | **No repositories linked** | Same GitHub settings page |
| GitHub automatic link/create on merge | Business-plan gate displayed; no active toggle | Same GitHub settings page |
| GitLab integration | **Not enabled**; page offers Enable / Connect GitLab integration | [GitLab settings](https://linear.app/d3space/settings/integrations/gitlab) |
| Loops | Current plan displays **Loops are available on paid plans**; no runnable Loop list is exposed | [Loops settings](https://linear.app/d3space/settings/loops) |

No configured issue-sync completion rule was found. Loops are unavailable under
the current plan; this is a plan-gate observation, not a claim that the API returned
an empty list of saved workflows. Re-audit if the plan/integrations change.

## Remediation status

1. PR merge → Done: **resolved** (team mapping set to No action).
2. Automatic parent closure: **resolved** (disabled).
3. Stale cancellation: **resolved** (disabled).
4. PR associations: still required in practice. Use status-neutral
   `Related to D3S-123` in PR text and keep issue IDs out of branch names. Commit
   linking stays off.
5. Re-read after remediation: done by the workspace admin on 2026-10-29.

Still open, outside this Linear gate: GitHub app access for `d3hl/contract-master`
(several apps with contents write on all repositories) belongs to pilot gate 6.
Re-audit after any Linear plan, team or integration change.

Linking and branch semantics are described in
[Linear's GitHub guide](https://linear.app/docs/github#workflow-automation).
[Loops documentation](https://linear.app/docs/loops) describes its plan requirement.
The *Before* values come from the authenticated workspace UI; the *After* values
come from the admin's saved-settings readback.

## Evidence and access correction

Local captures from the 2026-10-25 inspection under `.state/linear-audit/` include workflow/Loops/GitHub/GitLab
snapshots, before/after readbacks, original screenshots, `findings.json` and a
SHA-256 evidence manifest. `workflow.png` shows the five PR destinations;
`workflow-lower.png` captures branch/closure settings. Artifacts remain local;
no credentials were read, created or copied.

The earlier access limitation is superseded: Orca's status diagnostic still
reported `browser_unavailable`, but a direct `tab create` and authenticated
`snapshot` succeeded. Desktop computer-use failed and the issue connector still
does not expose admin rules. Actual page access supplied the evidence; the runtime
status flag was not treated as authoritative proof of browser unavailability.

Other API clients, manual users and external agents are outside this settings-only
audit. GitHub auto-merge was observed disabled separately.
