# Plan: Codex review and merge of manually opened registry/policy PRs

Status: implemented in this PR (2026-11-01), author: claude; Codex verification pending. Motivation: PR #56 (scope widening
for `d3-corp/corp-integrated-dashboard`) is a person-opened registry PR. Today no
manager path reviews or merges such PRs, so they wait for an ad hoc human merge
(pilot gate 6: "Revisit if contract-master gets a command for Codex to review and
merge non-task PRs"). This plan adds that command set. PR #56 and `main` are not
changed by this work.

Manually managed manager enhancement, like the earlier bootstrap code PRs. It is
not a Linear task: no fake issue, plan or implementation history is created, and
the docs-only pilot scope of `d3hl/contract-master` (`docs/knowledge`) is not
widened to let workers edit the manager.

## Behavior

```
open PR (person) ──review-scan──▶ record (repo#number, trusted base SHA, head SHA, scope)
   │                                  │ ineligible: reason recorded, no GitHub/Linear write
   ▼                                  ▼
Codex: review-inspect (trusted-base check argv at exact head) + diff review
   ──review-verify──▶ awaiting_merge │ changes_requested (author pushes; new head re-verifies)
   ──review-merge (dry run default; --live)──▶ d3hl-codex: check, APPROVE head, merge sha=head
   ──read-only merge gate──▶ merged ──review-confirm (Claude)──▶ done
```

- **Discovery.** The existing Orca coordinator turn runs one more one-shot command,
  `review-scan`. No new scheduler, timer, webhook or poller.
- **Opt-in, reviewed config.** A `governance_review` block on a repository in the
  registry. Only the copy loaded from the coordinator's clean `main` checkout counts.
  PR titles, labels, bodies and the PR's own registry content never grant
  eligibility, authors, paths, checks or commands.
- **Dedicated records**, table `pr_reviews`, key `<repo>#<number>`. A record binds
  repository, PR number, author, trusted base SHA, head SHA, changed files,
  structured registry changes, the derived acceptance criteria, and the check argv
  snapshotted from the trusted base. Records never enter `tasks`, never create
  Linear writes and never use task ownership tokens.
- **Serialized writes.** Every record write runs inside a manager SQLite
  transaction that also verifies the caller's turn lease is the live one
  (`turn-start` lease). A second coordinator, an expired lease or a stale head
  cannot write.
- **Head and base binding.** A different head SHA or a moved base branch resets
  the record to `verifying` and discards verdict and merge steps. `review-merge`
  re-reads both immediately before any write.
- **Codex review.** Codex runs checks from the record's snapshot (trusted base
  argv), in its own checkout at the exact head, and must give evidence for every
  derived criterion. Registry scope, check, documentation and per-repository
  changes each become explicit criteria.
- **Merge.** As `d3hl-codex` (`github_apps.merge`, narrowed installation token from
  1Password, same `RepoApp` as `codex-merge`): `codex-verification` check, APPROVE
  the exact head, merge with `sha`, read-only merge gate. Each step is recorded and
  skipped on rerun if GitHub already shows it. A human's latest
  `CHANGES_REQUESTED` vetoes (record `escalated`). Dry run by default; `--live`
  needs `automation_enabled`, `merge_gate_audited`, complete App config and an
  enabled `governance_review`.
- **Claude confirmation** records final acceptance on the merged commit (`done`).
- **Escalation is final for automation.** Two `changes` verdicts on a PR (counted
  across all its heads), a human veto, an unmergeable PR or a merge at an
  unverified head set `escalated`. Later heads or base moves never reopen it;
  a person merges or closes the PR by hand.

## Registry block

Added to `d3hl/contract-master` only and **enabled** in this PR: this PR is the
reviewed authorization for the bounded policy, so the path is usable after merge
without another activation PR. That changes no runtime or automation state:
`review-merge` stays a dry run unless `--live` is passed, and `--live` keeps the
existing gates (`automation_enabled`, `merge_gate_audited`, complete App config).
Because the path does not exist on `main` yet, this bootstrap PR follows the
current external review process. Later changes to `governance_review` itself are
refused by the governance path and stay human-merged.

