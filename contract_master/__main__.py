"""One-shot manager operations; the Orca coordinator drives every next action."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from . import context, github, github_app, governance, turns
from .adapters import Intake, LinearTransport, Orca
from .contracts import ContractError, ROOT
from .manager import Manager
from .outbox import Outbox

REPORT = ("task", "token", "file")
SETTLEMENT = ("task", "token", "settlement_evidence")

# Subcommand -> positional arguments, in help order.
COMMANDS = {
    "doctor": (),
    "reconcile": (),
    "flush-one": (),
    "export-handoffs": (),
    "intake": ("file",),
    "inspect-checkout": ("task", "workspace", "commit"),
    "show": ("task",),
    "claim": ("task", "owner", "workspace", "branch"),
    "pin-context": REPORT,
    "plan": REPORT,
    "implementation": REPORT,
    "verify": REPORT,
    "complete": REPORT,
    "handoff": REPORT,
    "orca-receipt": REPORT,
    "prepare-dispatch": ("task", "token", "runner"),
    "observe-head": ("task", "token", "commit"),
    "confirm-merge": ("task", "token", "pr_url"),
    "open-pr": ("task", "token"),
    "codex-merge": ("task", "token"),
    "release": SETTLEMENT,
    "supersede": SETTLEMENT,
    "bundle": ("commit",),
    "turn-start": (),
    "turn-renew": ("lease",),
    "turn-end": ("lease",),
    "turn-check": (),
    "review-refresh": (),
    "review-scan": (),
    "review-list": (),
    "review-show": ("key",),
    "review-inspect": ("key", "workspace"),
    "review-verify": ("key", "file"),
    "review-merge": ("key",),
    "review-confirm": ("key", "file"),
}

# Commands that take (task, token, JSON report file).
REPORT_METHODS = {
    "pin-context": "pin_context",
    "plan": "record_plan",
    "implementation": "implementation",
    "verify": "verify",
    "complete": "complete",
    "handoff": "handoff",
    "orca-receipt": "record_orca_receipt",
}


def read(path):
    return json.loads(Path(path).read_text())


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--registry", default=str(ROOT / "config/registry.json"))
    root.add_argument("--database", default=str(ROOT / ".state/manager.sqlite3"))
    sub = root.add_subparsers(dest="command", required=True)
    for name, positionals in COMMANDS.items():
        command = sub.add_parser(name)
        for argument in positionals:
            command.add_argument(argument)
        if name in ("prepare-dispatch", "open-pr", "codex-merge", "review-merge"):
            command.add_argument("--live", action="store_true")
        if name in ("review-refresh", "review-scan", "review-verify", "review-merge", "review-confirm"):
            command.add_argument("--lease", required=True)
        if name in ("turn-start", "turn-renew"):
            command.add_argument("--minutes", type=int, default=turns.DEFAULT_MINUTES)
        if name == "bundle":
            command.add_argument("--destination", default=str(ROOT / ".state/context"))
    return root


def run(args):
    registry = read(args.registry)
    manager = Manager(args.database, registry)
    command = args.command
    if command.startswith("review-"):
        return review_commands(manager.store, registry, args)
    if command in REPORT_METHODS:
        return getattr(manager, REPORT_METHODS[command])(args.task, args.token, read(args.file))
    if command.startswith("turn-"):
        lease = turns.TurnLease(manager.store)
        if command == "turn-start":
            return lease.start(args.minutes)
        if command == "turn-renew":
            return lease.renew(args.lease, args.minutes)
        return lease.end(args.lease) if command == "turn-end" else lease.check()
    if command == "doctor":
        from .readiness import report
        return report(registry)
    if command == "bundle":
        docs = sorted({d for r in registry["repositories"].values() for d in r["required_context"]})
        return context.build(ROOT, args.commit, docs, args.destination, registry["reviewed_master_commits"])
    if command == "intake":
        return manager.intake(read(args.file))
    if command == "inspect-checkout":
        from .evidence import inspect_checkout
        task = manager.task(args.task)
        issue = task["issue"]
        checks = {key: task["policy"]["checks"][key] for key in issue["required_checks"]}
        return inspect_checkout(args.workspace, issue["base_commit"], args.commit, issue["allowed_scope"], checks)
    if command == "show":
        return manager.task(args.task)
    if command == "claim":
        return {"token": manager.claim(args.task, args.owner, args.workspace, args.branch)}
    if command == "prepare-dispatch":
        return manager.prepare_dispatch(args.task, args.token, read(args.runner), args.live)
    if command == "observe-head":
        return manager.observe_head(args.task, args.token, args.commit)
    if command == "confirm-merge":
        from .github import GitHub
        return manager.confirm_merge(args.task, args.token, GitHub(), args.pr_url)
    if command in ("open-pr", "codex-merge"):
        return github_writes(manager, registry, args)
    if command == "release":
        return manager.release(args.task, args.token, args.settlement_evidence)
    if command == "supersede":
        return manager.supersede(args.task, args.token, args.settlement_evidence)
    if command == "export-handoffs":
        return manager.export_handoffs()
    if command == "reconcile":
        return Intake(manager, Orca(), registry["linear_workspace"]).reconcile()
    if command == "flush-one":
        return Outbox(manager.store).flush_one(LinearTransport(Orca(), registry["linear_workspace"]))
    raise ContractError("Unknown command: " + command)


def github_writes(manager, registry, args):
    """Dry run by default: report intended calls and blockers without touching GitHub or the task."""
    from . import github_app
    task = manager.task(args.task)
    repo = registry["repositories"][task["issue"]["repo_id"]]
    role = "pr" if args.command == "open-pr" else "merge"
    if not args.live:
        steps = (["find PR for " + str(task["branch"]), "push output commit if needed", "open PR if missing"]
                 if role == "pr" else ["read PR and reviews", "post " + github_app.CHECK_NAME, "approve exact commit",
                                       "merge with sha", "confirm-merge"])
        return {"dry_run": True, "phase": task["phase"], "output_commit": task["output_commit"], "steps": steps,
                "blockers": github_app.problems(repo)}
    blockers = github_app.problems(repo)
    if not registry["automation_enabled"] or not repo["merge_gate_audited"] or blockers:
        raise ContractError("Live GitHub writes are not enabled: " + "; ".join(blockers or ["activation gates"]))
    app = github_app.RepoApp(repo, role)
    if role == "pr":
        return manager.open_pr(args.task, args.token, app)
    from .github import GitHub
    return manager.codex_merge(args.task, args.token, app, GitHub())


def clean_checkout(root):
    """Tracked files only: the manager checkout legitimately holds untracked worktrees."""
    status = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
                            capture_output=True, text=True, check=False)
    return status.returncode == 0 and not status.stdout.strip()


def review_refresh(store, registry, args):
    enabled = [(repo_id, repo) for repo_id, repo in registry["repositories"].items()
               if (repo.get("governance_review") or {}).get("enabled") is True]
    if not enabled:
        return {"refreshed": False}
    branch = governance.git_run(ROOT, "rev-parse", "--abbrev-ref", "HEAD")
    current = branch.stdout.strip() if branch.returncode == 0 else ""
    bases = {github_app.base_branch(repo) for _, repo in enabled}
    if current not in bases:
        raise ContractError("Checkout is not on a governance base branch")
    return governance.Governance(store, registry).refresh(args.lease, ROOT, current,
                                                         governance.git_run)


def review_scan(store, registry, args, reader=None):
    """Discover open PRs from a clean checkout whose HEAD is the trusted base tip."""
    if Path(args.registry).resolve() != (ROOT / "config/registry.json").resolve():
        raise ContractError("review-scan requires the checkout's config/registry.json")
    if not clean_checkout(ROOT):
        raise ContractError("review-scan requires a clean checkout")
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=False)
    if head.returncode:
        raise ContractError("review-scan cannot read checkout HEAD")
    checkout = head.stdout.strip()

    def root_ok(tip):
        return tip == checkout

    engine = governance.Governance(store, registry)
    return governance.scan(engine, reader or governance.GitHubReader(), registry, args.lease, root_ok)


def review_inspect(store, registry, args):
    from .evidence import inspect_checkout
    record = governance.Governance(store, registry).get(args.key)
    if not record:
        raise ContractError("Unknown governance record")
    block = governance.policy(registry, record["repo"])
    workspace = Path(args.workspace)
    if context.git(workspace, "rev-parse", "HEAD").decode().strip() != record["head_sha"]:
        raise ContractError("Workspace HEAD differs from the governance head")
    base = subprocess.check_output(["git", "-C", str(workspace), "merge-base",
                                    record["base_sha"], record["head_sha"]],
                                   stderr=subprocess.PIPE).decode().strip()
    return inspect_checkout(workspace, base, record["head_sha"], block["allowed_paths"], record["checks"])


def review_merge(store, registry, args):
    engine = governance.Governance(store, registry)
    record = engine.get(args.key)
    if not record:
        raise ContractError("Unknown governance record")
    repo = registry["repositories"].get(record["repo"]) or {}
    steps = ["read PR and reviews", "post " + github_app.CHECK_NAME, "approve exact head",
             "merge with sha", "read-only confirmation"]
    if not args.live:
        return {"dry_run": True, "phase": record["phase"], "head_sha": record["head_sha"],
                "steps": steps, "blockers": github_app.problems(repo)}
    blockers = github_app.problems(repo)
    if not registry["automation_enabled"] or not repo.get("merge_gate_audited") or blockers:
        raise ContractError("Live governance merge is not enabled: "
                            + "; ".join(blockers or ["activation gates"]))
    governance.policy(registry, record["repo"])
    reader = governance.GitHubReader()
    name = github_app.repo_name(repo["url"])
    current = reader.base_tip(name, github_app.base_branch(repo))
    return engine.merge(args.lease, args.key, github_app.RepoApp(repo, "merge"),
                        github.GitHub(), current)


def review_commands(store, registry, args):
    engine = governance.Governance(store, registry)
    if args.command == "review-refresh":
        return review_refresh(store, registry, args)
    if args.command == "review-scan":
        return review_scan(store, registry, args)
    if args.command == "review-list":
        return engine.list()
    if args.command == "review-show":
        record = engine.get(args.key)
        if not record:
            raise ContractError("Unknown governance record")
        return record
    if args.command == "review-inspect":
        return review_inspect(store, registry, args)
    if args.command == "review-verify":
        return engine.verify(args.lease, args.key, read(args.file))
    if args.command == "review-merge":
        return review_merge(store, registry, args)
    if args.command == "review-confirm":
        return engine.confirm(args.lease, args.key, read(args.file))
    raise ContractError("Unknown command: " + args.command)


def main():
    result = run(parser().parse_args())
    print(json.dumps({"ok": True, "result": result}, indent=2))


if __name__ == "__main__":
    try:
        main()
    # SubprocessError covers failed or timed-out git/gh calls, so errors stay JSON.
    except (ContractError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        sys.exit(1)
