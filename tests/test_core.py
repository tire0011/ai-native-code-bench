import json
import unittest
from unittest.mock import MagicMock, patch

from bench.core import json_object, python_source, visible_result
from bench.edict import EdictSession, decode_tool_result, nested_value, normalize_duplicate_ids
from bench.__main__ import edict_prompt, edict_repair_prompt, run_edict
from bench.core import Generation


class CoreTests(unittest.TestCase):
    def test_extract_python_fenced(self):
        self.assertEqual(python_source("text\n```python\nprint(123)\n```"), "print(123)\n")

    def test_extract_python_raw(self):
        self.assertEqual(python_source("print(123)"), "print(123)\n")

    def test_json_object(self):
        self.assertEqual(json_object('{"kind":"module"}'), {"kind": "module"})
        with self.assertRaises(ValueError):
            json_object("[]")

    def test_mcp_diagnostics(self):
        self.assertIn("invalid", visible_result({"content": [{"type": "text", "text": "invalid"}]}))

    def test_edict_argument_mapping_object(self):
        instance = object.__new__(EdictSession)
        instance.tools = {"edict_compile": {"type": "object", "required": ["ast"],
                                            "properties": {"ast": {"type": "object"}}}}
        self.assertEqual(instance.arguments_for("edict_compile", {"kind": "module"}),
                         {"ast": {"kind": "module"}})

    def test_edict_argument_mapping_string(self):
        instance = object.__new__(EdictSession)
        instance.tools = {"edict_compile": {"type": "object", "required": ["program"],
                                            "properties": {"program": {"type": "string"}}}}
        mapped = instance.arguments_for("edict_compile", {"kind": "module"})
        self.assertEqual(json.loads(mapped["program"]), {"kind": "module"})

    def test_decode_mcp_json(self):
        self.assertEqual(decode_tool_result({"content": [{"type": "text", "text": '{"ok":true}'}]}),
                         {"ok": True})

    def test_decode_mcp_failure(self):
        with self.assertRaises(RuntimeError):
            decode_tool_result({"isError": True, "content": [{"type": "text", "text": "failed"}]})

    def test_find_wasm(self):
        self.assertEqual(nested_value({"result": {"wasm": "AAAB"}}, ("wasm",)), "AAAB")

    def test_normalize_duplicate_node_ids_preserves_source(self):
        original = {"kind": "module", "id": "same", "definitions": [
            {"kind": "fn", "id": "same", "body": [
                {"kind": "ident", "id": "same", "name": "n"},
                {"kind": "ident", "id": "unique", "name": "n"}]}]}
        normalized, changes = normalize_duplicate_ids(original)
        self.assertEqual(original["definitions"][0]["id"], "same")
        self.assertEqual(len(changes), 2)
        self.assertEqual(normalized["definitions"][0]["id"], "same-dedup-1")
        self.assertEqual(normalized["definitions"][0]["body"][0]["id"], "same-dedup-2")
        self.assertEqual(normalized["definitions"][0]["body"][1]["id"], "unique")

    def test_normalization_avoids_reserved_ids(self):
        original = {"kind": "module", "id": "a", "definitions": [
            {"kind": "fn", "id": "a", "body": [
                {"kind": "literal", "id": "a-dedup-1", "value": 0}]}]}
        normalized, changes = normalize_duplicate_ids(original)
        self.assertEqual(changes[0]["new_id"], "a-dedup-2")
        self.assertEqual(normalized["definitions"][0]["body"][0]["id"], "a-dedup-1")

    def test_edict_prompt_prohibits_invalid_nodes(self):
        prompt = edict_prompt("Compute 2 + 3")
        self.assertIn("Never reuse an id", prompt)
        self.assertIn("they are NOT Edict expression node kinds", prompt)
        self.assertIn('"op":"+"', prompt)

    def test_repair_prompt_contains_compiler_feedback(self):
        prompt = edict_repair_prompt("Compute 2 + 3", '{"kind":"module"}',
                                     '{"error":"duplicate_id"}')
        self.assertIn("duplicate_id", prompt)
        self.assertIn("Previous AST", prompt)

    @patch("bench.__main__.EdictSession")
    @patch("bench.__main__.generate")
    def test_run_edict_repairs_and_counts_all_tokens(self, generate_mock, session_cls):
        generate_mock.side_effect = [
            Generation('{"kind":"module","id":"a"}', 100, 30, 1000),
            Generation('{"kind":"module","id":"b"}', 150, 40, 2000),
        ]
        session = session_cls.return_value.__enter__.return_value
        session.compile.side_effect = [RuntimeError('{"error":"duplicate_id"}'), {"wasm": "AAAB"}]
        session.run.return_value = "5"
        record = {}
        run_edict(task={"prompt": "Compute 2+3", "expected_stdout": "5"},
                  endpoint="http://localhost:11434", model="test", max_repairs=2,
                  execute=True, record=record)
        self.assertTrue(record["passed"])
        self.assertEqual(len(record["attempts"]), 2)
        self.assertEqual(record["prompt_tokens"], 250)
        self.assertEqual(record["completion_tokens"], 70)
        self.assertEqual(record["duration_ns"], 3000)
        self.assertIn("duplicate_id", record["attempts"][0]["error"])
        self.assertIn("duplicate_id", generate_mock.call_args_list[1].kwargs["prompt"])

    @patch("bench.__main__.EdictSession")
    @patch("bench.__main__.generate")
    def test_run_edict_zero_repairs(self, generate_mock, session_cls):
        generate_mock.return_value = Generation('{"kind":"module"}', 100, 30, 1000)
        session = session_cls.return_value.__enter__.return_value
        session.compile.side_effect = RuntimeError("unknown_node_kind")
        record = {}
        run_edict(task={"prompt": "Compute 2+3", "expected_stdout": "5"},
                  endpoint="http://localhost:11434", model="test", max_repairs=0,
                  execute=True, record=record)
        self.assertIn("unknown_node_kind", record["error"])
        self.assertEqual(len(record["attempts"]), 1)

    @patch("bench.__main__.EdictSession")
    @patch("bench.__main__.generate")
    def test_wasm_execution_failure_is_not_sent_to_llm_repair(self, generate_mock, session_cls):
        generate_mock.return_value = Generation('{"kind":"module","id":"a"}', 10, 20, 30)
        session = session_cls.return_value.__enter__.return_value
        session.compile.return_value = {"wasm": "AAAB"}
        session.run.side_effect = RuntimeError("WASM instantiation error: invalid i32.store")
        record = {}
        run_edict(task={"prompt": "Compute 2+3", "expected_stdout": "5"},
                  endpoint="http://localhost:11434", model="test", max_repairs=2,
                  execute=True, record=record)
        self.assertEqual(generate_mock.call_count, 1)
        self.assertEqual(record["failure_stage"], "wasm_execution")
        self.assertTrue(record["compiled"])
        self.assertNotIn("passed", record)

    @patch("bench.__main__.generate")
    def test_generation_only_avoids_compiler(self, generate_mock):
        generate_mock.return_value = Generation('{"kind":"module"}', 10, 20, 30)
        record = {}
        run_edict(task={"prompt": "Compute 2+3", "expected_stdout": "5"},
                  endpoint="http://localhost:11434", model="test", max_repairs=2,
                  execute=False, record=record)
        self.assertEqual(record["artifact"], {"kind": "module"})
        self.assertEqual(record["prompt_tokens"], 10)


if __name__ == "__main__":
    unittest.main()
