"""Episodic memory: every turn in SQLite, with embeddings for recall.

Deviation from the blueprint, which names Chroma: embeddings live in the same
SQLite file as BLOBs and similarity is a brute-force cosine in numpy. For the
scale this will ever reach (thousands of turns, 768-dim vectors) that is
sub-millisecond, and it avoids a heavy dependency and a second datastore on a
machine already running Ollama. Swapping in Chroma later means replacing
`recall()` and nothing else.

Nothing here leaves the machine. Embeddings are produced by the local
nomic-embed-text model.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import urllib.request
from datetime import datetime
from pathlib import Path

import numpy as np

SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       TEXT NOT NULL,
    session  TEXT NOT NULL,
    role     TEXT NOT NULL,
    text     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session);
CREATE INDEX IF NOT EXISTS idx_turns_ts      ON turns(ts);

-- one embedding per user/assistant exchange, not per message
CREATE TABLE IF NOT EXISTS episodes (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT NOT NULL,
    session   TEXT NOT NULL,
    summary   TEXT NOT NULL,
    vec       BLOB
);
CREATE INDEX IF NOT EXISTS idx_episodes_ts ON episodes(ts);
"""


class Store:
    def __init__(self, path: Path, embed_host: str, embed_model: str = "nomic-embed-text"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.embed_host = embed_host.rstrip("/")
        self.embed_model = embed_model
        self._local = threading.local()
        self._last_error: str | None = None
        with self._conn() as c:
            c.executescript(SCHEMA)
        self.session = datetime.now().strftime("%Y%m%d-%H%M%S")

    def _conn(self) -> sqlite3.Connection:
        # sqlite connections are not shareable across threads
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(self.path, timeout=10)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    # ---------- writing ----------
    def add_turn(self, role: str, text: str) -> bool:
        """A failed write must not cost Neo his reply, so this swallows and
        records rather than raising."""
        try:
            with self._conn() as c:
                c.execute(
                    "INSERT INTO turns (ts, session, role, text) VALUES (?,?,?,?)",
                    (datetime.now().isoformat(timespec="seconds"),
                     self.session, role, text),
                )
            return True
        except Exception as e:                      # noqa: BLE001
            self._last_error = repr(e)
            return False

    def add_episode(self, user_text: str, reply_text: str) -> bool:
        """Store an exchange and embed it. Called off the hot path, on a daemon
        thread, so it must never raise: an unhandled exception there prints a
        raw traceback at the user and loses the turn silently anyway. Returns
        whether it was stored."""
        try:
            return self._add_episode(user_text, reply_text)
        except Exception as e:                      # noqa: BLE001
            self._last_error = repr(e)
            return False

    def _add_episode(self, user_text: str, reply_text: str) -> bool:
        summary = f"Neo: {user_text}\nCapri: {reply_text}"
        vec = self.embed(summary)
        blob = vec.astype(np.float32).tobytes() if vec is not None else None
        with self._conn() as c:
            c.execute(
                "INSERT INTO episodes (ts, session, summary, vec) VALUES (?,?,?,?)",
                (datetime.now().isoformat(timespec="seconds"), self.session, summary, blob),
            )
        return True

    # ---------- embedding ----------
    def embed(self, text: str, kind: str = "document") -> np.ndarray | None:
        """nomic-embed-text is trained with task prefixes and expects them.
        Without them every pair lands in a narrow 0.55-0.58 band and the
        threshold becomes a coin flip; with them the scores actually separate.
        """
        if self.embed_model.startswith("nomic-embed"):
            text = f"search_{'query' if kind == 'query' else 'document'}: {text}"
        payload = {"model": self.embed_model, "prompt": text}
        req = urllib.request.Request(
            f"{self.embed_host}/api/embeddings",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                v = json.loads(r.read()).get("embedding")
            if not v:
                return None
            a = np.asarray(v, dtype=np.float32)
            n = np.linalg.norm(a)
            return a / n if n else a
        except Exception:
            return None

    # ---------- reading ----------
    def recall(self, query: str, k: int = 3, min_score: float = 0.55) -> list[dict]:
        """Semantically closest past exchanges. Empty list if nothing is close."""
        qv = self.embed(query, kind="query")
        if qv is None:
            return []
        try:
            rows = self._conn().execute(
                "SELECT id, ts, summary, vec FROM episodes WHERE vec IS NOT NULL"
            ).fetchall()
        except Exception as e:                      # noqa: BLE001
            self._last_error = repr(e)
            return []
        if not rows:
            return []
        mat = np.vstack([np.frombuffer(r["vec"], dtype=np.float32) for r in rows])
        scores = mat @ qv                      # vectors are already normalised
        order = np.argsort(-scores)[:k]
        out = []
        for i in order:
            if float(scores[i]) < min_score:
                continue
            out.append({
                "ts": rows[i]["ts"],
                "summary": rows[i]["summary"],
                "score": round(float(scores[i]), 3),
            })
        return out

    def unindex(self, query: str) -> int:
        """Make matching episodes unrecallable, without deleting the record.

        This exists because recall entrenches her own mistakes. Measured: with
        a thin facts file she invented "CS101 assignment, due today at 5pm",
        that reply was stored as an episode, recall fed it back, and the next
        five answers repeated it verbatim - one even added "like I told you
        twice already". A single hallucination became durable memory that
        cites itself.

        Clearing `vec` removes it from retrieval so it stops influencing her,
        while the turn log keeps what was actually said. Forgetting should not
        rewrite history, it should stop acting on it.
        """
        q = query.strip().rstrip(".")
        if not q:
            return 0
        try:
            with self._conn() as c:
                cur = c.execute(
                    "UPDATE episodes SET vec = NULL "
                    "WHERE vec IS NOT NULL AND lower(summary) LIKE ?",
                    (f"%{q.lower()}%",),
                )
                return cur.rowcount or 0
        except Exception as e:                      # noqa: BLE001
            self._last_error = repr(e)
            return 0

    def stats(self) -> dict:
        try:
            c = self._conn()
        except Exception as e:                      # noqa: BLE001
            return {"turns": 0, "episodes": 0, "embedded": 0, "error": repr(e)}
        return {
            "turns": c.execute("SELECT COUNT(*) FROM turns").fetchone()[0],
            "episodes": c.execute("SELECT COUNT(*) FROM episodes").fetchone()[0],
            "embedded": c.execute(
                "SELECT COUNT(*) FROM episodes WHERE vec IS NOT NULL").fetchone()[0],
            # a store that is quietly failing should be visible in /health
            # rather than invisible, since writes never raise
            **({"last_error": self._last_error} if self._last_error else {}),
        }
