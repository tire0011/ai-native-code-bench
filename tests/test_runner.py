import json
import unittest
from runner import parse_events

class RunnerTests(unittest.TestCase):
    def test_real_tool_events(self):
        events = '\n'.join((
            json.dumps({'type':'tool_use','part':{'tool':'roslyn_find_symbol','state':{'status':'completed'}}}),
            json.dumps({'type':'text','part':{'text':'{\\"name\\":\\"tools.roslyn.fake\\"}'}})))
        parsed = parse_events(events)
        self.assertEqual(parsed['roslyn_calls'], 1)
        self.assertEqual(parsed['tool_calls_total'], 1)
    def test_text_only_does_not_count(self):
        parsed = parse_events(json.dumps({'type':'text','part':{'text':'tools.roslyn.find_symbol'}}))
        self.assertEqual(parsed['tool_calls_total'], 0)
    def test_invalid_lines(self):
        self.assertEqual(parse_events('not json\n{}')['tool_calls_total'], 0)

if __name__ == '__main__': unittest.main()
