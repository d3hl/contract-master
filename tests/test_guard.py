import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from contract_master import guard
from contract_master.contracts import ROOT


def bash(command):
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def write(path, cwd="/"):
    return {"tool_name": "Write", "tool_input": {"file_path": path, "content": "x"}, "cwd": cwd}


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "config").mkdir()
        registry = {"repositories": {"a/b": {"runner_config": "config/deepseek.json"},
                                     "c/d": {"runner_config": "config/off.json"}}}
        (self.root / "config/registry.json").write_text(json.dumps(registry))
        (self.root / "config/deepseek.json").write_text(json.dumps(
            {"role": "deepseek", "enabled": True, "environment": "rh1-d3", "agent": "opencode2"}))
        (self.root / "config/off.json").write_text(json.dumps(
            {"role": "deepseek", "enabled": False, "environment": "old", "agent": "opencode1"}))

    def tearDown(self):
        self.tmp.cleanup()

    def blocked(self, event):
        return guard.check(event, self.root)

    def test_edits_outside_temp_are_blocked(self):
        self.assertIn("DeepSeek", self.blocked(write(str(ROOT / "contract_master/manager.py"))))
        self.assertIsNotNone(self.blocked(write("src/app.py", cwd=str(ROOT))))
        self.assertIsNotNone(self.blocked({"tool_name": "NotebookEdit", "tool_input": {"notebook_path": "/srv/n.ipynb"}}))
        self.assertIsNotNone(self.blocked({"tool_name": "Edit", "tool_input": {}}))
        self.assertIsNotNone(self.blocked(write(tempfile.gettempdir() + "/../etc/passwd")))

    def test_spec_files_in_temp_are_allowed(self):
        self.assertIsNone(self.blocked(write(tempfile.gettempdir() + "/claude-1/spec.md")))
        self.assertIsNone(self.blocked(write("spec.md", cwd=tempfile.gettempdir())))

    def test_commit_push_and_merge_are_blocked(self):
        for command in ("git commit -m x", "git -C /repo push origin main", "cd x && git commit -F m.txt",
                        "GIT_AUTHOR_NAME=a git commit", "/usr/bin/gh pr merge 5 --squash"):
            self.assertIsNotNone(self.blocked(bash(command)), command)
        for command in ("git status", "git log --grep commit", "gh pr view 5", "echo git commit",
                        "python3 -m contract_master codex-merge T tok", "codex exec review < /dev/null"):
            self.assertIsNone(self.blocked(bash(command)), command)

    def test_quoted_newlines_stay_inside_one_word(self):
        review = 'codex exec "Review this diff.\nRun git diff and the registered checks." < /dev/null'
        self.assertIsNone(self.blocked(bash(review)))
        self.assertEqual(guard.segments(review)[0][:2], ["codex", "exec"])
        self.assertIsNone(self.blocked(bash("echo 'a\ngit commit'")))
        self.assertIsNotNone(self.blocked(bash("git status\ngit commit -m x")))
        self.assertIsNotNone(self.blocked(bash('echo "a\nb"\ngit push')))
        self.assertIsNotNone(self.blocked(bash("cd x &&\ngit commit -m x")))

    def test_worker_start_must_target_a_registered_runner(self):
        ok = "orca orchestration worker-start --task t --on rh1-d3 --agent opencode2 --json"
        self.assertIsNone(self.blocked(bash(ok)))
        self.assertIsNone(self.blocked(bash("$ORCA orchestration worker-start --on=rh1-d3 --agent=opencode2")))
        for command in ("orca orchestration worker-start --task t --worktree current --agent opencode2",
                        "orca orchestration worker-start --on rh1-d3 --agent claude",
                        "orca orchestration worker-start --on old --agent opencode1",
                        ok + " & orca orchestration worker-start --environment local --agent codex"):
            reason = self.blocked(bash(command))
            self.assertIsNotNone(reason, command)
        self.assertIn("--on rh1-d3 --agent opencode2", self.blocked(bash("orca orchestration worker-start")))
        self.assertIsNotNone(self.blocked(bash("timeout 60 orca orchestration worker-start --agent codex")))

    def test_worker_start_as_an_argument_is_not_a_launch(self):
        for command in ("rg worker-start docs/operations/orca.md", "echo worker-start",
                        "grep -n 'orchestration worker-start' docs/operations/orca.md",
                        "orca skills get orchestration --reference worker-start"):
            self.assertIsNone(self.blocked(bash(command)), command)

    def test_no_handoff_to_claude(self):
        self.assertIsNotNone(self.blocked(bash('orca worktree create --name x --agent claude --prompt "do it"')))
        self.assertIsNotNone(self.blocked(bash("orca automations edit x --provider=claude-code")))

    def test_unreadable_registry_and_commands_fail_closed(self):
        (self.root / "config/registry.json").write_text("{")
        self.assertIn("registry", self.blocked(bash("orca orchestration worker-start --on rh1-d3 --agent opencode2")))
        self.assertIsNotNone(self.blocked(bash("orca orchestration worker-start --spec 'unterminated")))
        self.assertIsNone(self.blocked(bash("echo 'unterminated")))

    def test_other_tools_pass(self):
        self.assertIsNone(self.blocked({"tool_name": "Read", "tool_input": {"file_path": "/etc/hosts"}}))

    def test_real_registry_allows_the_configured_runner(self):
        runner = json.loads((ROOT / "config/deepseek-runner.json").read_text())
        self.assertIn((runner["environment"], runner["agent"]), guard.allowed_runners())

    def test_main_exit_codes(self):
        err = io.StringIO()
        self.assertEqual(guard.main(io.StringIO("not json"), err), 2)
        self.assertEqual(guard.main(io.StringIO(json.dumps({"tool_name": "Read"})), io.StringIO()), 0)
        result = subprocess.run([sys.executable, "-m", "contract_master.guard"], cwd=ROOT, capture_output=True,
                                text=True, input=json.dumps(bash("git push")))
        self.assertEqual(result.returncode, 2)
        self.assertIn("Blocked git push", result.stderr)

    def test_coordinator_settings_load_the_guard(self):
        settings = json.loads((ROOT / ".claude/coordinator-settings.json").read_text())
        entry = settings["hooks"]["PreToolUse"][0]
        self.assertEqual(set(entry["matcher"].split("|")), guard.EDIT_TOOLS | {"Bash"})
        self.assertIn("python3 -m contract_master.guard", entry["hooks"][0]["command"])
        self.assertIn("Agent(general-purpose)", settings["permissions"]["deny"])


if __name__ == "__main__":
    unittest.main()
