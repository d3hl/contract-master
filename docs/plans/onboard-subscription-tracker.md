# Plan: onboard `d3hl/subscription-tracker`

Status: design approved by the owner on 2026-11-29; plan below awaiting review.

## Intent

The owner wants the approved subscription tracker
(`docs/superpowers/specs/2026-11-28-subscription-tracker-design.md` in that repo) built
through Contract Master: DeepSeek implements and tests, Codex verifies and merges,
Claude plans and confirms. It is a personal, local-only TypeScript tool with no code
yet; its 6-task implementation plan already exists
(`docs/superpowers/plans/2026-11-28-subscription-tracker.md`).

## Goals

- `d3hl/subscription-tracker` is a registered repository: Linear project, `repo:` label,
  Orca repo on both hosts, both GitHub Apps, checks, scope and a passing runner probe.
- The product plan's six tasks reach DeepSeek as ordinary Linear issues, one at a time.

## Non-goals

- No change to manager code, schemas or the coordinator prompt.
- No change to the product design or its plan (beyond issue wording).
- No widening of any other repository.

## Anti-goals

- A check that runs npm install scripts.
- Target `AGENTS.md`, CI or credentials inside the allowed scope.
- An issue queued with a placeholder base commit.

## Approaches (owner picked A, 2026-11-29)

| Approach | Trade-off |
|---|---|
| **A. Docs-only seed; DeepSeek builds everything (chosen)** | All product code follows the normal path. Checks cannot be proven on `main` before registration; they are first proven on Task 1's output and then re-run on merged `main`. |
| B. Owner scaffolds `package.json`/`tsconfig` by hand first | Matches earlier onboardings exactly, but the owner does manual work and the probe waits on it. |

Owner decisions: repository `d3hl/subscription-tracker`; approach A. Visibility
**public** is Claude's call (GitHub Free only offers branch protection on public
repositories; the repo holds no secrets or real data); the owner can overrule.

## Design

1. **Seed commit** (owner, by hand): the existing `docs/` plus a target `AGENTS.md`
   from `docs/templates/target-AGENTS.md`, adapted with the repo's commands
   (`npm ci`, `npm test`, `npx tsc --noEmit`) and the plan's Global Constraints.
   Public, default branch `main`, phase A protection.
2. **Owner-only steps:** add the repo to both `d3hl` App installations (176325322
   orca, 176202750 codex); create the Linear project and label
   `repo:subscription-tracker`.
3. **Orca:** register the repo on RH3 (coordinator) and clone it to
   `~/worker/repos/subscription-tracker` on RH1 (`rh1-d3`); read both repo ids.
4. **Registry entry** (reviewed, human-merged PR — new repositories are outside the
   governance path):
   - `allowed_scope`: `src`, `tests`, `package.json`, `package-lock.json`,
     `tsconfig.json`, `vitest.config.ts`, `.gitignore`, `README.md`.
     `AGENTS.md`, `docs` and `.github` stay out.
   - `checks`: `test` = `npm ci --ignore-scripts` then Vitest; `typecheck` = the same
     then `tsc --noEmit`. Checks run in a fresh temporary copy so `node_modules` never
     lands in the checkout. (The design first allowed install scripts for
     `better-sqlite3`; the probe showed its prebuilt binary makes that unnecessary.)
   - `dependency_versions`: Node as installed on both hosts (RH3 is 22.23.2; RH1 to
     be read).
   - Same Apps, `merge_identity`, runners and `merge_gate_audited` as `pve-orchenv`.
5. **Runner probe** on `rh1-d3` against the seed commit: proves the clone, Node,
   npm registry reach and a native `better-sqlite3` build inside the sandbox.
6. **Issues:** one tracking parent "Subscription tracker v1"; six executable children,
   one per plan task, each blocked by the previous. A child gets its
   `contract-master` block (with the real base commit) only when its predecessor is
   merged, so nothing waits in intake with a placeholder.
7. **Manual checks:** the plan's `notify-send` check (Task 4 Step 5) and smoke test
   (Task 6 Step 5) need the owner's desktop session; they are acceptance criteria the
   owner runs by hand before Claude confirms those tasks Done.
8. **Phase B** protection after Task 1's first `codex-merge`.


---

# Implementation plan

