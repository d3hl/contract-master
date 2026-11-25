# Plan: safely upgrade Orca on NTNSG-RH3 and NTNSG-RH1 (app, skills, orchestrator)

Status: proposed (2026-11-25). Planning only. Nothing in this document has been run
except the read-only checks listed under "Observed state". No live worker, restart,
install or merge happens until the operator starts Phase 1.

> **For agentic workers:** this plan needs `sudo` and service restarts on RH1, which
> sandboxed DeepSeek workers cannot do (`NoNewPrivileges`, see [worker host](../operations/worker-host.md)).
> A human operator runs Phases 0-5. Codex verifies the evidence and the Phase 6 docs
> PR. Claude confirms completion. Use `superpowers:executing-plans` for the checkboxes.

**Goal:** Both hosts run one matching, verified Orca build, with matching skills and
orchestrator guidance, without losing worker ownership or the manager database.

**Approach:** Freeze the coordinator, back up, upgrade the worker host (RH1) first as the
canary, prove it with a probe Dispatch, then upgrade the coordinator host (RH3), then
refresh skills and orchestrator docs, then unfreeze. Every phase has a gate and a
rollback.

**Spec:** [Orca coordination and recovery](../operations/orca.md),
[worker host](../operations/worker-host.md), [pilot gates](../operations/pilot.md).

## Global Constraints

- Orca is the only scheduler. Do not add cron, a second automation or a poller.
- Unknown worker ownership is preserved across interruption. Never stop, abandon or
  release a worker without positive exit evidence (orca.md, "Interruption").
- Maximum two implementation attempts per task. An upgrade never resets a counter.
- Secrets stay in 1Password. Never print a pairing code; pipe it straight into
  `orca environment add` (worker-host.md, "Re-pair").
- Never use the bare GNOME `orca`. Resolve the executable per orca.md
  (`ORCA_CLI_COMMAND`, else `orca-dev`, else `orca-ide`). On these hosts the shim is
  `/home/d3/.config/orca/cli/bin/orca`.
- Bash/zsh on Linux only. No Windows steps.

## Observed state (read-only, 2026-11-25)

| Item | RH3 (`ntnsg-rh3`, coordinator) | RH1 (`NTNSG-RH1`, worker host) |
|---|---|---|
| CLI / app on disk | `orca --version` = **1.4.274** (was 1.4.271 earlier today) | `/opt/contract-master-worker/orca-app` = **1.4.274**, replaced 2026-11-25 18:22 |
| Previous app | n/a | `orca-app.before-1.4.274` (the 2026-10-29 build) is the rollback copy |
| Running server | app pid 1535424 up; `desktopWindowStatus: blocked`, browser provider degraded | `d3-worker-orca` and `cm-worker-orca` both active since 2026-11-25 18:37:41 (same boot) |
| Server artifacts | `~/.config/orca/orcad-artifacts/linux-x64-glibc` refreshed 2026-11-25 18:20 | `~/.orca-serve/orcad-artifacts` holds **two** builds: `0.1.0+befec5392488` (old, documented) and `0.1.0+6a25fd26e384` |
| Automation `c0e63d16-…` | **live: disabled**; `config/orca-automation.json` says `enabled: true` | n/a |
| Worker env `rh1-d3` | saved, endpoint `ws://127.0.0.1:6792` | listening on 127.0.0.1:6792 |

Meaning: the binaries appear to be swapped already, so this is a **verify, reconcile and
finish** procedure, not a clean install. Phase 0 (run 2026-11-26) settled the unknowns:
(a) a systemd drop-in already overrides `d3-worker-orca`'s `ExecStart` to orcad
`0.1.0+6a25fd26e384`, and pid 1151 runs it, so Steps 2.2 and 2.3 are only a
confirmation; (b) the RH3 app process (pid 1535424, started 2026-11-25 18:20:33)
matches the on-disk build, so Step 3.1 needs no restart; (c) the automation was last run
2026-11-25 17:39 SGT and is disabled; the owner still has to say whether that was
deliberate (Step 0.4).

## Review Focus

- `cm-worker-orca` shares `/opt/contract-master-worker` with `d3-worker-orca`: the new
  app dir affects both. Expect it to need the same restart, or be retired.
