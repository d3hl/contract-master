# HANDOFF — pilot gate 8 passed

- Issue: [D3S-101](https://linear.app/d3space/issue/D3S-101), parent D3S-98.
- Phase: inspection and verification complete; In Review. No Done transition.
- Owner: human reviews evidence and remediation scope; Codex confirms resulting gates.
- Workspace: manager `main` at `e5d69e4` (PR #8 runner probe, PR #9 D3S-99 review
  and PR #11 manager fixes merged); the documentation/config changes are committed.
- Runner: OpenCode 2.1.4 / Orca `opencode2`, actual OpenRouter
  `deepseek/deepseek-v4.1-flash-1017`. Probe commit
  `f381bb8126a25ba0e7c90420372ed7ea8afbd101` from `d3adc3II/deepseek-runner-probe`
  is now on `main` via PR #8 (`aa1976a`); only its fixture module changed.
  Independent 7 fixture + 38 repository tests and portable result/read proof passed.
  [Runner evidence](runner-verification.md). The worker was released and delivery acked.
- Audit: [gate PASSES as of 2026-10-29](linear-status-audit.md). The admin set
  every D3S PR event (including merge) to No action and disabled parent auto-close
  and stale cancellation; `merge_gate_audited=true`. The 2026-10-25 inspection
  captures remain under `.state/linear-audit/`.
- Auto-archive closed items: 6 months. No branch overrides.
- Integration checks: commit linking off; GitHub issue sync has no repositories;
  GitLab not enabled; Loops unavailable on the current plan (paid-plan gate shown).
- Access correction: direct Orca browser access worked despite the runtime's
  `browser_unavailable` diagnostic. Actual settings replaced the earlier access
  blocker. User-supplied rule values are no longer required for this inspection.
- Runner isolation (gate 3) done 2026-10-29: DeepSeek workers run as Linux user
  `cm-worker` on a localhost-only Orca server (environment `cm-worker`,
  [worker host](worker-host.md)); probe Dispatch `ctx_ac7cba883d03` confirmed model
  `deepseek/deepseek-v4.1-flash-1017` and blocked access to coordinator credentials.
- Gate 4 rechecked 2026-10-29 on Orca 1.4.243: listing, cursor paging and full-read
  completeness pass (6 issues, read-only). Relation direction not re-observed: no
  live blocking relation exists in D3S; unknown shapes fail closed.
- Coordinator flow: runner `environment: cm-worker`; `worker_command` adds
  `--environment cm-worker --from <mailbox>`; coordinator prompt and Orca doc use
  that flow instead of `--on`. (The `environment` line was lost when #25 was merged
  after #24 and is restored here.)
- Gate 7 (2026-10-29): reviewed master `b590eb4` pinned (bundle `84ca586b…80fad8`),
  `automation_enabled=true`; the former delivery-only automation `dc0657b8-…` is now
  the single coordinator schedule (agent `claude`, every 10 minutes, precheck: clean
  `main` and no `doctor` blockers). Intake no longer comments on settled issues.
- Configuration: production runner `enabled=true`, automation enabled.
  Reviewed master `26e14a8` pinned (bundle digest `9ac1eae1…c5b7eb`). No external rule,
  credential, historical issue or deployment was changed. PRs #8 and #9 were
  merged on GitHub by account `d3adc3ii`; that is not recorded human-review evidence.
- Code changes merged via PR #11 (`e5d69e4`, outside D3S-101) by `d3adc3II` with
  no recorded GitHub approval; CI passed on Python 3.9 and 3.13. Rework can no longer skip dispatch via `observe-head`; provider
  read failures no longer post triage comments or fence tasks; phase rules live in
  `contract_master/phases.py`; schema validation rejects unsupported keywords and
  is cross-checked with `jsonschema` in CI. 57 tests pass.
- Role change (planned in PR #13, `45b78f3`): Claude plans and decides completion,
  Codex verifies, reviews and merges, humans handle escalations. The v1 `plan`,
  `task` and `completion` schemas were edited in place (`author: claude`;
  `reviewer`/`merger` replace `human_reviewer`/`human_merger`) because nothing is
  live. The merge gate now needs a registered Codex `merge_identity`, which is
  `null` until the pilot creates that GitHub identity. 63 tests pass.
- Codex merge automation (plan PR #20): `open-pr` and `codex-merge` manager commands,
  `contract_master/github_app.py` (App tokens from 1Password, narrowed per step) and
  the `github_apps` registry block. Dry run by default; `--live` stays gated. The
  live test passed 2026-10-29 in `d3hl/sandbox` PR #1: opened by `d3hl-orca[bot]`,
  checked, approved and merged by `d3hl-codex[bot]`; rerun made no duplicate writes.
  Registry now records both Apps; their keys are in the dedicated 1Password vault
  `contract-master`, the only vault the service account can read; a second live
  run with those keys (`d3hl/sandbox` PR #2) also passed. `contract-master` stays on
  phase A branch protection; phase B applies to onboarded target repos. 83 tests pass.
- Gate 8 **passed** (2026-10-30). [D3S-114](https://linear.app/d3space/issue/D3S-114)
  is Done (2026-10-29): planned, implemented by DeepSeek (`cd7486f`, Dispatch
  `ctx_56bf0be2af03`), PR #29 opened by `d3hl-orca[bot]`, verified, approved and
  merged by `d3hl-codex[bot]` as `a6bccb7`, confirmed by Claude. Scenarios 01 and 05
  observed live. [D3S-115](https://linear.app/d3space/issue/D3S-115) is Done
  (2026-10-30, manual run 132): DeepSeek `f5540e6` (Dispatch `ctx_1e04d27edf3a`),
  Codex pass, PR #32 merged by `d3hl-codex[bot]` as `9b3e141`, Claude reran the
  checks on the merged commit. All ten scenarios are recorded in
  [failure-scenarios.md](../knowledge/failure-scenarios.md).
- D3S-115 was closed by hand at 18:05 UTC on 2026-10-29 without a manager task, then
  reopened. Intake meanwhile queued `TRIAGE: Issue is closed` for it; the owner chose
  to send it in order. Fixed: intake no longer comments on closed issues.
- Dispatch quirks (documented in the coordinator prompt and Orca doc): `worker-start`
  left the OpenCode prompt pasted but unsubmitted (send exactly one Enter); `codex
  exec` needs stdin closed (`< /dev/null`).
- Overlapping runs: Orca started run 106 while 105 was still active, and scheduled
  runs 133 and 134 alongside manual run 132 (Orca marks manual runs `completed`
  while they work). Fixed: every turn holds the manager's turn lease and the
  precheck ends with `turn-check`.
- Coordinator outage (2026-10-29 22:10 to 2026-10-30 01:50 SGT, runs 109–131): the
  automation's agent had been switched from `claude` to Codex. Inside Codex's
  sandbox the Orca runtime was unreachable (`runtime_open_failed`), so every turn
  stopped before intake. No provider writes; outbox all delivered. Per-turn notes
  are in the local `.state/coordinator-turn-HANDOFF.md`. The owner set the agent
  back to `claude` and re-enabled it (2026-10-30).
- Ownership rows for D3S-114 and D3S-115 still exist in the manager database
  (both tasks done). They are preserved; reconcile before any cleanup.
- Turn lease is live: the automation precheck ends with `turn-check` (2026-10-30).
- D3S-113 closed as Done by hand (delivered by PR #21). D3S-109 (onboard
  `d3-corp/cf-mcp-gw` and `d3-corp/action1-dashboard`) is done in reviewed PRs,
  not by the coordinator. Step 1, label routing, merged (#35). Step 2: Apps
  installed on `d3-corp` (installations 176676496 orca, 176676979 codex; both reach
  both repos), Linear projects Cloudflare MCP Gateway and Action1 Dashboard, repos
  made public and on phase A protection, worker clones and Orca repos registered,
  checks verified on `main`, target `AGENTS.md` PRs (cf-mcp-gw #6,
  action1-dashboard #1), registry entries in this change.
- D3S-109 step 2 complete: target `AGENTS.md` PRs (cf-mcp-gw #6, action1-dashboard
  #1) and registry change #36 merged. DeepSeek runner probes passed on both
  repositories (2026-10-30, [runner verification](runner-verification.md)).
- D3S-109 step 3 complete (2026-10-30, one coordinator turn): first docs pilot per
  repository, both Done. [D3S-116](https://linear.app/d3space/issue/D3S-116)
  (cf-mcp-gw README and onboarding note): DeepSeek `d860e29` (Dispatch
  `ctx_e480b8dbba58`), Codex pass, PR #7 opened by `d3hl-orca[bot]` and merged by
  `d3hl-codex[bot]` as `91806ff`. [D3S-117](https://linear.app/d3space/issue/D3S-117)
  (action1-dashboard README section): DeepSeek `7e6c229` (Dispatch
  `ctx_ec8d7f6f02f8`), Codex pass, PR #2 merged by `d3hl-codex[bot]` as `d6abcc5`.
  Claude found each merged tree identical to the verified commit and reran the
  registered checks on it. One attempt each, no rework.
- Phase B protection applied to `main` of both repositories at the owner's request
  (2026-10-30): required `codex-verification` from App 5511451, push only
  `d3hl-codex`, `enforce_admins` on; PR still required (0 approvals, since
  `codex-merge` checks the Codex approval). Phase A settings are saved under
  `.state/branch-protection/` for rollback.
- Observed in D3S-117: the worker's first `worker_done` used a mistyped task ID and
  Orca rejected it; its resend settled the Dispatch. The worker's
  `~cm-worker/repos/contract-master` checkout was stale (`c92b334`, registry without
  `b590eb4`), so `bundle` refused there; it used an existing bundle whose digest
  matched. Neither prompt needed the extra Enter. That checkout was fast-forwarded
  to `87af868` on 2026-10-30.
- D3S-109 closed as Done (2026-10-30, owner decision): every step and acceptance
  criterion was met, so no child issues were needed.
- 2026-11-01: Governance PR review path implemented by DeepSeek on `cm-worker`
  (`contract_master/governance.py`, `review-*` commands, `pr_reviews`, two schemas,
  the enabled `governance_review` block and tests/docs); verification pending. PR
  #56 is unchanged.
- 2026-11-01: `d3-corp/corp-integrated-dashboard` onboarding started (no Linear
  issue; tracked in project Corp Integrated Dashboard `90d27bb0-…`, label
  `repo:corp-integrated-dashboard`). The repo held a real Action1 tenant snapshot
  while briefly public; `src/data/raw.ts` was replaced with fictional Contoso data
  and history rewritten (`a2e27c1` → `d6f76be`). GitHub may still serve the old
  SHAs until Support purges them. Then: public again, phase A protection (saved in
  `.state/branch-protection/`), both Apps mint narrowed tokens for it,
  `typecheck`/`build` pass on `d6f76be`, worker clone
  `~cm-worker/repos/corp-integrated-dashboard` (`57907de9-…`), target `AGENTS.md`
  PR (corp-integrated-dashboard #1), registry entry in this change.
- Exact next action: merge corp-integrated-dashboard #1, then this registry change;
  then the DeepSeek runner probe and one bounded docs pilot issue for it, then
  phase B after its first `codex-merge`. Other work for the registered
  repositories arrives as ordinary issues in their own Linear projects; widening
  scope beyond docs is a reviewed registry change.
- Local recovery: `.state/linear-audit/HANDOFF.md`, evidence manifest, settings
  screenshots and manager outbox preserve the result through Linear outages.
