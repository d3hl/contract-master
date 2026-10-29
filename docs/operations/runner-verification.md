# DeepSeek runner capability verification

Verified 2026-10-25 for [D3S-101](https://linear.app/d3space/issue/D3S-101).
**Verdict: real coding capabilities passed; production runner remains disabled.**

## Actual client and model

- User's “onecode” request was interpreted as installed OpenCode.
- Installed CLI: OpenCode **2.1.4**; Orca client adapter: **opencode2**.
- Provider/model observed in the actual provider session: OpenRouter,
  `deepseek/deepseek-v4.1-flash-1017`, variant `default`.
- Provider session: `ses_e8e6cdec7ffes1aTO1bK7tC0xE`.
- Reported provider cost: approximately **US$0.0074** for this fixture.
- Existing client authentication was used without reading/printing credential
  values or provisioning credentials. Its 1Password provenance was not verified.

Model identity was read from the exported session's top-level and assistant
message metadata. It was not inferred from requested launch arguments. Only the
allowlisted provenance fields are retained in `.state/runner-verification/model-evidence.json`.

## Capabilities and independent evidence

| Capability | Evidence |
|---|---|
| File reading | Task context digest matched; a fresh read-proof value from coordinator-owned context was returned |
| File editing | Actual diff changed only `runner_probe/tags.py`; frozen tests/context stayed unchanged |
| Shell/tests | Coordinator independently reran all **7 probe tests** and **38 repository tests** at the output commit; both passed |
| Git | Worker made local commit `f381bb8126a25ba0e7c90420372ed7ea8afbd101`; clean checkout and exact SHA verified |
| Structured result | Implementation-result v1 schema passed; task/attempt/plan/context/commit/read-proof bindings matched |
| Orca lifecycle | Accepted succeeded report for the expected Task/Dispatch; terminal released; delivery acknowledged; no reclaimable resources remain |

The fixture baseline was `d252d09b70eb7b915e2663469d6cb05fb778cd7f`. It deliberately failed before
implementation. The worker implemented list/string validation, whitespace
stripping, Unicode casefolding, blank-tag rejection and order-preserving duplicate
removal without mutating input. Codex reviewed the actual diff and independently
ran the frozen tests rather than accepting the worker's claimed outcomes.

## Durable identities

- Run: `run_54bf354da2ce`
- Orca Task: `task_f70a6e004df3`
- Dispatch: `ctx_80f2fb7aee5a`
- Accepted launch request: `0d9e5b75-dfa5-4fa3-abb7-422edc95b509`
- Portable probe task: `D3S-101-runner-probe`
- Output commit: `f381bb8126a25ba0e7c90420372ed7ea8afbd101`

Preserved artifacts under `.state/runner-verification/` include launch, completion,
release and acknowledgment receipts, the baseline log, result JSON, independent
verification, model metadata and the task plan. The isolated Orca child worktree
and branch were preserved for review and later merged to `main` through PR #8
(`aa1976a`).

## Installed-version launch behavior

Orca **1.4.235** refuses `opencode2 --model` before creating a Task/worker. Its
`opencode --model` path also refuses this installed V2 CLI as unsupported. Both
preflight refusals were inspected; neither created a Task or Dispatch.

The successful path pins the model in the isolated worktree's
`.opencode/opencode.json`, then invokes `worker-start --agent opencode2` **without**
`--model`. [Project configuration template](../../config/deepseek-opencode-project.json)
contains only the model setting and no credentials. Do not change a user's global
model default. Configure the target workspace before dispatch and recheck actual
session model metadata; a launch receipt with `model: null` is not model proof.

Context7 ID `/anomalyco/opencode` was resolved first, then version `v2.1.2` docs
were queried (installed patch 2.1.4 was unavailable). The local CLI help and actual
run established compatibility. Primary sources: [model selection](https://github.com/anomalyco/opencode/blob/v2.1.2/services/www/src/docs/content/models.mdx)
and [project config](https://github.com/anomalyco/opencode/blob/v2.1.2/services/www/src/docs/content/config.mdx).

## Isolated worker run (2026-10-29)

Production isolation is in place: OpenCode runs as Linux user `cm-worker` on its own
Orca server bound to `127.0.0.1:6791`, paired to the coordinator as environment
`cm-worker` ([setup](worker-host.md)). One supervised probe ran there:

- Run `run_920486eba1c1` on the worker server; Task `task_bb472d0c607f`. The first
  Dispatch `ctx_603e2243be03` failed at `agent_readiness` because `cm-worker` lacked
  the `opencode2` shim; after adding it, `--retry-of` Dispatch `ctx_ac7cba883d03`
  reported `succeeded`, was acknowledged and released.
- **Model:** the exported OpenCode session `ses_e7b1eeae9ffe0jvfa3IMw5wjDH` records
  provider `openrouter`, model `deepseek/deepseek-v4.1-flash-1017`, variant `default`
  on all 7 model records. Reported cost about US$0.003.
- **Isolation:** from inside the agent, `whoami` = `cm-worker`, `HOME` =
  `/home/cm-worker`; `/home/d3`, the 1Password service account token, the `gh`
  login and the manager database were all `blocked`. A separate shell check as
  `cm-worker` also blocked `~/.orca` and `~/.ssh`, and found no `sudo`, `op` or `gh`
  access.
- **Edit/Git:** commit `7acb8fb597c080d95ab2cd29160ba3c637c49568` adds only
  `runner_probe/isolation-probe.md`, authored by the worker identity, with a clean
  tree, verified by the coordinator rather than taken from the report. It was not
  pushed.

`config/deepseek-runner.json` is now `enabled: true`. Live dispatch still needs
`automation_enabled` (pilot gate 7).

## Scope and remaining gates

This is a user-authorized **capability probe**, not the registered production
pilot. No master review approval or production eligibility is asserted. The
fixture plan was read-only at the file-permission level; this was an isolated Git
worktree, not an OS sandbox. Read-only mounts/writable-path restrictions and
approved 1Password references still require setup for production use.

`config/deepseek-runner.json` now records `mode: live`, verified capabilities and
`agent: opencode2`, while keeping `enabled: false`. Project automation remains
disabled; reviewed context is still unregistered; the
[Linear automation audit](linear-status-audit.md) is complete and fails because
the current rules permit PR-merge completion and automatic parent closure. No merge, deployment or project-wide activation occurred.
