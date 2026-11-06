"""Ensure timed-out Qwen A/B runs are not marked complete."""
import unittest
from pathlib import Path


class LegacyComparisonStatusTests(unittest.TestCase):
    def test_timeout_cases_prevent_complete_status(self):
        source = (Path(__file__).resolve().parents[1] / "context_compare.py").read_text(encoding="utf-8")
        self.assertIn('all(case.get("ok") for case in result["cases"].values())', source)
        self.assertIn('else "partial"', source)


if __name__ == "__main__":
    unittest.main()
