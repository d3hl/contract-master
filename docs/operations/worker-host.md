# DeepSeek worker host

Since 2026-11-03, DeepSeek/OpenCode workers run as Linux user **`d3`** on
**`NTNSG-RH1`** (RHEL 9.8). They use their own Orca server there, which the coordinator
pairs as saved environment **`rh1-d3`**. This replaces the `cm-worker` account
([previous setup](#previous-setup-cm-worker)).

The runner stays `enabled: false` until both preconditions below are met.

## Precondition 1: no coordinator secrets in `d3` on NTNSG-RH1

A worker can read everything its Linux user can read. Running as `d3` is safe only
when the `d3` account on NTNSG-RH1 holds none of the coordinator's secrets or state.
Before enabling the runner, confirm that none of these exist or can be read as `d3`
on NTNSG-RH1:

- the 1Password service-account token (`~/.config/op/contract-master-sa-token`)
  and any `op` session;
- a `gh` login (`~/.config/gh/hosts.yml`), GitHub App private keys or any token
  that can push, approve or merge;
- SSH private keys that grant push or access to other hosts;
- the manager database and outbox (`.state/` of the coordinator checkout);
- the coordinator's own Orca runtime data (`~/.orca`), its Linear access and the
  scheduled coordinator automation.

If the coordinator itself still runs as `d3` on NTNSG-RH1, this precondition is not
met. Move it to another host or account first. The worker keeps only its own
OpenRouter login for OpenCode. It clones the target repositories over public HTTPS
and never pushes; `open-pr` (d3hl-orca) pushes output commits from the coordinator
side.

## Precondition 2: probe on `rh1-d3`

Run one supervised probe through the flow below and record it in
[runner verification](runner-verification.md). The probe must show:

- `whoami` = `d3` on `NTNSG-RH1`;
- the session model is OpenRouter `deepseek/deepseek-v4.1-flash-1017`;
- every path in precondition 1 is missing or refused;
- an output commit that Codex verifies independently.

Then set `enabled: true` in `config/deepseek-runner.json`.

## Layout

| Item | Location |
|---|---|
| Worker user | `d3` on `NTNSG-RH1`, with no coordinator credentials (precondition 1) |
| `opencode` / `opencode2` on PATH | `~d3/.opencode/bin/` |
| Orca server data | `~d3/.orca-serve/` (separate from any `~/.orca` runtime) |
| Worker repo clones | `~d3/repos/<repo>`; register each in the `rh1-d3` server and record its Orca repo id here |
| Model pin | `~d3/.config/opencode/opencode.json` (OpenRouter `deepseek/deepseek-v4.1-flash-1017`) for repos without `.opencode/opencode.json` |
| Git identity | `contract-master DeepSeek worker <d3-worker@d3hl.invalid>` |
| Service | `d3-worker-orca.service` (systemd user or system unit, `User=d3`) |

## Orca server

Start orcad with `--bind 127.0.0.1` on a fixed port (for example `6791`), as the
`cm-worker` service did. `orca serve` binds `0.0.0.0` by default. Keep the systemd
hardening (`ProtectSystem=strict`, `NoNewPrivileges`). Write output to
`~d3/.orca-serve/serve.log` and delete the pairing lines once pairing is done.

If the coordinator runs on another host, reach the server through an SSH tunnel to
`127.0.0.1:<port>` on NTNSG-RH1. Do not expose the port on the LAN. As of
2026-11-03, `ntnsg-rh3` cannot resolve `NTNSG-RH1`. Add a DNS or SSH config entry
before pairing from there.

## Coordinator connection

The coordinator pairs the server as saved environment **`rh1-d3`**
(`orca environment add --name rh1-d3 --pairing-code …`, without printing the code).
Its runtime rejects `worker-start --on` (`server_required`), so it addresses the
worker server directly:

1. `terminal create --environment rh1-d3 --worktree <repo root id>` → a plain
   mailbox terminal handle.
2. `orchestration run-create --environment rh1-d3 --from <mailbox>`.
3. `orchestration worker-start --environment rh1-d3 --from <mailbox> --run <run>
   --worktree new-top-level --repo id:<worker repo> --agent opencode2 --setup skip`.
4. `orchestration check --environment rh1-d3 --terminal <mailbox> --wait`, then
   ack, `worker-release --environment rh1-d3 --dispatch <id>`.

The Orca Run and mailbox live on the worker's server, which the worker can write.
Orca messages are hints only. The manager database stays authoritative on the
coordinator side, and Codex verifies the actual output commit independently. Treat
every `worker_done` as an unverified claim.

## Rebuild or remove

- Re-pair: restart the service, read the new `Pairing URL` from `serve.log`
  without printing it, `orca environment add --name rh1-d3 --pairing-code …`,
  then delete the pairing lines from the log.
- Remove: stop and disable `d3-worker-orca`, `orca environment rm --environment
  rh1-d3`, remove `~d3/.orca-serve` and `~d3/repos`.

## Previous setup: `cm-worker`

From 2026-10-29 to 2026-11-03, workers ran as the locked-down user `cm-worker` on
NTNSG-RH1. The account could not read `/home/d3` at all. It had its own Orca server
on `127.0.0.1:6791` (`cm-worker-orca.service`, binaries under
`/opt/contract-master-worker`) and was paired as environment `cm-worker`.
Evidence is in [runner verification](runner-verification.md). To remove it:
`systemctl disable --now cm-worker-orca`, `orca environment rm --environment
cm-worker`, `userdel -r cm-worker`, `rm -rf /opt/contract-master-worker`.
