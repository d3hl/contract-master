import argparse
import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from contract_master import governance
from contract_master.__main__ import clean_checkout, review_merge
from contract_master.contracts import ContractError, ProviderError
from contract_master.store import Store
from contract_master.turns import TurnLease
from support import A, B, C, FakeApp, FakeReader, WorkflowFixture

KEY = "example/repo#1"


def pull(number=1, state="open", draft=False, merged=False, head=A, base="main",
         author=("person", "User"), repo="example/repo", merged_at=None):
    return {"number": number, "state": state, "draft": draft, "merged": merged,
            "merged_at": merged_at, "html_url": "https://github.com/example/repo/pull/" + str(number),
            "user": {"login": author[0], "type": author[1]},
            "head": {"sha": head, "ref": "topic", "repo": {"full_name": repo}},
            "base": {"ref": base}}


def registry():
    return {
        "version": "1.0", "automation_enabled": True, "linear_workspace": "workspace",
        "reviewed_master_commits": [],
        "repositories": {"example/repo": {
            "url": "https://github.com/example/repo",
            "base_ref": "origin/main",
            "checks": {
                "unit": {"argv": ["python3", "-c", "print('ok')"], "timeout_seconds": 30},
                "other": {"argv": ["python3", "-c", "print('other')"]}},
            "merge_gate_audited": True,
            "merge_identity": {"login": "codex-bot[bot]", "type": "Bot"},
            "github_apps": {
                "pr": {"slug": "orca-bot", "app_id": 6, "installation_id": 2,
                       "key_reference": "op://vault/pr/key"},
                "merge": {"slug": "codex-bot", "app_id": 7, "installation_id": 3,
                          "key_reference": "op://vault/merge/key"}},
            "governance_review": {
                "enabled": True,
                "authors": [{"login": "person", "type": "User"}],
                "allowed_paths": ["config/registry.json", "docs/onboarding", "docs/knowledge"],
                "registry_fields": ["allowed_scope", "checks", "documentation_entrypoints",
                                    "dependency_versions"],
                "checks": ["unit"]},
        }},
    }


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class GovernanceFixture(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.database = Path(temp.name) / "state.sqlite3"
        self.store = Store(self.database)
        self.clock = Clock()
        self.registry = registry()
        self.lease = TurnLease(self.store, self.clock).start()["lease"]
        self.gov = governance.Governance(self.store, self.registry, self.clock)
        self.pull = pull()

    def intake(self, **overrides):
        arguments = {"lease": self.lease, "repo_id": "example/repo", "pull": copy.deepcopy(self.pull),
                     "files": ["docs/knowledge/note.md"], "base_sha": B}
        arguments.update(overrides)
        return self.gov.intake(**arguments)

    def evidence(self, record, verdict="pass", passed=True):
        return {
            "version": "1.0", "key": record["key"], "author": "codex",
            "head_sha": record["head_sha"], "base_sha": record["base_sha"], "verdict": verdict,
            "acceptance_evidence": [{"criterion": item, "passed": passed, "evidence": "reviewed"}
                                    for item in record["criteria"]],
            "checks": [{"id": check_id, "commit": record["head_sha"], "passed": passed,
                        "evidence": "independent check output"} for check_id in record["checks"]],
            "corrections": [] if verdict == "pass" else ["Correct the policy wording"],
            "diff_evidence": "git diff base..head reviewed independently",
        }

    def verified(self, verdict="pass"):
        record = self.intake()
        return self.gov.verify(self.lease, record["key"], self.evidence(record, verdict))

    def app(self):
        app = FakeApp(login="codex-bot[bot]", app_id=7)
        app.pulls[1] = copy.deepcopy(self.pull)
        return app

    def merge(self, app, base=B):
        return self.gov.merge(self.lease, KEY, app, FakeReader(app), base)


class IntakeTests(GovernanceFixture):
    def test_eligible_intake_creates_verifying_record(self):
        record = self.intake()
        self.assertEqual(record["phase"], "verifying")
        self.assertEqual(record["key"], KEY)
        self.assertEqual(record["url"], "https://github.com/example/repo/pull/1")
        self.assertEqual(record["files"], ["docs/knowledge/note.md"])
        self.assertEqual(record["changes"], [])
        self.assertEqual(record["checks"],
                         {"unit": {"argv": ["python3", "-c", "print('ok')"], "timeout_seconds": 30}})
        self.assertEqual(len(record["criteria"]), 2)
        self.assertEqual(len(record["history"]), 1)
        self.assertEqual(len(self.gov.list()), 1)

    def test_second_intake_of_same_head_is_a_noop(self):
        first = self.intake()
        second = self.intake()
        self.assertEqual(first, second)
        self.assertEqual(len(second["history"]), 1)

    def test_closed_unmerged_pr_is_recorded_closed(self):
        record = self.intake(pull=pull(state="closed"))
        self.assertEqual(record["phase"], "closed")
        self.assertEqual(self.intake(pull=pull(state="closed"))["phase"], "closed")

    def test_merged_record_is_never_rewritten(self):
        record = self.verified()
        app = self.app()
        merged = self.merge(app)
        self.assertEqual(merged["phase"], "merged")
        reopened = self.intake(pull=pull(state="closed", merged=True, merged_at="2026-11-01T00:00:00Z"))
        self.assertEqual(reopened["phase"], "merged")
        self.assertEqual(reopened["merge_receipt"], merged["merge_receipt"])

    def test_unregistered_repository_and_disabled_block_raise(self):
        with self.assertRaises(ContractError):
            self.intake(repo_id="other/repo")
        self.assertEqual(self.gov.list(), [])
        blocked = copy.deepcopy(self.registry)
        blocked["repositories"]["example/repo"]["governance_review"]["enabled"] = False
        disabled = governance.Governance(self.store, blocked, self.clock)
        with self.assertRaises(ContractError):
            disabled.intake(self.lease, "example/repo", copy.deepcopy(self.pull),
                            ["docs/knowledge/note.md"], B)
        self.assertEqual(self.gov.list(), [])

    def test_ineligible_reasons_are_recorded(self):
        cases = {
            "draft": (pull(draft=True), ["docs/knowledge/note.md"], "Draft PR"),
            "fork": (pull(repo="someone/fork"), ["docs/knowledge/note.md"], "Fork"),
            "author": (pull(author=("stranger", "User")), ["docs/knowledge/note.md"], "Author"),
            "base": (pull(base="develop"), ["docs/knowledge/note.md"], "Base ref"),
            "outside": (pull(), ["README.md"], "README.md"),
        }
        for name, (value, files, text) in cases.items():
            with self.subTest(name=name):
                self.setUp()
                record = self.intake(pull=value, files=files)
                self.assertEqual(record["phase"], "ineligible")
                self.assertIn(text, record["reason"])

    def test_forbidden_registry_changes_are_ineligible(self):
        def merge_identity(head):
            head["repositories"]["example/repo"]["merge_identity"] = {"login": "x", "type": "Bot"}

        def automation(head):
            head["automation_enabled"] = False

        def add_repository(head):
            head["repositories"]["other/repo"] = copy.deepcopy(head["repositories"]["example/repo"])

        def governance_block(head):
            head["repositories"]["example/repo"]["governance_review"]["checks"] = ["other"]

        cases = {"merge_identity": (merge_identity, "merge_identity"),
                 "automation_enabled": (automation, "automation_enabled"),
                 "new repository": (add_repository, "added repository"),
                 "governance_review": (governance_block, "governance_review")}
        for name, (mutate, text) in cases.items():
            with self.subTest(name=name):
                self.setUp()
                head = copy.deepcopy(self.registry)
                mutate(head)
                record = self.intake(files=["config/registry.json"], head_registry=head)
                self.assertEqual(record["phase"], "ineligible")
                self.assertIn(text, record["reason"])

    def test_head_registry_problems_are_ineligible(self):
        missing = self.intake(files=["config/registry.json"])
        self.assertEqual(missing["phase"], "ineligible")
        self.assertIn("unavailable", missing["reason"])
        not_object = self.intake(files=["config/registry.json"], head_registry=[])
        self.assertEqual(not_object["phase"], "ineligible")
        self.assertIn("not a JSON object", not_object["reason"])

    def test_allowed_check_change_keeps_base_argv_and_adds_criterion(self):
        head = copy.deepcopy(self.registry)
        head["repositories"]["example/repo"]["checks"]["unit"]["argv"] = ["python3", "-c", "print('new')"]
        record = self.intake(files=["config/registry.json"], head_registry=head)
        self.assertEqual(record["phase"], "verifying")
        self.assertEqual(record["checks"]["unit"]["argv"], ["python3", "-c", "print('ok')"])
        self.assertEqual(record["changes"][0]["field"], "checks")
        self.assertTrue(any("Check argv change" in item for item in record["criteria"]))
        self.assertTrue(any("Documentation matches" in item for item in record["criteria"]))


class BindingTests(GovernanceFixture):
    def test_head_move_before_verify_resets(self):
        self.intake()
        moved = self.intake(pull=pull(head=C))
        self.assertEqual(moved["phase"], "verifying")
        self.assertEqual(moved["head_sha"], C)
        self.assertEqual(len(moved["history"]), 2)
        self.assertEqual(moved["changes_verdicts"], 0)

    def test_head_move_after_verify_resets(self):
        self.verified()
        moved = self.intake(pull=pull(head=C))
        self.assertEqual(moved["phase"], "verifying")
        self.assertIsNone(moved["verification"])
        self.assertEqual(moved["merge_steps"], {})

    def test_head_move_between_approve_and_merge_resets_without_merge_write(self):
        self.verified()
        app = self.app()
        app.fail["merge"] = ProviderError("connection reset")
        with self.assertRaises(ProviderError):
            self.merge(app)
        self.assertEqual(len([write for write in app.writes if write[0] == "approve"]), 1)
        app.pulls[1]["head"]["sha"] = C
        before = list(app.writes)
        with self.assertRaises(ContractError):
            self.merge(app)
        self.assertEqual(app.writes, before)
        self.assertEqual([write for write in app.writes if write[0] == "merge"], [])
        record = self.gov.get(KEY)
        self.assertEqual(record["phase"], "verifying")
        self.assertIsNone(record["verification"])

    def test_base_move_resets_without_writes(self):
        self.verified()
        app = self.app()
        with self.assertRaises(ContractError):
            self.merge(app, base=C)
        self.assertEqual(app.writes, [])
        self.assertEqual(self.gov.get(KEY)["phase"], "verifying")

    def test_second_coordinator_cannot_write(self):
        for case in ("different", "expired", "missing"):
            with self.subTest(case=case):
                self.setUp()
                record = self.intake()
                if case == "different":
                    with self.assertRaises(ContractError):
                        self.intake(lease="bogus")
                elif case == "expired":
                    self.clock.now += 81 * 60
                    with self.assertRaises(ContractError):
                        self.intake()
                else:
                    with self.store.transaction() as db:
                        db.execute("DELETE FROM turn_lease")
                    with self.assertRaises(ContractError):
                        self.intake()
                self.assertEqual(self.gov.get(record["key"]), record)


class VerifyAndMergeTests(GovernanceFixture):
    def test_verify_rejects_stale_head_missing_criterion_and_wrong_commit(self):
        record = self.intake()
        good = self.evidence(record)
        with self.assertRaises(ContractError):
            self.gov.verify(self.lease, KEY, dict(good, head_sha=C))
        missing = copy.deepcopy(good)
        missing["acceptance_evidence"] = missing["acceptance_evidence"][1:]
        with self.assertRaises(ContractError):
            self.gov.verify(self.lease, KEY, missing)
        wrong = copy.deepcopy(good)
        wrong["checks"][0]["commit"] = C
        with self.assertRaises(ContractError):
            self.gov.verify(self.lease, KEY, wrong)
        self.assertEqual(self.gov.get(KEY)["phase"], "verifying")

    def test_second_changes_verdict_escalates(self):
        record = self.verified("changes")
        self.assertEqual(record["phase"], "changes_requested")
        self.assertEqual(record["changes_verdicts"], 1)
        record = self.gov.verify(self.lease, KEY, self.evidence(record, "changes"))
        self.assertEqual(record["phase"], "escalated")
        self.assertEqual(record["changes_verdicts"], 2)

    def test_crash_points_rerun_without_duplicate_writes(self):
        for point in ("create_check", "approve", "merge"):
            with self.subTest(point=point):
                self.setUp()
                self.verified()
                app = self.app()
                app.fail[point] = ProviderError("connection reset")
                with self.assertRaises(ProviderError):
                    self.merge(app)
                self.merge(app)
                self.assertEqual(len([write for write in app.writes if write[0] == "check"]), 1)
                self.assertEqual(len([write for write in app.writes if write[0] == "approve"]), 1)
                self.assertEqual(len([write for write in app.writes if write[0] == "merge"]), 1)

    def test_human_veto_escalates_without_writes(self):
        self.verified()
        app = self.app()
        app.review_list.append({"user": {"login": "person", "type": "User"},
                                "state": "CHANGES_REQUESTED", "commit_id": A})
        with self.assertRaises(ContractError):
            self.merge(app)
        self.assertEqual(app.writes, [])
        record = self.gov.get(KEY)
        self.assertEqual(record["phase"], "escalated")
        self.assertIn("human", record["reason"])

    def test_wrong_app_and_unmergeable_pr(self):
        self.verified()
        app = self.app()
        app.login = "other-bot[bot]"
        with self.assertRaises(ContractError):
            self.merge(app)
        self.assertEqual(app.writes, [])
        from contract_master import github_app
        app = self.app()
        app.fail["merge"] = github_app.GitHubWriteError(405, "Required status check is expected")
        with self.assertRaises(ContractError) as caught:
            self.merge(app)
        self.assertIn("escalate", str(caught.exception))
        self.assertEqual(self.gov.get(KEY)["phase"], "escalated")

    def test_confirm_path_to_done(self):
        record = self.verified()
        merged = self.merge(self.app())
        self.assertEqual(merged["phase"], "merged")
        receipt = merged["merge_receipt"]
        evidence = {
            "version": "1.0", "key": KEY, "author": "claude",
            "accepted_commit": record["head_sha"], "merged_commit": receipt["merged_commit"],
            "merger": receipt["merger"],
            "correspondence_evidence": "Merged tree matches the reviewed head",
            "acceptance_evidence": ["Acceptance reconfirmed on the merged commit"],
            "checks": [{"id": check_id, "commit": receipt["merged_commit"], "passed": True,
                        "evidence": "independent check output"} for check_id in record["checks"]],
        }
        done = self.gov.confirm(self.lease, KEY, evidence)
        self.assertEqual(done["phase"], "done")
        self.assertEqual(done["completion"], evidence)

    def test_merge_dry_run_writes_nothing_and_live_refuses_closed_gates(self):
        record = self.verified()
        arguments = argparse.Namespace(command="review-merge", key=KEY, lease=self.lease, live=False)
        result = review_merge(self.store, self.registry, arguments)
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["phase"], "awaiting_merge")
        self.assertEqual(result["head_sha"], record["head_sha"])
        self.assertEqual(result["blockers"], [])
        self.assertEqual(self.gov.get(KEY)["merge_steps"], {})
        arguments.live = True
        closed = copy.deepcopy(self.registry)
        closed["automation_enabled"] = False
        with self.assertRaises(ContractError):
            review_merge(self.store, closed, arguments)
        unaudited = copy.deepcopy(self.registry)
        unaudited["repositories"]["example/repo"]["merge_gate_audited"] = False
        with self.assertRaises(ContractError):
            review_merge(self.store, unaudited, arguments)


