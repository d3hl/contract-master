import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from contract_master.contracts import ROOT


class CliTests(unittest.TestCase):
    def run_cli(self, registry, *args):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "registry.json"
            path.write_text(json.dumps(registry))
            return subprocess.run([sys.executable, "-m", "contract_master", "--registry", str(path),
                                   "--database", str(Path(temp) / "state.sqlite3"), *args],
                                  cwd=str(ROOT), capture_output=True, text=True, timeout=60)

    def test_failed_git_call_returns_json_error(self):
        missing = "f" * 40  # allowlisted but absent from Git, so `git rev-parse` fails
        run = self.run_cli({"reviewed_master_commits": [missing], "repositories": {}}, "bundle", missing)
        self.assertEqual(run.returncode, 1)
        self.assertFalse(json.loads(run.stderr)["ok"])
        self.assertNotIn("Traceback", run.stderr)


if __name__ == "__main__":
    unittest.main()
