import argparse
from contract_master import github_app
from contract_master.__main__ import github_writes
from contract_master.contracts import ContractError, ProviderError
from support import WorkflowFixture, FakeApp, FakeReader, A, B, C


def writes(app, kind):
    return [w for w in app.writes if w[0] == kind]


class OpenPullRequestTests(WorkflowFixture):
    def ready(self):
        self.start(); self.implement()
        self.app = FakeApp()

    def test_pushes_and_opens_with_status_neutral_link(self):
        self.ready()
        record = self.manager.open_pr(self.task_id, self.token, self.app)
        self.assertEqual(record["number"], 1)
        self.assertEqual(writes(self.app, "push"), [("push", B, "task/one")])
        body = writes(self.app, "open")[0][3]
        self.assertTrue(body.startswith("Related to TEST-1"))
        self.assertNotRegex(body, r"(?i)\b(fix(es)?|close[sd]?|resolve[sd]?)\b")
        self.assertEqual(self.manager.task(self.task_id)["pull_request"]["url"], "https://github.com/example/repo/pull/1")

    def test_rerun_reuses_pr_without_new_writes(self):
        self.ready()
        self.manager.open_pr(self.task_id, self.token, self.app)
        before = list(self.app.writes)
        self.manager.open_pr(self.task_id, self.token, self.app)
        self.assertEqual(self.app.writes, before)

    def test_refuses_branch_with_issue_identifier_and_closed_pr(self):
        self.ready()
        with self.manager.store.transaction() as db:
            task = self.manager.store.task(db, self.task_id)
            task["branch"] = "task/test-1-parser"
            self.manager.store.save(db, task)
        with self.assertRaises(ContractError): self.manager.open_pr(self.task_id, self.token, self.app)
        self.assertEqual(self.app.writes, [])
        with self.manager.store.transaction() as db:
            task = self.manager.store.task(db, self.task_id)
            task["branch"] = "task/one"
            self.manager.store.save(db, task)
        self.manager.open_pr(self.task_id, self.token, self.app)
        self.app.pulls[1]["state"] = "closed"
        with self.assertRaises(ContractError): self.manager.open_pr(self.task_id, self.token, self.app)

    def test_rerun_after_merge_records_existing_pr(self):
        self.ready()
        self.manager.open_pr(self.task_id, self.token, self.app)
        self.app.pulls[1].update(state="closed", merged_at="2026-10-29T00:00:00Z")
        before = list(self.app.writes)
        self.assertEqual(self.manager.open_pr(self.task_id, self.token, self.app)["number"], 1)
        self.assertEqual(self.app.writes, before)

    def test_not_before_an_output_commit(self):
        self.start()
        with self.assertRaises(ContractError): self.manager.open_pr(self.task_id, self.token, FakeApp())


class CodexMergeTests(WorkflowFixture):
    def ready(self, opener=("coordinator", "User")):
        self.start(); self.implement()
        self.app = FakeApp(opener=opener)
        self.manager.open_pr(self.task_id, self.token, self.app)
        self.manager.verify(self.task_id, self.token, self.verification())

    def merge(self):
        return self.manager.codex_merge(self.task_id, self.token, self.app, FakeReader(self.app))

    def test_checks_approves_merges_exact_commit_then_completes(self):
        self.ready()
        receipt = self.merge()
        self.assertEqual([w[0] for w in self.app.writes[-3:]], ["check", "approve", "merge"])
        self.assertEqual(writes(self.app, "merge"), [("merge", 1, B)])
        self.assertEqual(receipt["merger"], "codex-bot[bot]")
        task = self.manager.task(self.task_id)
        self.assertEqual(task["merge_steps"], {"check": B, "approved": B, "merged": B})
        evidence = self.completion(confirm=False)
        evidence["pr_url"] = "https://github.com/example/repo/pull/1"
        self.manager.complete(self.task_id, self.token, evidence)
        self.assertEqual(self.manager.task(self.task_id)["phase"], "done")

    def test_rerun_after_each_crash_point_never_duplicates(self):
        for point in ("approve", "merge"):
            with self.subTest(point=point):
                self.setUp(); self.ready()
                self.app.fail[point] = ProviderError("connection reset")
                with self.assertRaises(ProviderError): self.merge()
                self.merge()
                self.assertEqual(len(writes(self.app, "check")), 1)
                self.assertEqual(len(writes(self.app, "approve")), 1)
                self.assertEqual(len(writes(self.app, "merge")), 1)

    def test_rerun_after_merge_only_confirms(self):
        self.ready()
        class Down:
            def confirm(self, *args): raise ProviderError("GitHub read failed")
        with self.assertRaises(ProviderError):
            self.manager.codex_merge(self.task_id, self.token, self.app, Down())
        self.merge()
        self.assertEqual(len(writes(self.app, "merge")), 1)

    def test_moved_head_returns_to_verification(self):
        self.ready()
        self.app.pulls[1]["head"]["sha"] = C
        with self.assertRaises(ContractError): self.merge()
        task = self.manager.task(self.task_id)
        self.assertEqual((task["phase"], task["output_commit"]), ("verifying", C))
        self.assertEqual(writes(self.app, "merge"), [])

    def test_refusals_make_no_writes(self):
        cases = {
            "own PR": lambda: self.ready(opener=("codex-bot[bot]", "Bot")),
            "human veto": lambda: (self.ready(), self.app.review_list.append(
                {"user": {"login": "person", "type": "User"}, "state": "CHANGES_REQUESTED", "commit_id": A})),
            "wrong app": lambda: (self.ready(), setattr(self.app, "login", "other-bot[bot]")),
        }
        for name, arrange in cases.items():
            with self.subTest(name):
                self.setUp(); arrange()
                before = list(self.app.writes)
                with self.assertRaises(ContractError): self.merge()
                self.assertEqual(self.app.writes, before)

    def test_needs_open_pr_and_passing_verdict(self):
        self.start(); self.implement()
        self.manager.verify(self.task_id, self.token, self.verification())
        self.app = FakeApp()
        with self.assertRaises(ContractError): self.merge()
        self.setUp(); self.start(); self.implement()
        self.app = FakeApp()
        with self.assertRaises(ContractError): self.merge()  # still verifying: phase gate

    def test_unmergeable_pr_stops_for_escalation(self):
        self.ready()
        self.app.fail["merge"] = github_app.GitHubWriteError(405, "Required status check is expected")
        with self.assertRaises(ContractError) as caught: self.merge()
        self.assertIn("escalate", str(caught.exception))
        self.assertIn("405", self.manager.task(self.task_id)["merge_steps"]["stopped"])


class CommandTests(WorkflowFixture):
    def args(self, command, live=False):
        return argparse.Namespace(command=command, task=self.task_id, token=self.token, live=live)

    def test_dry_run_reports_without_writes_and_live_needs_gates(self):
        self.start(); self.implement()
        for command in ("open-pr", "codex-merge"):
            result = github_writes(self.manager, self.registry, self.args(command))
            self.assertTrue(result["dry_run"])
            self.assertTrue(result["blockers"])
            with self.assertRaises(ContractError):
                github_writes(self.manager, self.registry, self.args(command, live=True))
        self.assertNotIn("pull_request", self.manager.task(self.task_id))