class CleanCheckoutTests(unittest.TestCase):
    def test_untracked_files_do_not_block_but_tracked_changes_do(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"],
                           check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
            (root / "tracked.txt").write_text("one\n")
            subprocess.run(["git", "-C", str(root), "add", "tracked.txt"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "base"], check=True)
            self.assertTrue(clean_checkout(root))
            (root / "untracked.txt").write_text("new\n")
            self.assertTrue(clean_checkout(root))
            (root / "tracked.txt").write_text("changed\n")
            self.assertFalse(clean_checkout(root))


class TaskWorkflowTests(WorkflowFixture):
    def test_task_workflow_still_works_with_governance_row(self):
        self.start()
        self.implement()
        with self.manager.store.transaction() as db:
            db.execute("INSERT INTO pr_reviews VALUES(?,?)", (KEY, json.dumps({"key": KEY})))
        app = FakeApp()
        self.manager.open_pr(self.task_id, self.token, app)
        self.manager.verify(self.task_id, self.token, self.verification())
        receipt = self.manager.codex_merge(self.task_id, self.token, app, FakeReader(app))
        self.assertEqual(receipt["merged_commit"], C)
        self.assertEqual(self.manager.task(self.task_id)["merge_steps"]["merged"], B)


if __name__ == "__main__":
    unittest.main()
