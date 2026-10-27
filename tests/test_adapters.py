import json
from contract_master.adapters import Intake, Orca, normalize, provider_status
from contract_master.contracts import ContractError, ProviderError
from contract_master.github import GitHub
from support import WorkflowFixture, A, B, C


class AdapterTests(WorkflowFixture):
    def full(self, **updates):
        block = {k: self.issue[k] for k in ("repo_id", "base_commit", "goal", "allowed_scope", "acceptance_criteria", "required_checks")}
        issue = {"id": "issue-1", "identifier": "TEST-1", "project": {"id": "project-1"}, "state": {"name": "Todo", "type": "unstarted"},
                 "description": "```contract-master\n" + json.dumps(block) + "\n```", "updatedAt": self.issue["updated_at"]}
        value = {"issue": issue, "children": [], "relations": [], "comments": []}
        value.update(updates)
        return value

    def test_provider_status_is_one_mapping(self):
        cases = {"completed": "done", "canceled": "canceled", "duplicate": "canceled", "started": "open", "unstarted": "open"}
        for state, status in cases.items():
            self.assertEqual(provider_status(state), status)

    def test_normalize_real_orca_directional_dependency_shape(self):
        inbound = {"type": "blocks", "direction": "inbound", "relationship": "blockedBy", "relatedIssue": {"id": "dependency"}}
        outbound = {"type": "blocks", "direction": "outbound", "relationship": "blocks", "relatedIssue": {"id": "child"}}
        self.assertEqual(normalize(self.full(relations=[inbound, outbound]))["dependencies"], ["dependency"])
        with self.assertRaises(ContractError): normalize(self.full(relations=[{"type": "blocks"}]))

    def test_malformed_scope_edit_cannot_leave_stale_ready_task(self):
        self.start()
        full = self.full()
        full["issue"]["description"] = full["issue"]["description"].replace('"src", "tests"', '"secrets"')
        class Source:
            def project_issues(self, *args): return [{"id": "issue-1", "identifier": "TEST-1"}]
            def issue(self, *args): return full
        Intake(self.manager, Source(), "workspace").reconcile()
        with self.assertRaises(ContractError): self.manager.prepare_dispatch(self.task_id, self.token, self.runner)

    def test_missing_block_and_parent_remain_unqueued(self):
        full = self.full(children=[{"id": "child"}])
        full["issue"]["description"] = "Tracking work"
        class Source:
            def project_issues(self, *args): return [{"id": "issue-1", "identifier": "TEST-1"}]
            def issue(self, *args): return full
        result = Intake(self.manager, Source(), "workspace").reconcile()
        self.assertFalse(any(r["queued"] for r in result))
        self.assertIn("Tracking parent", result[0]["reason"])

    def test_project_pagination_and_partial_reads(self):
        class Paged(Orca):
            def __init__(self): self.calls = 0
            def call(self, *args, **kwargs):
                self.calls += 1
                if self.calls == 1: return {"issues": [{"id": "1"}], "truncated": True, "meta": {"nextCursor": "opaque"}}
                return {"issues": [{"id": "2"}], "truncated": False}
        self.assertEqual([i["id"] for i in Paged().project_issues("project", "workspace")], ["1", "2"])
        class Partial(Orca):
            def call(self, *args, **kwargs): return {"issues": [], "meta": {"partial": True}}
        with self.assertRaises(ContractError): list(Partial().project_issues("p", "w"))
        class Truncated(Orca):
            def call(self, *args, **kwargs): return {"meta": {"sections": {"comments": {"hasMore": True}}}}
        with self.assertRaises(ContractError): Truncated().issue("i", "w")

    def outbox_count(self):
        with self.manager.store.transaction() as db:
            return db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]

    def test_dependency_read_outage_neither_comments_nor_fences_task(self):
        self.start()
        relation = {"type": "blocks", "direction": "inbound", "relationship": "blockedBy", "relatedIssue": {"id": "dep-1", "identifier": "TEST-2"}}
        full = self.full(relations=[relation])
        class Source:
            def project_issues(self, *args): return [{"id": "issue-1", "identifier": "TEST-1"}]
            def issue(self, identifier, *args):
                if identifier == "TEST-2": raise ProviderError("Incomplete issue context")
                return full
        before = self.outbox_count()
        result = Intake(self.manager, Source(), "workspace").reconcile()
        self.assertTrue(result[0]["retry"])
        self.assertEqual(self.outbox_count(), before)
        task = self.manager.task(self.task_id)
        self.assertEqual((task["needs_replan"], task["blocked"]), (False, None))

    def test_issue_read_outage_skips_only_that_issue(self):
        full = self.full()
        class Source:
            def project_issues(self, *args): return [{"id": "issue-0", "identifier": "TEST-0"}, {"id": "issue-1", "identifier": "TEST-1"}]
            def issue(self, identifier, *args):
                if identifier == "TEST-0": raise ProviderError("timeout")
                return full
        result = Intake(self.manager, Source(), "workspace").reconcile()
        self.assertTrue(result[0]["retry"])
        self.assertTrue(result[1]["queued"])

    def test_orca_failures_are_provider_errors(self):
        with self.assertRaises(ProviderError): Orca("contract-master-missing-orca-binary").call("status")
        class Partial(Orca):
            def call(self, *args, **kwargs): return {"issues": [], "meta": {"partial": True}}
        with self.assertRaises(ProviderError): list(Partial().project_issues("p", "w"))
        class Truncated(Orca):
            def call(self, *args, **kwargs): return {"meta": {"sections": {"comments": {"hasMore": True}}}}
        with self.assertRaises(ProviderError): Truncated().issue("i", "w")

    def test_provider_approval_exact_commit_human_merge_and_repository(self):
        class Provider(GitHub):
            def __init__(self): self.head, self.human, self.merged, self.approved = B, True, True, True
            def api(self, path):
                if "/reviews?" in path:
                    return [{"user": {"login": "reviewer", "type": "User"}, "state": "APPROVED" if self.approved else "CHANGES_REQUESTED", "commit_id": self.head}]
                return {"merged": self.merged, "head": {"sha": self.head}, "merged_by": {"login": "merger", "type": "User" if self.human else "Bot"}, "merge_commit_sha": C}
        provider = Provider()
        url = "https://github.com/example/repo/pull/1"
        self.assertEqual(provider.confirm("https://github.com/example/repo", url, B)["merged_commit"], C)
        for field, value in (("head", A), ("human", False), ("merged", False), ("approved", False)):
            provider = Provider(); setattr(provider, field, value)
            with self.assertRaises(ContractError): provider.confirm("https://github.com/example/repo", url, B)
        with self.assertRaises(ContractError): Provider().confirm("https://github.com/example/repo", "https://github.com/other/repo/pull/1", B)

    def test_null_merged_by_is_a_clean_refusal(self):
        class Provider(GitHub):
            def api(self, path):
                return {"merged": True, "head": {"sha": B}, "merged_by": None, "merge_commit_sha": C}
        with self.assertRaises(ContractError):
            Provider().confirm("https://github.com/example/repo", "https://github.com/example/repo/pull/1", B)

    def test_newer_dismissed_review_invalidates_old_approval(self):
        class Provider(GitHub):
            def api(self, path):
                if "/reviews?" in path:
                    return [{"user": {"login": "human", "type": "User"}, "state": state, "commit_id": B} for state in ("APPROVED", "DISMISSED")]
                return {"merged": True, "head": {"sha": B}, "merged_by": {"login": "merger", "type": "User"}, "merge_commit_sha": C}
        with self.assertRaises(ContractError): Provider().confirm("https://github.com/example/repo", "https://github.com/example/repo/pull/1", B)

