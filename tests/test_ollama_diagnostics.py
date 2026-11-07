import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ollama_diagnostics import capture_ollama_logs, ollama_diagnostics


class OllamaDiagnosticsTests(unittest.TestCase):
    def test_raw_log_copied_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "Ollama"
            source.mkdir()
            raw = b"original log\r\n\xff secret=unchanged\n"
            (source / "server.log").write_bytes(raw)
            with patch.dict("os.environ", {"LOCALAPPDATA": str(root)}):
                result = capture_ollama_logs(root / "local-results")
            self.assertEqual(len(result), 1)
            self.assertEqual(Path(result[0]).read_bytes(), raw)

    def test_missing_logs_are_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"LOCALAPPDATA": tmp}):
                self.assertEqual(ollama_diagnostics(Path(tmp) / "local-results"),
                                 {"log_files_copied": 0, "logs_local_only": True})


if __name__ == "__main__":
    unittest.main()
