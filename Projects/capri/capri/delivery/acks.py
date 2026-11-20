"""The delivery ledger: what has been sent, and what he answered.

Its own SQLite file, not a new table inside capri.db. Her memory and her
notification bookkeeping have no reason to share a failure: wiping delivery
state to clear a stuck reminder should never put a scratch on the record of
every conversation they have had.

One row per task, keyed on TickTick's task id. Completing a task in TickTick
removes it from the snapshot, so it simply stops being considered - finishing
something the normal way is the easiest acknowledgement there is, and it needs
no code here at all.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .policy import Sent

SCHEMA = """
CREATE TABLE IF NOT EXISTS deliveries (
    task_id       TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    tier          INTEGER NOT NULL,
    due           TEXT,
    first_sent    TEXT,
    last_sent     TEXT,
    sends         INTEGER NOT NULL DEFAULT 0,
    acked_at      TEXT,
    ack_source    TEXT,
    snooze_until  TEXT,
    notif_id      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_deliveries_last ON deliveries(last_sent);
"""


def _dt(v) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v))
    except ValueError:
        return None


@dataclass
class Record:
    task_id: str
    title: str
    tier: int
    due: str | None
    first_sent: datetime | None
    last_sent: datetime | None
    sends: int
    acked_at: datetime | None
    ack_source: str
    snooze_until: datetime | None
    notif_id: int

    @property
    def sent(self) -> Sent:
        return Sent(sends=self.sends, last_sent=self.last_sent,
                    acked_at=self.acked_at, snooze_until=self.snooze_until,
                    notif_id=self.notif_id)


class Ledger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=5)
        c.row_factory = sqlite3.Row
        return c

    # ---------- read ----------
    def get(self, task_id: str) -> Record | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM deliveries WHERE task_id=?",
                            (task_id,)).fetchone()
        return self._row(row) if row else None

    def sent_for(self, task_id: str) -> Sent:
        """Never None: an unseen task has simply never been sent."""
        r = self.get(task_id)
        return r.sent if r else Sent()

    def all(self) -> list[Record]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM deliveries ORDER BY tier, last_sent DESC"
            ).fetchall()
        return [self._row(r) for r in rows]

    def find(self, needle: str) -> list[Record]:
        """Match on a fragment of the title, so he can acknowledge something
        by typing three words of it rather than a TickTick id."""
        n = (needle or "").strip().lower()
        if not n:
            return []
        return [r for r in self.all() if n in r.title.lower()]

    @staticmethod
    def _row(row: sqlite3.Row) -> Record:
        return Record(
            task_id=row["task_id"], title=row["title"], tier=int(row["tier"]),
            due=row["due"], first_sent=_dt(row["first_sent"]),
            last_sent=_dt(row["last_sent"]), sends=int(row["sends"] or 0),
            acked_at=_dt(row["acked_at"]), ack_source=row["ack_source"] or "",
            snooze_until=_dt(row["snooze_until"]),
            notif_id=int(row["notif_id"] or 0))

    # ---------- write ----------
    def record_send(self, task_id: str, *, title: str, tier: int,
                    due: str | None = None, notif_id: int = 0,
                    now: datetime | None = None) -> None:
        now = (now or datetime.now()).isoformat(timespec="seconds")
        with self._conn() as c:
            c.execute("""
                INSERT INTO deliveries (task_id, title, tier, due, first_sent,
                                        last_sent, sends, notif_id)
                VALUES (?,?,?,?,?,?,1,?)
                ON CONFLICT(task_id) DO UPDATE SET
                    title=excluded.title,
                    tier=excluded.tier,
                    due=excluded.due,
                    last_sent=excluded.last_sent,
                    sends=deliveries.sends + 1,
                    notif_id=excluded.notif_id
            """, (task_id, title, int(tier), due, now, now, int(notif_id)))

    def ack(self, task_id: str, source: str = "cli",
            now: datetime | None = None) -> bool:
        now = (now or datetime.now()).isoformat(timespec="seconds")
        with self._conn() as c:
            cur = c.execute(
                "UPDATE deliveries SET acked_at=?, ack_source=?, snooze_until=NULL"
                " WHERE task_id=?", (now, source, task_id))
            return cur.rowcount > 0

    def snooze(self, task_id: str, until: datetime, source: str = "cli") -> bool:
        with self._conn() as c:
            cur = c.execute(
                "UPDATE deliveries SET snooze_until=?, ack_source=? WHERE task_id=?",
                (until.isoformat(timespec="seconds"), source, task_id))
            return cur.rowcount > 0

    def reset(self, task_id: str) -> bool:
        """Forget everything about one task, so it is treated as new again."""
        with self._conn() as c:
            return c.execute("DELETE FROM deliveries WHERE task_id=?",
                             (task_id,)).rowcount > 0

    def clear(self) -> int:
        with self._conn() as c:
            return c.execute("DELETE FROM deliveries").rowcount

    def prune(self, before: datetime) -> int:
        """Drop rows for tasks not touched since `before`. Completed tasks
        leave the snapshot and never come back, so their rows are dead weight."""
        with self._conn() as c:
            return c.execute(
                "DELETE FROM deliveries WHERE last_sent IS NOT NULL AND last_sent < ?",
                (before.isoformat(timespec="seconds"),)).rowcount
