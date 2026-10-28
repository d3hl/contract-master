"""One-shot manager operations; the Orca coordinator drives every next action."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from . import context
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
        if name in ("prepare-dispatch", "open-pr", "codex-merge"):
            command.add_argument("--live", action="store_true")
        if name == "bundle":
            command.add_argument("--destination", default=str(ROOT / ".state/context"))
    return root


def run(args):
    registry = read(args.registry)
    manager = Manager(args.database, registry)
    command = args.command
    if command in REPORT_METHODS:
        return getattr(manager, REPORT_METHODS[command])(args.task, args.token, read(args.file))
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
