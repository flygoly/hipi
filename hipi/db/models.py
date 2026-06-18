"""SQLite persistence for messages and calls."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hipi.config import DB_PATH, ensure_dirs
from hipi.util import normalize_number


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


@dataclass
class Contact:
    id: int
    name: str
    number: str
    notes: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "number": self.number,
            "notes": self.notes,
            "created_at": self.created_at,
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

            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                number TEXT NOT NULL UNIQUE,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_contacts_number ON contacts(number);
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

    # --- SMS forward settings ---

    def is_sms_forward_enabled(self) -> bool:
        return self.get_setting("sms_forward_enabled") == "1"

    def set_sms_forward_enabled(self, enabled: bool) -> None:
        self.set_setting("sms_forward_enabled", "1" if enabled else "0")

    def get_sms_forward_target(self) -> str | None:
        return self.get_setting("sms_forward_target")

    def set_sms_forward_target(self, target: str) -> None:
        self.set_setting("sms_forward_target", target)

    def get_sms_forward_config(self) -> dict[str, Any]:
        return {
            "enabled": self.is_sms_forward_enabled(),
            "target": self.get_sms_forward_target() or "",
            "webhook": self.get_sms_forward_webhook() or "",
            "webhook_secret_set": bool(self.get_sms_forward_webhook_secret()),
        }

    def get_sms_forward_webhook_secret(self) -> str | None:
        return self.get_setting("sms_forward_webhook_secret")

    def set_sms_forward_webhook_secret(self, secret: str) -> None:
        self.set_setting("sms_forward_webhook_secret", secret)

    def get_sms_forward_webhook(self) -> str | None:
        return self.get_setting("sms_forward_webhook")

    def set_sms_forward_webhook(self, url: str) -> None:
        self.set_setting("sms_forward_webhook", url)

    def count_unread_messages(self) -> int:
        row = self._conn.execute(
            """
            SELECT COUNT(*) AS c FROM messages
            WHERE direction = 'inbound' AND status = 'received'
            """
        ).fetchone()
        return int(row["c"]) if row else 0

    def import_contacts_batch(
        self, entries: list[tuple[str, str, str]], merge: bool = False
    ) -> dict[str, int]:
        imported = 0
        updated = 0
        skipped = 0
        for name, number, notes in entries:
            if not name.strip() or not number.strip():
                skipped += 1
                continue
            existing = self.get_contact_by_number(number)
            if existing:
                if merge:
                    new_notes = notes.strip() if notes.strip() else existing.notes
                    self.update_contact(existing.id, name.strip(), number, new_notes)
                    updated += 1
                else:
                    skipped += 1
                continue
            try:
                self.add_contact(name, number, notes)
                imported += 1
            except sqlite3.IntegrityError:
                skipped += 1
        return {"imported": imported, "updated": updated, "skipped": skipped}

    # --- Contacts ---

    def add_contact(self, name: str, number: str, notes: str = "") -> Contact:
        peer = normalize_number(number)
        created = _utc_now()
        cur = self._conn.execute(
            "INSERT INTO contacts(name, number, notes, created_at) VALUES (?, ?, ?, ?)",
            (name.strip(), peer, notes.strip(), created),
        )
        self._conn.commit()
        return Contact(id=cur.lastrowid, name=name.strip(), number=peer, notes=notes.strip(), created_at=created)

    def update_contact(self, contact_id: int, name: str, number: str, notes: str = "") -> None:
        peer = normalize_number(number)
        self._conn.execute(
            "UPDATE contacts SET name = ?, number = ?, notes = ? WHERE id = ?",
            (name.strip(), peer, notes.strip(), contact_id),
        )
        self._conn.commit()

    def delete_contact(self, contact_id: int) -> None:
        self._conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
        self._conn.commit()

    def list_contacts(self, query: str | None = None) -> list[Contact]:
        if query:
            q = f"%{query.strip()}%"
            rows = self._conn.execute(
                """
                SELECT * FROM contacts
                WHERE name LIKE ? OR number LIKE ?
                ORDER BY name COLLATE NOCASE
                """,
                (q, q),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM contacts ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [self._row_to_contact(r) for r in rows]

    def get_contact_by_number(self, number: str) -> Contact | None:
        peer = normalize_number(number)
        row = self._conn.execute("SELECT * FROM contacts WHERE number = ?", (peer,)).fetchone()
        return self._row_to_contact(row) if row else None

    def get_contact_map(self) -> dict[str, str]:
        rows = self._conn.execute("SELECT number, name FROM contacts").fetchall()
        return {r["number"]: r["name"] for r in rows}

    def resolve_name(self, number: str) -> str | None:
        contact = self.get_contact_by_number(number)
        return contact.name if contact else None

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

    def list_messages(
        self,
        limit: int = 100,
        peer: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> list[Message]:
        clauses: list[str] = []
        params: list[Any] = []
        if peer:
            clauses.append("peer = ?")
            params.append(peer)
        if since:
            clauses.append("timestamp >= ?")
            params.append(since)
        if until:
            clauses.append("timestamp <= ?")
            params.append(until)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT * FROM messages{where} ORDER BY timestamp DESC LIMIT ?",
            params,
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

    def list_calls(
        self,
        limit: int = 50,
        since: str | None = None,
        until: str | None = None,
    ) -> list[CallRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if since:
            clauses.append("started_at >= ?")
            params.append(since)
        if until:
            clauses.append("started_at <= ?")
            params.append(until)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT * FROM calls{where} ORDER BY started_at DESC LIMIT ?",
            params,
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

    @staticmethod
    def _row_to_contact(row: sqlite3.Row) -> Contact:
        return Contact(
            id=row["id"],
            name=row["name"],
            number=row["number"],
            notes=row["notes"],
            created_at=row["created_at"],
        )

    def close(self) -> None:
        self._conn.close()
