# Plan: automate Codex approval/merge and PR opening

Status: proposed (2026-10-29). Code, tests and docs only. No live GitHub writes,
credential provisioning or merges until the pilot gates below pass.

## Context

The workflow (PR #15) says Codex verifies, reviews and merges, and the registry
records `merge_identity: d3hl-codex[bot]` (PR #16). Today `d3hl-codex[bot]` can only
act when a person mints an App token by hand. Two pieces are missing:

1. **A gated merge step.** Nothing turns Codex's passing verification into a GitHub
   approval and merge of the exact verified commit.
2. **Someone to push the branch and open the PR.** Workers do not push. GitHub does
   not let an App approve a PR it opened, so `d3hl-codex` cannot open PRs itself.

Goal: the coordinator runs one manager command per step. Each command checks
manager state first, acts as the right GitHub App, records what it did, and is
safe to rerun after a crash.

```
DeepSeek output commit
  -> open-pr          (d3hl-orca[bot]: push task branch, open PR "Related to D3S-n")
  -> Codex verify     (existing; manager -> awaiting_review on pass)
  -> codex-merge      (d3hl-codex[bot]: check run, APPROVE, merge sha=verified commit)
  -> confirm-merge    (existing read-only gate)
  -> Claude complete  (existing; enqueues Linear Done)
```

## Decisions

- **Two Apps, separate duties.** `d3hl-orca` pushes task branches and opens PRs;
  `d3hl-codex` posts `codex-verification`, approves and merges. Neither can do the
  other's job: `d3hl-orca` is not on `main`'s push allowlist and has no checks
  permission; `d3hl-codex` never opens PRs.
- **Merging happens in a manager command, not an Action or a worker prompt.** The
  manager already holds the verification verdict and verified commit, so the
  preconditions are code, not instructions. Orca stays the only scheduler.
- **Keys stay in 1Password.** A 1Password service account that can read only the
  two App key items is available to the coordinator host as
  `OP_SERVICE_ACCOUNT_TOKEN`. Keys are read at call time and never written to disk,
  prompts, logs, worker envelopes or Linear. DeepSeek never receives any token.
- **Writes stay out of `github.py`.** That module remains the read-only merge gate;
  writes go in a new module so review can see the boundary.

## Code changes

### New `contract_master/github_app.py`

- `AppCredentials(app_id, installation_id, key_reference)`.
- `installation_token(credentials, permissions)`:
  - read the key with `op read <key_reference>` (subprocess, no shell);
  - build an RS256 JWT (header/payload via stdlib `json`/`base64`), signed with
    `openssl dgst -sha256 -sign /dev/fd/N`, the key passed through a pipe (`pass_fds`),
    never a temp file;
  - `POST /app/installations/{id}/access_tokens` requesting only the target repo
    and the permissions the step needs (narrower than the App's install);
  - return the token in memory; error messages never include key or token text.
- `GitHubApp(token)` with only these calls, via `urllib.request` (stdlib):
  - `find_pr(repo, branch)`, `open_pr(repo, branch, base, title, body)`;
  - `check_runs(repo, sha)`, `create_check(repo, sha, conclusion, summary)`;
  - `reviews(repo, pr)`, `approve(repo, pr, sha, body)`;
  - `merge(repo, pr, sha, method="squash")` — always passes `sha`, so GitHub refuses
    if the head moved.
- Branch push: `git push https://x-access-token@github.com/<repo> <commit>:refs/heads/<branch>`
  with the token supplied through `GIT_ASKPASS`/an environment helper, not argv or
  the remote URL. Never pushes to `main`; refuses non-`task/` branch names.

### Manager operations (`contract_master/manager.py`, `phases.py`)

- `open_pr(task_id, token, provider)` — phases `verifying`, `awaiting_review`.
  - Requires a recorded output commit and a `task/…` branch with no issue identifier
    in it (keeps Linear auto-linking off).
  - Idempotent: if a PR for the branch exists, verify its head is the output commit
    and record it; otherwise push and open. Body: `Related to <identifier>` (never
    `Fixes`/`Closes`), goal, acceptance criteria, task ID.
  - Records `pr_url`, `pr_number` and `pr_opened_by` on the task.
- `codex_merge(task_id, token, provider)` — phase `awaiting_review` only.
  - Preconditions: verification verdict `pass`; PR recorded and in the registered
    repo; PR head equals `output_commit`; PR not opened by the merge App; no human's
    latest review is `CHANGES_REQUESTED` (reuse the review logic from `github.py`,
    factored into a shared function).
  - Steps, each recorded in `task["merge_steps"]` and skipped if GitHub already shows
    it done for the same commit: (1) `codex-verification` success check, (2) APPROVE
    on the commit, (3) merge with `sha`.
  - Then calls the existing `confirm_merge` with the read-only provider.
  - Failure handling: a moved head calls `observe_head` (back to `verifying`); a
    non-mergeable PR (conflict, failing required check) records the reason and stops
    for escalation. No automatic retries beyond the idempotent rerun.
- Add both operations to `phases.OPERATIONS` and the gate table in
  `tests/test_phase_gates.py`.

### CLI (`contract_master/__main__.py`)

- `open-pr TASK TOKEN` and `codex-merge TASK TOKEN`. Both take `--live`; without it
  they run against a dry-run provider that records intended calls. `--live` also
  requires `automation_enabled`, `merge_gate_audited` and complete App config, the
  same pattern as `prepare_dispatch(live=True)`.

### Registry and readiness

- Per repository, replace loose fields with:
  ```json
  "github_apps": {
    "pr":    {"slug": "d3hl-orca",  "app_id": null, "installation_id": null, "key_reference": null},
    "merge": {"slug": "d3hl-codex", "app_id": 5511451, "installation_id": 176202750,
              "key_reference": "op://d3HL/d3hl-codex.2026-10-28.private-key/private key"}
  }
  ```
  Keep `merge_identity`; readiness checks it equals `<merge.slug>[bot]` / `Bot`.
- `readiness.py` blockers: either App incomplete; both Apps the same; key reference
  not an `op://` path.

## Tests (fake GitHub and fake `op`/`openssl`; no network)

- Token minting: JWT claims (`iss`, `iat` backdated, `exp` ≤ 10 min); requested
  permissions are per step; key and token never appear in exceptions or output.
- `open_pr`: refuses `main` and issue-ID branches; reuses an existing PR; refuses
  if an existing PR's head differs; body uses `Related to`.
- `codex_merge`: refuses outside `awaiting_review`, without a pass verdict, on a
  moved head, on a PR opened by the merge App, and on a human change request;
  rerun after each simulated crash point performs no duplicate check, approval or
  merge; merge always sends `sha`; ends with a confirmed merge receipt.
- Live flag refused while activation gates are closed.
- Readiness blockers for each misconfiguration.

## Docs

- `docs/policies/workflow.md`: PR opening by `d3hl-orca`; phase 5 runs `codex-merge`.
- `docs/operations/coordinator-prompt.md`: call order `open-pr` → verify →
  `codex-merge` → `confirm-merge` → Claude completion; escalate on stop reasons.
- `docs/contracts/v1.md`: new CLI commands and task fields.
- `docs/operations/pilot.md`: new gates below.
- `docs/policies/context-and-security.md`: service account scope and key handling.

## Pilot gates added (manual, outside this PR)

1. Create GitHub App `d3hl-orca` in the `d3hl` org: Contents read & write,
   Pull requests read & write, Metadata read; no webhook; install on selected repos.
   Do **not** add it to `main`'s push allowlist.
2. Store the `d3hl-orca` App private key (`.pem`) in 1Password next to the
   `d3hl-codex` key; record its `op://` reference, App ID and installation ID.
3. Create a 1Password service account limited to those two items; provide
   `OP_SERVICE_ACCOUNT_TOKEN` to the coordinator host only.
4. Run `open-pr` and `codex-merge --live` once against a throwaway repository and
   record the PR, check run, approval and `merged_by` as gate 6 evidence.
5. Then apply phase B protection on `contract-master`: require `codex-verification`
   from App 5511451, push allowlist `d3hl-codex` only, no bypass.

## Execution

One implementation PR on `feat/codex-merge-automation` after this plan is merged.
Scope: `contract_master/`, `tests/`, `config/registry.json`, the
docs above. Maximum two implementation attempts.

## Verification

- `python3 -m unittest discover -s tests -v` passes, including the new suites and
  the 120-column style test.
- `python3 -m contract_master doctor` lists the new App blockers until configured.
- `python3 -m contract_master codex-merge TASK TOKEN` (dry run) prints the intended
  calls for a simulated task and makes no network request.
