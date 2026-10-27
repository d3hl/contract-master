"""Independent checkout checks; trusted registry supplies argv, never an issue."""
import subprocess
from pathlib import Path
from .context import git
from .contracts import ContractError, within


def inspect_checkout(workspace, base, output, allowed_scope, checks):
    workspace = Path(workspace).resolve()
    if git(workspace, "rev-parse", "HEAD").decode().strip() != output:
        raise ContractError("Checkout HEAD differs from output commit")
    if git(workspace, "status", "--porcelain"):
        raise ContractError("Independent verification requires a clean checkout")
    ancestry = subprocess.run(["git", "-C", str(workspace), "merge-base", "--is-ancestor", base, output],
                              capture_output=True, check=False)
    if ancestry.returncode:
        raise ContractError("Output commit does not descend from the task base")
    paths = git(workspace, "diff", "--name-only", "-z", base, output).decode().strip("\x00").split("\x00")
    for name in paths:
        if not name or not within(name, allowed_scope):
            raise ContractError("Actual diff exceeds allowed scope or is empty")
    # Save/read the actual diff as evidence; tests alone do not prove acceptance.
    diff = git(workspace, "diff", "--no-ext-diff", base, output).decode()
    results = []
    for check_id, config in checks.items():
        timeout = config.get("timeout_seconds", 120)
        try:
            run = subprocess.run(config["argv"], cwd=str(workspace), capture_output=True, text=True,
                                 timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            # A hung check is a failed check, not a crash of the verifier.
            results.append({"id": check_id, "commit": output, "passed": False,
                            "evidence": "timed out after " + str(timeout) + " seconds"})
            continue
        results.append({"id": check_id, "commit": output, "passed": run.returncode == 0,
                        "evidence": (run.stdout + run.stderr).strip() or "exit=" + str(run.returncode)})
    if git(workspace, "rev-parse", "HEAD").decode().strip() != output or git(workspace, "status", "--porcelain"):
        raise ContractError("Checks changed HEAD or left uncommitted changes")
    return {"changed_files": paths, "diff": diff, "checks": results}
