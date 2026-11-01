# Register a target repository

1. Confirm owner, repo identity, default base and explicitly allowed Linear project
   UUIDs. New projects are opt-in. Resolve stable IDs using Orca discovery.
2. Keep a concise target AGENTS.md linking target architecture, API contracts,
   setup and test commands. Add a shared-context loader instruction; cross-repo
   links alone do not load files. Copy [target directory template](../templates/target-AGENTS.md).
3. Add the registry entry: remote identity, Orca repo ID, base ref, local entry
   points, required shared files, narrow allowed paths, check IDs with argv/timeouts,
   installed dependency versions, planning/implementation/verification runners,
   Linear mapping and 1Password references. Never add a machine-specific checkout
   path; the host supplies workspace placement.
4. Review the master commit and build/pin its bundle. Verify required local docs at
   the task base. Existing sessions keep their previous bundle.
5. Prove the runner's editing, command, Git and structured-result capabilities in a
   disposable fixture. Capture client version, model identity, execution host,
   isolation/mount settings, test evidence and account reference. A simulated
   capability declaration is insufficient for `mode: live`.
6. Audit integration automation settings and the Codex merge identity. Record evidence
   before setting `merge_gate_audited`. Do not change team-wide settings casually;
   choose a dedicated team if existing projects require conflicting automations.
   Install both GitHub Apps on the repository. After its first successful
   `codex-merge`, apply phase B protection on the default branch: require
   `codex-verification` from App 5511451, allow only `d3hl-codex` to push, no bypass
   (see [pilot gate 6](../operations/pilot.md)).
7. Run the scenario suite and [bounded pilot](../operations/pilot.md). Enable only
   after its activation gates are met. Adding future repositories is a reviewed
   registry change, not an issue instruction.

A repository may opt in to bounded person-opened PR review with a
`governance_review` registry block: `enabled`, `authors` (login/type),
`allowed_paths`, `registry_fields` and check IDs. The block only authorizes the
path; it never dispatches tasks or writes Linear. Only the registered
`registry_fields` of an existing repository may change through this path. Every
other registry change — top-level keys, adding or removing a repository,
`merge_identity`, `github_apps`, `credential_references`, `merge_gate_audited`,
`governance_review` itself, `linear_projects`, `url` and `base_ref` — stays
human-merged.

## Repository labels

A registry entry may set `linear_label` (a Linear label starting with `repo:`) to
route issues by label. The label confirms, never chooses, the repository: the
issue's `contract-master` block still names `repo_id`. Intake refuses, with a
TRIAGE clarification and no dispatch, when an issue:

- carries more than one `repo:` label;
- carries a `repo:` label that no repository registers;
- carries a label registered to a different repository than its block names;
- lacks the label its block's repository registers.

Apply exactly one repository label to each executable issue for a labeled
repository. Other labels are ignored. Each label belongs to one repository
(`doctor` reports duplicates). Repositories without `linear_label`, such as
`d3hl/contract-master`, accept issues without a `repo:` label.

Registered repositories (D3S-109, 2026-10-30; corp-integrated-dashboard 2026-11-01):

| Repository | Linear project | Label | Allowed scope (docs only) | Checks |
|---|---|---|---|---|
| `d3hl/contract-master` | Contract Master Automation | none | `docs/knowledge` | `unit` |
| `d3-corp/cf-mcp-gw` | Cloudflare MCP Gateway | `repo:cf-mcp-gw` | root plan/runbook `*.md`, `docs`, `pilot.example.json` | `typecheck`, `docs`, `secrets`, `tests` |
| `d3-corp/action1-dashboard` | Action1 Dashboard | `repo:action1-dashboard` | `README.md`, `VALIDATION.md`, `CLOUDFLARE.md`, `features.md`, `dashboard/README.md`, `docs` | `test` |
| `d3-corp/corp-integrated-dashboard` | Corp Integrated Dashboard | `repo:corp-integrated-dashboard` | `README.md`, `docs` | `typecheck`, `build` |

Use `repo:cf-mcp-gw` for Cloudflare setup and workflow tasks,
`repo:action1-dashboard` for Action1 tasks, including the Action1 dashboard, and
`repo:corp-integrated-dashboard` for the Vite/React corp integrated dashboard.
Target `AGENTS.md` stays out of scope so a worker cannot edit its own instructions.
All three `d3-corp` repositories are public (GitHub Free allows branch protection
only on public repositories). cf-mcp-gw and action1-dashboard are on phase B
protection since 2026-10-30, after their first `codex-merge` (cf-mcp-gw PR #7,
action1-dashboard PR #2): `main` requires `codex-verification` from App 5511451,
only `d3hl-codex` may push, and admins cannot bypass. Owner PRs there can no longer
merge outside a Contract Master task. corp-integrated-dashboard (registered
2026-11-01) is on phase A until its first `codex-merge`. Its tracked sample data
must stay fictional: the repository was briefly public with a real tenant snapshot,
which was removed by rewriting history. Checks on all three run
`npm ci --ignore-scripts` first and need Node.js 24 and registry.npmjs.org, no
credentials. Widening scope beyond docs is a
reviewed registry change.

The bootstrap registration is the manager itself for a narrow docs-only pilot.
Ordinary product tasks should target other registered repositories. The current
bootstrap implementation issue has wider scope than the pilot and is managed
manually; do not rewrite it into an automatically eligible task.
