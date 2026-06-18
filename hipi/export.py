"""CSV export for messages and call history."""

from __future__ import annotations

import csv
import io

from hipi.db.models import Database


def export_messages_csv(db: Database, limit: int = 10000) -> str:
    cmap = db.get_contact_map()
    rows = db.list_messages(limit=limit)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "timestamp", "peer", "contact_name", "direction", "status", "body"])
    for msg in rows:
        writer.writerow(
            [
                msg.id,
                msg.timestamp,
                msg.peer,
                cmap.get(msg.peer, ""),
                msg.direction,
                msg.status,
                msg.body,
            ]
        )
    return buf.getvalue()


def export_calls_csv(db: Database, limit: int = 10000) -> str:
    cmap = db.get_contact_map()
    rows = db.list_calls(limit=limit)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["id", "started_at", "ended_at", "peer", "contact_name", "direction", "state", "duration_sec"]
    )
    for call in rows:
        writer.writerow(
            [
                call.id,
                call.started_at,
                call.ended_at or "",
                call.peer,
                cmap.get(call.peer, ""),
                call.direction,
                call.state,
                call.duration_sec,
            ]
        )
    return buf.getvalue()
