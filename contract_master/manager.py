"""Trusted coordinator API. Worker reports are data, never execution authority."""
import copy
import json
import os
import uuid
from pathlib import Path
from . import context, github, github_app, phases
from .contracts import ContractError, digest, safe_path, validate, within
from .store import Store

# Fields whose change makes a new task revision. Comments, labels and status do not.
MATERIAL_FIELDS = ("issue_id", "repo_id", "base_commit", "goal", "allowed_scope", "acceptance_criteria",
                   "required_checks")


LABEL_PREFIX = "repo:"


def route(registry, issue):
    """Check the issue's repository label against the block's repo_id.

    Labels never choose a repository on their own: a missing, unknown or conflicting
    label, or one that names another repository, needs clarification before dispatch.
    """
    labels = issue.get("repo_labels", [])
    owners = {p["linear_label"]: r for r, p in registry["repositories"].items() if p.get("linear_label")}
    expected = registry["repositories"][issue["repo_id"]].get("linear_label")
    if len(labels) > 1:
        raise ContractError("Conflicting repository labels: " + ", ".join(labels))
    if labels:
        label = labels[0]
        if label not in owners:
            raise ContractError("Repository label " + label + " is not registered")
        if owners[label] != issue["repo_id"]:
            raise ContractError("Repository label " + label + " routes to " + owners[label]
                                + ", but the automation block names " + issue["repo_id"])
    elif expected:
        raise ContractError("Missing repository label " + expected + " for " + issue["repo_id"])


def revision_of(issue):
    return digest({k: issue[k] for k in MATERIAL_FIELDS})


REQUIRED_CAPABILITIES = {"read_files", "edit_files", "execute_commands", "git", "structured_results"}
MERGE_FIELDS = ("accepted_commit", "merged_commit", "reviewer", "merger", "pr_url")


def queue_comment(db, key, identifier, body):
    Store.enqueue(db, key, identifier, {"kind": "comment", "body": body})


def queue_status(db, key, identifier, state):
    Store.enqueue(db, key, identifier, {"kind": "status", "state": state})


