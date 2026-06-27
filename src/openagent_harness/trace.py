from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .env import sanitize_mapping
from .schema import TraceEvent


class JsonlTraceStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: TraceEvent) -> None:
        payload = _sanitize_event(event)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


class SqliteTraceStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                create table if not exists trace_events (
                    run_id text not null,
                    task_id text not null,
                    phase text not null,
                    step integer not null,
                    message text not null,
                    payload text not null
                )
                """
            )

    def append(self, event: TraceEvent) -> None:
        payload = _sanitize_event(event)
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "insert into trace_events values (?, ?, ?, ?, ?, ?)",
                (
                    payload["run_id"],
                    payload["task_id"],
                    payload["phase"],
                    payload["step"],
                    payload["message"],
                    json.dumps(payload, ensure_ascii=False),
                ),
            )


def _sanitize_event(event: TraceEvent) -> dict[str, object]:
    return sanitize_mapping(event.to_dict())
