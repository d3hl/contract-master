import base64
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from contract_master import github_app
from contract_master.contracts import ContractError, ProviderError

KEY = b"-----BEGIN PRIVATE KEY-----\nnot-a-real-key\n-----END PRIVATE KEY-----\n"
POLICY = {"url": "https://github.com/example/repo", "merge_identity": {"login": "codex[bot]", "type": "Bot"},
          "github_apps": {
              "pr": {"slug": "orca", "app_id": 1, "installation_id": 11, "key_reference": "op://v/pr/key"},
              "merge": {"slug": "codex", "app_id": 2, "installation_id": 22, "key_reference": "op://v/codex/key"}}}


def decode(part):
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


class Transport:
    def __init__(self, token="ghs_secret"):
        self.calls, self.token = [], token

    def __call__(self, method, path, body=None, auth=None):
        self.calls.append((method, path, body, auth))
        if path.endswith("/access_tokens"):
            return {"token": self.token}
        return {}


def app(role="merge", transport=None):
    return github_app.RepoApp(POLICY, role, transport=transport or Transport(), key_reader=lambda ref: KEY,
                              signer=lambda data, key: b"signature")


class GitHubAppTests(unittest.TestCase):
    def test_jwt_claims_stay_inside_github_limits(self):
        header, claims, signature = github_app.jwt(5511451, KEY, now=1000, signer=lambda d, k: b"sig").split(".")
        self.assertEqual(decode(header), {"alg": "RS256", "typ": "JWT"})
        self.assertEqual(decode(claims), {"iat": 940, "exp": 1540, "iss": "5511451"})
        self.assertLessEqual(decode(claims)["exp"] - 1000, 600)

    @unittest.skipUnless(shutil.which("openssl"), "openssl not installed")
    def test_openssl_signature_verifies_and_key_never_touches_disk(self):
        key = subprocess.run(["openssl", "genrsa", "2048"], capture_output=True, check=True).stdout
        if not key.startswith(b"-----BEGIN"):
            key = subprocess.run(["openssl", "genpkey", "-algorithm", "RSA"], capture_output=True, check=True).stdout
        signature = github_app.sign(b"payload", key)
        with tempfile.TemporaryDirectory() as temp:
            public = Path(temp) / "public.pem"
            subprocess.run(["openssl", "rsa", "-pubout", "-out", str(public)], input=key, capture_output=True,
                           check=True)
            (Path(temp) / "sig").write_bytes(signature)
            verify = subprocess.run(["openssl", "dgst", "-sha256", "-verify", str(public), "-signature",
                                     str(Path(temp) / "sig")], input=b"payload", capture_output=True)
        self.assertEqual(verify.returncode, 0, verify.stdout + verify.stderr)

    def test_token_request_is_narrowed_per_role(self):
        for role in ("pr", "merge"):
            transport = Transport()
            repo_app = app(role, transport)
            repo_app.pull(3)
            repo_app.pull(4)
            method, path, body, auth = transport.calls[0]
            installation = POLICY["github_apps"][role]["installation_id"]
            self.assertEqual((method, path), ("POST", "/app/installations/" + str(installation) + "/access_tokens"))
            self.assertTrue(auth.startswith("Bearer "))
            self.assertEqual(body, {"repositories": ["repo"], "permissions": github_app.PERMISSIONS[role]})
            self.assertEqual(len([c for c in transport.calls if c[1].endswith("/access_tokens")]), 1)
            self.assertEqual(transport.calls[1][3], "token ghs_secret")
        self.assertNotIn("checks", github_app.PERMISSIONS["pr"])

    def test_merge_and_approve_pin_the_exact_commit(self):
        transport = Transport()
        repo_app = app("merge", transport)
        repo_app.approve(7, "b" * 40, "ok")
        repo_app.merge(7, "b" * 40)
        repo_app.create_check("b" * 40, "summary")
        approve, merge, check = transport.calls[1:]
        self.assertEqual(approve[2]["commit_id"], "b" * 40)
        self.assertEqual((merge[0], merge[1], merge[2]["sha"]), ("PUT", "/repos/example/repo/pulls/7/merge", "b" * 40))
        self.assertEqual((check[2]["name"], check[2]["head_sha"]), ("codex-verification", "b" * 40))

    def test_errors_never_leak_key_or_token(self):
        def failing(method, path, body=None, auth=None):
            if path.endswith("/access_tokens"):
                return {"token": "ghs_secret"}
            raise github_app.GitHubWriteError(422, "Validation Failed")
        with self.assertRaises(github_app.GitHubWriteError) as caught:
            app("merge", failing).merge(1, "b" * 40)
        self.assertEqual(caught.exception.status, 422)
        for secret in ("ghs_secret", KEY.decode()):
            self.assertNotIn(secret, str(caught.exception))
        with mock.patch("subprocess.run", side_effect=FileNotFoundError("op")):
            with self.assertRaises(ProviderError) as missing:
                github_app.read_key("op://v/item/key")
        self.assertNotIn("op://v/item/key", str(missing.exception))

    def test_op_token_file_reaches_only_op_environment(self):
        ok = subprocess.CompletedProcess([], 0, KEY, b"")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "token"
            path.write_text("ops_secret\n")
            path.chmod(0o600)
            env = {"CONTRACT_MASTER_OP_TOKEN_FILE": str(path)}
            with mock.patch.dict("os.environ", env, clear=True), \
                    mock.patch("subprocess.run", return_value=ok) as run:
                self.assertEqual(github_app.read_key("op://v/item/key"), KEY)
            self.assertEqual(run.call_args[0][0], ["op", "read", "op://v/item/key"])
            self.assertEqual(run.call_args[1]["env"]["OP_SERVICE_ACCOUNT_TOKEN"], "ops_secret")
            self.assertNotIn("ops_secret", " ".join(run.call_args[0][0]))
            with mock.patch.dict("os.environ", dict(env, OP_SERVICE_ACCOUNT_TOKEN="from_env"), clear=True):
                self.assertEqual(github_app.op_environment()["OP_SERVICE_ACCOUNT_TOKEN"], "from_env")
            path.chmod(0o640)
            with mock.patch.dict("os.environ", env, clear=True), mock.patch("subprocess.run", return_value=ok):
                with self.assertRaises(ProviderError) as loose:
                    github_app.read_key("op://v/item/key")
            self.assertNotIn("ops_secret", str(loose.exception))
        with mock.patch.dict("os.environ", {"CONTRACT_MASTER_OP_TOKEN_FILE": "/nonexistent/token"}, clear=True):
            self.assertNotIn("OP_SERVICE_ACCOUNT_TOKEN", github_app.op_environment())

    def test_push_keeps_token_out_of_argv_and_only_task_branches(self):
        repo_app = app("pr")
        with self.assertRaises(ContractError): repo_app.push("/tmp", "b" * 40, "main")
        with mock.patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, b"", b"")) as run:
            repo_app.push("/work", "b" * 40, "task/one")
        argv, env = run.call_args[0][0], run.call_args[1]["env"]
        self.assertFalse(any("ghs_secret" in part for part in argv))
        self.assertEqual(env["CONTRACT_MASTER_GIT_TOKEN"], "ghs_secret")
        self.assertIn("b" * 40 + ":refs/heads/task/one", argv)
        self.assertNotIn("--force", argv)

    def test_configuration_problems(self):
        self.assertEqual(github_app.problems(POLICY), [])
        cases = {
            "not configured": {"pr": dict(POLICY["github_apps"]["pr"], app_id=None)},
            "op:// reference": {"pr": dict(POLICY["github_apps"]["pr"], key_reference="/home/key.pem")},
            "must be different": {"pr": dict(POLICY["github_apps"]["merge"])},
        }
        for message, update in cases.items():
            policy = dict(POLICY, github_apps=dict(POLICY["github_apps"], **update))
            self.assertTrue(any(message in p for p in github_app.problems(policy)), message)
        mismatch = dict(POLICY, merge_identity={"login": "someone", "type": "User"})
        self.assertTrue(any("merge_identity" in p for p in github_app.problems(mismatch)))
        self.assertEqual(github_app.base_branch({"base_ref": "origin/main"}), "main")


if __name__ == "__main__":
    unittest.main()
