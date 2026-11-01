import argparse
import base64
import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from contract_master import github_app, governance
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


def scan_registry():
    base = registry()
    base["repositories"]["example/repo"]["governance_review"]["authors"] = [
        {"login": "d3adc3II", "type": "User"}]
    base["repositories"]["d3-corp/corp-integrated-dashboard"] = {
        "url": "https://github.com/d3-corp/corp-integrated-dashboard",
        "base_ref": "origin/main",
        "allowed_scope": ["README.md", "docs"],
        "checks": {"typecheck": {"argv": ["python3", "-c", "print('typecheck')"]}},
    }
    return base


class ScanAPI:
    """REST-shaped read-only GitHub double for governance.scan."""

    def __init__(self, pulls, files, contents, tip):
        self.pulls, self.files, self.contents, self.tip = pulls, files, contents, tip

    def __call__(self, path):
        if path.startswith("repos/example/repo/pulls?state=open"):
            return [self.pulls[number] for number in sorted(self.pulls)]
        if "/pulls/" in path and path.endswith("/files?per_page=100&page=1"):
            number = int(path.split("/pulls/")[1].split("/")[0])
            return self.files[number][:100]
        if "/pulls/" in path and path.endswith("/files?per_page=100&page=2"):
            number = int(path.split("/pulls/")[1].split("/")[0])
            return self.files[number][100:200]
        if path.startswith("repos/example/repo/pulls/"):
            return self.pulls[int(path.rsplit("/", 1)[1])]
        if path.startswith("repos/example/repo/commits/"):
            return {"sha": self.tip}
        if path.startswith("repos/example/repo/contents/"):
            target = path.split("/contents/", 1)[1].split("?", 1)[0]
            ref = path.split("ref=", 1)[1]
            return {"encoding": "base64",
                    "content": base64.b64encode(self.contents[(target, ref)].encode()).decode()}
        raise AssertionError("unexpected path " + path)


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

    def test_intake_rejects_non_string_files(self):
        with self.assertRaises(ContractError):
            self.intake(files=[{"filename": "docs/knowledge/note.md"}])
        self.assertEqual(self.gov.list(), [])

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

    def test_malformed_registry_shapes_are_ineligible(self):
        shapes = []
        for value in (["bad"], "bad", 3, None):
            head = copy.deepcopy(self.registry)
            head["repositories"]["example/repo"] = value
            shapes.append(head)
        bad_repos = copy.deepcopy(self.registry)
        bad_repos["repositories"] = []
        shapes.append(bad_repos)
        shapes.append([])
        for head in shapes:
            with self.subTest(head=head):
                record = self.intake(files=["config/registry.json"], head_registry=head)
                self.assertEqual(record["phase"], "ineligible")
                self.assertTrue(record["reason"])

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


class ChangedPathsTests(unittest.TestCase):
    def test_rename_collects_both_paths(self):
        paths = governance.changed_paths(
            {"changed_files": 1},
            [{"filename": "docs/knowledge/x.py", "previous_filename": "contract_master/x.py"}])
        self.assertEqual(paths, ["docs/knowledge/x.py", "contract_master/x.py"])

    def test_malformed_or_incomplete_lists_raise(self):
        cases = [
            ({"changed_files": 1}, [{"filename": "a"}, "bad"]),
            ({"changed_files": 1}, ["bad"]),
            ({"changed_files": 1}, [{"filename": 3}]),
            ({"changed_files": 1}, [{"filename": "a", "previous_filename": 3}]),
            ({}, [{"filename": "a"}]),
            ({"changed_files": 3000}, [{"filename": "a"}]),
            ({"changed_files": 2}, [{"filename": "a"}]),
            ({"changed_files": True}, [{"filename": "a"}]),
            ([], [{"filename": "a"}]),
        ]
        for pull_data, files in cases:
            with self.subTest(pull=pull_data, files=files):
                with self.assertRaises(ProviderError):
                    governance.changed_paths(pull_data, files)


