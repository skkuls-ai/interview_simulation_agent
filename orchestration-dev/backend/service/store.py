"""세션, 백그라운드 평가, 결과 저장소 (SQLite)."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

SessionStatus = Literal["created", "analyzed", "in_progress", "completed", "abandoned", "expired"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    status TEXT NOT NULL,
    consent TEXT NOT NULL,
    config TEXT NOT NULL,
    target_role TEXT,
    blueprint TEXT,
    documents_deleted_at TEXT
);
CREATE TABLE IF NOT EXISTS evaluations (
    session_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    kind TEXT NOT NULL,              -- thread | intro
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (session_id, thread_id)
);
CREATE TABLE IF NOT EXISTS results (
    session_id TEXT PRIMARY KEY,
    completed_at TEXT NOT NULL,
    summary TEXT NOT NULL,
    detail TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dump(obj: Any) -> str:
    if isinstance(obj, BaseModel):
        return obj.model_dump_json()
    return json.dumps(obj, ensure_ascii=False, default=str)


class Store:
    def __init__(self, path: str | Path):
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.conn.executescript(SCHEMA)

    def _exec(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self.lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return cur.fetchall()

    # ------------------------------------------------------------ sessions

    def create_session(self, sid: str, consent: BaseModel, config: BaseModel) -> None:
        now = _now()
        self._exec(
            "INSERT INTO sessions (id, created_at, updated_at, status, consent, config) VALUES (?,?,?,?,?,?)",
            (sid, now, now, "created", _dump(consent), _dump(config)),
        )

    def session(self, sid: str) -> sqlite3.Row | None:
        rows = self._exec("SELECT * FROM sessions WHERE id=?", (sid,))
        return rows[0] if rows else None

    def update_session(self, sid: str, **fields: Any) -> None:
        cols = ", ".join(f"{k}=?" for k in fields) + ", updated_at=?"
        vals = tuple(_dump(v) if isinstance(v, (BaseModel, dict, list)) else v for v in fields.values())
        self._exec(f"UPDATE sessions SET {cols} WHERE id=?", (*vals, _now(), sid))

    def sessions(self, statuses: list[str] | None = None) -> list[sqlite3.Row]:
        if statuses:
            q = ",".join("?" * len(statuses))
            return self._exec(f"SELECT * FROM sessions WHERE status IN ({q}) ORDER BY updated_at DESC", tuple(statuses))
        return self._exec("SELECT * FROM sessions ORDER BY updated_at DESC")

    def stale_sessions(self, max_age: timedelta) -> list[str]:
        cutoff = (datetime.now(timezone.utc) - max_age).isoformat()
        rows = self._exec(
            "SELECT id FROM sessions WHERE status IN ('created','analyzed','in_progress') AND updated_at < ?", (cutoff,)
        )
        return [r["id"] for r in rows]

    # ------------------------------------------------------------ evaluations

    def save_evaluation(self, sid: str, thread_id: str, kind: str, payload: BaseModel) -> bool:
        """진행 중인 세션일 때만 저장합니다. 세션이 끝나 데이터를 지운 뒤 늦게 끝난 평가가 다시 쓰이지 않도록."""
        with self.lock:
            cur = self.conn.execute(
                "INSERT OR REPLACE INTO evaluations SELECT ?,?,?,?,? "
                "WHERE EXISTS (SELECT 1 FROM sessions WHERE id=? AND status='in_progress')",
                (sid, thread_id, kind, _dump(payload), _now(), sid),
            )
            self.conn.commit()
            return cur.rowcount > 0

    def touch(self, sid: str) -> None:
        self._exec("UPDATE sessions SET updated_at=? WHERE id=?", (_now(), sid))

    def evaluations(self, sid: str) -> dict[str, tuple[str, dict]]:
        rows = self._exec("SELECT thread_id, kind, payload FROM evaluations WHERE session_id=?", (sid,))
        return {r["thread_id"]: (r["kind"], json.loads(r["payload"])) for r in rows}

    def delete_evaluations(self, sid: str) -> None:
        self._exec("DELETE FROM evaluations WHERE session_id=?", (sid,))

    # ------------------------------------------------------------ results

    def save_result(self, sid: str, summary: dict, detail: dict) -> None:
        self._exec("INSERT OR REPLACE INTO results VALUES (?,?,?,?)", (sid, _now(), _dump(summary), _dump(detail)))

    def results(self) -> list[dict]:
        rows = self._exec("SELECT session_id, completed_at, summary FROM results ORDER BY completed_at DESC")
        return [{"session_id": r["session_id"], "completed_at": r["completed_at"], **json.loads(r["summary"])} for r in rows]

    def result(self, sid: str) -> dict | None:
        rows = self._exec("SELECT * FROM results WHERE session_id=?", (sid,))
        if not rows:
            return None
        r = rows[0]
        return {"session_id": sid, "completed_at": r["completed_at"], "summary": json.loads(r["summary"]),
                "detail": json.loads(r["detail"])}

    def delete_result(self, sid: str) -> bool:
        with self.lock:
            cur = self.conn.execute("DELETE FROM results WHERE session_id=?", (sid,))
            self.conn.commit()
            return cur.rowcount > 0
