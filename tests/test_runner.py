import json
import unittest
from runner import parse_events, tool_name

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
