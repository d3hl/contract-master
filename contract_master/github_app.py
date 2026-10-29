"""GitHub App writes: d3hl-orca opens PRs, d3hl-codex checks, approves and merges.

Keys are read from 1Password at call time and only ever held in memory. Tokens and
keys never appear in argv, files, error messages or return values. The read-only
merge gate stays in github.py.
"""
import base64
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from .contracts import ContractError, ProviderError

API = "https://api.github.com"
CHECK_NAME = "codex-verification"
ROLES = ("pr", "merge")
# Each role asks GitHub for only what its own steps need, narrower than the install.
PERMISSIONS = {
    "pr": {"contents": "write", "pull_requests": "write", "metadata": "read"},
    "merge": {"contents": "write", "pull_requests": "write", "checks": "write", "metadata": "read"},
}
# Scheduled coordinator turns start without the 1Password service account token in
# their environment. The manager then reads it from this owner-only file and passes it
# to `op` alone. Override the path with CONTRACT_MASTER_OP_TOKEN_FILE.
OP_TOKEN_FILE = "~/.config/op/contract-master-sa-token"
# Git reads the password from the environment, so the token is never in argv or a URL.
CREDENTIAL_HELPER = "!f() { echo username=x-access-token; echo password=$CONTRACT_MASTER_GIT_TOKEN; }; f"


class GitHubWriteError(ProviderError):
    def __init__(self, status, message):
        super().__init__("GitHub write failed (" + str(status) + "): " + message)
        self.status = status


def repo_name(url):
    match = re.fullmatch(r"https://github.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?", url)
    if not match:
        raise ContractError("Only registered GitHub repositories supported by this adapter")
    return match[1]


def base_branch(policy):
    ref = policy.get("base_ref", "origin/main")
    return ref.split("/", 1)[1] if ref.startswith("origin/") else ref


def app_config(policy, role):
    """Return complete App settings for a role, or raise naming what is missing."""
    app = (policy.get("github_apps") or {}).get(role) or {}
    missing = [k for k in ("slug", "app_id", "installation_id", "key_reference") if not app.get(k)]
    if missing:
        raise ContractError("GitHub App '" + role + "' is not configured: " + ", ".join(missing))
    if not str(app["key_reference"]).startswith("op://"):
        raise ContractError("GitHub App '" + role + "' key must be a 1Password op:// reference")
    return app


def problems(policy):
    """Configuration problems for readiness; empty when both Apps can be used."""
    found = []
    for role in ROLES:
        try:
            app_config(policy, role)
        except ContractError as exc:
            found.append(str(exc))
    apps = policy.get("github_apps") or {}
    slugs = [(apps.get(role) or {}).get("slug") for role in ROLES]
    if all(slugs) and slugs[0] == slugs[1]:
        found.append("PR-opening and merge Apps must be different")
    merge_slug = slugs[1]
    identity = policy.get("merge_identity") or {}
    if merge_slug and (identity.get("login"), identity.get("type")) != (merge_slug + "[bot]", "Bot"):
        found.append("merge_identity must be " + merge_slug + "[bot] (Bot)")
    return found


def op_environment():
    """Environment for `op`: the caller's, plus the service account token from its file."""
    env = dict(os.environ)
    if env.get("OP_SERVICE_ACCOUNT_TOKEN"):
        return env
    path = os.path.expanduser(env.get("CONTRACT_MASTER_OP_TOKEN_FILE") or OP_TOKEN_FILE)
    try:
        info = os.stat(path)
    except OSError:
        return env  # `op` may still have another sign-in; its failure is reported below.
    if info.st_mode & 0o077 or info.st_uid != os.getuid():
        raise ProviderError("1Password token file must be owner-only (0600) and owned by this user")
    with open(path) as handle:
        token = handle.read().strip()
    if token:
        env["OP_SERVICE_ACCOUNT_TOKEN"] = token
    return env


def read_key(reference):
    env = op_environment()
    try:
        run = subprocess.run(["op", "read", reference], capture_output=True, timeout=30, check=False, env=env)
    except (OSError, subprocess.SubprocessError):
        raise ProviderError("1Password read of the GitHub App key failed") from None
    if run.returncode or not run.stdout.strip():
        raise ProviderError("1Password read of the GitHub App key failed")
    return run.stdout


