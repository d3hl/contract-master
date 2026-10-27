"""Orca API boundary: bounded reads/writes and pure worker command preparation."""
import json
import os
import re
import subprocess
from .contracts import ContractError, ProviderError, digest, validate
from .outbox import BeforeSendError, Outbox


class Orca:
    def __init__(self, executable=None):
        # Resolve once. Never fall through to Linux's GNOME screen reader.
        self.executable = executable or os.environ.get("ORCA_CLI_COMMAND") or ("orca-dev" if os.environ.get("ORCA_DEV_REPO_ROOT") else "orca-ide")

    def call(self, *argv, body=None):
        try:
            result = subprocess.run([self.executable, *argv, "--json"], input=body, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ProviderError("Orca CLI did not complete: " + type(exc).__name__) from exc
        try:
            value = json.loads(result.stdout)
        except ValueError as exc:
            raise ProviderError("Orca returned an unreadable receipt") from exc
        if result.returncode or not value.get("ok", True):
            # Keep typed error/nextSteps for exact recovery; never replay a mutation here.
            raise ProviderError(json.dumps(value.get("error", value)))
        return value.get("result", value)

    def project_issues(self, project, workspace):
        cursor = None
        while True:
            args = ["linear", "list-issues", "--project", project, "--workspace", workspace, "--limit", "100"]
            if cursor:
                args += ["--cursor", cursor]
            result = self.call(*args)
            if result.get("meta", {}).get("partial"):
                raise ProviderError("Partial project listing; reconciliation must retry")
            yield from result["issues"]
            if not result.get("truncated", False) and not result.get("meta", {}).get("hasMore", False):
                return
            next_cursor = result.get("nextCursor") or result.get("meta", {}).get("nextCursor")
            if not next_cursor or next_cursor == cursor:
                raise ProviderError("Truncated listing without progress cursor")
            cursor = next_cursor

    def issue(self, issue_id, workspace):
        result = self.call("linear", "issue", issue_id, "--workspace", workspace, "--full")
        meta = result.get("meta", {})
        if meta.get("partial") is not False or meta.get("includeErrors") != []:
            raise ProviderError("Incomplete issue context")
        for section in ("comments", "children", "relations"):
            details = meta.get("sections", {}).get(section, {})
            complete_key = "mayHaveMore" if section == "children" else "hasMore"
            if not isinstance(result.get(section), list) or details.get(complete_key) is not False or details.get("capReached") is not False:
                raise ProviderError("Required issue context is truncated")
        return result

    def worker_command(self, task, orca_task_id, run_id, runner, request_id, workspace):
        """Return argv for coordinator review. This method NEVER launches a process."""
        validate("runner", runner)
        if not runner["enabled"] or runner["mode"] != "live":
            raise ContractError("Runner has no verified live integration")
        spec = json.dumps({"target": task["allowed_scope"], "change": task["acceptance_criteria"],
                           "constraints": "Use only the pinned plan/context. One task writer. No Linear writes.",
                           "ownership": workspace, "task": task}, indent=2)
        return {"spec": spec, "argv": [self.executable, "orchestration", "worker-start", "--task", orca_task_id,
                "--run", run_id, "--worktree", workspace, "--agent", runner["agent"],
                "--retry-request", request_id, "--json"]}


def provider_status(state_type):
    """Map a Linear workflow state type to the manager's issue/dependency status."""
    if state_type == "completed":
        return "done"
    return "canceled" if state_type in ("canceled", "duplicate") else "open"


def normalize(full):
    issue = full["issue"]
    matches = re.findall(r"```contract-master\s*\n(.*?)\n```", issue.get("description") or "", re.S)
    if len(matches) != 1:
        raise ContractError("Missing one complete contract-master block; goal, scope and acceptance required")
    data = json.loads(matches[0])
    # Identity, project, dependency facts, parent kind and status come from Linear, never the block.
    allowed = {"repo_id", "base_commit", "goal", "allowed_scope", "acceptance_criteria", "required_checks"}
    if set(data) != allowed:
        raise ContractError("Automation block contains missing or unauthorized fields")
    state = issue["state"]["type"]
    dependencies = []
    for relation in full.get("relations", []):
        # Installed Orca relation shape is normalized by its provider; unknown shapes fail closed.
        if relation.get("type") == "blocks":
            if relation.get("direction") == "inbound" and relation.get("relationship") == "blockedBy":
                dependencies.append(relation["relatedIssue"]["id"])
            elif relation.get("direction") == "outbound" and relation.get("relationship") == "blocks":
                continue
            else:
                raise ContractError("Ambiguous directional dependency relation")
        elif relation.get("type") not in ("related", "duplicate"):
            raise ContractError("Unknown dependency relation shape")
    data.update(issue_id=issue["id"], identifier=issue["identifier"], project_id=issue["project"]["id"],
                kind="tracking" if full.get("children") else "executable", dependencies=dependencies,
                status=provider_status(state),
                updated_at=issue["updatedAt"])
    return validate("issue", data)


class Intake:
    def __init__(self, manager, orca, workspace):
        self.manager, self.orca, self.workspace = manager, orca, workspace

    def reconcile(self):
        """Full project reconciliation, one bounded invocation; Orca owns cadence."""
        projects = {p for r in self.manager.registry["repositories"].values() for p in r["linear_projects"]}
        outcomes = []
        for project in sorted(projects):
            # A failed listing still aborts the pass: without it the project cannot be enumerated.
            for summary in self.orca.project_issues(project, self.workspace):
                try:
                    outcomes.append(self._triage(summary))
                except ProviderError as exc:
                    # A failed read says nothing about the issue: no comment, no fencing. The next pass retries.
                    outcomes.append({"queued": False, "issue": summary.get("identifier"),
                                     "reason": "Provider read failed: " + str(exc), "retry": True})
        outcomes.extend(self.manager.reconsider())
        return outcomes

    def _triage(self, summary):
        full = self.orca.issue(summary["identifier"], self.workspace)
        state = full["issue"]["state"]["type"]
        self.manager.dependency(summary["id"], provider_status(state), full["issue"]["updatedAt"])
        try:
            if full.get("children"):
                raise ContractError("Tracking parent; executable children own the work")
            snapshot = normalize(full)
            references = {r["relatedIssue"]["id"]: r["relatedIssue"].get("identifier") for r in full.get("relations", []) if "relatedIssue" in r}
            for dep in snapshot["dependencies"]:
                if not references.get(dep):
                    raise ContractError("Dependency identifier missing from provider context")
                dependency = self.orca.issue(references[dep], self.workspace)["issue"]
                self.manager.dependency(dep, provider_status(dependency["state"]["type"]), dependency["updatedAt"])
            return self.manager.intake(snapshot)
        except ProviderError:
            raise
        except (ValueError, KeyError, TypeError) as exc:
            # Human-authored issues remain visible but cannot dispatch without complete scope.
            self.manager.invalidate_issue(summary["id"], str(exc))
            Outbox(self.manager.store).enqueue("incomplete:" + digest([summary["id"], str(exc)]), summary["identifier"],
                {"kind": "comment", "body": "TRIAGE: " + str(exc)})
            return {"queued": False, "reason": str(exc)}


class LinearTransport:
    def __init__(self, orca, workspace):
        self.orca, self.workspace = orca, workspace

    @staticmethod
    def marker(entry):
        return "<!-- contract-master:" + digest(entry["key"]) + " -->"

    def lookup(self, entry):
        full = self.orca.issue(entry["issue"], self.workspace)
        payload = json.loads(entry["payload"])
        if payload["kind"] == "status":
            if full["issue"]["state"]["name"] == payload["state"]:
                return {"observed_state": payload["state"]}
        else:
            for comment in full.get("comments", []):
                if self.marker(entry) in comment.get("body", ""):
                    return {"comment_id": comment["id"], "reconciled": True}
        return None

    def send(self, entry):
        payload = json.loads(entry["payload"])
        # Read first also handles a previous accepted write whose local ack was interrupted.
        try:
            existing = self.lookup(entry)
        except Exception as exc:
            raise BeforeSendError("Linear unavailable before any write") from exc
        if existing:
            return existing
        if payload["kind"] == "comment":
            return self.orca.call("linear", "comment", "add", entry["issue"], "--workspace", self.workspace,
                                  "--body-file", "-", body=payload["body"] + "\n\n" + self.marker(entry))
        if payload["kind"] == "status":
            current = self.orca.issue(entry["issue"], self.workspace)["issue"]["state"]
            if current["type"] in ("completed", "canceled", "duplicate"):
                raise ContractError("Closed issue state must be reconciled by Codex before update")
            return self.orca.call("linear", "status", "set", entry["issue"], "--workspace", self.workspace, "--to", payload["state"])
        raise ContractError("Unsupported outbox operation")
