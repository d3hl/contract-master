# Isolated DeepSeek worker host

Set up 2026-10-29 on `NTNSG-RH1` (RHEL 9.8) for pilot gate 3. DeepSeek/OpenCode
workers run as a separate Linux user, `cm-worker`, on their own Orca server, so
they cannot read the coordinator's credentials or state.

## What the worker cannot reach

The coordinator account (`d3`) keeps its home at `0700`. As `cm-worker` these are
all refused (checked from a shell and again from inside a live OpenCode worker):

- `/home/d3` and everything below it, including
  `~/.config/op/contract-master-sa-token` (1Password service account → GitHub App
  keys), `~/.config/gh/hosts.yml`, `~/.ssh`, `~/.orca` and the manager database
  under `.state/`.
- `sudo` (password required; the account's password is locked).
- 1Password and GitHub: no `op` account and no `gh` login exist for `cm-worker`.

The worker has its own OpenRouter login for OpenCode only, stored in its private
home. It clones the public `d3hl/contract-master`, `d3-corp/cf-mcp-gw` and
`d3-corp/action1-dashboard` over HTTPS and never pushes;
`open-pr` (d3hl-orca) pushes output commits from the coordinator side.

## Layout

| Item | Location |
|---|---|
| Worker user | `cm-worker` (no sudo, password locked, SSH key `d3SSH-10-2026` only) |
| OpenCode 2.1.4 binary | `/opt/contract-master-worker/bin/opencode` (root-owned, read-only) |
| `opencode` / `opencode2` on PATH | `~cm-worker/.opencode/bin/` (symlink and the same 2-line shim as `d3`) |
| Orca app 1.4.243 (AppImage, SHA-512 checked against `latest-linux.yml`) | `/opt/contract-master-worker/orca-app/` (root-owned, read-only) |
| Orca server data | `~cm-worker/.orca-serve/` |
| Worker repo clone | `~cm-worker/repos/contract-master` (Orca repo `ddd5af7e-…`) |
| Target repo clones | `~cm-worker/repos/cf-mcp-gw` (`a848e871-…`), `~cm-worker/repos/action1-dashboard` (`e6dcfb9d-…`); public HTTPS fetch |
| Model pin | `~cm-worker/.config/opencode/opencode.json` (OpenRouter `deepseek/deepseek-v4.1-flash-1017`) for repos without `.opencode/opencode.json` |
| Git identity | `contract-master DeepSeek worker <cm-worker@d3hl.invalid>` |
| Service | `cm-worker-orca.service` (systemd, enabled) |

## Orca server

`orca serve` cannot run from the SSH-managed CLI and always binds `0.0.0.0`
(firewalld is not running here). The service therefore starts the same orcad that
`serve` selects, directly, with `--bind 127.0.0.1 --port 6791`. Its sandbox hides
`/home` except `/home/cm-worker` (`ProtectHome=tmpfs` + `BindPaths`), makes the
system read-only (`ProtectSystem=strict`) and sets `NoNewPrivileges`. Output goes
to `~cm-worker/.orca-serve/serve.log`; pairing lines are deleted after pairing.

The orcad path inside `~/.orca-serve/orcad-artifacts/` is version-pinned. After
an Orca upgrade, re-run the selection entry as `cm-worker` and update `ExecStart`:

```
ELECTRON_RUN_AS_NODE=1 /opt/contract-master-worker/orca-app/orca-ide \
  /opt/contract-master-worker/orca-app/resources/app.asar/out/main/orcad/orcad-local-serve-selection-entry.js \
  --user-data ~/.orca-serve --app-root /opt/contract-master-worker/orca-app/resources/app.asar
```

## Coordinator connection

The coordinator's Orca runtime pairs with this server as saved environment
**`cm-worker`** (`ws://127.0.0.1:6791`). That runtime is itself SSH-managed and
rejects `worker-start --on` (`server_required`), so the coordinator addresses the
worker server directly with `--environment cm-worker`:

1. `terminal create --environment cm-worker --worktree <repo root id>` → a plain
   mailbox terminal handle.
2. `orchestration run-create --environment cm-worker --from <mailbox>`.
3. `orchestration worker-start --environment cm-worker --from <mailbox> --run <run>
   --worktree new-top-level --repo id:<worker repo> --agent opencode2 --setup skip`.
4. `orchestration check --environment cm-worker --terminal <mailbox> --wait`, then
   ack, `worker-release --environment cm-worker --dispatch <id>`.

The Orca Run and mailbox therefore live on the worker's server, which `cm-worker`
can write. That is acceptable because Orca messages are hints: the manager
database (coordinator-only) stays authoritative, and Codex verifies the actual
output commit independently. Treat every `worker_done` as an unverified claim.

## Rebuild or remove

- Re-pair: restart the service, read the new `Pairing URL` from `serve.log`
  without printing it, `orca environment add --name cm-worker --pairing-code …`,
  then delete the pairing lines from the log.
- Remove: `systemctl disable --now cm-worker-orca`, `orca environment rm
  --environment cm-worker`, `userdel -r cm-worker`, `rm -rf /opt/contract-master-worker`.