```json
"governance_review": {
  "enabled": true,
  "authors": [{"login": "d3adc3II", "type": "User"}],
  "allowed_paths": ["config/registry.json", "docs/onboarding", "docs/knowledge",
                    "docs/operations/HANDOFF.md"],
  "registry_fields": ["allowed_scope", "checks", "documentation_entrypoints", "dependency_versions"],
  "checks": ["unit"]
}
```

The same change raises `d3hl/contract-master` `checks.unit.timeout_seconds` from
120 to 600: the 95-test base suite measured 116.6 s (PR #56 verification), so the
expanded suite would otherwise time out under `inspect_checkout`. The worker
records the measured duration of the final suite as evidence.

A PR's registry changes are its own delta: the registry at the PR's merge base
compared with the registry at its head (both untrusted data). Base-branch
additions since the merge base (for example this block, for PR #56) are not
deletions proposed by the PR. Each proposed change is then checked against the
current trusted registry: if the base changed the same field since the merge base,
or removed that repository, the PR is ineligible until rebased. Check argv always
comes from the current trusted registry.

Any registry change outside `registry_fields` of an **existing** repository makes
the PR ineligible: top-level keys (`automation_enabled`, `reviewed_master_commits`,
`linear_workspace`, `version`), added/removed repositories, `merge_identity`,
`github_apps`, `credential_references`, runners, `merge_gate_audited`,
`governance_review`, `linear_projects`, `linear_label`, `url`, `base_ref`. Those
stay human-merged.

## Code (new module; `manager.py` task path unchanged)

`contract_master/governance.py`:

- `policy(registry, repo_id)`: the enabled, well-formed block or `ContractError`.
- `registry_changes(base, head, fields)`: deterministic list of
  `{"repo", "field", "before", "after"}`; raises `ContractError` naming the first
  forbidden change. A non-object/unparseable head registry is ineligible.
- `criteria(record)`: sorted, deterministic strings: one scope criterion, one checks
  criterion, one per registry change (checks changes get a stricter wording: argv
  runs only that repository's own tooling, no credentials, no network writes beyond
  package install), one for docs consistency when the registry changed.
- `class Governance(store, registry, clock=time.time)`:
  - `intake(lease, pull, files, base_sha, head_registry=None)` → record summary.
    Eligibility (each failure stored as phase `ineligible` with reason): repository
    registered with an enabled block; PR open and not draft; base ref equals the
    registered base branch; head repository equals the base repository (no forks);
    author `(login, type)` listed; author is not the merge App; every file within
    `allowed_paths`; registry changes allowed. Same head+base: no-op. New head or
    base: reset to `verifying`, drop verification and merge steps, append to
    `history`. `merged`/`done` records never change. A closed unmerged PR becomes
    `closed`.
  - `verify(lease, key, result)` (schema `governance-verification`): phase
    `verifying`; `head_sha`/`base_sha` equal the record; criteria set equals the
    record's; check IDs equal the snapshot and each `commit` is the head; `pass`
    needs all criteria/checks passing and no corrections → `awaiting_merge`;
    `changes` needs corrections → `changes_requested`; the second `changes`
    verdict for a record → `escalated`.
  - `merge(lease, key, app, reader, current_base_sha)`: phase `awaiting_merge`;
    same steps and refusals as `Manager.codex_merge`, reusing
    `github.latest_reviews/approved_by/human_veto`; head or base moved → reset to
    `verifying` and raise; veto → `escalated`; 405/409/422 merge error → `escalated`
    with reason; success → `merge_receipt`, phase `merged`.
  - `confirm(lease, key, evidence)` (schema `governance-completion`): phase
    `merged`; `author: claude`; accepted/merged commits match the receipt; every
    snapshot check passed at the merged commit → `done`.
  - `get(key)`, `list()`.
- `store.py`: `CREATE TABLE IF NOT EXISTS pr_reviews(key TEXT PRIMARY KEY, data TEXT NOT NULL)`.
- `turns.py`: `TurnLease.require(db, lease)` raises unless `lease` is the live lease.
- `contracts/v1/governance-verification.schema.json`,
  `contracts/v1/governance-completion.schema.json`.

CLI (`__main__.py`), all JSON, all requiring `--lease`:

- `review-scan`: refuses unless `--registry` is the checkout's
  `config/registry.json`, the checkout is clean and its `HEAD` equals the base
  branch tip read from GitHub. Reads open PRs, files (paged) and, if
  `config/registry.json` changed, that file at the head SHA via read-only `gh api`.
  Also re-reads non-final records missing from the open list (closed/merged).
- `review-show KEY`, `review-list` (no lease needed).
- `review-inspect KEY WORKSPACE`: merge base of record base and head in
  WORKSPACE, then `evidence.inspect_checkout` with `allowed_paths` and the
  snapshotted check argv.
- `review-verify KEY FILE`, `review-confirm KEY FILE`.
- `review-merge KEY [--live]`: dry run lists steps and blockers, no writes.

## Tests (`tests/test_governance.py`, temporary state only)

Head move before verify, after verify and between approve and merge; base move;
concurrent coordinators (second lease refused, stale lease refused, two intakes of
the same PR leave one record); crash/rerun at check, approve and merge with no
duplicate writes; human veto; unregistered repo, disabled block, fork, unknown
author, draft, out-of-scope file, forbidden registry field, change to
`governance_review` itself; head registry that alters check argv is recorded only
as a criterion and the snapshot keeps base argv; dry run and live gates; schema
round-trips; existing suites unchanged (ordinary task path unaffected).

## Docs

`docs/policies/workflow.md` (governance PR section), `docs/operations/coordinator-prompt.md`,
`docs/contracts/v1.md`, `docs/onboarding/repositories.md` (block),
`docs/operations/pilot.md` (gate 6 note), `docs/operations/HANDOFF.md`.

## Limitations

- Checks execute PR code (as CI does) in Codex's separate checkout; argv comes from
  the trusted base only.
- Any movement of the base branch forces re-verification.
- Branch protection on `contract-master` stays phase A; any protection change is
  a separate reviewed change. The coordinator starts calling `review-scan` only
  after this PR merges and the scheduled turn reads the updated prompt.
- No Linear records: progress lives in `pr_reviews` and the turn HANDOFF.

## Activation after merge (not automatic)

Merging this PR does **not** by itself start discovery. Read-only check on
2026-11-01 (`automations show --id dc0657b8-923e-4d65-a57f-0a1d8b8ab4a9`):

- The installed prompt is a pointer, not a copy: "Run one Contract Master
  coordinator turn. Read docs/operations/coordinator-prompt.md in this workspace
  and follow it exactly, together with every document it requires." So no stored
  prompt refresh is needed; each turn reads the prompt file from the workspace.
- That workspace is the existing checkout `/home/d3/orca/workspaces/contract-master`
  (`workspaceMode: existing`), at `main` `e53703c`. Neither the precheck nor the
  prompt fetches or fast-forwards it, so a turn keeps reading the old prompt and
  old registry until someone updates the checkout.
- The automation is currently `enabled: false` (`config/orca-automation.json`
  still says `true`; the live state differs).

Steps for the owner after merge (none are done by this PR):

1. `git -C /home/d3/orca/workspaces/contract-master pull --ff-only` on `main`
   when no turn holds the lease (`python3 -m contract_master turn-check`).
2. Confirm `doctor` reports no blockers from that checkout.
3. Re-enable the schedule when the owner chooses
   (`automations edit dc0657b8-… --enabled`); the stored prompt stays as is.
   If an operator ever replaces it with a copied prompt, it must again only point
   to `docs/operations/coordinator-prompt.md`.

After that first manual update, `review-refresh` (run under the turn lease before
`review-scan`) fast-forwards the checkout only to a commit that the governance path
itself merged and recorded (`merge_receipt.merged_commit`). Any other movement of
`main` makes it refuse; a person updates the checkout, and ordinary Linear intake
continues meanwhile. This PR's own merge is not such a commit, so step 1 is manual.

`review-scan` checks that the checkout is clean for tracked files only
(`git status --porcelain --untracked-files=no`), the same rule as the precheck's
`git diff --quiet HEAD`, because the checkout holds untracked worktree folders.

## Execution

DeepSeek implements on `cm-worker` through Orca (one Run, one Task, at most two
attempts) from this plan's commit; Claude coordinates; the parent Codex session
independently verifies the resulting PR. No merge, deployment or credential change.
Verification: `python3 -m unittest discover -s tests -v`, 120-column style test,
`doctor` unchanged.
