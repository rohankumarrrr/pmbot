from __future__ import annotations

import json
import sqlite3
import time
import uuid
from importlib import resources
from pathlib import Path
from typing import Any, Iterable


def now() -> int:
    return int(time.time())


def new_id() -> str:
    return uuid.uuid4().hex


class Ledger:
    def __init__(self, path: str | Path = "data/ledger.sqlite"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(resources.files("pmbot.ledger").joinpath("schema.sql").read_text())
        # Columns added after a ledger was first created (CREATE TABLE IF NOT EXISTS leaves an old table as it is).
        for table, column, kind in (("markets", "settlement_value", "REAL"),):
            if column not in {r["name"] for r in self.db.execute(f"PRAGMA table_info({table})")}:
                self.db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    # --- generic helpers ---------------------------------------------------

    def insert(self, table: str, row: dict[str, Any], replace: bool = False) -> None:
        self.insert_many(table, [row], replace)

    def insert_many(self, table: str, rows: Iterable[dict[str, Any]], replace: bool = False) -> None:
        rows = list(rows)
        if not rows:
            return
        cols = list(rows[0])
        verb = "INSERT OR REPLACE" if replace else "INSERT OR IGNORE"
        sql = f"{verb} INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})"
        self.db.executemany(sql, [[_enc(r.get(c)) for c in cols] for r in rows])
        self.db.commit()

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        return self.db.execute(sql, tuple(params)).fetchall()

    def one(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        return self.db.execute(sql, tuple(params)).fetchone()

    def execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        self.db.execute(sql, tuple(params))
        self.db.commit()

    # --- key/value state ---------------------------------------------------

    def get_state(self, key: str, default: Any = None) -> Any:
        row = self.one("SELECT value FROM kv WHERE key=?", [key])
        return json.loads(row["value"]) if row else default

    def set_state(self, key: str, value: Any) -> None:
        self.execute("INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)", [key, json.dumps(value)])

    def risk_event(self, kind: str, detail: str) -> None:
        self.execute("INSERT INTO risk_events (ts, kind, detail) VALUES (?, ?, ?)", [now(), kind, detail])


def _enc(v: Any) -> Any:
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (dict, list)):
        return json.dumps(v)
    return v
