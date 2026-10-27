import subprocess
import tempfile
import unittest
from pathlib import Path

from contract_master import context
from contract_master.manager import Manager
from contract_master.outbox import BeforeSendError

A = "a" * 40
B = "b" * 40
C = "c" * 40


class FakeLinear:
    """Deterministic transport; NOT a model run or proof of provider compatibility."""
    def __init__(self):
        self.messages = {}
        self.calls = 0
        self.offline = False
        self.lose_ack = False

    def send(self, entry):
        if self.offline:
            raise BeforeSendError("not sent")
        self.calls += 1
        self.messages[entry["key"]] = {"id": str(self.calls)}
        if self.lose_ack:
            self.lose_ack = False
            raise TimeoutError("accepted but response lost")
        return self.messages[entry["key"]]

    def lookup(self, entry):
        return self.messages.get(entry["key"])


class WorkflowFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.master = self.root / "master"
        self.master.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Fixture")
        (self.master / "AGENTS.md").write_text("Read shared workflow and local guidance.\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Reviewed fixture")
        self.commit = self.git("rev-parse", "HEAD").strip()
        self.reference = context.build(self.master, self.commit, ["AGENTS.md"], self.root / "context", [self.commit])
        self.registry = {"automation_enabled": False, "reviewed_master_commits": [self.commit], "repositories": {
            "example/repo": {"linear_projects": ["project-1"], "required_context": ["AGENTS.md"],
                "documentation_entrypoints": ["README.md"], "allowed_scope": ["src", "tests"],
                "checks": {"unit": {"argv": ["python3", "-c", "print('ok')"]}}, "merge_gate_audited": False,
                "url": "https://github.com/example/repo", "implementation_runner": "deepseek-portable"}}}
        self.database = self.root / "state" / "manager.sqlite3"
        self.manager = Manager(self.database, self.registry)
        self.issue = {"issue_id": "issue-1", "identifier": "TEST-1", "project_id": "project-1", "repo_id": "example/repo",
                      "base_commit": A, "kind": "executable", "goal": "Correct the parser", "allowed_scope": ["src", "tests"],
                      "acceptance_criteria": ["Reject malformed input"], "required_checks": ["unit"], "dependencies": [],
                      "status": "open", "updated_at": "2026-10-25T00:00:00.000Z"}
        self.runner = {"version": "1.0", "id": "deepseek-portable", "role": "deepseek", "mode": "simulated",
                       "capabilities": ["read_files", "edit_files", "execute_commands", "git", "structured_results"],
                       "evidence": "Fixture capabilities only", "agent": "unconfigured", "enabled": False}

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.master), *args], stderr=subprocess.PIPE).decode()

    def start(self):
        self.task_id = self.manager.intake(self.issue)["task_id"]
        self.token = self.manager.claim(self.task_id, "coordinator", self.root / "workspace", "task/one")
        self.manager.pin_context(self.task_id, self.token, self.reference)
        self.plan = {"version": "1.0", "task_id": self.task_id, "author": "codex", "revision": 1,
                     "steps": ["Investigate parser; implement and check malformed input"], "context_digest": self.reference["digest"],
                     "read_documents": ["AGENTS.md", "README.md"], "investigation_evidence": ["src/parser.py inspected"], "latest_handoff_read": True, "documentation_sources": []}
        self.manager.record_plan(self.task_id, self.token, self.plan)

    def implement(self):
        task = self.manager.prepare_dispatch(self.task_id, self.token, self.runner)
        self.assertEqual(task["phase"], "implementing")
        self.result = {"version": "1.0", "task_id": self.task_id, "attempt": self.manager.task(self.task_id)["attempt"],
                       "plan_revision": 1, "context_digest": self.reference["digest"], "output_commit": B,
                       "change_summary": "Parser rejects malformed input", "tests": self.checks(B), "unresolved_concerns": [],
                       "artifacts": ["test log fixture"], "changed_files": ["src/parser.py", "tests/test_parser.py"]}
        self.manager.implementation(self.task_id, self.token, self.result)

    @staticmethod
    def checks(commit, passed=True):
        return [{"id": "unit", "commit": commit, "passed": passed, "evidence": "Independent test output fixture"}]

    def verification(self, passed=True, commit=B):
        return {"version": "1.0", "task_id": self.task_id, "author": "codex", "reviewed_commit": commit,
                "plan_revision": 1, "context_digest": self.reference["digest"], "verdict": "pass" if passed else "rework",
                "acceptance_evidence": [{"criterion": "Reject malformed input", "passed": passed, "evidence": "Malformed-input test and actual diff reviewed"}],
                "checks": self.checks(commit, passed), "corrections": [] if passed else ["Add missing empty-token rejection in src/parser.py"],
                "diff_evidence": "git diff base..output reviewed independently"}

    def completion(self):
        manager = self.manager
        task_id, token = self.task_id, self.token
        class Provider:
            def confirm(self, repo, url, commit):
                return {"accepted_commit": commit, "merged_commit": C, "human_reviewer": "reviewer", "human_merger": "merger",
                        "pr_url": url, "evidence": "Fake provider: merged + human approval on exact head"}
        if manager.task(task_id)["phase"] == "awaiting_review":
            manager.confirm_merge(task_id, token, Provider(), "https://example.invalid/pull/1")
        return {"version": "1.0", "task_id": self.task_id, "author": "codex", "accepted_commit": B, "merged_commit": C,
                "pr_url": "https://example.invalid/pull/1", "human_reviewer": "reviewer", "human_merger": "merger",
                "provider_evidence": "Provider merge receipt fixture", "correspondence_evidence": "Merged diff matches accepted change",
                "acceptance_evidence": ["Acceptance reconfirmed on merged commit"], "checks": self.checks(C)}

    def handoff(self):
        return {"version": "1.0", "task_id": self.task_id, "phase": self.manager.task(self.task_id)["phase"],
                "owner": "coordinator", "workspace": str(self.root / "workspace"), "branch": "task/one", "commit": B,
                "completed_work": ["Implementation returned"], "verification_evidence": [], "blockers": ["Linear outage"],
                "next_action": "Recover recorded Dispatch; independently verify output commit"}

