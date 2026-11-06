"""TickTick, read-only.

Phase 3 ships tasks:read only. There is no code here that creates, edits or
completes anything, so a bug cannot damage Neo's task list — the worst case
is a wrong answer, which is recoverable.

Auth: an access token obtained once by scripts/ticktick_auth.py and stored in
data/ticktick_token.json. data/ is gitignored, and the repository is public
and auto-pushes, so the token must never move out of there.

API surface used (developer.ticktick.com):
  GET  /open/v1/project                       list projects
  GET  /open/v1/project/{id}/data             a project's undone tasks
  POST /open/v1/task/undone                   undone tasks in a date range
Task fields: id, projectId, title, dueDate, priority (0/1/3/5), status.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = "https://api.ticktick.com"


@dataclass
class Task:
    id: str
    project_id: str
    title: str
    due: str | None
    priority: int
    status: int

    @classmethod
    def from_api(cls, d: dict) -> "Task":
        return cls(
            id=str(d.get("id", "")),
            project_id=str(d.get("projectId", "")),
            title=str(d.get("title", "")).strip(),
            due=d.get("dueDate"),
            priority=int(d.get("priority", 0) or 0),
            status=int(d.get("status", 0) or 0),
        )


class TickTickError(Exception):
    pass


class TickTick:
    def __init__(self, token_file: Path, opener=None):
        self.token_file = Path(token_file)
        self._opener = opener            # injected in tests; no network there
        self._token: str | None = None

    # ---------- auth ----------
    @property
    def token(self) -> str:
        if self._token is None:
            if not self.token_file.exists():
                raise TickTickError(
                    "not connected — run: ./.venv/bin/python "
                    "scripts/ticktick_auth.py")
            try:
                self._token = json.loads(
                    self.token_file.read_text())["access_token"]
            except Exception as e:       # noqa: BLE001
                raise TickTickError(f"token file unreadable: {e!r}")
        return self._token

    def connected(self) -> bool:
        try:
            return bool(self.token)
        except TickTickError:
            return False

    # ---------- transport ----------
    def _call(self, method: str, path: str, body: dict | None = None):
        if self._opener is not None:
            return self._opener(method, path, body)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"{BASE}{path}", data=data, method=method,
            headers={"Authorization": f"Bearer {self.token}",
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                raw = r.read().decode()
            return json.loads(raw) if raw else []
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise TickTickError(
                    "TickTick rejected the token — re-run "
                    "scripts/ticktick_auth.py")
            raise TickTickError(f"TickTick HTTP {e.code}")
        except Exception as e:           # noqa: BLE001
            raise TickTickError(repr(e))

    # ---------- read ----------
    def projects(self) -> list[dict]:
        return self._call("GET", "/open/v1/project") or []

    def project_tasks(self, project_id: str) -> list[Task]:
        d = self._call("GET", f"/open/v1/project/{project_id}/data") or {}
        return [Task.from_api(t) for t in d.get("tasks", [])]

    def undone(self, days: int = 14) -> list[Task]:
        """Undone tasks in the next `days`. The API caps the range at 14."""
        now = datetime.now(timezone.utc)
        body = {
            "startDate": now.strftime("%Y-%m-%dT%H:%M:%S+0000"),
            "endDate": (now + timedelta(days=min(days, 14))
                        ).strftime("%Y-%m-%dT%H:%M:%S+0000"),
        }
        out = self._call("POST", "/open/v1/task/undone", body) or []
        if isinstance(out, dict):
            out = out.get("tasks", [])
        return [Task.from_api(t) for t in out]

    def project_names(self) -> dict[str, str]:
        return {str(p.get("id")): str(p.get("name", "")) for p in self.projects()}

    def all_open(self) -> list[Task]:
        """Every undone task across every project. Used when the range-based
        endpoint is unavailable, and to catch tasks with no due date at all —
        which `undone` filters out and which are exactly the ones he forgets."""
        tasks: list[Task] = []
        for p in self.projects():
            pid = p.get("id")
            if pid:
                try:
                    tasks += self.project_tasks(pid)
                except TickTickError:
                    continue
        return [t for t in tasks if t.status == 0]
