import copy
import unittest
from contract_master import phases
from contract_master.contracts import ContractError
from contract_master.store import Store
from support import WorkflowFixture, B, C

PHASES = ("planning", "ready", "implementing", "verifying", "rework", "awaiting_review", "done", "escalated", "superseded")

# Which phases each phase-gated operation accepts. This is the workflow policy;
# changing it should be a deliberate, reviewed edit.
ALLOWED = {
    "claim": {"planning", "ready", "implementing", "verifying", "rework", "awaiting_review"},
    "pin_context": {"planning"},
    "record_plan": {"planning"},
    "prepare_dispatch": {"ready", "rework"},
    "implementation": {"implementing"},
    "verify": {"verifying"},
    # Not rework: a new head there must go through prepare_dispatch so the attempt cap holds.
    "observe_head": {"verifying", "awaiting_review"},
    "confirm_merge": {"awaiting_review"},
    "complete": {"awaiting_review"},
    "release": {"done", "escalated"},
    "supersede": {"planning", "ready", "implementing", "verifying", "rework", "awaiting_review"},
    "handoff": set(PHASES),
    "record_orca_receipt": set(PHASES),
}
DENIAL = {"claim": "Task is settled"}


class MergedProvider:
    def confirm(self, repo, url, commit):
        return {"accepted_commit": commit, "merged_commit": C, "human_reviewer": "reviewer", "human_merger": "merger",
                "pr_url": url, "evidence": "Fake provider: merged + human approval on exact head"}


class PhaseGateTests(WorkflowFixture):
    def operations(self):
        tid, tok = self.task_id, self.token
        m = self.manager
        url = "https://example.invalid/pull/1"
        return {
            "claim": lambda: m.claim(tid, "coordinator", self.root / "workspace", "task/one"),
            "pin_context": lambda: m.pin_context(tid, tok, self.reference),
            "record_plan": lambda: m.record_plan(tid, tok, dict(self.plan, revision=2)),
            "prepare_dispatch": lambda: m.prepare_dispatch(tid, tok, self.runner),
            "implementation": lambda: m.implementation(tid, tok, copy.deepcopy(self.result)),
            "verify": lambda: m.verify(tid, tok, self.verification()),
            "observe_head": lambda: m.observe_head(tid, tok, C),
            "confirm_merge": lambda: m.confirm_merge(tid, tok, MergedProvider(), url),
            "complete": lambda: m.complete(tid, tok, self.completion()),
            "release": lambda: m.release(tid, tok, "Orca settlement accepted"),
            "supersede": lambda: m.supersede(tid, tok, "Orca settlement accepted"),
            "handoff": lambda: m.handoff(tid, tok, self.handoff()),
            "record_orca_receipt": lambda: m.record_orca_receipt(tid, tok, {
                "run_id": "run", "orca_task_id": "ot", "dispatch_id": "od", "status": "unverifiable",
                "request_id": m.task(tid)["dispatch_request_id"], "recovery": "Inspect original Dispatch"}),
        }

    def set_phase(self, baseline, ownership, phase):
        # Reset task and ownership so an earlier successful call (e.g. release) cannot leak into the next pair.
        with self.manager.store.transaction() as db:
            Store.save(db, dict(copy.deepcopy(baseline), phase=phase))
            db.execute("DELETE FROM ownership WHERE task=?", (self.task_id,))
            db.execute("INSERT INTO ownership VALUES(?,?,?,?)", ownership)

    def test_every_phase_operation_pair_matches_policy(self):
        self.start(); self.implement()
        baseline = self.manager.task(self.task_id)
        with self.manager.store.transaction() as db:
            ownership = tuple(db.execute("SELECT workspace,task,token,owner FROM ownership WHERE task=?", (self.task_id,)).fetchone())
        operations = self.operations()
        self.assertEqual(set(operations), set(ALLOWED))
        for name, call in operations.items():
            for phase in PHASES:
                with self.subTest(operation=name, phase=phase):
                    self.set_phase(baseline, ownership, phase)
                    denial = DENIAL.get(name, "Invalid phase")
                    if phase in ALLOWED[name]:
                        # Allowed phases may still fail later checks, but never on the phase gate.
                        try:
                            call()
                        except ContractError as exc:
                            self.assertNotIn(denial, str(exc))
                    else:
                        with self.assertRaises(ContractError) as caught:
                            call()
                        self.assertIn(denial, str(caught.exception))

    def test_manager_table_matches_reviewed_policy(self):
        self.assertEqual(set(phases.ALL), set(PHASES))
        self.assertEqual({k: set(v) for k, v in phases.OPERATIONS.items()}, {k: v for k, v in ALLOWED.items() if k != "claim"})
        self.assertEqual(set(phases.TRANSITIONS), set(PHASES))
        for source, targets in phases.TRANSITIONS.items():
            self.assertTrue(set(targets) <= set(PHASES), source)
        for settled in phases.SETTLED:
            self.assertEqual(phases.TRANSITIONS[settled], ())

    def test_illegal_phase_change_is_rejected(self):
        for source, target in (("planning", "implementing"), ("rework", "verifying"), ("done", "verifying"),
                               ("escalated", "implementing"), ("implementing", "done")):
            with self.subTest(source=source, target=target):
                task = {"phase": source}
                with self.assertRaises(ContractError): phases.advance(task, target)
                self.assertEqual(task["phase"], source)

    def test_rework_cannot_skip_dispatch_via_new_head(self):
        self.start(); self.implement()
        self.manager.verify(self.task_id, self.token, self.verification(False))
        self.assertEqual(self.manager.task(self.task_id)["phase"], "rework")
        with self.assertRaises(ContractError): self.manager.observe_head(self.task_id, self.token, C)
        task = self.manager.task(self.task_id)
        self.assertEqual((task["phase"], task["attempt"], task["output_commit"]), ("rework", 1, B))
        self.assertEqual(self.manager.prepare_dispatch(self.task_id, self.token, self.runner)["attempt"], 2)


if __name__ == "__main__":
    unittest.main()
