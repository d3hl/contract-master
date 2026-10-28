# HANDOFF — runner verified; Linear audit complete with findings

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
- Configuration: production runner `enabled=true`, automation disabled.
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
- Exact next action: limit other GitHub apps' access to `d3hl/contract-master`
  and confirm the 1Password item holds the `d3hl-codex` App private key (gate 6);
  then pin a reviewed master commit and prepare the DeepSeek runner. Do not
  activate production from the successful runner probe.
- Local recovery: `.state/linear-audit/HANDOFF.md`, evidence manifest, settings
  screenshots and manager outbox preserve the result through Linear outages.
