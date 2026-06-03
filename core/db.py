import os
import threading
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool as _pgpool
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL не задана в переменных окружения")


def get_connection():
    """Одиночное соединение (для init/миграций). В хендлерах — db_cursor()."""
    return psycopg2.connect(DATABASE_URL)


_pool = None
_pool_lock = threading.Lock()


def _get_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = _pgpool.ThreadedConnectionPool(1, 10, DATABASE_URL)
    return _pool


@contextmanager
def db_cursor():
    """Курсор из пула соединений — без накладных расходов на connect на каждый вызов.

    Коммитит при успехе, откатывает при исключении. Битые соединения
    отбраковываются (по conn.closed на следующем заходе).
    """
    pool = _get_pool()
    conn = pool.getconn()
    if conn.closed:
        pool.putconn(conn, close=True)
        conn = pool.getconn()

    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        yield cur
        conn.commit()
    except BaseException:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            cur.close()
        except Exception:
            pass
        pool.putconn(conn)


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS members (
            id SERIAL PRIMARY KEY,
            telegram_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Migration: per-member timezone (added later, so guard with IF NOT EXISTS)
    cursor.execute("ALTER TABLE members ADD COLUMN IF NOT EXISTS timezone TEXT")

    # Single-field модель: храним только согласованный через диалог текст.
    # Сырого/приватного поля нет by design — см. scripts/migrate_to_single_field.py
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS notes (
            id SERIAL PRIMARY KEY,
            author_id TEXT NOT NULL,
            author_name TEXT NOT NULL,

            text TEXT NOT NULL,
            tags TEXT NOT NULL,

            event_date DATE,
            event_time TIME,

            note_type TEXT DEFAULT 'note',
            status TEXT,
            fulfilled_at TIMESTAMP,
            fulfilled_by TEXT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (author_id) REFERENCES members(telegram_id)
        )
        """
    )

    # Migration: машинная дата/время события (для вопросов «что завтра»)
    cursor.execute("ALTER TABLE notes ADD COLUMN IF NOT EXISTS event_date DATE")
    cursor.execute("ALTER TABLE notes ADD COLUMN IF NOT EXISTS event_time TIME")

    # Migration: желания (note_type=wish + жизненный цикл)
    cursor.execute("ALTER TABLE notes ADD COLUMN IF NOT EXISTS note_type TEXT DEFAULT 'note'")
    cursor.execute("ALTER TABLE notes ADD COLUMN IF NOT EXISTS status TEXT")
    cursor.execute("ALTER TABLE notes ADD COLUMN IF NOT EXISTS fulfilled_at TIMESTAMP")
    cursor.execute("ALTER TABLE notes ADD COLUMN IF NOT EXISTS fulfilled_by TEXT")

    conn.commit()
    conn.close()
