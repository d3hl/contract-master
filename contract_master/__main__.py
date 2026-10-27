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


def read(path):
    return json.loads(Path(path).read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default=str(ROOT / "config/registry.json"))
    parser.add_argument("--database", default=str(ROOT / ".state/manager.sqlite3"))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    sub.add_parser("reconcile")
    sub.add_parser("flush-one")
    sub.add_parser("export-handoffs")
    p = sub.add_parser("intake"); p.add_argument("file")
    p = sub.add_parser("inspect-checkout"); p.add_argument("task"); p.add_argument("workspace"); p.add_argument("commit")
    p = sub.add_parser("show"); p.add_argument("task")
    p = sub.add_parser("claim"); p.add_argument("task"); p.add_argument("owner"); p.add_argument("workspace"); p.add_argument("branch")
    for name in ("pin-context", "plan", "implementation", "verify", "complete", "handoff", "orca-receipt"):
        p = sub.add_parser(name); p.add_argument("task"); p.add_argument("token"); p.add_argument("file")
    p = sub.add_parser("prepare-dispatch"); p.add_argument("task"); p.add_argument("token"); p.add_argument("runner"); p.add_argument("--live", action="store_true")
    p = sub.add_parser("observe-head"); p.add_argument("task"); p.add_argument("token"); p.add_argument("commit")
    p = sub.add_parser("confirm-merge"); p.add_argument("task"); p.add_argument("token"); p.add_argument("pr_url")
    p = sub.add_parser("release"); p.add_argument("task"); p.add_argument("token"); p.add_argument("settlement_evidence")
    p = sub.add_parser("supersede"); p.add_argument("task"); p.add_argument("token"); p.add_argument("settlement_evidence")
    p = sub.add_parser("bundle"); p.add_argument("commit"); p.add_argument("--destination", default=str(ROOT / ".state/context"))
    args = parser.parse_args()
    registry = read(args.registry)
    manager = Manager(args.database, registry)
    result = None
    if args.command == "doctor":
        from .readiness import report
        result = report(registry)
    elif args.command == "bundle":
        docs = sorted({d for r in registry["repositories"].values() for d in r["required_context"]})
        result = context.build(ROOT, args.commit, docs, args.destination, registry["reviewed_master_commits"])
    elif args.command == "intake": result = manager.intake(read(args.file))
    elif args.command == "inspect-checkout":
        from .evidence import inspect_checkout
        task = manager.task(args.task)
        check_configs = {key: task["policy"]["checks"][key] for key in task["issue"]["required_checks"]}
        result = inspect_checkout(args.workspace, task["issue"]["base_commit"], args.commit, task["issue"]["allowed_scope"], check_configs)
    elif args.command == "show": result = manager.task(args.task)
    elif args.command == "claim": result = {"token": manager.claim(args.task, args.owner, args.workspace, args.branch)}
    elif args.command == "prepare-dispatch": result = manager.prepare_dispatch(args.task, args.token, read(args.runner), args.live)
    elif args.command == "observe-head": result = manager.observe_head(args.task, args.token, args.commit)
    elif args.command == "confirm-merge":
        from .github import GitHub
        result = manager.confirm_merge(args.task, args.token, GitHub(), args.pr_url)
    elif args.command == "release": result = manager.release(args.task, args.token, args.settlement_evidence)
    elif args.command == "supersede": result = manager.supersede(args.task, args.token, args.settlement_evidence)
    elif args.command == "export-handoffs": result = manager.export_handoffs()
    elif args.command == "reconcile": result = Intake(manager, Orca(), registry["linear_workspace"]).reconcile()
    elif args.command == "flush-one": result = Outbox(manager.store).flush_one(LinearTransport(Orca(), registry["linear_workspace"]))
    else:
        methods = {"pin-context": manager.pin_context, "plan": manager.record_plan, "implementation": manager.implementation,
                   "verify": manager.verify, "complete": manager.complete, "handoff": manager.handoff, "orca-receipt": manager.record_orca_receipt}
        result = methods[args.command](args.task, args.token, read(args.file))
    print(json.dumps({"ok": True, "result": result}, indent=2))


if __name__ == "__main__":
    try:
        main()
    # SubprocessError covers failed or timed-out git/gh calls, so errors stay JSON.
    except (ContractError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        sys.exit(1)
