"""The kill switch, and the circuit breaker behind it.

Built before the notifier, deliberately. Neo's instruction for this whole
project was "don't fuck my whole laptop out of impatience", and the version of
that for a notifier is: the thing that makes it stop must already work before
the thing that makes it start exists.

Two independent brakes:

  SILENCE   A file. `touch data/SILENCE` and nothing is delivered. Optionally
            holds an expiry, so "shut up for two hours" is also one command.
            It is read from disk on every check, never cached, so it stops a
            repeat cycle that is already running - including from a notification
            button, another terminal, or Dolphin.

  BREAKER   A rolling count of sends. More than `max_per_hour` in the last
            hour and delivery mutes itself until the hour has passed. This is
            not for Neo's benefit, it is for mine: the failure mode of a
            scheduler bug is thirty popups, and by then he has lost trust in
            her and no apology recovers it.

Both fail toward silence. If this file cannot be read, parsed, or written,
`check()` returns not-allowed.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

# Spelled-out units too: he types "shut up for 2 hours", not "2h".
DURATION = re.compile(
    r"^\s*(\d+)\s*(s|secs?|seconds?|m|mins?|minutes?|h|hrs?|hours?|d|days?)"
    r"\s*$", re.I)
_UNIT = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}


def parse_duration(s: str) -> timedelta | None:
    """'90m', '2h', '30s', '1d' -> timedelta. None if it is not a duration."""
    m = DURATION.match(s or "")
    if not m:
        return None
    return timedelta(**{_UNIT[m.group(2)[0].lower()]: int(m.group(1))})


@dataclass
class Verdict:
    allowed: bool
    reason: str


class Silence:
    def __init__(self, path: str | Path, *, max_per_hour: int = 6,
                 ledger: str | Path | None = None):
        self.path = Path(path)
        self.max_per_hour = int(max_per_hour)
        # the send history lives beside the switch, not in memory: a daemon
        # that crash-loops would otherwise reset its own rate limit on every
        # restart, which is exactly the situation the limit is for
        self.ledger = Path(ledger) if ledger else self.path.with_name("sent.json")

    # ---------- the switch ----------
    def engage(self, until: datetime | None = None, reason: str = "") -> None:
        """Silence delivery. `until=None` means indefinitely."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = {"reason": reason or "silenced by hand"}
        if until is not None:
            body["until"] = until.isoformat(timespec="seconds")
        self.path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")

    def release(self) -> bool:
        """Lift the silence. True if something was actually lifted."""
        try:
            self.path.unlink()
            return True
        except FileNotFoundError:
            return False

    def state(self, now: datetime | None = None) -> tuple[bool, str]:
        """(silent?, why). An expired silence file is removed as a side effect
        so that `status` and the daemon agree about the world."""
        now = now or datetime.now()
        if not self.path.exists():
            return False, ""
        try:
            raw = self.path.read_text(encoding="utf-8").strip()
        except OSError as e:
            # unreadable switch: assume it means stop. The one thing worse
            # than a missed reminder is a notifier that ignores its own brake.
            return True, f"silence file unreadable ({e.strerror}) - assuming silent"
        if not raw:
            return True, "silenced indefinitely"
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            # hand-written by a human in a hurry: `echo 2h > SILENCE` should
            # still mean something rather than being ignored
            d = parse_duration(raw)
            if d is not None:
                stamp = datetime.fromtimestamp(self.path.stat().st_mtime)
                if now < stamp + d:
                    return True, f"silenced until {(stamp + d):%H:%M}"
                self.release()
                return False, ""
            return True, "silence file unparseable - assuming silent"

        until = body.get("until")
        reason = str(body.get("reason") or "silenced")
        if not until:
            return True, reason
        try:
            end = datetime.fromisoformat(str(until))
        except ValueError:
            return True, f"{reason} (bad expiry, assuming silent)"
        if now < end:
            return True, f"{reason}, until {end:%a %H:%M}"
        self.release()
        return False, ""

    # ---------- the breaker ----------
    def _history(self) -> list[datetime]:
        try:
            raw = json.loads(self.ledger.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        out = []
        for s in raw if isinstance(raw, list) else []:
            try:
                out.append(datetime.fromisoformat(str(s)))
            except ValueError:
                continue
        return out

    def record_send(self, now: datetime | None = None) -> None:
        now = now or datetime.now()
        hist = [t for t in self._history() if now - t < timedelta(hours=1)]
        hist.append(now)
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.ledger.with_suffix(".tmp")
        tmp.write_text(json.dumps([t.isoformat(timespec="seconds")
                                   for t in hist[-100:]]), encoding="utf-8")
        os.replace(tmp, self.ledger)        # never a half-written ledger

    def sends_last_hour(self, now: datetime | None = None) -> int:
        now = now or datetime.now()
        return sum(1 for t in self._history() if now - t < timedelta(hours=1))

    # ---------- the one question the notifier asks ----------
    def check(self, now: datetime | None = None) -> Verdict:
        now = now or datetime.now()
        try:
            silent, why = self.state(now)
            if silent:
                return Verdict(False, why)
            n = self.sends_last_hour(now)
            if n >= self.max_per_hour:
                return Verdict(False, f"breaker tripped: {n} sends in the last "
                                      f"hour (limit {self.max_per_hour})")
            return Verdict(True, f"{n}/{self.max_per_hour} this hour")
        except Exception as e:                  # noqa: BLE001
            return Verdict(False, f"kill-switch error, staying quiet: {e!r}")