class ScanTests(GovernanceFixture):
    def setUp(self):
        super().setUp()
        self.registry = scan_registry()
        self.gov = governance.Governance(self.store, self.registry, self.clock)
        head = copy.deepcopy(self.registry)
        head["repositories"]["d3-corp/corp-integrated-dashboard"]["allowed_scope"] = [
            "README.md", "docs", "src", "server", "package.json", "package-lock.json"]
        self.contents = {("config/registry.json", A): json.dumps(head)}
        self.pulls, self.files = {}, {}
        for number in range(1, 10):
            self.pulls[number] = pull(number=number, author=("d3adc3II", "User"))
        self.pulls[1]["changed_files"] = 2
        self.files[1] = [{"filename": "config/registry.json"},
                         {"filename": "docs/onboarding/repositories.md"}]
        self.pulls[2]["changed_files"] = 150
        self.files[2] = [{"filename": "docs/knowledge/note-%03d.md" % index}
                         for index in range(150)]
        self.pulls[3]["changed_files"] = 1
        self.files[3] = [{"filename": "docs/knowledge/moved.py",
                          "previous_filename": "contract_master/moved.py"}]
        self.pulls[4]["changed_files"] = 2
        self.files[4] = [{"filename": "docs/knowledge/note.md"}, "bad"]
        self.pulls[5]["changed_files"] = 3000
        self.files[5] = [{"filename": "docs/knowledge/note.md"}]
        self.pulls[6]["changed_files"] = 2
        self.files[6] = [{"filename": "docs/knowledge/note.md"}]
        self.pulls[7]["changed_files"] = 1
        self.files[7] = [{"filename": "docs/knowledge/note.md"}]
        self.pulls[8] = pull(number=8, head=C, author=("d3adc3II", "User"))
        self.pulls[8]["changed_files"] = 1
        self.files[8] = [{"filename": "config/registry.json"}]
        bad = copy.deepcopy(self.registry)
        bad["repositories"]["example/repo"] = ["bad"]
        self.contents[("config/registry.json", C)] = json.dumps(bad)
        self.pulls[9]["changed_files"] = 1
        self.files[9] = [{"filename": "docs/knowledge/note.md"}]

    def test_scan_reads_rest_shaped_files_and_isolates_failures(self):
        reader = governance.GitHubReader(api=ScanAPI(self.pulls, self.files, self.contents, B))
        result = governance.scan(self.gov, reader, self.registry, self.lease, lambda tip: True)
        records = {record["key"]: record for record in self.gov.list()}
        first = records["example/repo#1"]
        self.assertEqual(first["phase"], "verifying")
        self.assertTrue(any("Scope change for d3-corp/corp-integrated-dashboard" in item
                            for item in first["criteria"]))
        self.assertEqual(len(records["example/repo#2"]["files"]), 150)
        self.assertEqual(records["example/repo#3"]["phase"], "ineligible")
        self.assertIn("contract_master/moved.py", records["example/repo#3"]["reason"])
        for number in (4, 5, 6):
            self.assertNotIn("example/repo#" + str(number), records)
        self.assertEqual(records["example/repo#7"]["phase"], "verifying")
        self.assertEqual(records["example/repo#8"]["phase"], "ineligible")
        self.assertEqual(records["example/repo#9"]["phase"], "verifying")
        retry = {item["number"] for item in result["records"] if item.get("retry")}
        self.assertEqual(retry, {4, 5, 6})


class RefreshTests(GovernanceFixture):
    def setUp(self):
        super().setUp()
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.origin = Path(temp.name) / "origin.git"
        self.clone = Path(temp.name) / "clone"
        subprocess.run(["git", "init", "--bare", "-q", str(self.origin)], check=True)
        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.clone)], check=True,
                       stderr=subprocess.DEVNULL)
        self.git(self.clone, "config", "user.email", "test@example.invalid")
        self.git(self.clone, "config", "user.name", "Test")
        self.git(self.clone, "checkout", "-q", "-b", "main")
        (self.clone / "a.txt").write_text("base\n")
        self.git(self.clone, "add", "a.txt")
        self.git(self.clone, "commit", "-qm", "base")
        self.base = self.git(self.clone, "rev-parse", "HEAD").strip()
        self.git(self.clone, "push", "-q", "origin", "main")

    def git(self, root, *args):
        return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                              text=True).stdout

    def record(self, merged):
        with self.store.transaction() as db:
            db.execute("INSERT OR REPLACE INTO pr_reviews VALUES(?,?)", (KEY, json.dumps({
                "key": KEY, "phase": "merged", "merge_receipt": {"merged_commit": merged},
                "merge_steps": {}, "head_sha": merged})))

    def advance_remote(self, name):
        (self.clone / name).write_text("next\n")
        self.git(self.clone, "add", name)
        self.git(self.clone, "commit", "-qm", name)
        commit = self.git(self.clone, "rev-parse", "HEAD").strip()
        self.git(self.clone, "push", "-q", "origin", "main")
        self.git(self.clone, "reset", "-q", "--hard", self.base)
        return commit

    def test_fast_forwards_to_recorded_merge(self):
        commit = self.advance_remote("merged.txt")
        self.record(commit)
        (self.clone / "untracked.txt").write_text("keep\n")
        result = self.gov.refresh(self.lease, self.clone, "main", governance.git_run)
        self.assertEqual(result, {"refreshed": True, "commit": commit})
        self.assertEqual(self.git(self.clone, "rev-parse", "HEAD").strip(), commit)
        self.assertTrue((self.clone / "untracked.txt").exists())

    def test_no_op_when_base_is_current(self):
        result = self.gov.refresh(self.lease, self.clone, "main", governance.git_run)
        self.assertEqual(result, {"refreshed": False})

    def test_refuses_unrecorded_remote_commit(self):
        self.advance_remote("unrecorded.txt")
        with self.assertRaises(ContractError) as caught:
            self.gov.refresh(self.lease, self.clone, "main", governance.git_run)
        self.assertIn("outside the governance path", str(caught.exception))
        self.assertEqual(self.git(self.clone, "rev-parse", "HEAD").strip(), self.base)

    def test_refuses_dirty_tracked_file(self):
        (self.clone / "a.txt").write_text("dirty\n")
        with self.assertRaises(ContractError):
            self.gov.refresh(self.lease, self.clone, "main", governance.git_run)
        self.assertEqual(self.git(self.clone, "rev-parse", "HEAD").strip(), self.base)

    def test_refuses_wrong_branch(self):
        self.git(self.clone, "checkout", "-q", "-b", "topic")
        with self.assertRaises(ContractError):
            self.gov.refresh(self.lease, self.clone, "main", governance.git_run)


