from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .schema import TraceEvent


class JsonlTraceStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: TraceEvent) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")


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
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "insert into trace_events values (?, ?, ?, ?, ?, ?)",
                (
                    event.run_id,
                    event.task_id,
                    event.phase,
                    event.step,
                    event.message,
                    json.dumps(event.to_dict(), ensure_ascii=False),
                ),
            )
