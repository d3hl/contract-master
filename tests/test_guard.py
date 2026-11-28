import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from contract_master import guard
from contract_master.contracts import ROOT
from contract_master.store import Store
from contract_master.turns import TurnLease


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

    def test_only_read_only_subagents_run(self):
        for kind in ("Explore", "Plan", "web-fetch"):
            self.assertIsNone(self.blocked({"tool_name": "Agent", "tool_input": {"subagent_type": kind}}), kind)
        for tool_input in ({"subagent_type": "general-purpose"}, {"subagent_type": "claude"},
                           {"subagent_type": "fork"}, {"prompt": "implement it"}):
            self.assertIsNotNone(self.blocked({"tool_name": "Agent", "tool_input": tool_input}), tool_input)
        self.assertIsNotNone(self.blocked({"tool_name": "Task", "tool_input": {"subagent_type": "general-purpose"}}))

    def lease_database(self, minutes=60):
        path = self.root / "state/manager.sqlite3"
        TurnLease(Store(path)).start(minutes)
        return path

    def test_turn_lease_gates_the_guard(self):
        self.assertFalse(guard.turn_active(self.root / "missing.sqlite3"))
        (self.root / "junk.sqlite3").write_text("not a database")
        self.assertFalse(guard.turn_active(self.root / "junk.sqlite3"))
        database = self.lease_database()
        self.assertTrue(guard.turn_active(database))
        self.assertFalse(guard.turn_active(database, clock=lambda: time.time() + 2 * 3600))
        empty = self.root / "empty/manager.sqlite3"
        Store(empty)
        self.assertFalse(guard.turn_active(empty))

    def test_main_exit_codes(self):
        live, idle = self.lease_database(), self.root / "none.sqlite3"
        push = json.dumps(bash("git push"))
        self.assertEqual(guard.main(io.StringIO(push), io.StringIO(), idle), 0)
        self.assertEqual(guard.main(io.StringIO("not json"), io.StringIO(), idle), 0)
        self.assertEqual(guard.main(io.StringIO("not json"), io.StringIO(), live), 2)
        self.assertEqual(guard.main(io.StringIO(json.dumps({"tool_name": "Read"})), io.StringIO(), live), 0)
        for database, code in ((live, 2), (idle, 0)):
            environment = dict(os.environ, **{guard.DATABASE_ENV: str(database)})
            result = subprocess.run([sys.executable, "-m", "contract_master.guard"], cwd=ROOT, capture_output=True,
                                    text=True, input=push, env=environment)
            self.assertEqual(result.returncode, code, result.stderr)
            self.assertEqual("Blocked git push" in result.stderr, code == 2)

    def test_shared_settings_load_the_guard(self):
        settings = json.loads((ROOT / ".claude/settings.json").read_text())
        entry = settings["hooks"]["PreToolUse"][0]
        self.assertEqual(set(entry["matcher"].split("|")), guard.EDIT_TOOLS | guard.AGENT_TOOLS | {"Bash"})
        self.assertIn("python3 -m contract_master.guard", entry["hooks"][0]["command"])
        self.assertFalse((ROOT / ".claude/coordinator-settings.json").exists())


if __name__ == "__main__":
    unittest.main()
