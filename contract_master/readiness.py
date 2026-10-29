"""Report configuration gates without provisioning credentials or starting workers."""
import json
from . import github_app
from .contracts import ROOT, validate
from .manager import LABEL_PREFIX, REQUIRED_CAPABILITIES


def report(registry):
    blockers = []
    if not registry["automation_enabled"]:
        blockers.append("Orca automation activation is disabled in registry")
    if not registry["reviewed_master_commits"]:
        blockers.append("Review and pin a master commit")
    labels = [p["linear_label"] for p in registry["repositories"].values() if p.get("linear_label")]
    for label in sorted(set(labels)):
        if labels.count(label) > 1:
            blockers.append("Repository label " + label + " is registered to more than one repository")
        if not label.startswith(LABEL_PREFIX) or label == LABEL_PREFIX:
            blockers.append("Repository label " + label + " must start with " + LABEL_PREFIX)
    for repo_id, policy in registry["repositories"].items():
        if not policy["merge_gate_audited"]:
            blockers.append(repo_id + ": audit Linear merge/status automations")
        if not policy.get("merge_identity"):
            blockers.append(repo_id + ": create the Codex GitHub merge identity and record merge_identity")
        blockers.extend(repo_id + ": " + problem for problem in github_app.problems(policy))
        roles = (policy.get("planning_runner"), policy.get("verification_runner"), policy.get("merge_runner"))
        if roles != ("claude", "codex", "codex"):
            blockers.append(repo_id + ": planning must be Claude; verification and merge must be Codex")
        config = policy.get("runner_config")
        if not config:
            blockers.append(repo_id + ": runner configuration is missing")
            continue
        try:
            runner = validate("runner", json.loads((ROOT / config).read_text()))
            verified = (runner["id"] == policy["implementation_runner"] and runner["role"] == "deepseek"
                        and runner["mode"] == "live" and runner["enabled"]
                        and REQUIRED_CAPABILITIES.issubset(runner["capabilities"]))
            if not verified:
                blockers.append(repo_id + ": verify and enable real DeepSeek runner capabilities")
        except (OSError, ValueError):
            blockers.append(repo_id + ": invalid runner configuration")
    return {"automation_enabled": registry["automation_enabled"],
            "reviewed_master_commits": registry["reviewed_master_commits"],
            "configuration_ready": not blockers, "blockers": blockers,
            "note": ("Configuration readiness does not prove model access, bundle availability, base commit or "
                     "execution-host isolation; validate per task before dispatch."),
            "simulation_command": "python3 -m unittest discover -s tests -v"}
