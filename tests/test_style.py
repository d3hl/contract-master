import unittest
from contract_master.contracts import ROOT

MAX_LINE = 120


class StyleTests(unittest.TestCase):
    def test_library_lines_fit(self):
        # No formatter is configured; this keeps the trusted manager code reviewable.
        long_lines = [str(path.relative_to(ROOT)) + ":" + str(number)
                      for path in sorted((ROOT / "contract_master").glob("*.py"))
                      for number, line in enumerate(path.read_text().splitlines(), 1) if len(line) > MAX_LINE]
        self.assertEqual(long_lines, [])


if __name__ == "__main__":
    unittest.main()