> **For agentic workers:** this is a manual manager change ([superpowers policy](../policies/superpowers.md#manual-manager-changes)).
> Claude runs the steps in this session with `superpowers:executing-plans`, outside any
> coordinator turn (`turn-check` must report `free` before each work session). Steps
> marked **(owner)** need the owner's GitHub or Linear admin rights. The DeepSeek probe in
> Task 3 is a DeepSeek worker, never a Claude one. Steps use `- [ ]` checkboxes.

**Goal:** `d3hl/subscription-tracker` is a registered, probed repository and its first
product issue is ready for the coordinator.

**Architecture:** One seed commit in the target repo, Orca registration on both hosts, one
supervised DeepSeek probe, one reviewed contract-master PR (registry entry, readiness test,
docs), then Linear issues created one at a time.

**Tech stack:** Orca CLI 1.4.280 (`/home/d3/.config/orca/cli/bin/orca`), `gh`, manager
CLI `python3 -m contract_master`, Node 22.23.2 (RH3) / 24.22.3 (RH1), npm.

**Spec:** the design above, and the product spec and plan in the target repo.

## Global Constraints

- Never edit the coordinator checkout `~/orca/workspaces/contract-master`; it must stay a
  clean `main`. All contract-master edits happen in this worktree
  (`~/orca/workspaces/contract-master-onboard-subtrack`, branch
  `d3adc3II/onboard-subscription-tracker`).
- Linear writes (project, label, issues) are the owner's; Claude drafts the text only.
- No secret value in any command, file, PR or report.
- Allowed scope, exactly: `src`, `tests`, `package.json`, `package-lock.json`,
  `tsconfig.json`, `vitest.config.ts`, `.gitignore`, `README.md`.
- Check argv, exactly (both `timeout_seconds: 600`):
  - `test`: `sh -c 'set -e; t=$(mktemp -d); trap "rm -rf \"$t\"" EXIT; tar -c --exclude=./.git --exclude=./node_modules --exclude=./dist . | tar -x -C "$t"; cd "$t"; npm ci --ignore-scripts --no-audit --no-fund; ./node_modules/.bin/vitest run'`
  - `typecheck`: the same prefix, ending `./node_modules/.bin/tsc --noEmit`.
  The copy keeps `node_modules` out of the checkout (inspection requires a clean tree)
  and includes uncommitted work when DeepSeek runs checks before committing.
  `--ignore-scripts` stays, as in every Node repo: the probe showed `better-sqlite3` 13
  ships a prebuilt linux-x64 binary, so no install script is needed (ruling 2026-11-29).
- `dependency_versions`: `{"node": "22.23.2"}` (the lower host version; the product plan
  needs Node ≥ 22).
- Orca 1.4.280 is newer than the 1.4.274 the `--on rh1-d3` route was proven on: re-read
  `orca skills get orchestration --reference references/placement-and-remote.md` before
  Task 3 and stop if the route changed.

## Review Focus

1. **Install scripts:** every registered `npm ci`, this repo's included, keeps `--ignore-scripts` (Task 4 test).
2. **Dirty tree after checks:** `inspect-checkout` must find the checkout unchanged after
   both checks (Task 3 Step 5).
3. **Native build in the sandbox:** `better-sqlite3` either downloads a prebuilt binary
   (needs github.com) or compiles (needs gcc/make/python3 — all present on RH1 at host
   level). The probe proves which works inside the sandbox (Task 3).
4. **Scope escape:** `AGENTS.md`, `docs/…`, `.github/…`, `node_modules/…`, `dist/…`
   are outside scope (Task 4 test).
5. **Folder → git project:** Orca already knows the workspace as a *folder* project
   (`09015dd3-…`); after `git init` it must be a git project with a fresh id (Task 2).

---

### Task 1: Seed the target repository

**Files (target repo, `~/orca/workspaces/subscription-tracker`):**
- Create: `AGENTS.md` (from `docs/templates/target-AGENTS.md` plus a "Commands" section:
  `npm ci`, `npm test`, `npx tsc --noEmit`; and the product plan's Global Constraints by
  reference to `docs/superpowers/plans/2026-11-28-subscription-tracker.md`).
- Create: `.gitignore` with `node_modules`, `dist`, `*.db` (so the seed is clean; Task 1 of
  the product plan may keep it).
- Existing: `docs/` (spec, now approved, and plan).

- [ ] **Step 1:** Write `AGENTS.md` and `.gitignore`; show the owner `AGENTS.md`.
- [ ] **Step 2:** `git init -b main && git add -A && git commit -m "docs: approved design, plan and agent instructions"`.
- [ ] **Step 3 (owner approves, Claude runs):** `gh repo create d3hl/subscription-tracker --public --source . --push`.
  Expected: `git ls-remote origin main` prints the seed SHA.
- [ ] **Step 4:** Apply phase A protection on `main` (PR required, admin bypass allowed),
  saving the before/after JSON under `.state/branch-protection/subscription-tracker-*.json`
  in the coordinator checkout's ignored `.state` (same as the other repos).
- [ ] **Step 5 (owner):** add the repo to the `d3hl` installations of `d3hl-orca`
  (176325322) and `d3hl-codex` (176202750).
  Expected: the owner confirms both installation pages list the repo (proven in Task 4 Step 6).
- [ ] **Step 6 (owner):** create Linear project "Subscription Tracker" (team D3S) and label
  `repo:subscription-tracker`. Claude reads back the project UUID with the Linear connector
  (read-only).

### Task 2: Register the repo in Orca on both hosts

- [ ] **Step 1:** Turn the RH3 folder project into a git project: find its setup with
  `orca project setups --json`, then `orca project setup-update --setup <id> --kind git --json`.
  If Orca refuses the kind change, `orca repo add --path /home/d3/orca/workspaces/subscription-tracker --kind git --json`.
  Expected: `orca repo list --json` shows `git` for that path; record the id as `orca_repo_id`.
- [ ] **Step 2:** Clone on RH1: `ssh rh1-worker 'git clone https://github.com/d3hl/subscription-tracker ~/worker/repos/subscription-tracker'`.
- [ ] **Step 3:** `orca repo add --environment rh1-d3 --path /home/d3/worker/repos/subscription-tracker --json`,
  then `orca project setup-update --environment rh1-d3 --setup <id> --worktree-base-path /home/d3/worker/worktrees --json`.
  Expected: `orca project setups --environment rh1-d3 --json` shows the row `ready`, kind
  `git`, host `local`; record its `repoId` for the probe.

### Task 3: DeepSeek runner probe on `rh1-d3`

Same shape as the pve-orchenv probe ([runner verification](../operations/runner-verification.md#pve-orchenv-probe-2026-11-07)).

- [ ] **Step 1:** Re-read the installed placement guide (Global Constraints). Stop on any
  route change.
- [ ] **Step 2:** `orchestration run-create --objective "subscription-tracker runner probe"`,
  then `task-create` with a spec file: on a new top-level worktree `cm-probe-subtrack`, add
  only `package.json` (`"type": "module"`, script `test: vitest run`, dependencies
  `better-sqlite3`, dev `vitest`, `typescript`), `package-lock.json`, a `tsconfig.json`
  (`strict`, `noEmit` ok) and `tests/probe.test.ts` that opens `new Database(':memory:')`
  and asserts `select 1 as x` returns `{x: 1}`; run both Global Constraints checks
  verbatim; commit locally; never push; report node/npm versions, model identity and
  check output in `worker_done`.
- [ ] **Step 3:** `worker-start --task … --run … --on rh1-d3 --worktree new-top-level --repo id:<rh1 repoId> --name cm-probe-subtrack --setup skip --agent opencode2 --retry-request <new id> --json`.
  Read it with `worker-read`; if the prompt is pasted but not submitted, send exactly one
  Enter (`terminal send --environment rh1-d3 --terminal <handle> --enter`). End the turn and
  wait for Orca to wake the session.
- [ ] **Step 4:** On `worker_done`, fetch the commit:
  `ssh rh1-worker "git -C ~/worker/worktrees/subscription-tracker/cm-probe-subtrack bundle create - <seed>..HEAD" > probe.bundle`
  into a fresh RH3 clone (scratchpad).
- [ ] **Step 5:** In that clone call `contract_master.evidence.inspect_checkout` with the
  two Global Constraints argv, as the pve-orchenv probe did. Expected: both pass, the diff is exactly the four probe files, and
  `git status --porcelain` is empty afterwards. A failure stops the onboarding and goes to
  the owner (Review Focus 2, 3).
- [ ] **Step 6:** `worker-release --dispatch <id>`. The probe commit is never pushed.

### Task 4: Registry entry, test and docs (contract-master PR)

**Files (this worktree):**
- Modify: `config/registry.json` (new `d3hl/subscription-tracker` entry)
- Modify: `tests/test_readiness.py` (new test)
- Modify: `docs/onboarding/repositories.md`, `docs/operations/worker-host.md`,
  `docs/operations/runner-verification.md`, `docs/operations/HANDOFF.md`

- [ ] **Step 1: Write the failing test** `test_subscription_tracker_scope_and_checks` in
  `tests/test_readiness.py`:

```python
policy = self.registry["repositories"]["d3hl/subscription-tracker"]
self.assertEqual(policy["linear_label"], "repo:subscription-tracker")
self.assertEqual(set(policy["checks"]), {"test", "typecheck"})
for path in ("AGENTS.md", "docs/x.md", ".github/workflows/ci.yml", "node_modules/a.js", "dist/main.js"):
    self.assertFalse(within(path, policy["allowed_scope"]), path)
for path in ("src/main.ts", "tests/domain/dates.test.ts", "package.json", "package-lock.json",
             "tsconfig.json", "vitest.config.ts", ".gitignore", "README.md"):
    self.assertTrue(within(path, policy["allowed_scope"]), path)
for check in policy["checks"].values():
    text = " ".join(check["argv"])
    self.assertIn("mktemp -d", text)
    self.assertIn("--exclude=./.git", text)
    self.assertNotIn("op://", text)
# No registered check runs npm install scripts.
for repo_id, other in self.registry["repositories"].items():
    for check in other["checks"].values():
        text = " ".join(check["argv"])
        if "npm ci" in text:
            self.assertIn("--ignore-scripts", text, repo_id)
```

- [ ] **Step 2:** `python3 -m unittest tests.test_readiness -v`. Expected: FAIL with
  `KeyError: 'd3hl/subscription-tracker'`.
- [ ] **Step 3:** Add the registry entry: copy `d3hl/pve-orchenv`'s `base_ref`, runners,
  `merge_gate_audited`, `merge_identity`, `github_apps`, `credential_references`,
  `required_context`, `runner_config`; set `url`, `orca_repo_id` (Task 2 Step 1),
  `linear_projects` (Task 1 Step 6), `documentation_entrypoints: ["AGENTS.md", "docs/superpowers/plans/2026-11-28-subscription-tracker.md"]`,
  `allowed_scope`, `checks`, `dependency_versions` (Global Constraints),
  `linear_label: "repo:subscription-tracker"`.
- [ ] **Step 4:** `python3 -m unittest discover -s tests -v`. Expected: all pass (including
  `test_registered_registry_has_no_blockers`); `python3 -m contract_master doctor` reports no
  blockers.
- [ ] **Step 5:** Docs: a row and paragraph in `repositories.md` (scope, checks, install
  scripts exception, phase A until first `codex-merge`, manual notify/smoke checks);
  the rh1 repo id in `worker-host.md`; a "subscription-tracker probe (2026-11-…)" section in
  `runner-verification.md` with the Run/Task/Dispatch ids and Task 3 Step 5 evidence; a
  HANDOFF line with the exact next action.
- [ ] **Step 6:** Mint one narrowed installation token per App with
  `contract_master.github_app.RepoApp(policy, "pr"|"merge").token()` and print only success
  or the HTTP status, never the token. A 422 means Task 1 Step 5 is missing (as on 2026-11-07
  for pve-orchenv).
- [ ] **Step 7:** Commit (`git commit -F <file>`), push the branch, open the PR as the owner's
  account with `gh pr create --body-file`. A new repository is outside the governance path,
  so the owner merges it by hand.

### Task 5: First product issue

- [ ] **Step 1:** After the PR merges, `doctor` on the coordinator checkout reports no
  blockers. No new pin is needed: this change edits no `required_context` file.
- [ ] **Step 2:** Draft, in the scratchpad, the parent "Subscription tracker v1" (tracking,
  no block) and child 1 "Project scaffold, dates and money" with a `contract-master` block:
  `repo_id` `d3hl/subscription-tracker`, `base_commit` = the seed SHA (full), goal and
  acceptance copied from product-plan Task 1 (incl. Review Focus 1 and 5 tests),
  `allowed_scope` = registry scope, `required_checks` `["test", "typecheck"]`.
  Children 2–6 are drafted without a block, to be completed when the previous one merges.
- [ ] **Step 3 (owner):** create the parent and child 1 in the Linear project with label
  `repo:subscription-tracker`.
- [ ] **Step 4:** Wait for the next coordinator turn (no manual dispatch). Expected:
  reconcile queues child 1 and plans it. Record the outcome in HANDOFF.
- [ ] **Step 5:** After child 1's first `codex-merge`, apply phase B protection (owner request,
  as for cf-mcp-gw) and confirm `test`/`typecheck` pass on merged `main`.
