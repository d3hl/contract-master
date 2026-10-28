"""Read-only GitHub merge gate. No review, merge or write operations exist here."""
import json
import re
import subprocess
from .contracts import ContractError, ProviderError


def latest_reviews(reviews):
    """Latest decision per reviewer; later dismissals/changes-requested replace earlier ones."""
    latest = {}
    for review in reviews:
        if review["state"] != "COMMENTED":
            latest[(review["user"]["login"], review["user"]["type"])] = review
    return latest


def approved_by(latest, identity, commit):
    review = latest.get((identity["login"], identity["type"]))
    return bool(review) and review["state"] == "APPROVED" and review["commit_id"] == commit


def human_veto(latest):
    return any(r["user"]["type"] == "User" and r["state"] == "CHANGES_REQUESTED" for r in latest.values())


class GitHub:
    @staticmethod
    def api(path):
        run = subprocess.run(["gh", "api", path], capture_output=True, text=True, timeout=45, check=False)
        if run.returncode:
            raise ProviderError("GitHub read failed; preserve review state")
        return json.loads(run.stdout)

    def confirm(self, repository_url, pr_url, accepted_commit, merge_identity):
        """Confirm Codex reviewed and merged the exact accepted head; a human may still veto."""
        if not merge_identity or not merge_identity.get("login") or not merge_identity.get("type"):
            raise ContractError("Codex merge identity is not configured for this repository")
        repo = re.fullmatch(r"https://github.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?", repository_url)
        if not repo:
            raise ContractError("Only registered GitHub repositories supported by this adapter")
        pr = re.fullmatch(r"https://github.com/" + re.escape(repo[1]) + r"/pull/([1-9][0-9]*)", pr_url)
        if not pr:
            raise ContractError("PR must belong to registered repository")
        endpoint = "repos/" + repo[1] + "/pulls/" + pr[1]
        value = self.api(endpoint)
        # merged_by can be null; `or {}` keeps that a clean refusal rather than a crash.
        merger = value.get("merged_by") or {}
        codex_merge = (merger.get("login"), merger.get("type")) == (merge_identity["login"], merge_identity["type"])
        if not value.get("merged") or value["head"]["sha"] != accepted_commit or not codex_merge:
            raise ContractError("Codex merge of current accepted head is not confirmed")
        reviews, page = [], 1
        while True:
            batch = self.api(endpoint + "/reviews?per_page=100&page=" + str(page))
            reviews.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        latest = latest_reviews(reviews)
        if not approved_by(latest, merge_identity, accepted_commit):
            raise ContractError("No current Codex approval on accepted head")
        if human_veto(latest):
            raise ContractError("A human requested changes; escalate instead of completing")
        return {"accepted_commit": accepted_commit, "merged_commit": value["merge_commit_sha"],
                "reviewer": merge_identity["login"], "merger": merger["login"], "pr_url": pr_url,
                "evidence": "GitHub REST " + endpoint + ": merged; Codex merger; latest Codex approval on exact head;"
                            " no human change request"}