class Manager:
    def __init__(self, database, registry):
        self.store = Store(database)
        self.registry = registry

    def task(self, task_id):
        with self.store.transaction() as db:
            return Store.task(db, task_id)

    def intake(self, issue):
        """Accept only current, fully fetched snapshots from the trusted intake adapter."""
        validate("issue", issue)
        repo = self.registry["repositories"].get(issue["repo_id"])
        if not repo or issue["project_id"] not in repo["linear_projects"]:
            self.invalidate_issue(issue["issue_id"], "Project/repository no longer registered")
            return {"queued": False, "reason": "Unregistered project/repository"}
        route(self.registry, issue)
        if issue["base_commit"] == "0" * 40:
            raise ContractError("Placeholder base commit is not executable")
        for path in issue["allowed_scope"]:
            safe_path(path)
            if not within(path, repo["allowed_scope"]):
                raise ContractError("Issue cannot expand registered scope")
        if not set(issue["required_checks"]).issubset(repo["checks"]):
            raise ContractError("Issue cannot introduce commands")
        material = {k: issue[k] for k in MATERIAL_FIELDS}
        revision = digest(material)
        task_id = "task-" + digest([issue["issue_id"], revision])[:24]
        with self.store.transaction() as db:
            old = db.execute("SELECT data FROM snapshots WHERE issue=?", (issue["issue_id"],)).fetchone()
            if old and json.loads(old[0])["updated_at"] > issue["updated_at"]:
                return {"queued": False, "reason": "Stale snapshot"}
            db.execute("INSERT OR REPLACE INTO snapshots VALUES(?,?)", (issue["issue_id"], json.dumps(issue)))
            self._dependency(db, issue["issue_id"], issue["status"], issue["updated_at"])
            waiting = []
            for dep in issue["dependencies"]:
                row = db.execute("SELECT status FROM dependencies WHERE issue=?", (dep,)).fetchone()
                if not row or row[0] != "done":
                    waiting.append(dep)
            reason = None
            if issue["status"] != "open":
                reason = "Issue is closed"
            elif issue["kind"] != "executable":
                reason = "Tracking parent"
            elif waiting:
                reason = "Blocked dependencies: " + ", ".join(waiting)
            active = db.execute("SELECT data FROM tasks WHERE issue=? AND active=1", (issue["issue_id"],)).fetchone()
            if active:
                task = json.loads(active[0])
                task["blocked"] = reason
                if task["revision"] == revision:
                    task["issue"] = issue
                    task["needs_replan"] = False
                else:
                    task["needs_replan"] = True
                    reason = "Material revision: settle current worker, then replan"
                Store.save(db, task)
                return {"queued": False, "task_id": task["id"], "reason": reason or "Existing execution"}
            existing = db.execute("SELECT id FROM tasks WHERE issue=? AND revision=?",
                                  (issue["issue_id"], revision)).fetchone()
            if existing:
                return {"queued": False, "task_id": existing[0], "reason": "Revision already accounted for"}
            if reason:
                # Closed issues are settled history: record why, but never comment on them.
                if issue["status"] == "open":
                    queue_comment(db, "triage:" + digest([material, reason]), issue["identifier"], "TRIAGE: " + reason)
                return {"queued": False, "reason": reason}
            task = {"id": task_id, "issue": issue, "revision": revision, "phase": "planning", "plan_revision": 0,
                    "attempt": 0, "policy": copy.deepcopy(repo), "policy_digest": digest(repo), "context": None,
                    "output_commit": None, "verification": None, "needs_replan": False, "blocked": None,
                    "workspace": None, "branch": None}
            db.execute("INSERT INTO tasks VALUES(?,?,?,?,?)",
                       (task_id, issue["issue_id"], revision, 1, json.dumps(task)))
            queue_comment(db, task_id + ":triage", issue["identifier"], "TRIAGE: eligible; Claude planning. " + task_id)
            return {"queued": True, "task_id": task_id}

    @staticmethod
    def _dependency(db, issue_id, status, updated_at):
        if status not in ("open", "done", "canceled"):
            raise ContractError("Unknown dependency status")
        # Newer-or-equal provider timestamps win; an older read never overwrites.
        db.execute("INSERT INTO dependencies VALUES(?,?,?) ON CONFLICT(issue) DO UPDATE"
                   " SET status=excluded.status, updated_at=excluded.updated_at"
                   " WHERE excluded.updated_at >= dependencies.updated_at", (issue_id, status, updated_at))

    def dependency(self, issue_id, status, updated_at):
        with self.store.transaction() as db:
            self._dependency(db, issue_id, status, updated_at)

    def invalidate_issue(self, issue_id, reason):
        with self.store.transaction() as db:
            db.execute("DELETE FROM snapshots WHERE issue=?", (issue_id,))
            rows = db.execute("SELECT data FROM tasks WHERE issue=? AND active=1", (issue_id,)).fetchall()
            for row in rows:
                task = json.loads(row[0])
                task["blocked"] = reason
                task["needs_replan"] = True
                Store.save(db, task)

    def reconsider(self):
        with self.store.transaction() as db:
            snapshots = [json.loads(r[0]) for r in db.execute("SELECT data FROM snapshots ORDER BY issue")]
        return [self.intake(s) for s in snapshots]

    def claim(self, task_id, owner, workspace, branch):
        workspace = os.path.normcase(str(Path(workspace).resolve()))
        with self.store.transaction() as db:
            task = Store.task(db, task_id)
            if task["phase"] in phases.SETTLED:
                raise ContractError("Task is settled")
            current = db.execute("SELECT * FROM ownership WHERE task=?", (task_id,)).fetchone()
            if current:
                if current["owner"] == owner and current["workspace"] == workspace:
                    return current["token"]
                raise ContractError("Existing owner must be recovered; never steal on timeout")
            token = str(uuid.uuid4())
            try:
                db.execute("INSERT INTO ownership VALUES(?,?,?,?)", (workspace, task_id, token, owner))
            except Exception as exc:
                raise ContractError("Workspace already has a writer") from exc
            task.update(workspace=workspace, branch=branch)
            Store.save(db, task)
            return token

    def _owned(self, db, task_id, token, operation, allow_blocked=False):
        row = db.execute("SELECT * FROM ownership WHERE task=? AND token=?", (task_id, token)).fetchone()
        if not row:
            raise ContractError("Stale or absent ownership token")
        task = Store.task(db, task_id)
        phases.check(operation, task["phase"])
        if not allow_blocked:
            for dep in task["issue"]["dependencies"]:
                status = db.execute("SELECT status FROM dependencies WHERE issue=?", (dep,)).fetchone()
                if not status or status[0] != "done":
                    raise ContractError("Dependency no longer permits execution")
        if not allow_blocked and (task["needs_replan"] or task["blocked"]):
            raise ContractError("Task is blocked or requires replanning")
        return task

    def pin_context(self, task_id, token, reference):
        with self.store.transaction() as db:
            task = self._owned(db, task_id, token, "pin_context")
            repo = task["policy"]
            if reference["source_commit"] not in self.registry["reviewed_master_commits"]:
                raise ContractError("Unreviewed master commit")
            context.load(reference, repo["required_context"])
            if task["context"] and task["context"] != reference:
                raise ContractError("Retries retain original context")
            task["context"] = reference
            Store.save(db, task)

    def record_plan(self, task_id, token, plan):
        validate("plan", plan)
        with self.store.transaction() as db:
            task = self._owned(db, task_id, token, "record_plan")
            self._binding(task, plan)
            repo = task["policy"]
            context.load(task["context"], repo["required_context"])
            required = set(repo["required_context"] + repo["documentation_entrypoints"])
            if not required.issubset(plan["read_documents"]) or not plan["latest_handoff_read"]:
                raise ContractError("Plan must explicitly load required guidance, local instructions and HANDOFF")
            if plan["revision"] != task["plan_revision"] + 1:
                raise ContractError("Plan revision mismatch")
            for library, version in repo.get("dependency_versions", {}).items():
                sources = plan["documentation_sources"]
                if not any(d["library_id"] == library and d["version"] == version for d in sources):
                    raise ContractError("Context7 documentation for installed dependency version is required")
            task.update(plan=plan, plan_revision=plan["revision"])
            phases.advance(task, "ready")
            Store.save(db, task)
            queue_comment(db, task_id + ":plan:" + str(plan["revision"]), task["issue"]["identifier"],
                    "PLAN\n" + json.dumps(plan, indent=2))

    @staticmethod
    def _binding(task, report):
        context_ref = task["context"]
        if report["task_id"] != task["id"] or not context_ref or report["context_digest"] != context_ref["digest"]:
            raise ContractError("Report identity/context mismatch")
        if "plan_revision" in report and report["plan_revision"] != task["plan_revision"]:
            raise ContractError("Report plan mismatch")

    def prepare_dispatch(self, task_id, token, runner, live=False):
        validate("runner", runner)
        with self.store.transaction() as db:
            task = self._owned(db, task_id, token, "prepare_dispatch")
            repo = task["policy"]
            if runner["role"] != "deepseek" or not REQUIRED_CAPABILITIES.issubset(runner["capabilities"]):
                raise ContractError("Unsupported implementation runner capabilities")
            if runner["id"] != repo["implementation_runner"]:
                raise ContractError("Runner is not registered for this repository")
            gates_open = (self.registry["automation_enabled"] and runner["enabled"] and runner["mode"] == "live"
                          and repo["merge_gate_audited"] and bool(repo.get("merge_identity")))
            if live and not gates_open:
                raise ContractError("Live activation gates are not satisfied")
            context.load(task["context"], repo["required_context"])
            if task["attempt"] >= 2:
                raise ContractError("Implementation attempt limit reached")
            task["attempt"] += 1
            phases.advance(task, "implementing")
            task["dispatch_mode"] = "live" if live else "simulated"
            task["dispatch_request_id"] = str(uuid.uuid4())
            Store.save(db, task)
            return self.envelope(task)

    @staticmethod
    def envelope(task):
        issue, checks = task["issue"], task["policy"]["checks"]
        result = {"version": "1.0", "task_id": task["id"], "issue_id": issue["issue_id"],
                  "repo_id": issue["repo_id"], "base_commit": issue["base_commit"],
                  "phase": task["phase"], "plan_revision": task["plan_revision"], "context": task["context"],
                  "allowed_scope": issue["allowed_scope"], "acceptance_criteria": issue["acceptance_criteria"],
                  "required_checks": issue["required_checks"], "plan": task["plan"], "attempt": task["attempt"],
                  "corrections": (task.get("verification") or {}).get("corrections", []),
                  "execution_policy_digest": task["policy_digest"],
                  "check_commands": [{"id": check_id, "argv": checks[check_id]["argv"],
                                      "timeout_seconds": checks[check_id].get("timeout_seconds", 120)}
                                     for check_id in issue["required_checks"]]}
        return validate("task", result)

    @staticmethod
    def _checks(task, checks, commit, require_pass=True):
        ids = [c["id"] for c in checks]
        if len(ids) != len(set(ids)) or set(ids) != set(task["issue"]["required_checks"]):
            raise ContractError("Required check set differs")
        if any(c["commit"] != commit or (require_pass and not c["passed"]) for c in checks):
            raise ContractError("Checks must pass against exact recorded commit")

    def implementation(self, task_id, token, result):
        validate("implementation-result", result)
        with self.store.transaction() as db:
            task = self._owned(db, task_id, token, "implementation")
            self._binding(task, result)
            if result["attempt"] != task["attempt"]:
                raise ContractError("Stale implementation attempt")
            for path in result["changed_files"]:
                if not within(path, task["issue"]["allowed_scope"]):
                    raise ContractError("Reported changes exceed allowed scope")
            self._checks(task, result["tests"], result["output_commit"], require_pass=False)
            task.update(implementation=result, output_commit=result["output_commit"], verification=None)
            phases.advance(task, "verifying")
            Store.save(db, task)
            if all(c["passed"] for c in result["tests"]):
                queue_status(db, task_id + ":review:" + result["output_commit"], task["issue"]["identifier"],
                             "In Review")

    def verify(self, task_id, token, result):
        validate("verification-result", result)
        with self.store.transaction() as db:
            task = self._owned(db, task_id, token, "verify")
            self._binding(task, result)
            if result["reviewed_commit"] != task["output_commit"]:
                raise ContractError("Verification commit is stale")
            self._checks(task, result["checks"], result["reviewed_commit"], require_pass=False)
            evidence = result["acceptance_evidence"]
            criteria = [e["criterion"] for e in evidence]
            if len(criteria) != len(set(criteria)) or set(criteria) != set(task["issue"]["acceptance_criteria"]):
                raise ContractError("Every acceptance criterion needs independent evidence")
            passed = all(e["passed"] for e in evidence) and all(c["passed"] for c in result["checks"])
            if result["verdict"] == "pass" and (not passed or result["corrections"]):
                raise ContractError("Passing verdict conflicts with evidence")
            if result["verdict"] == "rework" and not result["corrections"]:
                raise ContractError("Rework needs actionable corrections")
            task["verification"] = result
            if result["verdict"] == "pass":
                phases.advance(task, "awaiting_review")
            else:
                phases.advance(task, "rework" if task["attempt"] < 2 else "escalated")
            Store.save(db, task)
            queue_comment(db, task_id + ":verification:" + digest(result), task["issue"]["identifier"],
                    "VERIFICATION\n" + json.dumps(result, indent=2) + "\nNext phase: " + task["phase"])

    def observe_head(self, task_id, token, commit):
        if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
            raise ContractError("Expected full commit")
        with self.store.transaction() as db:
            task = self._owned(db, task_id, token, "observe_head")
            if task["output_commit"] != commit:
                task.update(output_commit=commit, verification=None, merge_receipt=None)
                phases.advance(task, "verifying")
                Store.save(db, task)

    def open_pr(self, task_id, token, app):
        """Push the output commit to the task branch and open (or reuse) its PR as the PR-opening App."""
        with self.store.transaction() as db:
            task = self._owned(db, task_id, token, "open_pr")
        commit, branch, issue = task["output_commit"], task["branch"] or "", task["issue"]
        if not commit:
            raise ContractError("No output commit to open a PR for")
        if not branch.startswith("task/") or issue["identifier"].lower() in branch.lower():
            # An issue ID in the branch name would let Linear auto-link and move the issue.
            raise ContractError("PR branch must be task/... without the issue identifier")
        pull = app.find_pull(branch)
        # The list endpoint reports merged_at, the single-PR endpoint merged.
        merged = bool(pull) and bool(pull.get("merged") or pull.get("merged_at"))
        already_merged = merged and pull["head"]["sha"] == commit
        if pull and pull["state"] != "open" and not already_merged:
            raise ContractError("PR for task branch is closed; escalate instead of reopening")
        if not pull or pull["head"]["sha"] != commit:
            app.push(task["workspace"], commit, branch)
        if not pull:
            body = ("Related to " + issue["identifier"] + "\n\nGoal: " + issue["goal"] + "\n\nAcceptance:\n"
                    + "".join("- " + c + "\n" for c in issue["acceptance_criteria"]) + "\nTask: " + task_id)
            pull = app.open_pull(branch, github_app.base_branch(task["policy"]), issue["goal"], body)
        pull = app.pull(pull["number"])
        if pull["head"]["sha"] != commit:
            raise ContractError("PR head differs from output commit")
        record = {"number": pull["number"], "url": pull["html_url"], "opened_by": pull["user"]["login"]}
        with self.store.transaction() as db:
            current = self._owned(db, task_id, token, "open_pr")
            if current["output_commit"] != commit:
                raise ContractError("Output commit changed while opening the PR")
            current["pull_request"] = record
            Store.save(db, current)
        return record

    def _merge_step(self, task_id, token, step, value):
        with self.store.transaction() as db:
            task = self._owned(db, task_id, token, "codex_merge", allow_blocked=True)
            steps = task.setdefault("merge_steps", {})
            steps[step] = value
            if step == "merged":
                steps.pop("stopped", None)  # an earlier stop was resolved before this merge
            Store.save(db, task)

    def codex_merge(self, task_id, token, app, reader):
        """Codex checks, approves and merges the exact verified commit, then the read-only gate confirms it."""
        with self.store.transaction() as db:
            task = self._owned(db, task_id, token, "codex_merge")
        verification, pull_request = task["verification"], task.get("pull_request")
        identity, commit = task["policy"].get("merge_identity"), task["output_commit"]
        if not verification or verification["verdict"] != "pass" or verification["reviewed_commit"] != commit:
            raise ContractError("Passing Codex verification of the output commit required")
        if not pull_request:
            raise ContractError("Open the PR before merging")
        if not identity or app.login != identity["login"]:
            raise ContractError("Merge App does not match the registered Codex merge identity")
        number = pull_request["number"]
        pull = app.pull(number)
        if pull["head"]["sha"] != commit:
            if not pull.get("merged"):
                self.observe_head(task_id, token, pull["head"]["sha"])
            raise ContractError("PR head moved after verification; verify the new head")
        if (pull["user"]["login"], pull["user"]["type"]) == (identity["login"], identity["type"]):
            raise ContractError("The merge App cannot approve a PR it opened")
        latest = github.latest_reviews(app.reviews(number))
        if github.human_veto(latest):
            self._merge_step(task_id, token, "stopped", "A human requested changes; escalate")
            raise ContractError("A human requested changes; escalate instead of merging")
        if not pull.get("merged"):
            runs = app.check_runs(commit)
            if not any(r["app"]["id"] == app.app_id and r["head_sha"] == commit and r["conclusion"] == "success"
                       for r in runs):
                summary = "Codex verified " + commit + " for " + task_id + ". " + verification["diff_evidence"]
                app.create_check(commit, summary)
            self._merge_step(task_id, token, "check", commit)
            if not github.approved_by(latest, identity, commit):
                app.approve(number, commit, "Codex verification passed for " + commit)
            self._merge_step(task_id, token, "approved", commit)
            try:
                app.merge(number, commit)
            except github_app.GitHubWriteError as exc:
                if exc.status not in (405, 409, 422):
                    raise
                self._merge_step(task_id, token, "stopped", str(exc))
                raise ContractError("PR is not mergeable; escalate: " + str(exc)) from None
        self._merge_step(task_id, token, "merged", commit)
        return self.confirm_merge(task_id, token, reader, pull_request["url"])

    def confirm_merge(self, task_id, token, provider, pr_url):
        # Provider is selected by trusted coordinator configuration, never by issue/worker output.
        task = self.task(task_id)
        repo = task["policy"]
        if not repo.get("merge_identity"):
            raise ContractError("Codex merge identity is not configured for this repository")
        receipt = provider.confirm(repo["url"], pr_url, task["output_commit"], repo["merge_identity"])
        required = set(MERGE_FIELDS) | {"evidence"}
        if set(receipt) != required or not all(isinstance(v, str) and v for v in receipt.values()):
            raise ContractError("Provider merge receipt is incomplete")
        with self.store.transaction() as db:
            current = self._owned(db, task_id, token, "confirm_merge")
            if receipt["accepted_commit"] != current["output_commit"]:
                raise ContractError("Provider head differs from currently verified commit")
            current["merge_receipt"] = receipt
            Store.save(db, current)
        return receipt

    def complete(self, task_id, token, evidence):
        validate("completion", evidence)
        with self.store.transaction() as db:
            task = self._owned(db, task_id, token, "complete")
            verification = task["verification"]
            verified = bool(verification) and verification["verdict"] == "pass"
            if evidence["task_id"] != task_id or not verified or evidence["accepted_commit"] != task["output_commit"]:
                raise ContractError("Current verification and accepted commit required")
            receipt = task.get("merge_receipt")
            if not receipt or any(evidence[k] != receipt[k] for k in MERGE_FIELDS):
                raise ContractError("Independent provider confirmation of Codex review and merge required")
            self._checks(task, evidence["checks"], evidence["merged_commit"])
            task.update(completion=evidence)
            phases.advance(task, "done")
            Store.save(db, task)
            identifier = task["issue"]["identifier"]
            queue_comment(db, task_id + ":completion", identifier, "COMPLETION\n" + json.dumps(evidence, indent=2))
            queue_status(db, task_id + ":done", identifier, "Done")

    def release(self, task_id, token, settlement_evidence):
        if not settlement_evidence:
            raise ContractError("Positive Orca settlement evidence required")
        with self.store.transaction() as db:
            task = self._owned(db, task_id, token, "release", allow_blocked=True)
            task["release_evidence"] = settlement_evidence
            Store.save(db, task)
            db.execute("DELETE FROM ownership WHERE task=?", (task_id,))

    def record_orca_receipt(self, task_id, token, receipt):
        """Preserve runtime authority and exact recovery action; timeout never releases ownership."""
        required = {"run_id", "orca_task_id", "dispatch_id", "request_id", "status", "recovery"}
        if set(receipt) != required or not all(isinstance(v, str) and v for v in receipt.values()):
            raise ContractError("Incomplete Orca authority receipt")
        with self.store.transaction() as db:
            task = self._owned(db, task_id, token, "record_orca_receipt", allow_blocked=True)
            if receipt["request_id"] != task.get("dispatch_request_id"):
                raise ContractError("Orca receipt request differs from prepared attempt")
            task.setdefault("orca_receipts", []).append(receipt)
            Store.save(db, task)

    def supersede(self, task_id, token, settlement_evidence):
        """Called only after Orca has positively settled the old authoritative Dispatch."""
        if not settlement_evidence:
            raise ContractError("Settlement evidence required")
        with self.store.transaction() as db:
            task = self._owned(db, task_id, token, "supersede", allow_blocked=True)
            if not task["needs_replan"]:
                raise ContractError("No material revision pending")
            snapshot = db.execute("SELECT data FROM snapshots WHERE issue=?",
                                  (task["issue"]["issue_id"],)).fetchone()
            if not snapshot:
                raise ContractError("Clarify incomplete issue before superseding its preserved identity")
            current = json.loads(snapshot[0])
            revision = revision_of(current)
            if revision == task["revision"]:
                raise ContractError("Unchanged revision must resume its existing identity")
            task.update(settlement_evidence=settlement_evidence)
            phases.advance(task, "superseded")
            Store.save(db, task)
            db.execute("DELETE FROM ownership WHERE task=?", (task_id,))
        return self.reconsider()

    def handoff(self, task_id, token, report):
        validate("handoff", report)
        with self.store.transaction() as db:
            task = self._owned(db, task_id, token, "handoff", allow_blocked=True)
            workspace = os.path.normcase(str(Path(report["workspace"]).resolve()))
            describes_task = (report["task_id"] == task_id and report["phase"] == task["phase"]
                              and workspace == task["workspace"] and report["branch"] == task["branch"])
            if not describes_task:
                raise ContractError("HANDOFF does not describe authoritative task")
            owner = db.execute("SELECT owner FROM ownership WHERE task=?", (task_id,)).fetchone()[0]
            if report["owner"] != owner:
                raise ContractError("HANDOFF owner mismatch")
            db.execute("INSERT OR REPLACE INTO handoffs VALUES(?,?)", (task_id, json.dumps(report)))
            queue_comment(db, task_id + ":handoff:" + digest(report), task["issue"]["identifier"],
                    "HANDOFF\n" + json.dumps(report, indent=2))
        self.export_handoffs()

    def export_handoffs(self):
        directory = self.store.path.parent / "handoffs"
        directory.mkdir(exist_ok=True)
        with self.store.transaction() as db:
            for row in db.execute("SELECT task,data FROM handoffs"):
                path = directory / (row["task"] + ".json")
                temp = path.with_suffix(".tmp")
                temp.write_text(row["data"] + "\n")
                temp.replace(path)
