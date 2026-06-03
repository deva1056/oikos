import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL не задана в переменных окружения")


def get_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn


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

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (author_id) REFERENCES members(telegram_id)
        )
        """
    )

    conn.commit()
    conn.close()
