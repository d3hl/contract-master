# Linear completion-automation audit

Inspected **2026-10-25T06:42:34.091173+00:00** through an authenticated Orca browser.
Scope: D3S team, Contract Master Automation project, `d3hl/contract-master`,
default branch `main`. **Inspection complete; activation gate FAILS.**
No settings were changed. `merge_gate_audited=false` and automation remain disabled.

## Current PR destinations

Source: [D3S Workflows & automations](https://linear.app/d3space/settings/teams/D3S/workflow). These are current UI
values, independently read back after inspection, not assumed product defaults.

| Event | Destination |
|---|---|
| Draft PR opened | No action |
| PR opened | In Progress |
| PR review request or activity | In Review |
| PR ready for merge | No action |
| PR merged | **Done** |
| Branch-specific overrides | **None listed**, including no override for `main` |

**Finding:** a closing-linked PR can move its issue to Done on merge before Codex
confirms the merged acceptance evidence. The team default applies because no
branch override is configured. Repository-specific GitHub app access was not
verified by this audit; this finding concerns linked PR behavior under these team
rules. Open/review transitions also write status outside the manager.

## Other closing automations

Source: the same team workflow page.

| Rule | Current value | Implication |
|---|---|---|
| Close parent when its last sub-issue closes | **Enabled** | A tracking parent can close outside an explicit Codex completion decision |
| Close all sub-issues when parent closes | Disabled | No automatic child-close path configured here |
| Close stale issues | **Enabled: 1 month → Canceled** | Waiting/unresolved work can be terminated outside the manager; this is cancellation, not a Done transition |
| Auto-archive closed items | 6 months | Archival only; not a completion trigger |

The parent rule counts closure, not independently verified acceptance. It should
be reviewed separately from the PR mapping. The stale rule can affect preserved
work even though its terminal destination is Canceled.

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

## Required remediation before activation

1. Prevent participating issues from using PR merge → Done. Use an approved
   No action mapping or an isolated automation team/policy that preserves the
   manager as completion writer. The current rules are team-scoped; assess effects
   on other D3S projects before changing them.
2. Remove automatic parent closure from manager-owned feature tracking, or record
   an explicitly accepted tracking-only exception. The current workflow requires
   Codex completion decisions, so this audit accepts no implicit exception.
3. Exclude manager-owned waiting work from stale cancellation, or disable that
   rule within the selected automation scope.
4. Use status-neutral `Related to D3S-123` PR associations, and review branch/title
   auto-linking. `Refs` still permits non-merge status transitions. Audit app access
   for the registered repository before claiming live integration readiness.
5. Re-read and capture the saved settings after remediation. Only then may the
   completion gate pass. This inspection does not authorize project activation,
   historical issue changes or a live merge.

Linking and branch semantics are described in
[Linear's GitHub guide](https://linear.app/docs/github#workflow-automation).
[Loops documentation](https://linear.app/docs/loops) describes its plan requirement.
The actual rule values above come from the authenticated workspace UI.

## Evidence and access correction

Local captures under `.state/linear-audit/` include workflow/Loops/GitHub/GitLab
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
audit. GitHub auto-merge was observed disabled separately; its state does not
prevent Linear's PR-merge status mapping from firing after a human merge.