def sign(data, key):
    """RS256 signature with openssl; the key travels through a pipe, never a file."""
    read_end, write_end = os.pipe()
    try:
        os.write(write_end, key)
        os.close(write_end)
        write_end = None
        run = subprocess.run(["openssl", "dgst", "-sha256", "-sign", "/dev/fd/" + str(read_end)], input=data,
                             capture_output=True, pass_fds=(read_end,), timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        raise ProviderError("Signing with the GitHub App key failed") from None
    finally:
        os.close(read_end)
        if write_end is not None:
            os.close(write_end)
    if run.returncode or not run.stdout:
        raise ProviderError("Signing with the GitHub App key failed")
    return run.stdout


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def jwt(app_id, key, now=None, signer=sign):
    now = int(time.time() if now is None else now)
    # Backdate iat for clock drift; GitHub rejects exp more than 10 minutes ahead.
    claims = {"iat": now - 60, "exp": now + 540, "iss": str(app_id)}
    body = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode()) + "." + _b64(json.dumps(claims).encode())
    return body + "." + _b64(signer(body.encode(), key))


def http(method, path, body=None, auth=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(API + path, method=method, data=data)
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    if auth:
        request.add_header("Authorization", auth)
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        try:
            message = json.loads(exc.read() or b"{}").get("message", "")
        except ValueError:
            message = ""
        raise GitHubWriteError(exc.code, message or exc.reason) from None
    except (urllib.error.URLError, OSError) as exc:
        raise ProviderError("GitHub request failed: " + type(exc).__name__) from None
    return json.loads(raw) if raw else {}


class RepoApp:
    """One GitHub App acting on one repository with a fresh, narrowed installation token."""

    def __init__(self, policy, role, transport=http, key_reader=read_key, signer=sign):
        self.app = app_config(policy, role)
        self.role = role
        self.repo = repo_name(policy["url"])
        self.login = self.app["slug"] + "[bot]"
        self.app_id = int(self.app["app_id"])
        self.transport, self.key_reader, self.signer = transport, key_reader, signer
        self._token = None

    def token(self):
        if self._token is None:
            assertion = jwt(self.app["app_id"], self.key_reader(self.app["key_reference"]), signer=self.signer)
            body = {"repositories": [self.repo.split("/", 1)[1]], "permissions": PERMISSIONS[self.role]}
            path = "/app/installations/" + str(self.app["installation_id"]) + "/access_tokens"
            value = self.transport("POST", path, body, "Bearer " + assertion).get("token")
            if not value:
                raise ProviderError("GitHub did not return an installation token")
            self._token = value
        return self._token

    def call(self, method, path, body=None):
        return self.transport(method, "/repos/" + self.repo + path, body, "token " + self.token())

    # Pull requests
    def pull(self, number):
        return self.call("GET", "/pulls/" + str(number))

    def find_pull(self, branch):
        owner = self.repo.split("/", 1)[0]
        pulls = self.call("GET", "/pulls?state=all&per_page=100&head=" + owner + ":" + branch)
        return pulls[0] if pulls else None

    def open_pull(self, branch, base, title, body):
        return self.call("POST", "/pulls", {"head": branch, "base": base, "title": title, "body": body})

    def push(self, workspace, commit, branch):
        """Fast-forward push of the exact commit to a task branch; never force, never main."""
        if not branch.startswith("task/"):
            raise ContractError("Only task/ branches may be pushed")
        env = dict(os.environ, CONTRACT_MASTER_GIT_TOKEN=self.token(), GIT_TERMINAL_PROMPT="0")
        target = "https://github.com/" + self.repo + ".git"
        try:
            run = subprocess.run(["git", "-C", str(workspace), "-c", "credential.helper=",
                                  "-c", "credential.helper=" + CREDENTIAL_HELPER,
                                  "push", target, commit + ":refs/heads/" + branch],
                                 env=env, capture_output=True, timeout=120, check=False)
        except (OSError, subprocess.SubprocessError):
            raise ProviderError("Push of task branch failed") from None
        if run.returncode:
            raise ProviderError("Push of task branch failed (not a fast-forward or no access)")

    # Codex review and merge
    def reviews(self, number):
        result, page = [], 1
        while True:
            batch = self.call("GET", "/pulls/" + str(number) + "/reviews?per_page=100&page=" + str(page))
            result.extend(batch)
            if len(batch) < 100:
                return result
            page += 1

    def check_runs(self, commit):
        runs = self.call("GET", "/commits/" + commit + "/check-runs?check_name=" + CHECK_NAME)
        return runs.get("check_runs", [])

    def create_check(self, commit, summary):
        return self.call("POST", "/check-runs", {
            "name": CHECK_NAME, "head_sha": commit, "status": "completed", "conclusion": "success",
            "output": {"title": "Codex verification passed", "summary": summary}})

    def approve(self, number, commit, body):
        return self.call("POST", "/pulls/" + str(number) + "/reviews",
                         {"event": "APPROVE", "commit_id": commit, "body": body})

    def merge(self, number, commit, method="squash"):
        # `sha` makes GitHub refuse the merge if the head moved after verification.
        return self.call("PUT", "/pulls/" + str(number) + "/merge", {"sha": commit, "merge_method": method})
