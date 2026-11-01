"""Governance review of manually opened registry/doc PRs; no Linear or task writes."""
import base64
import copy
import json
import time
import urllib.parse

from . import github, github_app
from .contracts import ContractError, digest, safe_path, validate, within
from .turns import TurnLease

PHASES = ("verifying", "changes_requested", "awaiting_merge", "merged", "done", "escalated",
          "closed", "ineligible")
FINAL = ("merged", "done")
FORBIDDEN_TOP = ("version", "automation_enabled", "linear_workspace", "reviewed_master_commits")
REGISTRY_PATH = "config/registry.json"


def policy(registry, repo_id):
    """Return the enabled, well-formed governance block or raise a specific refusal."""
    repo = (registry.get("repositories") or {}).get(repo_id)
    if not repo:
        raise ContractError("Repository " + repo_id + " is not registered")
    block = repo.get("governance_review")
    if not block:
        raise ContractError("Repository " + repo_id + " has no governance_review block")
    if not isinstance(block, dict):
        raise ContractError("Governance block for " + repo_id + " is not an object")
    if block.get("enabled") is not True:
        raise ContractError("Governance review is disabled for " + repo_id)
    authors = block.get("authors")
    if not isinstance(authors, list) or not authors:
        raise ContractError("Governance block for " + repo_id + " needs authors")
    for author in authors:
        if (not isinstance(author, dict) or not isinstance(author.get("login"), str)
                or not author["login"] or not isinstance(author.get("type"), str) or not author["type"]):
            raise ContractError("Governance author for " + repo_id + " needs login and type")
    paths = block.get("allowed_paths")
    if not isinstance(paths, list) or not paths:
        raise ContractError("Governance block for " + repo_id + " needs allowed_paths")
    for path in paths:
        try:
            safe_path(path)
        except ContractError as exc:
            raise ContractError("Governance allowed path for " + repo_id + " is invalid: " + str(exc)) from None
    fields = block.get("registry_fields")
    if not isinstance(fields, list) or not fields or not all(isinstance(f, str) and f for f in fields):
        raise ContractError("Governance block for " + repo_id + " needs registry_fields")
    checks = block.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ContractError("Governance block for " + repo_id + " needs checks")
    known = repo.get("checks") or {}
    for check_id in checks:
        if check_id not in known:
            raise ContractError("Governance check " + str(check_id) + " is not registered for " + repo_id)
    return block


def registry_changes(base, head, fields):
    """Return deterministic allowed registry field changes; refuse everything else."""
    if not isinstance(head, dict):
        raise ContractError("Head registry is not a JSON object")
    for key in sorted((set(base) | set(head)) - {"repositories"}):
        if base.get(key) != head.get(key):
            raise ContractError("Registry change to " + key + " needs a human merge")
    old_repos = base.get("repositories") or {}
    new_repos = head.get("repositories") or {}
    added = sorted(set(new_repos) - set(old_repos))
    removed = sorted(set(old_repos) - set(new_repos))
    if added:
        raise ContractError("Registry added repository " + added[0] + "; needs a human merge")
    if removed:
        raise ContractError("Registry removed repository " + removed[0] + "; needs a human merge")
    changes = []
    for repo in sorted(old_repos):
        old, new = old_repos[repo] or {}, new_repos[repo] or {}
        for key in sorted(set(old) | set(new)):
            if old.get(key) == new.get(key):
                continue
            if key == "governance_review" or key not in fields:
                raise ContractError("Registry change to " + repo + "." + key + " needs a human merge")
            changes.append({"repo": repo, "field": key, "before": old.get(key), "after": new.get(key)})
    return sorted(changes, key=lambda item: (item["repo"], item["field"]))


def criteria(changed_files, changes, check_ids):
    """Deterministic acceptance criteria for Codex's independent governance review."""
    values = [
        "Changed files stay within the governance allowed paths: " + ", ".join(sorted(changed_files)),
        "Trusted-base checks pass at the exact head: " + ", ".join(sorted(check_ids)),
    ]
    for change in changes:
        repo, field = change["repo"], change["field"]
        if field == "checks":
            text = ("Check argv change for " + repo + " runs only that repository's own tooling,"
                    " with no credentials and no network writes beyond package install")
        elif field == "allowed_scope":
            text = ("Scope change for " + repo + " is justified, minimal and keeps instructions,"
                    " credentials and CI out of scope")
        else:
            text = "Registry change to " + repo + "." + field + " is justified and consistent"
        suffix = json.dumps({"before": change["before"], "after": change["after"]}, sort_keys=True)
        values.append(text + ": " + suffix[:300])
    if changes:
        values.append("Documentation matches the registry change")
    return sorted(values)