- Version skew between the RH3 coordinator CLI and the RH1 server: expect an RPC or
  help-flag mismatch (the 1.4.235 → 1.4.240 `linear issue` change is the precedent).
- The sandbox tmpfs on RH1 is wiped on restart: expect lost `~/.claude`/`~/.orca` hooks
  inside the sandbox, but `~/worker` and `~/.orca-serve` must survive.
- A restart during a live Dispatch: expect an unverifiable worker, not an exited one.
- `--force` on `orca skills update` moves skill copies aside: expect a backup folder, and
  expect extra-file copies to be skipped without it.

## Phase 0: Baseline, freeze and back up (read-only until Step 0.5)

- [ ] **Step 0.1: Record versions.** On RH3 run `orca --version`, `orca status --json`,
  and compare the app process start time with the on-disk build time:
  `ps -o lstart= -p "$(pgrep -f 'orca-ide' | head -1)"` vs
  `ls -ld --time-style=full-iso ~/.config/orca/orcad-artifacts/linux-x64-glibc`.
  Expected: versions written into the evidence file. If the process is older than the
  build, RH3 still runs the old app in memory.
- [ ] **Step 0.2: Record RH1.** `ssh rh1-worker 'systemctl cat d3-worker-orca | grep -A3 ExecStart; ls ~/.orca-serve/orcad-artifacts/linux-x64-glibc; /opt/contract-master-worker/orca-app/orca-ide --version'`.
  Expected: which orcad build `ExecStart` uses and the app version. Decide from this
  whether Phase 2 is needed at all.
- [ ] **Step 0.3: Read the release notes.** For 1.4.271 → 1.4.274 (and 1.4.243 → 1.4.274
  for the worker server), list changes to `orchestration`, `worker-start`,
  `environment`, `linear` and `skills`. Re-read the installed guides:
  `orca skills get orchestration --json`, and its `coordinator-loop.md` and
  `placement-and-remote.md` references (orca.md says to re-read after upgrades).
- [ ] **Step 0.4: Explain the disabled automation.** `orca automations list` shows
  `c0e63d16-…` disabled. Ask the owner whether that was deliberate. If it was not, it is
  the reason runs stopped, not the upgrade. Record the answer. Do **not** enable it
  yet; Phase 5 does that.
- [ ] **Step 0.5: Freeze.** (a) `python3 -m contract_master turn-check` exits 0, so no
  turn holds the lease. (b) `orca automations runs --id c0e63d16-c147-40b2-bb1b-5698891f2ff0 --limit 20 --json`
  shows no `dispatched` run. (c) For every recorded Run, `orca orchestration worker-list --run <RUN> --include-remote --json`
  shows only settled or released Dispatches; any unknown one **stops the plan** and is
  handled by the orca.md interruption procedure. (d) Keep the automation disabled.
- [ ] **Step 0.6: Back up.** With the coordinator quiescent, take a SQLite online backup
  of the manager database (path from the manager config) plus `.state/`, bundles and
  preserved workspaces together (orca.md, "Durable authority"). On RH1, stop nothing yet;
  confirm `orca-app.before-1.4.274` exists, and plan `tar` of `~/.orca-serve` for
  Step 2.1 (taken with the service stopped).
- [ ] **Gate 0:** versions recorded, freeze proven, backups verified with
  `sqlite3 <backup> 'PRAGMA integrity_check;'` returning `ok`. Otherwise stop.

## Phase 1: Decide the cm-worker fallback

- [x] **Step 1.1: Decision (owner, 2026-11-26): retire `cm-worker-orca`.** It shares
  the app directory, so retiring removes a second server to upgrade and verify.
- [x] **Step 1.2: Stop and disable the service** (done 2026-11-26, after Gate 0):
  `sudo systemctl disable --now cm-worker-orca`. Expected: `inactive` / `disabled`, port
  6791 closed, `d3-worker-orca` still `active`. Rollback: `sudo systemctl enable --now cm-worker-orca`.
- [ ] **Step 1.3: Remove the account** (not done; needs a separate owner go-ahead
  because it is irreversible): `sudo userdel -r cm-worker`. First reconcile the manager
  `ownership` rows (HANDOFF: preserved, "reconcile before any cleanup") and keep
  `/opt/contract-master-worker`, which `d3-worker-orca` still uses. Tarball
  `/home/cm-worker` before deleting it.

