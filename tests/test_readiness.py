import copy
import json
import unittest
from contract_master.contracts import ROOT
from contract_master.readiness import report


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.registry = json.loads((ROOT / "config" / "registry.json").read_text())
        self.repo_id = next(iter(self.registry["repositories"]))

    def blockers(self, **updates):
        registry = copy.deepcopy(self.registry)
        registry["repositories"][self.repo_id].update(updates)
        return report(registry)["blockers"]

    def test_missing_codex_merge_identity_blocks(self):
        self.assertTrue(any("merge_identity" in b for b in self.blockers(merge_identity=None)))
        identity = {"login": "d3hl-codex[bot]", "type": "Bot"}
        self.assertFalse(any("merge_identity" in b for b in self.blockers(merge_identity=identity)))

    def test_role_assignment_is_enforced(self):
        self.assertFalse(any("planning must be Claude" in b for b in self.blockers()))
        for field, value in (("planning_runner", "codex"), ("verification_runner", "claude"), ("merge_runner", "human")):
            self.assertTrue(any("planning must be Claude" in b for b in self.blockers(**{field: value})), field)


    def test_repository_labels_are_unique_and_prefixed(self):
        self.assertFalse(any("Repository label" in b for b in self.blockers(linear_label="repo:contract-master")))
        self.assertTrue(any("must start with repo:" in b for b in self.blockers(linear_label="contract-master")))
        registry = copy.deepcopy(self.registry)
        registry["repositories"][self.repo_id]["linear_label"] = "repo:x"
        registry["repositories"]["other/repo"] = dict(registry["repositories"][self.repo_id])
        self.assertTrue(any("more than one repository" in b for b in report(registry)["blockers"]))

if __name__ == "__main__":
    unittest.main()
