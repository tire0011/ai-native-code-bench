"""Best-effort system telemetry for benchmark runs; no third-party dependencies.

CPU percentage is system-wide (not per Ollama process). GPU metrics require nvidia-smi.
Only aggregated numbers are published; individual samples stay local.
"""
import ctypes
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import threading
import time


def cpu_and_memory():
    if os.name != "nt":
        return None, None, None
    from ctypes import wintypes
    class FILETIME(ctypes.Structure):
        _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]
        def ticks(self):
            return (self.high << 32) | self.low
    idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
    if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        return None, None, None
    class MEMORYSTATUS(ctypes.Structure):
        _fields_ = [("length", wintypes.DWORD), ("memory_load", wintypes.DWORD),
                    ("total_physical", ctypes.c_ulonglong), ("available_physical", ctypes.c_ulonglong),
                    ("total_page", ctypes.c_ulonglong), ("available_page", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong), ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended", ctypes.c_ulonglong)]
    mem = MEMORYSTATUS()
    mem.length = ctypes.sizeof(mem)
    ram_used = None
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):
        ram_used = round((mem.total_physical - mem.available_physical) / (1024 ** 3), 2)
    return (idle.ticks(), kernel.ticks(), user.ticks()), mem.memory_load if ram_used is not None else None, ram_used


def gpu_sample():
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, "--query-gpu=utilization.gpu,memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=4)
        if proc.returncode != 0:
            return None
        first = proc.stdout.splitlines()[0].split(",")
        return float(first[0].strip()), float(first[1].strip())
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


class ResourceMonitor:
    def __init__(self, interval=3):
        self.interval = interval
        self.rows = []
        self.stop_event = threading.Event()
        self.thread = None

    def _run(self):
        previous = None
        while not self.stop_event.is_set():
            ticks, ram_pct, ram_gb = cpu_and_memory()
            cpu = None
            if ticks and previous:
                idle_delta = ticks[0] - previous[0]
                total_delta = (ticks[1] - previous[1]) + (ticks[2] - previous[2])
                if total_delta > 0:
                    cpu = round(max(0, min(100, 100 * (1 - idle_delta / total_delta))), 1)
            if ticks:
                previous = ticks
            gpu = gpu_sample()
            self.rows.append({"cpu_percent": cpu, "ram_percent": ram_pct,
                              "ram_used_gb": ram_gb,
                              "gpu_percent": gpu[0] if gpu else None,
                              "gpu_memory_mb": gpu[1] if gpu else None})
            self.stop_event.wait(self.interval)

    def __enter__(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop_event.set()
        self.thread.join(timeout=6)

    def summary(self):
        result = {"samples": len(self.rows), "interval_seconds": self.interval}
        for key in ("cpu_percent", "ram_percent", "ram_used_gb",
                    "gpu_percent", "gpu_memory_mb"):
            values = [r[key] for r in self.rows if r[key] is not None]
            result[key] = {"avg": round(statistics.mean(values), 2),
                           "peak": round(max(values), 2)} if values else None
        return result