## Phase 2: Upgrade the worker host RH1 (canary)

- [ ] **Step 2.1: Stop and snapshot.** `sudo systemctl stop d3-worker-orca` (and
  `cm-worker-orca` if kept). `tar -C ~ -czf ~/orca-serve-pre-1.4.274.tgz .orca-serve`.
  Expected: units inactive, tarball non-empty.
- [ ] **Step 2.2: Refresh the orcad artifacts as `d3`.** Run the selection entry from
  worker-host.md:
  `ELECTRON_RUN_AS_NODE=1 /opt/contract-master-worker/orca-app/orca-ide /opt/contract-master-worker/orca-app/resources/app.asar/out/main/orcad/orcad-local-serve-selection-entry.js --user-data ~/.orca-serve --app-root /opt/contract-master-worker/orca-app/resources/app.asar`.
  Expected: it selects `0.1.0+6a25fd26e384` or newer.
- [ ] **Step 2.3: Point the unit at the new build.** Edit `ExecStart` in
  `/etc/systemd/system/d3-worker-orca.service` to the new artifact path only; keep
  every sandbox line (`ProtectHome=tmpfs`, `TemporaryFileSystem=/home/d3`,
  `NoNewPrivileges`, empty `CapabilityBoundingSet`, `InaccessiblePaths=/run/docker.sock`,
  `ProtectSystem=strict`). `sudo systemctl daemon-reload && sudo systemctl start d3-worker-orca`.
  Expected: `systemctl is-active d3-worker-orca` prints `active`.
- [ ] **Step 2.4: Re-check isolation.** From RH1 run
  `sudo nsenter -t $(systemctl show -p MainPID --value d3-worker-orca) -m ls /home/d3`
  and expect only `worker` and `.orca-serve`; `sudo -n true` inside must be refused.
- [ ] **Step 2.5: Reconnect from RH3.** `XDG_RUNTIME_DIR=/run/user/$(id -u) systemctl --user is-active rh1-d3-tunnel`
  prints `active`; `orca status --environment rh1-d3` shows `runtimeReachable: true`. If
  pairing was lost, re-pair exactly as worker-host.md describes, never echoing the code.
- [ ] **Gate 2:** the server logs `orcad is bound to 127.0.0.1`, the repo ids on
  `rh1-d3` (contract-master, cf-mcp-gw, action1-dashboard, corp-integrated-dashboard,
  pve-orchenv) all list, and `~/worker` content is intact.
  **Rollback:** `sudo systemctl stop d3-worker-orca`, restore `ExecStart` to
  `0.1.0+befec5392488`, swap `orca-app` with `orca-app.before-1.4.274`, restore the
  `.orca-serve` tarball, start, and re-run Step 2.5.

## Phase 3: Upgrade the coordinator host RH3

- [ ] **Step 3.1:** Confirm `orca --version` prints **1.4.274** and the running app
  process is newer than the build (Step 0.1). If not, quit the Orca app on RH3 and
  reopen it so the running build matches the disk. Skipping this leaves a stale
  in-memory server (the 2026-10-29 outage came from a runtime mismatch).
- [ ] **Step 3.2:** `orca status --json` shows `runtimeReachable: true`,
  `graphState: ready`. Note `desktopWindowStatus: blocked` and the browser-provider
  warning; they are pre-existing (HANDOFF: direct browser access still works) and do not
  gate the upgrade, but record them so a regression is visible.
- [ ] **Step 3.3:** Run the repo tests: `python3 -m unittest discover -s tests -v`.
  Expected: all pass (83+ at last record).
- [ ] **Gate 3:** `python3 -m contract_master doctor` reports no blockers.
  **Rollback:** reinstall the previous Orca app build, reopen it, rerun
  `orca --version`. The shim at `~/.config/orca/cli/bin/orca` regenerates itself.

## Phase 4: Orca skills

- [ ] **Step 4.1: Dry run on RH3.** `orca skills update --all --dry-run --json`. Review
  the plan digest. Only skills already installed are touched; nothing is added.
- [ ] **Step 4.2: Apply selectively.** `orca skills update --skill orchestration --skill orca-cli --skill orca-linear --json`
  (add `--skill orca-per-workspace-env` and the rest only if the dry run lists them).
  A copy with extra files may be skipped. Use `--force` only after reading the skip
  list; it moves each replaced copy to `~/.agents/.orca-skill-backups`.