class BindingTests(GovernanceFixture):
    def test_head_move_before_verify_resets(self):
        record = self.verified("changes")
        self.assertEqual(record["changes_verdicts"], 1)
        moved = self.intake(pull=pull(head=C))
        self.assertEqual(moved["phase"], "verifying")
        self.assertEqual(moved["head_sha"], C)
        self.assertEqual(len(moved["history"]), 2)
        self.assertEqual(moved["changes_verdicts"], 1)

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

    def test_merge_confirm_failure_recovers_after_base_advance(self):
        self.verified()
        app = self.app()

        class FlakyReader:
            def __init__(self):
                self.calls = 0

            def confirm(self, *args):
                self.calls += 1
                if self.calls == 1:
                    raise ProviderError("lost acknowledgement")
                return FakeReader(app).confirm(*args)

        reader = FlakyReader()
        with self.assertRaises(ProviderError):
            self.gov.merge(self.lease, KEY, app, reader, B)
        self.assertEqual(self.gov.get(KEY)["phase"], "awaiting_merge")
        self.assertEqual(len([write for write in app.writes if write[0] == "check"]), 1)
        self.assertEqual(len([write for write in app.writes if write[0] == "approve"]), 1)
        self.assertEqual(len([write for write in app.writes if write[0] == "merge"]), 1)
        unchanged = self.intake(pull=pull(state="closed", merged=True,
                                         merged_at="2026-11-01T00:00:00Z"))
        self.assertEqual(unchanged["phase"], "awaiting_merge")
        merged = self.gov.merge(self.lease, KEY, app, reader, C)
        self.assertEqual(merged["phase"], "merged")
        self.assertIsNotNone(merged["merge_receipt"])
        self.assertEqual(len([write for write in app.writes if write[0] == "check"]), 1)
        self.assertEqual(len([write for write in app.writes if write[0] == "approve"]), 1)
        self.assertEqual(len([write for write in app.writes if write[0] == "merge"]), 1)

    def test_crash_after_merge_before_merged_step_recovers(self):
        self.verified()
        clock = self.clock

        class ClockJumpApp(FakeApp):
            def merge(self, number, commit, method="squash"):
                super().merge(number, commit, method)
                clock.now += 81 * 60

        app = ClockJumpApp(login="codex-bot[bot]", app_id=7)
        app.pulls[1] = copy.deepcopy(self.pull)
        with self.assertRaises(ContractError):
            self.gov.merge(self.lease, KEY, app, FakeReader(app), B)
        self.assertEqual(self.gov.get(KEY)["phase"], "awaiting_merge")
        self.assertEqual(len([write for write in app.writes if write[0] == "merge"]), 1)
        TurnLease(self.store, self.clock).renew(self.lease, 60)
        merged = self.gov.merge(self.lease, KEY, app, FakeReader(app), C)
        self.assertEqual(merged["phase"], "merged")
        self.assertEqual(len([write for write in app.writes if write[0] == "check"]), 1)
        self.assertEqual(len([write for write in app.writes if write[0] == "approve"]), 1)
        self.assertEqual(len([write for write in app.writes if write[0] == "merge"]), 1)

    def test_merged_at_different_head_escalates(self):
        self.verified()
        app = self.app()
        app.pulls[1].update(state="closed", merged=True, merged_at="2026-11-01T00:00:00Z")
        app.pulls[1]["head"]["sha"] = C
        with self.assertRaises(ContractError) as caught:
            self.merge(app)
        self.assertIn("not verified", str(caught.exception))
        record = self.gov.get(KEY)
        self.assertEqual(record["phase"], "escalated")
        self.assertEqual(record["reason"], "PR merged at a head that was not verified")
        self.assertEqual(app.writes, [])

    def test_409_head_move_resets_and_does_not_retry_merge(self):
        self.verified()

        class RacingApp(FakeApp):
            def __init__(self):
                super().__init__(login="codex-bot[bot]", app_id=7)
                self.merge_calls = 0

            def merge(self, number, commit, method="squash"):
                self.merge_calls += 1
                self.pulls[number]["head"]["sha"] = C
                raise github_app.GitHubWriteError(409, "head moved")

        app = RacingApp()
        app.pulls[1] = copy.deepcopy(self.pull)
        with self.assertRaises(ContractError) as caught:
            self.merge(app)
        self.assertIn("head moved before merge", str(caught.exception))
        self.assertEqual(app.merge_calls, 1)
        record = self.gov.get(KEY)
        self.assertEqual(record["phase"], "verifying")
        self.assertIsNone(record["verification"])
        self.assertEqual(record["merge_steps"], {})

    def test_409_conflict_without_head_move_escalates(self):
        self.verified()
        app = self.app()
        app.fail["merge"] = github_app.GitHubWriteError(409, "conflict")
        with self.assertRaises(ContractError) as caught:
            self.merge(app)
        self.assertIn("escalate", str(caught.exception))
        self.assertEqual(self.gov.get(KEY)["phase"], "escalated")

    def test_lease_expiry_inside_github_reads_prevents_all_mutations(self):
        for trigger in ("pull", "reviews", "check_runs"):
            with self.subTest(trigger=trigger):
                self.setUp()
                self.verified()
                clock = self.clock

                class JumpingApp(FakeApp):
                    def __init__(self):
                        super().__init__(login="codex-bot[bot]", app_id=7)

                    def _jump(self, name):
                        if name == trigger:
                            clock.now += 81 * 60

                    def pull(self, number):
                        self._jump("pull")
                        return super().pull(number)

                    def reviews(self, number):
                        self._jump("reviews")
                        return super().reviews(number)

                    def check_runs(self, commit):
                        self._jump("check_runs")
                        return super().check_runs(commit)

                app = JumpingApp()
                app.pulls[1] = copy.deepcopy(self.pull)
                with self.assertRaises(ContractError):
                    self.merge(app)
                self.assertEqual(app.writes, [])

    def test_lease_takeover_between_approve_and_merge_prevents_merge(self):
        self.verified()
        store, clock = self.store, self.clock

        class TakeoverApp(FakeApp):
            def __init__(self):
                super().__init__(login="codex-bot[bot]", app_id=7)

            def approve(self, number, commit, body):
                super().approve(number, commit, body)
                with store.transaction() as db:
                    db.execute("INSERT OR REPLACE INTO turn_lease VALUES(1,?,?)",
                               ("other", clock.now + 3600))

        app = TakeoverApp()
        app.pulls[1] = copy.deepcopy(self.pull)
        with self.assertRaises(ContractError):
            self.merge(app)
        self.assertEqual(len([write for write in app.writes if write[0] == "approve"]), 1)
        self.assertEqual([write for write in app.writes if write[0] == "merge"], [])
        self.assertEqual(self.gov.get(KEY)["phase"], "awaiting_merge")

    def test_second_changes_verdict_after_head_move_escalates(self):
        record = self.verified("changes")
        self.assertEqual(record["changes_verdicts"], 1)
        moved = self.intake(pull=pull(head=C))
        self.assertEqual(moved["phase"], "verifying")
        self.assertEqual(moved["changes_verdicts"], 1)
        record = self.gov.verify(self.lease, KEY, self.evidence(moved, "changes"))
        self.assertEqual(record["phase"], "escalated")
        self.assertEqual(record["changes_verdicts"], 2)

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
        bad = dict(evidence, merger="someone-else")
        with self.assertRaises(ContractError):
            self.gov.confirm(self.lease, KEY, bad)
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
