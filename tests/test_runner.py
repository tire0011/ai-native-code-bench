import json
import unittest
from runner import parse_events, tool_name, build_opencode_command

class RunnerTests(unittest.TestCase):
    def test_real_tool(self):
        raw = '\n'.join([
            json.dumps({'type': 'tool_use', 'part': {'tool': 'roslyn_find_symbol'}}),
            json.dumps({'type': 'text', 'part': {'text': '{"name":"tools.roslyn.fake"}'}})
        ])
        self.assertEqual(parse_events(raw)['roslyn_calls'], 1)
        self.assertEqual(parse_events(raw)['tool_calls_total'], 1)

    def test_text_not_tool(self):
        self.assertEqual(parse_events(json.dumps({
            'type': 'text', 'part': {'text': 'roslyn_find_symbol'}
        }))['tool_calls_total'], 0)

    def test_invalid_lines(self):
        self.assertEqual(parse_events('invalid\n{}')['tool_calls_total'], 0)

    def test_invalid_tool_name(self):
        self.assertIsNone(tool_name({'type':'tool_use','part':{'tool':'bad;command'}}))

    def test_opencode_v2_flags(self):
        cmd = build_opencode_command('ollama/qwen2.5-coder:7b', 'hello')
        self.assertEqual(cmd[:2], ['run', '--standalone'])
        self.assertEqual(cmd[cmd.index('--agent') + 1], 'build')
        self.assertNotIn('--archived', cmd)
        self.assertEqual(cmd[-1], 'hello')

    def test_scip_protobuf_symbols(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from scip_context import fields, occurrences, extract_symbol_context

        def vint(value):
            out = bytearray()
            while value > 127:
                out.append((value & 127) | 128)
                value >>= 7
            return bytes(out + bytes([value]))

        def blob(number, payload):
            return vint(number * 8 + 2) + vint(len(payload)) + payload

        def numeric(number, value):
            return vint(number * 8) + vint(value)

        sym = b"scip-dotnet . pkg . Example/BaseEntity#"
        definition = blob(1, bytes([2, 0, 10])) + blob(2, sym) + numeric(3, 1)
        reference = blob(1, bytes([2, 0, 10])) + blob(2, sym)
        doc1 = blob(1, b"BaseEntity.cs") + blob(2, definition)
        doc2 = blob(1, b"Consumer.cs") + blob(2, reference)
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "BaseEntity.cs").write_text("class BaseEntity {}\n", encoding="utf-8")
            (root / "Consumer.cs").write_text("class Consumer : BaseEntity {}\n", encoding="utf-8")
            index = root / "index.scip"
            index.write_bytes(blob(2, doc1) + blob(2, doc2))
            hits = list(occurrences(index))
            self.assertEqual(len(hits), 2)
            self.assertEqual(sum(d for _, _, _, d in hits), 1)
            context, count, symbols = extract_symbol_context(index, root)
            self.assertEqual(count, 2)
            self.assertEqual(symbols, 1)
            self.assertIn("BaseEntity.cs", context)
            self.assertIn("Consumer.cs", context)