class Governance:
    """Dedicated pr_reviews records; every write holds the caller's live turn lease."""

    def __init__(self, store, registry, clock=time.time):
        self.store, self.registry, self.clock = store, registry, clock

    def _load(self, db, key):
        row = db.execute("SELECT data FROM pr_reviews WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def _save(self, db, record):
        db.execute("INSERT OR REPLACE INTO pr_reviews VALUES(?,?)", (record["key"], json.dumps(record)))

    def _require(self, db, lease):
        TurnLease(self.store, self.clock).require(db, lease)

    def _snapshot(self, repo_id, block):
        checks = self.registry["repositories"][repo_id]["checks"]
        return {check_id: copy.deepcopy(checks[check_id]) for check_id in block["checks"]}

    def _new_record(self, block, repo_id, pull, files, base_sha, old, phase, reason, changes, checks):
        key = repo_id + "#" + str(pull["number"])
        head = pull["head"]["sha"]
        same_head = bool(old) and old.get("head_sha") == head
        names = sorted(files)
        return {
            "key": key, "repo": repo_id, "number": pull["number"],
            "url": pull.get("html_url") or pull.get("url"),
            "author": (pull.get("user") or {}).get("login"),
            "base_sha": base_sha, "head_sha": head, "files": names,
            "changes": changes, "criteria": criteria(names, changes, block["checks"]),
            "checks": checks, "policy_digest": digest(block), "phase": phase,
            "verification": None,
            "changes_verdicts": old.get("changes_verdicts", 0) if same_head else 0,
            "merge_steps": {}, "merge_receipt": None, "completion": None, "reason": reason,
            "history": list((old or {}).get("history") or [])
                       + [{"head_sha": head, "base_sha": base_sha, "at": self.clock()}],
        }

    def _eligibility(self, repo, block, pull, files, head_registry):
        if pull.get("draft"):
            return "Draft PR", None
        if (pull.get("base") or {}).get("ref") != github_app.base_branch(repo):
            return "Base ref is not the registered base branch", None
        if ((pull.get("head") or {}).get("repo") or {}).get("full_name") != github_app.repo_name(repo["url"]):
            return "Fork PRs are not eligible", None
        user = pull.get("user") or {}
        if (user.get("login"), user.get("type")) not in [(a["login"], a["type"]) for a in block["authors"]]:
            return "Author not allowed", None
        slug = ((repo.get("github_apps") or {}).get("merge") or {}).get("slug")
        if slug and user.get("login") == slug + "[bot]":
            return "The merge App cannot author a governance PR", None
        for name in files:
            try:
                allowed = within(name, block["allowed_paths"])
            except ContractError as exc:
                return str(exc), None
            if not allowed:
                return "Changed file is outside the governance allowed paths: " + name, None
        changes = []
        if REGISTRY_PATH in files:
            if head_registry is None:
                return "Head registry unavailable", None
            try:
                changes = registry_changes(self.registry, head_registry, block["registry_fields"])
            except ContractError as exc:
                return str(exc), None
        return None, changes

    def intake(self, lease, repo_id, pull, files, base_sha, head_registry=None):
        """Record eligibility and the trusted-base policy snapshot, or refuse to record."""
        block = policy(self.registry, repo_id)
        repo = self.registry["repositories"][repo_id]
        checks = self._snapshot(repo_id, block)
        key = repo_id + "#" + str(pull["number"])
        with self.store.transaction() as db:
            self._require(db, lease)
            old = self._load(db, key)
            if old and old["phase"] in FINAL:
                return old
            if pull.get("state") == "closed":
                if pull.get("merged") or pull.get("merged_at"):
                    return old
                record = self._new_record(block, repo_id, pull, files, base_sha, old, "closed",
                                          "PR is closed", [], checks)
                self._save(db, record)
                return record
            reason, changes = self._eligibility(repo, block, pull, files, head_registry)
            if reason:
                record = self._new_record(block, repo_id, pull, files, base_sha, old, "ineligible",
                                          reason, [], checks)
                self._save(db, record)
                return record
            if (old and old["head_sha"] == pull["head"]["sha"] and old["base_sha"] == base_sha
                    and old["phase"] not in ("ineligible", "closed")):
                return old
            record = self._new_record(block, repo_id, pull, files, base_sha, old, "verifying",
                                      None, changes, checks)
            self._save(db, record)
            return record

    def verify(self, lease, key, result):
        """Record Codex evidence; a second changes verdict escalates the record."""
        validate("governance-verification", result)
        with self.store.transaction() as db:
            self._require(db, lease)
            record = self._load(db, key)
            if not record:
                raise ContractError("Unknown governance record")
            # "changes_requested" stays open so a second verdict can reach the two-attempt cap.
            if record["phase"] not in ("verifying", "changes_requested"):
                raise ContractError("Governance record is not being verified")
            if result["key"] != key:
                raise ContractError("Verification key differs from the record")
            if result["head_sha"] != record["head_sha"] or result["base_sha"] != record["base_sha"]:
                raise ContractError("Verification head or base is stale")
            seen = [item["criterion"] for item in result["acceptance_evidence"]]
            if len(seen) != len(set(seen)) or set(seen) != set(record["criteria"]):
                raise ContractError("Every governance criterion needs evidence")
            ids = [item["id"] for item in result["checks"]]
            if len(ids) != len(set(ids)) or set(ids) != set(record["checks"]):
                raise ContractError("Governance check set differs")
            if any(item["commit"] != record["head_sha"] for item in result["checks"]):
                raise ContractError("Checks must run against the exact head")
            passed = (all(item["passed"] for item in result["acceptance_evidence"])
                      and all(item["passed"] for item in result["checks"]))
            if result["verdict"] == "pass" and (not passed or result["corrections"]):
                raise ContractError("Passing verdict conflicts with evidence")
            if result["verdict"] == "changes" and not result["corrections"]:
                raise ContractError("Change verdict needs actionable corrections")
            record["verification"] = result
            if result["verdict"] == "pass":
                record["phase"] = "awaiting_merge"
            else:
                record["changes_verdicts"] = record.get("changes_verdicts", 0) + 1
                record["phase"] = ("escalated" if record["changes_verdicts"] >= 2
                                   else "changes_requested")
            self._save(db, record)
            return record

    def _step(self, lease, key, head, step, value):
        with self.store.transaction() as db:
            self._require(db, lease)
            record = self._load(db, key)
            if not record or record["head_sha"] != head:
                raise ContractError("Governance record head moved")
            record.setdefault("merge_steps", {})[step] = value
            self._save(db, record)

    def _mutate(self, lease, key, head, updates):
        with self.store.transaction() as db:
            self._require(db, lease)
            record = self._load(db, key)
            if not record or record["head_sha"] != head:
                raise ContractError("Governance record head moved")
            record.update(updates)
            self._save(db, record)

    def _reset(self, lease, key, head):
        self._mutate(lease, key, head, {"phase": "verifying", "verification": None, "merge_steps": {}})

    def merge(self, lease, key, app, reader, current_base_sha):
        """Check, approve and merge the exact verified head as the registered Codex App."""
        with self.store.transaction() as db:
            self._require(db, lease)
            record = self._load(db, key)
            if not record:
                raise ContractError("Unknown governance record")
            if record["phase"] != "awaiting_merge":
                raise ContractError("Governance record is not awaiting merge")
            verification, head = record.get("verification"), record["head_sha"]
            if not verification or verification.get("verdict") != "pass" or verification.get("head_sha") != head:
                raise ContractError("Passing governance verification of the head is required")
            repo = self.registry["repositories"].get(record["repo"]) or {}
            identity = repo.get("merge_identity")
            if not identity or app.login != identity["login"]:
                raise ContractError("Merge App does not match the registered merge identity")
            number, url = record["number"], record["url"]
            repo_url, base_sha = repo.get("url"), record["base_sha"]
        pull = app.pull(number)
        if (pull["head"]["sha"] != head and not pull.get("merged")) or current_base_sha != base_sha:
            self._reset(lease, key, head)
            raise ContractError("PR head or base moved; verify again")
        if (pull["user"]["login"], pull["user"]["type"]) == (identity["login"], identity["type"]):
            raise ContractError("The merge App cannot approve a PR it opened")
        latest = github.latest_reviews(app.reviews(number))
        if github.human_veto(latest):
            self._mutate(lease, key, head, {"phase": "escalated", "reason": "A human requested changes"})
            raise ContractError("A human requested changes; escalate instead of merging")
        if not pull.get("merged"):
            runs = app.check_runs(head)
            if not any(run["app"]["id"] == app.app_id and run["head_sha"] == head
                       and run["conclusion"] == "success" for run in runs):
                summary = "Codex verified " + head + " for " + key + ". " + verification["diff_evidence"]
                app.create_check(head, summary)
            self._step(lease, key, head, "check", head)
            if not github.approved_by(latest, identity, head):
                app.approve(number, head, "Codex verification passed for " + head)
            self._step(lease, key, head, "approved", head)
            try:
                app.merge(number, head)
            except github_app.GitHubWriteError as exc:
                if exc.status not in (405, 409, 422):
                    raise
                self._mutate(lease, key, head, {"phase": "escalated", "reason": str(exc)})
                raise ContractError("PR is not mergeable; escalate: " + str(exc)) from None
        self._step(lease, key, head, "merged", head)
        receipt = reader.confirm(repo_url, url, head, identity)
        with self.store.transaction() as db:
            self._require(db, lease)
            record = self._load(db, key)
            if not record or record["head_sha"] != head:
                raise ContractError("Governance record head moved")
            record["merge_receipt"] = receipt
            record["phase"] = "merged"
            self._save(db, record)
            return record

    def confirm(self, lease, key, evidence):
        """Record Claude's final acceptance of the provider-merged commit."""
        validate("governance-completion", evidence)
        with self.store.transaction() as db:
            self._require(db, lease)
            record = self._load(db, key)
            if not record:
                raise ContractError("Unknown governance record")
            if record["phase"] != "merged":
                raise ContractError("Governance record is not merged")
            if evidence["key"] != key:
                raise ContractError("Completion key differs from the record")
            receipt = record.get("merge_receipt")
            if not receipt:
                raise ContractError("Provider merge receipt is required")
            if (evidence["accepted_commit"] != record["head_sha"]
                    or evidence["accepted_commit"] != receipt["accepted_commit"]):
                raise ContractError("Accepted commit does not match the head")
            if evidence["merged_commit"] != receipt["merged_commit"]:
                raise ContractError("Merged commit does not match the provider receipt")
            ids = [item["id"] for item in evidence["checks"]]
            if len(ids) != len(set(ids)) or set(ids) != set(record["checks"]):
                raise ContractError("Governance check set differs")
            if any(item["commit"] != evidence["merged_commit"] or not item["passed"]
                   for item in evidence["checks"]):
                raise ContractError("Checks must pass on the merged commit")
            record["completion"] = evidence
            record["phase"] = "done"
            self._save(db, record)
            return record

    def get(self, key):
        with self.store.transaction() as db:
            return self._load(db, key)

    def list(self):
        with self.store.transaction() as db:
            rows = db.execute("SELECT data FROM pr_reviews ORDER BY key").fetchall()
        return [json.loads(row[0]) for row in rows]


class GitHubReader:
    """Read-only GitHub reads used by review-scan and review-merge; never writes."""

    def __init__(self, api=None):
        self.api = api or github.GitHub.api

    def _paged(self, path):
        result, page = [], 1
        separator = "&" if "?" in path else "?"
        while True:
            batch = self.api(path + separator + "per_page=100&page=" + str(page))
            result.extend(batch)
            if len(batch) < 100:
                return result
            page += 1

    def open_pulls(self, repo):
        return self._paged("repos/" + repo + "/pulls?state=open")

    def pull(self, repo, number):
        return self.api("repos/" + repo + "/pulls/" + str(number))

    def files(self, repo, number):
        return self._paged("repos/" + repo + "/pulls/" + str(number) + "/files")

    def content(self, repo, path, ref):
        quoted = urllib.parse.quote(ref, safe="")
        value = self.api("repos/" + repo + "/contents/" + path + "?ref=" + quoted)
        if value.get("encoding") != "base64" or not value.get("content"):
            raise ContractError("GitHub file content is not base64")
        return base64.b64decode(value["content"]).decode("utf-8")

    def base_tip(self, repo, branch):
        return self.api("repos/" + repo + "/commits/" + urllib.parse.quote(branch, safe=""))["sha"]
