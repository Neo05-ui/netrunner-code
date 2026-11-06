"""Tier 0 tools: look, don't touch.

system_status is here for a reason beyond convenience. In real use Capri
invented "your ThinkPad's fans are still running, and the battery's..." —
she had no telemetry at all, so a friendly question got a plausible answer
instead of a true one. The persona can forbid that, but forbidding is a
patch over a missing sense. Give her the real reading and the pressure to
invent one disappears.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .registry import Result, Tier, Tool


class Sandbox:
    """Path allowlist. Every file access resolves symlinks first, then checks
    containment, so a symlink pointing outside an allowed root cannot be used
    to escape it."""

    def __init__(self, roots: list[str]):
        self.roots = [Path(r).expanduser().resolve() for r in roots]

    def resolve(self, path: str) -> Path:
        p = Path(path).expanduser()
        try:
            p = p.resolve(strict=True)
        except FileNotFoundError:
            raise ValueError(f"no such path: {path}")
        for root in self.roots:
            if p == root or root in p.parents:
                return p
        raise ValueError(f"outside the allowed folders: {path}")

    def describe(self) -> str:
        return ", ".join(str(r) for r in self.roots)


SKIP_SUFFIXES = {".db", ".sqlite", ".pyc", ".so", ".bin", ".png", ".jpg",
                 ".jpeg", ".gif", ".zip", ".pdf", ".mp3", ".mp4", ".webm"}


def build(sandbox: Sandbox) -> list[Tool]:
    def read_file(path: str, max_lines: int = 200) -> Result:
        p = sandbox.resolve(path)
        if p.is_dir():
            return Result(False, error=f"{path} is a folder — use list_dir")
        if p.suffix.lower() in SKIP_SUFFIXES:
            return Result(False, error=f"{p.suffix} is not readable as text")
        if p.stat().st_size > 2_000_000:
            return Result(False, error="file is too large to read")
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception as e:                  # noqa: BLE001
            return Result(False, error=repr(e))
        body = "\n".join(lines[:max_lines])
        return Result(True, content=body, truncated=len(lines) > max_lines)

    def list_dir(path: str) -> Result:
        p = sandbox.resolve(path)
        if not p.is_dir():
            return Result(False, error=f"{path} is not a folder")
        rows = []
        for item in sorted(p.iterdir())[:200]:
            if item.name.startswith("."):
                continue
            kind = "dir " if item.is_dir() else "file"
            size = "" if item.is_dir() else f"  {item.stat().st_size:>9,}b"
            rows.append(f"  {kind} {item.name}{size}")
        return Result(True, content="\n".join(rows) or "  (empty)")

    def system_status() -> Result:
        """Real readings only. Anything unavailable is reported as unknown,
        never guessed — an absent sensor must not become an invented one."""
        out = []
        try:
            load = os.getloadavg()
            out.append(f"load average: {load[0]:.2f} {load[1]:.2f} {load[2]:.2f}")
        except Exception:
            out.append("load average: unknown")

        try:
            up = float(Path("/proc/uptime").read_text().split()[0])
            h, m = int(up // 3600), int((up % 3600) // 60)
            out.append(f"uptime: {h}h {m}m")
        except Exception:
            out.append("uptime: unknown")

        try:
            mem = {}
            for ln in Path("/proc/meminfo").read_text().splitlines():
                k, _, v = ln.partition(":")
                mem[k] = int(v.strip().split()[0])
            total, avail = mem["MemTotal"] / 1048576, mem["MemAvailable"] / 1048576
            out.append(f"memory: {total - avail:.1f} of {total:.1f} GiB used")
        except Exception:
            out.append("memory: unknown")

        bat = Path("/sys/class/power_supply")
        found = False
        if bat.exists():
            for d in sorted(bat.iterdir()):
                cap, st = d / "capacity", d / "status"
                if cap.exists():
                    s = st.read_text().strip() if st.exists() else "unknown"
                    out.append(f"battery {d.name}: {cap.read_text().strip()}% ({s})")
                    found = True
        if not found:
            out.append("battery: no battery reported")

        temps = []
        for z in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
            try:
                t = int((z / "temp").read_text().strip()) / 1000
                if 0 < t < 150:
                    temps.append(f"{t:.0f}C")
            except Exception:
                pass
        out.append(f"temperatures: {', '.join(temps) if temps else 'unknown'}")

        try:
            fans = subprocess.run(["sensors"], capture_output=True, text=True,
                                  timeout=4).stdout
            rpm = [l.strip() for l in fans.splitlines() if "RPM" in l]
            out.append(f"fans: {rpm[0] if rpm else 'no fan reading'}")
        except Exception:
            out.append("fans: unknown (no lm-sensors)")

        return Result(True, content="\n".join(out))

    return [
        Tool("read_file",
             f"Read a text file. Allowed folders: {sandbox.describe()}. "
             f"Pass an absolute path inside one of them.",
             {"properties": {"path": {"type": "string"},
                             "max_lines": {"type": "integer"}},
              "required": ["path"]},
             Tier.READ_ONLY, read_file),
        Tool("list_dir",
             f"List a folder's contents. Allowed folders: {sandbox.describe()}. "
             f"With no better idea, pass exactly: {sandbox.roots[0]}",
             {"properties": {"path": {"type": "string"}}, "required": ["path"]},
             Tier.READ_ONLY, list_dir),
        Tool("system_status",
             "Real laptop readings: load, uptime, memory, battery, "
             "temperature, fans.",
             {"properties": {}}, Tier.READ_ONLY, system_status),
    ]
