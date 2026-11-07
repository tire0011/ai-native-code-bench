"""Local, unmodified Ollama server-log snapshots for benchmark failures."""
from pathlib import Path
import os
import shutil
import datetime as dt

def capture_ollama_logs(destination):
    """Copy raw logs locally, without truncation, redaction or publishing."""
    source = Path(os.environ.get("LOCALAPPDATA", "")) / "Ollama"
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    copied = []
    for path in sorted(source.glob("server*.log")) if source.is_dir() else []:
        if path.is_file():
            target = destination / path.name
            shutil.copy2(path, target)
            copied.append(str(target))
    return copied

def ollama_diagnostics(destination):
    """Collect raw local logs; return only structured availability metadata."""
    try:
        paths = capture_ollama_logs(destination)
        return {"log_files_copied": len(paths), "logs_local_only": True}
    except OSError as exc:
        return {"log_files_copied": 0, "logs_local_only": True,
                "capture_error_type": type(exc).__name__}
