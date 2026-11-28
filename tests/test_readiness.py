import copy
import json
import unittest
from contract_master.contracts import ROOT, within
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

    def test_registered_registry_has_no_blockers(self):
        self.assertEqual(report(self.registry)["blockers"], [])

    def test_pve_orchenv_scope_excludes_instructions_secrets_and_check_config(self):
        policy = self.registry["repositories"]["d3hl/pve-orchenv"]
        self.assertEqual(policy["linear_label"], "repo:pve-orchenv")
        self.assertEqual(set(policy["checks"]), {"test", "lint"})
        for path in ("AGENTS.md", "inventory/group_vars/all/vault.yml", "inventory/hosts.yml", "config/vault-pass",
                     "versions.env", "Makefile", ".ansible-lint", ".yamllint", "ansible/ansible.cfg",
                     "ansible/requirements.yml", "build/build.sh", "bootserver/bootserver.sh"):
            self.assertFalse(within(path, policy["allowed_scope"]), path)
        for path in ("docs/x.md", "build/README.md", "bootserver/answer/answer/render.py",
                     "ansible/roles/base/tasks/main.yml", "ansible/site.yml"):
            self.assertTrue(within(path, policy["allowed_scope"]), path)
        # Checks never read real secrets: lint gets a throwaway vault password.
        argv = " ".join(" ".join(check["argv"]) for check in policy["checks"].values())
        self.assertNotIn("config/vault-pass", argv)
        self.assertNotIn("op://", argv)

    def test_subscription_tracker_scope_and_checks(self):
        policy = self.registry["repositories"]["d3hl/subscription-tracker"]
        self.assertEqual(policy["linear_label"], "repo:subscription-tracker")
        self.assertEqual(set(policy["checks"]), {"test", "typecheck"})
        for path in ("AGENTS.md", "docs/x.md", ".github/workflows/ci.yml", "node_modules/a.js", "dist/main.js"):
            self.assertFalse(within(path, policy["allowed_scope"]), path)
        for path in ("src/main.ts", "tests/domain/dates.test.ts", "package.json", "package-lock.json",
                     "tsconfig.json", "vitest.config.ts", ".gitignore", "README.md"):
            self.assertTrue(within(path, policy["allowed_scope"]), path)
        # Checks run in a temporary copy so node_modules never lands in the checkout.
        for check in policy["checks"].values():
            text = " ".join(check["argv"])
            self.assertIn("mktemp -d", text)
            self.assertIn("--exclude=./.git", text)
            self.assertNotIn("op://", text)

    def test_no_registered_check_runs_npm_install_scripts(self):
        for repo_id, policy in self.registry["repositories"].items():
            for check_id, check in policy["checks"].items():
                text = " ".join(check["argv"])
                if "npm ci" in text:
                    self.assertIn("--ignore-scripts", text, repo_id + " " + check_id)

if __name__ == "__main__":
    unittest.main()
