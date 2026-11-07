# DeepSeek worker host

Since 2026-11-03, DeepSeek/OpenCode workers run as Linux user **`d3`** on
**`NTNSG-RH1`** (RHEL 9.8), on their own Orca server inside a systemd sandbox. The
coordinator runs on **`ntnsg-rh3`**. It reaches the server through an SSH tunnel and
pairs it as saved environment **`rh1-d3`**. This replaces the `cm-worker` account
([previous setup](#previous-setup-cm-worker)).

## Isolation

`d3` on RH1 is a full user account. It has passwordless `sudo`, belongs to the
`docker` group, and holds personal credentials (`gh` login, SSH keys, an API token in
`~/.zshrc`, a Claude Code login). Workers run as `d3` but cannot use any of that,
because the `d3-worker-orca` service, and every agent it starts, runs in a sandbox:

- `ProtectHome=tmpfs` plus `TemporaryFileSystem=/home/d3`: the worker's `/home/d3` is
  an empty private tmpfs. Only `~/.orca-serve` and `~/worker` are bind-mounted in.
  Every other home directory is hidden.
- `NoNewPrivileges` and an empty `CapabilityBoundingSet`, so `sudo` is refused.
- `InaccessiblePaths=/run/docker.sock`. The socket exists as a mode-000 placeholder
  and cannot be opened.
- `ProtectSystem=strict`: the system is read-only apart from the two bound folders.
- The `XDG_*` folders and `GIT_CONFIG_GLOBAL` point into `~/worker`, so the worker
  never reads `d3`'s personal OpenCode, git or shell configuration.

Anything created elsewhere under `/home/d3` inside the sandbox (for example Orca's
`~/.claude` agent hooks or `~/.orca`) lives in the tmpfs and is lost on restart.
Workers hold no GitHub credential and never push. `open-pr` (d3hl-orca) pushes
output commits from the coordinator.

Probe evidence: [runner verification](runner-verification.md#rh1-d3-probe-2026-11-03).

## Layout on NTNSG-RH1

| Item | Location |
|---|---|
| Service | `/etc/systemd/system/d3-worker-orca.service` (`User=d3`, enabled) |
| Orca server | orcad `0.1.0+befec5392488` (app 1.4.243), `ws://127.0.0.1:6792`, data in `~/.orca-serve/` |
| Log | `~/.orca-serve/serve.log` (owned by `d3`; pairing lines deleted after pairing) |
| OpenCode | verified v2.1.4: `~/worker/bin/opencode` → `/opt/contract-master-worker/bin/opencode`, plus the `opencode2` shim. Not `d3`'s own v2.2.5 |
| OpenCode config/data | `~/worker/config/opencode/opencode.json` (model `openrouter/deepseek/deepseek-v4.1-flash-1017`), `~/worker/data/opencode` (the worker's own OpenRouter credential) |
| Git identity | `~/worker/config/git/config`: `contract-master DeepSeek worker <d3-worker@d3hl.invalid>` |
| Repo clones | `~/worker/repos/<repo>`, public HTTPS, no credential helper |
| Worker worktrees | `~/worker/worktrees/<repo>/<name>` (each project's `worktreeBasePath`) |
| Pinned context | `~/worker/context/<digest>/` |

Orca repo ids on `rh1-d3`: contract-master `047231de-…`, cf-mcp-gw `1d201aa6-…`,
action1-dashboard `340ff8b0-…`, corp-integrated-dashboard `1501836a-…`,
pve-orchenv `d2492923-…` (added 2026-11-07 with `orca project setup-update
--worktree-base-path /home/d3/worker/worktrees`; `repo add` leaves it unset).

## Coordinator side (ntnsg-rh3)

| Item | Location |
|---|---|
| SSH alias | `rh1-worker` in `~/.ssh/config` → `d3@10.203.1.121`, key `~/.ssh/id_ed25519_rh1_worker`, host key alias `NTNSG-RH1` (ED25519 `SHA256:nb82cMH2…K004yOA`) |
| Tunnel | user unit `~/.config/systemd/user/rh1-d3-tunnel.service` (lingering): `127.0.0.1:6792` → RH1 `127.0.0.1:6792` |
| Orca environment | `rh1-d3` (`b0a564ff-…`) |

The SSH key lives only on RH3 and grants RH3 → RH1, never the reverse. The worker
cannot see `~/.ssh/authorized_keys` on RH1.

## Dispatch flow

Every orchestration command for an implementation attempt uses `--environment rh1-d3`.
The Run, Task and mailbox live on the worker server:

1. `terminal create --environment rh1-d3 --worktree id:<repo id>::/home/d3/worker/repos/<repo>`
   → a plain mailbox terminal handle.
2. `orchestration run-create --environment rh1-d3 --from <mailbox> --objective ...`.
3. Copy the pinned context in: `scp -r <context dir> rh1-worker:worker/context/`. The
   spec refers to `/home/d3/worker/context/...`.
4. `orchestration worker-start --environment rh1-d3 --from <mailbox> --run <run>
   --spec-file <spec> --worktree new-top-level --repo id:<repo id> --name <task>
   --agent opencode2 --setup skip --json`. Pass `--retry-request` only with a UUID
   Orca printed for the original request; it rejects made-up ids. Then read the
   worker (`worker-read --source auto`). If OpenCode shows the prompt pasted but not
   submitted, send exactly one Enter.
5. `orchestration check --environment rh1-d3 --terminal <mailbox> --wait`, then
   `worker-release --environment rh1-d3 --dispatch <id>`. This Orca version has no
   separate `ack`: `check` consumes the message.
6. Fetch the output commit as a bundle:
   `ssh rh1-worker "git -C ~/worker/worktrees/<repo>/<name> bundle create - <base>..HEAD" > out.bundle`
   after checking that the worktree `HEAD` is the reported commit (a bare SHA as the
   range end makes git refuse with "empty bundle"),
   then `git bundle verify` and `git fetch out.bundle` in the coordinator/Codex
   checkout.

Orca messages from that server are unverified claims. The manager database
(coordinator-only) stays authoritative, and Codex verifies the actual output commit
independently. To see what a worker really saw, inspect the sandbox from RH1:
`sudo nsenter -t $(systemctl show -p MainPID --value d3-worker-orca) -m <command>`.

## Rebuild or remove

- Restart: `sudo systemctl restart d3-worker-orca`. Sandbox tmpfs contents are lost;
  `~/worker` and `~/.orca-serve` persist.
- Re-pair: restart the service, then on RH3 read the new code over SSH straight into
  `orca environment add --name rh1-d3 --pairing-code …` without printing it. Delete
  the pairing lines from `serve.log`.
- After an Orca upgrade, re-run the selection entry as `d3` to refresh
  `~/.orca-serve/orcad-artifacts`, then update `ExecStart`:

  ```
  ELECTRON_RUN_AS_NODE=1 /opt/contract-master-worker/orca-app/orca-ide \
    /opt/contract-master-worker/orca-app/resources/app.asar/out/main/orcad/orcad-local-serve-selection-entry.js \
    --user-data ~/.orca-serve --app-root /opt/contract-master-worker/orca-app/resources/app.asar
  ```
- Remove: `sudo systemctl disable --now d3-worker-orca`, delete the unit,
  `orca environment rm --environment rh1-d3`, `systemctl --user disable --now
  rh1-d3-tunnel` on RH3, then remove `~/worker` and `~/.orca-serve` on RH1.

## Previous setup: `cm-worker`

From 2026-10-29 to 2026-11-03, workers ran as the locked-down user `cm-worker`
(`cm-worker-orca.service`, `127.0.0.1:6791`, binaries under
`/opt/contract-master-worker`), paired as environment `cm-worker` from a coordinator
on RH1. It is still running as a fallback. `/opt/contract-master-worker` is shared
with the new setup, so keep it. To retire `cm-worker`: `sudo systemctl disable --now
cm-worker-orca`, then `sudo userdel -r cm-worker`.
