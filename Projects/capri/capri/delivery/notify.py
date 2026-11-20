"""Desktop notifications, through the freedesktop spec on KDE's own daemon.

Sends with `gdbus call`, not `notify-send`. Measured on this machine:
`notify-send -p -A ...` does not flush the notification id until the process
exits, and `-A` makes it wait for the user - so the id for a notification with
buttons arrives minutes late or never. Without the id a repeat cannot REPLACE
the previous popup, and six tier-0 repeats become six stacked popups, which is
precisely the behaviour that would get this feature deleted.

`gdbus call ... Notify` returns the id immediately and exits. Button presses
come back as ActionInvoked signals on one long-lived `gdbus monitor`, which is
best-effort: if the monitor dies, buttons stop working and every other
acknowledgement path (completing the task in TickTick, the CLI, telling her in
chat) still does.

The server here is Plasma 5.27.12, spec 1.2.

Task titles are DATA. They are markup-escaped before display and
GVariant-escaped before they reach the bus; a quote in a task title must not
be able to malform the call, and there is no model in this path for a title to
give instructions to.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from typing import Callable

DEST = "org.freedesktop.Notifications"
OBJ = "/org/freedesktop/Notifications"

# urgency byte per the spec: 0 low, 1 normal, 2 critical
URGENCY = {"low": 0, "normal": 1, "critical": 2}

# A critical notification must not expire. On KDE that keeps it on screen until
# he dismisses it, which is the entire difference between "deadline" and
# "something flashed while I was in a game".
EXPIRY_MS = {"low": 8000, "normal": 20000, "critical": 0}

ICONS = {0: "dialog-warning", 1: "view-task", 2: "view-task-add",
         3: "applications-multimedia"}


def _markup(s: str) -> str:
    """Plasma renders a small HTML subset in the body. Show titles literally."""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _gv(s: str) -> str:
    """A GVariant single-quoted string. Escaping is not optional: TickTick
    titles contain apostrophes, and an unescaped one makes gdbus reject the
    whole call with a parse error - i.e. silently no notification."""
    out = str(s).replace("\\", "\\\\").replace("'", "\\'")
    return "'" + out.replace("\n", "\\n").replace("\r", "") + "'"


@dataclass
class Sent:
    ok: bool
    id: int = 0
    error: str = ""


class Notifier:
    def __init__(self, *, app: str = "Capri", dry_run: bool = False,
                 actions: bool = True, timeout_s: float = 6.0):
        self.app = app
        self.dry_run = dry_run
        self.actions_enabled = actions
        self.timeout_s = timeout_s
        self.gdbus = shutil.which("gdbus")
        self._monitor: subprocess.Popen | None = None
        self._on_action: Callable[[int, str], None] | None = None

    # ---------- health ----------
    def available(self) -> bool:
        if not self.gdbus:
            return False
        try:
            r = subprocess.run(
                [self.gdbus, "call", "--session", "--dest", DEST,
                 "--object-path", OBJ,
                 "--method", f"{DEST}.GetServerInformation"],
                capture_output=True, text=True, timeout=self.timeout_s)
            return r.returncode == 0
        except Exception:                       # noqa: BLE001
            return False

    def server(self) -> str:
        try:
            r = subprocess.run(
                [self.gdbus, "call", "--session", "--dest", DEST,
                 "--object-path", OBJ,
                 "--method", f"{DEST}.GetServerInformation"],
                capture_output=True, text=True, timeout=self.timeout_s)
            return r.stdout.strip() if r.returncode == 0 else r.stderr.strip()
        except Exception as e:                  # noqa: BLE001
            return repr(e)

    # ---------- send ----------
    ID_RE = re.compile(r"uint32\s+(\d+)")

    def send(self, summary: str, body: str, *, urgency: str = "normal",
             replace_id: int = 0, icon: str = "dialog-information",
             buttons: list[tuple[str, str]] | None = None,
             category: str = "capri.reminder") -> Sent:
        """Post one notification. Returns its id, for replacing it later.

        `buttons` is [(key, label), ...]; keys come back through the monitor.
        """
        if self.dry_run:
            return Sent(True, 0, "dry run")
        if not self.gdbus:
            return Sent(False, 0, "gdbus not found")

        acts: list[str] = []
        if buttons and self.actions_enabled:
            for key, label in buttons:
                acts += [_gv(key), _gv(label)]
        actions_gv = "[" + ", ".join(acts) + "]" if acts else "@as []"

        hints = (f"{{'urgency': <byte {URGENCY.get(urgency, 1)}>, "
                 f"'category': <{_gv(category)}>, "
                 # survive a Plasma restart rather than vanishing silently
                 f"'resident': <false>}}")

        argv = [self.gdbus, "call", "--session", "--dest", DEST,
                "--object-path", OBJ, "--method", f"{DEST}.Notify",
                self.app, str(int(replace_id)), icon,
                _markup(summary), _markup(body),
                actions_gv, hints, str(EXPIRY_MS.get(urgency, 20000))]
        try:
            r = subprocess.run(argv, capture_output=True, text=True,
                               timeout=self.timeout_s)
        except subprocess.TimeoutExpired:
            return Sent(False, 0, "notification daemon did not answer")
        except Exception as e:                  # noqa: BLE001
            return Sent(False, 0, repr(e))
        if r.returncode != 0:
            return Sent(False, 0, (r.stderr or "gdbus failed").strip()[:200])
        m = self.ID_RE.search(r.stdout or "")
        return Sent(True, int(m.group(1)) if m else 0)

    def close(self, notif_id: int) -> bool:
        if self.dry_run or not self.gdbus or not notif_id:
            return False
        try:
            r = subprocess.run(
                [self.gdbus, "call", "--session", "--dest", DEST,
                 "--object-path", OBJ,
                 "--method", f"{DEST}.CloseNotification", str(int(notif_id))],
                capture_output=True, text=True, timeout=self.timeout_s)
            return r.returncode == 0
        except Exception:                       # noqa: BLE001
            return False

    # ---------- button presses ----------
    # /org/freedesktop/Notifications: org.freedesktop.Notifications.ActionInvoked (uint32 7, 'done')
    ACTION_RE = re.compile(r"\.ActionInvoked\s*\(uint32\s+(\d+),\s*'([^']*)'")
    CLOSED_RE = re.compile(r"\.NotificationClosed\s*\(uint32\s+(\d+),\s*uint32\s+(\d+)")

    def watch_actions(self, on_action: Callable[[int, str], None]) -> bool:
        """Start the signal monitor. Best-effort, and never fatal: without it
        the buttons simply do nothing and the other ack paths are unaffected."""
        if not self.gdbus or not self.actions_enabled:
            return False
        self._on_action = on_action
        try:
            self._monitor = subprocess.Popen(
                [self.gdbus, "monitor", "--session", "--dest", DEST],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, bufsize=1)
        except Exception:                       # noqa: BLE001
            self._monitor = None
            return False
        threading.Thread(target=self._pump, daemon=True).start()
        return True

    def _pump(self) -> None:
        mon = self._monitor
        if mon is None or mon.stdout is None:
            return
        for line in mon.stdout:
            m = self.ACTION_RE.search(line)
            if m and self._on_action:
                try:
                    self._on_action(int(m.group(1)), m.group(2))
                except Exception:               # noqa: BLE001
                    pass                        # a bad handler must not end the pump

    def stop(self) -> None:
        if self._monitor and self._monitor.poll() is None:
            self._monitor.terminate()
