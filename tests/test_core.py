import json
import unittest
from unittest.mock import patch

from bench.core import json_object, python_source, visible_result
from bench.edict import EdictSession, decode_tool_result, nested_value


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


if __name__ == "__main__":
    unittest.main()