- [ ] **Step 4.3: Same dry run on RH1 as `d3`** (`ssh rh1-worker 'orca skills update --all --dry-run --json'`).
  Note the sandbox gets an empty `/home/d3`, so only real-account copies count.
- [ ] **Step 4.4: Confirm.** `orca skills get orchestration --json` returns the
  version matching 1.4.274 on both hosts. Skills from `Claude Code home` or the
  `Codex plugin cache` are not Orca-owned and are out of scope.
- [ ] **Gate 4:** both hosts report the same orchestration skill version; the
  backup folder is recorded if `--force` was used.

## Phase 5: Orchestrator update and acceptance

"Orchestrator" here means the Orca orchestration CLI/skill plus this repo's coordinator
flow (`docs/operations/coordinator-prompt.md`, the `worker_command` flags and the
`config/orca-automation.json` entry).

- [ ] **Step 5.1: Diff the flags.** Compare `orca orchestration --help`,
  `worker-start --help`, `run-create --help`, `task-create --help`, `check --help` and
  `worker-release --help` against what `worker_command` emits
  (`--environment rh1-d3 --from <mailbox> --agent opencode2 --setup skip`). Any renamed
  or removed flag is a defect to fix in Phase 6 before the automation runs.
- [ ] **Step 5.2: Probe Dispatch on `rh1-d3`** (pilot gate 3 recheck): run the runner
  probe in [runner verification](../operations/runner-verification.md). Expected: model
  `deepseek/deepseek-v4.1-flash-1017`, access to coordinator credentials blocked,
  worker released with no residual terminal.
- [ ] **Step 5.3: Linear completeness** (pilot gate 4, required after any Orca upgrade):
  rerun the read-only listing, cursor-paging and full-read check against the D3S
  project. Expected: counts match the previous record (6 issues at last check).
- [ ] **Step 5.4: Dry-run intake.** `python3 -m contract_master reconcile` (read/triage
  only). Expected: no `retry: true` issues, no writes.
- [ ] **Step 5.5: Unfreeze.** Only after Steps 5.1-5.4 pass and the owner agrees (Step
  0.4), enable the automation: `orca automations enable --id c0e63d16-c147-40b2-bb1b-5698891f2ff0`
  (confirm exact syntax with `orca automations --help`). Watch exactly one run finish.
- [ ] **Gate 5:** one scheduled run completes, takes and ends the turn lease, and
  leaves no `dispatched` run behind.

## Phase 6: Record it (reviewed PR, not a Linear task)

- [ ] **Step 6.1:** Update `docs/operations/orca.md` ("Verified against … rechecked on
  1.4.274 (2026-11-25)"), the Orca server row in `docs/operations/worker-host.md`, the
  automation `notes` in `config/orca-automation.json`, and a dated HANDOFF entry.
  Fix any flag change found in Step 5.1.
- [ ] **Step 6.2:** `python3 -m unittest discover -s tests -v` passes, then commit on a
  branch and open a PR. Codex verifies and merges; Claude confirms.

## Stop conditions

Stop and escalate to the owner, without retrying, if: a Dispatch is unverifiable
(Step 0.5c), a backup fails integrity check, isolation regresses (Step 2.4), the
probe leaks credentials, or any step needs a second attempt at the same change.

## Progress

| Phase | Status | Evidence |
|---|---|---|
| 0 Baseline, freeze, backup | **Gate 0 passed 2026-11-26** | RH3 1.4.274 (app matches disk); RH1 app 1.4.274, `d3-worker-orca` on orcad `6a25fd26e384`; `turn-check` free; `doctor` no blockers; no `dispatched` run; 0 workers on `rh1-d3`; 13 manager tasks, none active; backup `integrity_check` = `ok` in `~/backups/orca-upgrade-2026-11-26/` (database, rest of `.state`, automation config, repo head, automation list) |
| 1 cm-worker | Steps 1.1-1.2 done; 1.3 waits for owner | `cm-worker-orca` inactive and disabled; `d3-worker-orca` active; `rh1-d3` reachable |
| 2-6 | not started | Phase 0.3 (release notes) and 0.4 (automation answer) are still open |
