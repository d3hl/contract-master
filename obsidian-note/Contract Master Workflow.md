---
title: Contract Master Workflow
repo: d3hl/contract-master
updated: 2026-11-02
tags: [contract-master, workflow, orca, automation]
aliases: [Contract Master, CM workflow]
---

# Contract Master Workflow

> [!summary]
> Linear issue → Orca triage → Claude plans → DeepSeek implements → Codex verifies, opens PR and merges → Claude confirms → Linear Done.

## Purpose and scope

Contract Master turns Linear issues into reviewed, merged pull requests in registered repositories, with each step owned by one agent. It holds the shared automation contracts, the repository registry, pinned context, a durable SQLite task queue, workspace ownership, recovery state and serialized Linear writes.

Product code, tests, architecture and product API contracts stay in each target repository. Only explicitly registered project/repository pairs take part, and historical issues are never bulk migrated.

## Roles and ownership

Each actor has one job; no agent both implements and approves its own work.

| Actor | Owns |
| --- | --- |
| Linear | Requirements, priority, dependencies, acceptance criteria, plans, progress, HANDOFF |
| Contract Master (manager) | Contracts, registry, pinned context, durable queue, workspace ownership, recovery; the only Linear workflow writer |
| Orca | Only scheduler and coordinator: triage, assignment, sequencing, monitoring, escalation (the coordinator turn runs on Claude) |
| Claude | Investigation, design, planning, final completion decision |
| DeepSeek | Scoped implementation, tests, requested corrections |
| Codex | Independent verification, PR review and merge |
| Humans | Escalations only; may veto a PR by requesting changes |
| Target repository | Product code, tests, architecture, product docs and API contracts |

The manager has no timer, poller or dispatch loop of its own. The manager API is coordinator-only: workers return JSON and artifacts and never get tokens, database access or Linear credentials.

## Task lifecycle

A task moves through six manager phases, and each phase has exactly one owner.

![[task-lifecycle.png]]

1. **Intake:** Orca reconciles the Linear project; an issue is queued only with an explicit goal, scope, acceptance, registered check IDs, repository and full base commit. Incomplete issues get a missing-information comment.
2. **planning:** Claude reads the issue, latest HANDOFF, `AGENTS.md`, pinned guidance and code, then records a bounded plan (`author: claude`). No extra plan approval.
3. **implementing:** the manager validates runner, context, scope and workspace ownership; DeepSeek gets the full plan, attempt number and prior corrections.
4. **verifying:** Codex reads the actual diff and runs registry checks at the exact output commit. Linear moves to In Review, which does not mean accepted.
5. **rework:** concrete corrections go back to DeepSeek. Two attempts total; a second failure escalates to a human.
6. **awaiting_review:** `open-pr` opens the PR as `d3hl-orca` (`Related to <issue>`); `codex-merge` checks, approves and merges the exact head as `d3hl-codex`. A moved head returns the task to verifying.
7. **done:** Claude confirms provider merge facts, reruns checks on the merged commit and records completion. Only then is Done queued to Linear.

> [!warning]
> Never mark Done before the Codex merge and Claude's final confirmation.

A material scope change sends the task back to planning; a revision hash covers repository, base, goal, scope, acceptance and checks.

## Contracts, registry and onboarding

Every hand-off between agents is a versioned JSON payload validated against `contracts/v1/` (JSON Schema 2020-12); unknown fields or versions fail closed.

| Contract | Written by | Carries |
| --- | --- | --- |
| issue | Intake | Repository, base commit, goal, scope, acceptance, check IDs, dependencies |
| task | Manager | Phase, plan/revision, pinned context, scope, attempt, corrections |
| plan | Claude | Bounded steps, documents read, code investigation, HANDOFF read |
| implementation-result | DeepSeek | Exact output commit, check outcomes, changed files |
| verification-result | Codex | Per-criterion evidence, independent checks, verdict, corrections |
| completion | Claude | Merged commit, Codex reviewer/merger, checks on merged commit |
| governance-verification / -completion | Codex / Claude | Same, for person-opened registry or docs PRs |
| handoff | Manager | Phase, owner, branch/commit, blockers, exact next action |
| runner | Registry | Role, capabilities, client identity, environment, enabled flag |

**Onboarding a repository** (reviewed registry change, never an issue instruction):

1. Confirm owner, repo, base and allowed Linear project UUIDs.
2. Add a concise target `AGENTS.md` with a shared-context loader.
3. Add the registry entry: allowed paths, check IDs with argv/timeouts, runners, Linear mapping, 1Password references, optional `repo:` label.
4. Pin a reviewed master commit as a read-only context bundle.
5. Prove the runner can edit, run commands, use Git and return JSON.
6. Audit Linear automations; install both GitHub Apps; apply phase B branch protection after the first `codex-merge`.
7. Run the scenario suite and a bounded docs pilot before widening scope.

