"""Report configuration gates without provisioning credentials or starting workers."""
import json
from .contracts import ROOT, validate
from .manager import REQUIRED_CAPABILITIES


def report(registry):
    blockers = []
    if not registry["automation_enabled"]:
        blockers.append("Orca automation activation is disabled in registry")
    if not registry["reviewed_master_commits"]:
        blockers.append("Review and pin a master commit")
    for repo_id, policy in registry["repositories"].items():
        if not policy["merge_gate_audited"]:
            blockers.append(repo_id + ": audit Linear merge/status automations")
        config = policy.get("runner_config")
        if not config:
            blockers.append(repo_id + ": runner configuration is missing")
            continue
        try:
            runner = validate("runner", json.loads((ROOT / config).read_text()))
            if runner["id"] != policy["implementation_runner"] or runner["role"] != "deepseek" or runner["mode"] != "live" or not runner["enabled"] or not REQUIRED_CAPABILITIES.issubset(runner["capabilities"]):
                blockers.append(repo_id + ": verify and enable real DeepSeek runner capabilities")
        except (OSError, ValueError):
            blockers.append(repo_id + ": invalid runner configuration")
    return {"automation_enabled": registry["automation_enabled"], "reviewed_master_commits": registry["reviewed_master_commits"],
            "configuration_ready": not blockers, "blockers": blockers,
            "note": "Configuration readiness does not prove model access, bundle availability, base commit or execution-host isolation; validate per task before dispatch.",
            "simulation_command": "python3 -m unittest discover -s tests -v"}
