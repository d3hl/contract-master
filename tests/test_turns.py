import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from contract_master.contracts import ContractError, ROOT
from contract_master.store import Store
from contract_master.turns import TurnLease


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


class TurnLeaseTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "state.sqlite3"
        self.clock = Clock()
        self.lease = TurnLease(Store(self.path), self.clock)

    def test_second_turn_is_refused_while_first_holds_lease(self):
        first = self.lease.start(60)["lease"]
        with self.assertRaises(ContractError): self.lease.start(60)
        with self.assertRaises(ContractError): self.lease.check()
        # A second manager on the same database sees the same lease.
        with self.assertRaises(ContractError): TurnLease(Store(self.path), self.clock).start(60)
        self.assertEqual(self.lease.end(first), {"released": True})
        self.assertEqual(self.lease.check(), {"free": True})
        self.lease.start(60)

    def test_renew_extends_and_crashed_turn_expires(self):
        first = self.lease.start(60)["lease"]
        self.clock.now += 50 * 60
        self.lease.renew(first, 60)
        self.clock.now += 50 * 60
        with self.assertRaises(ContractError): self.lease.check()
        self.clock.now += 11 * 60  # the first turn crashed and never renewed
        self.assertEqual(self.lease.check(), {"free": True})
        second = self.lease.start(60)["lease"]
        with self.assertRaises(ContractError): self.lease.renew(first, 60)
        self.assertEqual(self.lease.end(first), {"released": False})
        with self.assertRaises(ContractError): self.lease.check()
        self.lease.end(second)

    def test_expired_lease_not_taken_over_can_still_renew(self):
        first = self.lease.start(1)["lease"]
        self.clock.now += 120
        self.lease.renew(first, 60)
        with self.assertRaises(ContractError): self.lease.start(60)

    def test_precheck_exit_codes(self):
        registry = Path(self.path.parent) / "registry.json"
        registry.write_text(json.dumps({"reviewed_master_commits": [], "repositories": {}}))

        def cli(*args):
            return subprocess.run([sys.executable, "-m", "contract_master", "--registry", str(registry),
                                   "--database", str(self.path), *args],
                                  cwd=str(ROOT), capture_output=True, text=True, timeout=60)
        self.assertEqual(cli("turn-check").returncode, 0)
        started = cli("turn-start", "--minutes", "30")
        lease = json.loads(started.stdout)["result"]["lease"]
        held = cli("turn-check")
        self.assertEqual(held.returncode, 1)
        self.assertIn("in progress", json.loads(held.stderr)["error"])
        self.assertEqual(cli("turn-start").returncode, 1)
        self.assertEqual(cli("turn-renew", lease).returncode, 0)
        self.assertEqual(cli("turn-end", lease).returncode, 0)
        self.assertEqual(cli("turn-check").returncode, 0)


if __name__ == "__main__":
    unittest.main()
