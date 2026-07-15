from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError as exc:  # pragma: no cover - optional dependency fallback
    psycopg2 = None
    RealDictCursor = None
    PSYCOPG2_IMPORT_ERROR = exc
else:
    PSYCOPG2_IMPORT_ERROR = None


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def get_db_config() -> dict[str, str | int]:
    _load_dotenv()
    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname": os.getenv("POSTGRES_DB", "tgbot_storage"),
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", ""),
    }


def is_available() -> bool:
    _load_dotenv()
    return psycopg2 is not None and os.getenv("STORAGE_BACKEND", "postgres").lower() != "json"


def unavailable_reason() -> str:
    _load_dotenv()
    if os.getenv("STORAGE_BACKEND", "postgres").lower() == "json":
        return "STORAGE_BACKEND=json"
    if psycopg2 is None:
        return f"psycopg2 is not installed or cannot be imported: {PSYCOPG2_IMPORT_ERROR}"
    return ""


@contextmanager
def get_connection() -> Iterator:
    if psycopg2 is None:
        raise RuntimeError("psycopg2 is not installed")

    conn = psycopg2.connect(**get_db_config())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_cursor(dict_rows: bool = False) -> Iterator:
    with get_connection() as conn:
        cursor_factory = RealDictCursor if dict_rows and RealDictCursor else None
        cursor = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cursor
        finally:
            cursor.close()
