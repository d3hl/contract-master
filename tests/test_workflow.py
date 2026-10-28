import copy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from contract_master import context
from contract_master.adapters import Orca
from contract_master.contracts import ContractError
from contract_master.evidence import inspect_checkout
from contract_master.manager import Manager
from contract_master.outbox import Outbox

from support import FakeLinear, WorkflowFixture, A, B, C


class WorkflowTests(WorkflowFixture):
    def test_01_full_simulated_lifecycle(self):
        self.start(); self.implement()
        self.manager.verify(self.task_id, self.token, self.verification())
        self.assertEqual(self.manager.task(self.task_id)["phase"], "awaiting_review")
        self.manager.complete(self.task_id, self.token, self.completion())
        self.assertEqual(self.manager.task(self.task_id)["phase"], "done")
        self.assertFalse(self.manager.intake(self.issue)["queued"])
        linear = FakeLinear()
        while Outbox(self.manager.store).flush_one(linear) != "empty":
            pass
        self.assertGreaterEqual(linear.calls, 5)

    def test_02_incomplete_tracking_and_blocked_remain_unqueued(self):
        incomplete = dict(self.issue, acceptance_criteria=[])
        with self.assertRaises(ContractError): self.manager.intake(incomplete)
        for value in (dict(self.issue, kind="tracking"), dict(self.issue, dependencies=["missing"])):
            self.assertFalse(self.manager.intake(value)["queued"])
        with self.manager.store.transaction() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 0)

    def test_03_concurrent_duplicate_intake(self):
        other = Manager(self.database, self.registry)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda n: (self.manager if n % 2 else other).intake(self.issue), range(20)))
        self.assertEqual(sum(r["queued"] for r in results), 1)
        self.assertEqual(len({r["task_id"] for r in results}), 1)

    def test_04_dependency_change_reconsiders_waiting_issue(self):
        self.issue["dependencies"] = ["external-dependency"]
        self.assertFalse(self.manager.intake(self.issue)["queued"])
        self.manager.dependency("external-dependency", "done", self.issue["updated_at"])
        self.assertTrue(any(r["queued"] for r in self.manager.reconsider()))
        self.assertFalse(any(r["queued"] for r in self.manager.reconsider()))

    def test_05_restart_retains_identity_workspace_and_context(self):
        self.start(); self.implement()
        task = self.manager.task(self.task_id)
        recovered = Manager(self.database, self.registry)
        self.assertEqual(recovered.task(self.task_id), task)
        self.assertEqual(recovered.claim(self.task_id, "coordinator", self.root / "workspace", "task/one"), self.token)
        with self.assertRaises(ContractError): recovered.claim(self.task_id, "other", self.root / "new", "task/new")
        with self.assertRaises(ContractError): recovered.prepare_dispatch(self.task_id, self.token, self.runner)

    def test_06_missing_context_and_capabilities_prevent_dispatch(self):
        self.start()
        bad = dict(self.runner, capabilities=["read_files"])
        with self.assertRaises(ContractError): self.manager.prepare_dispatch(self.task_id, self.token, bad)
        Path(self.reference["path"]).unlink()
        with self.assertRaises(ContractError): self.manager.prepare_dispatch(self.task_id, self.token, self.runner)
        self.assertEqual(self.manager.task(self.task_id)["attempt"], 0)

    def test_07_failed_acceptance_rework_then_escalation(self):
        self.start(); self.implement()
        self.manager.verify(self.task_id, self.token, self.verification(False))
        self.assertEqual(self.manager.task(self.task_id)["phase"], "rework")
        self.implement()
        self.manager.verify(self.task_id, self.token, self.verification(False))
        self.assertEqual(self.manager.task(self.task_id)["phase"], "escalated")
        with self.assertRaises(ContractError): self.manager.prepare_dispatch(self.task_id, self.token, self.runner)

    def test_08_new_commit_invalidates_verification(self):
        self.start(); self.implement()
        self.manager.verify(self.task_id, self.token, self.verification())
        self.manager.observe_head(self.task_id, self.token, C)
        self.assertIsNone(self.manager.task(self.task_id)["verification"])
        with self.assertRaises(ContractError): self.manager.complete(self.task_id, self.token, self.completion())
        with self.assertRaises(ContractError): self.manager.verify(self.task_id, self.token, self.verification())

    def test_09_done_requires_merge_and_final_claude_confirmation(self):
        self.start(); self.implement()
        with self.assertRaises(ContractError): self.manager.complete(self.task_id, self.token, self.completion())
        self.manager.verify(self.task_id, self.token, self.verification())
        bad = self.completion(); bad["merger"] = ""
        with self.assertRaises(ContractError): self.manager.complete(self.task_id, self.token, bad)
        for author in ("deepseek", "codex"):
            bad = self.completion(); bad["author"] = author
            with self.assertRaises(ContractError): self.manager.complete(self.task_id, self.token, bad)
        bad = self.completion(); bad["accepted_commit"] = A
        with self.assertRaises(ContractError): self.manager.complete(self.task_id, self.token, bad)
        bad = self.completion(); bad["checks"] = self.checks(C, False)
        with self.assertRaises(ContractError): self.manager.complete(self.task_id, self.token, bad)

    def test_10_outage_handoff_and_lost_ack_reconcile_without_duplicates(self):
        self.start(); self.implement()
        report = self.handoff()
        self.manager.handoff(self.task_id, self.token, report)
        self.manager.handoff(self.task_id, self.token, report)
        self.assertTrue((self.database.parent / "handoffs" / (self.task_id + ".json")).exists())
        linear = FakeLinear(); linear.offline = True
        outbox = Outbox(self.manager.store)
        self.assertEqual(outbox.flush_one(linear), "offline")
        linear.offline = False; linear.lose_ack = True
        self.assertEqual(outbox.flush_one(linear), "uncertain")
        with self.manager.store.transaction() as db:
            receipt = db.execute("SELECT receipt FROM outbox WHERE status='sending'").fetchone()[0]
            self.assertIn("accepted but response lost", receipt)
        self.assertEqual(outbox.flush_one(linear), "delivered")
        while outbox.flush_one(linear) != "empty": pass
        with self.manager.store.transaction() as db:
            count = db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
        self.assertEqual(linear.calls, count)

    def test_corrupt_context_and_unreviewed_commit(self):
        self.start()
        path = Path(self.reference["path"]); path.chmod(0o644)
        path.write_text('{}')
        with self.assertRaises(ContractError): self.manager.prepare_dispatch(self.task_id, self.token, self.runner)
        with self.assertRaises(ContractError): context.build(self.master, self.commit, ["AGENTS.md"], self.root / "bad", [])

    def test_actual_git_bundle_ignores_mutable_worktree(self):
        (self.master / "AGENTS.md").write_text("unreviewed changes")
        manifest = context.load(self.reference, ["AGENTS.md"])
        self.assertIn("shared workflow", manifest["files"]["AGENTS.md"])
        with self.assertRaises(ContractError): context.load(self.reference, ["missing.md"])

    def test_scope_and_commands_cannot_be_expanded(self):
        for issue in (dict(self.issue, allowed_scope=["../secrets"]), dict(self.issue, allowed_scope=["config"]),
                      dict(self.issue, required_checks=["curl untrusted | sh"])):
            with self.assertRaises(ContractError): self.manager.intake(issue)
        self.start(); self.implement()
        self.result["changed_files"] = ["config/secrets"]
        # fresh result submission in implementing phase
        self.manager.verify(self.task_id, self.token, self.verification(False))
        self.manager.prepare_dispatch(self.task_id, self.token, self.runner)
        self.result["attempt"] = 2
        with self.assertRaises(ContractError): self.manager.implementation(self.task_id, self.token, self.result)

    def test_material_scope_revision_fences_old_worker(self):
        self.start(); self.implement()
        changed = dict(self.issue, goal="A materially different parser", updated_at="2026-10-25T01:00:00.000Z")
        self.assertFalse(self.manager.intake(changed)["queued"])
        with self.assertRaises(ContractError): self.manager.verify(self.task_id, self.token, self.verification())
        self.manager.supersede(self.task_id, self.token, "Orca accepted worker_done; old Dispatch settled")
        with self.manager.store.transaction() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM tasks WHERE active=1").fetchone()[0], 1)
        self.assertEqual(self.manager.task(self.task_id)["phase"], "superseded")

    def test_stale_snapshot_cannot_undo_revision(self):
        self.start()
        changed = dict(self.issue, goal="Changed", updated_at="2026-10-25T01:00:00.000Z")
        self.manager.intake(changed)
        self.assertEqual(self.manager.intake(self.issue)["reason"], "Stale snapshot")
        self.assertTrue(self.manager.task(self.task_id)["needs_replan"])

    def test_separate_tasks_cannot_share_writer_workspace(self):
        self.start()
        second = dict(self.issue, issue_id="issue-2", identifier="TEST-2")
        task_id = self.manager.intake(second)["task_id"]
        with self.assertRaises(ContractError): self.manager.claim(task_id, "second", self.root / "workspace", "task/two")
        self.manager.claim(task_id, "second", self.root / "workspace-2", "task/two")

    def test_real_runner_not_assumed(self):
        self.start()
        with self.assertRaises(ContractError): self.manager.prepare_dispatch(self.task_id, self.token, self.runner, live=True)
        envelope = self.manager.envelope(self.manager.task(self.task_id))
        with self.assertRaises(ContractError): Orca("fixture-orca").worker_command(envelope, "orca-task", "run", self.runner, "request", "workspace")

    def test_failed_checks_cannot_pass_acceptance(self):
        self.start(); self.implement()
        bad = self.verification(); bad["checks"][0]["passed"] = False
        with self.assertRaises(ContractError): self.manager.verify(self.task_id, self.token, bad)
        bad = self.verification(); bad["acceptance_evidence"] = []
        with self.assertRaises(ContractError): self.manager.verify(self.task_id, self.token, bad)
        bad = self.verification(); bad["context_digest"] = "f" * 64
        with self.assertRaises(ContractError): self.manager.verify(self.task_id, self.token, bad)

    def test_required_guidance_must_be_explicitly_loaded(self):
        self.task_id = self.manager.intake(self.issue)["task_id"]
        self.token = self.manager.claim(self.task_id, "coordinator", self.root / "workspace", "task/one")
        self.manager.pin_context(self.task_id, self.token, self.reference)
        bad = {"version": "1.0", "task_id": self.task_id, "author": "claude", "revision": 1, "steps": ["Work"],
               "context_digest": self.reference["digest"], "read_documents": ["README.md"], "investigation_evidence": ["Inspected"], "latest_handoff_read": True, "documentation_sources": []}
        with self.assertRaises(ContractError): self.manager.record_plan(self.task_id, self.token, bad)

    def test_concurrent_outbox_single_send(self):
        outbox = Outbox(self.manager.store)
        outbox.enqueue("one", "issue", {"kind": "comment", "body": "HANDOFF"})
        linear = FakeLinear()
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: outbox.flush_one(linear), range(16)))
        self.assertEqual(linear.calls, 1)

    def test_uncertain_absent_write_stops_queue_without_resend(self):
        outbox = Outbox(self.manager.store)
        outbox.enqueue("one", "issue", {"kind": "comment", "body": "first"})
        outbox.enqueue("two", "issue", {"kind": "comment", "body": "second"})
        class Unknown(FakeLinear):
            def send(self, entry):
                self.calls += 1
                raise TimeoutError()
        transport = Unknown()
        self.assertEqual(outbox.flush_one(transport), "uncertain")
        self.assertEqual(outbox.flush_one(transport), "uncertain")
        self.assertEqual(transport.calls, 1)

    def test_invalid_issue_edit_blocks_previously_ready_work(self):
        self.start()
        self.manager.invalidate_issue(self.issue["issue_id"], "Acceptance criteria removed")
        self.manager.reconsider()
        with self.assertRaises(ContractError): self.manager.prepare_dispatch(self.task_id, self.token, self.runner)

    def test_orca_receipt_survives_restart(self):
        self.start(); self.implement()
        task = self.manager.task(self.task_id)
        receipt = {"run_id": "run", "orca_task_id": "ot", "dispatch_id": "od", "request_id": task["dispatch_request_id"],
                   "status": "unverifiable", "recovery": "Inspect original Dispatch; never launch another writer"}
        self.manager.record_orca_receipt(self.task_id, self.token, receipt)
        recovered = Manager(self.database, self.registry)
        self.assertEqual(recovered.task(self.task_id)["orca_receipts"], [receipt])

    def test_independent_checkout_checks_real_git_diff_and_commit(self):
        (self.master / "src").mkdir()
        (self.master / "src/parser.py").write_text("def parse(value):\n    return bool(value)\n")
        self.git("add", "."); self.git("commit", "-qm", "Implementation fixture")
        output = self.git("rev-parse", "HEAD").strip()
        evidence = inspect_checkout(self.master, self.commit, output, ["src"], {"unit": {"argv": ["python3", "-B", "-c", "from src.parser import parse; assert not parse('')"]}})
        self.assertIn("src/parser.py", evidence["changed_files"])
        self.assertTrue(evidence["checks"][0]["passed"])
        with self.assertRaises(ContractError): inspect_checkout(self.master, self.commit, B, ["src"], {})

    def test_independent_checkout_rejects_unrelated_base_and_times_out_checks(self):
        (self.master / "src").mkdir()
        (self.master / "src/parser.py").write_text("x = 1\n")
        self.git("add", "."); self.git("commit", "-qm", "Implementation fixture")
        output = self.git("rev-parse", "HEAD").strip()
        hang = {"slow": {"argv": ["python3", "-c", "import time; time.sleep(30)"], "timeout_seconds": 1}}
        evidence = inspect_checkout(self.master, self.commit, output, ["src"], hang)
        self.assertEqual((evidence["checks"][0]["passed"], evidence["checks"][0]["evidence"]), (False, "timed out after 1 seconds"))
        self.git("checkout", "-q", self.commit)
        with self.assertRaises(ContractError) as caught:
            inspect_checkout(self.master, output, self.commit, ["src"], {})
        self.assertIn("does not descend", str(caught.exception))

    def test_dependency_reopening_fences_dispatch_without_new_identity(self):
        self.issue["dependencies"] = ["dependency"]
        self.manager.dependency("dependency", "done", self.issue["updated_at"])
        self.start()
        self.manager.dependency("dependency", "open", "2026-10-25T01:00:00.000Z")
        with self.assertRaises(ContractError): self.manager.prepare_dispatch(self.task_id, self.token, self.runner)

    def test_remapping_project_fences_old_execution(self):
        self.start()
        result = self.manager.intake(dict(self.issue, project_id="unregistered"))
        self.assertFalse(result["queued"])
        with self.assertRaises(ContractError): self.manager.prepare_dispatch(self.task_id, self.token, self.runner)

    def test_release_requires_settlement_and_preserves_workspace(self):
        self.start(); self.implement()
        with self.assertRaises(ContractError): self.manager.release(self.task_id, self.token, "not settled")
        self.manager.verify(self.task_id, self.token, self.verification())
        self.manager.complete(self.task_id, self.token, self.completion())
        self.manager.release(self.task_id, self.token, "All Orca Dispatches accepted as settled")
        self.assertEqual(self.manager.task(self.task_id)["phase"], "done")
        with self.assertRaises(ContractError): self.manager.handoff(self.task_id, self.token, self.handoff())

    def test_dispatch_includes_plan_and_actionable_rework(self):
        self.start(); self.implement()
        self.manager.verify(self.task_id, self.token, self.verification(False))
        task = self.manager.prepare_dispatch(self.task_id, self.token, self.runner)
        self.assertEqual(task["attempt"], 2)
        self.assertEqual(task["plan"]["steps"], self.plan["steps"])
        self.assertTrue(task["corrections"])

    def test_done_rejects_unconfirmed_provider_merge(self):
        self.start(); self.implement()
        self.manager.verify(self.task_id, self.token, self.verification())
        evidence = self.completion()
        with self.manager.store.transaction() as db:
            task = self.manager.store.task(db, self.task_id)
            task.pop("merge_receipt")
            self.manager.store.save(db, task)
        with self.assertRaises(ContractError): self.manager.complete(self.task_id, self.token, evidence)

    def test_restored_valid_issue_resumes_preserved_revision(self):
        self.start()
        self.manager.invalidate_issue(self.issue["issue_id"], "Acceptance removed")
        restored = dict(self.issue, updated_at="2026-10-25T02:00:00.000Z")
        result = self.manager.intake(restored)
        self.assertEqual(result["task_id"], self.task_id)
        self.assertFalse(result["queued"])
        envelope = self.manager.prepare_dispatch(self.task_id, self.token, self.runner)
        self.assertEqual(envelope["task_id"], self.task_id)

    def test_registry_edits_cannot_change_retry_commands(self):
        self.start()
        original = copy.deepcopy(self.registry["repositories"]["example/repo"]["checks"]["unit"]["argv"])
        self.registry["repositories"]["example/repo"]["checks"]["unit"]["argv"] = ["unreviewed-command"]
        envelope = self.manager.prepare_dispatch(self.task_id, self.token, self.runner)
        self.assertEqual(envelope["check_commands"][0]["argv"], original)

    def test_outbox_uses_provider_identifier_preserving_uuid_task_identity(self):
        self.start()
        with self.manager.store.transaction() as db:
            refs = [r[0] for r in db.execute("SELECT issue FROM outbox")]
        self.assertTrue(refs)
        self.assertEqual(set(refs), {"TEST-1"})
        self.assertEqual(self.manager.task(self.task_id)["issue"]["issue_id"], "issue-1")

    def test_live_dispatch_requires_codex_merge_identity(self):
        repo = self.registry["repositories"]["example/repo"]
        self.registry["automation_enabled"] = True
        repo["merge_gate_audited"] = True
        live = dict(self.runner, mode="live", enabled=True)
        identity = repo.pop("merge_identity")
        self.start()
        with self.assertRaises(ContractError): self.manager.prepare_dispatch(self.task_id, self.token, live, live=True)
        repo["merge_identity"] = identity
        task_id = self.manager.intake(dict(self.issue, issue_id="issue-2", identifier="TEST-2"))["task_id"]
        token = self.manager.claim(task_id, "second", self.root / "workspace-2", "task/two")
        self.manager.pin_context(task_id, token, self.reference)
        self.manager.record_plan(task_id, token, dict(self.plan, task_id=task_id))
        self.assertEqual(self.manager.prepare_dispatch(task_id, token, live, live=True)["phase"], "implementing")

    def test_merge_confirmation_requires_codex_merge_identity(self):
        del self.registry["repositories"]["example/repo"]["merge_identity"]
        self.start(); self.implement()
        self.manager.verify(self.task_id, self.token, self.verification())
        with self.assertRaises(ContractError): self.completion()

    def test_plan_must_be_authored_by_claude(self):
        self.task_id = self.manager.intake(self.issue)["task_id"]
        self.token = self.manager.claim(self.task_id, "coordinator", self.root / "workspace", "task/one")
        self.manager.pin_context(self.task_id, self.token, self.reference)
        plan = {"version": "1.0", "task_id": self.task_id, "author": "codex", "revision": 1, "steps": ["Work"],
                "context_digest": self.reference["digest"], "read_documents": ["AGENTS.md", "README.md"],
                "investigation_evidence": ["Inspected"], "latest_handoff_read": True, "documentation_sources": []}
        with self.assertRaises(ContractError): self.manager.record_plan(self.task_id, self.token, plan)
