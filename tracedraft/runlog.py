"""Run log — create-only run folders, SHA-256 manifests, and an append-only ledger.

Interface:
    run = RunDir.create(root, label)          # fails if it exists
    run.write_json(name, obj) / run.write_jsonl(name, rows) / run.write_bytes(name, data)
    run.seal() -> manifest sha                # MANIFEST.sha256 over every file in the run
    append_ledger(root, entry)                # runs/LEDGER.jsonl, one line per run, never rewritten
"""
from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from pathlib import Path


class RunDir:
    def __init__(self, path: Path):
        self.path = path

    @classmethod
    def create(cls, root: str | Path, label: str) -> "RunDir":
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        path = root / f"{stamp}_{label}"
        n = 1
        while path.exists():
            n += 1
            path = root / f"{stamp}_{label}_{n}"
        path.mkdir()
        return cls(path)

    def _new(self, name: str) -> Path:
        p = self.path / name
        if p.exists():
            raise FileExistsError(f"create-only: {p}")
        return p

    def write_bytes(self, name: str, data: bytes) -> Path:
        p = self._new(name)
        p.write_bytes(data)
        return p

    def write_json(self, name: str, obj) -> Path:
        return self.write_bytes(name, (json.dumps(obj, ensure_ascii=False, indent=1, default=str) + "\n").encode("utf-8"))

    def write_jsonl(self, name: str, rows) -> Path:
        body = "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in rows)
        return self.write_bytes(name, body.encode("utf-8"))

    def seal(self) -> str:
        lines = []
        for p in sorted(self.path.rglob("*")):
            if p.is_file() and p.name != "MANIFEST.sha256":
                lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(self.path).as_posix()}")
        body = "\n".join(lines) + "\n"
        self.write_bytes("MANIFEST.sha256", body.encode("utf-8"))
        return hashlib.sha256(body.encode("utf-8")).hexdigest()


def environment() -> dict:
    return {"python": sys.version.split()[0], "platform": platform.platform(), "machine": platform.machine(),
            "hw": hardware()}


def _ram_gb() -> float | None:
    try:
        if sys.platform == "win32":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MS()
            m.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return round(m.ullTotalPhys / 2**30, 1)
        import os
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30, 1)
    except Exception:
        return None


def hardware() -> dict:
    """Hardware fingerprint recorded with every run, so the same harness can be compared across machines.
    Best effort: a missing tool gives None, never an error."""
    import os
    import subprocess
    gpu = None
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            gpu = [line.strip() for line in out.stdout.strip().splitlines()]
    except Exception:
        gpu = None
    cpu = platform.processor() or None
    if sys.platform == "win32":
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            cpu = winreg.QueryValueEx(k, "ProcessorNameString")[0].strip()
        except Exception:
            pass
    return {"cpu": cpu, "logical_cpus": os.cpu_count(), "ram_gb": _ram_gb(), "gpu": gpu}


def ollama_residency(base_url: str = "http://127.0.0.1:11434") -> list[dict] | None:
    """What Ollama has loaded and how much of it sits in VRAM (size_vram / size). None when unreachable."""
    import urllib.request
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/api/ps", timeout=3) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [{"model": m.get("name"), "size_gb": round((m.get("size") or 0) / 2**30, 2),
                 "vram_gb": round((m.get("size_vram") or 0) / 2**30, 2),
                 "gpu_share": round((m.get("size_vram") or 0) / m["size"], 3) if m.get("size") else None}
                for m in data.get("models", [])]
    except Exception:
        return None


def append_ledger(root: str | Path, entry: dict) -> None:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / "LEDGER.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def read_ledger(root: str | Path) -> list[dict]:
    p = Path(root) / "LEDGER.jsonl"
    if not p.is_file():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
