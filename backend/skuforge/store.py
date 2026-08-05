"""SQLite persistence for product records (stored as JSON documents)."""
import json
import sqlite3

from . import config
from .models import ProductRecord


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS records ("
        "id TEXT PRIMARY KEY, status TEXT, created_at TEXT, doc TEXT)"
    )
    return conn


def save(record: ProductRecord) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO records VALUES (?, ?, ?, ?)",
            (record.id, record.status.value, record.created_at,
             record.model_dump_json()),
        )


def get(record_id: str) -> ProductRecord | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT doc FROM records WHERE id = ?", (record_id,)
        ).fetchone()
    return ProductRecord.model_validate_json(row[0]) if row else None


def list_all() -> list[ProductRecord]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT doc FROM records ORDER BY created_at DESC"
        ).fetchall()
    return [ProductRecord.model_validate_json(r[0]) for r in rows]
