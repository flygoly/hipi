"""SQLite persistence for messages and calls."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hipi.config import DB_PATH, ensure_dirs


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Message:
    id: int
    peer: str
    body: str
    direction: str  # inbound | outbound
    status: str
    timestamp: str
    modem_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "peer": self.peer,
            "body": self.body,
            "direction": self.direction,
            "status": self.status,
            "timestamp": self.timestamp,
            "modem_path": self.modem_path,
        }


@dataclass
class CallRecord:
    id: int
    peer: str
    direction: str
    state: str
    started_at: str
    ended_at: str | None
    duration_sec: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "peer": self.peer,
            "direction": self.direction,
            "state": self.state,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_sec": self.duration_sec,
        }


class Database:
    def __init__(self, path: Path | None = None) -> None:
        ensure_dirs()
        self.path = path or DB_PATH
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                peer TEXT NOT NULL,
                body TEXT NOT NULL,
                direction TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'received',
                timestamp TEXT NOT NULL,
                modem_path TEXT,
                modem_sms_id TEXT UNIQUE
            );
            CREATE INDEX IF NOT EXISTS idx_messages_peer ON messages(peer);
            CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);

            CREATE TABLE IF NOT EXISTS calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                peer TEXT NOT NULL,
                direction TEXT NOT NULL,
                state TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                duration_sec INTEGER NOT NULL DEFAULT 0,
                modem_call_path TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_calls_started ON calls(started_at);

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self._conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._conn.commit()

    def is_onboarding_complete(self) -> bool:
        return self.get_setting("onboarding_complete") == "1"

    def mark_onboarding_complete(self) -> None:
        self.set_setting("onboarding_complete", "1")

    def add_message(
        self,
        peer: str,
        body: str,
        direction: str,
        status: str = "received",
        timestamp: str | None = None,
        modem_path: str | None = None,
        modem_sms_id: str | None = None,
    ) -> Message:
        ts = timestamp or _utc_now()
        cur = self._conn.execute(
            """
            INSERT INTO messages(peer, body, direction, status, timestamp, modem_path, modem_sms_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (peer, body, direction, status, ts, modem_path, modem_sms_id),
        )
        self._conn.commit()
        return Message(
            id=cur.lastrowid,
            peer=peer,
            body=body,
            direction=direction,
            status=status,
            timestamp=ts,
            modem_path=modem_path,
        )

    def update_message_status(self, message_id: int, status: str) -> None:
        self._conn.execute("UPDATE messages SET status = ? WHERE id = ?", (status, message_id))
        self._conn.commit()

    def update_message(self, message_id: int, status: str, body: str | None = None) -> None:
        if body is not None:
            self._conn.execute(
                "UPDATE messages SET status = ?, body = ? WHERE id = ?",
                (status, body, message_id),
            )
        else:
            self._conn.execute("UPDATE messages SET status = ? WHERE id = ?", (status, message_id))
        self._conn.commit()

    def get_message_by_id(self, message_id: int) -> Message | None:
        row = self._conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
        return self._row_to_message(row) if row else None

    def get_message_by_modem_sms_id(self, modem_sms_id: str) -> Message | None:
        row = self._conn.execute(
            "SELECT * FROM messages WHERE modem_sms_id = ?", (modem_sms_id,)
        ).fetchone()
        return self._row_to_message(row) if row else None

    def has_modem_sms(self, modem_sms_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM messages WHERE modem_sms_id = ?", (modem_sms_id,)
        ).fetchone()
        return row is not None

    def list_messages(self, limit: int = 100, peer: str | None = None) -> list[Message]:
        if peer:
            rows = self._conn.execute(
                """
                SELECT * FROM messages WHERE peer = ?
                ORDER BY timestamp DESC LIMIT ?
                """,
                (peer, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM messages ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def list_conversations(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT peer,
                   MAX(timestamp) AS last_timestamp,
                   (SELECT body FROM messages m2
                    WHERE m2.peer = m.peer
                    ORDER BY timestamp DESC LIMIT 1) AS last_body,
                   SUM(CASE WHEN direction = 'inbound' AND status = 'received' THEN 1 ELSE 0 END)
                       AS unread
            FROM messages m
            GROUP BY peer
            ORDER BY last_timestamp DESC
            """
        ).fetchall()
        return [
            {
                "peer": r["peer"],
                "last_timestamp": r["last_timestamp"],
                "last_body": r["last_body"],
                "unread": r["unread"],
            }
            for r in rows
        ]

    def add_call(
        self,
        peer: str,
        direction: str,
        state: str,
        modem_call_path: str | None = None,
    ) -> CallRecord:
        started = _utc_now()
        cur = self._conn.execute(
            """
            INSERT INTO calls(peer, direction, state, started_at, modem_call_path)
            VALUES (?, ?, ?, ?, ?)
            """,
            (peer, direction, state, started, modem_call_path),
        )
        self._conn.commit()
        return CallRecord(
            id=cur.lastrowid,
            peer=peer,
            direction=direction,
            state=state,
            started_at=started,
            ended_at=None,
            duration_sec=0,
        )

    def update_call(
        self,
        call_id: int,
        state: str,
        ended_at: str | None = None,
        duration_sec: int | None = None,
    ) -> None:
        self._conn.execute(
            """
            UPDATE calls SET state = ?,
                ended_at = COALESCE(?, ended_at),
                duration_sec = COALESCE(?, duration_sec)
            WHERE id = ?
            """,
            (state, ended_at, duration_sec, call_id),
        )
        self._conn.commit()

    def list_calls(self, limit: int = 50) -> list[CallRecord]:
        rows = self._conn.execute(
            "SELECT * FROM calls ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_call(r) for r in rows]

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> Message:
        return Message(
            id=row["id"],
            peer=row["peer"],
            body=row["body"],
            direction=row["direction"],
            status=row["status"],
            timestamp=row["timestamp"],
            modem_path=row["modem_path"],
        )

    @staticmethod
    def _row_to_call(row: sqlite3.Row) -> CallRecord:
        return CallRecord(
            id=row["id"],
            peer=row["peer"],
            direction=row["direction"],
            state=row["state"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            duration_sec=row["duration_sec"],
        )

    def close(self) -> None:
        self._conn.close()