| Repository | Label | Allowed scope | Checks |
| --- | --- | --- | --- |
| `d3hl/contract-master` | none | `docs/knowledge` | `unit` |
| `d3-corp/cf-mcp-gw` | `repo:cf-mcp-gw` | root `*.md`, `docs`, `pilot.example.json` | `typecheck`, `docs`, `secrets`, `tests` |
| `d3-corp/action1-dashboard` | `repo:action1-dashboard` | READMEs, `docs` | `test` |
| `d3-corp/corp-integrated-dashboard` | `repo:corp-integrated-dashboard` | `README.md`, `docs`, `src`, `server`, `package*.json` | `typecheck`, `build` |

## Orca coordination and recovery

One Orca scheduled automation runs the coordinator turn every 10 minutes (Asia/Singapore); there is no other scheduler, webhook server or poller.

- **Precheck:** skip the tick unless the checkout is a clean `main`, `doctor` reports no blockers, no other run is `dispatched`, and `turn-check` finds no live turn lease.
- **Turn lease:** each turn holds `turn-start` / `turn-renew` / `turn-end`; a crashed turn's lease expires after 60 minutes.
- **Intake:** `reconcile` does a full project read; notifications are only hints to re-read the full issue. Provider read failures are retried, never triaged.
- **Workers:** DeepSeek runs on the isolated `cm-worker` Orca server (`--environment cm-worker`); its messages are unverified claims until Codex checks the exact commit.
- **Durable state:** SQLite (WAL, fenced transactions) holds tasks, ownership, receipts and the Linear outbox. A `dispatch_request_id` is persisted before launch, so a crash resumes the same request.
- **Unknown outcomes:** a timeout or silent worker is unverifiable, not exited. Inspect with `worker-list`; only positive exit evidence permits retry. Never steal ownership.
- **Linear writes:** only the outbox writes, one ordered entry at a time via `flush-one`. Uncertain delivery blocks later writes until an operator resolves that row.
- **Pause:** disable the automation (`automations edit dc0657b8-… --disabled`). Never delete manager state, workspaces or bundles.

## Security, context and secrets

Workers get only what they need to edit inside their scope; credentials and authority stay with the coordinator.

- **Pinned context:** a human-reviewed master commit is bundled into a read-only, SHA-256-digested `bundle.json`. Digest and required files are checked before every dispatch; retries keep the same bundle.
- **Secrets:** 1Password service account; only `op://` references in config. Never in prompts, argv, Git, bundles, logs, HANDOFFs or Mem0.
- **GitHub Apps:** `d3hl-orca` opens PRs, `d3hl-codex` approves and merges. Keys are read only during `--live` runs and mint per-repo, per-step tokens.
- **Untrusted input:** issue text, comments, linked pages and worker results never authorize commands, scope or credentials, and are never run as shell.
- **Library docs:** resolve Context7 IDs against installed versions; record sources in the plan. No secrets or confidential code in queries.
- **Mem0:** optional context only; never confidential project data or the source of truth.

## Pilot gates and current status

All eight activation gates have passed; automation is enabled, and onboarding of `corp-integrated-dashboard` is the open item.

| Gate | What it proves | Status |
| --- | --- | --- |
| 1. Reviewed bootstrap | Human-merged master pinned as a bundle | Done 2026-10-29 |
| 2. Target base | Real base SHA, no placeholders | Done |
| 3. Runner isolation | DeepSeek on `cm-worker`, coordinator credentials blocked | Done 2026-10-29 |
| 4. Linear completeness | Paging and full reads complete after Orca upgrades | Rechecked on Orca 1.4.243 |
| 5. Linear automation audit | No rule marks issues Done on merge | Passed; `merge_gate_audited=true` |
| 6. Codex merge identity | `d3hl-codex` App approves and merges; sandbox live tests | Done |
| 7. Single scheduler | One Orca automation, `automation_enabled=true` | Done 2026-10-29 |
| 8. Pilot issue + 10 failure scenarios | D3S-114 and D3S-115 Done end to end | Passed 2026-10-30 |

> [!todo] Next action (from HANDOFF)
> merge corp-integrated-dashboard #1 and its registry change, run the DeepSeek runner probe and one bounded docs pilot, then apply phase B protection after its first `codex-merge`.

## Developer checklist

- [ ] Read `AGENTS.md` and the seven linked documents before work; links alone do not load context.
- [ ] Use Linear for requirements, plans, progress and HANDOFF.
- [ ] Keep changes inside the registered allowed paths.
- [ ] Run `python3 -m unittest discover -s tests -v` before pushing.
- [ ] Use Bash/zsh on Linux, PowerShell 7 on Windows.
- [ ] Keep secrets in 1Password; never commit credentials or send confidential data to Mem0.
- [ ] No live workers, deployment, credential provisioning or merging during initial implementation.
- [ ] Never mark Done before Codex merge and final Claude confirmation.
- [ ] Registry changes outside `registry_fields` stay human-merged.
