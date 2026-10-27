"""Read-only GitHub merge gate. No review, merge or write operations exist here."""
import json
import re
import subprocess
from .contracts import ContractError, ProviderError


class GitHub:
    @staticmethod
    def api(path):
        run = subprocess.run(["gh", "api", path], capture_output=True, text=True, timeout=45, check=False)
        if run.returncode:
            raise ProviderError("GitHub read failed; preserve review state")
        return json.loads(run.stdout)

    def confirm(self, repository_url, pr_url, accepted_commit):
        repo = re.fullmatch(r"https://github.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?", repository_url)
        if not repo:
            raise ContractError("Only registered GitHub repositories supported by this adapter")
        pr = re.fullmatch(r"https://github.com/" + re.escape(repo[1]) + r"/pull/([1-9][0-9]*)", pr_url)
        if not pr:
            raise ContractError("PR must belong to registered repository")
        endpoint = "repos/" + repo[1] + "/pulls/" + pr[1]
        value = self.api(endpoint)
        # merged_by can be null; `or {}` keeps that a clean refusal rather than a crash.
        human_merge = (value.get("merged_by") or {}).get("type") == "User"
        if not value.get("merged") or value["head"]["sha"] != accepted_commit or not human_merge:
            raise ContractError("Human merge of current accepted head is not confirmed")
        # Page every review; later dismissals/changes-requested replace earlier decisions per user.
        latest = {}
        page = 1
        while True:
            reviews = self.api(endpoint + "/reviews?per_page=100&page=" + str(page))
            for review in reviews:
                if review["user"]["type"] == "User" and review["state"] != "COMMENTED":
                    latest[review["user"]["login"]] = review
            if len(reviews) < 100:
                break
            page += 1
        approved = [r for r in latest.values() if r["state"] == "APPROVED" and r["commit_id"] == accepted_commit]
        if not approved:
            raise ContractError("No current human approval on accepted head")
        return {"accepted_commit": accepted_commit, "merged_commit": value["merge_commit_sha"],
                "human_reviewer": approved[0]["user"]["login"], "human_merger": value["merged_by"]["login"],
                "pr_url": pr_url,
                "evidence": "GitHub REST " + endpoint + ": merged; User merger; latest User approval on exact head"}
