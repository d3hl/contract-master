import json
from contract_master.adapters import Intake, Orca, normalize, provider_status
from contract_master.contracts import ContractError, ProviderError
from contract_master.github import GitHub
from support import WorkflowFixture, A, B, C


REPO = "https://github.com/example/repo"
CODEX = {"login": "codex-bot[bot]", "type": "Bot"}


def codex_review(state, commit=B):
    return {"user": dict(CODEX), "state": state, "commit_id": commit}


def human_review(state, commit=B):
    return {"user": {"login": "person", "type": "User"}, "state": state, "commit_id": commit}


class CodexProvider(GitHub):
    """Fake GitHub reads; defaults describe a Codex approval and merge of head B."""
    def __init__(self):
        self.head, self.merged, self.merger, self.reviews = B, True, dict(CODEX), [codex_review("APPROVED")]

    def api(self, path):
        if "/reviews?" in path:
            return self.reviews
        return {"merged": self.merged, "head": {"sha": self.head}, "merged_by": self.merger, "merge_commit_sha": C}


class AdapterTests(WorkflowFixture):
    def full(self, **updates):
        block = {k: self.issue[k] for k in ("repo_id", "base_commit", "goal", "allowed_scope", "acceptance_criteria", "required_checks")}
        issue = {"id": "issue-1", "identifier": "TEST-1", "project": {"id": "project-1"}, "state": {"name": "Todo", "type": "unstarted"},
                 "description": "```contract-master\n" + json.dumps(block) + "\n```", "updatedAt": self.issue["updated_at"],
                 "labels": [{"id": "l1", "name": "type:feature"}]}
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

    def test_normalize_keeps_only_repository_labels_and_requires_label_context(self):
        full = self.full()
        full["issue"]["labels"] += [{"id": "l2", "name": "repo:b"}, {"id": "l3", "name": "repo:a"}]
        self.assertEqual(normalize(full)["repo_labels"], ["repo:a", "repo:b"])
        del full["issue"]["labels"]
        with self.assertRaises(ContractError): normalize(full)

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

    def test_only_open_incomplete_issues_get_triage_comments(self):
        for state, comments in (("completed", 0), ("canceled", 0), ("started", 1), ("backlog", 1)):
            with self.subTest(state=state):
                self.setUp()
                full = self.full()
                full["issue"]["description"] = "Human-written issue without an automation block"
                full["issue"]["state"]["type"] = state
                class Source:
                    def project_issues(self, *args): return [{"id": "issue-1", "identifier": "TEST-1"}]
                    def issue(self, *args): return full
                before = self.outbox_count()
                result = Intake(self.manager, Source(), "workspace").reconcile()
                self.assertFalse(result[0]["queued"])
                self.assertEqual(self.outbox_count() - before, comments)

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

    def test_provider_requires_codex_approval_and_merge_on_exact_head(self):
        url = "https://github.com/example/repo/pull/1"
        provider = CodexProvider()
        receipt = provider.confirm(REPO, url, B, CODEX)
        self.assertEqual((receipt["merged_commit"], receipt["reviewer"], receipt["merger"]), (C, CODEX["login"], CODEX["login"]))
        cases = (("head", A), ("merged", False), ("merger", {"login": "person", "type": "User"}),
                 ("merger", {"login": "other-bot[bot]", "type": "Bot"}), ("reviews", []),
                 ("reviews", [codex_review("CHANGES_REQUESTED")]), ("reviews", [codex_review("APPROVED", A)]))
        for field, value in cases:
            provider = CodexProvider(); setattr(provider, field, value)
            with self.assertRaises(ContractError): provider.confirm(REPO, url, B, CODEX)
        with self.assertRaises(ContractError): CodexProvider().confirm(REPO, "https://github.com/other/repo/pull/1", B, CODEX)
        for identity in (None, {}, {"login": "codex-bot[bot]"}):
            with self.assertRaises(ContractError): CodexProvider().confirm(REPO, url, B, identity)

    def test_human_approval_is_optional_but_change_request_vetoes(self):
        url = "https://github.com/example/repo/pull/1"
        provider = CodexProvider()
        provider.reviews = [codex_review("APPROVED"), human_review("APPROVED")]
        self.assertEqual(provider.confirm(REPO, url, B, CODEX)["merger"], CODEX["login"])
        provider.reviews = [codex_review("APPROVED"), human_review("CHANGES_REQUESTED")]
        with self.assertRaises(ContractError): provider.confirm(REPO, url, B, CODEX)
        provider.reviews = [codex_review("APPROVED"), human_review("CHANGES_REQUESTED"), human_review("APPROVED")]
        self.assertEqual(provider.confirm(REPO, url, B, CODEX)["merger"], CODEX["login"])

    def test_null_merged_by_is_a_clean_refusal(self):
        provider = CodexProvider(); provider.merger = None
        with self.assertRaises(ContractError): provider.confirm(REPO, "https://github.com/example/repo/pull/1", B, CODEX)

    def test_newer_dismissed_review_invalidates_old_approval(self):
        provider = CodexProvider(); provider.reviews = [codex_review("APPROVED"), codex_review("DISMISSED")]
        with self.assertRaises(ContractError): provider.confirm(REPO, "https://github.com/example/repo/pull/1", B, CODEX)

