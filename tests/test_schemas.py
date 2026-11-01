import copy
import unittest
from contract_master import contracts, phases
from contract_master.contracts import ContractError, check_schema, validate
from support import A, B, C, WorkflowFixture

try:
    import jsonschema
except ImportError:  # optional; CI installs it
    jsonschema = None

NAMES = ("issue", "task", "plan", "implementation-result", "verification-result", "completion", "handoff",
         "runner", "governance-verification", "governance-completion")


class SchemaTests(WorkflowFixture):
    def payloads(self):
        self.start(); self.implement()
        envelope = self.manager.envelope(self.manager.task(self.task_id))
        governance_verification = {
            "version": "1.0", "key": "example/repo#1", "author": "codex", "head_sha": A, "base_sha": B,
            "verdict": "pass",
            "acceptance_evidence": [{"criterion": "Scope stays bounded", "passed": True, "evidence": "diff reviewed"}],
            "checks": [{"id": "unit", "commit": A, "passed": True, "evidence": "suite passed"}],
            "corrections": [], "diff_evidence": "git diff base..head reviewed"}
        governance_completion = {
            "version": "1.0", "key": "example/repo#1", "author": "claude", "accepted_commit": A,
            "merged_commit": C, "merger": "codex-bot[bot]",
            "correspondence_evidence": "Merged tree matches the reviewed head",
            "acceptance_evidence": ["Acceptance reconfirmed on the merged commit"],
            "checks": [{"id": "unit", "commit": C, "passed": True, "evidence": "suite passed"}]}
        return {"issue": self.issue, "task": envelope, "plan": self.plan, "implementation-result": self.result,
                "verification-result": self.verification(), "completion": self.completion(),
                "handoff": self.handoff(), "runner": self.runner,
                "governance-verification": governance_verification,
                "governance-completion": governance_completion}

    @staticmethod
    def broken(name, payload):
        """Payloads every validator must reject: missing field, unknown field, prefixed SHA."""
        schema = contracts.schema(name)
        cases = {}
        missing = copy.deepcopy(payload); missing.pop(schema["required"][0])
        cases["missing " + schema["required"][0]] = missing
        cases["unknown field"] = dict(copy.deepcopy(payload), unexpected=1)
        for key, rule in schema["properties"].items():
            if isinstance(payload.get(key), str) and "{40}" in rule.get("pattern", ""):
                cases["prefixed " + key] = dict(copy.deepcopy(payload), **{key: "zz" + payload[key]})
        return cases

    def test_all_contract_schemas_load(self):
        for name in NAMES:
            with self.subTest(name=name):
                contracts.schema(name)

    def test_unsupported_schema_rules_are_rejected(self):
        for bad in ({"type": "string", "maxLength": 3}, {"type": "number"}, {"type": "string", "pattern": "[0-9]+"},
                    {"type": "object", "additionalProperties": {"type": "string"}},
                    {"type": "object", "properties": {"nested": {"oneOf": []}}}):
            with self.subTest(schema=bad):
                with self.assertRaises(ContractError): check_schema(bad)

    def test_phase_enums_match_phase_table(self):
        for name in ("task", "handoff"):
            self.assertEqual(contracts.schema(name)["properties"]["phase"]["enum"], list(phases.ALL))

    def test_task_embeds_current_plan_schema(self):
        plan = {k: v for k, v in contracts.schema("plan").items() if k not in ("$schema", "$id", "title")}
        self.assertEqual(contracts.schema("task")["properties"]["plan"], plan)

    def test_broken_payloads_rejected(self):
        for name, payload in self.payloads().items():
            for label, bad in self.broken(name, payload).items():
                with self.subTest(name=name, case=label):
                    with self.assertRaises(ContractError): validate(name, bad)

    def test_whitespace_only_text_is_rejected(self):
        # Deliberately stricter than standard JSON Schema minLength.
        with self.assertRaises(ContractError): validate("plan", dict(self.payloads()["plan"], steps=["   "]))

    @unittest.skipIf(jsonschema is None, "jsonschema not installed")
    def test_reference_validator_agrees(self):
        for name, payload in self.payloads().items():
            schema = contracts.schema(name)
            reference = jsonschema.validators.validator_for(schema, default=jsonschema.Draft7Validator)
            reference.check_schema(schema)
            validator = reference(schema)
            with self.subTest(name=name, case="valid"):
                validate(name, payload)
                self.assertEqual(list(validator.iter_errors(payload)), [])
            for label, bad in self.broken(name, payload).items():
                with self.subTest(name=name, case=label):
                    self.assertTrue(list(validator.iter_errors(bad)))


if __name__ == "__main__":
    unittest.main()
