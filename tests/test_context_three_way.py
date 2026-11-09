"""Offline regression checks for three-way context selection and strict scoring."""
import unittest
from context_three_way import ARMS, SEEDS, TARGETS, OPTIONS, make_prompt, score_answer


class ThreeWayContextTests(unittest.TestCase):
    def test_three_conditions_and_repeatable_options(self):
        self.assertEqual(ARMS, ("no_context", "aider_map", "scip"))
        self.assertGreaterEqual(len(TARGETS), 2)
        self.assertEqual(SEEDS, (42, 43))
        self.assertEqual(OPTIONS["temperature"], 0)

    def test_strict_path_scoring_penalizes_extras_and_duplicates(self):
        definition = {"src/Core/Contributor.cs"}
        references = {"src/UseCases/UpdateContributor.cs", "src/Web/Contributor.cs"}
        answer = ("src/Core/Contributor.cs\n"
                  "src/UseCases/UpdateContributor.cs\n"
                  "src/Web/Extra.cs\n"
                  "src/UseCases/UpdateContributor.cs\n")
        scored = score_answer(answer, definition, references)
        self.assertTrue(scored["definition_found"])
        self.assertEqual(scored["reference_paths_found"], 1)
        self.assertEqual(scored["unexpected_paths"], 1)
        self.assertEqual(scored["duplicate_paths"], 1)
        self.assertFalse(scored["format_valid"])

    def test_unknown_answer_never_counts_as_correct(self):
        scored = score_answer("UNKNOWN", {"src/Core/Contributor.cs"}, set())
        self.assertFalse(scored["definition_found"])
        self.assertEqual(scored["exact_path_precision"], 0.0)

    def test_resource_summary_reports_average_peak_and_missing_gpu(self):
        from resource_monitor import ResourceMonitor
        monitor = ResourceMonitor()
        monitor.rows = [
            {"cpu_percent": 20, "ram_percent": 50, "ram_used_gb": 12,
             "gpu_percent": None, "gpu_memory_mb": None},
            {"cpu_percent": 60, "ram_percent": 52, "ram_used_gb": 13,
             "gpu_percent": None, "gpu_memory_mb": None},
        ]
        report = monitor.summary()
        self.assertEqual(report["cpu_percent"]["avg"], 40)
        self.assertEqual(report["cpu_percent"]["peak"], 60)
        self.assertEqual(report["ram_used_gb"]["peak"], 13)
        self.assertIsNone(report["gpu_percent"])

    def test_two_timeouts_skip_remaining_calls(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from unittest.mock import patch
        import context_three_way as bench
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "results" / "runs").mkdir(parents=True)
            aider_map = root / "map.txt"
            aider_map.write_text("src/Core/Contributor.cs", encoding="utf-8")
            with patch.object(bench, "ROOT", root), \
                 patch.object(bench, "FIXTURE", root), \
                 patch.object(bench, "ground_truth", return_value=({"src/Core/Contributor.cs"}, set())), \
                 patch.object(bench, "extract_symbol_context", return_value=("snippet", 1, 1)), \
                 patch.object(bench, "generate", side_effect=TimeoutError("ollama stuck")) as generate:
                result = bench.compare_three_way(
                    root / "dummy.scip", aider_map=aider_map, timeout=0.01)
            self.assertEqual(generate.call_count, 2)
            self.assertEqual(result["status"], "partial")
            self.assertEqual(sum(r["status"] == "error" for r in result["results"]), 2)
            self.assertEqual(sum(r["status"] == "skipped" for r in result["results"]), 10)
            self.assertTrue(list((root / "results" / "runs").glob("context-three-way-*.json")))

    def test_same_question_format_for_every_arm(self):
        base = make_prompt("Contributor", "")
        with_context = make_prompt("Contributor", "### src/Core/Contributor.cs")
        self.assertEqual(base.split("Reference data")[0],
                         with_context.split("Reference data")[0])
        self.assertIn("### src/Core/Contributor.cs", with_context)


if __name__ == "__main__":
    unittest.main()
