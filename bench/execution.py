"""Execute generated Python only in a restricted Docker container."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


def run_python(source: str, *, timeout: int = 15) -> str:
    if not shutil.which("docker"):
        raise RuntimeError("Docker is required for executing untrusted generated Python")
    with tempfile.TemporaryDirectory(prefix="aicb-") as directory:
        file = Path(directory) / "solution.py"
        file.write_text(source, encoding="utf-8")
        file.chmod(0o644)
        # Docker on Linux needs search permission on the bind-mounted directory.
        Path(directory).chmod(0o755)
        args = [
            "docker", "run", "--rm", "--pull=never", "--network=none",
            "--memory=256m", "--cpus=1", "--pids-limit=64", "--read-only",
            "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--user=65534:65534", "--tmpfs", "/tmp:rw,nosuid,noexec,size=16m",
            "--mount", f"type=bind,source={directory},target=/work,readonly",
            "--workdir", "/work", "python:3.12-alpine",
            "python", "-I", "-S", "-B", "/work/solution.py",
        ]
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout).strip()[:2000])
        return result.stdout.strip()

